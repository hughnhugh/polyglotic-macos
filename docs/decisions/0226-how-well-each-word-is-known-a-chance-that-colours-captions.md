# 0226 How well each word is known is a chance from 0 to 1, and Learning load colours every caption word by it

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user, 2026-11-18 ~06:08 (polyglotic-hq 489's brief:
  "Learning load should be a relative word known predicter. every word
  has a colour based on your knowledge of the language ... red (or
  completely unknown) ... green (mastered word). everything in between
  represents exposure or partial knowledge"). The numbers below are
  Claude's starting values, built in polyglotic-hq 489, and are meant to
  be tuned.

## Situation

`Knowledge.of` (polyglotic-hq 349, decision 0163) gives one yes-or-no
answer per word, and the known line is a step: every word within "I know
about N words" is known, and every word past it is new. The user wants a
colour for every word that shows how well it is known, with exposure and
partial knowledge between unknown and mastered. Their measure of
progress is fewer red words and more green.

The Lab's Learning load mode (324, decision 0117) coloured only the
load's next words, by stage. The user now wants that mode to show this
colour instead.

## Decision

- **The predictor** is `core.learning.known_chance.KnownChances`, held by
  `Vocabulary` as `chances`. It gives each word a chance from 0 to 1,
  with where it started and what moved it.
  - It works on the log-odds scale (x), and the chance is
    `1 / (1 + e^-x)`.
  - **Where a word starts** comes from `Knowledge.of`, so a word's
    evidence is read in one place:

    | What `Knowledge.of` says | Start (x) | Chance |
    |---|---|---|
    | The learner said known (graduations too) | +4 | 0.98 |
    | Known by an import | +3 | 0.95 |
    | A number in numerals | +3 | 0.95 |
    | Known by the words it is made of | +1.5 | 0.82 |
    | In the deck | -1 | 0.27 |
    | Turned new by two pinned lookups | -1 | 0.27 |
    | Not known by the words it is made of | -1.5 | 0.18 |
    | The learner said new | -3 | 0.05 |
    | Nothing places it: taken as the 30,000th word (rarer than the map) | the curve there | 0.05 at a line of 7,000 or less, 0.30 at 20,000 |

    A compound is placed no further than twice its rarest part (Chinese:
    its characters, `PARTS_FACTOR`). 输掉 is the 83,039th word in
    CC-CEDICT's list, but 输 is the 2,836th and 掉 the 987th, so it is
    placed at 5,672. Only where every part is placed. Word links still
    ask `Knowledge`, which doesn't read parts yet (349's step 2).
    | Ignored, or a name | not coloured | - |

  - **A placed word with nothing said about it** starts on a curve:
    `2.13 x ln(line / place)`, kept between -3 and +4.
    - The chance is 0.5 at the line, 0.82 at half the line and 0.18 at
      twice the line.
    - The slope 2.13 is 019's simulation's word-by-word spread (0.8 in
      natural-log rank) written as a logistic: 1.702 / 0.8.
    - The curve agrees with `Knowledge.of`: a word within the line is at
      0.5 or more, and a word past it is under 0.5.
  - **What moves a word:**

    | Evidence | Moves x by |
    |---|---|
    | Heard from what the PC played (never the mic), per separate day before today | +0.5, up to 5 days |
    | Saved | +0.5 |
    | A pinned lookup, then heard on a later day with no lookup since | +1 |
    | A pinned lookup in the last 3 days | -1.5 |
    | Two pinned lookups since the learner said they know it | -1.5 |

    Three rules go with it:
    - A word the learner has met is at least 0.16, out of red.
    - Today's hearing counts from tomorrow. Every word of a caption has
      just been heard, so counting it at once would mean no caption word
      could ever be red, and a word's colour would change while it was
      being read.
    - What raises a word never takes it past 0.80, and never lowers a
      word that started higher. Exposure and partial knowledge are the
      colours between; only what the learner said, or the line, makes a
      word green.
    - Every result is kept between 0.01 and 0.99.
  - **The bands:**
    - Red is under 0.15.
    - Green is 0.85 or more. This is 019's "sure" threshold, mirrored on
      the log-odds scale.
    - Everything between is exposure or partial knowledge.
  - **Speed:** about 2.6 µs a word on the user's PC. It is worked out
    per caption, with `each()`.
- **The separate days a word was heard on** are learning file version 11:
  `exposures.days_heard` and `exposures.last_heard`.
  - Each day is the learner's own, the PC's.
  - They are filled in from the daily counts still kept (the last 8
    weeks, in UTC days), and are at least 1 for a word already heard.
  - They stay on the PC, as exposure counts do.
- **Learning load's mode** (the Lab's switch, `Panel.load`) now colours
  every word of a finished caption in the language in use (the main
  tools', as the load is) by its chance. A row in another learned
  language beside it keeps its own marks (306). It replaces new-word dots, deck dashes and saved words'
  colours; word links are drawn as before.
  - There are two palettes (`views.known_colours`): red to green, the
    default, and orange to blue for red-green colour blindness.
  - Both run dark to light on a dark panel and light to dark on Paper's
    cream, so they read in greyscale.
  - Every colour reaches 4.5:1 against its panel and follows Vibrance.
    The contrast slider doesn't soften them: like saved words' colours,
    they stay readable whatever it says.
  - The stage colours, the stage underlines and "Words outside the load"
    are gone from captions. The Lab's `load_rare` setting is read as
    nothing.
- **The whole language at a glance** is on Learning
  (`core.learning.known_map`, `ui_next.known_map_card`), after 474's map.
  - It shows the 20,000 most common words of the language in use, one
    square each, commonest first, coloured as the captions are. A native
    speaker's map is all green.
  - Progress is measured the way the user defined it: the counts of red,
    between and green words, plus the share of what's heard that's
    green. Each word in that share is weighted by 1 / its place (Zipf's
    law), so it is an estimate from ranks, not from what this learner
    heard.
  - "In the last 7 days" rebuilds the map as it stood 7 days ago:
    - the statuses and the line from 477's histories;
    - the days heard, less those with a daily count since;
    - lookups and saves made since are left out.
  - Its words are read once per language and scheme, off the interface
    thread: about 0.7 s on the real CC-CEDICT. The chances, now and a
    week ago, take about 90-120 ms each time Learning shows the card.
- **The learning load itself stays.** It is still the next words to
  learn, their stages and the check, on Learning and on the lookup card.
  It is also what the quiet view's "Learning load" choice shows in blue.
  - The load's words are the red-to-amber words just past the line, and
    graduating one sets it known, which turns it green.
  - The load's meetings don't move a word's colour separately. The days
    it was heard on do that, the same for every word.

## Why

- A chance, rather than a fourth status, keeps `Knowledge.of` the one
  answer for links, marks and coverage. The colour is a reading of the
  same evidence, so the two can't disagree about which side of the line
  a word is on.
- The curve's spread comes from the only model we have (019).
  Frequency-profile studies of learners show the same shape, but that
  is from memory and was not re-read for this decision.
- Days rather than captions: hearing a word ten times in one video is
  not ten separate exposures. Our curriculum retires words by separate
  days for the same reason (473, 0219).
- **Alternatives not taken:**
  - A step with three bands. This is the old line with extra colours,
    and the user asked for "relative".
  - Fitting per-learner parameters. There is no data to fit them to yet:
    the 474 test and the review loop will supply it.
  - Colouring live captions. Their words change as they are spoken, so
    the colours would flicker.

## What would make us reverse it

- The test (019, 474) or reviews show the curve is too steep or too
  shallow. Answered words predicted at 0.8 would then be right far more
  or less often than 80 % of the time.
- Learners find exposure moves words too fast or too slowly.
- Testers find the colours of a whole caption too busy to read.

## How we'd reverse it

- The numbers are constants in `known_chance.py`. Changing them is a
  one-line edit plus the tests that pin them.
- A fitted slope per learner would replace `SLOPE` with a value stored
  beside the line.
- Turning the colours off in captions means flipping `Panel.load`'s
  branch in `caption_marks.py` back to the stages. 324's code for that
  is in this repository's history, before 489.
- Version 11's columns can stay. An older app refuses a newer file, as
  every version does (decision 0010).
