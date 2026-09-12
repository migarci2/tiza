# Continue editing the Tiza video

The current cut is **[tiza-fast-cut/tiza-60s.mp4](tiza-fast-cut/tiza-60s.mp4)**: 60 seconds, 1920×1080, 30 fps, entirely authored in HyperFrames with no Raylight footage or watermark.

Edit **[tiza-fast-cut/index.html](tiza-fast-cut/index.html)**. Its timing, text, motion and audio tracks are in this file. Every referenced media file and font is included under `assets/`; no running Tiza backend or AWS account is needed to edit or render this captured demo.

## On another computer

Install Node.js (tested with 24.12) and FFmpeg, then:

```sh
git clone git@github.com:migarci2/tiza.git
cd tiza/video/tiza-fast-cut
npm run dev
```

Open the Studio URL printed by the command. After editing:

```sh
npm run check
npm run render -- --workers 1 --output tiza-60s.mp4
```

The scripts pin HyperFrames 0.8.35. The first invocation downloads the CLI and its browser; it requires Internet access. On Linux, if the optional ONNX CUDA installation fails, prefix the command with `ONNXRUNTIME_NODE_INSTALL_CUDA=skip`.

## Sources

- [Current narration, timings and individual stems](../docs/video/audio/voice/60s/).
- [Audio provenance and licenses](../docs/video/audio/MANIFEST.md) and [cut credits](tiza-fast-cut/CREDITS.md).
- The music fade is baked into `assets/music-60s.wav`; narration is a separate `assets/voiceover.wav` track.
- [Production notes and verification](../docs/video/README.md).
- `tiza-working-cut/` preserves the older 135-second composition, its source assets and `tiza-film.mp4`. Its opening uses the earlier Raylight export with its badge; it is not the current cut.

The current cut uses synthetic learners and captured demo interactions. The connected-agent recording is still pending and is identified in the video. Replace that segment with an actual connected run before presenting it as proof of live Bedrock execution.
