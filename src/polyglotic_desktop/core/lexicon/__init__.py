"""Lexicon: dictionary entries for instant lookups, identified by entry IDs.

Owns dictionary entries (headword, readings such as pinyin and IPA,
meanings, levels such as HSK, frequency rank, the name flag), the word
split of Chinese text into dictionary words, everyday readings, parts,
reverse lookup, and which entry an inflected English word counts for.
Entries are shared with Learning and the server by entry ID only.

- `entries`: `DictionaryEntry`, and the level schemes a learner picks from.
- `chinese`: `ChineseDictionary` (CC-CEDICT) - lookups, word split, parts,
  reverse lookup.
- `english`: `EnglishDictionary` (ECDICT) - lookups, inflected forms.
- `pinyin`: tone marks.
- `basic`: `BasicDictionary`, a basic dictionary pack's lookups.
- `vietnamese`: Vietnamese's word split, by a pack's own words of one or
  more syllables (decision 0121).
- `thai`: Thai's word split, by a pack's own words in a line written
  without spaces (decision 0173).
- `meanings`: definitions apart from measure words; short meanings.

`words_in` (both dictionaries) gives Learning the words in a line as
`core.shared.WordInLine`s, with the facts it needs about each entry.

The dictionary files are read through the `DictionaryFile` port
(`ports.dictionary`, decision 0008); `main` hands one in.
"""
