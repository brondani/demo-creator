"""Offline desktop renderer. The storyboard is data; it never becomes code."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def seconds(path):
    result = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                      "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True)
    return float(result.strip())


def key(env, *keys):
    run(["xdotool", "key", "--clearmodifiers", *keys], env=env)


def pointer(env):
    for x in range(80, 620, 24):
        run(["xdotool", "mousemove", str(x), str(190 + x // 12)], env=env)
        time.sleep(0.028)
    run(["xdotool", "click", "1"], env=env)


def action(item, env):
    pointer(env)
    key(env, "ctrl+p")
    time.sleep(0.3)
    run(["xdotool", "type", "--clearmodifiers", "--delay", "6", "--", item["path"]], env=env)
    time.sleep(0.5)
    key(env, "Return")
    time.sleep(0.6)
    if item["type"] == "find_text":
        key(env, "ctrl+f")
        run(["xdotool", "type", "--clearmodifiers", "--delay", "6", "--", item["text"]], env=env)
        time.sleep(0.4)
        key(env, "Escape")
    elif item["type"] == "goto_line":
        key(env, "ctrl+g")
        run(["xdotool", "type", "--", str(item["line"])], env=env)
        key(env, "Return")
    elif item["type"] == "scroll_down":
        key(env, "Page_Down")


def wait_editor():
    # Electron's debugging endpoint is exposed only inside this container.
    import urllib.request
    for _ in range(100):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=0.5) as response:
                pages = json.load(response)
            if any(p.get("type") == "page" and p.get("webSocketDebuggerUrl") for p in pages):
                # Playwright is only used to verify readiness, never to drive the demo.
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5000)
                    ready = any(page.locator(".monaco-workbench").count() for context in browser.contexts for page in context.pages)
                    browser.close()
                if ready:
                    return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("VSCodium desktop did not become ready")


def main(script, output):
    data = json.loads(Path(script).read_text())
    # The host validates the full schema and Git evidence before launching us.
    # Recheck the action allowlist at this trust boundary.
    for scene in data["scenes"]:
        if scene["action"]["type"] not in ("open_file", "find_text", "goto_line", "scroll_down"):
            raise ValueError("unsupported action")
        path = Path("/work", scene["action"]["path"])
        if not path.is_file() or not path.resolve().is_relative_to(Path("/work")):
            raise ValueError("action path is not a file in the isolated tree")
    Path("/tmp/home").mkdir()
    Path("/tmp/runtime").mkdir(mode=0o700)
    settings = Path("/tmp/profile/User/settings.json")
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"security.workspace.trust.enabled": False,
                                    "workbench.startupEditor": "none", "editor.minimap.enabled": False,
                                    "update.mode": "none"}))
    env = os.environ.copy()
    env["DISPLAY"] = ":88"
    xvfb = subprocess.Popen(["Xvfb", ":88", "-screen", "0", "1280x720x24", "-nolisten", "tcp"], env=env)
    window_manager = None
    editor = None
    try:
        time.sleep(0.5)
        window_manager = subprocess.Popen(["openbox", "--sm-disable"], env=env,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        editor = subprocess.Popen(["/opt/codium/bin/codium", "--no-sandbox", "--disable-gpu", "--disable-updates",
                                   "--disable-dev-shm-usage",
                                   "--disable-extensions", "--skip-welcome", "--skip-release-notes",
                                   "--new-window", "--user-data-dir=/tmp/profile", "--extensions-dir=/tmp/extensions",
                                   "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222", "/work"], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_editor()
        tmp = Path("/tmp/scenes")
        tmp.mkdir()
        parts = []
        for i, scene in enumerate(data["scenes"]):
            wav = tmp / f"{i}.wav"
            run(["flite", "-voice", "kal", "-t", scene["narration"], "-o", str(wav)], env=env)
            audio_duration = seconds(wav)
            raw = tmp / f"{i}-video.webm"
            ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab",
                                   "-draw_mouse", "1", "-framerate", "15", "-video_size", "1280x720",
                                   "-i", ":88", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "6",
                                   "-an", str(raw)], env=env, stdin=subprocess.PIPE)
            start = time.monotonic()
            try:
                time.sleep(0.25)
                action(scene["action"], env)
                remaining = audio_duration + 0.9 - (time.monotonic() - start)
                if remaining > 0:
                    time.sleep(remaining)
            finally:
                ff.communicate(input=b"q", timeout=20)
            if ff.returncode:
                raise RuntimeError(f"screen capture failed for scene {i + 1}")
            length = seconds(raw)
            if length + 0.2 < audio_duration:
                raise RuntimeError(f"video is shorter than narration in scene {i + 1}")
            part = tmp / f"{i}.webm"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-i", str(wav),
                 "-filter_complex", f"[1:a]apad,atrim=duration={length:.3f}[a]", "-map", "0:v:0", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "libopus", "-b:a", "64k", "-t", f"{length:.3f}", str(part)], env=env)
            parts.append(part)
        listing = tmp / "concat.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-c", "copy", output], env=env)
    finally:
        if editor:
            editor.terminate()
            try: editor.wait(timeout=4)
            except subprocess.TimeoutExpired: editor.kill()
        if window_manager:
            window_manager.terminate()
            try: window_manager.wait(timeout=4)
            except subprocess.TimeoutExpired: window_manager.kill()
        xvfb.terminate()
        try: xvfb.wait(timeout=4)
        except subprocess.TimeoutExpired: xvfb.kill()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
