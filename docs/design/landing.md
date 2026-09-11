# Landing and code access

The entry screen follows the generated `access-reference.png`: warm paper, two-column introduction and a white access panel. The implementation adds the reinforcement cycle and an actual synthetic workspace preview. Following the revised brief, the public demo button was removed; access uses email and code only.

Reference generated with the built-in image tool on 10 September 2026. Direction: Tiza desktop sign-in, system sans-serif, paper #F6F3EB, ink #1F2C25, green #28614B, muted #536357, amber #EABD5B; editorial whitespace, left product introduction, right bordered 18px white form, no decorative gradients. The generated reference originally included a demo shortcut, removed in code after the user's correction.

Browser captures: `landing-desktop.png` and `landing-mobile.png`. Local code flow explicitly displays that no email was sent. The original unauthenticated session shortcut now returns 410.

## Illustrated scrollytelling revision — 11 September 2026

The revised landing follows the local Yuvo project's actual `Story` visual pattern: Manrope, blue pill actions, warm white paper, sunny yellow/coral/sky accents, a pinned illustration beside three sequential chapters, and compact illustrated exploration cards. Code is newly authored for Tiza; all three character illustrations are generated with GPT Image. The login remains the existing code flow and is now the final section with direct header/hero access.

All three scenes now use generated raster images. The two temporary SVG illustrations were replaced with GPT Image output on 11 September. See `apps/web/public/art/SOURCES.md`. The page has no scroll hijacking or animation library; IntersectionObserver selects the chapter, and reduced-motion disables transitions. Content is readable in document order.

## Product loop

The hero embeds a muted MP4 loop inside a clean rounded frame, with yellow, coral and mint circles behind it. The visible title bar, footer controls, caption and download link were removed; pause remains available on hover, keyboard focus and touch. A GIF export remains in the media folder. Browser recording runs real synthetic classroom actions; its optional `TIZA_SIMULATE_AGENT=1` mode intercepts the activity response only in the capture browser to illustrate the four Strands tools. No live run metadata is altered. The media manifest preserves the real `model_invoked=false` and identifies the illustrated sequence. The illustrative provenance is retained in the screen-reader description and media manifest.

Reproduce from a running local API, worker and Vite server: `cd apps/web && TIZA_SIMULATE_AGENT=1 pnpm exec node scripts/record-demo.mjs`; then from the root run `uv run python scripts/export_demo.py`. The recorder resets the synthetic demo classroom. Raw recordings stay in ignored `data/recordings/`. Final GIF, MP4, poster and manifest live under `apps/web/public/media/`.


The landing and workspace now share the root palette, Manrope, yellow letter mark and blue pill actions. The empty classroom and next-lesson card reuse Tiza's own illustrations. The capture-only agent sequence takes two seconds per stage, showing completed, active and pending steps; assignment results appear after all four stages. Recorder assertions verify this order and prevent drafts from appearing early. Production jobs have no artificial delay.


The recording also includes a capture-only cursor overlay driven by real pointer events. The recorder reuses the macOS arrow and text-pointer assets from Yuvo, switches to the text cursor over fields, and decelerates into click targets with distance-dependent timing. It checks that the cursor hotspot matches every click target. There is no click halo. The cursor is baked into the MP4/GIF, not installed in the application.


The current access card contains one Demo code field and Enter workspace action. It calls `/api/auth/demo-code` directly, without email collection or an OTP request step. The code is validated server-side and the existing session and CSRF protections remain in place. The endpoint is disabled outside demo mode.


The design and copy pass removes the repeated chapter-card grid, redundant color-dot rows and scroll cue, the duplicate empty-class CTA and the second preparation spinner. Copy names the goal, exercises, responses and review action directly. The planner is called Practice planner with a NotebookPen icon. The requested video circles, generated illustrations and Yuvo-derived palette remain the visual signature.
