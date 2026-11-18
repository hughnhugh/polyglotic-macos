# The coverage probe's sentences

One sentence per line, per caption language (`<code>.txt`): the first 100
sentences of the FLEURS test split's transcripts in that language, as
polyglotic-hq project 086 measured speech and translation on them
(`projects/086-languages-measured/results/mt/<code>-en.json`, the
`source` column; whitespace collapsed).

`tools.dictionaries.coverage` splits them with the pack's word split and
counts how many content words the pack has an entry for. A language is
offered as a basic dictionary only if that share reaches the basic tier's
floor (polyglotic-hq project 157: 90 %).

- FLEURS: Google, https://huggingface.co/datasets/google/fleurs, CC BY 4.0
  (as polyglotic-hq project 086 recorded it).
- FLEURS's sentences are FLoRes-101's (Meta AI). Its repository gives
  FLORES-200, the later set, as CC BY-SA 4.0 and states no licence for
  FLoRes-101 itself (read 2026-11-08):
  https://github.com/facebookresearch/flores
- Read text, not conversation: real captions have more names and slang,
  so they will miss more.

`en.txt` is English's, the same way (086's `en-de.json`): what
`tools.dictionaries.english_check` measures `ecdict-en.sqlite`'s English
meanings on (polyglotic-hq 447). English isn't a pack.
