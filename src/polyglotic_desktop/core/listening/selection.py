"""What the learner dragged across in a caption window, as places in its
captions (polyglotic-hq 340's design, built in 358; the user, 2026-11-15:
"I want drag and select and ctrl c / right click to copy. Should be able
to freely copy all texts across all caption interface").

- **A place** (`Place`): a point in a window's captions - before a
  character of one clause's text on one side, in the caption with the
  history's key. Never a line or a pixel on the screen.
- **A selection** (`Selection`): from the place the drag began to the
  place it is. Both on one side: that side's words between them, across
  clauses and captions. One on each side: both sides of every clause
  between, whole.
- **What it holds** (`selected`) is asked of the captions as they are now,
  so it is the same words after a resize, in another layout, and when its
  captions grow; a caption withdrawn or gone from the window has none.
- **Its text** (`selected_text`): a caption a line - two, what was said
  and then its translation, when both sides are held - its clauses joined
  as the transcript joins them (decision 0126).

Works on any captions that give a key and each clause's text by side
(`CaptionText`): the caption model does (`caption_model.CaptionModel`),
and so do the rows a window shows. Plain values, no Qt. Holds caption
text: never log it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.history import join_text


class ClauseText(Protocol):
    """A clause's text on each side ("" for none)."""

    def text(self, side: RowKind) -> str: ...


class CaptionText(Protocol):
    """A caption's key (the caption history's) and its clauses."""

    @property
    def key(self) -> int: ...

    @property
    def clauses(self) -> Sequence[ClauseText]: ...


@dataclass(frozen=True, slots=True, order=True)
class Place:
    """Before character `char` of clause `clause`'s text on `side`, in the
    caption with the history's key `caption`. Ordered as they are read:
    by caption, clause, character."""

    caption: int
    clause: int
    char: int
    side: RowKind = RowKind.ORIGINAL


@dataclass(frozen=True, slots=True)
class Selection:
    """From `anchor` (where the drag began) to `focus` (where it is)."""

    anchor: Place
    focus: Place

    @property
    def one_clause(self) -> bool:
        """Within one clause's text on one side: a phrase - what a lookup
        can be made of."""
        a, b = self.anchor, self.focus
        return (a.caption, a.clause, a.side) == (b.caption, b.clause, b.side)

    @property
    def both_sides(self) -> bool:
        return self.anchor.side is not self.focus.side


def selected(
    captions: Sequence[CaptionText], selection: Selection
) -> list[tuple[int, Words]]:
    """The words `selection` holds now, in reading order: each the key of
    its caption and a place in it. Clipped to what the captions hold - a
    caption withdrawn or gone has none, a clause rewritten shorter ends
    where its text does. `captions` oldest first."""
    first, last = sorted((selection.anchor, selection.focus))
    both = selection.both_sides
    sides = (
        (RowKind.ORIGINAL, RowKind.TRANSLATION) if both else (selection.anchor.side,)
    )
    begin, end_at = (first.caption, first.clause), (last.caption, last.clause)
    found: list[tuple[int, Words]] = []
    for caption in captions:
        if not first.caption <= caption.key <= last.caption:
            continue
        for n, clause in enumerate(caption.clauses):
            at = (caption.key, n)
            if not begin <= at <= end_at:
                continue
            for side in sides:
                text = clause.text(side)
                start, end = 0, len(text)
                if not both and at == begin:
                    start = min(first.char, end)
                if not both and at == end_at:
                    end = min(last.char, end)
                if start < end:
                    found.append((caption.key, Words(side, n, start, end)))
    return found


def selected_text(captions: Sequence[CaptionText], selection: Selection) -> str:
    """`selection` as text to copy: each caption on a line of its own - or
    two, what was said and then its translation, when it holds both
    sides - its clauses joined as the transcript joins them."""
    by_key = {caption.key: caption for caption in captions}
    lines: dict[tuple[int, RowKind], list[str]] = {}
    for key, words in selected(captions, selection):
        text = by_key[key].clauses[words.clause].text(words.side)
        lines.setdefault((key, words.side), []).append(text[words.start : words.end])
    return "\n".join(
        joined for pieces in lines.values() if (joined := join_text(pieces))
    )
