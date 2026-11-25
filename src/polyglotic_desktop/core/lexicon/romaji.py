"""Dependency-free Japanese kana to modified Hepburn romanisation.

The converter accepts the reading supplied by Sudachi or JMdict.  Particle
pronunciations are opt-in because they depend on Sudachi's part of speech,
not on the spelling alone.
"""
# ruff: noqa: SIM905

from __future__ import annotations

import unicodedata

MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}
VOWELS = frozenset(MACRON)
PARTICLES = {"は": "wa", "へ": "e", "を": "o"}

# Longest match wins.  These are the modified-Hepburn exceptions; regular
# consonant + small ya/yu/yo combinations are derived below.
COMBINATIONS = {
    "しゃ": "sha",
    "しゅ": "shu",
    "しょ": "sho",
    "ちゃ": "cha",
    "ちゅ": "chu",
    "ちょ": "cho",
    "じゃ": "ja",
    "じゅ": "ju",
    "じょ": "jo",
    "うぃ": "wi",
    "うぇ": "we",
    "うぉ": "wo",
    "ゔぁ": "va",
    "ゔぃ": "vi",
    "ゔぇ": "ve",
    "ゔぉ": "vo",
    "ゔゅ": "vyu",
    "きぇ": "kye",
    "ぎぇ": "gye",
    "しぇ": "she",
    "じぇ": "je",
    "ちぇ": "che",
    "にぇ": "nye",
    "ひぇ": "hye",
    "びぇ": "bye",
    "ぴぇ": "pye",
    "みぇ": "mye",
    "りぇ": "rye",
    "てぃ": "ti",
    "でぃ": "di",
    "てゅ": "tyu",
    "でゅ": "dyu",
    "とぅ": "tu",
    "どぅ": "du",
    "つぁ": "tsa",
    "つぃ": "tsi",
    "つぇ": "tse",
    "つぉ": "tso",
    "ふぁ": "fa",
    "ふぃ": "fi",
    "ふぇ": "fe",
    "ふぉ": "fo",
    "ふゅ": "fyu",
}
MONOGRAPHS = dict(
    zip(
        "あいうえおかきくけこさしすせそたちつてとなにぬねの"
        "はひふへほまみむめもやゆよらりるれろわをん"
        "ゐゑ"
        "がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゔ",
        (
            "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to "
            "na ni nu ne no ha hi fu he ho ma mi mu me mo ya yu yo "
            "ra ri ru re ro wa o n wi we ga gi gu ge go za ji zu ze zo "
            "da ji zu de do ba bi bu be bo pa pi pu pe po vu"
        ).split(),
        strict=True,
    )
)
SMALL = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}
YOON = {"ゃ": "ya", "ゅ": "yu", "ょ": "yo"}


def romaji(kana: str, *, particle: bool = False) -> str:
    """Return ``kana`` in modified Hepburn, preserving non-kana text.

    ``particle`` applies Sudachi's particle pronunciation to an exact は, へ,
    or を token. Long *ou*, *oo*, and *uu* sounds use macrons.
    """
    text = _hiragana(unicodedata.normalize("NFKC", kana))
    # The lexicalised greeting is written with historical particle は.
    if text == "こんにちは":
        return "konnichiwa"
    if particle and text in PARTICLES:
        return PARTICLES[text]
    pieces: list[str] = []
    at = 0
    geminate = False
    while at < len(text):
        char = text[at]
        if char == "っ":
            geminate = True
            at += 1
            continue
        if char == "ー":
            _lengthen_last(pieces)
            at += 1
            continue
        pair = text[at : at + 2]
        said = COMBINATIONS.get(pair)
        if said is None and len(pair) == 2 and pair[1] in YOON:
            first = MONOGRAPHS.get(pair[0])
            if first is not None and first.endswith("i"):
                said = first[:-1] + YOON[pair[1]]
        if said is not None:
            at += 2
        else:
            said = MONOGRAPHS.get(char, SMALL.get(char, char))
            at += 1
        if said == "n" and at < len(text):
            following = _next_sound(text, at)
            if following[:1] in VOWELS or following.startswith("y"):
                said = "n'"
        if geminate and said:
            said = _geminated(said)
            geminate = False
        pieces.append(said)
    return _long_vowels("".join(pieces))


def _hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def _next_sound(text: str, at: int) -> str:
    pair = text[at : at + 2]
    return COMBINATIONS.get(pair, MONOGRAPHS.get(text[at], ""))


def _geminated(said: str) -> str:
    if said.startswith("ch"):
        return "t" + said
    if said.startswith("sh"):
        return "s" + said
    if said.startswith("ts"):
        return "t" + said
    return said[0] + said


def _lengthen_last(pieces: list[str]) -> None:
    if not pieces:
        return
    for index in range(len(pieces[-1]) - 1, -1, -1):
        if pieces[-1][index] in VOWELS:
            vowel = pieces[-1][index]
            pieces[-1] = pieces[-1][:index] + MACRON[vowel] + pieces[-1][index + 1 :]
            return


def _long_vowels(text: str) -> str:
    # Hepburn treats おう and おお alike; うう is likewise requested here.
    for plain, long in (("ou", "ō"), ("oo", "ō"), ("uu", "ū")):
        text = text.replace(plain, long)
    return text
