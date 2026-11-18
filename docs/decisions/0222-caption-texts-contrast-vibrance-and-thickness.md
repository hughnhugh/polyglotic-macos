# 0222 Caption text's contrast, vibrance and thickness are applied where captions are drawn, with a floor; word links keep their colours

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user asked for the two settings (polyglotic-hq 481's
  brief, 2026-11-18 ~04:57: "Make a contrast vibrance settings"); the
  floor, the curves and leaving word links' colours alone are Claude's
  reversible choices in 481, put to the user in its report. Thickness
  added the same morning (the user, ~05:15: "there should be different
  font thickness, visibility, contrast, brightness customisations").

## Situation

The learner wants two sliders in Settings > Look: how strongly captions
stand out from their panel (soft to crisp) and how vivid their colours are
(muted to vivid), for every caption window and transcript, every mode,
the quiet view (477) included, today's look in the middle. Captions are
drawn with many colours from many places: the look's two text colours, a
line's ink (newest, older, live, Quick preview's, the quiet view's), word
links' colours (lines, words, readings), saved words' categories, the
quiet view's blue, the learning load's stages, new-word dots and deck
dashes, readings, your own speech's colour.

## Decision

- **Two numbers in the look,** `CaptionLook.contrast` and `vibrance`,
  -100 to 100, 0 the look as it was; kept as `caption_contrast` and
  `caption_vibrance` (0 for anyone without them). They don't change the
  look's stored colours (a preset stays chosen); they're applied when the
  captions are drawn.
- **The arithmetic is plain Python** (`ui_next.views.tone`): `strength`
  (a line's ink: towards full ink up to crisp, towards Quick preview's
  0.6 of itself down to soft), `ratio` (what a colour moved to be
  readable is moved to reach: down to the floor on the soft side),
  `floor_alpha` and `floored` (never under 3.7:1 on the panel drawn
  solid, 3:1 seen through it over a light or a black video - unless
  today's look already is and the vibrance hasn't moved), and `vibrant` (chroma scaled in OKLCH, the
  dull boosted more than the vivid, greys left grey, hue kept, lightness
  kept or moved at most 0.05 where sRGB holds no more chroma).
- **Applied in three places:** `caption_window.look_ink` gives the ink
  the look's colours at the vibrance and the contrast;
  `caption_layout.drawn_ink` draws each row, label and quiet reading at
  the contrast's ink with the floor (and `link_ink` lowers its ratio with
  it); `caption_marks.Panel.vibrance` gives the marks' colours at the
  vibrance. A transcript follows the caption windows' (`set_tone`).
- **Thickness is a weight number** (`CaptionLook.thickness`, 300 to 700
  in hundreds, 500 - Medium, what captions have always asked for - by
  default; `caption_weight`). Qt draws the nearest weight each face
  really holds, so nothing is made bold that has a bold of its own.
  Readings ask one step above the text (`CaptionStyle.reading_weight`:
  today's 600 over 500), Bold at most. Windows lists Segoe UI Variable
  Display's Light and Semibold as families of their own
  (`fonts.WEIGHT_FACES`): they're named first at those weights, never for
  a reading. A font build (479) that ships real Medium faces honours the
  same numbers.
- **Visibility is an edge round the letters** (`CaptionLook.edge`,
  `views.tone.TextEdge`: none - today's - a soft shadow, an outline;
  `caption_edge`): the row and its readings drawn again under them,
  offset (`EDGE_PASSES`, grown with the text), in black around light text
  and white around dark (`edge_colour`), as faint as the text. How solid
  the panel is stays Look's own slider; Visibility's tip points to it.
  Caption windows only: a transcript is a page to read.
- **No Brightness slider.** On a panel, text's brightness is its distance
  from the panel: dimmer text on a dark panel is softer contrast, and on
  a light panel "brighter" text would be fainter. The two collapse into
  Contrast; two sliders would do the same thing.
- **Word links' colours keep theirs at every vibrance.** Their ten are
  at the edge of being told apart (446: 13.1 apart at the closest, 13
  needed); muting them took red and pink to 9.6 on Classic and green and
  mint to 7.9 on Paper, and vivid took green and olive to 12.2 on Paper.
- **The UI lab holds a soft caption window to 3:1 as drawn** (its
  `contrast_floor` property, set by the lab's soft states): everywhere
  else caption text must measure 4.5:1, and soft is the learner's choice
  to go under it - 3.7:1 as worked out, 3:1 in the pixels.
- Tested in `tests/ui_next/test_tone.py` (the arithmetic) and
  `tests/ui_next/test_tone_on_captions.py` (the numbers at each slider's
  ends on every preset, dark and light; the settings; the sliders and the
  keyboard; a transcript).

## Why

- At paint time, not stored: a slider back to 0 is exactly today's look,
  presets keep matching, and one number changes every colour together.
- One place for each kind of colour: the ink (`look_ink`, `drawn_ink`)
  and the marks (`Panel`). The alternative - a contrast and a vibrance
  per colour setting - would be a dozen controls nobody asked for.
- Alpha, not a mixed colour, for contrast: it's how Quick preview's line,
  older captions and the quiet view are already faint, so soft is "as
  faint as Quick preview" by construction.
- The floor (3.7:1): the faintest Quick preview line the user has seen
  and liked (477 measured 3.7:1 to 4.5:1), with room over WCAG 2.2's 3:1
  for large text for what italic's thin strokes cost (4.5 measured 4.3 in
  the UI lab, 477).
- OKLCH for vibrance: its lightness is perceptual, so a muted or vivid
  colour keeps its brightness (and its contrast) as no HSL change does.

## What would make us reverse it

- The user finds word links' colours should mute too, and accepts closer
  pairs - or a palette with room to mute is found.
- The floor proves too high (soft barely softer on some panels) or too
  low (testers can't read the softest).
- A colour drawn somewhere new doesn't go through `look_ink`, `drawn_ink`
  or the marks' `Panel`, and so ignores the sliders.

## How we'd reverse it

- Links following vibrance: `vibrant` on `LINK_COLORS` in
  `CaptionMarks` (where the other marks' colours are) and in the hover
  tint - a few lines, and the told-apart test's floor decided again.
- Another floor: `views.tone.FLOOR`, one number; its tests read it.
- Dropping the sliders: the two fields, the two settings, the row in
  Look, and the `strength`/`vibrant` calls (each a no-op at 0).
