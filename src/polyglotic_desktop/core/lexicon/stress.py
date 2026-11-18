"""Stress marks over Russian: the reading line's acute over each word's
stressed vowel (молоко́), from the Russian pack (polyglotic-hq 370 and
511).

Russian text doesn't mark its stress, and the stress moves as a word
inflects (рука́, ру́ку), so learners' books mark it. The Russian pack has
it already, from Wiktionary: each inflected form's own stressed spelling
(its form readings: "руку" ру́ку) and each headword's (its entry's
reading: молоко́). A word's mark goes over its stressed vowel - the vowel
the acute follows, or the ё a reading writes where the caption writes е
(еще: ещё). None where it isn't needed or isn't known:
- a word of one vowel, or one written with ё, which is always stressed;
- a word the pack has stressed two ways - a form two words share (ру́ки,
  "hands", and руки́, "of the hand") or a word said either way: about 7 %
  of Russian words (370). The card shows both; above running text one
  would often be wrong;
- a word the pack hasn't got.

Holds caption text's sound: never log it.
"""

from __future__ import annotations

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.readings import Reading

ACUTE = "́"
"""The combining acute: main stress, as Wiktionary marks it."""
GRAVE = "̀"
"""The combining grave: secondary stress, not shown."""
MARK = "\u00b4"
"""What is drawn over the stressed vowel: the spacing acute, in the
text's own size, where an accent on the letter would be (`Reading.mark`)."""
VOWELS = frozenset("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
STRESSES_KEPT = 20000
"""How many words' stresses a reader keeps: a caption's words come again
and again."""


def stressed_at(word: str, reading: str) -> int | None:
    """Which of `word`'s letters `reading` (its stressed spelling) says is
    stressed: the vowel before the acute, or a ё the word writes е - None
    if the reading isn't `word`'s spelling, or marks no stress or two
    (тво́ро́г: said either way)."""
    if reading.count(ACUTE) > 1:
        return None
    letters: list[str] = []
    at: int | None = None
    for char in reading:
        if char == ACUTE:
            if letters:
                at = len(letters) - 1
        elif char != GRAVE:
            letters.append(char)
    plain = "".join(letters)
    if len(plain) != len(word) or _e(plain.lower()) != _e(word.lower()):
        return None
    if at is None and "ё" in plain.lower():
        at = plain.lower().index("ё")
    return at


def _e(text: str) -> str:
    return text.replace("ё", "е")


class StressReader:
    """The stress marks of Russian text, by the Russian pack."""

    def __init__(self, dictionary: BasicDictionary) -> None:
        self.dictionary = dictionary
        self._stressed: dict[str, int | None] = {}

    @property
    def ready(self) -> bool:
        """Whether its word split can answer now (`BasicDictionary.ready`)."""
        return self.dictionary.ready

    def readings(self, text: str) -> list[Reading]:
        """A mark over the stressed vowel of each word of `text` the pack
        stresses one way (`stressed`)."""
        found = []
        for start, end in self.dictionary.words(text):
            at = self.stressed(text[start:end])
            if at is not None:
                found.append(Reading(start + at, start + at + 1, MARK, mark=True))
        return found

    def stressed(self, word: str) -> int | None:
        """Which letter of `word` is stressed, where it needs a mark and the
        pack says one way only - None otherwise."""
        if word in self._stressed:
            return self._stressed[word]
        at = None
        if sum(c in VOWELS for c in word) > 1 and "ё" not in word.lower():
            places = {stressed_at(word, said) for said in self._readings(word)}
            places.discard(None)
            if len(places) == 1:
                at = places.pop()
        if len(self._stressed) >= STRESSES_KEPT:
            self._stressed.clear()
        self._stressed[word] = at
        return at

    def _readings(self, word: str) -> list[str]:
        """Every stressed spelling the pack has of `word` itself: its form
        readings, else its headwords' readings."""
        forms = self.dictionary.form_reading(word)
        if forms:
            return [said.strip() for said in forms.split(",")]
        return [
            entry.reading
            for entry in self.dictionary.lookup(word)
            if stressed_at(word, entry.reading) is not None
        ]
