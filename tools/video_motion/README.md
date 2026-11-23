# Video motion replay

Replay the same Video packets through the desktop's Qt paint path and the reference engine for Instant and Scrolling. The complete reference page is pinned as `reference.html`. Node executes the page's engine and uses headless Chromium to shape and measure reference ink. Qt records positioned glyphs from the app's paint calls. Both supply the frames used by the comparer.

The first run caches two caption fonts from a pinned revision of Google Fonts and verifies their SHA-256 digests. Later runs can work offline. Set `VIDEO_REFERENCE_FONTS` to a preloaded directory containing `NotoSans.ttf` and `NotoSansSC.ttf`, or `CHROME_BIN` to an alternative Chromium executable. [Pinned fonts and licences](https://github.com/google/fonts/tree/06bfe0d62a98375cb09c942fa18e68bd32cff057/ofl)

## Matrix

Run from the desktop worktree. The matrix takes the shared Qt lock for the Qt phase on the Polyglotic PC.

```powershell
node --test tools/video_motion/reference.test.mjs
uv run python -m tools.video_motion.matrix build/video-motion --pictures build/video-pictures
```

The matrix covers three timelines in Tiny, Small, Medium and Large with both starting modes. It adds Narrow, fast arrivals, toggles and a mid-line mode switch with each starting mode, for a total of 32 cases. Use `--timeline` or `--preset` to restrict the continuous-playback cases. The matrix runs all its cases and writes `pass-table.csv` and `critics.csv` even when cases fail. Each case directory contains the complete frame dumps, the reference events and paired PNGs. The cooking keyframes at Medium and Tiny are also copied to the pictures directory when requested.

The 60 Hz matrix supplies the same packet-sized arrivals to both engines. It measures visible positions within 2 px, event times within one frame, signed motion speeds within 10%, and opacity within one 8-bit level. Both engines are audited separately for overlapping or clipped glyph ink, duplicate copies, downward movement, Instant sideways movement, font-size changes, and movement before the 0.5-second minimum hold. The intentional viewport crop on the horizontally scrolling track is measured for word exposure. The reference counts ink above 0.002 opacity. Word ink has 200 ms from arrival for a caption already on screen, or from row clearance for a queued caption. Revisions superseded in the queue coalesce. The pass table separately reports median and maximum queue delay, including captions admitted immediately. Run `uv run python -m tools.video_motion.compare CASE --reference-only` to audit the reference independently.

## Returning to live

This fixture scrolls back, holds, leaves the window and returns after a long translation arrives behind the history view. Run it for both modes. Set `VIDEO_PACED` for the reference's word cadence.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:VIDEO_PACED = '1'
$lock = '../../../polyglotic-hq/projects/346-claudes-own-validation-loop/tool/qtlock.py'
foreach ($mode in 'instant', 'scrolling') {
    $out = "build/video-return-$mode"
    node tools/video_motion/reference.mjs $out medium $mode tools/video_motion/return-to-live.json
    python -I $lock --who 743 -- uv run python -m tools.video_motion.app $out
    uv run python -m tools.video_motion.compare $out
}
```

The replay checks both renderers for a fixed history view, bounded and single-copy ink after return, and a complete wrapped translation in Instant when it fits. The Qt replay uses different original and translation fonts. Set `EXTRA_FRAME` before running Node to capture a specific zero-based frame.

## Timelines and attribution

The cooking example comes from project 686. The recorded fixtures use the first four consecutive captions from two public recordings captured by project 526 on 2026-11-20. `recorded.py` preserves their relative times and recognition and translation revisions. In those recordings partial translations arrived with their originals.

- The English fixture adapts the spoken Wikipedia article *Bone Wars*, read by theayeaye. The text and translations are provided under CC BY-SA 4.0. [Recording and attribution](https://commons.wikimedia.org/wiki/File:Bone_Wars_spoken_Wikipedia_article_(English).ogg) [Licence](https://creativecommons.org/licenses/by-sa/4.0/)
- The Mandarin fixture adapts four captions from the FLEURS Mandarin development recordings. The text and translations are provided under CC BY 4.0. [Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs) [Licence](https://creativecommons.org/licenses/by/4.0/)

The desktop takes its motion settings from the tunables registry. `video_motion.settle` defaults to 0.5 seconds (range 0.5–1.0). A finished row stays in place for that duration plus any residual reading time, up to the existing one-second residual wait cap. `video_motion.instant_word_interval` defaults to 0.016 seconds (0.016–0.05), one word per paint at 60 Hz. `video_motion.catchup` defaults to 0.200 seconds (0.05–0.20), `video_motion.max_step` to 128 logical pixels per paint (16–160), and `video_motion.glide` to 360 logical pixels per second (100–800). The comparison uses the shipped defaults.
