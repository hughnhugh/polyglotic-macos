"""Your own speech's look, in the Lab (polyglotic-hq 305; the user,
2026-11-13: "Your own speech should be formatted differently. (perhaps
right aligned? I'm not sure another lab setting / default some other
identifier)"): on the right, a tint behind it, a bar at its side, and its
"You" label as now, in a badge or not shown - each off by default, so an
untouched Lab draws today's window. Offscreen, made-up captions; painted
into images, never the screen."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui_next.caption_layout import (
    BADGE_PAD,
    OWN_BAR_GAP_PX,
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
)
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Labels, Line
from polyglotic_desktop.ui_next.views.flow import FlowOptions
from polyglotic_desktop.ui_next.views.lab import CaptionLab, OwnLabel
from polyglotic_desktop.ui_next.views.panels import LookView

EN = Language("en")
WIDTH = 600
YOU = "#8be38f"
PANEL = QColor("#101216")


@pytest.fixture
def lines(qapp: QApplication) -> tuple[Line, Line]:
    """An app's caption and one of the user's own, with their labels."""
    view = CaptionLines((APP, MIC), EN, keep=10, yours=(MIC,))
    view.set_labels(
        Labels(
            {APP: SourceLabel("Discord", "#4dd0e1")},
            show_source=True,
            you=SourceLabel("You", YOU),
        )
    )
    view.apply(finished("a", clause("你今天有空吗？", "Are you free today?")))
    view.apply(finished("y", clause("Yes, after eight."), source=MIC, language=EN))
    theirs, yours = view.lines
    assert yours.by_you and not theirs.by_you and yours.label == "You"
    return theirs, yours


def painted(line: Line, style: CaptionStyle) -> tuple[QImage, LaidLine]:
    engine = CaptionLayout(style)
    laid = engine.laid(line, WIDTH, 1.0)
    image = QImage(WIDTH + 40, int(laid.height) + 30, QImage.Format.Format_ARGB32)
    image.fill(PANEL)
    painter = QPainter(image)
    engine.paint(painter, line, laid, QPointF(20, 15), Ink())
    painter.end()
    return image, laid


def near(found: QColor, wanted: str, within: int = 60) -> bool:
    want = QColor(wanted)
    return (
        abs(found.red() - want.red())
        + abs(found.green() - want.green())
        + abs(found.blue() - want.blue())
    ) <= within


def test_your_speech_is_on_the_right_by_default_and_the_rest_as_before(
    lines: tuple[Line, Line],
) -> None:
    """B, the default (the user, 2026-11-14, DECISIONS #133: "pick a
    reasonable default"): your speech on the right, like a chat; the tint,
    the bar and the label as before. A learner who never touched the Lab
    stores nothing and gets it; one who turns it off keeps that."""
    lab = CaptionLab()
    assert (lab.own_right, lab.own_tint, lab.own_bar) == (True, False, False)
    assert lab.own_label is OwnLabel.AS_NOW and lab.to_stored() == {}
    grouped = CaptionStyle(flow=FlowOptions())
    assert caption_style(CaptionLook()) == replace(grouped, own_right=True)
    off = replace(lab, own_right=False)
    assert off.to_stored() == {"own_right": False}
    assert CaptionLab.from_stored(off.to_stored()) == off  # a choice is kept
    theirs, yours = lines
    on_the_right, _ = painted(yours, caption_style(CaptionLook(lab=lab)))
    assert on_the_right == painted(yours, replace(grouped, own_right=True))[0]
    as_before, _ = painted(yours, caption_style(CaptionLook(lab=off)))
    assert as_before == painted(yours, grouped)[0]  # A: as before
    # an app's captions: as they were either way
    assert (
        painted(theirs, caption_style(CaptionLook()))[0] == painted(theirs, grouped)[0]
    )


def test_a_window_captioning_the_mic_alone_keeps_it_on_the_left() -> None:
    """Every line of a window captioning the mic alone is yours: on the
    right it'd be a chat with no one, so it stays as it was."""
    look = CaptionLook()
    assert caption_style(look).own_right
    assert not caption_style(look, mine_only=True).own_right


def test_it_is_kept_and_read_back_leniently() -> None:
    lab = CaptionLab(own_right=True, own_bar=True, own_label=OwnLabel.BADGE)
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    odd = {"own_right": "yes", "own_tint": 1, "own_label": "sideways"}
    assert CaptionLab.from_stored(odd) == CaptionLab()
    style = caption_style(CaptionLook(lab=lab))
    assert (style.own_right, style.own_bar, style.own_label) == (
        True,
        True,
        OwnLabel.BADGE,
    )


def test_on_the_right_lines_up_only_your_speech_there(lines: tuple[Line, Line]) -> None:
    theirs, yours = lines
    engine = CaptionLayout(CaptionStyle(own_right=True))
    for line, right in ((theirs, False), (yours, True)):
        laid = engine.laid(line, WIDTH, 1.0)
        rows = [r.layout.lineAt(0).naturalTextRect() for r in laid.rows]
        assert laid.label is not None
        rows.append(laid.label.lineAt(0).naturalTextRect())
        for rect in rows:
            if right:
                assert rect.right() == pytest.approx(WIDTH, abs=1.5)
            else:
                assert rect.left() == pytest.approx(0, abs=1.5)


def test_a_tint_and_a_bar_in_your_labels_colour(lines: tuple[Line, Line]) -> None:
    theirs, yours = lines
    plain, laid = painted(yours, CaptionStyle())
    tinted, _ = painted(yours, CaptionStyle(own_tint=True))
    gap = QPointF(20 + WIDTH - 5, 15 + laid.height / 2)  # right of the text
    assert plain.pixelColor(gap.toPoint()) == PANEL
    tint = tinted.pixelColor(gap.toPoint())
    assert tint != PANEL and tint.green() > PANEL.green() + 8  # YOU's green
    barred, _ = painted(yours, CaptionStyle(own_bar=True))
    bar = QPointF(20 - OWN_BAR_GAP_PX + 1.5, 15 + laid.height / 2).toPoint()
    assert near(barred.pixelColor(bar), YOU)
    right, _ = painted(yours, CaptionStyle(own_bar=True, own_right=True))
    at_right = QPointF(20 + WIDTH + OWN_BAR_GAP_PX - 1.5, 15 + laid.height / 2)
    assert near(right.pixelColor(at_right.toPoint()), YOU)
    assert right.pixelColor(bar) == PANEL  # on the right only
    theirs_drawn, _ = painted(theirs, CaptionStyle(own_tint=True, own_bar=True))
    theirs_plain, _ = painted(theirs, CaptionStyle())
    assert theirs_drawn == theirs_plain  # an app's caption: as it was


def test_the_label_in_a_badge_or_not_at_all(lines: tuple[Line, Line]) -> None:
    theirs, yours = lines
    as_now = CaptionLayout(CaptionStyle()).laid(yours, WIDTH, 1.0)
    badge, laid = painted(yours, CaptionStyle(own_label=OwnLabel.BADGE))
    assert laid.label is not None and laid.rows[0].top > as_now.rows[0].top  # room
    box = laid.label.lineAt(0).naturalTextRect().translated(20 + BADGE_PAD[0], 15)
    assert box.left() - BADGE_PAD[0] >= 20  # lined up with the text, not out past it
    y = int(box.center().y())
    around = [  # the badge's room either side of its words
        badge.pixelColor(int(box.left()) - 3, y),
        badge.pixelColor(int(box.right()) + 2, y),
    ]
    assert all(near(c, YOU) for c in around), around
    plain, _ = painted(yours, CaptionStyle())
    assert plain.pixelColor(int(box.right()) + 2, y) == PANEL  # no badge as now
    hidden = CaptionLayout(CaptionStyle(own_label=OwnLabel.NONE))
    assert hidden.laid(yours, WIDTH, 1.0).label is None
    assert hidden.laid(theirs, WIDTH, 1.0).label is not None  # theirs keep theirs


@pytest.fixture
def panel(qapp: QApplication) -> Iterator[tuple[LabPanel, list[CaptionLook]]]:
    changes: list[CaptionLook] = []
    view = LookView(CaptionLook(), changes.append)
    shown = LabPanel(view)
    yield shown, changes
    shown.close()
    shiboken6.delete(shown)


def test_the_lab_card_turns_each_on_or_off_and_reset_puts_them_back(
    panel: tuple[LabPanel, list[CaptionLook]],
) -> None:
    shown, _ = panel
    assert shown.own["own_right"].switch.isChecked()  # B: on by default
    for name in ("own_right", "own_tint", "own_bar"):
        before = getattr(shown.view.value.lab, name)
        shown.own[name].switch.click()
        assert getattr(shown.view.value.lab, name) is not before
    shown.own_label.choose(OwnLabel.BADGE)
    assert shown.view.value.lab == replace(
        CaptionLab(),
        own_right=False,  # A: as before
        own_tint=True,
        own_bar=True,
        own_label=OwnLabel.BADGE,
    )
    shown.reset.click()
    assert shown.view.value.lab == CaptionLab()
    checked = {name: row.switch.isChecked() for name, row in shown.own.items()}
    assert checked == {"own_right": True, "own_tint": False, "own_bar": False}
    assert shown.own_label.value() is OwnLabel.AS_NOW


def test_caption_windows_take_the_default_but_not_one_of_the_mic_alone(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
    from polyglotic_desktop.ui_next.views.placement import Rect

    made = []
    try:
        for source in (APP, MIC):
            window = CaptionWindow(
                "w", source, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
                mic=MIC, areas=lambda: [Rect(0, 0, 1920, 1040)],
            )  # fmt: skip
            made.append(window)
        app_window, mic_window = made
        assert app_window.canvas.engine.style.own_right  # B
        assert not mic_window.canvas.engine.style.own_right  # the mic alone
        app_window.set_look(CaptionLook(lab=CaptionLab(own_right=False)))
        assert not app_window.canvas.engine.style.own_right  # A, chosen
    finally:
        for window in made:
            window.close()
            window.deleteLater()
