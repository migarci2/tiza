# Revised brand film — 14 September 2026

The current editable source is `video/tiza-fast-cut/index.html`; the revised export is `video/tiza-fast-cut/tiza-60s-v2.mp4` (60 seconds, 1080p, 30 fps). The earlier MP4s remain available.

The new opening uses Pavel Danilyuk's Pexels footage. Krea Seedance 2.5 supplies the tactile chalk sequence. Six selected ElevenLabs v3 stems make a teacher/assistant dialogue, with inline delivery tags. Generated chalk/chime and paper sounds join the existing music, spectrally carved around every voice. GPT Image supplied the logo; it was traced into actual SVG paths and deployed on the website.

Source decisions and prompts: `video/tiza-fast-cut/PROVENANCE.json`, `STORYBOARD.md`, `DESIGN.md`, and `CREDITS.md`. HyperFrames upgraded 0.8.35 → 0.8.38; current composition check passes without warnings. Desktop/mobile branding checked locally and in production; live SVG bytes match the source, and the API health check returns `ok`.

Production is now running with `TIZA_AGENT_MODE=bedrock`, `TIZA_DEMO_MODE=true`, and `eu.amazon.nova-2-lite-v1:0`. A read-only check also found a completed preparation from 13 September with `model_invoked=true` and 11 model calls; the limited evidence is saved in [production-agent-check.json](production-agent-check.json). The film keeps captured synthetic-demo interactions and makes no live-execution or measured-impact claim. The historical account blocker below describes the earlier recording session, not current AWS account status.

## Revised export verification

Full FFmpeg decode passed. H.264, 1920×1080, 30 fps, 1,800 frames, AAC audio, exactly 60.000 seconds, 31,091,411 bytes. No black interval ≥0.3 seconds. Audio mean −20.5 dBFS, peak −1.5 dBFS. Reviewed the final exported contact sheet, including product frames and opening/closing states. HyperFrames check: zero errors/warnings, 23/23 contrast checks pass. The animation map contains 23 seek-safe tweens; holds preserve footage playback or reading time.

SHA-256: `d80f8413a5b9f946d9179f6ef035a80ca570a90e5b9e1d25070ac9af6377f211`.

---

# Historical working cuts

Production started 12 September 2026. English, 16:9, 1080p, 30 fps. The full working cut is 2:15.

## Latest cut — 60 seconds, all HyperFrames

The revised video is `video/tiza-fast-cut/tiza-60s.mp4`; its editable composition is `video/tiza-fast-cut/index.html`. It replaces the 135-second working cut for review. The opening is newly authored native text/shape animation: no Raylight footage or audio is included. New English narration, faster transitions and retimed product captures reduce the duration from 135 to 60 seconds. The original files remain intact.

Narration and timings: [60-second script](audio/voice/60s/script.md). Music has a baked 1.5-second fade at the end so the voice is unaffected. To render, run `npm run check` and `npm run render -- --workers 1 --output tiza-60s.mp4` from `video/tiza-fast-cut`.

Verified revised export: 60.000 seconds, 1920×1080, 30 fps, 1,800 frames, AAC stereo. HyperFrames check: zero errors and warnings. Full decode passed; no black interval ≥0.3s; audio peak −1.1 dBFS. Reviewed opening, scene snapshots and the final exported contact sheet.

## Sources and editing

- [Raylight opening project](https://www.raylight.app/editor/25cc7949-3102-46d8-979c-5e324a4a97ba): 11.4 seconds, created from the “Text with Apple inspiration” template. Edited through Raylight MCP; a separate project preserves the existing “Take this apart” project.
- [Storyboard](storyboard-v1.png): GPT Image visual direction using the existing Tiza teacher illustration as reference. This contact sheet is a concept, not a product screenshot.
- [Music and sound licenses](audio/MANIFEST.md).
- Full editable assembly: `video/tiza-working-cut/index.html`, HyperFrames.
- Review video: `video/tiza-working-cut/tiza-film.mp4` (with final audio fade).
- Intermediate render: `video/tiza-working-cut/tiza-working-cut.mp4`.
- [English narration and timings](audio/voice/script.md): local Kokoro voice, music and click/typing/whoosh effects.

Raylight opening beats: 0–3.2 “Class dismissed.”; 3.2–5.8 “Work continues.”; 5.8–8.4 “Eight learners.”; 8.4–11.4 “Meet Tiza.” The current app palette and Manrope replace the template styling. The existing GPT Image teacher illustration is used in the final beat.

Music: “Electrodoodle” Kevin MacLeod (incompetech.com), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Opening SFX: typing at 0.25s, whooshes peaking at 3.2s and 5.8s, soft click at 8.45s. Raylight's onset analysis placed the main cuts within 19ms of an audio onset.

Free Raylight export retains its “Made in Raylight” badge. No paid credits were purchased. Preserve that badge when using the exported clip in the full assembly.

## Release status

This is a working cut. AWS account verification currently blocks live Bedrock inference. The existing landing preview includes an illustrated agent sequence and does not prove an actual model run. The working cut identifies the pending connected-agent recording at 45–62 seconds and in narration. Replace that section with a real run and retain its trace before presenting it as a connected-agent demonstration.

No video has been submitted to Devpost or published to YouTube/Vimeo by this workflow.

## Reopen or render

From `video/tiza-working-cut`:

```sh
ONNXRUNTIME_NODE_INSTALL_CUDA=skip npx --yes hyperframes@0.8.35 preview --background
npm run check
npm run render -- --workers 1 --output tiza-working-cut.mp4
ffmpeg -y -i tiza-working-cut.mp4 -c:v copy -af "afade=t=out:st=132:d=3" -c:a aac -b:a 192k -movflags +faststart tiza-film.mp4
```

The first section remains editable in Raylight; the remaining composition, source captures, holds, narration and audio levels remain editable in HyperFrames. The free Raylight badge remains visible in the opening.

## Export verification

12 September 2026: HyperFrames check passed with zero errors; the intentional decorative circles outside the canvas account for the remaining layout warning. Reviewed scene snapshots and a contact sheet extracted from the final MP4. Full FFmpeg decode passed: 4,050 video frames, 1920×1080 at 30 fps, 135 seconds of picture, AAC stereo audio. No black interval of 0.3 seconds or longer was detected; audio peak is −2.0 dBFS. AAC encoding adds about 0.02 seconds to container duration.
