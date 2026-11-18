"""Korean in Revised Romanization: the reading line over Korean, each word
(a run of Hangul) romanized as it is said (polyglotic-hq 370 and 511).

Revised Romanization (the official system, korean.go.kr) writes the sound
changes at each syllable's join - so 한국어 is hangugeo, 국물 gungmul, 신라
Silla, 좋다 jota - but not tensing. These are 370's rules: liaison, ㅎ
aspiration, palatalization, nasalization, ㄹ assimilation and
liquidization, with no dictionary. 370 measured them on 1,542 words of
FLEURS's Korean: 99.6 % agreed with g2pk's pronunciation (Apache-2.0)
romanized the same way; korean-romanizer, which lacks the sound changes,
had 89.5 % and is GPL - kept out. What they miss: ㄴ insertion (솜이불
somnibul) and a noun that keeps its h (북한 Bukhan, not bukan), which need
a word list; and nothing across a space.

Holds caption text's sound: never log it.
"""

from __future__ import annotations

import re

from polyglotic_desktop.core.lexicon.readings import Reading

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ("", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
_R_CHO = dict(
    zip(
        _CHO,
        "g kk n d tt r m b pp s ss _ j jj ch k t p h".replace("_", "").split(" "),
        strict=True,
    )
)
_R_JUNG = dict(
    zip(
        _JUNG,
        [
            "a",
            "ae",
            "ya",
            "yae",
            "eo",
            "e",
            "yeo",
            "ye",
            "o",
            "wa",
            "wae",
            "oe",
            "yo",
            "u",
            "wo",
            "we",
            "wi",
            "yu",
            "eu",
            "ui",
            "i",
        ],
        strict=True,
    )
)
_R_JONG = {
    "": "",
    "ㄱ": "k",
    "ㄴ": "n",
    "ㄷ": "t",
    "ㄹ": "l",
    "ㅁ": "m",
    "ㅂ": "p",
    "ㅇ": "ng",
}
_TENSE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
"""A tense consonant RR writes plain, where the spelling has it plain."""
_NEUTRAL = {
    "ㄲ": "ㄱ", "ㅋ": "ㄱ", "ㄳ": "ㄱ", "ㄺ": "ㄱ", "ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ",
    "ㅊ": "ㄷ", "ㅌ": "ㄷ", "ㅎ": "ㄷ", "ㅍ": "ㅂ", "ㅄ": "ㅂ", "ㄿ": "ㅂ", "ㄵ": "ㄴ",
    "ㄶ": "ㄴ", "ㄻ": "ㅁ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㅀ": "ㄹ",
}  # fmt: skip
"""A final consonant as it sounds before another consonant or a pause."""
_SPLIT = {
    "ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"),
    "ㄼ": ("ㄹ", "ㅂ"), "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"),
    "ㅄ": ("ㅂ", "ㅅ"), "ㄶ": ("ㄴ", "ㅎ"), "ㅀ": ("ㄹ", "ㅎ"),
}  # fmt: skip
"""A double final's two consonants."""
_ASPIRATED = {"ㄱ": "ㅋ", "ㄷ": "ㅌ", "ㅂ": "ㅍ", "ㅈ": "ㅊ"}
_NASAL = {"ㄱ": "ㅇ", "ㄷ": "ㄴ", "ㅂ": "ㅁ"}
HANGUL = re.compile("[가-힣]+")
"""A word's run of Hangul syllables."""

Syllable = list[str]
"""A syllable's initial, vowel and final (jamo; "" for none)."""


def _split(word: str) -> list[Syllable]:
    out = []
    for char in word:
        n = ord(char) - 0xAC00
        out.append([_CHO[n // 588], _JUNG[(n % 588) // 28], _JONG[n % 28]])
    return out


def _pronounced(word: str) -> list[Syllable]:
    """`word`'s syllables as said: each join's sound change (370's rules)."""
    s = _split(word)
    for i in range(len(s) - 1):
        f, c, v = s[i][2], s[i + 1][0], s[i + 1][1]
        if c == "ㅇ":  # a vowel next: the final moves over (liaison)
            if f == "ㅎ":
                s[i][2] = ""
            elif f in ("ㄶ", "ㅀ"):
                s[i][2], s[i + 1][0] = "", _SPLIT[f][0]
            elif f in _SPLIT:
                s[i][2], s[i + 1][0] = _SPLIT[f]
            elif f in ("ㄷ", "ㅌ") and v == "ㅣ":  # palatalization: 같이 gachi
                s[i][2], s[i + 1][0] = "", "ㅈ" if f == "ㄷ" else "ㅊ"
            elif f and f != "ㅇ":
                s[i][2], s[i + 1][0] = "", f
            continue
        if c == "ㅎ" and f:  # aspiration: 놓고 noko (a noun keeps h: not known)
            first, last = _SPLIT.get(f, ("", f))
            n = (
                "ㄷ"
                if last == "ㅅ"
                else _NEUTRAL.get(last, last)
                if last != "ㅈ"
                else "ㅈ"
            )
            if n in _ASPIRATED:
                s[i][2] = first
                s[i + 1][0] = "ㅊ" if (n == "ㄷ" and v == "ㅣ") else _ASPIRATED[n]
            continue
        if f in ("ㅎ", "ㄶ", "ㅀ"):  # ㅎ before a consonant: 좋다 jota
            rest = {"ㅎ": "", "ㄶ": "ㄴ", "ㅀ": "ㄹ"}[f]
            if c in _ASPIRATED:
                s[i][2], s[i + 1][0] = rest, _ASPIRATED[c]
                continue
            if c == "ㄴ":
                s[i][2] = rest or "ㄴ"
                if rest == "ㄹ":
                    s[i + 1][0] = "ㄹ"
                continue
            s[i][2] = f = rest
        if f in _SPLIT:
            f = "ㄹ" if f == "ㄺ" and c == "ㄱ" else _NEUTRAL[f]
        f = _NEUTRAL.get(f, f)
        s[i][2] = f
        if c == "ㄹ":  # ㄹ after a consonant: 국립 gungnip, 신라 silla
            if f in ("ㅁ", "ㅇ"):
                s[i + 1][0] = "ㄴ"
            elif f in _NASAL:
                s[i + 1][0], s[i][2] = "ㄴ", _NASAL[f]
            elif f == "ㄴ":
                s[i][2] = "ㄹ"
        elif c in ("ㄴ", "ㅁ") and f in _NASAL:  # nasalization: 국물 gungmul
            s[i][2] = _NASAL[f]
        elif f == "ㄹ" and c == "ㄴ":
            s[i + 1][0] = "ㄹ"
    return s


def romanized(word: str) -> str:
    """A run of Hangul in Revised Romanization, its sound changes written
    (한국어: hangugeo); tensing isn't (RR doesn't write it)."""
    said, spelt = _pronounced(word), _split(word)
    out = []
    for i, (c, _, f) in enumerate(said):
        written = spelt[i][0]
        if c in _TENSE and written == _TENSE[c]:
            c = written
        elif c in _TENSE and written == "ㅇ" and i:
            moved = _SPLIT.get(spelt[i - 1][2], ("", spelt[i - 1][2]))[1]
            if moved == _TENSE[c]:
                c = moved
        initial = "l" if c == "ㄹ" and i and said[i - 1][2] == "ㄹ" else _R_CHO[c]
        out.append(initial + _R_JUNG[spelt[i][1]] + _R_JONG.get(_NEUTRAL.get(f, f), ""))
    return "".join(out)


class KoreanReader:
    """Revised Romanization over Korean text: no dictionary needed."""

    ready = True

    def readings(self, text: str) -> list[Reading]:
        """Each run of Hangul in `text`, romanized over it."""
        return [
            Reading(m.start(), m.end(), romanized(m.group()))
            for m in HANGUL.finditer(text)
        ]
