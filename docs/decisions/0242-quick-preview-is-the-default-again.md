# 0242 Quick preview is the default again, for everyone who hasn't chosen

- **Status:** replaced by [0246](0246-steady-is-word-by-word-and-the-default-quick-preview-retires.md); it replaced the default in [0055](0055-steady-is-the-default-again.md) (its "a choice stays" rule is kept)
- **Date:** 2026-11-18
- **Decided by:** the user, after trying 0.1.9's preview 1 (2026-11-18,
  polyglotic-hq project 522's brief: "I guess quick preview is our desired
  mode to optimise ... the balance between live updates and steady ...
  gives people an option to go steadier or more live ... comes with the
  most engineered behaviour"); polyglotic-hq 522 built it; Claude reviews

## Situation

0055 made Steady the default on 2026-11-09. Since then Quick preview has
kept updating through long speech (260), every mode got the longest wait
for text (277) and the listening mark, and the provisional line settles
in place. The user now wants Quick preview, the middle of the three, to
be what a learner starts on and what the timing work tunes.

## Decision

- `core.listening.timing.default_caption_mode()` returns Quick preview.
  It is still the one place the default is decided.
- 0037's and 0055's rule stands: the settings keep only the mode the
  learner **chose** (`caption_mode_chosen`). One who chose Steady or Live
  updates keeps it; one who never chose is on Quick preview from their
  next start.
- Settings > Timing records a mode as chosen only when the learner picks
  one (another mode than the one followed, or any once they have chosen):
  moving the longest wait for text, or Live updates' interval, no longer
  saves the mode followed as chosen (`main.timing_changes`). Before this,
  any change there pinned a learner to the default of the day.
- Help's "When do captions appear?" names the default first. The Timing
  panel keeps its order, steadier to more live - Steady, Quick preview,
  Live updates - with the default between ("an option to go steadier or
  more live").

## Why

- Quick preview shows the first words about 2 seconds in, as a dim line
  the finished caption replaces: sooner than Steady (about 4.5-5.5 s,
  project 145), without Live updates' rewriting.
- Its cost is about 1.4-1.7x Steady's GPU work (projects 021 and 033);
  the alpha's numbers are small enough for that.
- Not taken: Quick preview for new installs only - one rule, "the default
  moves everyone who hasn't chosen", as in 0055.

## What would make us reverse it

The alpha's `caption_mode` statistics show most learners leaving Quick
preview for one mode, or the server's GPU time per caption becomes the
limit on how many learners a card serves.

## How we'd reverse it

Return another mode from `default_caption_mode()`: everyone who hasn't
chosen follows at their next start. Help's "When do captions appear?"
names the default first and changes with it (a test checks).
