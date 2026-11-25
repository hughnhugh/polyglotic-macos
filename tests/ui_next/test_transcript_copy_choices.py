"""A transcript line's right-click Copy choices (polyglotic-hq 333): the
line as Copy all writes it, what was said alone, or its translation alone
- the text that lands on the clipboard for each. A real window,
offscreen."""

from collections.abc import Callable, Iterator
from datetime import datetime
from functools import partial

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.toast import hide_toast, toast_text
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.transcript import Transcript, TranscriptChoices

DISCORD = SourceLabel("Discord", "#4dd0e1")


@pytest.fixture
def window(qapp: QApplication) -> Iterator[TranscriptWindow]:
    QGuiApplication.clipboard().setText("before")
    transcript = Transcript(APP, EN, mic=MIC)
    for update in finished_updates(4):
        transcript.apply(update)
    shown = TranscriptWindow("Discord.exe", transcript, DISCORD, TranscriptChoices())
    shown.animate = False
    shown.resize(900, 600)
    shown.show()
    qapp.processEvents()
    yield shown
    shown.close()
    shown.deleteLater()
    qapp.processEvents()


def menu_texts(window: TranscriptWindow) -> list[str]:
    menu = window.list.line_menu(window.transcript.lines[1])
    try:
        return [action.text() for action in menu.actions()]
    finally:
        menu.deleteLater()


def choose(window: TranscriptWindow, text: str) -> str:
    """The second line's menu item `text`, chosen: what was copied."""
    menu = window.list.line_menu(window.transcript.lines[1])
    try:
        next(a for a in menu.actions() if a.text() == text).trigger()
    finally:
        menu.deleteLater()
    return QGuiApplication.clipboard().text()


def test_a_lines_menu_offers_the_three_copies(window: TranscriptWindow) -> None:
    """And no "Looks wrong?" (polyglotic-hq 339)."""
    assert menu_texts(window) == [
        "Copy",
        "Copy what was said",
        "Copy the translation",
    ]


def test_each_copy_puts_its_own_text_on_the_clipboard(
    window: TranscriptWindow,
) -> None:
    line = window.transcript.lines[1]
    [caption] = window.transcript.captions.captions_of([line])
    at = caption.started_at.astimezone(datetime.now().astimezone().tzinfo)
    translation = caption.translation(EN)
    assert choose(window, "Copy") == (
        f"[{at:%H:%M:%S}] {caption.original}\n    English: {translation}\n"
    )
    assert choose(window, "Copy what was said") == caption.original
    assert choose(window, "Copy the translation") == translation


def test_original_only_has_no_translation_to_copy(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    window.transcript.set_language(None, None)
    qapp.processEvents()
    assert "Copy the translation" not in menu_texts(window)
    [caption] = window.transcript.captions.captions_of([window.transcript.lines[1]])
    assert choose(window, "Copy what was said") == caption.original


def said_after(do: Callable[[], object]) -> str:
    """What shows in the themed toast after `do`: "" if none."""
    hide_toast()
    do()
    return toast_text()


def test_each_copy_says_copied(window: TranscriptWindow, qapp: QApplication) -> None:
    """The transcript's menu copies show the themed "Copied to clipboard"
    toast (polyglotic-hq 950); Copy all on the strip says "✓ Copied" on
    itself for a moment, as the lookup card's Copy does."""
    for text in ("Copy", "Copy what was said", "Copy the translation"):
        assert said_after(partial(choose, window, text)) == "Copied to clipboard", text
    button = window.buttons["copy"]
    width = button.width()
    button.click()
    qapp.processEvents()
    assert button.text() == "✓ Copied" and button.width() >= width
    assert QGuiApplication.clipboard().text() == window.text()
    window._copied_shown.timeout.emit()
    qapp.processEvents()
    assert button.text() == "Copy all"
    more = window.buttons["more"].menu()
    assert more is not None
    copy_all = next(a for a in more.actions() if a.text() == "Copy all")
    assert said_after(copy_all.trigger) == "Copied to clipboard"


def test_a_selection_copied_from_its_menu_says_so_and_ctrl_c_doesnt(
    window: TranscriptWindow,
) -> None:
    listed = window.list
    listed.select_all()
    menu = listed.menu_at(0)
    assert menu is not None
    try:
        copy = next(a for a in menu.actions() if a.text() == "Copy")
        assert said_after(copy.trigger) == "Copied to clipboard"
    finally:
        menu.deleteLater()
    assert said_after(listed.copy_selection) == ""  # bare copy_selection()
    assert said_after(listed.copy_by_key) == "Copied to clipboard"  # Ctrl+C's
