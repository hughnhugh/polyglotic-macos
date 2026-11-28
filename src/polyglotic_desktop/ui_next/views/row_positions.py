"""Vertical placement of live caption rows between deliberate viewport changes."""

from collections.abc import Iterator, Mapping
from difflib import SequenceMatcher


def row_tops[K](natural: dict[K, float], previous: Mapping[K, float]) -> dict[K, float]:
    """Fit new rows into gaps left by edits, preserving the order and row pitches.

    A retained row bounds its own top. A new row follows the preceding row
    into any available gap. Work back from the foot so a bound on a lower
    row also makes room above it. Rows sharing a baseline move together.
    """
    if not previous or not natural:
        return natural
    if all(previous.get(k, y) >= y for k, y in natural.items()):
        return natural
    offsets: dict[float, float] = {}
    carry = 0.0
    ordered = sorted(natural, key=natural.__getitem__)
    for key in ordered:
        y = natural[key]
        if key in previous:
            carry = min(0.0, previous[key] - y)
        carry = offsets[y] = min(offsets.get(y, 0.0), carry)
    lift = 0.0
    for y in reversed(offsets):
        lift = offsets[y] = min(lift, offsets[y])
    return {k: y + offsets[y] for k, y in natural.items()}


def moved_characters[K](
    old: str, sources: list[K], new: str, destinations: list[K]
) -> Iterator[tuple[K, K]]:
    """Surviving characters whose row changed, including across a clause split."""
    common = min(len(old), len(new))
    if old[:common] == new[:common]:
        blocks = [(0, 0, common)]  # ordinary appends and truncations
    else:
        blocks = [
            (a, b, n)
            for a, b, n in SequenceMatcher(
                None, old, new, autojunk=False
            ).get_matching_blocks()
        ]
    for a, b, length in blocks:
        for source, dest in zip(
            sources[a : a + length], destinations[b : b + length], strict=True
        ):
            if source != dest:
                yield source, dest
