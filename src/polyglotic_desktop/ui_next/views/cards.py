"""Steady's card stack: captions dealt onto cards that never change shape
(polyglotic-hq 552, decision 0260; the user, 2026-11-20: "a smooth mode in
steady ... no text jumping around up and back, lines being formed to and
fro, translations popping in mid way pushing everything around").

A caption window in a paced mode shows cards, not captions:

- **A card** is one line of what was said, with the room under it kept for
  its translation. A word placed on a card keeps its card and its place.
- **Words are added at the end of the front card.** A word that doesn't
  fit - or whose translation wouldn't, as far as the server's unseen text
  says - starts the next card, and so does a new caption: a card's
  translation is its own caption's. Nothing goes back.
- **A shown word the server changes** is changed where it is if the new
  one fits its room; otherwise the change waits until its caption is
  finished, and the card is then set again within itself, once
  (`Deck.counts.settles`). A word never changes card.
- **A translation goes into the room kept for it**: a caption's, one
  text, cut between its cards at a word's edge where the fewest word links
  cross; what is wider than its card runs on into the next card's room,
  and at the last is cut short with an ellipsis. It never takes a second
  line, so it never moves a word.
- **The next card is made a word ahead** (`Deck.room`): the server's text
  runs ahead of what the playout shows, so the deck knows when the next
  word won't fit. The stack moves while the last word of the line is
  read, and the word arrives on a card already in place.

`Deck` turns the caption updates a window is shown into caption updates of
cards: each card a small caption (`CaptionId` "card:...") of clauses that
fit one line. Everything after it - the view, the layout, word links,
lookups, selection, copying - sees captions, as it always did; nothing
downstream knows a deck exists (as nothing knows a playout does).

`Glide` is the stack's one motion: a critically damped spring. `drum` is
where a card is drawn as it recedes. Plain Python, no Qt; widths are
measured by whoever lays the cards out (`Measure`).
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.core.shared.tunables import tunable

Measure = Callable[[str, bool], float]
"""A text's width in px as a card draws it: what was said (False) or a
translation (True)."""
Split = Callable[[str], Sequence[tuple[int, int]]]

_UNSPACED = "㐀-鿿぀-ヿ"
_PIECES = re.compile(rf"[{_UNSPACED}]+|[^\s{_UNSPACED}]+|\s+")
LIKELY_RATIO = 1.3
"""A translation's width over what was said's, before any is known."""
NEW_CARD_AFTER_SEC = tunable(
    "cards.new_card_after",
    5.0,
    "seconds",
    (1.0, 10.0),
    source="552 card stack; 583 depth",
)
"""A caption said this long after the front card's last one ended - a
pause in the speech, by the captions' own times (else since the last word
was shown) - starts a card; before it, short captions share the line
until it is full (polyglotic-hq 583, the user, 2026-11-21: "consecutive
lines get made for single words in a sentence"). Not a sentence's end:
the server ends every finished fragment with a full stop ("目前在。",
"因为。"), and in slow speech pauses of 2-4 s fell inside sentences; the
app's own joins (`JOIN_GAP_SEC`, 2 s) already take shorter ones as one."""
FIT = 0.97
"""The share of a card's width the deck fills: the layout's own spacing
between a card's clauses takes the rest."""
TO_SPARE = 1.15
"""How much wider than the server's unseen translation a card allows for:
the finished one is often longer."""
ELLIPSIS = "…"
CARD = "card:"


def unspaced(char: str) -> bool:
    """A character of a writing without spaces between words."""
    return "㐀" <= char <= "鿿" or "぀" <= char <= "ヿ"


def pieces(text: str, split: Split) -> list[tuple[str, bool]]:
    """`text` as the units a card is never broken inside - a word with the
    punctuation after it - each with whether a space follows it."""
    out: list[tuple[str, bool]] = []
    for found in _PIECES.finditer(text):
        piece = found.group()
        if piece.isspace():
            if out:
                out[-1] = (out[-1][0], True)
        elif unspaced(piece[0]):
            out += [(piece[a:b], False) for a, b in split(piece)]
        elif out and not out[-1][1] and not any(c.isalnum() for c in piece):
            out[-1] = (out[-1][0] + piece, False)  # punctuation stays with its word
        else:
            out.append((piece, False))
    return out


@dataclass(slots=True)
class Word:
    text: str
    clause: int
    width: float
    space: bool
    ratio: float
    ahead: bool = False
    """Not yet shown as said (the playout's words ahead): free to change."""
    synced: bool = True
    """Its text is the server's latest (False: a change is waiting)."""


@dataclass(slots=True)
class Card:
    number: int
    source: SourceId
    words: list[tuple[CaptionId, Word]] = field(default_factory=list)
    translations: dict[tuple[CaptionId, Language], tuple[str, int]] = field(
        default_factory=dict
    )
    """Each caption's translation on this card, and where it starts in the
    caption's whole translation - by caption and target."""
    lit: dict[tuple[CaptionId, Language], tuple[str, int]] = field(default_factory=dict)
    """`translations` as shown: a translation lands only while the stack
    is at rest (`Deck.reveal`), so it never seems to push anything."""
    closed: bool = False
    """The card after it has been made: it takes no more words."""
    changed: bool = True
    sent: CaptionUpdate | None = None
    """The last visible content, before the cause's trace time is attached."""
    named: tuple[Language | None, tuple[Language, ...]] | None = None
    """Its language and the languages heard in it, as first shown."""

    def used(self, space: float) -> float:
        return sum(w.width + (space if w.space else 0.0) for _, w in self.words)


@dataclass(slots=True)
class Counts:
    """What a deck did, for its tests and the measured checks: no caption
    text."""

    cards: int = 0
    words: int = 0
    in_place: int = 0  # a shown word changed where it is
    waited: int = 0  # changes to shown words left until the caption finished
    settles: int = 0  # cards set again within themselves at a finish
    made_ahead: int = 0
    cut_short: int = 0  # translations cut with an ellipsis


class Deck:
    """One source's captions dealt onto cards `width` px wide."""

    def __init__(
        self,
        width: float,
        measure: Measure,
        split: Split,
        prefix: str = "",
        likely: float | None = None,
    ) -> None:
        self.width = width * FIT
        self._likely = LIKELY_RATIO if likely is None else likely
        self._learn = likely is None
        self._ratios: list[float] = []
        """How much wider than their words the last finished captions'
        translations were: a card keeps room for the next one's by them."""
        self._last_word_at = -1e9
        self._measure, self._split, self._prefix = measure, split, prefix
        self._space = measure(" ", False)
        self.cards: list[Card] = []
        self._placed: dict[CaptionId, list[tuple[Card, Word]]] = {}
        self._heard: dict[CaptionId, CaptionUpdate] = {}
        self._heard_at: dict[CaptionId, float] = {}
        self.reveal = True
        """Whether translations land as they come (the window: only while
        the stack is at rest; the rest wait for `flush`)."""
        self._ends: dict[
            tuple[CaptionId, Language], tuple[str, list[int], list[int]]
        ] = {}
        """Each caption's translation as last cut: the text, its cards and
        where each card's share ends - shown words keep their card."""
        self._latest: dict[CaptionId, CaptionUpdate] = {}
        self._whole: dict[
            tuple[CaptionId, Language], tuple[str, tuple[WordLink, ...]]
        ] = {}
        """Each caption's translation as one text, and its word links in
        that text and the caption's shown words (`_translate`)."""
        self.counts = Counts()

    # -- what the server last said, unseen ---------------------------------------------

    def hear(self, update: CaptionUpdate, now: float = 0.0) -> None:
        """A caption update as the server sent it, before the playout shows
        any of it: only to size the cards and to see what is coming."""
        if update.kind is CaptionKind.WITHDRAWN:
            self._heard.pop(update.caption_id, None)
            self._heard_at.pop(update.caption_id, None)
            return
        for gone in update.replaces:
            if gone != update.caption_id:
                self._heard.pop(gone, None)
                self._heard_at.pop(gone, None)
        self._heard[update.caption_id] = update
        self._heard_at.setdefault(update.caption_id, now)
        while len(self._heard) > 60:
            oldest = next(iter(self._heard))
            del self._heard[oldest]
            self._heard_at.pop(oldest, None)

    def spoken(self, card_id: CaptionId) -> set[Language | None]:
        """The languages of the captions on card `card_id` (None: one not
        known) - empty if it isn't one of the newest cards."""
        for card in reversed(self.cards[-40:]):
            if self.card_id(card) == card_id:
                found: set[Language | None] = set()
                for caption, _ in card.words:
                    update = self._latest.get(caption)
                    found.add(update.language if update is not None else None)
                return found
        return set()

    def expected(self, card_id: CaptionId) -> float | None:
        """How wide card `card_id`'s words will likely be: its words, and
        what the server has said of its last caption that the playout has
        yet to show, as far as it fits - where a centred card first
        stands, so it grows into the middle (None: closed, or not a card
        of the newest)."""
        for card in reversed(self.cards[-8:]):
            if self.card_id(card) != card_id:
                continue
            if card.closed or not card.words:
                return None  # all of it there: centred as it is
            used = card.used(self._space)
            caption = card.words[-1][0]
            heard = self._heard.get(caption)
            mine = self._placed.get(caption, [])
            if heard is None:
                return used
            for _, text, _ in self._pieces(heard)[len(mine) :]:
                width = self._measure(text, False)
                if used + width > self.width:
                    break
                used += width + self._space
            return used
        return None

    def set_width(self, width: float) -> None:
        """The cards are `width` px wide from the next word on (the window
        was resized): words placed keep their card, which the window lays
        out again at its new width - nothing is dealt again."""
        self.width = width * FIT

    def said_at(self, when: float) -> None:
        """The last word shown was shown at `when` (the cards dealt again:
        each caption at its own time)."""
        self._last_word_at = when

    def coming(self, now: float = 0.0) -> bool:
        """Whether what the server has said, and the playout has yet to
        show, will need another card: a caption not begun (heard within
        `COMING_SEC`), or more words than the front card has room for. The
        window opens the room before the card comes (decision 0261)."""
        if not self.cards:
            return False
        front = self.cards[-1]
        if not front.words:
            return True  # made ahead already
        for caption, heard in self._heard.items():
            ahead = self._pieces(heard)
            mine = self._placed.get(caption)
            if not mine:
                fresh = now - self._heard_at.get(caption, now) <= COMING_SEC
                if ahead and fresh and caption not in self._latest:
                    return True
                continue
            if mine[-1][0] is not front or len(ahead) <= len(mine):
                continue
            used = front.used(self._space)
            lines = sum((w.width + self._space) * w.ratio for _, w in front.words)
            for clause, text, _ in ahead[len(mine) :]:
                width = self._measure(text, False)
                ratio = self._ratio(caption, clause)
                if used + width > self.width or lines + width * ratio > self.width:
                    return True
                used += width + self._space
                lines += (width + self._space) * ratio
        return False

    @property
    def room(self) -> bool:
        """A card has been made ahead of its first word: the stack keeps
        its place."""
        return bool(self.cards) and not self.cards[-1].words

    def finish(self) -> tuple[CaptionUpdate, ...]:
        """The deck is put away (the mode changed): the cards of captions
        still being said are withdrawn - their captions show as they come
        from here on - and the rest are finished, as they stand."""
        self.reveal = True
        for card in self.cards[-40:]:
            if card.lit != card.translations:
                card.changed = True
        out: list[CaptionUpdate] = []
        for caption, update in list(self._latest.items()):
            if update.kind is not CaptionKind.FINISHED:
                gone = CaptionUpdate(caption, update.source_id, CaptionKind.WITHDRAWN)
                out += self.show(gone, 0.0)
        for card in self.cards:
            if not card.closed:
                card.closed = card.changed = True
        if self.cards:
            cause = CaptionUpdate(
                CaptionId(""), self.cards[-1].source, CaptionKind.FINISHED
            )
            out += self._changes(cause)
        return tuple(out)

    def pending(self) -> bool:
        """A translation waits to land (`reveal` was off when it came)."""
        return any(card.lit != card.translations for card in self.cards[-40:])

    def flush(self) -> tuple[CaptionUpdate, ...]:
        """The translations that waited, landed: the cards they are on."""
        waiting = [c for c in self.cards[-40:] if c.lit != c.translations]
        if not waiting:
            return ()
        for card in waiting:
            card.changed = True
        cause = CaptionUpdate(CaptionId(""), waiting[-1].source, CaptionKind.FINISHED)
        was, self.reveal = self.reveal, True
        try:
            return self._changes(cause)
        finally:
            self.reveal = was

    def owns(self, caption: CaptionId) -> bool:
        """Whether `caption`'s words are on these cards."""
        return caption in self._placed

    def _ratio(self, caption: CaptionId, clause: int) -> float:
        heard = self._heard.get(caption)
        if heard is not None and clause < len(heard.clauses):
            said = heard.clauses[clause].original
            lines = [t for t in heard.clauses[clause].translations.values() if t]
            if said.strip() and lines:
                wide = max(self._measure(t, True) for t in lines)
                return TO_SPARE * wide / max(1.0, self._measure(said, False))
        if self._learn and len(self._ratios) >= 3:
            return TO_SPARE * sorted(self._ratios)[-2]
        return self._likely

    def _fits(self, card: Card, width: float, ratio: float) -> bool:
        if card.closed:
            return False
        if not card.words:
            return True
        if card.used(self._space) + width > self.width:
            return False
        estimates: dict[CaptionId, float] = {}
        for owner, word in card.words:
            estimates[owner] = (
                estimates.get(owner, 0.0) + (word.width + self._space) * word.ratio
            )
        # A translation already assigned to this card can be wider than
        # its share estimated from the original. Keep that actual space
        # when later words are dealt. Each target has its own row.
        extra: dict[Language, float] = {}
        for (owner, target), (text, _) in card.translations.items():
            if text:
                actual = self._measure(text, True) + self._space
                extra[target] = extra.get(target, 0.0) + max(
                    0.0, actual - estimates.get(owner, 0.0)
                )
        used = sum(estimates.values()) + max(extra.values(), default=0.0)
        return used + width * ratio <= self.width

    def _pieces(self, update: CaptionUpdate) -> list[tuple[int, str, bool]]:
        found: list[tuple[int, str, bool]] = []
        for i, clause in enumerate(update.clauses):
            if (
                found
                and not unspaced(found[-1][1][-1])
                and ord(found[-1][1][-1]) < 0x2E80
            ):
                found[-1] = (found[-1][0], found[-1][1], True)  # a clause apart
            found += [
                (i, text, space) for text, space in pieces(clause.original, self._split)
            ]
        return found

    # -- a caption update, as the window is shown it -------------------------------------

    def show(self, update: CaptionUpdate, now: float) -> tuple[CaptionUpdate, ...]:
        """A caption update: the card updates it makes."""
        caption = update.caption_id
        if update.kind is CaptionKind.WITHDRAWN:
            self._latest.pop(caption, None)
            for card, word in self._placed.pop(caption, []):
                self._take(card, word)
            return self._changes(update)
        taken: list[tuple[Card, Word]] = []
        for gone in update.replaces:  # a joined caption takes its captions' places
            if gone == caption:
                continue
            self._latest.pop(gone, None)
            for card, word in self._placed.pop(gone, []):
                card.words = [
                    (caption, each) if each is word else (owner, each)
                    for owner, each in card.words
                ]
                card.changed = True
                taken.append((card, word))
            for card in self.cards:
                for key in [k for k in card.translations if k[0] == gone]:
                    del card.translations[key]
        if taken:  # in the order they stand: a join can take a later caption's
            self._placed[caption] = self._in_order(
                [*taken, *self._placed.get(caption, [])]
            )
        finished = update.kind is CaptionKind.FINISHED
        self._latest[caption] = update
        new = self._pieces(update)
        shown = len(new)
        if not finished:  # how many of its words are established: the rest are ahead
            shown, count = 0, update.established
            for _, text, space in new:
                if count < len(text):
                    break
                count -= len(text) + space
                shown += 1
        old = self._placed.get(caption, [])
        # A waiting word already occupies a place on a card. Lighting it
        # (or extending the same hearing) must not deal it past a closed
        # card. Only the revised part of a tentative suffix needs dealing.
        for index, (_, word) in enumerate(old):
            if word.ahead and (index >= len(new) or word.text != new[index][1]):
                for card, tentative in old[index:]:
                    self._take(card, tentative)
                old = old[:index]
                break
        kept, tail, again = self._changed(old, new, finished)
        self._placed[caption] = kept
        for card, at in again.values():
            self._set_again(card, at)
        for index, (clause, text, space) in enumerate(tail, start=len(kept)):
            self._place(update, clause, text, space, index >= shown, now)
        for n, (_, word) in enumerate(self._placed[caption]):
            word.ahead = n >= shown
        if tail:
            self._last_word_at = now
            self._look_ahead(update, now)
        for card in {id(c): c for c, _ in self._placed[caption]}.values():
            card.changed = True
        self._translate(caption)
        return self._changes(update)

    def _changed(
        self,
        old: list[tuple[Card, Word]],
        new: list[tuple[int, str, bool]],
        finished: bool,
    ) -> tuple[
        list[tuple[Card, Word]],
        list[tuple[int, str, bool]],
        dict[int, tuple[Card, int]],
    ]:
        """`old` (the caption's shown words) against `new` (its words now):
        the words kept in their places, those to add at the end, and the
        cards to set again from a word on (only when `finished`)."""
        ops = SequenceMatcher(
            None, [w.text for _, w in old], [n[1] for n in new], autojunk=False
        ).get_opcodes()
        kept: list[tuple[Card, Word]] = []
        tail: list[tuple[int, str, bool]] = []
        again: dict[int, tuple[Card, int]] = {}

        def mark(card: Card, at: int) -> None:
            was = again.get(id(card))
            again[id(card)] = (card, at if was is None else min(was[1], at))

        def index(card: Card, word: Word | None) -> int:
            for n, (_, each) in enumerate(card.words):
                if each is word:
                    return n
            return len(card.words)

        for n, (op, i1, i2, j1, j2) in enumerate(ops):
            last = n == len(ops) - 1 and i2 == len(old)
            if op == "equal":
                for (card, word), piece in zip(old[i1:i2], new[j1:j2], strict=True):
                    word.clause, word.space, word.synced = piece[0], piece[2], True
                    kept.append((card, word))
                continue
            pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
            if pairs and ((i2 - i1) == (j2 - j1) or last or finished):
                for (card, word), piece in zip(
                    old[i1 : i1 + pairs], new[j1 : j1 + pairs], strict=True
                ):
                    width = self._measure(piece[1], False)
                    # where it is only if no word after it moves for it: as
                    # wide as it was, or the last on its card with room
                    fits = abs(width - word.width) <= 1.0 or (
                        card.words[-1][1] is word
                        and width <= self._slot(card, word) + 0.5
                    )
                    if fits or finished:
                        word.text, word.width = piece[1], width
                        word.clause, word.space, word.synced = piece[0], piece[2], True
                        card.changed = True
                        if fits:
                            self.counts.in_place += 1
                        else:
                            mark(card, index(card, word))
                    else:
                        word.synced = False
                        self.counts.waited += 1
                    kept.append((card, word))
                i1, j1 = i1 + pairs, j1 + pairs
            if i1 < i2:  # shown words the server no longer has
                if finished:
                    for card, word in old[i1:i2]:
                        mark(card, index(card, word))
                        self._take(card, word)
                else:
                    self.counts.waited += i2 - i1
                    for card, word in old[i1:i2]:
                        word.synced = False
                        kept.append((card, word))
            if j1 < j2:  # words it has that aren't shown
                if last or not old:
                    tail += new[j1:j2]
                elif finished:
                    card, before = kept[-1] if kept else (old[0][0], None)
                    at = index(card, before) + 1 if before is not None else 0
                    mark(card, at)
                    for k, piece in enumerate(new[j1:j2]):
                        word = Word(
                            piece[1],
                            piece[0],
                            self._measure(piece[1], False),
                            piece[2],
                            1.0,
                        )
                        card.words.insert(at + k, (self._owner(old), word))
                        kept.append((card, word))
                else:
                    self.counts.waited += j2 - j1
        return kept, tail, again

    def _in_order(self, words: list[tuple[Card, Word]]) -> list[tuple[Card, Word]]:
        """`words` as they stand on the cards: by card, then on its card."""
        cards = {id(card): n for n, card in enumerate(self.cards)}

        def where(each: tuple[Card, Word]) -> tuple[int, int]:
            card, word = each
            at = next((n for n, (_, mine) in enumerate(card.words) if mine is word), 0)
            return cards.get(id(card), -1), at

        return sorted(words, key=where)

    def _owner(self, old: list[tuple[Card, Word]]) -> CaptionId:
        """The caption `old`'s words are of."""
        card, word = old[0]
        return next(caption for caption, each in card.words if each is word)

    def _take(self, card: Card, word: Word) -> None:
        card.words = [each for each in card.words if each[1] is not word]
        card.changed = True

    def _slot(self, card: Card, word: Word) -> float:
        """The room `word` has where it is: as much as it took, and what
        is left of its card if it is the card's last."""
        if card.words and card.words[-1][1] is word:
            return word.width + max(0.0, self.width - card.used(self._space))
        return word.width

    def _set_again(self, card: Card, at: int) -> None:
        """`card` from its `at`-th word on, packed again within the card:
        the only time shown words move sideways - once, when their caption
        finished with other words. A card that is now too full stays one
        card: the layout draws it as it can."""
        card.changed = True
        self.counts.settles += 1

    def _place(
        self,
        update: CaptionUpdate,
        clause: int,
        text: str,
        space: bool,
        ahead: bool,
        now: float,
    ) -> None:
        caption = update.caption_id
        width = self._measure(text, False)
        ratio = self._ratio(caption, clause)
        mine = self._placed.setdefault(caption, [])
        if mine:
            at = self.cards.index(mine[-1][0])
        else:
            at = len(self.cards) - 1
            front = self.cards[at] if at >= 0 else None
            if front is None or self._breaks(front, update, now):
                # another speaker, language or a long pause starts a card;
                # else a caption carries on on the front card while it
                # fits: a short clause doesn't push the line just written
                # (553's third recording), and a sentence said slowly is
                # one line, not a card a word (583)
                at = self._new_card(update.source_id)
        while not self._fits(self.cards[at], width, ratio):
            at = (
                at + 1 if at < len(self.cards) - 1 else self._new_card(update.source_id)
            )
        card = self.cards[at]
        word = Word(text, clause, width, space, ratio, ahead)
        card.words.append((caption, word))
        card.changed = True
        mine.append((card, word))
        self.counts.words += 1

    def _breaks(self, front: Card, update: CaptionUpdate, now: float) -> bool:
        """Whether caption `update` starts a card rather than carrying on on
        `front`: said by another source, in another language (one card
        names one language, and its translation goes one way), or after a
        pause of over `NEW_CARD_AFTER_SEC`."""
        if front.source != update.source_id:
            return True
        if not front.words:
            return False  # made ahead for it
        before = self._latest.get(front.words[-1][0])
        if before is None:
            return now - self._last_word_at > NEW_CARD_AFTER_SEC.value
        if before.respoken != update.respoken:
            return True  # the source window marks only the learner's own words
        if (
            update.language is not None
            and before.language is not None
            and update.language != before.language
            and len(update.languages_heard) <= 1
            and len(before.languages_heard) <= 1
        ):
            return True
        if update.times is not None and before.times is not None:
            pause = update.times.speech_start - before.times.speech_end
        else:
            pause = now - self._last_word_at
        return pause > NEW_CARD_AFTER_SEC.value

    def _look_ahead(self, update: CaptionUpdate, now: float) -> None:
        """The next word is known before it is shown: if it won't fit the
        front card, the next card is made now."""
        heard = self._heard.get(update.caption_id)
        mine = self._placed.get(update.caption_id, [])
        if heard is None or not mine or mine[-1][0] is not self.cards[-1]:
            return
        ahead = self._pieces(heard)
        n = len(mine)
        if len(ahead) <= n or ahead[n - 1][1] != mine[-1][1].text:
            return
        clause, text, _ = ahead[n]
        width = self._measure(text, False)
        if not self._fits(
            self.cards[-1], width, self._ratio(update.caption_id, clause)
        ):
            self._new_card(update.source_id)
            self.counts.made_ahead += 1

    def _new_card(self, source: SourceId) -> int:
        if self.cards:
            self.cards[-1].closed = True
            self.cards[-1].changed = True
        self.cards.append(Card(self.counts.cards, source))
        self.counts.cards += 1
        return len(self.cards) - 1

    # -- translations into the cards' room -------------------------------------------------

    def _translate(self, caption: CaptionId) -> None:
        """The caption's translation - its clauses', one text - cut between
        the cards its words are on, at a word's edge."""
        update = self._latest.get(caption)
        mine = self._placed.get(caption, [])
        for card in self.cards[-40:]:
            for key in [k for k in card.translations if k[0] == caption]:
                del card.translations[key]
                card.changed = True
        for key in [k for k in self._whole if k[0] == caption]:
            del self._whole[key]
        if update is None or not mine:
            for key in [k for k in self._ends if k[0] == caption]:
                del self._ends[key]
            return
        # the clauses said in full, in order: with its last word, as the playout gives it
        ready, starts, said = 0, [], 0
        for number in range(len(update.clauses)):
            words = [word for _, word in mine if word.clause == number]
            if (
                any(word.ahead for word in words)
                and not update.clauses[number].translations
            ):
                break
            if not words and update.clauses[number].original.strip():
                break
            starts.append(said)
            said += sum(len(word.text) + word.space for word in words)
            ready = number + 1
        if not ready:
            return
        cards: list[Card] = []
        shares: list[int] = []
        for card, word in mine:
            if word.clause >= ready:
                break
            if not cards or cards[-1] is not card:
                cards.append(card)
                shares.append(0)
            shares[-1] += len(word.text) + word.space
        targets: list[Language] = []
        for clause in update.clauses[:ready]:
            targets += [
                t
                for t, text in clause.translations.items()
                if text and t not in targets
            ]
        for target in targets:
            whole, links = "", []
            for number, clause in enumerate(update.clauses[:ready]):
                text = clause.translations.get(target, "").strip()
                if not text:
                    continue
                lead = len(clause.translations[target]) - len(
                    clause.translations[target].lstrip()
                )
                if whole:
                    whole += " "
                for link in clause.links.get(target, ()):
                    links.append(
                        replace(
                            link,
                            original=(
                                link.original[0] + starts[number],
                                link.original[1] + starts[number],
                            ),
                            translation=(
                                link.translation[0] - lead + len(whole),
                                link.translation[1] - lead + len(whole),
                            ),
                        )
                    )
                whole += text
            if not whole:
                continue
            self._whole[(caption, target)] = (whole, tuple(links))
            if update.kind is CaptionKind.FINISHED and ready == len(update.clauses):
                said_px = sum(w.width + self._space for _, w in mine) or 1.0
                self._ratios = [
                    *self._ratios[-7:],
                    self._measure(whole, True) / said_px,
                ]
            ends = self._fitted(caption, target, whole, cards, shares, links)
            start = 0
            for n, card in enumerate(cards):
                part = whole[start : ends[n]]
                lead = len(part) - len(part.lstrip())
                card.translations[(caption, target)] = (part.strip(), start + lead)
                card.changed = True
                start = ends[n]

    def _fitted(
        self,
        caption: CaptionId,
        target: Language,
        whole: str,
        cards: list[Card],
        shares: list[int],
        links: Sequence[WordLink],
    ) -> list[int]:
        """Where each of `cards`' share of `whole` ends. Words already
        shown keep their card: when the text only grew, every card but the
        last cut keeps its share and that one keeps at least its own. What
        doesn't fit a card runs on into the next; what doesn't fit the last
        goes back where there is room; and what still doesn't fit stays
        whole - the card takes a second line. Never cut short."""
        ends = self._cuts(whole, shares, links)
        before = self._ends.get((caption, target))
        fixed, floor = 0, 0
        if (
            before is not None
            and whole.startswith(before[0])
            and [id(card) for card in cards[: len(before[1])]] == before[1]
        ):
            fixed, floor = len(before[1]) - 1, len(before[0])
            ends[:fixed] = before[2][:fixed]
            if fixed < len(ends):
                ends[fixed] = max(ends[fixed], floor)
        for n in range(1, len(ends)):
            ends[n] = max(ends[n], ends[n - 1])
        ends[-1] = len(whole)

        def over(n: int, start: int, end: int) -> bool:
            return self._over(cards[n], caption, target, whole[start:end])

        for n in range(fixed, len(cards) - 1):  # forwards: it runs on
            start = ends[n - 1] if n else 0
            least = max(start, floor if n == fixed else 0)
            end = ends[n]
            while end > least and whole[start:end].strip() and over(n, start, end):
                end = start + len(self._shorter(whole[start:end]))
            ends[n] = max(end, least)
            ends[n + 1] = max(ends[n + 1], ends[n])
        edges = self._edges(whole)
        for n in range(len(cards) - 1, fixed, -1):  # backwards: where there is room
            first = ends[n - 2] if n > 1 else 0
            while over(n, ends[n - 1], ends[n]):
                nxt = next((e for e in edges if e > ends[n - 1]), None)
                if nxt is None or nxt > ends[n] or over(n - 1, first, nxt):
                    break
                ends[n - 1] = nxt
        if over(len(cards) - 1, ends[-2] if len(ends) > 1 else 0, ends[-1]):
            self.counts.cut_short += 1  # counted still: a card with a second line
        self._ends[(caption, target)] = (whole, [id(card) for card in cards], ends)
        return ends

    def _over(
        self, card: Card, caption: CaptionId, target: Language, part: str
    ) -> bool:
        others = sum(
            self._measure(text, True) + self._space
            for key, (text, _) in card.translations.items()
            if key[1] == target and key[0] != caption and text
        )
        return others + self._measure(part.strip(), True) > self.width

    def _edges(self, text: str) -> list[int]:
        """Where `text` may be cut: before each word - a run of Chinese as
        the dictionary's words - never inside one, and at its end."""
        edges: list[int] = []
        spaced = True
        for found in _PIECES.finditer(text):
            piece = found.group()
            if piece.isspace():
                spaced = True
            elif unspaced(piece[0]):
                edges += [found.start() + a for a, _ in self._split(piece)]
                spaced = False
            else:
                if spaced or any(c.isalnum() for c in piece):
                    edges.append(found.start())  # else punctuation: with its word
                spaced = False
        return [*dict.fromkeys(edges), len(text)]

    def _shorter(self, part: str) -> str:
        """`part` less its last word: never a word cut through."""
        edges = self._edges(part.rstrip())
        return part[: edges[-2]] if len(edges) > 1 else ""

    def _cuts(
        self, text: str, shares: list[int], links: Sequence[WordLink]
    ) -> list[int]:
        """Where `text` (a caption's translation) is cut between cards that
        hold `shares` characters of what was said each: at a word's edge,
        where the fewest word links cross; with none, in proportion."""
        if len(shares) == 1:
            return [len(text)]
        edges = [0, *self._edges(text)]
        total = sum(shares) or 1
        cuts: list[int] = []
        said, least = 0, 0
        for share in shares[:-1]:
            said += share
            wanted = len(text) * said / total

            def cost(
                edge: int, said: int = said, wanted: float = wanted
            ) -> tuple[int, float]:
                crossing = sum(
                    1
                    for link in links
                    if (link.original[1] <= said) != (link.translation[1] <= edge)
                )
                return crossing, abs(edge - wanted)

            cut = min((e for e in edges if e >= least), key=cost)
            cuts.append(cut)
            least = cut
        return [*cuts, len(text)]

    # -- the cards as captions ------------------------------------------------------------

    def _changes(self, cause: CaptionUpdate) -> tuple[CaptionUpdate, ...]:
        out: list[CaptionUpdate] = []
        for card in self.cards:
            if not card.changed:
                continue
            card.changed = False
            if self.reveal or card.sent is None:
                # A new card arrives with its pair already in place.
                card.lit = dict(card.translations)
            else:  # none lands now; one whose caption went goes at once
                card.lit = {k: v for k, v in card.lit.items() if k in card.translations}
            update = self._as_caption(card, cause)
            if update == card.sent:
                continue  # lighting another card has not changed this one
            card.sent = update
            if update is None:
                update = CaptionUpdate(
                    self.card_id(card), card.source, CaptionKind.WITHDRAWN
                )
            out.append(update)
        if out and cause.times is not None:  # the caption timelines follow the first
            out[0] = replace(out[0], times=cause.times)
        while len(self.cards) > 400:  # long gone from any window
            del self.cards[0]
        return tuple(out)

    def card_id(self, card: Card) -> CaptionId:
        return CaptionId(f"{CARD}{self._prefix}{card.number}")

    def _as_caption(self, card: Card, cause: CaptionUpdate) -> CaptionUpdate | None:
        """`card` as a caption update: one clause - its words and their
        share of the translation - for each caption on it (one, but for a
        caption joined or set again)."""
        if not card.words:
            return None
        if card.sent is None and all(word.ahead for _, word in card.words):
            caption = card.words[0][0]
            if self._placed[caption][0][0] is not card:
                # The first line offers the waiting words immediately. A
                # later line must not roll it away until its own first beat.
                return None
        clauses: list[Clause] = []
        heard: list[Language] = []
        language: Language | None = None
        established, live = 0, not card.closed
        respoken = False
        # A same-ID finish can take back words beyond another caption on
        # this card. The translation and its link offsets belong to all
        # of that caption's words here, even when dealt in separate runs.
        by_caption: dict[CaptionId, list[Word]] = {}
        for caption, word in card.words:
            by_caption.setdefault(caption, []).append(word)
        for caption, words in by_caption.items():
            first = words[0]
            said = "".join(w.text + (" " if w.space else "") for w in words).rstrip()
            lit = [w for w in words if not w.ahead]
            established += (
                len("".join(w.text + (" " if w.space else "") for w in lit).rstrip())
                if len(lit) < len(words)
                else len(said)
            )
            update = self._latest.get(caption)
            if update is None:
                clauses.append(Clause(said))
                continue
            respoken = respoken or update.respoken
            live = live or update.kind is not CaptionKind.FINISHED
            language = language or update.language
            heard += [each for each in update.languages_heard if each not in heard]
            source = (
                update.clauses[first.clause]
                if first.clause < len(update.clauses)
                else None
            )
            mine = self._placed.get(caption, [])
            offset = 0  # where this card's words start in the caption's shown words
            for _, word in mine:
                if word is first:
                    break
                offset += len(word.text) + word.space
            synced = all(word.synced for _, word in mine)
            translations: dict[Language, str] = {}
            links: dict[Language, tuple[WordLink, ...]] = {}
            for (owner, target), (text, start) in card.lit.items():
                if owner != caption or not text:
                    continue
                translations[target] = text
                whole = self._whole.get((caption, target))
                if whole is None or not synced:
                    continue
                if card.translations.get((owner, target)) != (text, start):
                    continue  # an older text still shown: its links went
                room = len(text.rstrip(ELLIPSIS))
                found = []
                for link in whole[1]:
                    o = (link.original[0] - offset, link.original[1] - offset)
                    t = (link.translation[0] - start, link.translation[1] - start)
                    if o[0] >= 0 and o[1] <= len(said) and t[0] >= 0 and t[1] <= room:
                        found.append(replace(link, original=o, translation=t))
                if found:
                    links[target] = tuple(found)
            clauses.append(
                Clause(
                    said,
                    translations,
                    links,
                    dict(source.written_in) if source is not None else {},
                )
            )
        if card.named is None:  # as first shown: a label never comes or goes
            card.named = (
                language or cause.language,
                tuple(heard) or cause.languages_heard,
            )
        return CaptionUpdate(
            self.card_id(card),
            card.source,
            CaptionKind.LIVE if live else CaptionKind.FINISHED,
            clauses=tuple(clauses),
            language=card.named[0],
            languages_heard=card.named[1],
            established=established if live else 0,
            respoken=respoken,
            display_member=cause.display_member,
        )


class Glide:
    """The stack's one motion: how far below its place it is drawn (`px`),
    following a critically damped spring to rest. A push while it moves
    adds to how far it has to go and keeps its speed, so a burst of cards
    is one glide; from rest it starts gently; it never passes its place,
    so nothing comes back. Scrolling back, it is drawn above its place
    (`px` negative) and comes down to it the same way."""

    def __init__(self, omega: float = 8.0) -> None:
        self.omega = omega
        """A step is within 2 % of its place after about 5.8 / omega
        seconds (8: 0.7 s, most of the way in 0.4: slow and smooth)."""
        self.px = 0.0
        self.speed = 0.0
        self._w = omega
        self._at: float | None = None

    def push(self, now: float, px: float, most: float | None = None) -> None:
        """The stack's place rose `px`: that much further to go - never
        more than `most` in all: a burst of cards isn't followed from
        below the window."""
        self.to(now)
        self.px += px
        if most is not None and abs(self.px) > most:
            self.px = math.copysign(most, self.px)
        # From rest, the spring's peak speed is distance * w / e. At the
        # speed limit, distance * w <= 2 * limit keeps it from accelerating
        # further. Interpolate between those bounds for the speed it kept.
        limit = GLIDE_FASTEST.value
        spare = max(0.0, limit - abs(self.speed))
        distance = max(1.0, abs(self.px))
        max_rate = (2.0 * limit + (math.e - 2.0) * spare) / distance
        self._w = min(self.omega, max_rate)

    def to(self, now: float) -> float:
        """The spring at `now`: how far below its place the stack is."""
        dt = 0.0 if self._at is None else max(0.0, now - self._at)
        self._at = now
        if dt and (self.px or self.speed):
            w = self._w
            decay = math.exp(-w * dt)
            a = self.speed + w * self.px
            was = self.px
            self.px, self.speed = (
                (self.px + a * dt) * decay,
                (self.speed - w * a * dt) * decay,
            )
            passed = was * self.px < 0.0
            if passed or (abs(self.px) < 0.25 and abs(self.speed) < 2.0):
                self.px = self.speed = 0.0
        return self.px

    def moving(self, now: float) -> bool:
        return self.to(now) != 0.0

    def stop(self) -> None:
        self.px = self.speed = 0.0


COMING_SEC = 4.0
"""A caption heard this long ago and never shown isn't coming."""
GLIDE_FASTEST = tunable(
    "cards.glide_fastest",
    300.0,
    "pixels/s",
    (100.0, 600.0),
    source="552 card stack; 583 depth",
)
"""Px a second: the stack never glides faster, however far it has to go."""

FLAT_SHARE = tunable(
    "cards.flat_share", 0.55, "fraction", (0.3, 0.9), source="552 card stack; 583 depth"
)
"""The foot of the window, as a share of its height, where cards are flat
and full: the one being written and those still being read."""
FAR_INK = tunable(
    "cards.far_ink", 0.3, "fraction", (0.15, 1.0), source="552 card stack; 583 depth"
)
"""A card's ink at the far end, where it leaves: fainter all the way up,
never an empty band while earlier cards exist."""
GONE_AT = 1.15
"""Radians a card has turned at the far end, the view's top edge."""
SMEAR = 0.4
"""A card squashed to less than this isn't drawn: its text would be a smear."""
FLAT_ENOUGH = 0.95
"""A card the drum squashes less than this (0.967 for Video's older card,
0.986 for Everyday's second, at rest) is drawn flat at its place: a squash
so slight only softened its text (584)."""


def drum(top: float, height: float, view: float) -> tuple[float, float, float]:
    """Where a card whose top is at `top` (in a flat list `view` tall, 0
    its top edge; negative: above it) is drawn on the drum, for a card
    `height` tall: its top, how much it is squashed (1.0 flat) and its ink
    (1.0 full, 0.0 gone). Flat in the foot of the view; above that it
    turns away - closer together, flatter, fainter (`FAR_INK` at the far
    end) - and leaves over the view's top edge, the only way a card ever
    goes. Each edge of a card is turned by itself, so a
    card's foot stays on the top of the card under it."""
    flat = view * (1.0 - FLAT_SHARE.value)  # what is below this is flat
    if top >= flat or flat <= 0.0 or height <= 0.0:
        return top, 1.0, 1.0
    radius = flat / math.sin(GONE_AT)

    def turned(y: float) -> float:
        if y >= flat:
            return y
        return flat - radius * math.sin(min(GONE_AT, (flat - y) / radius))

    if (flat - top - height) / radius >= GONE_AT:
        return 0.0, 0.0, 0.0  # all of it past the far end
    at, foot = turned(top), turned(top + height)
    middle = min(GONE_AT, max(0.0, (flat - top - height / 2.0) / radius))
    ink = 1.0 - (1.0 - FAR_INK.value) * middle / GONE_AT
    return at, min(1.0, max(0.0, (foot - at) / height)), ink


DEPTH_SCALES = tunable(
    "cards.depth_scales",
    (1.0, 0.9, 0.8),
    "fraction",
    (0.8, 1.0),
    source="552 card stack; 583 depth",
)
"""Subtitles that recede (Video; polyglotic-hq 583, the user, 2026-11-21:
"instead of rolling up, I want it to go deeper into the screen, so
they're still readable"): the newest card's text size, then each older
card's, as a share of the window's - each laid out again at it, never a
picture scaled. Video draws as many cards as there are steps. 0.8 at the
back: 585's reading rules (provisional, 2026-11-21) count a card as
readable at 0.8 of its height or more, and 0.6 of its ink."""
DEPTH_INK = tunable(
    "cards.depth_ink",
    (1.0, 0.86, 0.74),
    "fraction",
    (0.6, 1.0),
    source="552 card stack; 583 depth",
)
"""How much of its colour each step keeps, the rest mixed towards what is
behind its letters (`caption_window.receded_ink`): never under 4.5:1."""
DEPTH_SEC = tunable(
    "cards.depth", 0.3, "seconds", (0.15, 0.8), source="552 card stack; 583 depth"
)
"""One new card: the cards step back together in this long, eased - or
longer, so no card goes faster than `GLIDE_FASTEST` at the step's peak
(583's Video film: Video's 130 px cards stepping back in 0.3 s were 27
jumps of 360 px a second or more)."""
DEPTH_RISE = tunable(
    "cards.depth_rise", 0.25, "fraction", (0.0, 1.0), source="552 card stack; 583 depth"
)
"""A new card comes up into its place from this share of its height below,
as it fades in."""
DEPTH_WIDTH_SPARE = tunable(
    "cards.depth_width_spare",
    1.04,
    "factor",
    (1.0, 1.25),
    source="552 card stack; 583 depth",
)
"""A card stepped back is laid out this much wider than in proportion to
its size: a smaller font is never quite in proportion, and a card keeps
its rows at every step."""


EASE_PEAK = 1.5
"""`ease`'s fastest, as a share of the average speed."""


def ease(share: float) -> float:
    """Eased in and out (smoothstep): 0 at 0, 1 at 1, gentle at both ends,
    `EASE_PEAK` times the average speed at its fastest."""
    x = min(1.0, max(0.0, share))
    return x * x * (3.0 - 2.0 * x)


class Depth:
    """How far the cards still have to step back (`behind`, in steps):
    1 when a card has just come, eased to 0 over `DEPTH_SEC`. A card that
    comes while they step back adds its step to what is left, so nothing
    jumps. Plain numbers: the window draws each card `place` steps back."""

    def __init__(self) -> None:
        self._from = 0.0
        self._at = -1e9
        self._sec = DEPTH_SEC.value

    def came(self, now: float, px: float = 0.0) -> None:
        """A new card: every card steps back one more."""
        self.shift(now, 1, px)

    def shift(self, now: float, steps: int, px: float = 0.0) -> None:
        """The cards drawn moved `steps` places back - forward if negative:
        a card in front of them went - from where they stand now; `px` the
        most any card moves for one step, which sets how long it takes."""
        if not steps:
            return
        self._from = max(-2.0, min(2.0, self.behind(now) + steps))
        self._at = now
        fastest = EASE_PEAK * px * abs(self._from) / GLIDE_FASTEST.value
        self._sec = max(DEPTH_SEC.value, fastest)

    def behind(self, now: float) -> float:
        if not self._from:
            return 0.0
        share = (now - self._at) / self._sec
        if share >= 1.0:
            self._from = 0.0
            return 0.0
        return self._from * (1.0 - ease(share))

    def moving(self, now: float) -> bool:
        return self.behind(now) > 0.0

    def stop(self) -> None:
        self._from = 0.0

    @staticmethod
    def moved(before: Sequence[int], now: Sequence[int]) -> int:
        """How many places back the cards drawn `before` (keys, the newest
        first) stand `now`: by the first of them still drawn - 0 when a
        card was dealt again in its place, below 0 when one in front went."""
        for at, key in enumerate(before):
            if key in now:
                return list(now).index(key) - at
        return 0

    def place(self, back: int, now: float) -> float:
        """Where card `back` (0 the newest) is drawn now, in steps back:
        below 0 while the newest comes in."""
        return back - self.behind(now)


def depth_scale(place: float) -> float:
    """The text size, as a share, of a card `place` steps back: between
    `DEPTH_SCALES`' steps, and on past the last at its rate, as a card
    leaves from the back. A card coming in (below 0) is full size."""
    if place <= 0.0:
        return 1.0
    return _between(DEPTH_SCALES.value, place)


def depth_ink(place: float) -> float:
    """How much of its colour a card `place` steps back keeps."""
    if place <= 0.0:
        return 1.0
    return _between(DEPTH_INK.value, place)


def depth_alpha(place: float, cards: int) -> float:
    """How solid a card `place` steps back is, with `cards` drawn: fading
    in at the front while it comes (below 0) and out past the last."""
    if place < 0.0:
        return max(0.0, 1.0 + place)
    return max(0.0, min(1.0, cards - place))


def _between(steps: tuple[float, ...], place: float) -> float:
    last = len(steps) - 1
    if place >= last:
        rate = steps[last] / steps[last - 1] if last else 1.0
        return steps[last] * rate ** (place - last)
    low = int(place)
    share = place - low
    return steps[low] + (steps[low + 1] - steps[low]) * share


def drum_room(view: float) -> float:
    """How much more of a flat list a drum `view` px tall shows than the
    view itself would: what turns away above its flat part."""
    flat = view * (1.0 - FLAT_SHARE.value)
    if flat <= 0.0:
        return 0.0
    return flat / math.sin(GONE_AT) * GONE_AT - flat
