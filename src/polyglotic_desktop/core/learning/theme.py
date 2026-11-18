"""The conversation's words (polyglotic-hq 485, 491; desktop decision 0227):
what each source is talking about now, from its last `WINDOW` of finished
captions - for our curriculum's set (`curriculum`) to light in blue.

- **A source's window** (`SourceWindow`): the finished captions of what the
  PC played from one source (an app; never the learner's own mic) over the
  last `WINDOW`, with each word's caption count. Older captions drop out.
- **An update** comes after each `EVERY` of a source's talk
  (`ConversationThemes.heard` says when): the curriculum takes its words
  then, and only then - mid-sitting too (the user, 2026-11-18).
- **Everyday talk** (`everyday`) never lights: fillers (嗯, "um") and words
  of everyday speech that the pack's written ranks place far too rare
  (就是说, 没什么, "okay") - `EntryFacts.spoken_rank`, from subtitles,
  separate data. A word whose spoken rank is within the learner's line
  counts as known here (`known_by_speech`).
- **Stretch words** (`Chosen.STRETCH`): the conversation's own core words
  past the learner's window (业主 in a residents' meeting, "rubber" in a
  design meeting) once said in `STRETCH_IN` captions of the window; in
  Chinese two characters or more - one rare character said again and again
  is nearly always a piece of a name the word split cut up (潇 and 璐 of
  黄潇璐, in 491's live captions) - and never a word with no place at all
  (no rank, no level): more often a phrase the ranks didn't count (那时候)
  than a rare word.
- **Theme words** (`Chosen.THEME`): words in the learner's window said in
  `HEARD_IN` or more captions, said more here than their everyday share
  (keyness against the word's place), the keyest first.
- **Names the dictionary doesn't know** never light: in a language whose
  capitals inside a sentence mark only names (English, not German), a word
  never written in small letters in the window (Julia);
  in Chinese, one rare character past the window (below).
- **Look-alikes wait** (`look_alike`): a word one letter or character from
  one already lit waits until that one has gone.
- **The theme's name** (`theme_name`): the window's `NAME_WORDS` keyest
  words at any level ("业主 · 小区 · 物业").

All of it is in memory on the PC: nothing is stored or sent. The PC holds
every caption it shows, so it needs nothing from the server; a server's
conversation memory, if one comes (polyglotic-hq 487), would come in
behind `ConversationThemes`' calls (`heard`, `withdrawn`, `window`,
`said_lately`, `form`) as an adapter of its own. Holds caption words:
never log them.
"""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from polyglotic_desktop.core.learning.levels import place
from polyglotic_desktop.core.shared import EntryFacts, EntryId

WINDOW = timedelta(minutes=10)
"""How far back a source's window reaches (485: the theme of the last 10
minutes follows a meeting as it moves)."""

EVERY = timedelta(minutes=2)
"""A source's talk between updates (the user, 2026-11-18: "Theme should
constantly update on some rate, every few minutes")."""

HEARD_IN = 2
"""Captions of the window a word must be said in: once is chance."""

STRETCH_IN = 3
"""Captions of the window a word past the learner's window must be said in
to be lit as a stretch word (485 proposed 8; 491 measured 2, 3 and 4 on 75
public conversations: at 3 every meeting had stretch words, and 43 % of
them were said again within 10 minutes - at 2, 34 %)."""

EVERYDAY_TOP = 3000
"""Everyday talk: among this many commonest spoken words..."""

EVERYDAY_RATIO = 3
"""...and at least this many times commoner said than written (就是说:
2,495th said, 11,167th written; 便宜, 1,806th and 3,857th, isn't)."""

NAME_WORDS = 3
"""Words naming the theme."""

NAME_FLOOR = 1000
"""The theme's name skips the commonest words (an everyday place under
this): every conversation says them (咱们, 车 named a residents' meeting
before 业主 and 车位)."""

LARGEST = 100_000
"""The place of a word with none: rarer than any pack ranks."""

_H = math.log(LARGEST) + 0.5772
"""Zipf's law: a word's share of running text is about 1 / (place x H)."""

_REFERENCE_WORDS = 1e8
"""The general speech a window is compared with, in words (485)."""


class Chosen(StrEnum):
    """Why the conversation offers a word."""

    STRETCH = "stretch"
    THEME = "theme"


@dataclass(frozen=True, slots=True)
class Said:
    """An entry said in a source's window: in how many of its captions, how
    many times in all, the form it was said in, and when last;
    `capitalised`: never yet written in small letters there (Julia, of
    Julia Friedlander - a name, in a script with capitals)."""

    entry: EntryFacts
    form: str
    captions: int
    times: int
    last: datetime
    capitalised: bool = False


@dataclass(frozen=True, slots=True)
class Offered:
    """A word the conversation offers the curriculum: why, and `rate` - the
    share of the window's captions that said it, the blue words it adds to
    a caption, on average, while the talk goes on as it has."""

    said: Said
    chosen: Chosen
    rate: float


Word = tuple[EntryFacts, str]
"""A word of a finished caption: its entry's facts and the form said."""


class SourceWindow:
    """One source's finished captions over the last `span`, each kept once
    by its ID: a caption finished again (a join, "Looks wrong?") counts as
    it now stands, and a withdrawn one leaves."""

    def __init__(self, span: timedelta = WINDOW) -> None:
        self.span = span
        self._captions: dict[str, tuple[datetime, tuple[Word, ...]]] = {}
        """Oldest first."""
        self._said: dict[EntryId, Said] = {}
        self.words = 0
        """The words of the captions in it."""

    @property
    def captions(self) -> int:
        return len(self._captions)

    def add(self, caption_id: str, words: Sequence[Word], at: datetime) -> None:
        """A finished caption's words (names and numbers too: they count in
        the window's size)."""
        self.withdraw(caption_id)
        self.drop_before(at)
        kept = tuple(words)
        self._captions[caption_id] = (at, kept)
        self.words += len(kept)
        for entry_id, (facts, form, times) in _counted(kept).items():
            said = self._said.get(entry_id)
            forms = [f for f, e in _forms(kept) if e == entry_id]
            small = [f for f in forms if not f[:1].isupper()]
            capital = not small
            if said is None:
                said = Said(facts, form, 0, 0, at, capital)
            # the newest form in small letters, if it has one ("pressure",
            # not a sentence's first word "Pressure")
            if small:
                form = small[0]
            elif not said.capitalised:
                form = said.form
            self._said[entry_id] = replace(
                said,
                entry=facts,
                form=form,
                captions=said.captions + 1,
                times=said.times + times,
                last=at,
                capitalised=said.capitalised and capital,
            )

    def withdraw(self, caption_id: str) -> None:
        """A caption withdrawn, or about to count again: its words leave."""
        found = self._captions.pop(caption_id, None)
        if found is None:
            return
        _, words = found
        self.words -= len(words)
        for entry_id, (_, _, times) in _counted(words).items():
            said = self._said[entry_id]
            if said.captions <= 1:
                del self._said[entry_id]
            else:
                self._said[entry_id] = replace(
                    said, captions=said.captions - 1, times=said.times - times
                )

    def drop_before(self, now: datetime) -> None:
        """Captions older than the span leave."""
        while self._captions:
            caption_id, (at, _) = next(iter(self._captions.items()))
            if at >= now - self.span:
                return
            self.withdraw(caption_id)

    def said(self) -> Iterable[Said]:
        return self._said.values()

    def word(self, entry_id: EntryId) -> Said | None:
        return self._said.get(entry_id)

    def rate(self, entry_id: EntryId) -> float:
        """The share of its captions that said the word."""
        said = self._said.get(entry_id)
        return said.captions / len(self._captions) if said and self._captions else 0.0


def _forms(words: Iterable[Word]) -> Iterable[tuple[str, EntryId]]:
    return ((form, facts.entry_id) for facts, form in words)


def _counted(words: Iterable[Word]) -> dict[EntryId, tuple[EntryFacts, str, int]]:
    """Each entry in a caption once: its facts, its first form, its times."""
    found: dict[EntryId, tuple[EntryFacts, str, int]] = {}
    for facts, form in words:
        before = found.get(facts.entry_id)
        found[facts.entry_id] = (
            (facts, form, 1)
            if before is None
            else (before[0], before[1], before[2] + 1)
        )
    return found


class ConversationThemes:
    """Each source's window, and when its next update is due. In memory
    only: nothing here is stored or sent."""

    def __init__(self, span: timedelta = WINDOW, every: timedelta = EVERY) -> None:
        self.span = span
        self.every = every
        self._windows: dict[str, SourceWindow] = {}
        self._last_update: dict[str, datetime] = {}
        """When each source last had an update - or began talking again."""

    def heard(
        self, caption_id: str, source: str, words: Sequence[Word], at: datetime
    ) -> bool:
        """A finished caption from what the PC played, into its source's
        window. True when that source's update is due: `every` of its talk
        since the last one - the first `every` after it began talking (or
        began again, after a window's silence)."""
        window = self._windows.get(source)
        if window is None:
            window = self._windows[source] = SourceWindow(self.span)
        window.add(caption_id, words, at)
        last = self._last_update.get(source)
        if last is None or at - last > self.span:
            self._last_update[source] = at
            return False
        if at - last >= self.every:
            self._last_update[source] = at
            return True
        return False

    def withdrawn(self, caption_id: str) -> None:
        """A caption withdrawn (or joined into another): out of its window."""
        for window in self._windows.values():
            window.withdraw(caption_id)

    def window(self, source: str) -> SourceWindow | None:
        return self._windows.get(source)

    def said_lately(self, entry_id: EntryId, now: datetime) -> bool:
        """Whether any source's window still holds the word."""
        for window in self._windows.values():
            window.drop_before(now)
            if window.word(entry_id) is not None:
                return True
        return False

    def form(self, entry_id: EntryId) -> str | None:
        """The form the word was last said in, if a window holds it."""
        for window in self._windows.values():
            said = window.word(entry_id)
            if said is not None:
                return said.form
        return None

    def clear(self) -> None:
        self._windows.clear()
        self._last_update.clear()


# -- the rules -----------------------------------------------------------------


def everyday(facts: EntryFacts) -> bool:
    """Everyday talk, never lit from a conversation: a filler, or one of the
    `EVERYDAY_TOP` commonest spoken words said at least `EVERYDAY_RATIO`
    times more often than its place in writing says."""
    if facts.is_filler:
        return True
    spoken, written = facts.spoken_rank, place(facts)
    return (
        spoken is not None
        and spoken <= EVERYDAY_TOP
        and (written is None or written >= EVERYDAY_RATIO * spoken)
    )


def known_by_speech(facts: EntryFacts, known_words: int) -> bool:
    """Whether the learner hears the word so often they know it: its rank
    in speech within the words they know."""
    return facts.spoken_rank is not None and facts.spoken_rank <= known_words


def reference_place(facts: EntryFacts) -> int:
    """The word's everyday place: the smaller of its place and its rank in
    speech (`LARGEST` when it has neither)."""
    found = [p for p in (place(facts), facts.spoken_rank) if p is not None]
    return min(found) if found else LARGEST


def keyness(times: int, words: int, reference: int) -> float:
    """How much more the word is said here than its everyday share: log2
    of the ratio (485's log-ratio). Above 0: said more than usual."""
    if times <= 0 or words <= 0:
        return -math.inf
    return math.log2(times / words * reference * _H)


def _log_likelihood(times: int, words: int, reference: int) -> float:
    """Dunning's G2 against general speech, signed (485's theme keywords):
    weighs how often against how rare."""
    share = 1.0 / (reference * _H)
    usual = share * _REFERENCE_WORDS
    total = words + _REFERENCE_WORDS
    here = words * (times + usual) / total
    there = _REFERENCE_WORDS * (times + usual) / total
    g2 = 2 * (times * math.log(times / here) + usual * math.log(usual / there))
    return g2 if times / words > share else -g2


def _countable(facts: EntryFacts) -> bool:
    return not (
        facts.is_name or facts.is_number or facts.spells_a_number or everyday(facts)
    )


def offered(
    window: SourceWindow,
    may_enter: Callable[[EntryFacts], bool],
    reaches: Callable[[EntryFacts], bool],
    known_words: int,
) -> list[Offered]:
    """What the window offers the curriculum, in its order: stretch words
    (past the learner's window: not `reaches`), the most said first; then
    theme words (in it), the keyest first. `may_enter`: the word may be in
    the set (past the line, not known or ignored). Look-alikes are the
    curriculum's to keep apart (it knows what is lit)."""
    stretch: list[tuple[int, float, str, Said]] = []
    theme: list[tuple[float, str, Said]] = []
    for said in window.said():
        facts = said.entry
        if said.captions < HEARD_IN or not _countable(facts) or _a_name(said):
            continue
        if known_by_speech(facts, known_words) or not may_enter(facts):
            continue
        key = keyness(said.times, window.words, reference_place(facts))
        if key <= 0:
            continue
        if reaches(facts):
            theme.append((-key, facts.entry_id, said))
        elif (
            said.captions >= STRETCH_IN
            and not _one_character(said.form)
            and place(facts) is not None
        ):
            stretch.append((-said.captions, -key, facts.entry_id, said))
    stretch.sort()
    theme.sort()
    return [
        Offered(s, Chosen.STRETCH, window.rate(s.entry.entry_id)) for *_, s in stretch
    ] + [Offered(s, Chosen.THEME, window.rate(s.entry.entry_id)) for *_, s in theme]


def theme_name(window: SourceWindow, words: int = NAME_WORDS) -> list[Said]:
    """The window's theme, named by its `words` keyest words at any level:
    said in `HEARD_IN` captions or more, past the commonest words, never
    everyday talk, names, numbers, one Chinese character or a word with no
    place; by log-likelihood, which weighs how often against how rare."""
    scored = [
        (-_log_likelihood(s.times, window.words, reference_place(s.entry)), s)
        for s in window.said()
        if s.captions >= HEARD_IN
        and _countable(s.entry)
        and not _a_name(s)
        and not _one_character(s.form)
        and place(s.entry) is not None
        and reference_place(s.entry) >= NAME_FLOOR
    ]
    scored = [(g, s) for g, s in scored if g < 0]
    scored.sort(key=lambda pair: (pair[0], pair[1].entry.entry_id))
    return [s for _, s in scored[:words]]


def look_alike(a: str, b: str) -> bool:
    """Forms a learner could take for each other (473: kept apart). Chinese:
    the same length, two characters or more, one of them different (发表,
    发布). Others: one letter apart, two when both are long (remote,
    remove; expense, expensive)."""
    if a == b:
        return False
    if _han(a) or _han(b):
        return (
            len(a) == len(b) >= 2
            and sum(x != y for x, y in zip(a, b, strict=False)) == 1
        )
    a, b = a.lower(), b.lower()
    most = 2 if min(len(a), len(b)) >= 7 else 1
    if abs(len(a) - len(b)) > most:
        return False
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        before, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            before, row[j] = (
                row[j],
                min(row[j] + 1, row[j - 1] + 1, before + (ca != cb)),
            )
    return 0 < row[-1] <= most


def _a_name(said: Said) -> bool:
    """Never written in small letters, in a language whose capitals inside
    a sentence mark only names."""
    return said.capitalised and said.entry.names_capitalised


def _one_character(form: str) -> bool:
    """A Chinese word of one character."""
    return len(form) == 1 and _han(form)


def _han(text: str) -> bool:
    return any("㐀" <= c <= "鿿" for c in text)
