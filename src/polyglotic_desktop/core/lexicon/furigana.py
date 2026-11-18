"""Furigana over Japanese: the reading line's kana, from the Japanese
pack's word split (polyglotic-hq 370, 383 and 511; decision 0155).

The word split (Sudachi, with the small dictionary the app already ships)
reads each word of a line in katakana (`SplitWord.kana`). A reading line
puts that in hiragana over each run of kanji in the word, the kana
written beside them (okurigana) left out by matching the two
(`readings_of`): 食べ たべ gives た over 食, 取り扱い とりあつかい gives と
over 取 and あつか over 扱. A number's counter is read by the number
before it (`COUNTERS`: 1本 いっぽん, 3分 さんぷん), which the word split
reads alike whatever comes before. Two or three words the split cut
where the pack has them as one headword are read as it reads that word
(`FuriganaReader.joined`): a compound's sound changes, which the split's
pieces don't know (辛抱強く: しんぼうづよ, not しんぼうつよ).

370 judged Sudachi small's readings of 1,168 kanji runs in FLEURS's
Japanese by hand: 97.3 % right, and 98.1 % with the word split's two
name rules (日本人 じん, アマゾン川 がわ); 511 measured this module on the
same sentences (its report): 99.4 % of 844 kanji runs (the rules made
there) and 98.1 % of 324 held out. Its misses are mostly the choice
between a kanji's readings (雪道 ゆきみち, 地ビール じ).

Holds caption text's sound: never log it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.ports.word_split import SplitWord

KANJI = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f々〆ヶ]+")
"""A run of kanji: the CJK ideographs, and 々 (repeat the one before), 〆
and ヶ (the small ke of 3ヶ月), which are read as kanji are."""

COUNTERS = {
    "本": ("ほん", "ぽん", "ぼん"),
    "杯": ("はい", "ぱい", "ばい"),
    "匹": ("ひき", "ぴき", "びき"),
    "分": ("ふん", "ぷん", "ぷん"),
    "対": ("たい", "たい", "たい"),
}
"""A counter whose first sound changes with the number before it, read
plainly, after 1, 6, 8 or 10 (a number ending in 0), and after 3 - and
for 分, after 4 as after 3: 2本 にほん, 1本 いっぽん, 3本 さんぼん, 4分
よんぷん. Sudachi small reads each the same after any number (本 ぽん,
分 ふん). And 対 between two numbers, a score, is たい (21対20), not つい."""
_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_KANA = re.compile("[ぁ-ゖァ-ヺー]+")
JOINED = (3, 2)
"""How many of the split's words may read as one of the pack's headwords,
most first (`FuriganaReader.joined`)."""
KEPT = 20000
"""How many headwords' kana a reader keeps: captions say them again."""


def hiragana(kana: str) -> str:
    """`kana` with its katakana as hiragana (タベ: たべ); the rest as it is."""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in kana)


def readings_of(text: str, word: SplitWord) -> list[Reading]:
    """The furigana of `word` in `text`: one reading for each run of kanji,
    its kana found by matching the word's kana written around it - none
    for a word without kanji or without kana. Where the two don't match
    (a reading Sudachi gives as said, a number written in digits: 1人
    ひとり), its whole reading over the word, less the kana it starts and
    ends with."""
    surface = text[word.start : word.end]
    kana = hiragana(word.kana)
    runs = [(m.start(), m.end()) for m in KANJI.finditer(surface)]
    if not runs or not kana:
        return []
    counted = _counted(text, word.start, surface)
    if counted:
        kana = counted
    pattern, at = "", 0
    for start, end in runs:
        pattern += re.escape(hiragana(surface[at:start])) + "(.+?)"
        at = end
    pattern += re.escape(hiragana(surface[at:]))
    found = re.fullmatch(pattern, kana)
    if found is not None:
        last = len(runs) - 1
        return [
            Reading(word.start + start, word.start + end, found.group(n + 1), n == last)
            for n, (start, end) in enumerate(runs)
        ]
    return _whole(word.start, surface, kana)


def _whole(at: int, surface: str, kana: str) -> list[Reading]:
    """`kana` over `surface` (at `at`) less the kana both start and end
    with."""
    plain = hiragana(surface)
    first = 0
    while first < min(len(plain), len(kana)) - 1 and plain[first] == kana[first]:
        first += 1
    last = 0
    while (
        last < min(len(plain), len(kana)) - first - 1
        and plain[-1 - last] == kana[-1 - last]
    ):
        last += 1
    read = kana[first : len(kana) - last]
    return [Reading(at + first, at + len(surface) - last, read)] if read else []


def _counted(text: str, start: int, surface: str) -> str:
    """A counter's reading after the number before it (`COUNTERS`) - ""
    if `surface` isn't a counter after a number."""
    forms = COUNTERS.get(surface)
    if forms is None or start == 0:
        return ""
    end = start
    while end > 0 and text[end - 1].translate(_DIGITS).isdigit():
        end -= 1
    number = text[end:start].translate(_DIGITS)
    if not number.isascii() or not number.isdigit():
        return ""
    plain, after_one, after_three = forms
    last = number[-1]
    if last in "1680":
        return after_one
    if last == "3" or (last == "4" and surface == "分"):
        return after_three
    return plain


def _within(text: str, start: int, end: int, head: str, kana: str) -> list[Reading]:
    """`head`'s furigana by `kana` over `text[start:end]`, its inflected
    spelling (辛抱強く as 辛抱強い): the runs of kanji the two share."""
    surface = text[start:end]
    return [
        Reading(start + r.start, start + r.end, r.text, r.ends_word)
        for r in readings_of(head, SplitWord(0, len(head), kana=kana))
        if r.end <= len(surface) and head[r.start : r.end] == surface[r.start : r.end]
    ]


class FuriganaReader:
    """The furigana of Japanese text, by the Japanese pack's word split."""

    def __init__(self, dictionary: BasicDictionary) -> None:
        self.dictionary = dictionary
        self._kana: dict[str, str] = {}

    @property
    def ready(self) -> bool:
        """Whether its word split can answer now (`BasicDictionary.ready`)."""
        return self.dictionary.ready

    def readings(self, text: str) -> list[Reading]:
        """Furigana over each word of `text` with kanji (`readings_of`) -
        or over two or three words the pack has as one (`joined`)."""
        found: list[Reading] = []
        words: Sequence[SplitWord] = self.dictionary.split(text)
        at = 0
        while at < len(words):
            count, head, kana = self.joined(text, words, at)
            if count > 1:
                end = words[at + count - 1].end
                found.extend(_within(text, words[at].start, end, head, kana))
            else:
                found.extend(readings_of(text, words[at]))
            at += count
        return found

    def joined(
        self, text: str, words: Sequence[SplitWord], at: int
    ) -> tuple[int, str, str]:
        """How many words from `at` read as one of the pack's headwords -
        their spelling, or with the last in its dictionary form (辛抱強く:
        辛抱強い) - with the one kana the pack gives it; (1, "", "") if
        none. Only where kanji meet kanji between the words: a compound,
        not a word and its particle."""
        for count in JOINED:
            run = words[at : at + count]
            if len(run) < count or not all(
                a.end == b.start and _kanji(text[a.end - 1]) and _kanji(text[b.start])
                for a, b in pairwise(run)
            ):
                continue
            stem = text[run[0].start : run[-1].start]
            spelt = text[run[0].start : run[-1].end]
            for head in dict.fromkeys(
                (spelt, *(stem + lemma for lemma in run[-1].lemmas))
            ):
                kana = self._kana_of(head)
                if kana:
                    return count, head, kana
        return 1, "", ""

    def _kana_of(self, head: str) -> str:
        """The one kana reading the pack gives `head` as a headword - ""
        where it has none, or more than one."""
        kept = self._kana.get(head)
        if kept is not None:
            return kept
        said = {
            entry.reading
            for entry in self.dictionary.lookup_split(head, SplitWord(0, len(head)))
            if entry.headword == head and _KANA.fullmatch(entry.reading)
        }
        kana = said.pop() if len(said) == 1 else ""
        if len(self._kana) >= KEPT:
            self._kana.clear()
        self._kana[head] = kana
        return kana


def _kanji(char: str) -> bool:
    return bool(KANJI.fullmatch(char))
