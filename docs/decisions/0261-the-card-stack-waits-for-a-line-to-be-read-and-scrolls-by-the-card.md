# 0261 The card stack waits for a line to be read, and scrolls by the card

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, reversibly, on polyglotic-hq 553's first recording
  of the card stack ([0260](0260-steadys-captions-are-dealt-onto-cards-that-never-change-shape.md))
  against main, the same day. The user's words it answers: "lines getting
  pushed too much whilst I'm reading it" and "slow and smooth".

## Situation

The first card stack ended main's jumps, rewraps and vanishing lines (553's
table: jumps 34 to 4, rewraps 7 to 0, vanished 11 to 0 in four minutes of
Mandarin) but made one thing worse: 39 of 49 lines moved within 1.5 s of
being written (main: 10), because the stack made room for the next card
the moment the last word of a card was known. The same recording found:

- the wheel moved 140, 96 then 48 px, the first in one frame, and left a
  row cut at the foot under Back to live, which then jumped 350 px home;
- a change of mode or look laid the whole history out again in one frame
  (338 px sideways, 111 px down);
- a translation's room 12-17 px short of the translation, so it arrived
  cut and the page nudged;
- after a narrower window dealt the cards again, translations cut inside
  words ("Accordi|ng") and a row whose translation was another row's;
- a caption shown as it came, then finished on cards after a change of
  mode: the draft stood beside its final lines.

## Decision

Amended the same night after 553's second recording, which found the
dwell alone left an empty band at the foot for seconds, the page rising as
translations landed (17 times), translations cut with an ellipsis, a
13 px hop when the oldest line was dropped, and a grey flash on every
change of look.

1. **Room opens when the next card is heard coming.** The deck hears the
   server's text before the playout shows it (`Deck.coming`): when that
   text will need another card, the stack makes room in one glide - but
   not before the newest card has stood `CARD_DWELL_SEC` (1.6 s), nor
   within `TRANSLATION_REST_SEC` (0.7 s) of a translation landing. With
   nothing coming there is no room: no empty band while nobody speaks.
2. **A new line never rides the glide.** A card that comes before its room
   is ready stands in its place from the first frame, fading in as the
   stack rises from under it (`CaptionWindow.card_offset`).
3. **The glide is never fast**: at most `GLIDE_FASTEST` (300 px a second)
   however far it has to go, and at most three cards' height from its
   place.
4. **A translation lands only while the stack is at rest** (`Deck.reveal`,
   `Deck.flush`; never later than `TRANSLATION_WAIT_SEC`, 2.5 s): it
   comes into room measured for it (a probe card laid out with a
   translation and without) and moves nothing.
5. **A translation is never cut short.** A caption's translation is one
   text, cut between its cards at a word's edge - a run of Chinese at the
   dictionary's words; what doesn't fit a card runs on into the next, what
   doesn't fit the last goes back where there is room, and what still
   doesn't fit stays whole on a second line. As the caption goes on, words
   already shown keep their card. A new caption starts a card; a joined
   caption keeps its captions' words where they stood.
6. **Scrolling is by the card.** A wheel notch is one card, eased by the
   same glide, and the view rests with a card's top at its top; scrolled
   back, only whole cards stand. Back to live keeps its own strip under
   the cards and slides the stack home; the scroll bar eases the same way.
   While the stack glides, the cards beyond the view are drawn where it
   came from: no empty band.
7. **A change of look or mode never moves what was read in one frame, and
   never flashes.** Leaving Steady, finished cards stay as the captions
   they were (`Deck.finish`); only new captions are dealt when Steady
   comes back. A change that moves the rows (look, links, reading path)
   glides the stack from where its newest row stood. Only a new width or
   text size deals the cards again.
8. **Nothing leaves at full ink.** A card that the toolbar or a question
   comes to cover fades out over `COVER_FADE_SEC` and back in after; the
   newest card is always drawn. A card's label, once given, stays: the
   line above it leaving the list no longer names it again.
9. **The cards take a draft's place**: a caption first shown as it came is
   withdrawn when the deck first deals it.
10. **The learner can turn the stack off**: Settings > Timing, "Card
    stack" (`steady_cards`). Off: the two zones (0251).

## Changed on 2026-11-21 (553's third recording, 567's and 556's runs)

553's third recording passed on jumps, rewraps and translation pushes and
failed on lines pushed while read (18, 14 and 5 against main's 5, 1 and 7):
"the reading line floats, and the stack rises with nothing arriving". Items
1 and 6 above are replaced by these:

1. **The stack moves only when a card arrives.** No room is opened ahead
   (item 1 is withdrawn; `Deck.coming` now only tells a translation when to
   wait).
2. **A caption carries on on the front card** when it follows within
   `NEW_CARD_AFTER_SEC` (2.5 s) and fits: a short clause no longer starts a
   card and pushes the line just written. A card can hold more than one
   caption's words and translations, side by side.
3. **A new card waits while the line before it is new**: kept back until
   that line has stood `CARD_READ_SEC` (1.9 s from when it came, about 1.6 s
   at full ink), `CARD_WAIT_SEC` (0.6 s) at most. A burst of cards (text
   held back, then let go) comes in one card every `CARD_STEP_SEC` (0.5 s).
4. **A translation lands when the stack is at rest and no card is about to
   come, or in the frame a card arrives** - within `TRANSLATION_WAIT_SEC`.
5. **Scrolled back, the cards stand whole from the foot up**, as they do
   live: the last card that fits ends at the foot, and what doesn't fit is
   at the top, where the card before isn't drawn. A notch moves the stack
   one card. No card is cut, or fades, at the foot.
6. **Scrolled back stays scrolled back** until the learner goes back (the
   pill, End, the wheel or the bar to the newest): cards below the held one
   going (a caption set again or withdrawn) no longer let go of it
   (`Scroll.sticky`).
7. **Back to live is one slide the whole way** (up to `HOME_CARDS_MOST`
   cards), in the time a one-card slide takes - so it is fast when far:
   item 3's limit doesn't apply to a way the learner asked for.
8. **No scroll mark without a panel** (Video).

The cost: in fast speech in a narrow window, a card's words can be up to
0.6 s later than the playout gives them, and Back to live from far back
passes the cards between at speed.

## Changed again on 2026-11-21 (553's fourth recording)

The four complaints passed against main. What the recording and its review
still found, and what changed:

- **Back to live is one slide at the glide's own pace** (never faster than
  `GLIDE_FASTEST`), the whole way from up to `HOME_CARDS_MOST` (6) cards
  back; from further it starts that far from home. Item 7 of the list above
  (the same time however far) is withdrawn: it measured 1,128 px a second.
- **A new card shows once the card before has cleared its place**, not
  while that card's translation is still over it.
- **At the oldest cards the stack stands from the top** and the foot cuts
  the last card like any list's; everywhere else it stands from the foot.
  Scrolled back, only the top can hide a card.
- **Cards dealt again** (a new width or text size) start where they
  started: each caption is dealt at the time it came, so one that began a
  card after a pause begins one again; and the first card after a re-deal
  glides like any other.

## Changed a third time on 2026-11-21 (553's fifth recording, 572's reviews)

- **No room is kept for a translation that will not come**: a card whose
  captions were all said in the language the window translates into (the
  server translates only the others) is as tall as its words.
- **The first notch from live goes a card further**, and the notch back
  down returns to live: Back to live takes a strip of the foot, so one card
  back showed less than a card more.
- **Scrolled back, the cards start under the toolbar's strip** whether it
  shows or not: it never hides the top card and nothing moves as it comes
  and goes. The strip is empty while the toolbar is hidden.
- **Back to live from further than it slides** (more than
  `HOME_CARDS_MOST` cards beyond the view): the whole view fades out, comes
  home unseen and fades in at rest, `VEIL_SEC` (0.3 s) in all. No card is
  drawn anywhere but its place. This is the one fade of the whole view;
  decision 0260's "no crossfade" stands everywhere else.

## Consequences

- A notch is a card (about 60-90 px with a translation), not 48 px: the
  view can't both move a fixed 48 px and rest on whole rows.
- A translation can land up to the length of a glide (about 0.7 s) after
  it came, and a new line that had no room fades in over about 0.3 s.
- When the playout runs only a little behind the server, the room opens
  as the card comes rather than before it.
- Scrolled back, up to a card's height stays empty at the foot, above Back
  to live.
- The stack is in motion more of the time than main's list (which steps
  in a frame): each card is one glide of about half a second.
- A translation longer than its cards can hold takes a second line, and
  that card grows by a row when it lands.

## Checked by

`tests/ui_next/test_cards.py` (the glide either way and never fast, a card
seen coming, the deck put away, a translation never cut short nor inside a
word, shown words keeping their card) and
`tests/ui_next/test_card_stack.py` (room when a card is heard coming, not
as a translation lands, a translation landing only at rest, a new card
standing in its place, a notch a card and whole cards at rest, Back to
live, leaving Steady, a draft never beside its final lines, a
translation's room tall enough); `tests/ui_next/test_panels.py` and
`tests/ui/test_caption_paths.py` (the switch).
