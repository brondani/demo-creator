---
name: demo-render
description: Render a reviewed demo creator storyboard to a narrated WebM. Use when asked to render or make a video from an explicitly approved storyboard.
---

# Render a reviewed demo

1. Identify the target Git repository containing the recorded objects, the reviewed JSON script, and the output WebM path. Ask for missing inputs. If the user has not explicitly approved this specific storyboard for rendering, stop and request review and approval; do not infer approval from a request to create a demo.
2. Locate the demo creator's executable: use a path supplied by the user, the `demo` at the root of the demo-creator checkout containing this skill, or an installed executable on `PATH`. If none is available, ask for its location. Do not assume the target repository contains it.
3. From the target repository, run the following command with the actual quoted paths:

   ```sh
   /path/to/demo-creator/demo render --script reviewed.json --out demo.webm
   ```

   Do not modify or regenerate the approved script, or overwrite an existing output without consent. Rendering validates the script and uses it as supplied without a model call. It requires the prebuilt renderer image and rootless Podman; consult the demo creator README for setup. Do not use sudo, privileged containers, host displays, or bypass sandbox or approval restrictions. If validation or rendering fails, report the error and stop instead of changing the script or claiming success.
4. Report the output path only after the command succeeds. Describe the video as a source walkthrough, not a demonstration of runtime behavior.
