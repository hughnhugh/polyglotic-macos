"""The lookup from a transcript window (`ui_next.transcript_window`): the
word under the mouse looked up in the card the caption windows share -
after the hover delay, pinned by a click - offscreen, with made-up
captions and the sample dictionary."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_lookup_card import click
from tests.ui_next.test_lookup_card import find as find_in_window

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_layout import cursor_x
from polyglotic_desktop.ui_next.caption_window import Marked
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.transcript_window import TranscriptList
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)


@pytest.fixture
def both(qapp: QApplication) -> Iterator[tuple[CaptionWindows, Transcripts]]:
    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    windows.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
    transcripts = Transcripts(windows, None, learner=tools, areas=lambda: [AREA])
    windows.set_captioned([("app", APP)])
    for update in finished_updates(30):
        windows.apply(update)
        transcripts.apply(update)
    # Detect, kept: the spoken-language question these captions raise would
    # take the top rows the tests click (polyglotic-hq 350)
    windows.windows["app"].set_spoken_language(None)
    transcripts.show("app")
    shown = transcripts.shown["app"]
    shown.resize(900, 600)
    qapp.processEvents()
    shown.list.repaint()
    yield windows, transcripts
    transcripts.close()
    windows.close()


def listed(transcripts: Transcripts) -> TranscriptList:
    return transcripts.shown["app"].list


def find(shown: TranscriptList, text: str) -> tuple[Marked, QPointF]:
    """`text` in the newest lines drawn, and a point on its first character."""
    for line, laid, at in reversed(shown.drawn):
        for row in laid.rows:
            found = row.row.text.find(text)
            if found < 0:
                continue
            text_line = row.layout.lineForTextPosition(found)
            point = QPointF(
                at.x() + cursor_x(text_line, found) + 3,
                at.y() + row.top + text_line.y() + text_line.height() / 2,
            )
            return Marked(line.key, row.index, found, found + len(text)), point
    raise LookupError(text)


def mouse(shown: TranscriptList, kind: QEvent.Type, pos: QPointF) -> None:
    held = kind == QEvent.Type.MouseButtonPress
    event = QMouseEvent(
        kind,
        pos,
        shown.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    if kind == QEvent.Type.MouseMove:
        shown.mouseMoveEvent(event)
    elif kind == QEvent.Type.MouseButtonRelease:
        shown.mouseReleaseEvent(event)
    else:
        shown.mousePressEvent(event)


def click_list(shown: TranscriptList, pos: QPointF) -> None:
    """A click: pressed and let go where it was - a word is looked up on
    the release, unless the mouse dragged (polyglotic-hq 343)."""
    mouse(shown, QEvent.Type.MouseButtonPress, pos)
    mouse(shown, QEvent.Type.MouseButtonRelease, pos)


def card(windows: CaptionWindows) -> LookupCard:
    assert windows.card is not None
    return windows.card


def test_the_transcript_uses_the_card_the_caption_windows_share(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    windows, transcripts = both
    assert listed(transcripts).card is card(windows)


def test_a_word_rested_on_is_looked_up(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    windows, transcripts = both
    shown, shared = listed(transcripts), card(windows)
    word, point = find(shown, "电脑")
    mouse(shown, QEvent.Type.MouseMove, point)
    assert shown.hovered == word
    shared._hover.timeout.emit()  # the mouse rested
    assert shared.isVisible() and not shared.pinned
    assert shared.model.card().word == "电脑"
    mouse(shown, QEvent.Type.MouseMove, QPointF(shown.width() - 30, 5))
    assert shown.hovered is None and shared._hide.isActive()


def test_a_click_on_a_word_pins_it_with_its_line_for_context(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    windows, transcripts = both
    shown, shared = listed(transcripts), card(windows)
    _, point = find(shown, "游戏")
    click_list(shown, point)
    assert shared.pinned and shared.model.card().actions
    request = shared.request
    assert request is not None and request.word == "游戏"
    assert request.context.translation  # the clause's translation


def test_no_learner_no_lookup(qapp: QApplication) -> None:
    windows = CaptionWindows(None, MIC, lambda: [AREA])
    transcripts = Transcripts(windows, None, areas=lambda: [AREA])
    windows.set_captioned([("app", APP)])
    for update in finished_updates(5):
        transcripts.apply(update)
    transcripts.show("app")
    shown = listed(transcripts)
    qapp.processEvents()
    shown.repaint()
    _, point = find(shown, "电脑")
    mouse(shown, QEvent.Type.MouseMove, point)
    assert shown.hovered is None and shown.card is None
    transcripts.close()
    windows.close()


def test_a_pinned_card_closes_with_the_window_it_came_from(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    """polyglotic-hq 133: a card pinned from a caption window stayed up after
    the window was closed, until Esc, a click elsewhere or 10 s. It goes with
    the window it came from - however that closed - and only with that one."""
    windows, transcripts = both
    shown, shared = listed(transcripts), card(windows)
    caption_window = windows.windows["app"]
    caption_window.show()
    _, point = find(shown, "游戏")
    click_list(shown, point)
    assert shared.pinned
    caption_window.hide()  # not where it came from: it stays
    assert shared.pinned
    transcripts.shown["app"].close()  # its title bar's x, Alt+F4...
    assert not shared.isVisible() and shared.origin is None

    caption_window.setGeometry(480, 600, 960, 360)
    caption_window.show()
    QApplication.processEvents()
    caption_window.canvas.repaint()
    _, at = find_in_window(caption_window, "电脑")
    click(caption_window, at)
    assert shared.pinned and shared.origin is caption_window
    caption_window.close()
    assert not shared.isVisible()
