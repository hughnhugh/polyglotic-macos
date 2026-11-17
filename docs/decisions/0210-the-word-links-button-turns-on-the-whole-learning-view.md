# 0210 The word links button turns on the whole learning view

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** the user (what the click shows: polyglotic-hq 446,
  2026-11-17); Claude, for project 446 (how it is built, a reversible
  choice)

## Situation

A caption window's Word links button (249's F9) turned word links on as
Colours, underlines alone, unless another way had been chosen in Look.
Since 395 and 431, a learner could also colour linked words in what was
said and in the translation, and draw pinyin in its word link's colour,
each a separate setting that was off. To see the view in the user's
preview-3 screenshot a learner needed five settings in two places.

The user, 2026-11-17: "the word linkage caption window nav bar option
should default switch on with arrows ... also showing pinyin colour,
translation text colour matching and caption colour matching ...
essentially this should be the one click default", and "a first time
user selecting the word linkage nav bar icon should see all coloured
linked words / pinyin etc."

## Decision

- **One click on** (`views.panels.learning_view`): word links as the way
  last chosen in Look this run, else Arrows (with their lines); linked
  words in their link's colour on both sides; pinyin in its word link's
  colour, unless the learner picked a colour of their own; and the
  reading line of the clicked window's languages (`CaptionWindow.readings`:
  "zh" for a window whose spoken language, translation or second language
  is Chinese, or which has heard Chinese).
- **A saved Underline isn't a way chosen:** before 446 the button itself
  saved Colours (Underline). At start, a saved Underline doesn't become
  the button's way, so a tester's next click after the update shows the
  lines; a saved On hover or Arrows, and any way chosen in Look while the
  app runs, still do (`LookView._remember`).
- **One click off**: word links off and the other four back to what they
  were before the click on (kept while the app runs, as the filled lines
  button keeps the Lab, 372). Not known - links turned on in Settings, or
  before a restart - only word links go off.
- **New defaults**: both sides coloured and pinyin in its link's colour.
  Word links stay off until the learner clicks, so a new install looks the
  same until then; turning links on in Settings shows the same view.
  Settings saved by a 0.1.7 preview's single switch keep its value
  (`ui.settings._migrated`).

## Consequences

- The Settings rows and the popover's switches are the same values: a
  change there while the view is on shows at once; the click off still
  puts back what was there before the click on.
- A learner who turned a part off before gets it on again with the next
  click on: the click is the whole view. Their choice comes back with the
  click off.
- To make the button word links alone again, `learning_view` is the one
  place to change.
