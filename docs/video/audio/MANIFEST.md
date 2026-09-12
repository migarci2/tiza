# Tiza video audio manifest

Checked 12 September 2026. All files were probed with `ffprobe` after copying.

## Music

### `music/electrodoodle-kevin-macleod.mp3`

- Title: **Electrodoodle**
- Creator: Kevin MacLeod
- Source: https://incompetech.com/music/royalty-free/index.html?Search=Search&isrc=USUAN1200079
- License: Creative Commons Attribution 4.0, https://creativecommons.org/licenses/by/4.0/
- Required credit: `"Electrodoodle" Kevin MacLeod (incompetech.com), licensed under CC BY 4.0.`
- Catalog metadata: instrumental electronica; synths and kit; bouncy/uplifting; 120 BPM; ISRC `USUAN1200079`.
- File: MP3, 44.1 kHz stereo, 166.060 s, 6,644,624 bytes, 320,106 bit/s.
- SHA-256: `75227ad153780ee0c57ae529caa7f8a891877a46596ff8800a16c90b34b6d18c`
- Origin: previously frozen local media cache; its recorded source URL is `https://incompetech.com/music/royalty-free/mp3-royaltyfree/Electrodoodle.mp3`.

## Sound effects

These four files come from the media-use skill's bundled SFX library. Its `CREDITS.md` records Pixabay as the source and the [Pixabay Content License](https://pixabay.com/service/license-summary/) as the license. Attribution is not required. The bundled ledger does not retain individual Pixabay item URLs, so this common origin is the most precise provenance available.

| File | Intended use | ffprobe result | SHA-256 |
| --- | --- | --- | --- |
| `sfx/typing.mp3` | Short keyboard burst during typed text | MP3, 44.1 kHz stereo, 1.541 s, 26,852 bytes | `944160652faeb7b32acc9341ede4d735a5c9a4ce3fe8509ef7eab91efb430487` |
| `sfx/key-press.mp3` | One deliberate keystroke | MP3, 48 kHz mono, 0.432 s, 3,909 bytes | `bcc892df0898bf466162f14233c3e92a8c1ea351f6affd8a3a7e56c9a760bb72` |
| `sfx/click-soft.mp3` | Approval/publish click | MP3, 44.1 kHz stereo, 0.366 s, 11,702 bytes | `075e17bdac5c13662a1c9530050e0046f81d4138e00eb3bf30427a7b4404103d` |
| `sfx/whoosh-short.mp3` | Circle mask or lateral transition | MP3, 44.1 kHz stereo, 0.575 s, 18,390 bytes | `c2efd9d902a59bf9ec5019035d7deadd17762136896b6e3cb6dd99ea50997a30` |

## Mix proposal

- Start music under the opening title, around `-24 LUFS` beneath narration; raise it 3–4 dB during gaps.
- Duck the music by 8–10 dB from 1:02 to just before the approval click, then leave about 250 ms of near-silence before `click-soft.mp3`.
- Use `typing.mp3` once for the opening words or the goal entry; use `key-press.mp3` only for one emphasized input.
- Use `whoosh-short.mp3` sparingly on the recurring circle-mask/lateral transition, around `-18 dBFS` peak.
- Fade the music over the three-second closing hold. For a 2:15 cut, the 2:46 track needs only a trim and fade, not a loop.

## Missing paper foley

No paper sound is included. The authenticated catalog provider was unavailable, and the bundled library has no paper effect with traceable per-file provenance. Add one only when its exact source item and license can be recorded here.
