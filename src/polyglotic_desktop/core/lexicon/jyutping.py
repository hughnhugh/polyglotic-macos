"""Jyutping over Cantonese: the reading line's syllables, from the Cantonese
pack (polyglotic-hq 371 and 450; decisions 0155 and 0160).

The pack writes each entry's Jyutping with its tone raised (hai⁶) and puts
a word's everyday reading first (rime-cantonese's), so a caption is read
as Chinese's pinyin is (`chinese.ChineseDictionary.readings`): each word of
the pack's word split as its first entry with a syllable for each
character reads it - 銀行 ngan⁴ hong⁴, 行路 haang⁴ lou⁶ - and a word the
pack hasn't got whole, character by character. 371 measured the pack's
readings over its own split against HKCanCor's hand transcription: 96.0 %
of characters outside sentence particles, whose tones vary as they are
said.

Holds caption text's sound: never log it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import has_han, is_han
from polyglotic_desktop.core.lexicon.readings import Reading

READINGS_KEPT = 20000
"""How many words' syllables a reader keeps: a caption's words come again
and again."""
_SYLLABLE = re.compile(r"^[a-z]+[¹²³⁴⁵⁶]$")
"""One Jyutping syllable, its tone raised."""


def syllables_of(reading: str) -> list[str] | None:
    """`reading`'s syllables, if it is all Jyutping (not CC-Canto's "AA
    ji¹", English letters in a word) - else None."""
    found = reading.split()
    return found if found and all(_SYLLABLE.match(s) for s in found) else None


class JyutpingReader:
    """The Jyutping of Cantonese text, by a Cantonese pack (`dictionary`)."""

    def __init__(self, dictionary: BasicDictionary) -> None:
        self.dictionary = dictionary
        self._read: dict[str, list[str] | None] = {}

    @property
    def ready(self) -> bool:
        """Whether its word split can answer now (`BasicDictionary.ready`)."""
        return self.dictionary.ready

    def readings(self, text: str) -> list[Reading]:
        """A syllable over each Chinese character of `text` the pack can
        read: each word as its everyday entry reads it, else character by
        character. Nothing over what isn't a Chinese character."""
        found: list[Reading] = []
        for start, end in self.dictionary.words(text):
            word = text[start:end]
            if not has_han(word):
                continue
            syllables: Sequence[str] | None = self._syllables(word)
            if syllables is None:
                syllables = [
                    (self._syllables(ch) or [""])[0] if is_han(ch) else ""
                    for ch in word
                ]
            last = max((n for n, s in enumerate(syllables) if s), default=-1)
            for n, syllable in enumerate(syllables):
                if syllable:
                    found.append(Reading(start + n, start + n + 1, syllable, n == last))
        return found

    def _syllables(self, word: str) -> list[str] | None:
        """`word`'s everyday Jyutping, a syllable a character: its first
        entry's that has one for each - None if none has."""
        if word in self._read:
            return self._read[word]
        syllables = None
        for entry in self.dictionary.lookup(word):
            found = syllables_of(entry.reading)
            if found is not None and len(found) == len(word):
                syllables = found
                break
        if len(self._read) >= READINGS_KEPT:
            self._read.clear()
        self._read[word] = syllables
        return syllables
