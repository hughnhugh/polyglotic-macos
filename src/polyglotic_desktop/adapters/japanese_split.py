"""Japanese words, by Sudachi (SudachiPy with SudachiDict's small
dictionary): the `WordSplit` port for the Japanese dictionary pack.

Sudachi splits a line into morphemes, each with its dictionary form
("食べ" -> 食べる), its normalised form (いる -> 居る, which tells "to be"
from 要る, "to need") and part of speech. Split mode C gives the longest
units the small dictionary knows. Particles, auxiliaries and symbols are
words too (a hover still finds は or ます) but not *content* words.

Sudachi (Apache-2.0) loads its dictionary in about 0.1 s; it's imported
only when the Japanese pack is used (polyglotic-hq project 164 measured
its install size).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from polyglotic_desktop.ports.word_split import SplitWord

# Sudachi's first part-of-speech level for words with meaning of their own
# (the set polyglotic-hq project 157's coverage probe counted)
CONTENT = frozenset({"名詞", "動詞", "形容詞", "副詞", "形状詞", "連体詞", "感動詞"})
NOT_WORDS = frozenset({"補助記号", "空白"})  # punctuation, spaces


class JapaneseSplit:
    """Japanese words by Sudachi. Loads its dictionary when first asked."""

    def __init__(self) -> None:
        self._tokenizer: Any = None

    def _tokenize(self, text: str) -> Any:
        if self._tokenizer is None:
            from sudachipy import Dictionary, SplitMode

            self._mode = SplitMode.C
            self._tokenizer = Dictionary(dict="small").tokenizer(mode=self._mode)
        return self._tokenizer.tokenize(text, self._mode)

    def words(self, text: str) -> Sequence[SplitWord]:
        out = []
        for m in self._tokenize(text):
            pos = m.part_of_speech()[0]
            if pos in NOT_WORDS or m.begin() >= m.end():
                continue
            surface = m.surface()
            # the normalised form first: it tells いる "to be" (居る) from
            # いる "to need" (要る), and する (為る) from its namesakes
            lemmas = tuple(
                f
                for f in dict.fromkeys((m.normalized_form(), m.dictionary_form()))
                if f and f != surface
            )
            out.append(SplitWord(m.begin(), m.end(), lemmas, content=pos in CONTENT))
        return out
