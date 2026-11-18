"""Japanese words, by Sudachi (SudachiPy with SudachiDict's small
dictionary): the `WordSplit` port for the Japanese dictionary pack.

Sudachi splits a line into morphemes, each with its dictionary form
("食べ" -> 食べる), its normalised form (いる -> 居る, which tells "to be"
from 要る, "to need") and part of speech. Split mode C gives the longest
units the small dictionary knows. Particles, auxiliaries and symbols are
words too (a hover still finds は or ます) but not *content* words.

Each word carries Sudachi's reading of it in its line, in katakana
(`SplitWord.kana`), for furigana (`core.lexicon.furigana`; polyglotic-hq
370 and 511) - with the small dictionary's known misreadings put right
(`READ_AS`, `AFTER_A_NAME`).

Sudachi (Apache-2.0) loads its dictionary in about 0.1 s; it's imported
only when the Japanese pack is used (polyglotic-hq project 164 measured
its install size).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from polyglotic_desktop.ports.word_split import SplitWord

# Sudachi's first part-of-speech level for words with meaning of their own
# (the set polyglotic-hq project 157's coverage probe counted)
CONTENT = frozenset({"名詞", "動詞", "形容詞", "副詞", "形状詞", "連体詞", "感動詞"})
NOT_WORDS = frozenset({"補助記号", "空白"})  # punctuation, spaces

READ_AS = {
    ("日本", "ニッポン"): "ニホン",
    ("私", "ワタクシ"): "ワタシ",
    ("明日", "アス"): "アシタ",
    ("言う", "ユウ"): "イウ",
}
"""Sudachi small's reading of a word, where everyday speech reads it
otherwise: 日本 is にほん far more often than にっぽん, 私 わたし, not the
formal わたくし, and 明日 あした (polyglotic-hq 370's and 511's checks) -
or where furigana writes what is spelt, not what is said: 言う いう."""
AFTER_A_NAME = {"人": "ジン", "川": "ガワ"}
"""A suffix read so after a place's or people's name (a proper noun, a
word in katakana, or 外国): Sudachi small reads 日本人 and アラブ人 with
にん and アマゾン川 with かわ - 8 of its 24 misses on 370's sentences.
After a common noun it keeps its own reading (管理人 にん). And 日 after
a day's name is び: Sudachi small reads 月曜日 げつようひ."""
_KATAKANA = re.compile(r"[ァ-ヺー・]+")


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
        before: Any = None  # the morpheme before, for AFTER_A_NAME
        for m in self._tokenize(text):
            pos = m.part_of_speech()[0]
            if pos in NOT_WORDS or m.begin() >= m.end():
                before = m
                continue
            surface = m.surface()
            # the normalised form first: it tells いる "to be" (居る) from
            # いる "to need" (要る), and する (為る) from its namesakes
            lemmas = tuple(
                f
                for f in dict.fromkeys((m.normalized_form(), m.dictionary_form()))
                if f and f != surface
            )
            kana = _kana(surface, m.reading_form(), before)
            out.append(
                SplitWord(m.begin(), m.end(), lemmas, content=pos in CONTENT, kana=kana)
            )
            before = m
        return out


def _kana(surface: str, reading: str, before: Any) -> str:
    """How a morpheme is read in its line: Sudachi's reading, put right
    where `READ_AS` or `AFTER_A_NAME` says, or a day's 日 - "" for a word it doesn't
    know (its reading isn't kana)."""
    if surface in AFTER_A_NAME and before is not None and _a_name(before):
        return AFTER_A_NAME[surface]
    if surface == "日" and before is not None and before.surface().endswith("曜"):
        return "ビ"
    reading = READ_AS.get((surface, reading), reading)
    return reading if _KATAKANA.fullmatch(reading) else ""


def _a_name(morpheme: Any) -> bool:
    """Whether a morpheme names a place or a people: a proper noun, a word
    in katakana, or 外国 (foreign)."""
    surface = morpheme.surface()
    return (
        morpheme.part_of_speech()[1] == "固有名詞"
        or bool(_KATAKANA.fullmatch(surface))
        or surface == "外国"
    )
