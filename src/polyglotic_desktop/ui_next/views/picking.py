"""Words picked together in a list, as a file manager picks files
(polyglotic-hq 342; the user, 2026-11-15: "shift clicking range"). Plain
Python, for a list drawn as rows of widgets (the learning load's card);
Words' tables use Qt's own selection, which does the same.

- a click picks one word, and is where a Shift-click picks from;
- Shift picks every word from there to the one clicked;
- Ctrl adds a word, or takes it away;
- with the keyboard, the arrows move, Shift and an arrow pick as they go,
  Space picks or lets go, Ctrl+A picks all, Esc lets go of all.

Words are kept by their keys (entry IDs), not their rows: the list is
shown again as captions come in, its words in another order or gone, and
what's picked stays picked where it's still listed (`keep`).
"""

from collections.abc import Sequence


class Picking:
    """What's picked in one list, and where a Shift-click picks from."""

    def __init__(self) -> None:
        self.picked: set[str] = set()
        self.anchor: str | None = None
        """Where Shift picks from: the last word clicked without Shift."""
        self.current: str | None = None
        """The word the keyboard is on."""

    def click(
        self, key: str, order: Sequence[str], shift: bool = False, ctrl: bool = False
    ) -> None:
        """A click on `key` in the list `order`, with Shift or Ctrl held."""
        if shift and self.anchor in order:
            self.picked = set(_between(order, self.anchor, key))
        elif ctrl:
            self.picked ^= {key}
            self.anchor = key
        else:
            self.picked = {key}
            self.anchor = key
        self.current = key

    def move(self, step: int, order: Sequence[str], shift: bool = False) -> None:
        """An arrow: the keyboard's word `step` rows on (or the first);
        with Shift, every word from the anchor to it picked."""
        if not order:
            return
        at = order.index(self.current) + step if self.current in order else 0
        key = order[max(0, min(len(order) - 1, at))]
        if shift:
            if self.anchor not in order:
                self.anchor = self.current if self.current in order else key
            self.picked = set(_between(order, self.anchor, key))
            self.current = key
        else:
            self.current = key

    def toggle(self) -> None:
        """Space: the keyboard's word picked, or let go."""
        if self.current is not None:
            self.picked ^= {self.current}
            self.anchor = self.current

    def all(self, order: Sequence[str]) -> None:
        self.picked = set(order)

    def clear(self) -> None:
        self.picked = set()

    def keep(self, order: Sequence[str]) -> None:
        """The list shown again as `order`: only what's still listed stays."""
        listed = set(order)
        self.picked &= listed
        if self.anchor not in listed:
            self.anchor = None
        if self.current not in listed:
            self.current = None

    def in_order(self, order: Sequence[str]) -> list[str]:
        """What's picked, in the list's order."""
        return [key for key in order if key in self.picked]


def _between(order: Sequence[str], start: str | None, end: str) -> Sequence[str]:
    a = order.index(start) if start in order else order.index(end)
    b = order.index(end)
    return order[min(a, b) : max(a, b) + 1]
