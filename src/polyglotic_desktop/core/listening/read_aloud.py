"""A selection read aloud, in its spoken form (polyglotic-hq 488, 495;
decision 0229). Plain Python, no Qt.

"Say it" reads what the learner selected - one side of it: what was said,
or its translation - as it would be said, not as the captions cut it:
- **at a caption cut** (where one caption ends and the next begins, and
  only there): a syllable or word said on both sides is said once
  (群岛主|主要 -> 群岛主要), a full stop the cut put mid-sentence goes
  ("críticos. a través"), and a capital it put mid-sentence is lowered
  ("cope With") - on a word that is never a name (`LOWERED`);
- **fillers** go: um, uh, erm, hmm in English; 嗯, 呃 standing alone in
  Chinese (`FILLERS`). Words that are also fillers elsewhere stay (对, 啊);
- **years are read as years:** "1767" as "seventeen sixty-seven" in
  English (only where it reads as a year: standing alone, or after "in",
  "since", "by"...), and 1767年 as 一七六七年 in Chinese - Windows' voices
  say both as a count (measured 2026-11-18).

Nothing else changes: no rewording (a model's job, 486's). Each character
of the spoken form knows the characters of the selection it came from
(`ReadAloud.came_from`), so the word being said lights where it is shown.
It is read a sentence at a time (`ReadAloud.chunks`).

Holds caption text: never log it.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.listening.history import is_cjk


@dataclass(frozen=True)
class Stretch:
    """Text read aloud as the window shows it: one clause's selected
    characters on one side, and the caption (its key) they are in - where
    the caption changes is a caption cut."""

    text: str
    caption: int


Origin = tuple[int, int, int]
"""Where spoken text came from: the stretch, and its characters
`[start, end)`."""


@dataclass(frozen=True)
class ReadAloud:
    """A selection's side in its spoken form: `text`, what the voice is
    given; `chunks`, its sentences as `[start, end)` of it, read one at a
    time; `origins`, for each character of `text`, where it came from."""

    text: str
    chunks: tuple[tuple[int, int], ...]
    origins: tuple[Origin | None, ...]

    def chunk_texts(self) -> tuple[str, ...]:
        return tuple(self.text[a:b] for a, b in self.chunks)

    def came_from(self, chunk: int, start: int, end: int) -> tuple[Origin, ...]:
        """The stretches' characters that `[start, end)` of chunk `chunk`
        was made from: one `(stretch, start, end)` a stretch, in order -
        what to light while a word is said. None for a chunk not read."""
        if not 0 <= chunk < len(self.chunks):
            return ()
        offset, limit = self.chunks[chunk]
        spans: dict[int, tuple[int, int]] = {}
        for each in self.origins[offset + max(0, start) : offset + min(end, limit)]:
            if each is None:
                continue
            stretch, first, last = each
            held = spans.get(stretch)
            spans[stretch] = (
                (min(held[0], first), max(held[1], last)) if held else (first, last)
            )
        return tuple((s, a, b) for s, (a, b) in sorted(spans.items()))


CJK_LANGUAGES = ("zh", "yue", "ja")
"""Languages written without spaces between words: a cut's repeat is a
syllable, not a word."""

FILLERS: dict[str, tuple[str, ...]] = {
    "en": ("uh-huh", "mm-hmm", "um", "uh", "erm", "hmm", "mhm"),
    "zh": ("嗯哼", "嗯", "呃"),
    "yue": ("嗯", "呃"),
}
"""Sounds that fill a pause, by language - from the server's own list
(polyglotic-server `core/listening/filters.py`, `FILLER_WORDS`, 2026-11-18),
less those that are words too: "mm" (millimetres), 额 (金额, 额外),
Vietnamese ừ/ờ ("yes"). The Chinese ones only where they stand alone, between
marks or at an end."""

LOWERED = frozenset(
    (
        *("with", "the", "a", "an", "and", "of", "to", "in", "for", "on", "at"),
        *("by", "from", "but", "or", "as", "that", "which", "who", "is", "are"),
        *("was", "were", "it", "its", "this", "these", "those", "into", "than"),
        *("con", "el", "la", "los", "las", "en", "de", "y", "que", "del", "por"),
        *("para", "un", "una", "le", "les", "des", "du", "et", "der", "die"),
        *("das", "und", "mit", "il", "di", "e"),
    )
)
"""Words a cut's capital is taken off: never names (polyglotic-hq 488)."""

YEAR_BEFORE = frozenset(
    (
        *("in", "since", "by", "from", "until", "till", "to", "before", "after"),
        *("around", "circa", "c.", "of", "year", "early", "late", "mid", "during"),
        *("between", "and", "spring", "summer", "autumn", "fall", "winter"),
        *("january", "february", "march", "april", "may", "june", "july"),
        *("august", "september", "october", "november", "december"),
    )
)
"""A four-figure number after one of these is a year (English)."""

_SENTENCE_END = re.compile(r"[.!?。！？…]+[\"'”’」』)）]*")
_ABBREVIATIONS = frozenset(
    ("mr", "mrs", "ms", "dr", "st", "mt", "jr", "sr", "vs", "etc", "no", "prof")
)
_HAN_DIGITS = "〇一二三四五六七八九"
_ONES = (
    *("", "one", "two", "three", "four", "five", "six", "seven", "eight"),
    *("nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen"),
    *("sixteen", "seventeen", "eighteen", "nineteen"),
)
_TENS = (
    *("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy"),
    *("eighty", "ninety"),
)


class _Text:
    """Text being made into its spoken form: each character with where it
    came from, so removing and replacing keeps track."""

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.origins: list[Origin | None] = []

    def add(self, text: str, origin: list[Origin | None]) -> None:
        self.chars.extend(text)
        self.origins.extend(origin)

    @property
    def text(self) -> str:
        return "".join(self.chars)

    def replace(self, start: int, end: int, said: str) -> None:
        """`[start, end)` said as `said`: each of its characters from the
        whole of what it replaces."""
        known = [o for o in self.origins[start:end] if o is not None]
        origin: Origin | None = None
        if known:
            origin = (known[0][0], known[0][1], known[-1][2])
        self.chars[start:end] = list(said)
        self.origins[start:end] = [origin] * len(said)


def read_aloud(stretches: Sequence[Stretch], language: str) -> ReadAloud:
    """`stretches` (in reading order) in their spoken form in `language` (as
    a caption row names it: "zh", "en"...)."""
    made = _Text()
    cuts: list[int] = []
    caption: int | None = None
    for index, stretch in enumerate(stretches):
        text = stretch.text.strip()
        if not text:
            continue
        lead = len(stretch.text) - len(stretch.text.lstrip())
        if made.chars:
            if not (is_cjk(made.chars[-1]) or is_cjk(text[0])):
                made.add(" ", [None])
            if caption != stretch.caption:
                cuts.append(len(made.chars))
        caption = stretch.caption
        made.add(text, [(index, lead + i, lead + i + 1) for i in range(len(text))])
    primary = language.split("-")[0].lower()
    for cut in reversed(cuts):
        _mend_cut(made, cut, primary)
    _drop_fillers(made, primary)
    _years(made, primary)
    text = made.text
    return ReadAloud(text, _sentences(text), tuple(made.origins))


def _mend_cut(made: _Text, cut: int, language: str) -> None:
    """A caption cut at `cut`: a syllable or word said on both sides said
    once; a full stop or capital the cut put mid-sentence taken out."""
    text = made.text
    left, right = text[:cut], text[cut:]
    if language in CJK_LANGUAGES:
        for size in (3, 2, 1):
            tail = left[-size:]
            if len(left) >= size and right.startswith(tail) and _letters(tail):
                del made.chars[cut : cut + size]
                del made.origins[cut : cut + size]
                return
        return
    words_left, words_right = left.split(), right.split()
    if not words_left or not words_right:
        return
    last, first = words_left[-1], words_right[0]
    if _bare(last) and _bare(last) == _bare(first) and last[-1:].isalnum():
        start = cut + (len(right) - len(right.lstrip()))
        end = start + len(first)
        while end < len(made.chars) and made.chars[end] == " ":
            end += 1
        del made.chars[start:end]
        del made.origins[start:end]
        return
    stripped = left.rstrip()
    if stripped.endswith(".") and first[:1].islower() and not _abbreviation(last):
        at = len(stripped) - 1
        del made.chars[at]
        del made.origins[at]
        return
    if (
        first[:1].isupper()
        and not stripped.endswith((".", "?", "!", ":"))
        and _bare(first) in LOWERED
    ):
        at = cut + (len(right) - len(right.lstrip()))
        made.chars[at] = made.chars[at].lower()


def _letters(text: str) -> bool:
    return all(c.isalpha() for c in text)


def _bare(word: str) -> str:
    return word.strip(",.;:!?\"'()").lower()


def _abbreviation(word: str) -> bool:
    return word.rstrip(".").lower() in _ABBREVIATIONS


def _drop_fillers(made: _Text, language: str) -> None:
    fillers = FILLERS.get(language, ())
    if not fillers:
        return
    words = "|".join(re.escape(f) for f in fillers)
    if language in CJK_LANGUAGES:
        # alone: at the start or after a mark, and at the end or before one
        mark = "，。、,.！？!?；;：:"
        pattern = re.compile(
            rf"(?:^|(?<=[{mark}\s]))(?:{words})(?:[，、,]|(?=[{mark}])|$)"
        )
    else:
        pattern = re.compile(rf"(?:,\s*)?\b(?:{words})\b,?", re.IGNORECASE)
    while (found := pattern.search(made.text)) is not None:
        del made.chars[found.start() : found.end()]
        del made.origins[found.start() : found.end()]
    _tidy(made)


def _tidy(made: _Text) -> None:
    """No space or comma left at an end, doubled, or before a mark - where
    a filler was taken out."""
    index = 0
    while index < len(made.chars):
        char = made.chars[index]
        following = made.chars[index + 1] if index + 1 < len(made.chars) else ""
        extra = (
            char == " " and (not index or not following or following in " ,.!?;:")
        ) or (char in "，、," and (not index or following in "。！？.!?，、,"))
        if extra:
            del made.chars[index]
            del made.origins[index]
            index = max(0, index - 1)
        else:
            index += 1


def _years(made: _Text, language: str) -> None:
    if language in ("zh", "yue"):
        for found in reversed(list(re.finditer(r"(?<!\d)(\d{4})(?=年)", made.text))):
            said = "".join(_HAN_DIGITS[int(d)] for d in found.group(1))
            made.replace(*found.span(1), said)
    elif language == "en":
        text = made.text
        number = re.compile(r"(?<![\d$£€¥.,])\b(1[0-9]{3})\b(?![\d%]|[.,]\d)")
        for found in reversed(list(number.finditer(text))):
            year = int(found.group(1))
            if year < 1010 or not _a_year(text, *found.span()):
                continue
            made.replace(*found.span(), _english_year(year))


def _a_year(text: str, start: int, end: int) -> bool:
    """Whether the number at `[start, end)` of English `text` reads as a
    year: standing alone (between marks or ends), or after a word years
    follow ("in 1767")."""
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    alone_before = not before or before[-1] in '.!?;:(—–-"“'
    alone_after = not after or after[0] in '.!?,;:)—–-"”'
    if alone_before and alone_after:
        return True
    words = before.split()
    return bool(words) and words[-1].lower().strip(",(") in YEAR_BEFORE


def _english_year(year: int) -> str:
    """1767 as "seventeen sixty-seven", 1900 "nineteen hundred", 1905
    "nineteen oh five" (1010-1999)."""
    high, low = divmod(year, 100)
    if low == 0:
        return f"{_english_number(high)} hundred"
    if low < 10:
        return f"{_english_number(high)} oh {_ONES[low]}"
    return f"{_english_number(high)} {_english_number(low)}"


def _english_number(number: int) -> str:
    """1-99 in words."""
    if number < 20:
        return _ONES[number]
    tens, ones = divmod(number, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _sentences(text: str) -> tuple[tuple[int, int], ...]:
    """`text`'s sentences as `[start, end)`, without the spaces between:
    cut after a full stop, question or exclamation mark (and a closing
    quote) - not after an abbreviation ("St.") or inside a number."""
    found: list[tuple[int, int]] = []
    start = 0
    for mark in _SENTENCE_END.finditer(text):
        end = mark.end()
        following = text[end : end + 1]
        if following and not (following.isspace() or is_cjk(text[mark.start()])):
            continue  # "1.5", "e.g." - or a mark run on into a word
        words = text[start : mark.start()].split()
        if text[mark.start()] == "." and words and _abbreviation(words[-1]):
            continue
        found.append((start, end))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    if start < len(text):
        found.append((start, len(text)))
    return tuple((a, b) for a, b in found if text[a:b].strip())
