"""Settled text: what a caption has shown for a few seconds doesn't change.

The learner reads a caption as it appears. A later hearing of the same
speech - the next live update, the finished caption, a join - used to
rewrite all of it, words read seconds ago among them (the user,
2026-11-13: "We don't need to rewrite words spoken 3 seconds ago right?";
polyglotic-hq 296, decision 0088). The rule:

- **Settled words.** Words a caption has shown unchanged for
  `SETTLE_AFTER_SEC` (or the shorter time the learner chose, down to none:
  `SETTLE_RANGE`), and every clause above its last `OPEN_CLAUSES`, are
  settled: an update never changes them. Only what comes after them is
  taken from the update. Never half a word; and not the last word of a
  live caption, which trails off mid-speech.
- **Settled rows.** A settled clause that has its translations keeps them
  and its place too: its row pair is as it was. One still waiting for a
  translation (live captions untranslated, a translation on its way)
  takes the update's rows over its settled words.
- **Where the update carries on.** The update is the same speech heard
  again, so its words are lined up with the ones shown (word by word;
  character by character in Chinese or Japanese), and the words after the
  place the settled ones end at are what's new. The lining up is the one
  that passes over the fewest words (`_shared`): a word one hearing lost
  or gained just before that place is passed over, never made up for by
  finding a common word further on - that left words out (polyglotic-hq
  301). Where the two hearings share nothing to line up by, the place is
  reckoned by length - or by how much longer the speech had become, if
  known (`grew`).
- **Rows the hearings split differently.** When the update's clause at
  that place starts further back than a settled row, that row joins it:
  the words stay, the row and its translation are the update's - so a
  translation never says part of a line twice or leaves part out.

`Stable` keeps how long a caption's words have stood; `settle` applies the
rule to an update's clauses. Nothing here reads a clock. Holds caption
text: never log it.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from polyglotic_desktop.core.listening.captions import Clause

SETTLE_AFTER_SEC = 3.0
"""Words shown unchanged this long are settled (the user's "3 seconds"),
unless the learner chose less (`SETTLE_RANGE`)."""

SETTLE_RANGE = (0.0, SETTLE_AFTER_SEC)
"""How long the learner may let shown words still change (the user,
2026-11-14: "changing lines up to 3 seconds in live updates is a bit too
long anyway, make this a configurable setting. After 0s - 3seconds";
polyglotic-hq 309, decision 0099). 0: a word is settled as soon as it is
shown - but for the last word of a live caption, which may be half said."""

OPEN_CLAUSES = 2
"""Only a caption's last clauses may still be rewritten, however new the
ones above them are (the user: "after 1-2 lines, lines should settle")."""


def shown_text(clauses: Sequence[Clause]) -> str:
    """The clauses' originals end to end - a space between two that would
    run together: what positions here count in."""
    text = ""
    for clause in clauses:
        text += joint(text, clause.original) + clause.original
    return text


@dataclass(frozen=True, slots=True)
class Stable:
    """How long a caption's shown words have stood: `marks` are (since,
    length) pairs, oldest first - the text's first `length` characters
    have been as they are since `since` (seconds on any one clock)."""

    marks: tuple[tuple[float, int], ...] = ()

    def after(self, before: str, now: str, at: float) -> "Stable":
        """The marks once `before` has become `now` at `at`: what the two
        share from the start has stood as long as it had; the rest is new."""
        same = _common_prefix(before, now)
        marks: list[tuple[float, int]] = []
        for since, length in self.marks:
            shared = min(length, same)
            if shared > (marks[-1][1] if marks else 0):
                marks.append((since, shared))
        if not marks or marks[-1][1] < len(now):
            marks.append((at, len(now)))
        return Stable(tuple(marks))

    def then(self, length: int, starts: int, following: "Stable") -> "Stable":
        """These marks for a text of `length` characters, with `following`'s
        for the text that comes after it, from `starts` on: one text's
        marks."""
        whole = max((since for since, n in self.marks if n >= length), default=None)
        if length and whole is None:
            return self  # its own end hasn't stood: nothing after it has
        marks = [mark for mark in self.marks if mark[1] <= length]
        for since, n in following.marks:
            marks.append((max(since, whole or since), starts + n))
        return Stable(tuple(sorted(set(marks), key=lambda m: (m[1], m[0]))))

    def stood(self, at: float, seconds: float = SETTLE_AFTER_SEC) -> int:
        """How many characters from the start have stood for `seconds`."""
        return max(
            (length for since, length in self.marks if at - since >= seconds),
            default=0,
        )


def settled_length(clauses: Sequence[Clause], stood: int, live: bool) -> int:
    """How much of the shown text is settled: what has `stood` long enough
    and every clause above the last `OPEN_CLAUSES` - but never half a
    word, nor the last word of a `live` caption."""
    words = _Words(clauses)
    above = words.clause_starts[max(0, len(clauses) - OPEN_CLAUSES)]
    settled = max(words.start_of(min(stood, len(words.text))), above)
    if live and words.starts:
        settled = min(settled, words.starts[-1])
    return settled


def settle(
    shown: Sequence[Clause],
    update: Sequence[Clause],
    settled: int,
    grew: float | None = None,
) -> tuple[Clause, ...]:
    """`update`'s clauses with the first `settled` characters of `shown`'s
    text kept as they are (the module's rule). The same clauses back when
    nothing is settled. `grew`: how many times longer the speech the
    update heard is than the speech `shown` heard, if known."""
    old, new = _Words(shown), _Words(update)
    settled = old.start_of(min(settled, len(old.text)))
    if settled <= 0 or not update:
        return tuple(update)
    lined_up = _LinedUp(old, new, grew)
    carries_on = lined_up.forward(settled)
    wanted = {language for clause in update for language in clause.translations}

    # The rows that stay: settled clauses that have every translation wanted
    # - fewer, until the update has a clause starting where the rest starts.
    rows = 0
    for n, clause in enumerate(shown):
        if old.clause_starts[n] + len(clause.original) > settled or any(
            not clause.translations.get(language) for language in wanted
        ):
            break
        rows = n + 1
    first = 0
    while rows:
        if rows == len(shown):
            rest = carries_on
            if rest >= len(new.text):
                first = len(update)  # nothing carries on: no row is added
                break
        else:
            rest = lined_up.forward(old.clause_starts[rows])
        first = min(bisect_right(new.clause_starts, rest), len(update)) - 1
        if _same_place(new.text, new.clause_starts[first], rest):
            break
        if _same_place(new.text, new.clause_starts[first + 1], rest):
            first += 1
            break
        rows, first = rows - 1, 0

    # The rest: the settled words left, then the update's from where it
    # carries on, in the update's rows.
    kept = old.text[old.clause_starts[rows] : settled]
    tail = new.text[carries_on:]
    kept += joint(kept, tail)
    words = kept + tail
    if first >= len(update) and words.strip():
        first = len(update) - 1  # settled words past the update's end: its last row
    again = {clause.original: clause for clause in update}
    result = [
        _with_links(clause, again.get(clause.original)) for clause in shown[:rows]
    ]
    at = 0
    for n in range(first, len(update)):
        clause = update[n]
        end_in_new = new.clause_starts[n + 1]
        if n == len(update) - 1:
            end = len(words)
        elif end_in_new <= carries_on:  # it ends inside the settled words
            end = min(lined_up.back(end_in_new), settled) - old.clause_starts[rows]
            end = max(0, end)
        else:
            end = len(words) - (len(new.text) - end_in_new)
        if end <= at:
            continue
        text, at = words[at:end], end
        if text.strip() == clause.original.strip():
            result.append(clause)
        elif text.strip():
            result.append(_shown_with_links(text.strip(), clause))
    return tuple(result)


def _shown_with_links(shown: str, update: Clause) -> Clause:
    """A row of settled words that differ from the update's - with the
    update's translations, and its word links for the words both have
    (polyglotic-hq 340: the row had no links at all, though one word in
    twelve differed). A link to a word the update changed goes: it would
    underline other characters than the ones it was made for. The
    translation is the update's own, so its ends there stand."""
    matcher = SequenceMatcher(None, update.original, shown, autojunk=False)
    same = [block for block in matcher.get_matching_blocks() if block.size]
    links = {}
    for language, sent in update.links.items():
        kept = []
        for link in sent:
            start, end = link.original
            block = next(
                (b for b in same if b.a <= start and end <= b.a + b.size), None
            )
            if block is not None:
                moved = block.b - block.a
                kept.append(replace(link, original=(start + moved, end + moved)))
        if kept:
            links[language] = tuple(kept)
    return Clause(shown, update.translations, links, update.written_in)


def _with_links(shown: Clause, again: Clause | None) -> Clause:
    """A settled row as the update has it, if that only adds to it: the
    same words and translations, now with their word links."""
    if again is not None and all(
        again.translations.get(language) == text
        for language, text in shown.translations.items()
    ):
        return again
    return shown


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def _wide(char: str) -> bool:
    """A character of a script written without spaces between words: each
    is lined up on its own."""
    return (
        "⺀" <= char <= "鿿"
        or "豈" <= char <= "﫿"
        or "＀" <= char <= "￯"
        or "฀" <= char <= "໿"  # Thai, Lao
    )


def joint(before: str, after: str) -> str:
    """A space where two pieces of spaced text would run together."""
    if not before or not after or before[-1].isspace() or after[0].isspace():
        return ""
    return "" if _wide(before[-1]) or _wide(after[0]) else " "


def _same_place(text: str, a: int, b: int) -> bool:
    """Whether two places in `text` have no word between them."""
    low, high = sorted((a, b))
    return not any(char.isalnum() for char in text[low:high])


class _Words:
    """Clauses' text end to end (`shown_text`), and where its words and
    clauses start - `clause_starts` has the text's end last. A word is a
    run of characters between spaces (its punctuation with it), or one
    character of a script written without them; a clause always starts
    one."""

    def __init__(self, clauses: Sequence[Clause]) -> None:
        self.text = ""
        self.clause_starts = []
        for clause in clauses:
            self.text += joint(self.text, clause.original)
            self.clause_starts.append(len(self.text))
            self.text += clause.original
        self.clause_starts.append(len(self.text))
        clause_starts = set(self.clause_starts)
        self.starts: list[int] = []
        before = " "
        for at, char in enumerate(self.text):
            if not char.isspace() and (
                before.isspace() or _wide(before) or _wide(char) or at in clause_starts
            ):
                self.starts.append(at)
            before = char
        ends = [*self.starts[1:], len(self.text)][: len(self.starts)]
        self.keys = [
            _key(self.text[start:end])
            for start, end in zip(self.starts, ends, strict=True)
        ]

    def start_of(self, at: int) -> int:
        """`at`, or the start of the word it falls inside - the next
        word's, from the space after one (the text's end stays the end)."""
        while at < len(self.text) and self.text[at].isspace():
            at += 1
        if at >= len(self.text):
            return len(self.text)
        n = bisect_right(self.starts, at)
        return self.starts[n - 1] if n else 0

    def word_at(self, at: int) -> int:
        """Which word starts at or after `at`: how many start before it."""
        return bisect_left(self.starts, at)

    def place(self, word: int) -> int:
        """Where word number `word` starts - the text's end, past the last."""
        return self.starts[word] if word < len(self.starts) else len(self.text)


def _key(word: str) -> str:
    """What two hearings of a word are compared by: its letters and digits,
    whatever the case or the punctuation around it."""
    letters = "".join(char for char in word if char.isalnum()).casefold()
    return letters or word.strip()


class _LinedUp:
    """Two hearings of the same speech lined up word by word: where a place
    in one falls in the other. Between words they share, in proportion.
    After the last word they share, the new hearing has the old one's last
    words again and then goes on: as many words on - or, with `grew` (how
    many times longer the new one's speech is), as far on as the speech
    says, at an even pace."""

    def __init__(self, old: _Words, new: _Words, grew: float | None) -> None:
        self._old, self._new = old, new
        self._points = [(0, 0)]
        for a, b in _shared(old.keys, new.keys):
            if len(self._points) > 1 and self._points[-1] == (a, b):
                self._points[-1] = (a + 1, b + 1)  # the run of words goes on
            else:
                self._points += [(a, b), (a + 1, b + 1)]
        shared_old, shared_new = self._points[-1]
        self._left_old = len(old.keys) - shared_old
        self._left_new = len(new.keys) - shared_new
        # how much of the new hearing's last words the old one's last words are
        self._share = 1.0
        if grew is not None and old.keys and grew > 0:
            heard = shared_old / len(old.keys)  # of the old speech, till there
            self._share = min(1.0, (1 - heard) / max(grew - heard, 1e-9))
        elif self._left_new:
            self._share = min(1.0, self._left_old / self._left_new)

    def forward(self, at: int) -> int:
        """Where the place `at` in the old text falls in the new."""
        word = self._old.word_at(at)
        found = _between(self._points, word, 0)
        if found is None:
            shared_old, shared_new = self._points[-1]
            along = (word - shared_old) / self._left_old if self._left_old else 1.0
            found = shared_new + round(along * self._share * self._left_new)
        return self._new.place(found)

    def back(self, at: int) -> int:
        """Where the place `at` in the new text falls in the old."""
        word = self._new.word_at(at)
        found = _between(self._points, word, 1)
        if found is None:
            shared_old, shared_new = self._points[-1]
            again = self._share * self._left_new  # the old one's last words
            along = min(1.0, (word - shared_new) / again) if again else 1.0
            found = shared_old + round(along * self._left_old)
        return self._old.place(found)


_SKIP = 4
"""What a word of either hearing costs that the other hasn't got."""

_SAME = -3
"""What a word both have is worth. With `_SKIP`: a lone word the old
hearing ends on is the new one's only if at most one word was gained
before it; two together, three; three, five."""

_ALIKE = -1
"""What a word cut short in one hearing is worth ("refresh", "refreshing")."""

_STEM = 3
"""The fewest letters of a word that count as the word cut short."""


_APART = 24
"""How many words apart the same word may be in the two hearings (counted
from the first word they differ at): keeps the lining up quick for a long
caption, and one hearing is never that many words out from the other."""


def _shared(old: Sequence[str], new: Sequence[str]) -> list[tuple[int, int]]:
    """Which words of the old hearing are which of the new one's: (old,
    new) word numbers, in order.

    The new hearing is the old speech again, and then goes on. So every
    old word is either found in the new hearing or passed over (`_SKIP`),
    and so is every new word up to the last one found - the new words
    after that are the speech going on, and cost nothing. The cheapest
    such lining up is taken (polyglotic-hq 301). That is what keeps a
    word the old hearing has and the new one lost ("entered the yard",
    then "entered yard and cornered the inmates") from being found in a
    "the" three words on: passing "the" over costs one word, reaching the
    later one costs three. Of two equally cheap, the one that finds the
    old words earliest in the new hearing: no new word is left out."""
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    pairs = [(n, n) for n in range(start)]
    a, b = old[start:], new[start:]
    if not a or not b:
        return pairs
    # cost[i][j]: the cheapest lining up of a[i:] with b[j:] - worked out
    # only where the two places are within `_APART` words of each other
    width = len(b) + 1
    far = _SKIP * (len(a) + len(b) + 1)  # dearer than any lining up
    cost = [[far] * width for _ in range(len(a))]
    below = [0] * width  # every old word found or passed: the rest is free
    for i in range(len(a) - 1, -1, -1):
        row, word, last = cost[i], a[i], i == len(a) - 1
        if len(b) <= i + _APART:
            row[len(b)] = below[len(b)] + _SKIP
        for j in range(min(len(b), i + _APART + 1) - 1, max(0, i - _APART) - 1, -1):
            best = min(below[j], row[j + 1]) + _SKIP
            worth = _worth(word, b[j], last)
            if worth is not None and below[j + 1] + worth < best:
                best = below[j + 1] + worth
            row[j] = best
        below = row
    cost.append([0] * width)
    i = j = 0
    while i < len(a) and j < len(b):
        worth = _worth(a[i], b[j], i == len(a) - 1)
        if worth is not None and cost[i][j] == cost[i + 1][j + 1] + worth:
            pairs.append((start + i, start + j))
            i, j = i + 1, j + 1
        elif cost[i][j] == cost[i + 1][j] + _SKIP:
            i += 1
        else:
            j += 1
    return pairs


def _worth(old: str, new: str, last: bool) -> int | None:
    """What lining these two words up is worth - None: they aren't one
    word. `last`: the old hearing's last word, which may be half said -
    any start of the new one will do for it."""
    if old == new:
        return _SAME
    if (last or len(old) >= _STEM) and new.startswith(old):
        return _ALIKE
    if len(new) >= _STEM and old.startswith(new):
        return _ALIKE
    return None


def _between(points: Sequence[tuple[int, int]], at: int, axis: int) -> int | None:
    """Where word `at` of one hearing falls in the other, between the words
    they share (`points`, in order) - None after the last of them."""
    other = 1 - axis
    before = points[0]
    for point in points[1:]:
        if point[axis] >= at:
            span = point[axis] - before[axis]
            if span <= 0:
                return point[other]
            share = (at - before[axis]) / span
            return before[other] + round(share * (point[other] - before[other]))
        before = point
    return None if at > before[axis] else before[other]
