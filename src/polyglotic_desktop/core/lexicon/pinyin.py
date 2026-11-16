"""Pinyin: CC-CEDICT's numbered pinyin ("dian4 nao3") with tone marks ("diàn nǎo")."""

import re

_MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
_SYLLABLE = re.compile(r"([A-Za-z:]+)([1-5])")


def _mark_syllable(syllable: str) -> str:
    """ "nao3" -> "nǎo", "lu:4" -> "lǜ", "r5" -> "r". The mark goes on a or e
    if there is one, on the o of "ou", and otherwise on the last vowel."""
    match = _SYLLABLE.fullmatch(syllable)
    if not match:
        return syllable.replace("u:", "ü").replace("U:", "Ü")
    letters = match.group(1).replace("u:", "ü").replace("U:", "Ü")
    tone = int(match.group(2))
    if tone == 5:
        return letters
    lower = letters.lower()
    if "a" in lower:
        at = lower.index("a")
    elif "e" in lower:
        at = lower.index("e")
    elif "ou" in lower:
        at = lower.index("o")
    else:
        at = max((i for i, c in enumerate(lower) if c in "iouü"), default=-1)
        if at < 0:
            return letters  # "m2", "ng2" - no vowel to mark
    marked = _MARKS[lower[at]][tone - 1]
    return (
        letters[:at]
        + (marked.upper() if letters[at].isupper() else marked)
        + letters[at + 1 :]
    )


def mark_pinyin(numbered: str) -> str:
    """CC-CEDICT's numbered pinyin ("dian4 nao3") with tone marks ("diàn nǎo")."""
    return " ".join(_mark_syllable(s) for s in numbered.split())
