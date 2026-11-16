# 0088 Shown text settles: Live updates finishes long speech in pieces, and settled words never change

- **Status:** accepted
- **Date:** 2026-11-13
- **Decided by:** polyglotic-hq project 296 (the user, 2026-11-13: "We
  don't need to rewrite words spoken 3 seconds ago right?" and "after 1-2
  lines, lines should settle"); Claude reviews it with the pull request,
  and the user may overrule it.

## Situation

In Live updates a caption grew for as long as the speaker didn't pause:
the app sent the whole stretch again at every live update, and when the
stretch ended - or at 20 s - the finished caption heard all of it once
more and replaced every word shown, with its translation. Words the
learner had read ten seconds earlier changed under their eyes.

Steady and Quick preview already finish unbroken speech in pieces (the
breath cut, polyglotic-hq 260: after 3 s at a 0.3 s pause, at 6 s
whatever). Live updates had been left out, because its live updates
already showed text along the way.

296 measured it: five minutes of public recordings (FLEURS, read
speech, clips end to end) through the app's own speech detection and
timing, on the real models, Live updates every 1.5 s.

| English, 5 min | Before | In pieces |
|---|---|---|
| Updates that rewrote words already shown | 22 of 172 | 8 of 183 |
| Words rewritten | 34 | 8 |
| ... of them shown for 3 s or more | 15 | 0 |
| The oldest word rewritten had been shown for | 11.1 s | 1.7 s |
| The furthest above the newest word (lines of 48 characters) | 4.0 | 0.5 |
| Translation rows changed after standing 3 s or more | 14 | 0 |
| Word error rate against FLEURS' text | 4.42% (31/701) | 4.71% (33/701) |

| Mandarin, 5 min | Before | In pieces |
|---|---|---|
| Updates that rewrote characters already shown | 18 of 133 | 8 of 139 |
| Characters rewritten | 31 | 10 |
| ... of them shown for 3 s or more | 11 | 0 |
| The oldest character rewritten had been shown for | 7.4 s | 3.0 s |
| The furthest above the newest (lines of 24 characters) | 1.8 | 0.7 |
| Translation rows changed after standing 3 s or more | 8 | 0 |
| Character error rate against FLEURS' text | 9.86% (80/811) | 10.48% (85/811) |

## Decision

- **Live updates has the breath cut too**, the same numbers as Steady's:
  `BREATH_CUTS[CaptionMode.LIVE] = BreathCut(after=3.0, pause=0.3,
  limit=6.0)`. A caption that has run 3 s finishes at the next 0.3 s
  pause, and at 6 s whatever; the next words start a new caption below
  it. So a live caption is never more than about 6 s of speech, and the
  finished caption that replaces it hears only that.
- Live updates carry on inside each piece, at the interval chosen.
- Enforced by `tests/test_timing.py`
  (`test_live_updates_finish_unbroken_speech_in_pieces`,
  `test_live_updates_finish_at_a_breath_once_a_caption_has_run_a_while`)
  and the rule cases in `docs/rule-cases/timing.json`.

## Why

- The rewriting came from re-hearing a long stretch. Shorter stretches
  leave less to re-hear: nothing older than a piece can change.
- Steady's cut was measured for accuracy and delay in 260 and 282; using
  the same numbers keeps one rule to tune.
- **The cost:** a piece is heard with less speech before and after it
  than a whole 20 s stretch, so a word at a cut can be heard worse. In
  the measurement above the error rate went from 4.42% to 4.71% in
  English (two words in 701) and from 9.86% to 10.48% in Mandarin (five
  characters in 811). That is one five-minute sample of read speech in
  each language, not a claim.
- Not taken: keeping the long caption and freezing its old words in
  the app alone. That hides the rewriting but still sends up to 20 s
  again at every live update. (The app does also keep settled words, as
  a guarantee: see "Settled text" below, added with its own pull
  request.)
- Not taken: a new look for Live updates (one growing paragraph). It's
  the user's to decide (polyglotic-hq 296's report proposes it).

## What would make us reverse it

Live updates measurably less accurate than Steady on conversation or
film speech at the same cut; or learners preferring one long caption to
several short ones in Live updates.

## Settled text (added 2026-11-13, with its own pull request)

*Amended 2026-11-14 by
[0099](0099-how-long-shown-text-may-change-is-the-learners-choice.md):
the 3 s below is the default of a setting, 0 to 3 s.*

Pieces make the rewriting rare; they don't rule it out. A piece runs up
to 6 s and its finished caption re-hears all of it; a fragment joins the
caption before it; a slow answer can arrive seconds late. So the caption
history also keeps a rule of its own, in the user's words: "after 1-2
lines, lines should settle" and "we don't need to rewrite words spoken 3
seconds ago".

- **Settled words never change.** Words a caption has shown unchanged
  for 3 s (`SETTLE_AFTER_SEC`), and every clause above its last two
  (`OPEN_CLAUSES`), are settled. An update - the next live update, the
  finished caption, a join - is the same speech heard again:
  `CaptionHistory.apply` keeps the settled words and takes only what
  comes after them from the update (`core/listening/settling.py`). Never
  half a word, and never the last word of a live caption, which may be
  half said.
- **A word has stood since the text before it last changed.** A rewrite
  earlier in a caption starts the count again for everything after it:
  the rule is about the text as read from the start, so it never has to
  guess which later word is "the same" one.
- **Settled rows keep their translation and their place.** A settled
  clause that has its translation keeps it. One still waiting for a
  translation takes the update's. Where the update splits the speech
  into clauses differently, the row at the boundary is the update's -
  the settled words stay, and a translation never says part of a line
  twice.
- **Where the update carries on** is found by lining its words up with
  the shown ones (word by word; character by character in Chinese and
  Japanese). How they are lined up changed with
  [0091](0091-two-hearings-are-lined-up-by-the-fewest-words-passed-over.md):
  `difflib` could take a common word further on for a settled one, and
  leave out the words between.
- It applies in every timing, and wherever captions are kept: the rule
  is in `CaptionHistory`, and each caption window, each transcript and
  the app's own feed keeps one. Each settles by when it showed the
  words itself. They take an update in the same instant, so they agree
  - except where one of them showed it later (a caption window holds
  new captions while the mouse is over it; the Lab's arrival gap): there
  the window keeps what it had shown for 3 s, and the transcript may
  have the corrected word. Known and accepted: the promise is about
  what the learner saw in that place.
- Enforced by `tests/test_settling.py` (the rule, and 500 made-up pairs
  of hearings: the settled words always stay, word for word) and
  `tests/test_caption_history.py`.

### What it costs

The finished caption hears more speech than the live update it
replaces, so it is the better hearing; keeping settled words throws
away its corrections to them. Measured on the same recordings, by
replaying each through the history with the rule off and on:

| Recording (5 min each) | Words shown 3 s or more, then rewritten: rule off -> on | Error rate: off -> on | Words that end up different |
|---|---|---|---|
| Live updates in pieces, English | 0 -> 0 | 4.71% -> 4.71% | 0 |
| Live updates in pieces, Mandarin | 0 -> 0 | 10.48% -> 10.48% | 0 |
| Steady, English | 0 -> 0 | 4.71% -> 4.71% | 0 |
| Steady, Mandarin | 0 -> 0 | 10.48% -> 10.48% | 0 |
| Live updates as before pieces, English | 15 -> 0 | 4.42% -> 5.85% | 15 of 701 |
| Live updates as before pieces, Mandarin | 11 -> 1 | 9.86% -> 10.73% | 10 of 811 |

With pieces, no update in these recordings reached a settled word, so
the rule changed nothing and cost nothing: there it is a guarantee, not
a change. Where it does act - the last two rows, long stretches
re-heard - it costs about one word in a hundred. (The one Mandarin
character left: it had stood 3.5 s by itself, but the text before it
had changed more recently, so the rule didn't count it as settled.)
One sample of read speech in each language, not a claim.

### Not taken

- **5 s instead of 3 s**: fewer corrections lost, but words read five
  seconds ago still change (on the before-pieces recordings: 3 words
  and 8 characters shown 3 s or more were still rewritten; error rates
  5.71% and 10.11%).
- **The server sending only the new words**: the right long-term shape
  (less speech re-heard, less to send), but a protocol change; the app's
  rule is needed anyway for older servers and late answers.
- **Marking a corrected word instead of keeping the old one** (a quiet
  underline, the correction on hover): a look for the user to decide.

### What would make us reverse it

Learners seeing a wrong word stay wrong where the finished caption had
it right, more often than the rewriting bothered them: the measure is
the error rate with the rule on against off, on conversation speech.
