# 0230 Words at your edge; a conversation's word retires when known; names stay names in Chinese

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude, from the user's direction ("2-10 words on each
  screen", "alternate word selection methods", "go with safe defaults
  but take into account my direction" - polyglotic-hq DECISIONS #215 and
  #214's note); polyglotic-hq 496's brief and report, on 491's live
  captions. Amends decision 0227 (the conversation's words) in one place
  and 0219 (our curriculum) in one, said below.

## Situation

On 491's live captions a learner of 1,000 words saw 0.67 blue words a
quiet-view screen in Mandarin (16 % of screens in the user's 2-10) and 3.3
in English (79 %). A Mandarin talk repeats too few words at that edge for
our curriculum's set to light more, and no setting of the set raised it.
Across a series (one learner, 20 Mandarin meetings a day apart) the set's
3-day retirement halved the blue: the series' core words (业主, 物业) were
met on 3 days and retired. And names lit and were coloured as words: 万里 of
黄万里, the pieces of a foreign name the dictionary hasn't got (杜|瓦|尔 of
杜瓦尔, 米|勒 of 米勒), 乃 and 凡 of 张乃器 and 张立凡.

## Decision

- **Words at your edge** (`ChosenWords.EDGE`, `Vocabulary.at_edge`, `lit`):
  a fourth choice of the quiet view's blue words. Any word in the
  learner's learning window, new or in the deck, each time it is said -
  never a name, a number (in numerals or spelled out), everyday talk or a
  filler, nor a word heard so often the learner knows it (491's filters);
  in a language whose capitals inside a sentence mark only names
  (English), never a word written with one there ("Agency" of the Central
  Intelligence Agency).
  It lights while a caption shows fewer than `EDGE_PER_CAPTION` (2) blue
  words, the commonest first: the user's "a couple per sentence". The
  other chosen words always light. Ticked by default for a new learner
  (`DEFAULT_CHOSEN`, `AppSettings.quiet_words`); a settings file that
  holds the choice keeps it. Not kept in the named set `QUIET_SET`: it is
  a rule, not a list.
- **The learner's chosen learning window** reaches `Vocabulary`
  (`set_window_size`, from `LearningTools.set_choices`): words at your
  edge and our curriculum's conversation words follow it (491 used the
  default 1,000 words).
- **A conversation's word retires when the learner knows it** (amends
  0227 and 0219): a theme or stretch word met while 489's chance says
  green (0.85 or more; `KnownChances`, decision 0226) retires; set known
  or ignored it leaves, as before. It no longer retires on its 3rd day
  met. A word that came by being heard or by the load's order keeps
  #859's 3-day rule. Hearing alone never makes a word green, so in
  practice a conversation's word lights until the learner says they know
  it or their line passes it.
- **Names stay names in Chinese** (`core/lexicon/chinese.py`): a run of
  word-split pieces side by side made only of the characters Chinese
  spells foreign names with (`SOUND_CHARACTERS`), with a lone character
  rarer than the 2,000th word, is a name (`names_spelt_by_sound`, in
  `words_in`); and a word its translation writes by its sound,
  capitalised (Wanli for 万里, Nai for 乃) is a name
  (`named_by_sound`, through the caption's word links: `LearningTools.words_in(said=...)`,
  `CaptionFeed`'s words for Learning and the caption window's marks). A
  name is neither coloured by how well it's known nor lit blue, and our
  curriculum never takes it.

## Why

- The edge words are the supply 491 measured: 0.57 a caption in Mandarin
  and 1.09 in English for a learner of 1,000 words. With them Mandarin
  reaches the user's 2-10 on about 60 % of screens (from 15 %); the cap of
  2 a caption keeps English at 93 % (without it 82 %, with 18 % of screens
  over 10).
- The series keeps its blue: 0.38 a caption in the second half of the
  Mandarin meetings (0.15 with the 3-day rule).
- Every word the translation's sound found in 491's 282 live clauses with
  word links was a name or a place; of the 33 sound runs found in 491's
  live captions, 100 FLEURS sentences and 485's 10,540 meeting lines, 31
  were names, one a name with a word stuck to it (埃里克因, 因 "because")
  and one not a name (沙什) - without a new data file.

## What would make us reverse it

- Learners find the edge words noisy, or untick them: the cap, the
  default or the choice itself would change.
- A conversation's word that never retires crowds the set: 474's test gives
  answered words, and the chance can turn green from them; or a cap on a
  word's days could come back for conversation words.
- A name rule that hides real words often enough to matter (a common
  word translated as its pinyin, a run of sound characters that is a
  phrase).

## How we'd reverse it

- Drop `ChosenWords.EDGE` from `DEFAULT_CHOSEN` and the settings default;
  or set `EDGE_PER_CAPTION`.
- `Curriculum._retires`: one line brings back the days for conversation
  words.
- `ChineseDictionary.words_in` returns the split's facts as they were;
  `LearningTools.words_in` ignores `said`.
