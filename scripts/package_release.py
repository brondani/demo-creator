#!/usr/bin/env python3
"""Package a CLI release pinned to the renderer image published by CI."""
import argparse
import gzip
import io
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent
IMAGE_RE = re.compile(r"ghcr\.io/brondani/demo-creator@sha256:[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release version without the v prefix")
    parser.add_argument("--image", required=True, help="published renderer image by sha256 digest")
    parser.add_argument("--output", type=Path, required=True, help="output directory")
    args = parser.parse_args()
    if not VERSION_RE.fullmatch(args.version):
        parser.error("version must be a numeric MAJOR.MINOR.PATCH")
    if not IMAGE_RE.fullmatch(args.image):
        parser.error("image must be the demo-creator GHCR image pinned by sha256 digest")

    cli = (ROOT / "demo").read_text()
    version_line = f'VERSION = "{args.version}+dev"'
    image_line = 'IMAGE = "localhost/demo-creator:1"'
    if cli.count(version_line) != 1 or cli.count(image_line) != 1:
        parser.error("release version does not match the development CLI or its image marker")
    cli = cli.replace(version_line, f'VERSION = "{args.version}"')
    cli = cli.replace(image_line, f'IMAGE = "{args.image}"')

    files = [
        ("demo", cli.encode(), 0o755),
        ("README.md", (ROOT / "README.md").read_bytes(), 0o644),
        ("LICENSE", (ROOT / "LICENSE").read_bytes(), 0o644),
    ]
    for name in ("demo-plan", "demo-render"):
        files.append((f"skills/{name}/SKILL.md",
                      (ROOT / ".github" / "skills" / name / "SKILL.md").read_bytes(), 0o644))

    args.output.mkdir(parents=True, exist_ok=True)
    archive_path = args.output / f"demo-creator-{args.version}.tar.gz"
    root = f"demo-creator-{args.version}"
    with archive_path.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path, content, mode in files:
                    info = tarfile.TarInfo(f"{root}/{path}")
                    info.size = len(content)
                    info.mode = mode
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(content))
    print(archive_path)


if __name__ == "__main__":
    main()
