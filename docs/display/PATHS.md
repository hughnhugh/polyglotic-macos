# Which code lays out each kind of window

Measured, not read off the code: every one of the 27 recorded caption
streams was replayed on a real window in each set-up (readings off and on,
two widths, both Long lines arrangements; 1,404 replays), and each replay
noted which of the layout's four paths ran. Made on 2026-11-27 from the
0.1.13 train (`8e242c484`) with

    python -m tools.scene_replay record --out recording.json
    python -m tools.scene_replay paths recording.json

The paths are 827's names (its SPEC, section 1.1): **A** clause rows
(`CaptionLayout._laid_row_text`), **B** the composer (`CaptionLayout._flowed`),
**C** Video's tracks (`CaptionLayout._subtitle_tracks` and `VideoFlow`) and
**the pour** (`CaptionLayout._poured`). A cell is the number of replays in
which the path ran; a replay can use more than one.

| Surface and mode | Long lines | Runs | A clause rows (Qt may wrap) | A clause rows (one line) | B the composer | C Video tracks | the pour |
|---|---|---:|---:|---:|---:|---:|---:|
| Caption window: Everyday, Conversation, Learning (Instant) | Grouped | 108 | - | - | 108 | - | - |
| Caption window: Everyday, Conversation, Learning (Instant) | Display new lines | 108 | - | - | 108 | - | - |
| Caption window: Steady, card stack | Grouped | 108 | - | - | 108 | - | - |
| Caption window: Steady, card stack | Display new lines | 108 | - | - | 108 | - | - |
| Caption window: Steady, settled transcript and live zone | Grouped | 108 | - | - | 108 | - | - |
| Caption window: Steady, settled transcript and live zone | Display new lines | 108 | - | - | 108 | - | - |
| Joined window (each column a caption window, Instant) | Grouped | 108 | - | - | 104 | - | - |
| Joined window (each column a caption window, Instant) | Display new lines | 108 | - | - | 104 | - | - |
| Video, Instant | Grouped | 108 | - | 104 | - | 12 | - |
| Video, Instant | Display new lines | 108 | - | 104 | - | 12 | - |
| Video, Scrolling | Grouped | 108 | - | 104 | - | 12 | - |
| Video, Scrolling | Display new lines | 108 | - | 104 | - | 12 | - |
| Transcript window | Grouped | 108 | 84 | - | - | - | - |

## What it shows

- **Every caption window is laid out by the composer**, in every mode:
  Everyday, Conversation and Learning, the Steady card stack, Steady's zones
  and each column of the joined window, with Long lines set either way. 827's
  table had the caption windows on A or the pour; that has not been so since
  the composer became the one path for them.
- **Video uses A with one line to a row**, and C when a subtitle is long
  enough for tracks (12 of 108 replays each way).
- **The transcript window is the only place Qt wraps a row itself** (A, with
  wrapping left to Qt). It is the one exception to "Every row is a single
  line".
- **The pour did not run in any replay**, and `CaptionLayout.separate_rows`
  has no caller. Either the recorded streams never reach them or they are
  dead; `display-2` should find out before carrying them over.
- A count under the number of runs (104 of 108, 84 of 108) is a stream that
  put nothing on that surface: no finished caption for the transcript, or
  nothing from the first source for a joined column.

## What it cannot show

The count is of paths that ran, not of rows each produced, and only for the
27 recorded streams: a path that needs a setting the set-ups do not vary
(a look, a text size, right-to-left text) would not be seen here.
