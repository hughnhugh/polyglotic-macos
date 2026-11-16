"""Vietnamese's own rules for its pack (polyglotic-hq 325; decision 0121).

- **Which words:** Wiktionary lists Vietnamese words in two scripts: the
  Latin one captions are written in (chữ Quốc ngữ) and Hán Nôm's
  characters. Only the first are a caption's (`is_latin`).
- **Counting words:** every published frequency list counts Vietnamese
  syllables, not words - wordfreq's and OpenSubtitles' alike have "học"
  and "sinh", never "học sinh" (pupil) - and estimating a word from its
  syllables put "là là" and "có là" in the top 30. So the pack counts its
  own words (`counted_words`): lines of subtitles, cut into the
  dictionary's words by the app's own word split
  (`core.lexicon.vietnamese.cut`).
"""

from __future__ import annotations

import gzip
import unicodedata
from collections import Counter
from collections.abc import Container
from pathlib import Path

from polyglotic_desktop.core.lexicon.vietnamese import cut, key
from tools.dictionaries.frequency import Frequencies


def is_latin(word: str) -> bool:
    """Whether `word` is written in the Latin script, as captions are: it
    has a letter, and every letter is Latin ("học sinh", "ki-lô-mét"; not
    "學生")."""
    letters = [c for c in word if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)


def counted_words(corpus: Path, words: Container[str]) -> Frequencies:
    """Each word's share of the words in `corpus` (gzipped text, a line of
    subtitles per line), the lines cut by the word split over `words`
    (`key`s): a dictionary word, or a syllable it hasn't got. Words with no
    letter (numbers) aren't counted."""
    counts: Counter[str] = Counter()
    with gzip.open(corpus, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = unicodedata.normalize("NFC", line)
            for start, end in cut(line, words, {}):
                counts[key(line[start:end])] += 1
    total = sum(counts.values()) or 1
    return Frequencies(
        ((word, n / total) for word, n in counts.items()), hyphenated=True
    )
