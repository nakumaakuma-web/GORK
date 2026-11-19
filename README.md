# Prompt Extractor Studio

Local reverse prompting for still images and sampled video frames with an existing [llama.cpp](https://github.com/ggml-org/llama.cpp) vision model endpoint. Local UI: `http://127.0.0.1:8765`.

- No user images, video, model weights, credentials, or generated prompts are published here.
- Available outputs: Positive / Negative (RU/EN), appearance, pose, lighting, FramePack motion drafts.
- This repository is an update channel for **Prompt Extractor Studio only**.
- User approval is required to install each update in the app; upgrades verify SHA-256 checksums and keep backups.

**Current version:** v0.7.0. See [README_RU.md](README_RU.md) for setup, updater linking and limitations.

**v0.7:** deep photo mode rechecks original image; separate anatomy, pose and diagnostic consistency flags.

### 0.5.0
Fix language labels for Positive/Negative RU/EN with automatic validation, an isolated Qwen translation retry, and a fail-closed warning for repeated mismatches.

Version 0.5.1: expanded live status monitor with elapsed time, frame ranges, stage history and truthful indeterminate progress bar.


### Video-field repair (v0.7.0)
When Qwen omits FramePack RU/EN or Timeline RU, Studio makes a separate text-only recovery call from its saved analysis. Existing results can be loaded from exported JSON and repaired without reprocessing video frames.


## Motion Director v0.7

A local storyboard-to-video workflow: anime / semi-realistic / photorealistic presets, up to 5 timed motion beats, camera & pacing, RU/EN motion prompt composition using local Qwen (or manual English prompt), editable JSON/TXT export. Optional experimental integration with the *official local FramePack F1 Gradio interface* using a localhost-only, schema-validated bridge. The bridge transfers the source image, sends the generated motion prompt and supports MP4 preview/download. No remote generation service is used. No trained models are bundled or modified. The FramePack integration was validated using local API mocks, **not** a live FramePack install. Consult README_RU.md for complete limits and instructions.
