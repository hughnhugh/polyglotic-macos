"""The one layout in the caption layout engine and a caption window
(polyglotic-hq 340, decision 0132; the Lab's New layout): word links keep
their colours, their arrows and the learning load in every way of filling
the window; captions run on into each other, each laid out by itself and
none before it again; and a resize step and a new caption stay in today's
budgets. Offscreen, made-up captions."""

from collections.abc import Iterator
from dataclasses import replace
from functools import partial
from itertools import cycle, pairwise

import pytest
import shiboken6
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from tests.budget_judge import sampled, within
from tests.ui_next.made_up import EN, finished_updates, live_update
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.listening.captions import Clause
from polyglotic_desktop.core.listening.display import (
    LIVE_TRAIL,
    DisplayOptions,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import (
    APP,
    BOUGHT,
    CONTROLS,
    FRUIT,
    GAME,
    OKAY,
    WEEKEND,
    finished,
    live,
)
from polyglotic_desktop.ui_next.caption_layout import (
    CJK_FAMILIES,
    DOT_DROP_PX,
    DOT_PX,
    LINK_MARK,
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
)
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks, link_colour
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import (
    PACE_INK_CLEARANCE_PX,
    RUN_ON_MOST,
    CaptionWindow,
    caption_style,
    runs_on,
)
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.flow import Cut, FlowOptions
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.word_classes import CLASS_COLOURS

ROWS = FlowOptions()
STACKED = FlowOptions(Cut.CAPTION)
PAIRED = FlowOptions(share=True, split=True)
ALIGNED = FlowOptions(share=True, split=True, aligned=True)
RUN_ON = FlowOptions(share=True, split=True, run_on=True)
EVERY = (ROWS, STACKED, PAIRED, ALIGNED, RUN_ON)

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each window deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def lines_of(*updates: object, links: WordLinks = WordLinks.COLOURS) -> CaptionLines:
    view = CaptionLines((APP,), EN, keep=20, options=DisplayOptions(word_links=links))
    view.set_models(True)
    for update in updates:
        view.apply(update)  # type: ignore[arg-type]
    return view


def engine_of(flow: FlowOptions, **style: object) -> CaptionLayout:
    return CaptionLayout(CaptionStyle(link_room=True, flow=flow, **style))  # type: ignore[arg-type]


# -- word links ------------------------------------------------------------------------


def test_two_clauses_on_one_line_keep_separate_links_and_hover_colours() -> None:
    """Pairing across clauses uses unique IDs even when classes share a swatch."""
    (line,) = lines_of(finished("a", WEEKEND, OKAY)).lines
    marks = CaptionMarks(None)
    marks.set_look(WordLinks.COLOURS, WordIntroductions.OFF)
    colours: dict[int, set[str]] = {}
    for index, row in enumerate(line.rows):
        for _, _, format_ in marks(line, index):
            if format_.hasProperty(LINK_MARK):
                link = int(format_.property(LINK_MARK))
                colours.setdefault(row.clause, set()).add(
                    link_colour(marks.panel, link)
                )
    assert len(colours[0]) == 4 and len(colours[1]) == 1
    assert colours[0].isdisjoint(colours[1])


def test_video_links_show_a_contrasting_edge_over_matching_footage(
    qapp: QApplication,
) -> None:
    (line,) = lines_of(finished("a", OKAY)).lines
    marks = CaptionMarks(None)
    panel = replace(marks.panel, opacity=0.0)
    marks.set_look(WordLinks.COLOURS, WordIntroductions.OFF, panel)
    engine = engine_of(ROWS)
    laid = engine.laid(line, 500, 1.0)
    ink = Ink(panel=panel.background, panel_opacity=panel.opacity)
    scene = QImage(500, 180, QImage.Format.Format_RGB32)
    scene.fill(QColor(CLASS_COLOURS[None]))
    with QPainter(scene) as painter:
        engine.paint(painter, line, laid, QPointF(0, 0), ink, marks)
    # Grey marks are on a grey scene. The contrasting edge is the only black ink.
    assert QColor("#000000").rgb() in (
        scene.pixel(x, y) for y in range(scene.height()) for x in range(scene.width())
    )


def test_joined_card_layout_and_links_match_a_fresh_paint_after_resizing(
    qapp: QApplication,
) -> None:
    (line,) = lines_of(finished("card", WEEKEND, OKAY), links=WordLinks.ARROWS).lines
    engine = engine_of(PAIRED, arrows=True)
    marks = CaptionMarks(None)

    def draw(laid: LaidLine, clip_top: int, alpha: float) -> QImage:
        image = QImage(600, 350, QImage.Format.Format_ARGB32)
        image.fill(QColor("black"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(QRectF(0, clip_top, image.width(), image.height()))
        ink = Ink(
            said_in_link_colours=True, translation_in_link_colours=True, alpha=alpha
        )
        engine.paint(painter, line, laid, QPointF(5.25, 10.5), ink, marks)
        painter.end()
        return image

    for width in (580, 575, 160, 580):
        card = engine.laid_card(line, width, 1.0)
        fresh = engine.laid(line, width, 1.0)
        assert card.height == fresh.height
        for links in (WordLinks.ARROWS, WordLinks.OFF, WordLinks.ARROWS):
            marks.set_look(links, WordIntroductions.OFF)
            for clip, alpha in ((0, 1.0), (0, 1.0), (45, 0.6), (0, 1.0)):
                assert draw(card, clip, alpha) == draw(fresh, clip, alpha)


def test_wrapped_translation_keeps_its_words_whole(qapp: QApplication) -> None:
    clause = Clause(
        "五六七八九十。",
        {EN: "Found fifteen green flags on the other side of the great river."},
    )
    (line,) = lines_of(
        finished(
            "sample", Clause("一二三四", {EN: "Seven runners scored points."}), clause
        )
    ).lines
    laid = engine_of(PAIRED).laid_card(line, 260, 1.0)
    text = clause.translations[EN]
    rows = [
        r for r in laid.rows if r.row.kind is RowKind.TRANSLATION and r.row.clause == 1
    ]
    assert "".join(row.row.text for row in rows) == text
    assert len(rows) > 1 and all(row.layout.lineCount() == 1 for row in rows)
    for row in rows[1:]:
        at = row.start
        assert not (text[at - 1].isalpha() and text[at].isalpha())


def painted(engine: CaptionLayout, line: Line, width: int) -> tuple[QImage, LaidLine]:
    marks = CaptionMarks(None)
    marks.set_look(WordLinks.ARROWS, WordIntroductions.OFF)
    laid = engine.laid(line, width, 1.0)
    image = QImage(width + 20, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    engine.paint(painter, line, laid, QPointF(10, 10), Ink(), marks)
    painter.end()
    return image, laid


@pytest.mark.parametrize("flow", [ROWS, PAIRED, ALIGNED])
def test_arrows_join_a_word_to_its_counterpart_in_every_line_pair(
    qapp: QApplication, flow: FlowOptions
) -> None:
    """Arrows were turned off whenever captions filled the width: the pour
    had no facing rows to join (309)."""
    (line,) = lines_of(finished("a", GAME, CONTROLS), links=WordLinks.ARROWS).lines
    image, laid = painted(engine_of(flow, arrows=True), line, 900)
    said = next(r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
    meant = next(r for r in laid.rows if r.row.kind is RowKind.TRANSLATION)
    bottom = said.top + said.layout.lineAt(0).height()
    top = meant.top + meant.layout.lineAt(0).y()
    third = (top - bottom) / 3
    assert third > 3
    # the middle of the room between the two lines: only a curve is there
    crossing = sum(
        1
        for y in range(int(10 + bottom + third), int(10 + top - third))
        for x in range(image.width())
        if image.pixelColor(x, y).lightness() > 60
    )
    assert crossing > 20


# -- every character laid, whatever the options ------------------------------------------


@pytest.mark.parametrize("flow", EVERY)
def test_the_engine_lays_every_character_in_lines_inside_the_width(
    qapp: QApplication, flow: FlowOptions
) -> None:
    view = lines_of(
        finished("a", GAME, CONTROLS, WEEKEND, OKAY), live("b", FRUIT, BOUGHT)
    )
    engine = engine_of(flow)
    for width in (240, 420, 610, 900, 1500):
        for line in view.lines:
            laid = engine.laid(line, width, 1.0)
            assert laid.poured and laid.height > 0
            assert laid.breaks and laid.breaks[-1] == pytest.approx(laid.height)
            for row in laid.rows:
                layout = row.layout
                held = sum(
                    layout.lineAt(n).textLength() for n in range(layout.lineCount())
                )
                display = (
                    row.row.text.rstrip() + "..." if row.continues else row.row.text
                )
                assert layout.text() == display
                assert held == len(display)
                # a live caption's trail is added after its words are
                # placed, so it may hang past the width - by itself at most
                # (by 189 + 69.5 - 240 = 18.5 px in Linux's fonts, 357)
                hang = 0.0
                if row.row.text.endswith(LIVE_TRAIL):
                    hang = QFontMetricsF(layout.font()).horizontalAdvance(LIVE_TRAIL)
                for n in range(layout.lineCount()):
                    box = layout.lineAt(n).naturalTextRect()
                    assert box.right() <= width + hang + 1.0


# -- in a caption window, within today's budgets -----------------------------------------


LABS = {
    "rows": CaptionLab(flow=True),
    "stacked": CaptionLab(flow=True, fill=Fill.STACKED),
    "line by line": CaptionLab(flow=True, fill=Fill.PAIRED),
    "lined up": CaptionLab(flow=True, fill=Fill.PAIRED, aligned=True),
    "run on": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
    # parts lined up in every way of filling (372)
    "rows lined up": CaptionLab(flow=True, aligned=True),
    "below lined up": CaptionLab(flow=True, fill=Fill.STACKED, aligned=True),
}


def a_chinese_face() -> None:
    """Skips a test of a caption window's lines on a machine where the
    faces the captions name for Chinese have no Chinese (Linux CI, 357).
    There it comes from a fallback whose lines are taller than the face
    the layout measured, so the window's lines overlap and no top edge
    clears them. Windows always has a Chinese face."""
    font = QFont()
    font.setFamilies(list(CJK_FAMILIES["zh"]))
    if not QFontMetricsF(font).inFont("我"):
        pytest.skip("no Chinese in the faces the captions name (Linux CI's fonts)")


def flow_window(
    qapp: QApplication, lab: CaptionLab, captions: int = 30
) -> CaptionWindow:
    look = CaptionLook(lab=lab, arrival=Arrival.STEP, word_links=WordLinks.COLOURS)
    window = window_of(qapp, captions=captions, look=look)
    MADE.append(window)
    window.canvas.repaint()
    return window


def test_the_labs_new_layout_puts_a_caption_window_on_the_one_layout(
    qapp: QApplication,
) -> None:
    assert caption_style(CaptionLook()).flow is not None  # every mode: no Qt wrap
    untouched = CaptionLab(fill=Fill.PAIRED, run_on=True, aligned=True)
    assert caption_style(CaptionLook(lab=untouched)).flow is not None
    window = flow_window(qapp, LABS["line by line"])
    assert window.canvas.engine.style.flow == PAIRED
    assert all(line.model is not None for line in window.view.lines)
    assert window.canvas.placed and all(
        laid.poured for _, laid, _ in window.canvas.placed
    )
    assert caption_style(CaptionLook(lab=LABS["lined up"])).flow == ALIGNED
    assert caption_style(CaptionLook(lab=LABS["run on"])).flow == RUN_ON
    # run-on is Line by line's; lined up is every way's (372)
    rows = CaptionLab(flow=True, run_on=True, aligned=True)
    assert caption_style(CaptionLook(lab=rows)).flow == replace(ROWS, aligned=True)
    arrows = CaptionLook(word_links=WordLinks.ARROWS, lab=LABS["line by line"])
    assert caption_style(arrows).arrows  # in every layout now


@pytest.mark.usefixtures("fill_the_width_on")
def test_the_new_layout_is_off_until_chosen_and_saved_leniently() -> None:
    lab = CaptionLab()
    assert (lab.flow, lab.run_on, lab.aligned) == (False, False, False)
    assert lab.to_stored() == {}
    chosen = CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True, aligned=True)
    stored = chosen.to_stored()
    assert stored == {"fill": "paired", "flow": True, "run_on": True, "aligned": True}
    assert CaptionLab.from_stored(stored) == chosen
    assert CaptionLab.from_stored({"flow": "yes", "run_on": 1}) == CaptionLab()


def test_the_lab_turns_the_new_layout_on_and_its_two_choices(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = LabPanel(view)
    MADE.append(panel)
    panel.refresh()
    panel.flow.switch.setChecked(True)
    panel.fill.choose(Fill.PAIRED)
    panel.refresh()
    assert view.value.lab.flow and view.value.lab.fill is Fill.PAIRED
    panel.run_on.switch.setChecked(True)
    panel.aligned.switch.setChecked(True)
    assert view.value.lab == CaptionLab(
        flow=True, fill=Fill.PAIRED, run_on=True, aligned=True
    )


def test_turning_a_line_by_line_choice_on_brings_what_it_needs() -> None:
    """365 (the user, 2026-11-15, on 0.1.6's greyed-out switches: "I can't
    seem to select these settings"): run-on turns New layout on and fill
    to Line by line, lined up New layout alone (372: it works in every way
    of filling); off, they change nothing else."""
    needs = CaptionLab(flow=True, fill=Fill.PAIRED)
    assert CaptionLab().choose(run_on=True) == replace(needs, run_on=True)
    assert CaptionLab().choose(aligned=True) == CaptionLab(flow=True, aligned=True)
    assert CaptionLab(fill=Fill.PAIRED).choose(aligned=True) == replace(
        needs, aligned=True
    )
    # and the captions are laid out so
    chose = CaptionLab().choose
    assert caption_style(CaptionLook(lab=chose(run_on=True))).flow == RUN_ON
    assert caption_style(CaptionLook(lab=chose(aligned=True))).flow == replace(
        ROWS, aligned=True
    )
    stacked = CaptionLab(fill=Fill.STACKED, run_on=True)
    assert not stacked.line_by_line
    assert stacked.choose(run_on=False) == CaptionLab(fill=Fill.STACKED)
    assert stacked.choose(aligned=False) == CaptionLab(fill=Fill.STACKED, run_on=True)
    on = replace(needs, run_on=True, aligned=True)
    assert on.line_by_line
    # moving what they need away keeps their value
    assert on.choose(fill=Fill.STACKED) == replace(on, fill=Fill.STACKED)
    assert on.choose(flow=False) == replace(on, flow=False)


def test_the_labs_line_by_line_switches_can_be_clicked_from_the_start(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = LabPanel(view)
    MADE.append(panel)
    for row in (panel.run_on, panel.aligned):
        assert row.switch.isEnabled() and not row.switch.isChecked()
    panel.run_on.switch.click()
    lab = view.value.lab
    assert (lab.flow, lab.fill, lab.run_on, lab.aligned) == (
        True,
        Fill.PAIRED,
        True,
        False,
    )
    # the rows it set show it
    assert panel.flow.switch.isChecked() and panel.fill.value() is Fill.PAIRED
    assert panel.run_on.switch.isChecked()
    # fill moved away: off where it does nothing, its value kept
    panel.fill.choose(Fill.STACKED)
    assert view.value.lab.run_on and not panel.run_on.switch.isChecked()
    panel.fill.choose(Fill.PAIRED)
    assert panel.run_on.switch.isChecked()
    panel.flow.switch.click()  # New layout off: the same
    assert view.value.lab.run_on and not panel.run_on.switch.isChecked()
    panel.run_on.switch.click()  # one click makes it work again
    assert view.value.lab.line_by_line and panel.run_on.switch.isChecked()
    # off changes nothing else
    panel.run_on.switch.click()
    lab = view.value.lab
    assert (lab.flow, lab.fill, lab.run_on) == (True, Fill.PAIRED, False)


# -- captions that run on ----------------------------------------------------------------


def test_the_engine_lays_a_caption_out_from_what_the_one_before_left_open(
    qapp: QApplication,
) -> None:
    view = lines_of(finished("a", OKAY), finished("b", GAME))
    first, second = view.lines
    engine = engine_of(RUN_ON)
    before = engine.laid(first, 900, 1.0)
    entry = engine.left_open(first, 900, 1.0)
    assert entry is not None and before.open == entry and before.lead == 0.0
    assert entry.upper is not None and entry.lower is not None
    rows = engine.laid_out
    laid = engine.laid(second, 900, 1.0, entry)
    assert engine.laid_out == rows + len(second.rows)  # the first: not again
    assert engine.laid(first, 900, 1.0) is before
    assert laid.lead == pytest.approx(entry.height) and laid.label is None
    said = next(r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
    meant = next(r for r in laid.rows if r.row.kind is RowKind.TRANSLATION)
    assert said.top == 0.0  # on the first's line pair, after its text
    assert said.layout.lineAt(0).naturalTextRect().left() > entry.upper.end
    assert meant.layout.lineAt(0).naturalTextRect().left() > entry.lower.end
    assert laid.height == pytest.approx(entry.height)  # no line of its own
    # the ellipsis between them is the second's to draw, before its text
    assert said.trails and said.trails[0].x() >= entry.upper.end
    # and by itself it starts at the left, as before
    alone = engine.laid(second, 900, 1.0)
    assert alone.lead == 0.0
    assert alone.rows[0].layout.lineAt(0).naturalTextRect().left() == 0.0


def test_only_captions_of_one_source_under_one_label_run_on() -> None:
    view = lines_of(finished("a", OKAY), finished("b", GAME), live("c", FRUIT))
    first, second, spoken = (
        replace(line, key=RUN_ON_MOST + 1 + n) for n, line in enumerate(view.lines)
    )
    assert runs_on(first, second) and runs_on(second, spoken)
    # a run starts a line of its own every so often: it bounds the work
    assert not runs_on(first, replace(second, key=2 * RUN_ON_MOST))
    assert not runs_on(spoken, second)  # its end still moves
    assert not runs_on(first, replace(second, label="Discord  Mandarin"))
    assert not runs_on(first, replace(second, has_pace=True))
    assert not runs_on(first, replace(second, by_you=True))
    assert not runs_on(first, replace(second, provisional=True))
    assert not runs_on(replace(first, provisional=True), second)
    assert not runs_on(first, replace(second, model=None))


def drawn(window: CaptionWindow) -> dict[tuple[int, int, int], tuple[float, float]]:
    """Each text line the window drew, by caption, row and line: where."""
    found = {}
    for line, laid, rect in window.canvas.placed:
        for row in laid.rows:
            for n in range(row.layout.lineCount()):
                box = row.layout.lineAt(n).naturalTextRect()
                found[(line.key, row.index, row.visual_line + n)] = (
                    box.left(),
                    rect.top() + row.top + box.top(),
                )
    return found


def fullness(window: CaptionWindow) -> float:
    """Mean fraction of the available text width filled by visible lines."""
    ends: dict[float, float] = {}
    foot = PAD + window.canvas._seen_height()
    for _, laid, rect in window.canvas.placed:
        for row in laid.rows:
            for n in range(row.layout.lineCount()):
                box = row.layout.lineAt(n).naturalTextRect()
                top = rect.top() + row.top + box.top()
                if (
                    top < window.canvas.clear_top - 0.5
                    or top + box.height() > foot + 0.5
                ):
                    continue
                y = round(top)
                ends[y] = max(ends.get(y, 0.0), box.right())
    return sum(ends.values()) / (len(ends) * window.canvas._width())


def test_captions_run_on_in_a_window_and_fill_its_lines(qapp: QApplication) -> None:
    """The user, 2026-11-15: "customise the lines to accurately fill screen
    width". Each caption starting a line of its own, most of a wide
    window's lines stay short."""
    a_chinese_face()
    apart = flow_window(qapp, LABS["line by line"], captions=12)
    together = flow_window(qapp, LABS["run on"], captions=12)
    for window in (apart, together):
        window.resize(1400, 420)
        window.set_pace(142, 135, 118, 110)
        window.canvas.repaint()
    # Compare the same words and screen face. The shorter language and the
    # final pair of each run leave different amounts of space on each platform.
    assert fullness(together) > fullness(apart)
    assert len(together.canvas.placed) > len(apart.canvas.placed)  # more in view
    # a caption that carries on is drawn over the end of the one before
    placed = together.canvas.placed
    over = [
        rect.top() < earlier.bottom() - 1.0
        for (_, _, earlier), (_, _, rect) in pairwise(placed)
    ]
    assert any(over)
    # and has no label of its own: the run's first says whose they are
    assert not any(laid.label for _, laid, _ in placed if laid.lead)
    # The fixed label reserves only the part of its rows it actually uses:
    # run-on text may pack beside it, but shaped row geometry stays clear.
    pace = QRectF(together.pace.geometry()).adjusted(
        -PACE_INK_CLEARANCE_PX,
        -PACE_INK_CLEARANCE_PX,
        PACE_INK_CLEARANCE_PX,
        PACE_INK_CLEARANCE_PX,
    )
    beside = 0
    # A taller face changes which pair lands next to the label. Cover one
    # layout's height, including positions where the whole pair is clipped.
    first_height = together.height()
    layout_height = round(max(laid.height for _, laid, _ in placed))
    for height in range(first_height, first_height + layout_height, 16):
        together.resize(together.width(), height)
        together.canvas.repaint()
        for _, laid, rect in together.canvas.placed:
            for row in laid.rows:
                for n in range(row.layout.lineCount()):
                    ink = (
                        row.layout.lineAt(n)
                        .naturalTextRect()
                        .translated(rect.left(), rect.top() + row.top)
                    )
                    if max(ink.top(), together.canvas.clear_top, pace.top()) < min(
                        ink.bottom(), pace.bottom()
                    ):
                        beside += 1
                        assert ink.right() <= pace.left(), (ink, pace)
    assert beside, "the packing rule is exercised by a row beside pace"


def test_text_already_shown_stays_where_it_is_when_a_caption_runs_on(
    qapp: QApplication,
) -> None:
    window = flow_window(qapp, LABS["run on"], captions=6)
    window.resize(1100, 600)
    window.canvas.repaint()
    before = drawn(window)
    newest = max(key for key, _, _ in before)
    window.view.apply(finished_updates(7)[-1])
    window.apply_changed(new_caption=True)
    window.canvas.repaint()
    after = drawn(window)
    assert max(key for key, _, _ in after) > newest
    common = before.keys() & after.keys()
    assert common
    assert all(after[at][0] == before[at][0] for at in common)
    # Compare the travel itself at QTextLine's 1/64 px precision.
    rises = [before[at][1] - after[at][1] for at in common]
    assert max(rises) - min(rises) <= 1 / 64


def test_run_on_lines_glide_with_the_caption_they_share(qapp: QApplication) -> None:
    window = flow_window(qapp, LABS["run on"], captions=8)
    window.set_look(replace(window.look, arrival=Arrival.STEP_AND_SLIDE))
    window.resize(1100, 600)
    now = 10.0
    window.clock = lambda: now
    window.canvas.repaint()
    leads = {line.key for line, laid, _ in window.canvas.placed if laid.lead}
    before = drawn(window)
    # A long caption forces the shared lines above it to rise.
    arrival = replace(
        finished_updates(1, start=20)[0],
        clauses=(
            Clause("Another lantern is coming. " * 5, {EN: "A line of lights. " * 6}),
        ),
    )
    window.receive(arrival)
    window.canvas.repaint()
    first = drawn(window)
    held = [k for k in before.keys() & first.keys() if k[0] in leads]
    assert held and window.arriving
    assert all(first[k][1] == pytest.approx(before[k][1]) for k in held)
    now += 0.15
    window.canvas.repaint()
    moving = drawn(window)
    assert any(moving[k][1] < first[k][1] for k in held if k in moving)


def test_a_word_is_found_under_the_mouse_where_two_captions_share_a_line(
    qapp: QApplication,
) -> None:
    window = flow_window(qapp, LABS["run on"], captions=8)
    window.resize(1400, 420)
    window.canvas.repaint()
    canvas = window.canvas
    line, laid, rect = next(
        (line, laid, rect)
        for line, laid, rect in canvas.placed
        if laid.lead and laid.rows[0].layout.lineAt(0).naturalTextRect().left() > 0
    )
    row = laid.rows[0]
    box = row.layout.lineAt(0).naturalTextRect()
    pos = QPointF(rect.x() + box.left() + 4, rect.top() + row.top + box.center().y())
    found = canvas.hit(pos)
    assert found is not None and found[0].key == line.key and found[3] == 0
    earlier = canvas.hit(QPointF(rect.x() + 4, pos.y()))
    assert earlier is not None and earlier[0].key < line.key


@pytest.mark.parametrize("lab", list(LABS))
def test_word_links_are_drawn_in_every_option(qapp: QApplication, lab: str) -> None:
    """Colours in each - no option turns them off - and Arrows too."""
    window = flow_window(qapp, LABS[lab], captions=8)
    marks = window.marks
    linked = sum(
        1
        for line, _, _ in window.canvas.placed
        for n in range(len(line.rows))
        for mark in marks(line, n)
        if mark[2].hasProperty(LINK_MARK)
    )
    assert linked > 0
    assert caption_style(CaptionLook(lab=LABS[lab], word_links=WordLinks.ARROWS)).arrows


@pytest.mark.parametrize("lab", list(LABS))
def test_a_resize_step_is_within_a_frame(qapp: QApplication, lab: str) -> None:
    window = flow_window(qapp, LABS[lab], captions=150)
    width, height = window.width(), window.height()

    def step(n: int) -> None:
        window.resize(width - 150 + n * 9, height + n)
        window.canvas.repaint()

    within(budgets.FRAME, lambda: sampled(qapp, [partial(step, n) for n in range(30)]))


@pytest.mark.parametrize("lab", list(LABS))
def test_a_live_update_is_within_a_new_captions_budget(
    qapp: QApplication, lab: str
) -> None:
    window = flow_window(qapp, LABS[lab], captions=150)
    pool = finished_updates(8)
    grown = [
        replace(
            live_update("app-live"),
            clauses=tuple(
                Clause(
                    f"{c.original} {'and more ' * n}",
                    {EN: f"{c.translations[EN]} {'and more ' * n}"},
                    c.links,
                )
                for c in pool[n % 8].clauses
            ),
        )
        for n in range(12)
    ]
    # as many as the tries take: 24 a try, and a busy PC's third ran out (437)
    updates = cycle(grown)

    def arrive() -> None:
        window.view.apply(next(updates))
        window.apply_changed(new_caption=False)
        window.canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 12))


def test_a_line_cut_off_at_the_top_takes_its_link_bars_with_it(
    qapp: QApplication,
) -> None:
    """Captions that run on scroll by the line, so the top often cuts a
    caption between its lines. The line above the cut wasn't drawn, but
    its word links' bars - drawn under it - were: a bar alone over the
    first line showing. Now the window starts below them."""
    a_chinese_face()
    window = flow_window(qapp, LABS["run on"], captions=20)
    under = window.canvas._under()
    assert under > 0
    cut = 0
    for height in range(150, 330, 7):  # lines land at every offset
        window.resize(900, height)
        window.canvas.grab()
        top = window.canvas.clear_top
        for _, laid, rect in window.canvas.placed:
            for row in laid.rows:
                for n in range(row.layout.lineCount()):
                    line = row.layout.lineAt(n)
                    at = rect.top() + row.top + line.y()
                    if at < top - 0.01:  # not drawn: nor is what's under it
                        cut += 1
                        assert at + line.height() + under <= top + 0.01, height
    assert cut
    assert flow_window(qapp, CaptionLab()).canvas._under() > 0.0


def test_a_line_cut_off_at_the_top_takes_its_new_words_dots_with_it(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 402 (QA batch 11, on real captions at 700 px): with word
    links off there are no bars, but a new word's dots still hang under its
    line, below the line's descent. The line above the cut wasn't drawn;
    its dots were - a row of dots alone over the first line showing. The
    window now starts below where any cut line's dots could be."""
    a_chinese_face()
    look = CaptionLook(
        lab=LABS["run on"], arrival=Arrival.STEP, word_links=WordLinks.OFF
    )
    window = window_of(qapp, captions=20, look=look)
    MADE.append(window)
    assert not window.canvas.engine.style.link_room  # no bars to make room for
    cut = 0
    for height in range(150, 330, 7):  # lines land at every offset
        window.resize(900, height)
        window.canvas.grab()
        top = window.canvas.clear_top
        for _, laid, rect in window.canvas.placed:
            for row in laid.rows:
                font = row.layout.font()  # where `_dots` puts them
                scale = max(0.5, font.pixelSize() / 21.0)
                metrics = QFontMetricsF(font)
                drop = (
                    metrics.underlinePos() + metrics.lineWidth() + DOT_DROP_PX * scale
                )
                size = DOT_PX * scale
                for n in range(row.layout.lineCount()):
                    line = row.layout.lineAt(n)
                    at = rect.top() + row.top + line.y()
                    if at + line.height() <= top + 0.01:  # above it: nor its dots
                        cut += 1
                        dots_end = at + line.ascent() + drop + size
                        assert dots_end <= top + 0.01, (height, dots_end, top)
    assert cut


@pytest.mark.parametrize("lab", ["line by line", "lined up", "run on"])
def test_a_translation_never_shows_without_the_line_it_translates(
    qapp: QApplication, lab: str
) -> None:
    """On real captions (the validation run, 2026-11-15) the window's
    first line was often a translation alone: the top cut its pair in two.
    Line by line, the window starts at a whole pair."""
    window = flow_window(qapp, LABS[lab], captions=20)
    halved = 0
    for height in range(150, 330, 7):
        window.resize(900, height)
        window.canvas.grab()
        top = window.canvas.clear_top
        tops: dict[bool, list[float]] = {True: [], False: []}
        for _, laid, rect in window.canvas.placed:
            first = min(laid.rows, key=lambda row: row.top).row.kind
            for row in laid.rows:
                for n in range(row.layout.lineCount()):
                    at = rect.top() + row.top + row.layout.lineAt(n).y()
                    tops[row.row.kind is first].append(at)
        for at in tops[False]:
            if at < top - 0.01:
                continue  # not drawn
            above = max(u for u in tops[True] if u < at - 0.01)
            halved += above < top - 0.01
    assert not halved


def test_the_new_layout_starts_below_the_spoken_language_question(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """350's room for the question and 340's layout together: captions
    that run on start below the question, at a whole pair, and no cut
    line's link bars are left under it."""
    a_chinese_face()
    window = flow_window(qapp, LABS["run on"], captions=20)
    window.resize(900, 300)
    monkeypatch.setattr(window, "question_foot", lambda: 61.0)
    window.canvas.grab()
    top = window.canvas.clear_top
    assert top >= 61.0
    under = window.canvas._under()
    drawn = 0
    for _, laid, rect in window.canvas.placed:
        for row in laid.rows:
            for n in range(row.layout.lineCount()):
                line = row.layout.lineAt(n)
                at = rect.top() + row.top + line.y()
                if at < top - 0.01:
                    assert at + line.height() + under <= top + 0.01
                else:
                    drawn += 1
    assert drawn
