#!/usr/bin/env python3
"""Small end-to-end fixture; planning uses a deterministic Codex stub."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import wave

DEMO = Path(__file__).resolve().with_name("demo")


def cmd(args, **kw):
    result = subprocess.run(args, text=True, capture_output=True, **kw)
    if result.returncode:
        raise RuntimeError(f"{' '.join(map(str, args))}: {result.stderr.strip()}")
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="demo-smoke-") as tmp:
        root = Path(tmp)
        repo = root / "fixture"
        repo.mkdir()
        cmd(["git", "init", "-q", str(repo)])
        for name, value in (("user.name", "Smoke"), ("user.email", "smoke@example.invalid")):
            cmd(["git", "-C", str(repo), "config", name, value])
        source = repo / "hello.py"
        source.write_text("def greeting():\n    return 'hello'\n")
        (repo / "link.py").symlink_to("hello.py")
        cmd(["git", "-C", str(repo), "add", "-A"])
        cmd(["git", "-C", str(repo), "commit", "-qm", "initial"])
        source.write_text("def greeting():\n    return 'hello from the revised function'\n")
        cmd(["git", "-C", str(repo), "commit", "-qam", "revise greeting"])
        stub_dir = root / "bin"
        stub_dir.mkdir()
        stub = stub_dir / "codex"
        stub.write_text("""#!/usr/bin/env python3
import json,sys
args=sys.argv
out=args[args.index('--output-last-message')+1]
prompt=sys.stdin.read()
action=({'type':'find_text','path':'hello.py','text':'hello from the revised function'}
        if 'hello from the revised function' in prompt else {'type':'open_file','path':'hello.py'})
data={'scenes':[{'kind':'source_walkthrough','narration':'The greeting function now returns the revised text.',
 'evidence':{'path':'hello.py','symbol':'greeting'},
 'action':action,
 'expected':'The revised greeting string is visible in the editor.'}]}
open(out,'w').write(json.dumps(data))
""")
        stub.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{stub_dir}:{env['PATH']}"
        draft = root / "draft.json"
        cmd([str(DEMO), "plan", "--commit", "HEAD", "--out", str(draft)], cwd=repo, env=env)
        data = json.loads(draft.read_text())
        assert data["version"] == 1 and len(data["scenes"]) == 1
        assert not list(root.glob("*.webm")), "planning unexpectedly rendered a video"
        root_draft = root / "root.json"
        cmd([str(DEMO), "plan", "--commit", "HEAD^", "--out", str(root_draft)], cwd=repo, env=env)
        root_data = json.loads(root_draft.read_text())
        assert root_data["revision"]["kind"] == "commit"
        assert root_data["revision"]["base"] != root_data["revision"]["head"]
        pr_draft = root / "pr.json"
        cmd([str(DEMO), "plan", "--base", "HEAD^", "--head", "HEAD", "--out", str(pr_draft)], cwd=repo, env=env)
        pr_data = json.loads(pr_draft.read_text())
        assert pr_data["revision"]["kind"] == "pr"
        assert pr_data["revision"]["base"] == root_data["revision"]["head"]
        source.write_text("UNCOMMITTED LIVE CHECKOUT CONTENT\n")
        isolated = root / "isolated"
        isolated.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(repo)
            runpy.run_path(str(DEMO))["export_tree"](data["revision"]["head"], isolated)
        finally:
            os.chdir(previous)
        assert "revised function" in (isolated / "hello.py").read_text()
        assert "UNCOMMITTED" not in (isolated / "hello.py").read_text()
        assert (isolated / "link.py").is_symlink()
        edited = ("The reviewer changed this exact spoken line for the smoke test. "
                  "This longer narration describes the revised greeting text, and the video must stay visible "
                  "until the final spoken word finishes.")
        data["scenes"][0]["narration"] = edited
        draft.write_text(json.dumps(data))
        invalid = root / "invalid.json"
        bad_data = json.loads(draft.read_text())
        bad_data["scenes"][0]["action"]["type"] = "shell"
        invalid.write_text(json.dumps(bad_data))
        rejected = subprocess.run([str(DEMO), "render", "--script", str(invalid), "--out", str(root / "bad.webm")],
                                  cwd=repo, capture_output=True, text=True)
        assert rejected.returncode != 0 and "invalid editor action" in rejected.stderr
        print("PASS: plan produced a valid draft and stopped before rendering")
        preflight = subprocess.run([str(DEMO), "preflight"], cwd=repo, capture_output=True, text=True)
        if preflight.returncode:
            print("GUI smoke unavailable:", preflight.stderr.strip())
            print("On a rootless Podman VM: podman build --pull=always -t localhost/demo-creator:1 -f Containerfile . && ./smoke.py")
            return 2
        output = root / "demo.webm"
        cmd([str(DEMO), "render", "--script", str(draft), "--out", str(output)], cwd=repo)
        # ffprobe/ffmpeg are available inside the image; mount the output read-only.
        def media(*args, binary=False):
            return subprocess.run(["podman", "run", "--rm", "--pull=never", "--network=none", "--userns=keep-id",
                                   "--user", f"{os.getuid()}:{os.getgid()}", "--mount",
                                   f"type=bind,src={output},dst=/video.webm,ro=true", "localhost/demo-creator:1", *args],
                                  check=True, capture_output=True, text=not binary)
        info = json.loads(media("ffprobe", "-v", "error", "-show_streams", "-of", "json", "/video.webm").stdout)
        codecs = {s["codec_type"]: s["codec_name"] for s in info["streams"]}
        assert codecs.get("video") == "vp9" and codecs.get("audio") == "opus", codecs
        pcm = media("ffmpeg", "-v", "error", "-i", "/video.webm", "-vn", "-f", "s16le", "-ac", "1", "-", binary=True).stdout
        assert any(pcm[i:i+2] != b"\0\0" for i in range(0, len(pcm), 2)), "audio is silent"
        frames = media("ffmpeg", "-v", "error", "-ss", "0.4", "-t", "0.7", "-i", "/video.webm",
                       "-vf", "crop=540:110:80:180,format=gray", "-f", "rawvideo", "-", binary=True).stdout
        frame_size = 540 * 110
        images = [frames[i:i+frame_size] for i in range(0, len(frames), frame_size) if len(frames[i:i+frame_size]) == frame_size]
        assert len(images) >= 3 and len(set(images)) >= 3, "cursor motion was not visible in recorded frames"
        # The manually edited narration must determine scene duration.
        reference = root / "edited.wav"
        cmd(["podman", "run", "--rm", "--pull=never", "--network=none", "--userns=keep-id",
             "--user", f"{os.getuid()}:{os.getgid()}", "--mount",
             f"type=bind,src={root},dst=/scratch,rw=true", "localhost/demo-creator:1",
             "flite", "-voice", "kal", "-t", edited, "-o", "/scratch/edited.wav"])
        with wave.open(str(reference)) as wav:
            expected_duration = wav.getnframes() / wav.getframerate()
        duration = float(media("ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "default=noprint_wrappers=1:nokey=1", "/video.webm").stdout.strip())
        assert duration >= expected_duration, "reviewed narration appears to have been cut off"
        print("PASS: reviewed narration rendered; VP9 video, Opus non-silent audio, moving cursor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
