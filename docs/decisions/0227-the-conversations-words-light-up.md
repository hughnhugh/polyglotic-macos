# 0227 The conversation's words light up in our curriculum's set

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude, from the user's direction of 2026-11-18 (~06:30,
  answering polyglotic-hq DECISIONS #209: "I'd expect 2-10 words on each
  screen", "stretch words should definitely be included and arguably a
  prerequisite", "Theme should constantly update on some rate, every few
  minutes"); polyglotic-hq 491's brief and report, on 485's research.
  Amends decision 0219 (our curriculum's active set) in two places, said
  below.

## Situation

Our curriculum's active set (0219) lights 50 words in the quiet view: the
words the learner's audio said first, then the load's order. In what a
learner watches, few of them are said: on 75 public conversations the
load's order came up again 0-15 % of the time (485), so a screen of
captions showed almost no blue. And #859's heard-first fill took any word
heard once, with no bound past the line, so 嗯, 呃 and "um" - which the
packs' written ranks place past 3,000 - were among its first words.

The user wants 2-10 blue words on a screen, the conversation's own core
words first (业主 in a residents' meeting, "rubber" in a design meeting),
and the choice to follow the conversation as it moves.

## Decision

- **A source's window** (`core/learning/theme.py`): the finished captions
  of one source (an app, never the learner's own mic) over the last 10
  minutes, kept in memory on the PC. Nothing new leaves the PC and nothing
  new is stored but the set's rows.
- **An update every 2 minutes of that source's talk.** At it, the
  conversation's words enter the set **mid-sitting** - the one exception
  to 0219's "only between sittings" - in this order: **stretch words**
  (past the learning window, said in 3+ captions of the window, the most
  said first; in Chinese two characters or more, and never a word with no
  place - on live captions one rare character was a piece of a name, 潇
  and 璐 of 黄潇璐, and an unranked word a phrase, 那时候), then **theme
  words** (in the learning window, said in 2+ captions, the keyest first:
  said most above their everyday share). Never a name, a number (二十, or
  spelled out: "fourteen") or - in English, whose capitals inside a
  sentence mark only names - a word never written in small letters in the
  window ("Julia": a name the dictionary doesn't know; German's nouns keep
  theirs). They
  enter while the set's words make under 1.0 blue word a caption of the
  window (each word's share of captions said it), 10 at most an update. A
  look-alike of a lit word (one character or letter apart) waits.
- **Making room:** a conversation's word takes the place of the newest word
  never met (the load's order's before heard-first's); never a met one;
  else it waits.
- **Resting:** a conversation's word not said for 10 minutes (out of every
  window) rests at the next update: out of the set, its days met kept
  (a new `Standing.RESTING` row), back in when it is said again. The 3
  separate days that retire a word (0219) still count across rests.
- **Heard-first fixed** (amends 0219): at a sitting's start the set fills
  with the words heard in 2+ captions, inside the learning window, never
  everyday talk or a number - then the load's order.
- **Everyday talk is never lit** by the theme or heard-first: a filler
  (嗯, 呃, "um", "uh-huh": a hand list of interjections), or one of the
  3,000 commonest spoken words said at least 3 times more often than its
  written place says (就是说, 没什么, "okay"). And a word whose spoken rank
  is within the learner's known words counts as known here. The spoken
  ranks come from separate data: OpenSubtitles 2018's counts
  (FrequencyWords, CC BY-SA 4.0 - the source Russian's ranks already use),
  made into `core/lexicon/spoken_ranks.py` by `tools/spoken_ranks.py`, and
  carried to Learning in `EntryFacts.spoken_rank` and `is_filler`.
- **The theme's name:** in the quiet view the hover strip shows, after the
  source's label, the window's 3 keyest words at any level past the
  commonest 1,000 ("业主 · 小区 · 物业").

## Why

- **Density, not a count:** 485's "3 every 5 minutes" was too few for the
  user. A rate per caption is what a screen shows; the measured supply of
  words said twice binds before the target in nearly every conversation
  (491's sweeps: targets of 0.6, 1.0 and 1.5 gave 0.38-0.43 blue words a
  caption in Mandarin meetings, a learner at 1,000 words).
- **Stretch words first** were the user's "prerequisite"; at a gate of 3
  captions every meeting had them and 43 % came again within 10 minutes
  (2 captions: 34 %; 4: 47 % but fewer).
- **On the PC:** it holds every caption it shows; a server-side memory
  would add only what the PC can't see (another device's listening, other
  learners' streams), which nothing here needs. The seam: `Curriculum`
  reaches the windows only through `ConversationThemes`' calls (`heard`,
  `withdrawn`, `window`, `said_lately`, `form`); a server's conversation
  memory (polyglotic-hq 487) would come in behind them as an adapter.
- **Spoken ranks, not 485's everyday list:** that list was made from the
  conversations it was measured on. Subtitles are speech, separate, already
  licensed and pinned for Russian. Not taken: a 512 MB model to name
  themes, vectors to pick (485: they changed 3 picks of 57).

## What would make us reverse it

- Testers find the blue words jumping about mid-sitting, or reading a
  caption while words light distracts them.
- The comes-again rate of lit words on testers' real listening (content-
  free counts) falls well under heard-first's.
- Subtitles' own bias shows: film words (警察, 长官, "sir") treated as
  everyday talk where a learner needs them.

## How we'd reverse it

- Mid-sitting entry: `Curriculum._conversation_update` is one call in
  `caption_finished`; without it the set is 0219's again (resting rows
  would then never come back - delete them, or let heard-first take them).
- The density and gates are constants in `curriculum.py` and `theme.py`.
- Everyday talk: `theme.everyday`; another spoken source means rerunning
  `tools/spoken_ranks.py` against it.
- No file format changes: `Standing.RESTING`, `Came.THEME` and
  `Came.STRETCH` are new values in the existing text columns; an older app
  leaves rows it can't read where they are.
