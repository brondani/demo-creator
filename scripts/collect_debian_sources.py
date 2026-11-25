#!/usr/bin/env python3
"""Download the exact Debian sources for the packages installed in an image."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

NAME = re.compile(r"[a-z0-9][a-z0-9+.-]+\Z")
VERSION = re.compile(r"(?:[0-9]+:)?[0-9][a-zA-Z0-9.+~:-]*\Z")
HASH = re.compile(r"[0-9a-f]{40}\Z")
BASE = "https://snapshot.debian.org"


def sources(inventory):
    packages = set()
    for line in inventory.splitlines():
        fields = line.split("\t")
        if len(fields) != 5:
            raise ValueError(f"invalid package inventory line: {line!r}")
        status, _, _, name, version = fields
        if status != "installed":
            continue
        if not NAME.fullmatch(name) or not VERSION.fullmatch(version):
            raise ValueError(f"invalid Debian source package: {name!r} {version!r}")
        packages.add((name, version))
    if not packages:
        raise ValueError("the package inventory contains no installed packages")
    return sorted(packages)


def open_url(url):
    for attempt in range(4):
        try:
            return urlopen(Request(url, headers={"User-Agent": "demo-creator-source-collector/1"}), timeout=120)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
        print(f"Retrying {url} after a download error", file=sys.stderr)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"could not download {url}")


def collect(package, output):
    name, version = package
    metadata_url = f"{BASE}/mr/package/{quote(name, safe='')}/{quote(version, safe='')}/srcfiles?fileinfo=1"
    with open_url(metadata_url) as response:
        metadata = json.load(response)
    if metadata["package"] != name or metadata["version"] != version:
        raise ValueError(f"snapshot returned the wrong source package for {name} {version}")
    records = metadata["result"]
    if not records:
        raise ValueError(f"no source files found for {name} {version}")
    folder = output / name / quote(version, safe="")
    folder.mkdir(parents=True)
    filenames = set()
    for record in records:
        digest = record["hash"]
        if not HASH.fullmatch(digest):
            raise ValueError(f"invalid snapshot hash for {name} {version}")
        info = next((entry for entry in metadata["fileinfo"][digest]
                     if entry["archive_name"] in ("debian", "debian-security")), None)
        if info is None:
            continue
        filename = info["name"]
        if Path(filename).name != filename or filename in (".", "..") or filename in filenames:
            raise ValueError(f"invalid or duplicate source filename: {filename!r}")
        filenames.add(filename)
        target = folder / filename
        checksum = hashlib.sha1()
        size = 0
        with open_url(f"{BASE}/file/{digest}") as response, target.open("xb") as file:
            while chunk := response.read(1024 * 1024):
                checksum.update(chunk)
                size += len(chunk)
                file.write(chunk)
        if checksum.hexdigest() != digest or size != info["size"]:
            raise ValueError(f"source file failed integrity check: {name} {version} {filename}")
    if not any(filename.endswith(".dsc") for filename in filenames):
        raise ValueError(f"source package has no .dsc file: {name} {version}")
    print(f"Collected {name} {version}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--image", help="local Podman image to inventory offline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.image:
        inventory = subprocess.run(
            ["podman", "run", "--rm", "--pull=never", "--network=none", args.image,
             "dpkg-query", "-W",
             "-f=${db:Status-Status}\\t${binary:Package}\\t${Version}\\t${source:Package}\\t${source:Version}\\n"],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
    else:
        inventory = args.manifest.read_text()
    packages = sources(inventory)
    args.output.mkdir(parents=True)
    (args.output / "installed-packages.tsv").write_text(inventory)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for _ in executor.map(lambda package: collect(package, args.output), packages):
            pass


if __name__ == "__main__":
    main()
