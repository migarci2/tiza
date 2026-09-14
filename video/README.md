# Edit the Tiza film

Current composition: [tiza-fast-cut/index.html](tiza-fast-cut/index.html). Revised export: [tiza-fast-cut/tiza-60s-v2.mp4](tiza-fast-cut/tiza-60s-v2.mp4), 60 seconds, 1080p, 30 fps.

The film combines a Pexels editorial opening, Krea Seedance 2.5 chalk footage, captured Tiza interactions, and an ElevenLabs v3 teacher/assistant conversation with acting tags. The new GPT Image logo is traced to SVG and shared with the deployed website.

## Preview and render

Requires Node 22+ and FFmpeg. From `video/tiza-fast-cut`:

```sh
npm run dev
npm run check
npm run render -- --workers 1 --quality delivery --output tiza-60s-v2.mp4
```

HyperFrames was upgraded from 0.8.35 to 0.8.38 and checked. Assets, fonts, GSAP and selected audio stems are local; no provider key or running backend is needed to render. The first CLI invocation needs network access to install its pinned runtime.

- [Storyboard](tiza-fast-cut/STORYBOARD.md), [brand direction](tiza-fast-cut/DESIGN.md), [exact prompts and selected generations](tiza-fast-cut/PROVENANCE.json).
- [Credits](tiza-fast-cut/CREDITS.md), [production notes](../docs/video/README.md).
- `tiza-fast-cut/tiza-60s.mp4` preserves the previous 60-second version. `tiza-working-cut/` preserves the older 135-second composition.

The product footage contains synthetic learners. Production is deployed and configured for Bedrock; these captured interactions do not demonstrate a live model invocation.
