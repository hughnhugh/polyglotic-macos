# The desktop's rules as shared test cases

What the app's rules must answer, as JSON, so a later port - a phone app
(polyglotic-hq project 050 recommends Kotlin Multiplatform), or the
server taking the timing rules over in protocol v2 - can be checked
against the same cases, as polyglotic-server's protocol examples check
each side's messages. Project 051, 2026-11-05.

- **Where the cases come from:** every input is one this repo's tests of
  the rule use (`tests/test_timing.py`, `tests/learning/test_levels.py`,
  `tests/learning/test_highlights.py`, `tests/lexicon/test_chinese.py`,
  `tests/test_caption_display.py`); every expected answer is what the
  rule gives today. `tools/rule_cases.py` writes the files;
  `tests/test_rule_cases.py` reads only the files and checks this app's
  rules against them.
- **Changing a rule on purpose:** change the code and its tests, then
  `uv run python -m tools.rule_cases write`; the diff of these files shows
  every answer that changed - a port has to follow it. Never edit them by
  hand (`tests/test_rule_cases.py` fails if they aren't what the tool
  writes).
- **Numbers:** times and chances are rounded to 6 decimals; compare
  within 1e-6. Text is UTF-8; spans are `[start, end)` in code points.
- Made-up words and sentences only; the Chinese sample is CC-CEDICT's own
  lines (CC BY-SA 4.0), as the tests use them.

## `timing.json` - the live-update timing rules

`core/listening/timing.py`: when to send live updates and finished
speech, long-speech splits, breath cuts, turn cuts, joins, the lead-in.

- `t0`, `frame_seconds` (0.032: 512 samples at 16 kHz).
- Each case: `rules` (`TimingRules`' fields: `schedule` `every` /
  `growing` / `glimpse`; `silence_hangover`; `breath_cut` `{after, pause,
  limit}` or null; `turn_cut`; `join_gap`; `join_only_under`; `lead_in`),
  `live_update_interval` (null: finished captions only), `pace_hint`
  (the server's `pace`, or null), and `sources`, each with an `id`, a
  `category` and a `pattern` of `[seconds, speaking]` stretches from the
  start.
- **Frames from a pattern:** frame `i` (from 0) of a source ends at
  `t0 + (i + 1) x frame_seconds`, for `i` below `floor(total seconds /
  frame_seconds)`; it is speech if its middle (`end - frame_seconds / 2`)
  falls in a speaking stretch `[from, to)`. Every source's frames are fed
  in order of their end time, then source id.
- **Caption ids:** `c1`, `c2`, ... in the order the rules ask for new ones.
- `decisions`, in order: a transcription request `{caption, kind (live /
  finished), source, start, end, section (live updates; null otherwise),
  replaces, at}` - `start`, `end` and `at` (the frame end that produced
  it) in seconds after `t0` - or a withdrawal `{withdraw, source, reason}`.
- **The caption modes** the app offers (Steady, Quick preview, Live
  updates - `CaptionMode`, project 064) are the last three cases, named
  for them: a port offering the modes uses exactly those `rules` and
  `live_update_interval` (Live updates' interval is the learner's).

## `levels.json` - the known line and the learning window

`core/learning/levels.py`: whether a word is known, in the learning window
or rarer. A word's `place` is the smaller of its frequency `rank` and its
level's vocabulary (`level_words`); `null` when it has neither. On the
`words` scale a word is `known` up to place `known`, `reached` up to
`window_last` (`known` + `window_size`, the default when `null`) and
`in_window` between the two. A `window_size` of `"unlimited"` has no end
(`window_last` is `null`): every word is reached, those with no `place`
too. On a level scheme's scale (a line kept as a level) it's known up to
level `known` and the window is the next level, whatever number
`window_size` is; unlimited, every level above it. `stored` is what the learning data keeps for the
line: the scale and, for a level, the point half a level above it.

## `highlights.json` - unfamiliar words

`core/learning/highlights.py`: which new words a finished caption shows.
`caption_cap`: how many a caption of so many dictionary words may show
with "a few per caption" (`common_only`). Each case: the line's `scale`
and `known` (its window the default size), `common_only`, how many
captions each word was `heard` in (missing: 0), the caption's `lines` of
words - each with its `start`/`end` in the line, `level`, frequency
`rank`, whether it's a `name`, and its `status` (as the learner's statuses
and the line give it) - and the words `shown` per line, in line order.
Without `common_only`, every new word the window reaches is shown; a line
kept as a level shows every new word, as it did before there were windows.

## `word-split.json` - the Chinese word split

`core/lexicon/chinese.py`, `ChineseDictionary.split`: the fewest, most
even words, ties to the commoner words; a headword without a rank that is
two words each among the 3,000 commonest (`COMMON_PARTS`) isn't a word,
unless it is kept whole (decision 0151). Each case is a dictionary - its
`headwords` (both scripts), `frequency_ranks` (by headword; missing:
unranked) and `kept_whole` (headwords that are a name, an idiom or a word a
syllabus lists) - and lines with the `words` they split into. Nothing else
of the dictionary is used.

## `display.json` - caption display rules

`core/listening/display.py`:
- `caption_rows`: a `caption` (clauses with `original`, `translations`
  and `links` by language; `live`; the spoken `language`), the overlay's
  `target` and `second` language and its `options` -> its `rows` (`text`,
  `kind` original / translation, `language`, `clause`, `starts_clause`,
  `links` as `[start, end, link number]` - numbered across the
  caption, each clause's after the ones before it: polyglotic-hq 340).
  A live caption's last row ends with `live_trail`.
- `numbered_links`: a clause's word links, `detail` (`key` / `most`),
  `cap`, the texts' lengths -> the linked words in the original and the
  translation, numbered.
- `first_rewritten`: old and new rows -> the first rewritten row (null:
  none).
- `following_top`: the one-way layout - captions' `height` and last `top`
  (null: arriving), the canvas, `gap`, `last_is_live`, `headroom`,
  `reanchor` -> the stack's `top`.
