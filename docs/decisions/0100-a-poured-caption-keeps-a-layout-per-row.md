# 0100 A poured caption keeps a layout per row: the pour only says where each row's lines go

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 309 (the user,
  2026-11-14: "I want it to use up more of the screen. often clauses will
  only be a few words and rarely make it to the complete width of the
  window ... text will fill the complete caption window line by line
  seperating by ellipsis ... it should know which size the caption window
  is and assign the correct number of words per line"). A reversible
  technical choice; the mode itself is the Lab's, off by default
  (decision 0074).

## Situation

A caption is shown a clause a row: what was said, its translation under
it. A short clause leaves most of its row empty. The Lab's "Captions fill
the width" pours a caption's clauses into lines as wide as the window: a
line ends where the next word wouldn't fit, not where a clause ends.

Everything that points at caption text goes by **row and character**: the
word under the mouse, a lookup and its context, a dragged phrase, saved
words' colours, underlines, word links, the hover highlight, "Looks
wrong?". Each row is one `QTextLayout` of its own text. Joining a
caption's clauses into one text would have meant mapping every one of
those back to a clause.

## Decision

- **The rows stay as they are** (`core.listening.display.caption_rows`):
  a clause's original, its translation. Poured, each row still has its
  own `QTextLayout` of its own text; only where its lines sit changes.
- **The pour is plain Python** (`ui_next.views.pour`): given the rows'
  text and a way to measure it, it returns the lines - each a list of
  pieces, "characters `[start, end)` of row `r`, from `x`" - and where an
  ellipsis is drawn. It decides every line break itself: words whole in a
  spaced language, any character in Chinese, Japanese and Thai, closing
  punctuation with its character, a word wider than the whole line cut
  to fit.
- **The layout engine places them** (`CaptionLayout._poured`): one
  `QTextLine` per piece, exactly its characters (`setNumColumns`), at the
  piece's `x`, the pieces of a line on one baseline. So a row can start
  part way along a line and end part way along another, and
  `char_under`, `span_rects`, the marks and the underlines find its
  characters as before.
- **The ellipses aren't text**: they are drawn after a row (`LaidRow.trails`),
  fainter, so no character index shifts and a lookup never includes one.
- **The style says which** (`CaptionStyle.fill`, `join`, from the Lab's
  `CaptionLab.fill`, `join`): `Fill.CLAUSES` is today's code path,
  untouched.
- **Stacked** (`Fill.STACKED`, the brief's placement (a)): what was said
  is one stream, poured into the upper lines of the caption; its
  translation another, poured into the lines below.
- **Line by line** (`Fill.PAIRED`, the brief's placement (b)): lines
  alternate - a line of what was said, the line of its translation under
  it, a clause's gap, the next pair.
  - Both are cut at **matching places**: a clause's end, or inside a
    clause where every word link lies wholly before the cut in both or
    wholly after it in both (`pour.matching_cuts`). Where the languages
    order the words differently the links cross, and there is no cut.
    Words with no link go with the linked words after them (an article,
    a preposition), or in Chinese, Japanese and Thai with those before
    (了, 的).
  - A pair of lines takes as many such parts as fit both lines.
  - **Fallback:** a part wider than a line on either side, with no
    matching place inside it, wraps as a clause row does today - its
    original over the lines it needs, then its translation
    (`Poured.fallback`).
  - The cuts are worked out with the line (`Line.cuts`,
    `CaptionLines.set_cuts`), from the clause's word links whether or not
    they're drawn, and only while a window pours line by line. A live
    caption's unfinished clause has none: it wraps.
- **No Arrows while poured** (the user's suggestion): a clause and its
  translation aren't on facing rows. Underlines, colours and hover links
  work.
- **Per caption.** Each caption is poured on its own and starts a new
  line: a caption has its own label, ink (older captions dim), "Looks
  wrong?" and key. Captions running on into each other is not built
  (polyglotic-hq 309's report proposes it).
- **Arrows could come back line by line, not built:** a matching cut
  keeps both ends of every link in the same pair of lines, so a curve
  never has to cross a pair. It needs the arrows' ends found per pair of
  lines, not per row, and the fallback's wrapped parts drawn as today's.
- Enforced by `tests/ui_next/test_pour.py` (the rules, without Qt) and
  `tests/ui_next/test_caption_fill.py` (every word whole within the
  width at five widths, three text sizes and each join; the word under
  the mouse; a resize; the budget).

## Why

- Nothing that reads a caption had to learn a new shape: the change is
  in one function of the layout engine and one module beside it.
- Measuring in the pour, not asking Qt where it would break, is what
  lets a row begin after another on the same line and lets the next
  pull request cut two rows at matching places.
- Not taken: one layout of the joined text (above). Not taken: asking Qt
  to break each row at the window's width and moving the lines after
  (Qt breaks a word anywhere when the room left on a line is small).

## What it costs

Laying out a caption measures each word once (`QFontMetricsF`) before Qt
shapes it. In the UI lab's caption window (the made-up conversation,
offscreen): a resize step 1.0 ms poured against 0.5 ms in rows; a new
caption 1.2 ms against 0.6 ms (budgets: 8 ms a frame, 4 ms a new
caption). A live update in a window of 30 poured captions: 1.1 ms median
(`test_a_live_update_in_a_full_poured_window_is_within_budget`).

## What would make us reverse it

The Lab's testers not wanting the mode: then `Fill`, `Join`, `views.pour`
and `_poured` go. Or captions needing to run on across captions, which
wants a stream above the caption, not inside it.

## How we'd reverse it

Delete `views/pour.py`, `CaptionLayout._poured` / `_place` / `_pour` and
the two Lab fields and controls; `Fill.CLAUSES` is the code that was
there before. A stored `fill` is then ignored (0074).
