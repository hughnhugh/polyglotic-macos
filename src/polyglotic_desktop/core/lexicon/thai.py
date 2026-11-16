"""Thai words: the word split for Thai captions (polyglotic-hq 389;
decision 0173).

Thai writes a sentence's words without spaces ("ฉันกินข้าว", I eat rice);
a space ends a phrase or a sentence. So a caption's words are found by the
dictionary pack's own words, as Chinese's and Vietnamese's are: each run
of Thai letters is cut into the pack's words at the least cost
(`cut_run`). A word costs a little (`WORD`) plus how rare it is (log2 of
its rank), so a compound the pack has (ที่ดิน, land) beats its parts and
the commoner of two cuts wins (ตา + กลม, round eyes, over ตาก + ลม);
each cluster no word covers costs more than any ranked word
(`LEFT_OVER`), so the pack's words cover all they can. On a tie the
longer word comes first.

**Never inside a letter's cluster.** A cut never falls before a vowel or
tone mark written above or below a consonant (ั ิ ่ ้ ์...), before a
vowel that follows its consonant (ะ า ำ), after a vowel written before its
consonant (เ แ โ ใ ไ), or before a consonant silenced by ์ ("จันทร์"):
the rules of Thai character clusters (Theeramunkong et al., 2000), as far
as a dictionary-led split needs them - so "กา" is never found inside
"กาะ", and a word the pack hasn't got is left whole between the words it
has (a name: "ทักษิณ" stays one piece), not cut into letters.

ๆ (mai yamok: say the word before again) is a word of its own, not a
content word: it has no entry, and isn't a miss.

No library: plain Python over the pack's written forms, read once at the
first split (`DictionaryFile.headwords`), as Vietnamese's are. 389
measured it against UD Thai's segmented sentences beside PyThaiNLP's
newmm, and its cost per caption: decision 0173.
"""

from __future__ import annotations

import math
import threading
import unicodedata
from collections.abc import Collection, Container, Mapping, Sequence

from polyglotic_desktop.core.lexicon.english import words as letter_runs
from polyglotic_desktop.ports.dictionary import DictionaryFile
from polyglotic_desktop.ports.word_split import SplitWord

MAX_WORD = 30
"""The longest word the split looks for, in characters: 99.9 % of
Wiktionary's Thai headwords are 27 or shorter; the longer are titles and
proverbs, which a caption rarely says whole."""

REPEAT = "ๆ"
"""Mai yamok: the word before, said again."""
_ABOVE_OR_BELOW = frozenset("ัิีึืฺุู") | frozenset(chr(c) for c in range(0x0E47, 0x0E4F))
"""Marks written above or below a consonant: vowels (ั ิ ี ึ ื ุ ู ฺ),
tone marks, ็ ์ ํ ๎."""
_FOLLOWING = frozenset("ะาำๅ")
"""Vowels written after their consonant but never starting a syllable:
ะ า ำ ๅ."""
_LEADING = frozenset("เแโใไ")
"""Vowels written before their consonant: เ แ โ ใ ไ."""
_SILENCED = "์"
"""์ (thanthakhat): the consonant under it is silent, part of the
syllable before."""
_ABBREVIATION = "ฯ"
"""ฯ: the word before, abbreviated ("กรุงเทพฯ")."""


def is_thai(ch: str) -> bool:
    """A letter or mark of the Thai script (not its digits or ฿)."""
    return "ก" <= ch <= "๎" and ch != "฿"


def has_thai(text: str) -> bool:
    return any(is_thai(ch) for ch in text)


def boundaries(run: str) -> list[int]:
    """Where a cut may fall in `run` (Thai letters and marks): 0, the
    end, and each place between two clusters (the module's rules)."""
    n = len(run)
    out = [0]
    for i in range(1, n):
        ch, before = run[i], run[i - 1]
        if (
            ch in _ABOVE_OR_BELOW
            or ch in _FOLLOWING
            or ch == _ABBREVIATION
            or before in _LEADING
            or (i + 1 < n and run[i + 1] == _SILENCED)
        ) and REPEAT not in (ch, before):
            continue
        out.append(i)
    if n:
        out.append(n)
    return out


WORD = 4.0
"""What a word costs beyond its rarity (`word_cost`): fewer words win
where rarity is close."""
LEFT_OVER = 20.0
"""What each cluster no word covers costs: more than any word but the
rarest, so the pack's words cover what they can - but not by a string of
rare short words through a name (`cut_run`)."""


SARA_AM = "ำ"
"""ำ: how the pack writes the vowel -am."""
SARA_AM_APART = "ํา"
"""ํา: the same vowel as two characters (its compatibility form) - how the
speech model writes it now and then ("ประจํา" for ประจำ, polyglotic-hq
389's captions)."""


def written(text: str) -> str:
    """`text` as the pack writes it: marks in Unicode's order (NFC), and
    ำ as one character."""
    return unicodedata.normalize("NFC", text).replace(SARA_AM_APART, SARA_AM)


def spellings(form: str) -> tuple[str, ...]:
    """A pack's form as a caption may write it: as it is, and with ำ as two
    characters."""
    if SARA_AM in form:
        return (form, form.replace(SARA_AM, SARA_AM_APART))
    return (form,)


def word_cost(rank: int | None, ranks: int) -> float:
    """What a word costs the split: `WORD` plus how rare it is - log2 of
    its rank (the rank's share of all words falls about as one over the
    rank), past the last rank (`ranks`) for a word without one."""
    return WORD + math.log2(rank if rank else ranks + 1)


def prefixes(words: Collection[str]) -> frozenset[str]:
    """Every start of every word (the words too): the split stops reading
    longer pieces once none is a word's start."""
    return frozenset(w[:k] for w in words for k in range(1, min(len(w), MAX_WORD) + 1))


def cut_run(
    run: str,
    words: Container[str],
    starts: Container[str],
    cost: Mapping[str, float],
    unranked: float = WORD + 20,
) -> list[tuple[int, int, bool]]:
    """(start, end, found) of each word of `run` (Thai letters only): the
    pack's `words` cutting it at the least cost - each word's own (`cost`,
    `word_cost`; `unranked` for one not in it), each cluster left over
    `LEFT_OVER` - and on a tie the longer word first; `starts`: every start
    of a word (`prefixes`). What the words don't cover is left as pieces
    between them, `found` False."""
    cuts = boundaries(run)
    at = {b: n for n, b in enumerate(cuts)}
    key = unicodedata.normalize("NFC", run)  # marks in order: no length change
    if len(key) != len(run):
        key = run
    m = len(cuts)
    # best[k]: (cost of run[:cuts[k]], previous k, a word?)
    best: list[tuple[float, int, bool] | None] = [(0.0, -1, True)] + [None] * (m - 1)

    def offer(k: int, candidate: tuple[float, int, bool]) -> None:
        current = best[k]
        # <=: on a tie the later start wins - the longer earlier word
        if current is None or candidate[0] <= current[0]:
            best[k] = candidate

    for k in range(m - 1):
        before = best[k]
        if before is None:
            continue
        start = cuts[k]
        offer(k + 1, (before[0] + LEFT_OVER, k, False))  # a cluster left over
        for end in range(start + 1, min(len(run), start + MAX_WORD) + 1):
            piece = key[start:end]
            if piece not in starts:
                break
            if end in at and piece in words:
                offer(at[end], (before[0] + cost.get(piece, unranked), k, True))
    spans: list[tuple[int, int, bool]] = []
    k = m - 1
    while k > 0:
        step = best[k]
        assert step is not None  # every cluster is a step
        start, end, found = cuts[step[1]], cuts[k], step[2]
        if spans and not found and not spans[-1][2]:
            spans[-1] = (start, spans[-1][1], False)  # left over: one piece
        else:
            spans.append((start, end, found))
        k = step[1]
    spans.reverse()
    return _repeats_apart(run, spans)


def _repeats_apart(
    run: str, spans: list[tuple[int, int, bool]]
) -> list[tuple[int, int, bool]]:
    """ๆ as a word of its own, never inside a piece left over."""
    out = []
    for start, end, found in spans:
        piece = start
        for i in range(start, end):
            if run[i] == REPEAT:
                if piece < i:
                    out.append((piece, i, found))
                out.append((i, i + 1, False))
                piece = i + 1
        if piece < end:
            out.append((piece, end, found))
    return out


def thai_runs(text: str) -> list[tuple[int, int]]:
    """(start, end) of each run of `text` in one script: the letter runs
    (`english.words`) cut where Thai meets another script ("AIจะ"); a
    hyphen or apostrophe between the two is neither's ("ไทย-จีน")."""
    out = []
    for start, end in letter_runs(text):
        i = start
        while i < end:
            thai = is_thai(text[i])
            j = i + 1
            while j < end and is_thai(text[j]) == thai:
                j += 1
            a, b = i, j
            while a < b and not text[a].isalpha():
                a += 1
            while b > a and not (text[b - 1].isalpha() or is_thai(text[b - 1])):
                b -= 1
            if a < b:
                out.append((a, b))
            i = j
    return out


def split(
    text: str,
    words: Container[str],
    starts: Container[str],
    cost: Mapping[str, float],
    unranked: float = WORD + 20,
) -> list[SplitWord]:
    """The words of `text`: each Thai run cut by `cut_run`, a run in
    another script (an English word) whole. A word written otherwise than
    the pack writes it (`written`) is looked up as the pack writes it."""
    out = []
    for start, end in thai_runs(text):
        if not is_thai(text[start]):
            out.append(SplitWord(start, end))
            continue
        for a, b, _ in cut_run(text[start:end], words, starts, cost, unranked):
            said = text[start + a : start + b]
            form = written(said)
            out.append(
                SplitWord(
                    start + a,
                    start + b,
                    lemmas=(form,) if form != said else (),
                    content=said != REPEAT,
                )
            )
    return out


class ThaiSplit:
    """The `WordSplit` port for Thai, over a dictionary pack's written
    forms and ranks."""

    def __init__(self, file: DictionaryFile) -> None:
        self._file = file
        self._data: (
            tuple[frozenset[str], frozenset[str], dict[str, float], float] | None
        ) = None
        self._lock = threading.Lock()

    def _read(self) -> tuple[frozenset[str], frozenset[str], dict[str, float], float]:
        """The written forms (each as a caption may spell it: `spellings`),
        every start of one, their costs and an unranked one's - read now if
        not yet."""
        with self._lock:
            if self._data is None:
                words = frozenset(
                    s
                    for w in self._file.headwords()
                    if has_thai(w)
                    for s in spellings(w)
                )
                ranks = self._file.frequency_ranks()
                last = max(ranks.values(), default=0)
                cost = {
                    s: word_cost(rank, last)
                    for form, rank in ranks.items()
                    for s in spellings(form)
                }
                self._data = (words, prefixes(words), cost, word_cost(None, last))
            return self._data

    def words(self, text: str) -> Sequence[SplitWord]:
        return split(text, *self._read())
