# 0030 "Looks wrong?": a line checked with the best model, over the listening session, nothing kept

- **Status:** accepted; its interface taken out by [0131](0131-looks-wrong-leaves-the-interface.md) (2026-11-15) - the protocol and the server's side stay
- **Date:** 2026-11-06
- **Decided by:** the user's idea (2026-11-06); project 087's picks taken as defaults (polyglotic-hq DECISIONS.md #42); brief 101. The server's side is polyglotic-server decision 0031. Keeping a flagged line (the consent box) is not part of this: it changes the privacy line and waits for the notice (project 040).

## Situation

The learner sometimes sees a caption that looks wrong and can't tell
whether the small models misheard it. The app now holds the last two
minutes of finished speech in memory (decision 0027), and the server can
run a line on its best models (server decision 0031).

## Decision

- **Three ways in** (087, wireframe 2.1): "Looks wrong?" at the top right
  of a finished caption hovered on the unlocked overlay (drawn on the
  canvas, `Overlays.looks_wrong`); "Looks wrong?" beside a hovered
  Transcript row; **Ctrl+Alt+W** for the newest finished line, a hotkey
  like L, P and H, so it works over a game with the overlay locked.
- **The comparison is a card over the main window** (`ui/looks_wrong.py`,
  `ComparisonCard`), never over a game: what was seen and the best
  model's version, original and translations, what differs boxed
  (`core.listening.recheck.differences`: whole words, or characters in
  Chinese and Japanese); optional answers.
- **The flow** (`LooksWrong`): the line's held speech
  (`SpeechPipeline.get`, the `RecentSpeechPort`) goes out as a recheck
  frame on the **listening session** (`ListeningSession.recheck`), with
  the listening settings as they are now; the answer comes to the
  listener's `rechecked` and is queued to the Qt thread. Not held any
  more, nobody listening, or no answer in 30 seconds are said on the card
  at once - no retries.
- **"The best model is right"** puts the best model's version in the
  caption's place in the history (`CaptionHistory.use_checked`): the
  Transcript (and the overlay) show it, marked "checked by the best
  model", and its words are counted for Learning instead of the first
  version's. The first version is kept on the caption (`first_shown`)
  while the history holds it; it isn't shown yet.
- **Nothing is kept**, from calls or anything else: the card holds the two
  versions while it is open. When it closes, the content-free
  `line_flagged` usage event (language, source category, outcome, answer)
  is kept to send - only with consent to usage statistics.

## Why

- **The listening session** carries it because the held speech exists
  only while sources are captured, i.e. while listening; a sync session
  would add a second connection for a few seconds' work.
- **A card, not a page:** a check is a moment's question; the Transcript
  stays where the learner was reading.
- **No retries:** a failed check is rare and the learner can ask again;
  sending audio again on its own would surprise them.

## What would make us reverse it

- Learners want to check lines older than two minutes: the hold (0027)
  changes, not this.
- Keeping flagged lines is agreed (the consent box, Settings' "Lines I
  flag"): a new record, after the privacy notice.
- Model levels are shown to learners (server decision 0019 leaves it
  open): the card's wording changes.

## How we'd reverse it

The feature is `core/listening/recheck.py`, `ui/looks_wrong.py`, the
overlay's and Transcript's buttons, the W hotkey, `use_checked`, and the
recheck paths in `connection/`. Removing it removes those; the protocol
messages stay valid on the server.
