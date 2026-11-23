"""One model of a caption: its words, its word links and where it may be
cut - built once from the server's clauses, for every layout to lay out
(polyglotic-hq 340, decision 0132; the user, 2026-11-15: "processed data
and word linkages should be catered to the caption window and caption
window is dynamic").

Each feature read the server's clauses its own way: the clause rows
numbered a clause's links from 0, the pour cut the text into words of its
own, the cuts for line-by-line were worked out beside the rows, and the
card's counterpart read the raw links again. Here it is done once. This
is the first step of 340's migration (docs/caption-model.md): the model
is here and tested, and `ui_next.views.pour` takes its units and its
matching cuts from it; the layouts move onto it in the steps after.

- **A place** (`Words`): characters `[start, end)` of one clause's text on
  one side - what was said, or its translation. Everything that points at
  caption text - a link's end, the word under the mouse, a mark, a line's
  run - is a place, whatever the layout.
- **Units** (`units`): the pieces of a clause's text a line is never
  broken inside - a word of a spaced language, a character of Chinese,
  Japanese or Thai with the punctuation that stays with it. Cut once per
  clause, kept while the clause is the same.
- **Links** (`Link`): numbered across the whole caption, in reading order,
  so no two links of a caption share a number - and a clause that comes
  later never renumbers the ones before. One link per counterpart, as
  `display.numbered_links` groups them; every link the server sent is here,
  key or minor - which of them are drawn is asked of the model
  (`shown_links`).
- **Parts** (`ClauseModel.cuts`): where a settled clause and its
  translation can both be cut so each part of one says what the same part
  of the other does (`matching_cuts`).
- **Settled** (`ClauseModel.settled`): every clause but a live caption's
  last - its words can still change, so it has no links and no cuts yet.

Built by `caption_model`; given the model built for the caption's last
version, a clause that didn't change keeps its `ClauseModel` - the very
object - so what a layout measured for it is kept through live updates.

A word's learning state (known, in the load, saved) isn't here: that is
the learning context's, laid over the same places by the interface.
Plain values, no Qt. Holds caption text: never log it.
"""

import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.listening.captions import Clause, Language, WordClass
from polyglotic_desktop.core.listening.display import (
    GroupedLink,
    LinkDetail,
    RowKind,
    TranslationShown,
    group_links,
    translation_shown,
)
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

Span = tuple[int, int]
Unit = tuple[int, int, int]
"""A piece of text a line is never broken inside: `text[start:end]`, and
`text[end:after]` the spaces after it."""

NO_START = frozenset(
    "，。、！？；：）」』】》〉’”,.!?;:)]}%…—～・ー々っゃゅょァィゥェォッャュョ"
)
"""Characters a line never starts with: they stay with the one before."""
NO_END = frozenset("（「『【《〈‘“([{")
"""Characters a line never ends with: they stay with the one after."""
ELLIPSIS = "…"


def wide(char: str) -> bool:
    """A character of a script written without spaces between words: a
    line may end after any of them."""
    return (
        "⺀" <= char <= "鿿"
        or "豈" <= char <= "﫿"
        or "＀" <= char <= "￯"
        or "฀" <= char <= "໿"  # Thai, Lao
    )


def units(text: str) -> tuple[Unit, ...]:
    """`text` as the pieces a line is never broken inside, covering it end
    to end; a trailing ellipsis stays with the last word."""
    starts = [0]
    for at in range(1, len(text)):
        char, before = text[at], text[at - 1]
        if char.isspace():
            continue
        if (
            before.isspace()
            or (wide(before) or wide(char))
            and not (char in NO_START or before in NO_END)
        ):
            starts.append(at)
    found: list[Unit] = []
    for start, after in zip(starts, [*starts[1:], len(text)], strict=True):
        end = after
        while end > start and text[end - 1].isspace():
            end -= 1
        if found and text[start:end] == ELLIPSIS:
            found[-1] = (found[-1][0], end, after)
            continue
        found.append((start, end, after))
    if len(found) > 1 and found[0][1] == found[0][0]:  # only spaces first
        found[1] = (0, found[1][1], found[1][2])
        del found[0]
    return tuple(found)


def matching_cuts(
    original: str,
    translation: str,
    links: Sequence[tuple[Span, Span]],
    original_units: Sequence[Unit] | None = None,
    translation_units: Sequence[Unit] | None = None,
) -> tuple[tuple[int, int], ...]:
    """Where a clause and its translation can both be cut so that each
    part of one says what the same part of the other says: (p, q) - before
    character `p` of the original and `q` of the translation, each the
    start of a unit - such that every word link lies wholly before both or
    wholly after both. None where the links cross, where a link straddles
    the place, or where one side has no linked word to go by. In order,
    each further on in both. Words with no link between two cuts' linked
    words go with the words after them (an article, a preposition) - or,
    in a script written without spaces, with those before (了, 的)."""
    spans = [
        (a, b, c, d)
        for (a, b), (c, d) in links
        if 0 <= a < b <= len(original) and 0 <= c < d <= len(translation)
    ]
    if len(spans) < 2:
        return ()
    if original_units is None:
        original_units = units(original)
    if translation_units is None:
        translation_units = units(translation)
    starts = [start for start, _, _ in translation_units]
    cuts: list[tuple[int, int]] = []
    for p, _, _ in original_units[1:]:
        if any(a < p < b for a, b, _, _ in spans):
            continue  # inside a linked word
        before = [d for _, b, _, d in spans if b <= p]
        after = [c for a, _, c, _ in spans if a >= p]
        if not before or not after or max(before) > min(after):
            continue  # nothing to go by, or the links cross here
        low, high = max(before), min(after)
        between = [s for s in starts if low <= s <= high]
        if not between:
            continue
        q = between[-1] if wide(translation[high]) else between[0]
        if cuts and q == cuts[-1][1] and wide(original[p]):
            cuts[-1] = (p, q)  # the same place: its 了 stays with it
        elif q > (cuts[-1][1] if cuts else 0):
            cuts.append((p, q))
    return tuple(cuts)


@dataclass(frozen=True, slots=True)
class Words:
    """A place in a caption: characters `[start, end)` of clause `clause`'s
    text on `side`."""

    side: RowKind
    clause: int
    start: int
    end: int
    pos: WordClass | None = None

    def meets(self, other: "Words") -> bool:
        return (
            self.side is other.side
            and self.clause == other.clause
            and self.start < other.end
            and other.start < self.end
        )


@dataclass(frozen=True, slots=True)
class Link:
    """Words of what was said and of its translation that say the same
    thing. `number` is the link's in the whole caption, in reading order -
    a layout pairs its ends by number. `original` can be several places (a word
    said twice for the same thing). `key`: content words, not a pronoun or
    a particle; `confidence` from 0 to 1 (the surest of its pairs)."""

    number: int
    key: bool
    confidence: float
    original: tuple[Words, ...]
    translation: tuple[Words, ...]

    def meets(self, words: Words) -> bool:
        """Whether one of its ends shares a character with `words`."""
        ends = self.original if words.side is RowKind.ORIGINAL else self.translation
        return any(end.meets(words) for end in ends)


@dataclass(frozen=True, slots=True, eq=False)
class ClauseModel:
    """A clause as every layout reads it: its texts, their units, its
    links and where both sides can be cut. `translation` None: not
    translated into the language shown (or not yet). `settled`: not a live
    caption's last clause. Compared by identity: a layout keeps what it
    measured for as long as the caption keeps the very object."""

    original: str
    translation: str | None
    language: Language | None
    """The translation's language (the target, or the second language) -
    what it is written in, for its font and reading line."""
    settled: bool
    original_units: tuple[Unit, ...]
    translation_units: tuple[Unit, ...]
    pairs: tuple[GroupedLink, ...]
    cuts: tuple[tuple[int, int], ...]
    source: Clause

    def text(self, side: RowKind) -> str:
        if side is RowKind.ORIGINAL:
            return self.original
        return self.translation or ""

    def units(self, side: RowKind) -> tuple[Unit, ...]:
        if side is RowKind.ORIGINAL:
            return self.original_units
        return self.translation_units

    @property
    def parts(self) -> tuple[tuple[Span, Span], ...]:
        """The clause as the parts both sides can be cut into: each the
        original's characters and the translation's."""
        ends = len(self.original), len(self.translation or "")
        bounds = [(0, 0), *self.cuts, ends]
        return tuple(((p, r), (q, s)) for (p, q), (r, s) in itertools.pairwise(bounds))


@dataclass(frozen=True, slots=True, eq=False)
class CaptionModel:
    """A caption as every layout reads it. `key` is the caption history's:
    the same through its updates and joins."""

    key: int
    caption_id: CaptionId
    source: SourceId
    by_you: bool
    live: bool
    language: Language | None
    clauses: tuple[ClauseModel, ...]
    links: tuple[Link, ...]

    def text(self, words: Words) -> str:
        return self.clauses[words.clause].text(words.side)[words.start : words.end]

    def links_at(self, words: Words) -> tuple[Link, ...]:
        """The links with an end on `words`."""
        return tuple(link for link in self.links if link.meets(words))

    def shown_links(
        self, detail: LinkDetail = LinkDetail.MOST, cap: int | None = None
    ) -> Iterator[Link]:
        """The links a layout draws: with "key words", key links only;
        with `cap`, each clause's surest - key links first."""
        per_clause: dict[int, list[Link]] = {}
        for link in self.links:
            if detail is LinkDetail.KEY and not link.key:
                continue
            per_clause.setdefault(link.translation[0].clause, []).append(link)
        for found in per_clause.values():
            if cap is not None and len(found) > cap:
                surest = sorted(found, key=lambda k: (not k.key, -k.confidence))[:cap]
                found = sorted(surest, key=lambda k: k.number)
            yield from found


def caption_model(
    caption: Caption,
    target: Language | None,
    second: Language | None = None,
    previous: CaptionModel | None = None,
) -> CaptionModel:
    """`caption` as its model, translated into `target` - or, for a clause
    already in it, into `second`; None: captions only. `previous`: the
    model built for this caption's last version - its clauses that didn't
    change are kept as they are."""
    kept = previous.clauses if previous is not None else ()
    last = len(caption.clauses) - 1
    clauses: list[ClauseModel] = []
    for n, clause in enumerate(caption.clauses):
        settled = not (caption.live and n == last)
        shown = (
            translation_shown(clause, caption.language, target, second)
            if target is not None
            else None
        )
        language = shown.language if shown is not None else target
        translation = shown.text if shown is not None else None
        old = kept[n] if n < len(kept) else None
        if (
            old is not None
            and old.source is clause
            and old.settled == settled
            and old.language == language
            and old.translation == translation
        ):
            clauses.append(old)
        else:
            clauses.append(_clause_model(clause, shown, target, settled))
    links: list[Link] = []
    for n, model in enumerate(clauses):
        for pairs in model.pairs:
            links.append(
                Link(
                    len(links),
                    pairs.key,
                    pairs.confidence,
                    tuple(
                        Words(RowKind.ORIGINAL, n, a, b, pos)
                        for (a, b), pos in zip(
                            pairs.original, pairs.original_pos, strict=True
                        )
                    ),
                    (
                        Words(
                            RowKind.TRANSLATION,
                            n,
                            *pairs.translation,
                            pairs.translation_pos,
                        ),
                    ),
                )
            )
    return CaptionModel(
        caption.key,
        caption.caption_id,
        caption.source_id,
        caption.by_you,
        caption.live,
        caption.language,
        tuple(clauses),
        tuple(links),
    )


def _clause_model(
    clause: Clause,
    shown: TranslationShown | None,
    target: Language | None,
    settled: bool,
) -> ClauseModel:
    """`shown`: its translation as the window shows it (None: none);
    `target`: the window's."""
    translation = shown.text if shown is not None else None
    original_units = units(clause.original)
    translation_units = units(translation) if translation else ()
    pairs: tuple[GroupedLink, ...] = ()
    cuts: tuple[tuple[int, int], ...] = ()
    if settled and shown is not None and translation:
        sent = clause.links.get(shown.target, ())
        groups = group_links(sent, len(clause.original), len(translation))
        pairs = tuple(
            sorted(groups, key=lambda pair: (pair.original[0], pair.translation))
        )
        cuts = matching_cuts(
            clause.original,
            translation,
            [(k.original, k.translation) for k in sent],
            original_units,
            translation_units,
        )
    return ClauseModel(
        clause.original,
        translation,
        shown.language if shown is not None else target,
        settled,
        original_units,
        translation_units,
        pairs,
        cuts,
        clause,
    )
