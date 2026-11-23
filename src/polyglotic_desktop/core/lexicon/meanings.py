"""Meanings as a lookup shows them: definitions apart from measure words,
and a short meaning for saving a word.

From the proof of concept's `ui/lookup.py` (`_definitions`, `meaning_of`),
moved out of Qt.
"""

import re
from collections.abc import Sequence

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, has_han
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry, DictionarySense
from polyglotic_desktop.core.lexicon.pinyin import mark_pinyin

# CC-CEDICT's measure words: "CL:個|个[ge4],臺|台[tai2]"
_MEASURE_WORD = re.compile(r"(?:([^|\[,]+)\|)?([^|\[,]+)\[([^\]]+)\]")


def definitions(entry: DictionaryEntry) -> tuple[list[str], list[str]]:
    senses, measure_words = display_senses(entry)
    return [sense.gloss for sense in senses], measure_words


def display_senses(entry: DictionaryEntry) -> tuple[list[DictionarySense], list[str]]:
    """(definitions, measure words): CC-CEDICT's "CL:個|个[ge4]" meanings
    pulled out as "个 gè" (simplified, with tone marks)."""
    found: list[DictionarySense] = []
    measure_words: list[str] = []
    for sense in entry.senses:
        meaning = sense.gloss
        if meaning.startswith("CL:"):
            measure_words += [
                f"{simplified} {mark_pinyin(pinyin)}"
                for _, simplified, pinyin in _MEASURE_WORD.findall(meaning[3:])
            ]
        else:
            found.append(sense)
    return found, measure_words


def short_meaning(entries: Sequence[DictionaryEntry], limit: int = 3) -> str:
    """A short meaning: the first entry's (everyday reading's) first few
    definitions - what a saved word keeps, and the Anki card shows."""
    return "; ".join(definitions(entries[0])[0][:limit]) if entries else ""


def meaning_of(dictionary: ChineseDictionary, word: str, limit: int = 3) -> str:
    """A short meaning for any Chinese text: its own entry's, or for a
    phrase the dictionary hasn't got as a whole, its words' first meanings
    joined ("打 + 游戏"-style: "to hit + game"); "" if none."""
    entries = dictionary.lookup(word)
    if entries:
        return short_meaning(entries, limit)
    parts = [
        word[start:end]
        for start, end in dictionary.split(word)
        if has_han(word[start:end])
    ]
    if len(parts) < 2:
        return ""
    return " + ".join(meaning_of(dictionary, part, 1) or "?" for part in parts)
