"""Hindi in Latin letters: the reading line over Hindi, each word as
Wiktionary romanizes it (kitāb, hindī), by rule (polyglotic-hq 370 and
511).

Devanagari is read letter by letter, but a consonant's own a (the schwa)
isn't always said: कमरा is kamrā, not kamarā. The rule (370's): a word's
last consonant drops its a, and so does a consonant between a vowel and
a consonant that has one (कमरा: ka-m-rā) - but y, r and v keep it after
a cluster (सामान्य sāmānya, क्षेत्र kṣetra), as a last y does after i
(भारतीय bhārtīya). Then Wiktionary's letters:
long vowels with a macron (ā ī ū), the retroflexes with a dot (ṭ ḍ ṇ ṣ ṛ),
ś for श, c for च, ŕ for ृ, a nasal vowel with a tilde (हैं: haĩ), and ं
as the nasal its next consonant takes (हिंदी hindī, रंग raṅg, संबंध
sambandh). 370 measured the rule against Wiktionary's own romanization
on FLEURS's Hindi without the marks: 96.1 % of the words Wiktionary has;
with 511's letters and rules, its report. What it misses: compounds
(लोकप्रिय lokpriya) and a word written without its nukta (खास, xās).

Holds caption text's sound: never log it.
"""

from __future__ import annotations

import re

from polyglotic_desktop.core.lexicon.readings import Reading

_CONSONANTS = dict(
    zip(
        "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
        [
            "k",
            "kh",
            "g",
            "gh",
            "ṅ",
            "c",
            "ch",
            "j",
            "jh",
            "ñ",
            "ṭ",
            "ṭh",
            "ḍ",
            "ḍh",
            "ṇ",
            "t",
            "th",
            "d",
            "dh",
            "n",
            "p",
            "ph",
            "b",
            "bh",
            "m",
            "y",
            "r",
            "l",
            "v",
            "ś",
            "ṣ",
            "s",
            "h",
        ],
        strict=True,
    )
)
_NUKTA = {
    "क": "q",
    "ख": "x",
    "ग": "ġ",
    "ज": "z",
    "झ": "ž",
    "ड": "ṛ",
    "ढ": "ṛh",
    "फ": "f",
}
_VOWELS = dict(
    zip(
        "अआइईउऊऋएऐओऔऍऑ",
        ["a", "ā", "i", "ī", "u", "ū", "ŕ", "e", "ai", "o", "au", "ê", "ŏ"],
        strict=True,
    )
)
_SIGNS = dict(
    zip(
        "ािीुूृेैोौॅॉ",
        ["ā", "i", "ī", "u", "ū", "ŕ", "e", "ai", "o", "au", "ê", "ŏ"],
        strict=True,
    )
)
_VIRAMA, _ANUSVARA, _CANDRABINDU, _VISARGA, _NUKTA_SIGN = "्", "ं", "ँ", "ः", "़"
_TILDE = "̃"
_DOUBLE_TILDE = "͠"
"""Over both letters of ai and au: हैं is ha͠i."""
_NASALS = (("kgṅh", "ṅ"), ("cjñ", "ñ"), ("ṭḍṇ", "ṇ"), ("pbm", "m"), ("y", _TILDE))
"""ं before a consonant: the nasal of its place (सिंह siṅh, करेंगे
kareṅge), n before the rest - a nasal vowel before y (संयंत्र sãyantra)."""
_NASAL_VOWELS = ("o", "au")
"""After these ं is the vowel's nasal, before a consonant too (क्योंकि
kyõki, उन्होंने unhõne)."""
_KEEPS_A_AFTER_A_CLUSTER = ("y", "r", "v")
"""A last consonant that keeps its a after a cluster: सामान्य sāmānya,
क्षेत्र kṣetra - but धर्म dharm, युद्ध yuddh."""
_KEEPS_A = ("i", "ī")
"""A last य after these keeps its a: भारतीय bhārtīya, प्रिय priya."""
_PRECOMPOSED = str.maketrans(
    {chr(0x0958 + n): base + "़" for n, base in enumerate("कखगजडढफय")}
)
"""क़ and its kind written as one character: as the letter and its nukta."""
WORD = re.compile("[ऀ-ॿ]+")
"""A run of Devanagari: a word."""


def _units(word: str) -> list[list[str]]:
    """Each letter as [kind, consonant, vowel]: C (a consonant, its vowel
    "a" unless a sign or virama says), V (a vowel), N (ं), M (ँ), H (ः)."""
    out, i = [], 0
    while i < len(word):
        char = word[i]
        if char in _CONSONANTS:
            sound = _CONSONANTS[char]
            if word[i + 1 : i + 2] == _NUKTA_SIGN:
                sound = _NUKTA.get(char, sound)
                i += 1
            vowel = "a"
            if word[i + 1 : i + 2] and word[i + 1] in _SIGNS:
                vowel = _SIGNS[word[i + 1]]
                i += 1
            elif word[i + 1 : i + 2] == _VIRAMA:
                vowel = ""
                i += 1
            out.append(["C", sound, vowel, "a" if vowel == "a" else ""])
        elif char in _VOWELS:
            out.append(["V", "", _VOWELS[char], ""])
        elif char == _ANUSVARA:
            out.append(["N", "", "", ""])
        elif char == _CANDRABINDU:
            out.append(["M", "", "", ""])
        elif char == _VISARGA:
            out.append(["H", "h", "", ""])
        i += 1
    return out


def romanized(word: str) -> str:
    """A Devanagari word in Wiktionary's Latin letters, its unsaid a's left
    out (कमरा: kamrā)."""
    u = _units(word.translate(_PRECOMPOSED))
    if len(u) > 1 and u[-1][0] == "C" and u[-1][3]:
        cluster = u[-2][0] == "C" and not u[-2][2]
        cluster = cluster and u[-1][1] in _KEEPS_A_AFTER_A_CLUSTER
        if not cluster and not (u[-1][1] == "y" and u[-2][2] in _KEEPS_A):
            u[-1][2] = ""  # the last consonant's own a
    for k in range(len(u) - 2, 0, -1):
        if (
            u[k][0] == "C"
            and u[k][3]
            and u[k - 1][2]
            and u[k + 1][0] == "C"
            and u[k + 1][2]
        ):
            u[k][2] = ""  # between a vowel and a consonant with one
    out = ""
    for k, (kind, sound, vowel, _) in enumerate(u):
        if kind in ("N", "M"):
            after = u[k + 1][1] if k + 1 < len(u) and u[k + 1][0] == "C" else ""
            before = u[k - 1][2] if k else ""
            if kind == "M" or not after or before in _NASAL_VOWELS:
                out = _nasal(out, before)
            else:
                out += next((n for places, n in _NASALS if after[0] in places), "n")
        else:
            out += sound + vowel
    return out


def _nasal(out: str, vowel: str) -> str:
    """`out` with its last vowel said through the nose: a tilde over it,
    over both letters of ai and au."""
    if len(vowel) == 2 and out.endswith(vowel):
        return out[:-1] + _DOUBLE_TILDE + out[-1]
    return out + _TILDE


class HindiReader:
    """Hindi's Latin letters over Hindi text: no dictionary needed."""

    ready = True

    def readings(self, text: str) -> list[Reading]:
        """Each Devanagari word of `text`, romanized over it."""
        return [
            Reading(m.start(), m.end(), romanized(m.group()))
            for m in WORD.finditer(text)
        ]
