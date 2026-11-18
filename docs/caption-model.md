# The caption model and the one layout - design note

polyglotic-hq project 340, 2026-11-15. Agreed by the user that day
(DECISIONS.md #161); the decision is
[decisions/0132](decisions/0132-one-model-of-a-caption-one-layout.md).
It is built in the steps under "Migration" below. **On `main`: step 1,
the model.** The layout, the selection and the rest described here are
on the prototype branch `340-caption-model` (pull request #637, a
reference, not for merge) until their step.

## The shape

```
server's clauses ──> caption history ──> CAPTION MODEL ──────────┐
(text, links)        (settled text;      core.listening          │
                      links carried      .caption_model          │
                      through it)        places, units, links,   │
                                         cuts, selection         │
                                                                 v
learning (known, load, saved) ──> marks over the same places ──> ONE LAYOUT ──> runs ──> paint
                                  (interface)                    ui_next.views.flow       hit test
window: width, text size, options ──────────────────────────────>                         selection
```

- **A place** is characters `[start, end)` of one clause's text on one
  side (what was said / its translation). It is the only way anything
  points at caption text.
- **The model** holds what the server's data says, once: units (where a
  line may break), links numbered across the caption, where both sides
  can be cut, which clauses are settled. No sizes, no fonts, no options.
- **The layout** takes models, the window's width and the fonts'
  measuring, and gives lines of **runs** - each a place and where it is
  drawn. It is first-fit and never looks ahead: more text never moves
  text already shown. Widths are measured once per clause and text size;
  a resize is arithmetic over them, on every step.
- **Everything drawn on text** (link underlines and curves, stage
  colours, dots, the hover, a selection) asks one question: where are
  this place's characters? So none of it knows which option is on.

## The options (one composer, no modes of its own)

| Option | What it does |
|---|---|
| `cut=CLAUSE` | a clause and its translation are a line pair (the default: "a clause a row") |
| `cut=CAPTION` | the caption's clauses run on above, their translations below ("Translation below") |
| `share` | clauses share a line pair as they fit |
| `split` | a clause that does not fit what is left of the pair is cut there, both sides, where the fewest links cross ("Line by line" = `share` + `split`) |
| `aligned` | each part starts at the same x in both lines: a word's counterpart is under it - in every option (372): a clause a row keeps a clause's parts in its pair; Translation below composes Line by line's pairs and gathers each caption's lines of what was said over its translation's, so the k-th translation line faces the k-th line above; a part wider than a line is cut on both sides, as Line by line cuts |
| `run_on` | the next caption carries on in the line pair the last one ended in (Line by line only: `share`) |
| `join` | what stands between clauses on a line: an ellipsis, one at line ends too, a space - drawn in room that is there, never given room |
| `show_original`, `right` | originals hidden; your own speech against the right edge |

Joined windows need nothing: each column is a surface with its own width.
The Strip (one or two rows) was removed in 272; were it wanted again it is
a window height, not a layout.

**What "fills the width" can and cannot mean.** Chinese is about half as
wide as its English. Line by line keeps the two in step, so the wider
language fills its line and the other fills in proportion. Only
"Translation below" fills both, by giving up the pairing. A smaller
translation size (305) narrows the gap.

Measured offscreen on recorded caption text (340 part 3, 2026-11-15: 100
FLEURS sentences each way with the real translator's output, a caption per
clause as real captions are - 22 characters a caption of Mandarin, 70 of
English; the window 460 px tall, measured after every 6th caption; no word
links in the record). How full the lines are, by 346's measure (each band
of text's width over the window's):

| Mandarin -> English | 900 px | 1,400 px | 2,000 px |
|---|---|---|---|
| today, every layout | 39 % | 28 % | 20 % |
| new layout, line by line, captions run on | 67 % | 62 % | 58 % |
| ... and parts lined up | 71 % | 69 % | 65 % |

| English -> Mandarin | 900 px | 1,400 px | 2,000 px |
|---|---|---|---|
| today, every layout | 37 % | 26 % | 19 % |
| new layout, line by line, captions run on | 65 % | 64 % | 62 % |
| ... and parts lined up | 67 % | 70 % | 69 % |

Without run-on the new layout fills no more than today's: a caption is a
clause or two, and each starts a line of its own. With it, the wider
language's lines are 76-84 % full and the other's 53-60 % (lined up:
66-74 %, because the gaps that line the parts up reach further along the
line). What keeps the wider language from 100 %: the line being filled at
the bottom, a run's last line (`RUN_ON_MOST`), and a clause that is not
cut for less than a tenth of the width (`WORTH_FILLING`).

## Captions that run on, a caption at a time

A surface lays out, keeps and scrolls captions one by one, measuring only
what shows (`views.scroll`). Run-on keeps that:

- **Each composition says what it left open** (`Flowed.open`: where the
  text of its last line pair ends, and that pair's height) and **the next
  is composed from there** (`compose(entry=...)`): its first runs are on
  that pair. Composed one by one this way, the text is exactly where
  composing the captions together puts it (a test at six widths and three
  joins).
- **The engine** keys a caption's layout by its entry too
  (`CaptionLayout.laid(line, width, text_size, entry)`), gives it no label
  (the run's first caption has it) and says how much of its top lies over
  the caption before (`LaidLine.lead`). `left_open` composes without
  laying out: arithmetic over widths measured once.
- **The canvas** (`caption_window.Canvas`) follows each run in view from
  its start (`_entry`), draws a caption that carries on `lead` higher, and
  tells the scroll how far each caption takes the text (`_height`): its
  height less `lead`, or plus the gap between captions for one that starts
  a line. A word under the mouse is looked for in every caption whose
  rows reach that line.
- **Which captions run on** (`runs_on`): the same source and speaker under
  the same label, the earlier one finished (its end no longer moves),
  neither Quick preview's line - and a new run starts at every caption
  whose key is a multiple of `RUN_ON_MOST` (12), so where runs start never
  changes as captions come and go. That bounds the work: a resize step
  composes the runs in view, not all 150 captions (6.5 ms of the frame's
  8 before the bound, 1.7 ms after). It also brings the label back and
  reads as a paragraph's end.
- **Text already shown never moves** when a caption arrives: a caption
  that is still being spoken leaves nothing open, and the one after a
  finished caption only adds to its last pair.

Not done: your own speech on the right does not run on (a line against
the right edge moves as it grows); "Translation below" does not run on
(its two streams would have to be composed across captions); a caption
flagged or copied by a right-click on a shared line is the earlier one's.

## Word links

- Numbered across the caption, so colours are never shared on a line.
  Captions that run on carry the count on.
- **Arrows** join a word to its counterpart whenever that is on the line
  under it - in every option. With `aligned` nearly all are; a link whose
  ends are further apart keeps its colour alone.
- **The learning load**: the stage is the word's colour and the line just
  under it; the link's bar sits below that. Both show.
- **Which show** (key words, the cap, words past what I know) is asked of
  the model and the learning marks; nothing is renumbered when it changes.
- **Through settled text**: a row of settled words keeps the links of the
  words it shares with what the server sent next.
- **Across clauses**: the server links within a clause today. A `Link`'s
  ends are places, each with its clause, so a link across clauses needs
  no change here - only the server sending one (a protocol addition).

## Selection (the user, 2026-11-15)

A `Selection` is two places: where the drag began, where it is.
- Both on one side: that side's words between them, across lines,
  clauses and captions.
- One on each side: both sides of every clause between, whole.
- It names places, so it is the same words after a resize, in another
  option, and when its captions grow; a caption withdrawn or joined away
  drops out of it.

**Told apart from drag-to-pin a phrase** by where the drag goes, not by a
key:
- press on a word, release on it: its lookup (today's);
- drag within the word's own clause and side: a phrase - highlighted as
  now, its lookup pinned on release (today's). It is also a selection:
  right-click copies it;
- drag out of that clause (another line's clause, the translation,
  another caption): a selection. No lookup. It stays until a click
  elsewhere or Esc;
- a drag that starts on no word still moves the window.

Copying: right-click on a selection copies it without taking the keyboard
(343's shared piece); Ctrl+C once the learner has clicked into the window.
`selected_text` gives the text: a caption a line, or two when both sides
are held, clauses joined as the transcript joins them (decision 0126).
**Built** (358, decision 0150): `core.listening.selection` and
`ui_next.caption_selection`, in today's layout and the New layout; the
caption window still never takes the keyboard, so Ctrl+C works while one
of the app's windows has it, and the right-click everywhere.

## Kept for later, and where they sit

- **Pinyin above Chinese** (DECISIONS #153): a
  per-unit annotation over places of the original side; the layout gives
  a line an annotation band (more ascent) and widens a unit to its
  annotation. `_Side` is where a unit's width is decided.
- **Saving a sentence** (#153): a `Selection` over one caption, or the
  caption's key - both already stable through updates.
- **Links across clauses**: above.

## What the prototype has

| In | Not in |
|---|---|
| The model, with tests (`tests/test_caption_model.py`) | `caption_rows` derived from the model (rows are still built beside it and renumbered) |
| The composer, every option, with tests of coverage, stability and "a resize measures nothing" (`tests/ui_next/test_flow.py`) | Captions that run on **in the caption window** (the composer does it; the window's scroll, dimming and labels are per caption) |
| The layout engine composing through it; arrows in any option; links in the load (`tests/ui_next/test_caption_flow.py`) | The Lab's controls for `aligned` and `run_on` (no interface text added) |
| A caption window on it behind `POLYGLOTIC_CAPTION_FLOW=1` (or `aligned`), in today's budgets | Transcripts, the Look's preview and the Lab's preview on it (they take the old path) |
| Links through settled text | Selection's gesture and copy; `views.word_marks` without Qt |

## Migration, in small merges (each green on its own, nothing behind a long-lived branch)

1. **The model lands, unused by layout.** `caption_model.py`, its tests;
   `views.pour` takes `units` and `matching_cuts` from it (one cutter).
   No behaviour changes.
2. **Links numbered across the caption.** `caption_rows` numbers from the
   model. Fixes shared colours on poured lines today. Goldens for poured
   states change.
3. **Links through settled text** (`settling._shown_with_links`). A fix
   on its own; measure how often it bites first (a proposed project).
4. **The one layout behind the Lab**, beside the pour: `views.flow`, the
   engine's `_flowed`, a Lab value "New layout" (a flag with an expiry:
   step 5 removes it). Arrows in any option come with it; links in the
   load were turned on for today's layout too. Captions run on and parts
   lined up are Lab choices of Line by line (steps 8 and 9 below, brought
   forward: the user, 2026-11-15 ~12:35). The user tries it by eye.
   **Done** (340 part 3).
5. **The switch-over.** Every surface on the one layout; the pour, the
   clause-row wrap, `Line.cuts`, `CaptionLines.set_cuts` and
   `LaidLine.poured`'s branches deleted; goldens re-approved once.
   Decision 0100 marked replaced.
6. **Marks without Qt.** `views.word_marks` gives states over places;
   `caption_marks` only turns them into formats. `Line.rows` goes; the
   hover, lookup and reveal take places.
7. **Selection and copy** in caption windows, on 343's shared piece.
   **Done** (358, decision 0150).
8. **Captions run on** in the window: done with step 4, a caption at a
   time (above) - the surface still scrolls captions.
9. **Lined up**: a Lab choice with step 4; then pinyin and sentences can
   sit on the model.
