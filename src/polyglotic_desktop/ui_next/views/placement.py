"""Where a caption window goes, and how it moves and resizes - plain
geometry, no Qt (polyglotic-hq project 109's structure, 10.1 and 10.3).

Sizes are logical pixels. A window has a **position preset** - an anchor
and an alignment: Bottom left, Bottom centre, Top centre - or is "where I
put it" (`CUSTOM`), which only a drag that doesn't snap makes it.

- **Resizing** moves the edges dragged and nothing else: the opposite edge
  or corner stays put, so a window hugging the bottom of the screen never
  grows off it (108's bug 2). A centred preset resizes both sides equally,
  so it stays centred and keeps its preset; a resize never changes the
  preset. The drag stops at the minimum size and at the work area's edge.
- **Moving** is clamped to the work area. Within `SNAP` pixels of a
  preset's place the window snaps there and takes that preset; dropped
  anywhere else it is "where I put it".
- **At the start** a saved place whose centre is on no screen goes back to
  its preset; one partly off a screen is pulled back onto it.

- **A joined window** (109's 2a, 10.6) takes the place and height of the
  window the command came from and the windows' widths together, clamped
  to the screen; its width divides equally between its columns, each at
  least `MIN_COLUMN` wide.

The Qt window finds the work area (the screen holding the window's centre,
the taskbar excluded) and hands it in; nothing here knows about screens.
"""

from dataclasses import dataclass
from enum import IntFlag, StrEnum


@dataclass(frozen=True, slots=True)
class Rect:
    """A rectangle: its top left corner and its size. `right` and `bottom`
    are one past its last pixel."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def holds(self, x: float, y: float) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]


class Preset(StrEnum):
    """Where a window is put: an anchor and an alignment, or `CUSTOM` -
    "Where I put it"."""

    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTRE = "bottom_centre"
    TOP_CENTRE = "top_centre"
    CUSTOM = "custom"

    @property
    def centred(self) -> bool:
        return self in (Preset.BOTTOM_CENTRE, Preset.TOP_CENTRE)


PRESETS = (Preset.BOTTOM_LEFT, Preset.BOTTOM_CENTRE, Preset.TOP_CENTRE)
"""The presets a window can be put at (the "..." menu's Position)."""


class Edge(IntFlag):
    """The edges a resize drags: one, or two for a corner."""

    NONE = 0
    LEFT = 1
    TOP = 2
    RIGHT = 4
    BOTTOM = 8


EDGE_ZONE = 6
"""Pixels inside each edge that resize it."""
CORNER_ZONE = 10
"""The corners' squares, in pixels: they resize two edges at once."""
SNAP = 24
"""Pixels from a preset's place within which a dragged window snaps to it."""
EDGE_MARGIN = 40
"""Pixels from the work area's left (Bottom left) and top (Top centre)."""
BOTTOM_MARGIN = 90
"""Pixels between a bottom preset's window and the work area's bottom
(today's overlays': above a video player's controls)."""
STACK_GAP = 12
"""Pixels between windows stacked at the start, so three never overlap."""
DEFAULT_HEIGHT = 300
"""A new window's height: two real captions whole at the default text size
and width - FLEURS's median sentence (about 120 characters of English, or
40 of Chinese) and its translation take 108-138 px each at 960 px wide,
two with the gap and padding 284 px (polyglotic-hq 158). 180 px, the
proof of concept's, held one (145)."""
LEAST_DEFAULT_HEIGHT = 180
"""On a short screen, a new window is never lower than this (the height
before 158)."""
STACKED = 3
"""Windows that stack at the start without overlapping (three apps)."""
MAX_DEFAULT_WIDTH = 960
"""A first window is half the work area wide, up to this (today's)."""


@dataclass(frozen=True, slots=True)
class Size:
    width: int
    height: int


def default_size(area: Rect) -> Size:
    """A new window's size: half the work area's width (at most
    MAX_DEFAULT_WIDTH), DEFAULT_HEIGHT high - or lower on a short screen,
    so STACKED windows still stack above the bottom margin without
    overlapping, but never under LEAST_DEFAULT_HEIGHT."""
    width = min(MAX_DEFAULT_WIDTH, area.width // 2)
    room = (area.height - BOTTOM_MARGIN - (STACKED - 1) * STACK_GAP) // STACKED
    height = max(LEAST_DEFAULT_HEIGHT, min(DEFAULT_HEIGHT, room))
    return Size(max(1, min(width, area.width)), min(height, area.height))


def slot(preset: Preset, area: Rect, size: Size, index: int = 0) -> Rect:
    """A window of `size` at `preset` in `area`: the `index`-th of windows
    stacked there - upwards from a bottom preset, downwards from the top -
    each STACK_GAP from the last. "Where I put it" has no place of its own:
    it gets Bottom centre's."""
    width, height = min(size.width, area.width), min(size.height, area.height)
    step = index * (height + STACK_GAP)
    if preset is Preset.BOTTOM_LEFT:
        x = area.x + EDGE_MARGIN
    else:
        x = area.x + (area.width - width) // 2
    if preset is Preset.TOP_CENTRE:
        y = area.y + EDGE_MARGIN + step
    else:
        y = area.bottom - BOTTOM_MARGIN - height - step
    return clamped(Rect(x, y, width, height), area)


def clamped(rect: Rect, area: Rect) -> Rect:
    """`rect` inside `area`: moved in, and made smaller only if it's bigger
    than the area."""
    width, height = min(rect.width, area.width), min(rect.height, area.height)
    x = min(max(rect.x, area.x), area.right - width)
    y = min(max(rect.y, area.y), area.bottom - height)
    return Rect(x, y, width, height)


def edges_at(x: float, y: float, width: int, height: int) -> Edge:
    """The edges a press at (`x`, `y`) inside a window of that size would
    resize: two in a CORNER_ZONE square at a corner, one within EDGE_ZONE
    of an edge, none elsewhere."""
    left, right = x < CORNER_ZONE, x >= width - CORNER_ZONE
    top, bottom = y < CORNER_ZONE, y >= height - CORNER_ZONE
    found = Edge.NONE
    if (left or right) and (top or bottom):  # a corner
        found = (Edge.LEFT if left else Edge.RIGHT) | (Edge.TOP if top else Edge.BOTTOM)
    else:
        if x < EDGE_ZONE:
            found |= Edge.LEFT
        elif x >= width - EDGE_ZONE:
            found |= Edge.RIGHT
        if y < EDGE_ZONE:
            found |= Edge.TOP
        elif y >= height - EDGE_ZONE:
            found |= Edge.BOTTOM
    return found


def resized(
    start: Rect,
    edges: Edge,
    dx: int,
    dy: int,
    preset: Preset,
    minimum: Size,
    area: Rect,
) -> Rect:
    """`start` with `edges` dragged by (`dx`, `dy`) since the drag began.

    The opposite edges stay put. A centred preset's width changes on both
    sides equally, so the window stays centred (a corner too: x mirrored,
    y anchored as for any window). Stops at `minimum` and at `area`'s
    edges."""
    x, width = start.x, start.width
    if edges & (Edge.LEFT | Edge.RIGHT):
        if preset.centred:
            grow = 2 * dx if edges & Edge.RIGHT else -2 * dx
            centre = start.x + start.width / 2
            room = 2 * min(centre - area.x, area.right - centre)
            width = int(max(minimum.width, min(start.width + grow, room)))
            x = round(centre - width / 2)
        elif edges & Edge.RIGHT:
            right = max(min(start.right + dx, area.right), start.x + minimum.width)
            width = right - start.x
        else:
            left = min(max(start.x + dx, area.x), start.right - minimum.width)
            x, width = left, start.right - left
    y, height = start.y, start.height
    if edges & Edge.BOTTOM:
        bottom = max(min(start.bottom + dy, area.bottom), start.y + minimum.height)
        height = bottom - start.y
    elif edges & Edge.TOP:
        top = min(max(start.y + dy, area.y), start.bottom - minimum.height)
        y, height = top, start.bottom - top
    return Rect(x, y, width, height)


def moved(start: Rect, dx: int, dy: int, area: Rect) -> Rect:
    """`start` dragged by (`dx`, `dy`), kept in `area`."""
    return clamped(Rect(start.x + dx, start.y + dy, start.width, start.height), area)


def snapped(rect: Rect, area: Rect) -> tuple[Rect, Preset]:
    """Where a window dragged to `rect` goes: a preset's place within SNAP
    pixels of it, with that preset; or `rect` itself, "where I put it"."""
    size = Size(rect.width, rect.height)
    for preset in PRESETS:
        place = slot(preset, area, size)
        if abs(place.x - rect.x) <= SNAP and abs(place.y - rect.y) <= SNAP:
            return place, preset
    return rect, Preset.CUSTOM


MIN_COLUMN = 320
"""A joined window's narrowest column, in pixels (109's 10.6)."""


def joined(start: Rect, preset: Preset, width: int, area: Rect) -> Rect:
    """A joined window `width` wide at `start`'s place and height (the
    window the command came from): a centred preset keeps its centre, any
    other its left edge; clamped to `area` (109's 2a)."""
    width = max(1, min(width, area.width))
    x = round(start.x + start.width / 2 - width / 2) if preset.centred else start.x
    return clamped(Rect(x, start.y, width, start.height), area)


def columns(
    width: int, count: int, shares: tuple[float, ...] = ()
) -> list[tuple[int, int]]:
    """`count` columns across `width`: each one's left edge and width.
    `shares`: each column's share of the width, as the learner dragged the
    dividers (polyglotic-hq 284) - equal without them, or if they're not
    one a column; the first ones take the pixels left over."""
    if count < 1:
        return []
    if len(shares) != count:
        each, over = divmod(max(0, width), count)
        found, x = [], 0
        for index in range(count):
            size = each + (1 if index < over else 0)
            found.append((x, size))
            x += size
        return found
    edges = [round(width * sum(shares[:i])) for i in range(count)] + [max(0, width)]
    return [(edges[i], edges[i + 1] - edges[i]) for i in range(count)]


def shares_of(shares: tuple[float, ...], count: int) -> tuple[float, ...]:
    """`count` columns' shares of the width: `shares` if they're one a column
    and all more than nothing (scaled to add up to 1), else equal."""
    if len(shares) != count or count < 1 or any(s <= 0 for s in shares):
        return tuple(1.0 / count for _ in range(count)) if count else ()
    total = sum(shares)
    return tuple(s / total for s in shares)


DIVIDER_ZONE = EDGE_ZONE
"""Pixels either side of a divider between two columns that drag it."""


def divider_at(
    x: float, width: int, shares: tuple[float, ...], count: int
) -> int | None:
    """The divider a press at `x` (in the joined window) drags - its index,
    the one after column `index` - or None."""
    for index, (left, _) in enumerate(columns(width, count, shares)[1:]):
        if abs(x - left) <= DIVIDER_ZONE:
            return index
    return None


def moved_divider(
    shares: tuple[float, ...], index: int, dx: float, width: int, least: int
) -> tuple[float, ...]:
    """`shares` with divider `index` (after column `index`) moved `dx`
    pixels: the columns either side give and take; neither narrower than
    `least` (MIN_COLUMN), if the width allows."""
    if width <= 0 or not 0 <= index < len(shares) - 1:
        return shares
    pair = shares[index] + shares[index + 1]
    floor = min(least / width, pair / 2)
    left = min(max(shares[index] + dx / width, floor), pair - floor)
    moved = list(shares)
    moved[index], moved[index + 1] = left, pair - left
    return tuple(moved)


def at_start(
    saved: Rect | None,
    preset: Preset,
    areas: list[Rect],
    default: Rect,
) -> Rect:
    """Where a window opens: its saved place, pulled onto the screen
    holding its centre - or, if no screen does (a screen gone), `default`
    (its preset's place)."""
    if saved is None:
        return default
    for area in areas:
        if area.holds(*saved.centre):
            return clamped(saved, area)
    return default


def area_for(rect: Rect, areas: list[Rect]) -> Rect | None:
    """The work area holding `rect`'s centre (a window straddling two
    screens belongs to that one); None if none does."""
    for area in areas:
        if area.holds(*rect.centre):
            return area
    return None
