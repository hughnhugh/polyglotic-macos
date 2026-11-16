"""Copying captions from a caption window (polyglotic-hq 333; the user's
feedback 11, 2026-11-13: "Copy to clipboard on all translation/captions"):
all of them, or the one right-clicked - as the transcript's Copy writes
them - to the clipboard and nowhere else. Copy the newest caption went
(polyglotic-hq 339; the user, 2026-11-15: "I dont want copy last line
caption setting"). Real windows, offscreen."""

import logging
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui_next.made_up import EN, ZH, finished_updates, live_update

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.languages import show_mandarin_in_traditional
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, ROWS
from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.placement import Rect

SECOND_APP = SourceId("app-2")
UNTOUCHED = "what was on the clipboard before"


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


def window_of(qapp: QApplication, captions: int, **choices: object) -> CaptionWindow:
    chosen = replace(WindowChoices(), **choices)  # type: ignore[arg-type]
    window = CaptionWindow(
        "Discord.exe", APP, chosen, SourceLabel("Discord", "#4dd0e1"), mic=MIC,
        areas=areas,
    )  # fmt: skip
    for update in finished_updates(captions):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    return window


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    shown = window_of(qapp, 5)
    yield shown
    shown.close()
    shown.deleteLater()
    qapp.processEvents()


def copied() -> str:
    return QGuiApplication.clipboard().text()


def paragraph(window: CaptionWindow, line: Line, who: str = "") -> str:
    """A caption as the transcript's Copy writes it, by hand."""
    caption = window.view.caption(line.key)
    assert caption is not None
    at = caption.started_at.astimezone(datetime.now().astimezone().tzinfo)
    head = f"[{at:%H:%M:%S}]" + (f" {who}:" if who else "")
    translation = caption.translation(EN)
    return f"{head} {caption.original}\n    English: {translation}"


def test_there_is_no_copy_the_newest_caption(
    window: CaptionWindow, qapp: QApplication
) -> None:
    """339: neither the window's settings nor a joined column's offer it."""
    assert "copy" not in window.controls
    assert "copy" not in ROWS and "copy" not in COLUMN_ROWS
    window.hovered = True
    window._show_band(True)
    window.buttons["settings"].click()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    texts = [r.text() for r in popover.rows.values() if isinstance(r, QPushButton)]
    assert "Copy all captions" in texts
    assert not any("newest" in text for text in texts)
    popover.hide()


def test_copy_all_copies_every_finished_caption_it_holds_oldest_first(
    window: CaptionWindow,
) -> None:
    window.controls["copy_all"].trigger()
    lines = window.view.lines
    assert len(lines) == 5
    assert copied() == "\n\n".join(paragraph(window, ln) for ln in lines) + "\n"
    assert window.notice.text() == "Copied 5 captions"


def test_a_caption_still_being_heard_isnt_copied(
    window: CaptionWindow, qapp: QApplication
) -> None:
    window.view.apply(live_update("still-speaking"))
    window.apply_changed(new_caption=True)
    qapp.processEvents()
    assert window.view.lines[-1].live
    finished = [ln for ln in window.view.lines if not ln.live]
    window.controls["copy_all"].trigger()
    assert copied().count("    English: ") == len(finished) == 5


def test_original_only_copies_what_was_said_alone(qapp: QApplication) -> None:
    window = window_of(qapp, 3, translate_into="")
    try:
        window.controls["copy_all"].trigger()
        text = copied()
        assert "English:" not in text and len(text.strip().split("\n\n")) == 3
        caption = window.view.caption(window.view.lines[0].key)
        assert caption is not None and caption.original in text
    finally:
        window.close()
        window.deleteLater()


def test_the_learners_own_speech_is_copied_as_you(qapp: QApplication) -> None:
    window = window_of(qapp, 2, show_mic=True)
    try:
        window.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
        mine = finished_updates(1, MIC, start=50)[0]
        assert window.view.apply(mine)
        window.apply_changed(new_caption=True)
        window.controls["copy_all"].trigger()
        newest = window.view.lines[-1]
        assert newest.by_you
        assert copied().endswith("\n\n" + paragraph(window, newest, "You") + "\n")
    finally:
        window.close()
        window.deleteLater()


def test_a_right_click_on_a_caption_copies_that_one(
    window: CaptionWindow, qapp: QApplication
) -> None:
    window.canvas.repaint()
    qapp.processEvents()
    line, _, rect = window.canvas.placed[0]  # not the newest
    assert line.key != window.view.lines[-1].key
    at = QPointF(rect.center())
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, at, window.mapToGlobal(at),
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    window.mousePressEvent(press)
    assert copied() == paragraph(window, line) + "\n"
    assert window.notice.text() == "Copied 1 caption"


def test_a_locked_window_copies_nothing(
    window: CaptionWindow, qapp: QApplication
) -> None:
    window.canvas.repaint()
    window.set_locked(True)
    _, _, rect = window.canvas.placed[0]
    at = QPointF(rect.center())
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, at, window.mapToGlobal(at),
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    window.mousePressEvent(press)
    assert copied() == UNTOUCHED


def test_with_nothing_finished_it_says_so_and_leaves_the_clipboard(
    qapp: QApplication,
) -> None:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    window = window_of(qapp, 0)
    try:
        window.controls["copy_all"].trigger()
        assert copied() == UNTOUCHED
        assert window.notice.text() == "Nothing to copy yet"
    finally:
        window.close()
        window.deleteLater()


def test_the_settings_offer_both_and_close_once_copied(
    window: CaptionWindow, qapp: QApplication
) -> None:
    assert ROWS.index("copy_all") < ROWS.index("transcript")
    assert "copy_all" in COLUMN_ROWS
    window.hovered = True
    window._show_band(True)
    window.buttons["settings"].click()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    row = popover.rows["copy_all"]
    assert isinstance(row, QPushButton) and row.text() == "Copy all captions"
    row.click()
    assert not popover.isVisible()
    assert copied().count("    English: ") == 5


def test_a_joined_column_copies_its_own_and_the_window_says_so(
    qapp: QApplication,
) -> None:
    class Store:
        def __init__(self) -> None:
            self.values: dict[str, object] = {"targets": ["en"]}

        def load(self) -> dict[str, object]:
            return dict(self.values)

        def save(self, values: object) -> None:
            assert isinstance(values, dict)
            self.values = dict(values)

    windows = CaptionWindows(Store(), MIC, areas)
    try:
        windows.set_labels(
            {
                APP: SourceLabel("Discord", "#4dd0e1"),
                SECOND_APP: SourceLabel("Video Player", "#a5d66f"),
            },
            "You",
        )
        windows.set_captioned([("a", APP), ("b", SECOND_APP)])
        for update in finished_updates(3, APP):
            windows.apply(update)
        for update in finished_updates(2, SECOND_APP, start=10):
            windows.apply(update)
        windows.join("a")
        qapp.processEvents()
        joined = windows.joined_window
        assert joined is not None
        second = joined.columns[1]
        assert second.source == SECOND_APP
        second.controls["copy_all"].trigger()
        assert len(copied().strip().split("\n\n")) == 2  # its own two, not three
        assert copied() == second.copy_text(second.view.lines)
        assert joined.notice.isVisible() and joined.notice.text() == "Copied 2 captions"
    finally:
        windows.close()
        qapp.processEvents()


def test_nothing_copied_is_logged(
    window: CaptionWindow, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    window.controls["copy_all"].trigger()
    for line in window.view.lines:
        caption = window.view.caption(line.key)
        assert caption is not None
        assert caption.original not in caplog.text


def test_a_second_language_line_is_copied_under_its_language(
    qapp: QApplication,
) -> None:
    """English heard in a window into English, Chinese its second language:
    the server keeps the Chinese line under English; Copy named it English
    (polyglotic-hq 432)."""
    window = window_of(qapp, 0)
    try:
        window.set_second_languages({EN: ZH})
        said = CaptionUpdate(
            CaptionId("c1"),
            APP,
            CaptionKind.FINISHED,
            clauses=(Clause("See you tomorrow.", translations={EN: "明天见。"}),),
            language=EN,
            languages_heard=(EN,),
        )
        window.view.apply(said)
        window.apply_changed(new_caption=True)
        window.controls["copy_all"].trigger()
        assert copied().endswith(
            "See you tomorrow.\n    Chinese (Simplified): 明天见。\n"
        )
    finally:
        window.close()
        window.deleteLater()


def test_traditional_lines_are_copied_as_traditional(qapp: QApplication) -> None:
    """ "Show Mandarin in: Traditional": each Chinese line arrives converted
    (polyglotic-hq 432), and Copy names it by its script, not "Chinese
    (Simplified)" (433)."""
    window = window_of(qapp, 0)
    show_mandarin_in_traditional(True)
    try:
        window.set_second_languages({EN: ZH})
        said = CaptionUpdate(
            CaptionId("c1"),
            APP,
            CaptionKind.FINISHED,
            clauses=(Clause("See you tomorrow.", translations={EN: "明天見。"}),),
            language=EN,
            languages_heard=(EN,),
        )
        window.view.apply(said)
        window.apply_changed(new_caption=True)
        window.controls["copy_all"].trigger()
        assert copied().endswith(
            "See you tomorrow.\n    Chinese (Traditional): 明天見。\n"
        )
    finally:
        show_mandarin_in_traditional(False)
        window.close()
        window.deleteLater()
