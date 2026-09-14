# Tiza identity

Generated on 14 September 2026 with the built-in GPT Image tool. `tiza-gpt-image.png` is the original transparent raster; `tiza-traced.svg` is the intermediate trace. The production logo and standalone mark live in `apps/web/public/brand/`.

Conversion: threshold the original alpha at 160, crop to the opaque bounds, trace with VTracer 0.6.12 (`colormode=binary`, `mode=spline`, `filter_speckle=12`, `corner_threshold=60`, `length_threshold=4`, `splice_threshold=45`, `path_precision=2`), recolor paths to #0866e6 and add SVG viewBox padding. These are actual vector paths, with no embedded bitmap or font dependency.

## Exact image prompt

Use case: logo-brand. Generate one minimal horizontal logo for the teacher workspace "tiza". Compact abstract lowercase t symbol formed from two bold rounded chalk strokes beside the exact lowercase word "tiza" in friendly confident geometric sans lettering. Solid cobalt blue #0866e6 on pure white. Crisp smooth flat vector-like shapes, generous margin. No gradients, texture, shadows, mockups, slogans, sparkles or extra symbols. One logo only; intended for conversion to SVG paths.

## Verification and release

Frontend build and existing Vitest check passed. Desktop and mobile reviewed in Chromium. Deployed only the gateway frontend on 14 September; the live SVG bytes match the local files and `/api/health` returns `ok`.

Production rollback: source backup `/opt/tiza-brand-before-20260914.tgz`, previous image `tiza-gateway:before-brand-20260914`. Production screenshots are `production-desktop.png` and `production-mobile.png`.
