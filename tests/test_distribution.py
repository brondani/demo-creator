import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ghcr.io/brondani/demo-creator@sha256:" + "a" * 64
VERSION = runpy.run_path(str(ROOT / "demo"))["VERSION"].removesuffix("+dev")


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="demo-distribution-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "dist"
        result = self.package(VERSION, IMAGE, self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.archive = self.out / f"demo-creator-{VERSION}.tar.gz"
        with tarfile.open(self.archive) as tar:
            if sys.version_info >= (3, 12):
                tar.extractall(self.root, filter="data")
            else:
                tar.extractall(self.root)
        self.cli = self.root / f"demo-creator-{VERSION}" / "demo"
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.root / "home")
        Path(self.env["HOME"]).mkdir()

    def package(self, version, image, output):
        return subprocess.run(
            ["python3", str(ROOT / "scripts" / "package_release.py"), "--version", version,
             "--image", image, "--output", str(output)],
            text=True, capture_output=True,
        )

    def call(self, *args):
        return subprocess.run([str(self.cli), *args], env=self.env, text=True, capture_output=True)

    def fake_podman(self):
        bindir = self.root / "bin"
        bindir.mkdir()
        podman = bindir / "podman"
        podman.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["PODMAN_LOG"], "a") as output:
    output.write(json.dumps(args) + "\\n")
if args[0] == "info":
    print(os.environ.get("PODMAN_ROOTLESS", "true"))
elif args[:2] == ["image", "exists"]:
    if os.environ.get("PODMAN_STORAGE_ERROR"):
        print("storage unavailable", file=sys.stderr)
        sys.exit(125)
    sys.exit(0 if pathlib.Path(os.environ["PODMAN_IMAGE"]).exists() else 1)
elif args[0] == "pull":
    pathlib.Path(os.environ["PODMAN_IMAGE"]).touch()
""")
        podman.chmod(0o755)
        self.env["PATH"] = str(bindir) + os.pathsep + self.env.get("PATH", "")
        self.env["PODMAN_LOG"] = str(self.root / "podman.log")
        self.env["PODMAN_IMAGE"] = str(self.root / "image-present")

    def calls(self):
        return [json.loads(line) for line in Path(self.env["PODMAN_LOG"]).read_text().splitlines()]

    def test_release_is_reproducible_and_pins_image(self):
        other = self.root / "other"
        self.assertEqual(self.package(VERSION, IMAGE, other).returncode, 0)
        self.assertEqual(self.archive.read_bytes(), (other / self.archive.name).read_bytes())
        self.assertEqual(self.call("--version").stdout.strip(), f"demo {VERSION}")
        self.assertIn(f'IMAGE = "{IMAGE}"', self.cli.read_text())
        self.assertTrue((self.cli.parent / "skills" / "demo-plan" / "SKILL.md").is_file())

    def test_release_rejects_unpinned_image_and_mismatched_version(self):
        result = self.package(VERSION, "ghcr.io/brondani/demo-creator:latest", self.root / "bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned", result.stderr)
        result = self.package("999.999.999", IMAGE, self.root / "bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match", result.stderr)

    def test_user_install_is_repeatable_and_refuses_existing_command(self):
        prefix = self.root / "prefix"
        result = self.call("install", "--prefix", str(prefix))
        self.assertEqual(result.returncode, 0, result.stderr)
        link = prefix / "bin" / "demo"
        self.assertTrue(link.is_symlink())
        result = subprocess.run([str(link), "--version"], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.stdout.strip(), f"demo {VERSION}")
        self.assertEqual(self.call("install", "--prefix", str(prefix)).returncode, 0)

        previous = prefix / "share" / "demo-creator" / "0.0.9" / "demo"
        previous.parent.mkdir(parents=True)
        previous.write_text("previous installed version")
        link.unlink()
        link.symlink_to(previous)
        self.assertEqual(self.call("install", "--prefix", str(prefix)).returncode, 0)
        self.assertEqual(link.resolve(), (prefix / "share" / "demo-creator" / VERSION / "demo"))
        self.assertEqual(previous.read_text(), "previous installed version")

        other = self.root / "other-prefix"
        (other / "bin").mkdir(parents=True)
        existing = other / "bin" / "demo"
        existing.write_text("existing command")
        result = self.call("install", "--prefix", str(other))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace", result.stderr)
        self.assertEqual(existing.read_text(), "existing command")

    def test_skill_install_refuses_conflicts_without_partial_copy(self):
        conflict = Path(self.env["HOME"]) / ".copilot" / "skills" / "demo-render"
        conflict.mkdir(parents=True)
        (conflict / "SKILL.md").write_text("my customized skill")
        result = self.call("install-skills", "--for", "all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists and differs", result.stderr)
        self.assertEqual((conflict / "SKILL.md").read_text(), "my customized skill")
        self.assertFalse((Path(self.env["HOME"]) / ".agents" / "skills" / "demo-plan").exists())

    @unittest.skipIf(os.geteuid() == 0, "rootless setup requires a non-root test user")
    def test_setup_checks_rootless_before_pulling_and_reuses_image(self):
        self.fake_podman()
        result = self.call("setup", "--skills", "all")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        pull = next(i for i, command in enumerate(calls) if command[0] == "pull")
        self.assertIn(["unshare", "true"], calls[:pull])
        self.assertTrue(any(command[0] == "run" and "--network=none" in command
                            and any(arg.startswith("docker.io/library/busybox@sha256:") for arg in command)
                            for command in calls[:pull]))
        self.assertEqual(calls[pull], ["pull", IMAGE])
        self.assertTrue(any(command[0] == "run" and "--network=none" in command
                            and "--pull=never" in command and IMAGE in command for command in calls[pull + 1:]))
        skill = Path(self.env["HOME"]) / ".agents" / "skills" / "demo-plan" / "SKILL.md"
        self.assertTrue(skill.is_file())

        Path(self.env["PODMAN_LOG"]).unlink()
        result = self.call("setup", "--skills", "all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(command[0] == "pull" for command in self.calls()))
        self.assertFalse(any(any(arg.startswith("docker.io/library/busybox@sha256:") for arg in command)
                             for command in self.calls()))

    @unittest.skipIf(os.geteuid() == 0, "rootless setup requires a non-root test user")
    def test_setup_reports_rootless_and_storage_failures(self):
        self.fake_podman()
        self.env["PODMAN_ROOTLESS"] = "false"
        result = self.call("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not running rootless", result.stderr)
        self.assertFalse(any(command[0] == "pull" for command in self.calls()))

        self.env["PODMAN_ROOTLESS"] = "true"
        self.env["PODMAN_STORAGE_ERROR"] = "1"
        result = self.call("setup")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("storage unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
