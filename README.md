# Demo creator

`demo` makes a short narrated **source walkthrough** from a Git commit or a locally available PR head. It never calls a model while rendering. A walkthrough shows changed code and should not be described as proof that the application behaves differently. The current action allowlist does not run the target project, so a storyboard claiming a demonstrated behavior change is rejected.

## Install a release

Run as an ordinary user on Linux x86-64 with Git, Python 3.10+, and preconfigured **rootless Podman**. Planning also requires the Codex CLI to be installed and authenticated. Once a release is published, download its versioned archive and checksum:

```sh
VERSION=0.1.1
BASE="https://github.com/brondani/demo-creator/releases/download/v$VERSION"
curl -fLO "$BASE/demo-creator-$VERSION.tar.gz"
curl -fLO "$BASE/SHA256SUMS"
sha256sum --check SHA256SUMS
tar -xzf "demo-creator-$VERSION.tar.gz"
"./demo-creator-$VERSION/demo" install
~/.local/bin/demo setup --skills all
```

Add `~/.local/bin` to `PATH` if necessary. `demo install` keeps releases under `~/.local/share/demo-creator/`, and switches its own managed `demo` link when upgrading; it will not replace another command. The checksum verifies the download against the release's checksum file, not an independent signature. To choose only one agent, replace `--skills all` with `--skills codex` or `--skills vscode`; omit it to install no skills. Existing customized skills are never overwritten.

`demo setup` checks rootless Podman before pulling the release's exact renderer image digest. It may first pull a small, digest-pinned BusyBox image to verify that an offline container can launch. Setup needs network access; rendering does not. If rootless containers cannot run on the VM, setup reports the error and cannot fix the host configuration. There is no host sudo, package installation prompt, privileged container, display mount, or Docker socket. Rootless Docker is not supported.

## Plan and render

From the target Git repository:

```sh
cd /path/to/target-repo
demo plan --commit HEAD --out draft.json
# Or: demo plan --base origin/main --head my-pr --out draft.json
# Review and edit draft.json, especially every factual claim and narration line.
demo render --script draft.json --out demo.webm
```

`render` validates the entire storyboard and its Git evidence before launching the container. The recorded head is exported with `git archive` into a temporary tree; the live checkout is never mounted. The container runs offline with a private Xvfb display, fresh VSCodium profile, non-root UID, read-only root filesystem, no capabilities, and only the exported tree, storyboard, and output directory mounted. No home directory, credentials, or host display are mounted.

The draft records immutable Git object IDs. For a normal commit, `base` is its first parent; for a root commit it is the empty tree ID. For a PR, `base` is the merge base of the supplied refs and `head` is the resolved head commit. The list of changed files is checked again at render time. Keep the source repository and those objects available until rendering finishes.

Each scene has `kind: source_walkthrough`, `narration`, `evidence` (`path`, optional `symbol` as an empty string), one `action`, and `expected` (what should appear in the editor). Actions are limited to `open_file`, `find_text`, `goto_line`, and `scroll_down`. Paths must be changed files in the recorded revision. Narration is synthesized locally with Flite's bundled `kal` voice, one scene at a time. Actual WAV durations determine capture time. FFmpeg records the visible X11 cursor and muxes VP9 video with Opus audio into WebM. Playwright checks that the real VSCodium desktop is ready; xdotool provides pointer and keyboard input.

## Agent chat skills

The `demo-plan` and `demo-render` skills guide an agent through the same two-step workflow, with explicit review and approval before rendering. Install them during setup as shown above, or separately without Podman:

```sh
demo install-skills --for all
# Or use --for codex or --for vscode.
```

Start a fresh chat in the target repository. In VS Code Copilot, select `/demo-plan` or `/demo-render`; in Codex CLI or its IDE extension, use `/skills` or mention `$demo-plan` or `$demo-render`. Skills may also be selected automatically. Planning invokes authenticated Codex even when started from VS Code. In this source checkout, VS Code discovers project skills in `.github/skills/` and Codex discovers the links in `.agents/skills/`.

## Development and releases

To build the image from source on a machine that already has rootless Podman configured:

```sh
./demo preflight
podman build --pull=always -t localhost/demo-creator:1 -f Containerfile .
./demo setup
python3 -m unittest discover -s tests -v
./smoke.py
```

The development CLI reports `0.1.1+dev` and uses the local image; `demo install` accepts packaged releases only. `./smoke.py --plan-only` checks planning without a container. The full smoke test uses a tiny local Git fixture and a deterministic Codex stub, edits narration, and checks the rendered WebM's codecs, audio, duration, and changing cursor frames.

The release workflow runs on a `vMAJOR.MINOR.PATCH` tag matching the development CLI version. It tests the CLI and local renderer before pushing an image to GHCR, embeds that image's immutable digest in the release archive, tests the packaged CLI and image, and publishes the release only if the image is publicly pullable. A new GHCR package may initially be private: make the `demo-creator` container package public in GitHub Packages, then rerun the Release workflow for the tag. A published release is never overwritten by the workflow.

## License

The project source is licensed under [Apache-2.0](LICENSE). The renderer image combines separately licensed components; see below before redistributing it.

## Version and license notes

The image uses Debian `12.12-slim` with packages selected from the dated `20260101T000000Z` Debian archive, VSCodium `1.105.17075` with a checked SHA-256 digest, and Playwright Python `1.56.0` with pinned, hash-checked Python dependencies. Debian package versions are frozen by the archive date. The image is a collection of components with separate licenses:

| Component | License | Source |
| --- | --- | --- |
| VSCodium / Code - OSS | MIT | [VSCodium](https://github.com/VSCodium/vscodium) |
| Playwright | Apache-2.0 | [Playwright license](https://github.com/microsoft/playwright/blob/main/LICENSE) |
| pyee | MIT | [pyee license](https://github.com/jfhbrook/pyee/blob/main/LICENSE) |
| greenlet | MIT and Python-2.0 | [greenlet licenses](https://github.com/python-greenlet/greenlet/blob/master/LICENSE) |
| typing-extensions | PSF-2.0 | [typing-extensions license](https://github.com/python/typing_extensions/blob/main/LICENSE) |
| xdotool input driver | BSD-3-Clause | [xdotool copyright](https://github.com/jordansissel/xdotool/blob/main/COPYRIGHT) |
| Flite engine and bundled `kal` voice | CMU permissive license; `kal` is free for use | [Flite COPYING](https://github.com/festvox/flite/blob/master/COPYING), [Festival voice note](https://github.com/festvox/festival/blob/master/COPYING) |
| FFmpeg recorder/muxer | LGPL-2.1-or-later in its base configuration; Debian's build may enable GPL components | [FFmpeg license](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md) |
| libvpx VP9 codec | BSD-3-Clause | [libvpx](https://github.com/webmproject/libvpx) |
| libopus Opus codec | BSD-style | [Opus license](https://github.com/xiph/opus/blob/main/LICENSE_PLEASE_READ.txt) |

FFmpeg is the principal non-permissive runtime dependency. Debian's X11, GTK, Electron, and other system libraries also carry their own licenses; no single license is claimed for the image. Inspect the built image's `/usr/share/doc/*/copyright` and `ffmpeg -buildconf` before redistributing it.
