"""Building the dictionary files the app ships, from pinned sources.

- `entry_ids`: stable entry IDs and the registry that carries them across
  dictionary updates (decision 0007).
- `sources`: each source pinned to a version and checksum; fetching them.
- `cedict`, `ecdict`: reading CC-CEDICT's text and ECDICT's CSV.
- `oewn`, `english_meanings`, `english_core.txt`: an English word's
  meanings in English for `ecdict-en.sqlite` - Open English WordNet's,
  ordered by UD English-EWT's counts, and our own (decision 0211);
  `english_check` measures them on FLEURS and wordfreq's commonest.
- `english_pairs`: English's meanings in each learner's language, as
  ECDICT's meanings files (`ecdict-<language>.meanings`, decision 0234) -
  Wiktionary's translation tables and each language's own Wiktionary.
- `wordfreq_ranks`: frequency ranks from wordfreq's data.
- `frequency`: a pack's frequency lists - wordfreq's, or counts from
  subtitles - and averaging them (decision 0120).
- `kaikki`, `jmdict`: reading Wiktionary as kaikki.org extracts it, and
  JMdict as jmdict-simplified's JSON.
- `spanish`: Spanish's own rules - pronominal verbs and attached pronouns.
- `russian`: Russian's own rules - stress marks, ё, which listed forms are
  inflections, participles declined.
- `packs`: `python -m tools.dictionaries.packs` writes the basic packs
  (Spanish, Russian, Japanese, Vietnamese), not shipped yet (decision 0035).
- `vietnamese`: Vietnamese's own rules - which of Wiktionary's words are
  a caption's, and its words counted in subtitles (decision 0121).
- `rank_check`: a built pack's top 1,000 words checked for junk - affixes,
  numbers, too many names, another alphabet's words, syllables for words
  (decision 0162).
- `coverage`: the probe a basic pack must pass - the share of its
  language's FLEURS sentences' words it finds (`probe/`) - and the share
  of running words it finds, by wordfreq's frequencies.
- `build`: `python -m tools.dictionaries.build` writes the dictionary files
  and their credits (decision 0009).
- `update_ids`: run when a source's pinned version changes, to carry entry
  IDs from the old release to the new one.
"""
