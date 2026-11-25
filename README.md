# Demo creator

`demo` makes a short narrated **source walkthrough** from a Git commit or a locally available PR head. It never calls a model while rendering. A walkthrough shows changed code and should not be described as proof that the application behaves differently. The current action allowlist does not run the target project, so a storyboard claiming a demonstrated behavior change is rejected.

## Requirements and use

Run as an ordinary user on Linux x86-64 with Git, Python 3.10+, Codex CLI (authenticated for `plan`), and preconfigured **rootless Podman**. There is no host package installer, sudo step, display mount, or Docker socket. The build is non-interactive:

```sh
cd /path/to/demo-creator
./demo preflight
podman build --pull=always -t localhost/demo-creator:1 -f Containerfile .
./smoke.py
cd /path/to/target-repo
/path/to/demo-creator/demo plan --commit HEAD --out draft.json
# Or: /path/to/demo-creator/demo plan --base origin/main --head my-pr --out draft.json
# Review and edit draft.json, especially every factual claim and narration line.
/path/to/demo-creator/demo render --script draft.json --out demo.webm
```

`preflight` checks Podman's rootless mode, user namespaces, and a real offline container launch. It pulls `docker.io/library/busybox:1.36.1` on first use, so preflight needs registry access once. It fails clearly when this VM cannot run rootless containers. `render` validates the entire storyboard and its Git evidence before launching the container. The recorded head is exported with `git archive` into a temporary tree; the live checkout is never mounted. The container runs offline with a private Xvfb display, fresh VSCodium profile, non-root UID, read-only root filesystem, no capabilities, and only the exported tree, storyboard, and output directory mounted. No home directory, credentials, or host display are mounted. Rootless Docker is not supported by this CLI.

The draft records immutable Git object IDs. For a normal commit, `base` is its first parent; for a root commit it is the empty tree ID. For a PR, `base` is the merge base of the supplied refs and `head` is the resolved head commit. The list of changed files is checked again at render time. Keep the source repository and those objects available until rendering finishes.

Each scene has `kind: source_walkthrough`, `narration`, `evidence` (`path`, optional `symbol` as an empty string), one `action`, and `expected` (what should appear in the editor). Actions are limited to `open_file`, `find_text`, `goto_line`, and `scroll_down`. Paths must be changed files in the recorded revision. Narration is synthesized locally with Flite's bundled `kal` voice, one scene at a time. Actual WAV durations determine capture time. FFmpeg records the visible X11 cursor and muxes VP9 video with Opus audio into WebM. Playwright checks that the real VSCodium desktop is ready; xdotool provides pointer and keyboard input.

The smoke test uses a tiny local Git fixture and a deterministic Codex stub to check the `plan` contract without consuming a model call. It edits narration manually, then uses the real container to check that rendering lasts through the edited speech, that the result has decodable VP9 video and non-silent Opus audio, and that frames change during visible cursor motion. A separate live Codex plan can be checked with the first command above.

## Version and license notes

The image uses Debian `12.12-slim` with packages selected from the dated `20260101T000000Z` Debian archive, VSCodium `1.105.17075` with a checked SHA-256 digest, and Playwright Python `1.56.0`. Debian package versions are frozen by the archive date. The image is a collection of components with separate licenses:

| Component | License | Source |
| --- | --- | --- |
| VSCodium / Code - OSS | MIT | [VSCodium](https://github.com/VSCodium/vscodium) |
| Playwright | Apache-2.0 | [Playwright license](https://github.com/microsoft/playwright/blob/main/LICENSE) |
| xdotool input driver | BSD-3-Clause | [xdotool copyright](https://github.com/jordansissel/xdotool/blob/main/COPYRIGHT) |
| Flite engine and bundled `kal` voice | CMU permissive license; `kal` is free for use | [Flite COPYING](https://github.com/festvox/flite/blob/master/COPYING), [Festival voice note](https://github.com/festvox/festival/blob/master/COPYING) |
| FFmpeg recorder/muxer | LGPL-2.1-or-later in its base configuration; Debian's build may enable GPL components | [FFmpeg license](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md) |
| libvpx VP9 codec | BSD-3-Clause | [libvpx](https://github.com/webmproject/libvpx) |
| libopus Opus codec | BSD-style | [Opus license](https://github.com/xiph/opus/blob/main/LICENSE_PLEASE_READ.txt) |

FFmpeg is the principal non-permissive runtime dependency. Debian's X11, GTK, Electron, and other system libraries also carry their own licenses; no single license is claimed for the image. Inspect the built image's `/usr/share/doc/*/copyright` and `ffmpeg -buildconf` before redistributing it.
