"""Zhuyin (bopomofo, 注音): a pinyin syllable as Taiwan's readers write it
(polyglotic-hq 395: "Readings above Chinese: Pinyin / Zhuyin").

From the tone-marked pinyin the Chinese dictionary already gives
(`pinyin.mark_pinyin`'s "yóu", "nǚ", "le"), by the standard table: the
initial's symbol, then the final's (ㄧ ㄨ ㄩ for i, u, ü before the rest);
zhi, chi, shi, ri, zi, ci and si the initial alone; ju, qu, xu and the
y- and w- spellings read as what they stand for. Tones as zhuyin marks
them: the first unmarked, ˊ ˇ ˋ after the syllable, the neutral tone's ˙
before it ("le": ˙ㄌㄜ).

A syllable the table doesn't know ("m", "hng", a Latin letter) is kept as
it was. Plain Python; holds caption text's sound: never log it.
"""

import unicodedata

INITIALS = {
    "zh": "ㄓ", "ch": "ㄔ", "sh": "ㄕ",
    "b": "ㄅ", "p": "ㄆ", "m": "ㄇ", "f": "ㄈ", "d": "ㄉ", "t": "ㄊ", "n": "ㄋ",
    "l": "ㄌ", "g": "ㄍ", "k": "ㄎ", "h": "ㄏ", "j": "ㄐ", "q": "ㄑ", "x": "ㄒ",
    "r": "ㄖ", "z": "ㄗ", "c": "ㄘ", "s": "ㄙ",
}  # fmt: skip
"""Longest first: zh before z."""

FINALS = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ê": "ㄝ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ",
    "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ", "er": "ㄦ",
    "ong": "ㄨㄥ",
    "i": "ㄧ", "ia": "ㄧㄚ", "io": "ㄧㄛ", "ie": "ㄧㄝ", "iao": "ㄧㄠ", "iu": "ㄧㄡ",
    "iou": "ㄧㄡ", "ian": "ㄧㄢ", "in": "ㄧㄣ", "iang": "ㄧㄤ", "ing": "ㄧㄥ",
    "iong": "ㄩㄥ",
    "u": "ㄨ", "ua": "ㄨㄚ", "uo": "ㄨㄛ", "uai": "ㄨㄞ", "ui": "ㄨㄟ", "uei": "ㄨㄟ",
    "uan": "ㄨㄢ", "un": "ㄨㄣ", "uen": "ㄨㄣ", "uang": "ㄨㄤ", "ueng": "ㄨㄥ",
    "ü": "ㄩ", "üe": "ㄩㄝ", "üan": "ㄩㄢ", "ün": "ㄩㄣ",
}  # fmt: skip

WHOLE = {
    "yi": "ㄧ", "ya": "ㄧㄚ", "yo": "ㄧㄛ", "ye": "ㄧㄝ", "yai": "ㄧㄞ", "yao": "ㄧㄠ",
    "you": "ㄧㄡ", "yan": "ㄧㄢ", "yin": "ㄧㄣ", "yang": "ㄧㄤ", "ying": "ㄧㄥ",
    "yong": "ㄩㄥ", "yu": "ㄩ", "yue": "ㄩㄝ", "yuan": "ㄩㄢ", "yun": "ㄩㄣ",
    "wu": "ㄨ", "wa": "ㄨㄚ", "wo": "ㄨㄛ", "wai": "ㄨㄞ", "wei": "ㄨㄟ", "wan": "ㄨㄢ",
    "wen": "ㄨㄣ", "wang": "ㄨㄤ", "weng": "ㄨㄥ",
    "zhi": "ㄓ", "chi": "ㄔ", "shi": "ㄕ", "ri": "ㄖ", "zi": "ㄗ", "ci": "ㄘ", "si": "ㄙ",
    "r": "ㄦ",  # erhua's 儿 read on its own
}  # fmt: skip
"""Syllables spelt otherwise than initial + final."""

TONES = {"̄": 1, "́": 2, "̌": 3, "̀": 4}
"""The combining marks pinyin's tones are written with."""
MARKS = {2: "ˊ", 3: "ˇ", 4: "ˋ"}
NEUTRAL = "˙"


def split_tone(syllable: str) -> tuple[str, int]:
    """A tone-marked pinyin syllable's letters, lower case with ü, and its
    tone: 1-4, or 5 for the neutral tone (no mark)."""
    tone = 5
    letters = []
    for char in unicodedata.normalize("NFD", syllable.lower()):
        if char in TONES:
            tone = TONES[char]
        else:
            letters.append(char)
    plain = unicodedata.normalize("NFC", "".join(letters))
    return plain.replace("v", "ü").replace("u:", "ü"), tone


def zhuyin(syllable: str) -> str:
    """`syllable` (tone-marked pinyin: "yóu") in zhuyin ("ㄧㄡˊ"); as it
    was if the table doesn't know it."""
    letters, tone = split_tone(syllable)
    found = WHOLE.get(letters)
    if found is None:
        found = _spelt(letters)
    if found is None:
        return syllable
    if tone == 5:
        return NEUTRAL + found
    return found + MARKS.get(tone, "")


def _spelt(letters: str) -> str | None:
    """Initial + final, or None."""
    for initial, symbol in INITIALS.items():
        if letters.startswith(initial):
            final = letters[len(initial) :]
            if initial in ("j", "q", "x") and final.startswith("u"):
                final = "ü" + final[1:]  # ju, que, xuan: ü written as u
            symbols = FINALS.get(final)
            return symbol + symbols if symbols is not None else None
    return FINALS.get(letters)  # a syllable with no initial: ài, ēn, ér
