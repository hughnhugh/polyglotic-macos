"""Where a surface's lines are scrolled to - following the newest, or held
where the learner scrolled back - measuring only what shows."""

from dataclasses import dataclass

from polyglotic_desktop.ui_next.views.scroll import Anchor, Scroll

VIEW = 100.0
GAP = 10.0


@dataclass(frozen=True)
class Row:
    key: int
    height: float = 30.0


class Measured:
    """Heights, counting what was measured."""

    def __init__(self) -> None:
        self.asked: list[int] = []

    def __call__(self, row: Row) -> float:
        self.asked.append(row.key)
        return row.height


def rows(count: int, start: int = 1) -> list[Row]:
    return [Row(key) for key in range(start, start + count)]


def test_following_shows_the_newest_at_the_bottom() -> None:
    lines = rows(10)
    placed = Scroll().placed(lines, Measured(), VIEW, GAP)
    assert [p.line.key for p in placed] == [8, 9, 10]
    assert placed[-1].top + 30 == VIEW
    assert placed[0].top < 0  # the oldest that shows, partly


def test_only_the_lines_that_show_are_measured() -> None:
    lines = rows(1_000)
    measured = Measured()
    scroll = Scroll()
    scroll.placed(lines, measured, VIEW, GAP)
    assert len(measured.asked) == 3
    measured.asked.clear()
    scroll.scroll_by(500, lines, measured, VIEW, GAP)
    assert len(measured.asked) < 40  # the lines stepped over, not the list


def test_scrolled_back_holds_its_line_as_new_ones_arrive() -> None:
    lines = rows(10)
    scroll = Scroll()
    scroll.scroll_by(80, lines, Measured(), VIEW, GAP)
    assert not scroll.following
    held = scroll.placed(lines, Measured(), VIEW, GAP)
    lines += rows(5, start=11)
    assert scroll.placed(lines, Measured(), VIEW, GAP) == held


def test_scrolling_down_to_the_newest_follows_again() -> None:
    lines = rows(10)
    scroll = Scroll()
    scroll.scroll_by(80, lines, Measured(), VIEW, GAP)
    scroll.scroll_by(-200, lines, Measured(), VIEW, GAP)
    assert scroll.following
    assert scroll.placed(lines, Measured(), VIEW, GAP)[-1].line.key == 10


def test_scrolling_back_stops_at_the_oldest_line() -> None:
    lines = rows(10)
    scroll = Scroll()
    scroll.scroll_by(10_000, lines, Measured(), VIEW, GAP)
    assert scroll.anchor == Anchor(1, 0.0)
    assert scroll.placed(lines, Measured(), VIEW, GAP)[0].top == 0.0


def test_a_short_list_follows_whatever_the_scroll() -> None:
    lines = rows(2)
    scroll = Scroll()
    scroll.scroll_by(100, lines, Measured(), VIEW, GAP)
    assert scroll.following
    assert scroll.placed(lines, Measured(), VIEW, GAP)[-1].top == VIEW - 30


def test_a_held_line_that_went_is_replaced_by_the_next() -> None:
    lines = rows(10)
    scroll = Scroll()
    scroll.anchor = Anchor(4, 0.0)
    lines = [line for line in lines if line.key != 4]
    assert scroll.placed(lines, Measured(), VIEW, GAP)[0].line.key == 5


def test_a_held_line_that_shrank_past_the_top_is_skipped() -> None:
    lines = rows(10)
    scroll = Scroll()
    scroll.anchor = Anchor(3, -25.0)
    shrunk = [Row(line.key, 20.0) for line in lines]  # wider window, say
    assert scroll.placed(shrunk, Measured(), VIEW, GAP)[0].line.key == 4
