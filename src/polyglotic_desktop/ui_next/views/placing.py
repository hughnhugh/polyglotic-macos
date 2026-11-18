"""Where a line's parts go when they needn't be packed to the left
(polyglotic-hq 458; the user, 2026-11-17: "placing characters in such a
way to reducing distance between all arrow length sums ... a 3rd alternate
lab mode could be clean even space everything").

The parts of a line keep their order and never overlap, so a part can
only be pushed right of where the packed line has it: part `i`'s shift
`y[i]` obeys `0 <= y[0] <= y[1] <= ... <= most`. Each part wants the
shifts that would put one of its linked words right over (or under) its
counterpart; the total length of the links, across, is the sum of
`|y[i] - want|` over every part's wants.

`nearest` finds the shifts with the least total: isotonic regression in
the L1 norm ("isotonic median regression"), solved exactly by pooling
adjacent violators - a run of parts that would cross is moved as one
block, to a median of all its wants (Chakravarti, "Isotonic median
regression: a linear programming approach", Mathematics of Operations
Research 14(2), 1989; Stout's survey of the bounds: n log n on a line).
It is also a row of cells placed in a fixed order for the least wire
length (Brenner and Vygen, "Faster optimal single-row placement with
fixed ordering", DATE 2000, pp. 117-121). A line has a dozen parts at
most, so the pooling here is the plain one, sorting each block again.
Where the medians are a range, the block takes the point of it nearest
the mean of its wants (the least sum of squares among the least sums),
so a part with two links sits between them. Clipping the answer to
`[0, most]` keeps it the best one inside those bounds
(`tests/ui_next/test_parts_placed.py` checks it against every placing
on a grid).

Plain Python; holds nothing.
"""

from collections.abc import Sequence


def _middle(pooled: list[float]) -> float:
    """The median of `pooled` (sorted) nearest its mean."""
    count = len(pooled)
    low, high = pooled[(count - 1) // 2], pooled[count // 2]
    return min(max(sum(pooled) / count, low), high)


def nearest(wants: Sequence[Sequence[float]], most: float) -> list[float]:
    """Each part's shift, left to right: no less than the part before's,
    all within `[0, most]`, the least total distance from every part's
    `wants`. A part with none goes evenly between its neighbours that
    have some - before the first of them, between the line's start and
    it; after the last, it stays with it."""
    most = max(0.0, most)
    blocks: list[tuple[list[float], float, list[int]]] = []
    for index, wanted in enumerate(wants):
        if not wanted:
            continue
        pooled = sorted(wanted)
        blocks.append((pooled, _middle(pooled), [index]))
        while len(blocks) > 1 and blocks[-2][1] > blocks[-1][1]:
            later = blocks.pop()
            earlier = blocks.pop()
            pooled = sorted(earlier[0] + later[0])
            blocks.append((pooled, _middle(pooled), earlier[2] + later[2]))
    found: list[float | None] = [None] * len(wants)
    for _, value, members in blocks:
        for index in members:
            found[index] = min(max(value, 0.0), most)
    return _between(found)


def _between(found: list[float | None]) -> list[float]:
    """`found` with each None filled evenly between the values around it."""
    filled: list[float] = []
    before, at = 0.0, 0
    while at < len(found):
        value = found[at]
        if value is not None:
            filled.append(value)
            before = value
            at += 1
            continue
        end = at
        while end < len(found) and found[end] is None:
            end += 1
        after = found[end] if end < len(found) else None
        count = end - at
        for n in range(count):
            if after is None:
                filled.append(before)
            else:
                filled.append(before + (after - before) * (n + 1) / (count + 1))
        at = end
    return filled


def evenly(count: int, room: float, after_text: bool = False) -> list[float]:
    """The shifts that spread `count` parts over a line with `room` to
    spare, the gaps between them all growing alike: the first stays (or,
    `after_text`, has a gap before it too - the line already holds the
    caption before's text), the last reaches the line's end."""
    gaps = count - 1 + (1 if after_text else 0)
    if count <= 0 or gaps <= 0 or room <= 0.0:
        return [0.0] * max(0, count)
    first = 1 if after_text else 0
    return [room * (n + first) / gaps for n in range(count)]
