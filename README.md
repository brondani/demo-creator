# Demo creator

`demo` makes a short narrated **source walkthrough** from a Git commit or a locally available PR head. It never calls a model while rendering. A walkthrough shows changed code and should not be described as proof that the application behaves differently. The current action allowlist does not run the target project, so a storyboard claiming a demonstrated behavior change is rejected.

## Install a release

Run as an ordinary user on Linux x86-64 with Git, Python 3.10+, and preconfigured **rootless Podman**. Planning also requires the Codex CLI to be installed and authenticated. Once a release is published, download its versioned archive and checksum:

```sh
VERSION=0.1.2
BASE="https://github.com/brondani/demo-creator/releases/download/v$VERSION"
curl -fLO "$BASE/demo-creator-$VERSION.tar.gz"
curl -fLO "$BASE/SHA256SUMS"
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf "demo-creator-$VERSION.tar.gz"
"./demo-creator-$VERSION/demo" install
~/.local/bin/demo setup --skills all
```

Add `~/.local/bin` to `PATH` if necessary. `demo install` keeps releases under `~/.local/share/demo-creator/`, and switches its own managed `demo` link when upgrading; it will not replace another command. The checksum verifies the download against the release's checksum file, not an independent signature. To choose only one agent, replace `--skills all` with `--skills codex` or `--skills vscode`; omit it to install no skills. Existing customized skills are never overwritten. On upgrade, if an existing skill differs, review and back up that skill before moving it aside and rerunning `demo install-skills --for all`.

`demo setup` checks rootless Podman before pulling the release's exact renderer image digest. It may first pull a small, digest-pinned BusyBox image to verify that an offline container can launch. Setup needs network access; rendering does not. If rootless containers cannot run on the VM, setup reports the error and cannot fix the host configuration. There is no host sudo, package installation prompt, privileged container, display mount, or Docker socket. Rootless Docker is not supported.

## Windows PC using WSL2

The CLI and renderer do not run natively on Windows. The intended route on an **x86-64** Windows 10/11 PC is Ubuntu on WSL2 with rootless Podman. WSL2 requires hardware virtualization and may be restricted by your organization. The Linux container is tested in hosted CI; this WSL2 setup has not yet been tested end-to-end on a Windows PC.

1. In **PowerShell as administrator**, install Ubuntu and restart Windows if prompted:

   ```powershell
   wsl --install -d Ubuntu-24.04
   wsl --list --verbose
   ```

   Create a normal Linux user when Ubuntu first starts. Verify that Ubuntu uses WSL version **2**. If WSL is already installed, see the [Microsoft WSL installation guide](https://learn.microsoft.com/windows/wsl/install).

2. Open the **Ubuntu** terminal, not PowerShell. Install prerequisites, then install and sign in to Codex and GitHub CLI in WSL:

   ```sh
   sudo apt update
   sudo apt install -y git curl ca-certificates python3 podman uidmap slirp4netns fuse-overlayfs gh nodejs npm
   export PATH="$HOME/.local/bin:$PATH"
   npm install --global --prefix "$HOME/.local" @openai/codex
   codex login
   gh auth login --web --git-protocol https
   ```

   If a browser login cannot open, `codex login --device-auth` is an alternative when your account permits it. Repeat the `PATH` export in new terminals, or add it to your shell profile. Codex needs a permitted account and network access; planning sends the selected diff to Codex. The GitHub login is needed for the PR and Actions commands below.

3. Still in Ubuntu, follow [Install a release](#install-a-release) above. Run `demo setup --skills all` as your **ordinary Linux user**, never with sudo. It verifies rootless Podman and downloads the prebuilt renderer. If setup reports a user-namespace error, ask your administrator to configure rootless Podman; do not switch to a privileged container. Use the Linux filesystem (for example `~/src`) for your checkout and container storage.

4. Clone the PR's **base repository**, fetch its head, and create the storyboard. Replace the three placeholders:

   ```sh
   OWNER=Open-CMSIS-Pack
   REPO=vscode-cmsis-solution
   PR=123                       # replace with the PR number
   mkdir -p ~/src && cd ~/src
   gh repo clone "$OWNER/$REPO" # skip if you already have this checkout
   cd "$REPO"
   gh pr checkout "$PR" --detach
   BASE=$(gh pr view "$PR" --json baseRefName --jq .baseRefName)
   git fetch origin "$BASE:refs/remotes/origin/$BASE"
   demo plan --base "origin/$BASE" --head HEAD --out draft.json
   ```

   Review and edit `draft.json`. After approving that specific storyboard, run:

   ```sh
   demo render --script draft.json --out demo.webm
   explorer.exe .
   ```

   Windows File Explorer opens the WSL directory; the WebM can be opened in Edge. Keep the Git repository and recorded commits until rendering finishes. Large diffs over 100 KB are rejected; select a smaller revision instead.

5. To use agent chat instead, open the repository in a VS Code **WSL** window and start a fresh chat. Ask `/demo-plan` to use the PR base and head, with `~/.local/bin/demo` as the executable. After reviewing the draft, explicitly approve it and ask `/demo-render` to render it. The CLI commands above are also available if skill discovery differs in your VS Code configuration.

### Optional: check a VSIX in WSL

`demo prepare` needs a **Linux x64** VS Code distribution inside WSL; the Windows VS Code executable and Remote WSL server are not sufficient. For example, download the official VS Code 1.109.5 Linux archive used by CI:

```sh
VSCODE_DIR="$HOME/.local/share/demo-creator/vscode-1.109.5"
mkdir -p "$VSCODE_DIR" "$HOME/.cache"
curl -fsSL https://update.code.visualstudio.com/1.109.5/linux-x64/stable -o "$HOME/.cache/demo-vscode-1.109.5.tar.gz"
echo "70160103c0dda50f651a37ee27a65a9a64a6938734cf1a0bcd49d83612bdb1a7  $HOME/.cache/demo-vscode-1.109.5.tar.gz" | sha256sum --check
tar -xzf "$HOME/.cache/demo-vscode-1.109.5.tar.gz" -C "$VSCODE_DIR" --strip-components=1
```

Choose a newer compatible Linux build if the extension requires it. To verify a trusted Linux VSIX from a Windows download or direct HTTPS URL:

```sh
demo prepare --source /mnt/c/Users/YOUR_USER/Downloads/nightly-linux-x64.vsix --vscode "$VSCODE_DIR"
```

Alternatively, find the Actions run for the checked-out head and select its artifact ID:

```sh
gh run list --commit "$(git rev-parse HEAD)" --limit 20
gh api "repos/$OWNER/$REPO/actions/runs/RUN_ID/artifacts" --jq '.artifacts[] | [.id,.name] | @tsv'
demo prepare --pr-artifact "$OWNER/$REPO" ARTIFACT_ID --commit HEAD --vscode "$VSCODE_DIR"
```

Replace `RUN_ID` and `ARTIFACT_ID` with the selected values. Windows-only VSIX files and Windows `.exe` tools cannot be prepared in this Linux container. Preparation verifies activation or a standalone Linux tool's version; it does not record the artifact in action or exercise a target board.

## Prepare a PR artifact or a supplied build

`demo prepare` optionally verifies the tool or extension build before you plan or record. Choose a **GitHub Actions artifact** uploaded for the commit being demoed, or a **local file or direct HTTPS download URL**. Only run builds you trust: the tool or extension executes inside the disposable container. Nothing is installed into your daily editor.

```sh
# A VSIX you already have; for a direct download, pass its HTTPS URL instead.
demo prepare --source /path/to/cmsis-nightly.vsix

# From the target checkout, use the Actions artifact ID (not the run ID).
demo prepare --pr-artifact Open-CMSIS-Pack/vscode-cmsis-solution 123456789 \
  --commit my-pr --vscode /usr/share/code

# A self-contained Linux x64 CLI; must return a version from --version.
demo prepare --kind tool --source /path/to/cmsis-toolbox-binary
```

For Actions downloads, authenticate `gh` with read access to the repository. The CLI rejects expired artifacts and artifacts whose recorded workflow head differs from the selected commit (`HEAD` by default). It accepts a direct VSIX artifact or a ZIP containing a VSIX. For a ZIP with multiple VSIX files, or for a standalone tool inside an Actions ZIP, provide `--member` with the exact path inside the ZIP. A direct URL must return the actual VSIX or executable, not an Actions page, ZIP wrapper, or installer. The CLI prints the artifact's SHA-256; pass `--sha256` with a trusted expected digest to verify it. A supplied file or URL is not automatically tied to the PR.

For Open-CMSIS-Pack extensions, preparation detects a normal Microsoft VS Code **Linux x64** installation from `code` on `PATH` or `/usr/share/code`. To select another build, pass `--vscode` with its installation directory or the directory of an extracted official Linux archive. Use a version accepted by the selected VSIX's `engines.vscode`. VS Code is not bundled or redistributed. Preparation installs into an empty profile, checks the installed ID and version, then activates the selected extension in a real VS Code extension host. No extensions are fetched from the Marketplace. Supply any required companion extensions as local VSIX files or direct HTTPS URLs with repeatable `--dependency` options. For example, the CMSIS Debugger extension pack lists Serial Monitor and Eclipse CDT extensions; pack entries are not installed automatically.

Acquisition can use the network, but installation, activation, and version checks run offline with no host profile, credentials, or hardware access. The prepared profile is discarded afterward. Activation in an empty window does not verify CMSIS builds, debugging, or features that require a project, additional tools, network, or a target board. The recording workflow below is unchanged: it uses the prebuilt VSCodium renderer for source walkthroughs and does not record the prepared artifact in action.

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

The development CLI reports `0.1.2+dev` and uses the local image; `demo install` accepts packaged releases only. `./smoke.py --plan-only` checks planning without a container. The full smoke test uses a tiny local Git fixture and a deterministic Codex stub, edits narration, and checks the rendered WebM's codecs, audio, duration, and changing cursor frames.
Pass `./smoke.py --vscode /path/to/vscode` to also verify standalone tool version reporting and real VSIX activation.

The release workflow runs on a `vMAJOR.MINOR.PATCH` tag matching the development CLI version. It tests the CLI and local renderer, collects the exact Debian source packages for the image, and publishes those sources both as a separate GHCR image and as a release asset. It then pushes the renderer to GHCR, embeds that image's immutable digest in the release archive, tests the packaged CLI and image, and publishes the release only if both images are publicly pullable. A new GHCR package may initially be private: make the `demo-creator` container package public in GitHub Packages, then rerun the Release workflow for the tag. A published release is never overwritten by the workflow.

## License

The project source is licensed under [Apache-2.0](LICENSE). The renderer image combines separately licensed components; see below before redistributing it.

## Version and license notes

The image uses Debian `12.12-slim` with packages selected from the dated `20260101T000000Z` Debian archive, VSCodium `1.105.17075` with a checked SHA-256 digest, and Playwright Python `1.56.0` with pinned, hash-checked Python dependencies. Debian package versions are frozen by the archive date. The image is a collection of components with separate licenses:

| Component | License | Source |
| --- | --- | --- |
| VSCodium / Code - OSS | MIT | [VSCodium](https://github.com/VSCodium/vscodium) |
| Playwright | Apache-2.0 | [Playwright license](https://github.com/microsoft/playwright/blob/main/LICENSE) |
| pyee | MIT | [pyee license](https://github.com/jfhbrook/pyee/blob/main/LICENSE) |
| greenlet | MIT; PSF license for Stackless-derived files | [greenlet licenses](https://github.com/python-greenlet/greenlet/blob/master/LICENSE) |
| typing-extensions | PSF-2.0 | [typing-extensions license](https://github.com/python/typing_extensions/blob/main/LICENSE) |
| xdotool input driver | BSD-3-Clause | [xdotool copyright](https://github.com/jordansissel/xdotool/blob/main/COPYRIGHT) |
| Flite engine and bundled `kal` voice | CMU permissive license; `kal` is free for use | [Flite COPYING](https://github.com/festvox/flite/blob/master/COPYING), [Festival voice note](https://github.com/festvox/festival/blob/master/COPYING) |
| FFmpeg recorder/muxer | LGPL-2.1-or-later in its base configuration; Debian's build may enable GPL components | [FFmpeg license](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md) |
| libvpx VP9 codec | BSD-3-Clause | [libvpx](https://github.com/webmproject/libvpx) |
| libopus Opus codec | BSD-style | [Opus license](https://github.com/xiph/opus/blob/main/LICENSE_PLEASE_READ.txt) |

FFmpeg is the principal non-permissive runtime dependency. Debian's X11, GTK, Electron, and other system libraries also carry their own licenses; no single license is claimed for the image. Inspect the built image's `/usr/share/doc/*/copyright` and `ffmpeg -buildconf` before redistributing it.
