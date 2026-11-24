"""Captions fill the width, in the Lab (polyglotic-hq 309; the user,
2026-11-14: "often clauses will only be a few words and rarely make it to
the complete width of the window ... text will fill the complete caption
window line by line seperating by ellipsis"): a caption's clauses run on
in lines as wide as the window, what was said above and its translation
below - and the word under the mouse, the marks and a resize still work.
Off by default: a clause a row, as it was. Offscreen, made-up captions."""

import itertools
from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import QApplication, QWidget
from tests.budget_judge import sampled, within
from tests.ui_next.made_up import EN, finished_updates, live_update
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.captions import Clause
from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import (
    APP,
    FRUIT,
    MIC,
    clause,
    finished,
    live,
)
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    LaidLine,
    span_rects,
)
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, caption_style
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill, Join
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.pour import ELLIPSIS, tokens

STACKED = CaptionStyle(fill=Fill.STACKED)
POURED = CaptionLook(lab=CaptionLab(fill=Fill.STACKED), arrival=Arrival.STEP)

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each window and panel deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def a_line(*clauses: tuple[str, str], mine: bool = False) -> Line:
    """A finished caption's line: the recorded conversation's first (two
    clauses, translated), or `clauses` - (what was said, its translation)."""
    source = MIC if mine else APP
    view = CaptionLines((source,), EN, keep=10, yours=(MIC,))
    update = finished_updates(1, source)[0]
    if clauses:
        update = replace(update, clauses=tuple(Clause(o, {EN: t}) for o, t in clauses))
    view.apply(update)
    return view.lines[0]


def text_lines(laid: LaidLine) -> list[tuple[int, float, float, float, int, int]]:
    """Every text line laid: its row, top, left, right, and the characters
    it holds - from the caption's top left."""
    found = []
    for row in laid.rows:
        for n in range(row.layout.lineCount()):
            line = row.layout.lineAt(n)
            box = line.naturalTextRect()
            start = line.textStart()
            found.append(
                (row.index, row.top + line.y(), box.left(), box.right(), start,
                 start + line.textLength())
            )  # fmt: skip
    return found


def poured_window(
    qapp: QApplication, captions: int = 6, **lab: object
) -> CaptionWindow:
    look = replace(POURED, lab=replace(POURED.lab, **lab))  # type: ignore[arg-type]
    window = window_of(qapp, captions=captions, look=look)
    MADE.append(window)
    window.canvas.repaint()
    return window


# -- the Lab's values ---------------------------------------------------------------


def test_an_untouched_lab_keeps_a_clause_a_row() -> None:
    lab = CaptionLab()
    assert (lab.fill, lab.join) == (Fill.CLAUSES, Join.ELLIPSIS)
    assert lab.to_stored() == {}
    assert caption_style(CaptionLook()).fill is Fill.CLAUSES


@pytest.mark.usefixtures("fill_the_width_on")
def test_the_fill_is_saved_and_read_back_leniently() -> None:
    lab = CaptionLab(fill=Fill.STACKED, join=Join.LINE_ENDS)
    assert lab.to_stored() == {"fill": "stacked", "join": "line_ends"}
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    assert CaptionLab.from_stored({"fill": "sideways", "join": 3}) == CaptionLab()
    style = caption_style(CaptionLook(lab=lab))
    assert (style.fill, style.join) == (Fill.STACKED, Join.LINE_ENDS)


def test_no_arrows_while_captions_fill_the_width() -> None:
    """The user: "Might need to restrict this mode to no arrow word
    linkage" - a clause and its translation aren't on facing rows. The
    underlines stay, with their room."""
    arrows = CaptionLook(word_links=WordLinks.ARROWS)
    assert caption_style(arrows).arrows
    poured = caption_style(replace(arrows, lab=CaptionLab(fill=Fill.STACKED)))
    assert not poured.arrows and poured.link_room


# -- the layout ---------------------------------------------------------------------


def test_clauses_run_on_where_each_had_a_row(qapp: QApplication) -> None:
    line = a_line()
    rows = CaptionLayout().laid(line, 900, 1.0)
    poured = CaptionLayout(STACKED).laid(line, 900, 1.0)
    originals = [r for r in poured.rows if r.row.kind is RowKind.ORIGINAL]
    assert len(originals) == 2
    first, second = originals
    assert second.top == first.top  # the second clause on the first's line
    assert second.layout.lineAt(0).naturalTextRect().left() > 0
    assert first.trails and not second.trails  # an ellipsis at the join
    tops = {r.index: r.top for r in poured.rows}
    assert tops[1] == tops[3] > tops[0]  # the translations, below, run on too
    assert [r.top for r in poured.rows] == sorted(tops.values())  # down the caption
    assert poured.height < rows.height  # two lines, where rows took four
    assert sorted(r.index for r in poured.rows) == [r.index for r in rows.rows]


def test_a_live_revision_keeps_an_established_line_break(qapp: QApplication) -> None:
    """A shorter correction must not pull an already-shown word up a line."""
    engine = CaptionLayout()
    line = a_line(("alpha beta gamma delta", ""))
    font = engine._font(line.rows[0], 1.0, False)
    width = round(QFontMetricsF(font).horizontalAdvance("alpha beta ") + 2)

    before = engine.laid(line, width, 1.0).rows[0].layout
    assert before.lineCount() > 1
    old_end = before.lineAt(0).textStart() + before.lineAt(0).textLength()

    row = replace(line.rows[0], text="a beta gamma delta epsilon")
    revised = replace(line, rows=(row,))
    after = engine.laid(revised, width, 1.0).rows[0].layout

    assert after.lineAt(0).textStart() + after.lineAt(0).textLength() == old_end - 4
    assert row.text[: after.lineAt(0).textLength()].rstrip() == "a"


def test_only_a_space_between_clauses_draws_no_ellipsis(qapp: QApplication) -> None:
    style = replace(STACKED, join=Join.SPACE)
    laid = CaptionLayout(style).laid(a_line(), 900, 1.0)
    assert not any(row.trails for row in laid.rows)


LONG = (
    ("The speed limit on the motorway was lifted,", "高速公路上的限速取消了，"),
    (
        "and the insurance company refused to pay anything.",
        "保险公司拒绝支付任何费用。",
    ),
    ("Nobody was surprised 🙂.", "没有人感到惊讶 🙂。"),
)


@pytest.mark.parametrize("join", list(Join))
@pytest.mark.parametrize("width", [150, 260, 420, 640, 932])
@pytest.mark.parametrize("text_size", [0.6, 1.0, 2.2])
def test_every_word_is_laid_whole_within_the_width(
    qapp: QApplication, join: Join, width: int, text_size: float
) -> None:
    """What fits is measured - the window's width, the text size, the
    font: a line ends where the next word wouldn't fit, no word is split,
    nothing said is left out, nothing runs past the window's edge."""
    line = a_line(*LONG)
    laid = CaptionLayout(replace(STACKED, join=join)).laid(line, width, text_size)
    by_row: dict[int, list[tuple[int, int]]] = {}
    for index, _, _, right, start, end in text_lines(laid):
        assert right <= width + 1.5
        by_row.setdefault(index, []).append((start, end))
    for row in laid.rows:
        text = row.row.text
        units = len(text.encode("utf-16-le")) // 2  # as Qt counts characters
        spans = by_row[row.index]
        assert spans[0][0] == 0 and spans[-1][1] == units  # all of it
        assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))
        if not text.isascii():
            continue  # the Chinese rows: any character may start a line
        words = tokens(text)
        metrics = QFontMetricsF(row.layout.font())
        # "At line ends too" keeps room for half a space and the ellipsis at
        # the end of every line (pour.py): a word only a little narrower
        # than the window may still be wider than a line (polyglotic-hq 386:
        # with a CJK font on Linux, "insurance" at text size 2.2 was)
        ends = metrics.horizontalAdvance(" ") / 2 + metrics.horizontalAdvance(ELLIPSIS)
        room = width - 40 - (ends if join is Join.LINE_ENDS else 0.0)
        if all(metrics.horizontalAdvance(text[s:e]) < room for s, e, _ in words):
            starts = {start for start, _, _ in words}  # no word wider than a line
            assert all(start in starts for start, _ in spans)


def test_a_narrower_window_pours_into_more_lines(qapp: QApplication) -> None:
    engine = CaptionLayout(STACKED)
    line = a_line(*LONG)
    wide_, narrow = engine.laid(line, 900, 1.0), engine.laid(line, 300, 1.0)
    count = lambda laid: len({round(top) for _, top, *_ in text_lines(laid)})
    assert count(narrow) > count(wide_)
    assert narrow.height > wide_.height
    assert engine.laid(line, 900, 1.0) is wide_  # kept per width, as rows are


def test_your_own_speech_is_poured_against_the_right_edge(qapp: QApplication) -> None:
    # only a space at a join: a line's text is the last thing on it (with an
    # ellipsis the text ends short of the edge by it - which lines, by the font)
    style = replace(STACKED, own_right=True, join=Join.SPACE)
    laid = CaptionLayout(style).laid(a_line(*LONG, mine=True), 420, 1.0)
    ends: dict[int, float] = {}
    for row in laid.rows:  # a poured line by its baseline: two rows' pieces on
        # it share that, whatever their fonts' ascents (their tops differ)
        for n in range(row.layout.lineCount()):
            line = row.layout.lineAt(n)
            base = round(row.top + line.y() + line.ascent())
            ends[base] = max(ends.get(base, 0.0), line.naturalTextRect().right())
    assert len(ends) > 2
    assert all(418.0 <= right <= 421.5 for right in ends.values()), ends


def test_a_live_caption_is_poured_as_it_grows(qapp: QApplication) -> None:
    """Live updates: the last line grows as words come, the trailing
    ellipsis with its last word."""
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(live_update("app-00000"))
    line = view.lines[0]
    laid = CaptionLayout(STACKED).laid(line, 900, 1.0)
    assert line.live and line.rows[-1].text.endswith(" …")
    tops = {round(top) for _, top, *_ in text_lines(laid)}
    assert len(tops) == 2  # what was said on one line, its translation on one


# -- in a caption window ------------------------------------------------------------


def test_the_word_under_the_mouse_is_found_on_a_poured_line(
    qapp: QApplication,
) -> None:
    """Hover, a lookup and a dragged phrase go by row and character: a
    clause that runs on from another is still its own row."""
    window = poured_window(qapp)
    line, laid, rect = window.canvas.placed[-1]
    row = next(r for r in laid.rows if r.index == 2)  # the second clause's
    assert row.layout.lineAt(0).naturalTextRect().left() > 0  # it runs on
    word = span_rects(row.layout, 1, 2)[0].translated(rect.x(), rect.y() + row.top)
    found = window.canvas.hit(QPointF(word.center()))
    assert found is not None
    hit_line, hit_row, origin, index = found
    assert (hit_line.key, hit_row.index, index) == (line.key, 2, 1)
    assert origin == QPointF(rect.x(), rect.y() + row.top)
    start = next(r for r in laid.rows if r.index == 0)
    at = rect.y() + start.top
    before = span_rects(start.layout, 0, 1)[0].translated(rect.x(), at)
    first = window.canvas.hit(QPointF(before.center()))
    assert first is not None and (first[1].index, first[3]) == (0, 0)


def test_nothing_poured_is_below_the_windows_bottom_edge(qapp: QApplication) -> None:
    for size in (0.6, 1.0, 2.5):
        window = poured_window(qapp, captions=12)
        window.set_text_size(size)
        window.canvas.repaint()
        bottom = window.canvas.height() - PAD
        assert window.canvas.placed
        assert all(rect.bottom() <= bottom + 0.5 for _, _, rect in window.canvas.placed)
        newest = window.canvas.placed[-1]
        assert newest[0].key == window.view.lines[-1].key  # following the newest


def test_the_lab_turns_it_on_in_the_running_windows(qapp: QApplication) -> None:
    window = window_of(qapp, captions=4, look=replace(POURED, lab=CaptionLab()))
    MADE.append(window)
    view = LookView(window.look, window.set_look)
    panel = LabPanel(view)
    MADE.append(panel)
    assert panel.join.isEnabled()  # never greyed: a choice brings fill (368)
    panel.fill.choose(Fill.STACKED)
    assert window.look.lab.fill is Fill.STACKED
    assert window.canvas.engine.style.fill is Fill.STACKED
    panel.join.choose(Join.SPACE)
    assert window.canvas.engine.style.join is Join.SPACE
    window.canvas.repaint()
    _, laid, _ = window.canvas.placed[-1]
    tops = {row.index: row.top for row in laid.rows}
    assert tops[2] == tops[0]  # poured, at once
    view.reset_lab()
    assert window.canvas.engine.style.fill is Fill.CLAUSES


def test_between_clauses_can_be_chosen_with_fill_off_and_brings_it(
    qapp: QApplication,
) -> None:
    """368 (365's step 2): "Between clauses" was greyed while Captions fill
    the width was Off - the trap 365 took out of the Lab's switches.
    Choosing one now sets fill to Translation below (the choice that
    changes nothing more of the layout); with fill on, it changes only
    itself; fill moved back to Off keeps its value, shown."""
    assert CaptionLab().choose(join=Join.SPACE) == CaptionLab(
        fill=Fill.STACKED, join=Join.SPACE
    )
    paired = CaptionLab(fill=Fill.PAIRED)
    assert paired.choose(join=Join.SPACE) == replace(paired, join=Join.SPACE)
    window = window_of(qapp, captions=4, look=replace(POURED, lab=CaptionLab()))
    MADE.append(window)
    view = LookView(window.look, window.set_look)
    panel = LabPanel(view)
    MADE.append(panel)
    panel.join.choose(Join.ELLIPSIS)  # the one shown, clicked: it works
    assert (window.look.lab.fill, window.look.lab.join) == (
        Fill.STACKED,
        Join.ELLIPSIS,
    )
    assert panel.fill.value() is Fill.STACKED
    assert window.canvas.engine.style.fill is Fill.STACKED
    panel.join.choose(Join.SPACE)
    panel.fill.choose(Fill.CLAUSES)  # off again: the choice kept and shown
    assert window.look.lab.join is Join.SPACE and panel.join.value() is Join.SPACE
    assert panel.join.isEnabled()


def test_a_live_update_in_a_full_poured_window_is_within_budget(
    qapp: QApplication,
) -> None:
    """Thirty lines poured, Live updates: each live update lays out and
    paints its own caption within a new caption's budget."""
    window = poured_window(qapp, captions=30)
    grown = [
        replace(
            live_update("app-live"),
            clauses=tuple(
                Clause(f"{o} {'and more ' * n}", {EN: f"{t} {'and more ' * n}"})
                for o, t in LONG[:2]
            ),
        )
        for n in range(12)
    ]
    # as many as the tries take: 24 a try, and a busy PC's third ran out (437)
    updates = itertools.cycle(grown)

    def arrive() -> None:
        window.view.apply(next(updates))
        window.apply_changed(new_caption=False)
        window.canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 12))


# -- line by line (placement (b)) ------------------------------------------------------

PAIRED = CaptionStyle(fill=Fill.PAIRED)
WENT = clause(
    "我买了很多然后回家了，",
    "I bought a lot and then went home,",
    (("买", "bought"), ("很多", "a lot"), ("然后", "then"), ("回家", "home")),
)


def a_paired_line(*clauses: Clause, cuts: bool = True) -> Line:
    view = CaptionLines((APP,), EN, keep=10, cuts=cuts)
    view.apply(finished("c1", *(clauses or (WENT, FRUIT))))
    return view.lines[0]


def test_a_line_says_where_its_clauses_can_be_cut_only_when_asked() -> None:
    assert a_paired_line(cuts=False).cuts == ()
    line = a_paired_line()
    assert line.cuts[0] == ((3, 9), (5, 15), (7, 24))
    assert len(line.cuts[1]) == 1  # the fruit at the supermarket: links cross
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("c1", WENT))
    before = view.revision
    view.set_cuts(True)
    assert view.lines[0].cuts and view.revision > before
    captions_only = CaptionLines((APP,), None, keep=10, cuts=True)
    captions_only.apply(finished("c1", WENT))
    assert captions_only.lines[0].cuts == ((),)


def test_a_live_captions_unfinished_clause_is_not_cut() -> None:
    view = CaptionLines((APP,), EN, keep=10, cuts=True)
    view.apply(live("c1", FRUIT, WENT))
    assert view.lines[0].cuts[0] and view.lines[0].cuts[1] == ()


def test_line_by_line_a_line_of_each_cut_at_the_same_place(qapp: QApplication) -> None:
    """In a window just wide enough for "I bought a lot", the first pair
    of lines is 我买了很多 over "I bought a lot": the rest of each follows
    on the next pair."""
    line = a_paired_line()
    engine = CaptionLayout(PAIRED)
    # the translation's font: `rows[1]` is the second clause's Chinese (rows
    # go by top), whose Latin letters were Noto Sans SC's, about as wide as
    # IBM Plex's - Ma Shan Zheng's are narrower (532)
    english = next(r for r in engine.laid(line, 2000, 1.0).rows if r.index == 1)
    assert english.row.kind is RowKind.TRANSLATION
    font = english.layout.font()
    width = int(QFontMetricsF(font).horizontalAdvance("I bought a lot")) + 3
    laid = engine.laid(line, width, 1.0)
    assert laid.poured
    found = sorted(text_lines(laid), key=lambda found: found[1])
    assert [(index, start, end) for index, _, _, _, start, end in found[:2]] == [
        (0, 0, 5),
        (1, 0, 15),
    ]
    assert [(index, start) for index, _, _, _, start, _ in found[2:4]] == [
        (0, 5),
        (1, 15),
    ]
    tops = [top for _, top, *_ in found[:4]]
    assert tops == sorted(tops) and len(set(tops)) == 4
    assert tops[2] - tops[1] > tops[1] - tops[0]  # a clause's gap between pairs


def test_line_by_line_two_short_clauses_share_a_pair_of_lines(
    qapp: QApplication,
) -> None:
    laid = CaptionLayout(PAIRED).laid(a_paired_line(), 2000, 1.0)
    tops = {row.index: row.top for row in laid.rows}
    assert tops[0] == tops[2] < tops[1] == tops[3]
    stacked = CaptionLayout(STACKED).laid(a_paired_line(), 2000, 1.0)
    assert laid.height == stacked.height  # as wide as this, the same two lines


@pytest.mark.parametrize("join", list(Join))
@pytest.mark.parametrize("width", [150, 260, 420, 640, 932])
@pytest.mark.parametrize("text_size", [0.6, 1.0, 2.2])
@pytest.mark.parametrize("linked", [True, False])
def test_line_by_line_all_of_it_is_laid_within_the_width(
    qapp: QApplication, join: Join, width: int, text_size: float, linked: bool
) -> None:
    """With links to cut by, or none (every part falls back to wrapping):
    nothing said is left out, nothing runs past the window's edge."""
    line = a_paired_line() if linked else a_line(*LONG)
    laid = CaptionLayout(replace(PAIRED, join=join)).laid(line, width, text_size)
    by_row: dict[int, list[tuple[int, int]]] = {}
    for index, _, _, right, start, end in text_lines(laid):
        assert right <= width + 1.5
        by_row.setdefault(index, []).append((start, end))
    for row in laid.rows:
        units = len(row.row.text.encode("utf-16-le")) // 2
        spans = by_row[row.index]
        assert spans[0][0] == 0 and spans[-1][1] == units
        assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))


def test_line_by_line_a_word_is_found_where_it_was_poured(qapp: QApplication) -> None:
    line = a_paired_line()
    engine = CaptionLayout(PAIRED)
    font = engine.laid(line, 2000, 1.0).rows[1].layout.font()
    width = int(QFontMetricsF(font).horizontalAdvance("I bought a lot")) + 3
    laid = engine.laid(line, width, 1.0)
    row = next(row for row in laid.rows if row.index == 1)
    start = row.row.text.index("went")
    (rect,) = span_rects(row.layout, start, start + 4)
    its = next(
        found
        for found in text_lines(laid)
        if found[0] == 1 and found[4] <= start < found[5]
    )
    assert its[4] > 0  # not on the caption's first pair of lines
    assert abs(row.top + rect.top() - its[1]) < 1.0  # on the line it was poured to
    assert abs(rect.left() - its[2]) < 1.0 or its[4] < start


@pytest.mark.usefixtures("fill_the_width_on")
def test_the_lab_offers_line_by_line_and_the_windows_follow(qapp: QApplication) -> None:
    assert CaptionLab.from_stored({"fill": "paired"}).fill is Fill.PAIRED
    window = window_of(qapp, captions=4, look=replace(POURED, lab=CaptionLab()))
    MADE.append(window)
    assert not any(line.cuts for line in window.view.lines)
    view = LookView(window.look, window.set_look)
    panel = LabPanel(view)
    MADE.append(panel)
    panel.fill.choose(Fill.PAIRED)
    assert window.canvas.engine.style.fill is Fill.PAIRED
    assert not window.canvas.engine.style.arrows
    assert all(len(line.cuts) > 0 for line in window.view.lines)
    window.canvas.repaint()
    assert all(laid.poured for _, laid, _ in window.canvas.placed)
    panel.fill.choose(Fill.STACKED)
    assert not any(line.cuts for line in window.view.lines)
