# Prompt Extractor Studio v0.8.0

Local image prompt reverse analysis and **separate time-oriented video analysis** via Qwen3.5/llama.cpp and FramePack F1 Motion Director.

- Photo mode: Positive/Negative RU/EN, appearance, anatomy, pose and style.
- Video mode: `standard` or `adult` (18+, with user age confirmation), participants, setting, visible action process, contacts, rhythm, camera, timestamped evidence, uncertainty, timeline and FramePack RU/EN.
- Video temporal scan: 48/96 evenly spaced pixel-difference probes; 12/20 timestamped observations selected for sequential Qwen analysis. No guesswork about unobserved intervals.
- Adult mode changes **analytical attention** to observed interactions, contacts, sequence and rhythm. Reports are neutral and evidence-based; the mode does not prove the content category or participant age.
- Built-in Motion Director has anime / semi-realistic 2.5D / realistic styles and optional local FramePack F1 connection.

**Important limitation:** temporal scanning is **not native video token inference**. The currently installed llama.cpp input uses groups of images. Pixel differences alone cannot identify actions. Native Conv3D / temporal M-RoPE handling would require a validated compatible runtime or separate video model. Video findings require verification against the original clip.

See [README_RU.md](README_RU.md) for Russian instructions. Local UI: http://127.0.0.1:8765, Qwen server: http://127.0.0.1:8080.


PES v0.9.0: Beginner motion brief -> local Qwen -> one FramePack F1 prompt, advanced preserved.
