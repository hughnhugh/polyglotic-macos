"""Hovering a caption block, side Save/Copy buttons, Ctrl+C and the themed
"Copied to clipboard" / "Saved" toast (polyglotic-hq 950).

Real windows, offscreen; made-up captions and the sample Chinese dictionary.
"""

import logging
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next import test_lookup_card as cards
from tests.ui_next.test_copy_from_the_transcript import (
    drag as transcript_drag,
)
from tests.ui_next.test_copy_from_the_transcript import (
    press_copy as transcript_ctrl_c,
)
from tests.ui_next.test_lookup_card import Keys, card, find, mouse, window
from tests.ui_next.test_select_captions import (
    SAID,
    ctrl_c,
    drag,
    last_two,
    point,
)
from tests.ui_next.test_transcript_lookup import both, listed
from tests.ui_next.test_transcript_lookup import find as transcript_find

from polyglotic_desktop.core.shared.tunables import declarations
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.toast import (
    Toast,
    current_toast,
    hide_toast,
    toast_text,
)
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.card_window_defaults import (
    CAPTION_HOVER_ALPHA,
    TOAST_DURATION_SEC,
    TOAST_FADE_SEC,
)

windows = cards.windows
keys = cards.keys
problem = cards.problem
__all__ = ["both", "keys", "problem", "windows"]

UNTOUCHED = "what was on the clipboard before"


@pytest.fixture(autouse=True)
def clean_clipboard_and_toast() -> None:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    hide_toast()


def _grab(widget: QWidget) -> QImage:
    return widget.grab().toImage()


def _mean_luma(image: QImage, x: int, y: int) -> float:
    pixel = QColor(image.pixel(x, y))
    return 0.2126 * pixel.red() + 0.7152 * pixel.green() + 0.0722 * pixel.blue()


# -- hover tint & side Save / Copy buttons ---------------------------------------------


def test_hover_tints_only_that_caption_and_shows_save_and_copy_without_layout_shift(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    shown = window(windows)
    shown.canvas.repaint()
    qapp.processEvents()
    before_width = shown.canvas._width()
    before_placed = [(ln.key, rect) for ln, _, rect in shown.canvas.placed]
    assert len(before_placed) >= 2
    first_line, _, first_rect = shown.canvas.placed[-2]
    second_line, _, second_rect = shown.canvas.placed[-1]
    assert first_line.key != second_line.key

    # Sample an empty margin spot inside each caption block (no glyphs there).
    sample_first = (round(first_rect.right()) - 4, round(first_rect.bottom()) - 3)
    sample_second = (round(second_rect.right()) - 4, round(second_rect.bottom()) - 3)
    baseline = _grab(shown.canvas)
    first_before = _mean_luma(baseline, *sample_first)
    second_before = _mean_luma(baseline, *sample_second)

    mouse(shown, "move", first_rect.center(), held=False)
    shown.canvas.repaint()
    qapp.processEvents()

    assert shown.hovered_line == first_line.key
    assert shown.line_actions.isVisible()
    assert shown.line_save_button.isVisible()
    assert shown.line_copy_button.isVisible()
    assert shown.line_save_button.toolTip() == "Save caption"
    assert shown.line_copy_button.toolTip() == "Copy caption"
    assert shown.line_save_button.accessibleName() == "Save caption"
    assert shown.line_copy_button.accessibleName() == "Copy caption"
    # Zero layout shift: canvas width and placed caption geometry stay identical.
    assert shown.canvas._width() == before_width
    assert [(ln.key, rect) for ln, _, rect in shown.canvas.placed] == before_placed

    # Only the hovered caption block is tinted; the other stays untouched.
    tinted = _grab(shown.canvas)
    assert _mean_luma(tinted, *sample_first) > first_before + 3.0
    assert abs(_mean_luma(tinted, *sample_second) - second_before) < 1.0

    # Leaving clears both tint and side buttons.
    shown.leaveEvent(None)
    shown.canvas.repaint()
    qapp.processEvents()
    assert shown.hovered_line is None
    assert not shown.line_actions.isVisible()
    after_leave = _grab(shown.canvas)
    assert abs(_mean_luma(after_leave, *sample_first) - first_before) < 1.0


def test_hover_tint_honours_panel_opacity_and_stays_off_over_video_subtitles(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    shown = window(windows)
    shown.canvas.repaint()
    _, _, rect = shown.canvas.placed[-1]
    sample = (round(rect.right()) - 4, round(rect.bottom()) - 3)

    # Zero panel opacity -> no painted tint box.
    windows.set_look(replace(windows.look, opacity=0.0))
    shown.canvas.repaint()
    before = _grab(shown.canvas)
    mouse(shown, "move", rect.center(), held=False)
    shown.canvas.repaint()
    after = _grab(shown.canvas)
    assert abs(_mean_luma(after, *sample) - _mean_luma(before, *sample)) < 0.5

    # Video subtitles -> neither hover block nor side buttons appear.
    windows.set_look(replace(windows.look, opacity=0.85))
    shown.set_video(True)
    shown.canvas.repaint()
    qapp.processEvents()
    assert shown.hovered_line is None
    assert not shown.line_actions.isVisible()
    if shown.canvas.placed:
        mouse(shown, "move", shown.canvas.placed[-1][2].center(), held=False)
        qapp.processEvents()
        assert shown.hovered_line is None
        assert not shown.line_actions.isVisible()


def test_word_hover_lookup_still_opens_inside_hovered_caption(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    shown, shared = window(windows), card(windows)
    word, at = find(shown, "电脑")
    mouse(shown, "move", at, held=False)
    qapp.processEvents()
    assert shown.hovered_line == word.key
    assert shown.line_actions.isVisible()
    assert shown.canvas.hovered == word
    assert shared._pending is not None and shared._pending.word == "电脑"
    shared._show_pending()
    assert shared.isVisible() and shared.model.word == "电脑"


# -- side Copy and Save buttons --------------------------------------------------------


def test_copy_button_copies_caption_shows_toast_and_logs_nothing(
    windows: CaptionWindows, qapp: QApplication, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    shown = window(windows)
    shown.canvas.repaint()
    target_line, _, rect = shown.canvas.placed[-2]
    mouse(shown, "move", rect.center(), held=False)
    qapp.processEvents()
    assert shown.line_copy_button.isVisible()

    shown.line_copy_button.click()
    qapp.processEvents()

    caption = shown.view.caption(target_line.key)
    assert caption is not None
    # the caption's own words, nothing else (the user, 2026-11-25): no time,
    # no speaker, no translation line
    assert QGuiApplication.clipboard().text() == caption.original.strip()
    assert "[" not in QGuiApplication.clipboard().text()
    assert len(QGuiApplication.clipboard().text().splitlines()) == 1
    assert toast_text() == "Copied to clipboard"
    assert caption.original not in caplog.text


def test_save_button_saves_caption_to_study_and_shows_saved_toast(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    shown = window(windows)
    shown.canvas.repaint()
    target_line, _, rect = shown.canvas.placed[-2]
    vocabulary = cards.tools(windows).vocabulary
    assert vocabulary.sentences == []

    mouse(shown, "move", rect.center(), held=False)
    qapp.processEvents()
    assert shown.line_save_button.isVisible() and shown.line_save_button.isEnabled()

    shown.line_save_button.click()
    qapp.processEvents()

    (saved,) = vocabulary.sentences
    assert saved.category_id == "saved"
    caption = shown.view.caption(target_line.key)
    assert caption is not None
    assert saved.original == caption.original
    assert saved.translation
    assert toast_text() == "Saved"


# -- Ctrl+C (selection and hovered caption, including over another app) ---------------


def test_ctrl_c_copies_selected_text_and_shows_toast_even_over_another_app(
    windows: CaptionWindows, keys: Keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = window(windows)
    first, second = last_two(shown)
    drag(shown, point(shown, first.key, SAID, 0), point(shown, second.key, SAID, 2))
    expected = shown.held.text()
    assert expected

    # Case 1: Polyglotic has focus (Qt key event).
    holder = QWidget()
    ctrl_c(holder)
    assert QGuiApplication.clipboard().text() == expected
    assert toast_text() == "Copied to clipboard"
    holder.deleteLater()

    # Case 2: Another app (browser/game) has focus -> OS key state poll.
    QGuiApplication.clipboard().setText(UNTOUCHED)
    hide_toast()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    keys.held.add("copy")
    shown.held._look_at_keys()
    keys.held.discard("copy")
    assert QGuiApplication.clipboard().text() == expected
    assert toast_text() == "Copied to clipboard"


def test_ctrl_c_with_no_selection_copies_hovered_caption(
    windows: CaptionWindows, keys: Keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = window(windows)
    shown.canvas.repaint()
    target_line, _, rect = shown.canvas.placed[-2]
    caption = shown.view.caption(target_line.key)
    assert caption is not None
    expected = caption.original.strip()  # the words only
    mouse(shown, "move", rect.center(), held=False)
    assert shown.held.selection is None
    assert shown.hovered_line == target_line.key

    # Case 1: Qt Ctrl+C key event on the window / app.
    holder = QWidget()
    ctrl_c(holder)
    assert QGuiApplication.clipboard().text() == expected
    assert toast_text() == "Copied to clipboard"
    holder.deleteLater()

    # Case 2: another app has the keyboard -> its Ctrl+C is its own; the
    # hovered caption must not overwrite what was copied there.
    QGuiApplication.clipboard().setText(UNTOUCHED)
    hide_toast()
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    keys.held.add("copy")
    shown._look_at_line_keys()
    keys.held.discard("copy")
    assert QGuiApplication.clipboard().text() == UNTOUCHED


def test_ctrl_c_in_transcript_copies_selection_or_hovered_caption(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    shown = listed(both[1])
    # With no selection, hovering a caption and pressing Ctrl+C copies that caption.
    line, rect = shown.placed[-2]
    mouse_move = QEvent.Type.MouseMove
    from tests.ui_next.test_transcript_lookup import mouse as transcript_mouse

    transcript_mouse(shown, mouse_move, rect.center())
    assert not shown.hasSelectedText()
    assert shown.hovered_line == line.key
    transcript_ctrl_c(shown)
    copied_line = QGuiApplication.clipboard().text()
    assert line.rows[0].text in copied_line
    assert toast_text() == "Copied to clipboard"

    # With a selection, Ctrl+C copies the selection and shows the toast.
    hide_toast()
    _, start = transcript_find(shown, "电脑")
    _, end = transcript_find(shown, "游戏")
    transcript_drag(shown, start, end)
    selected = shown.selectedText()
    assert selected
    transcript_ctrl_c(shown)
    assert QGuiApplication.clipboard().text() == selected
    assert toast_text() == "Copied to clipboard"


# -- toast fade, lifecycle and tunables ------------------------------------------------


def test_toast_text_fades_and_ends(
    windows: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = window(windows)
    now = [100.0]
    monkeypatch.setattr(
        "polyglotic_desktop.ui_next.toast._reduced_motion", lambda: False
    )
    toast = Toast(shown, clock=lambda: now[0])
    try:
        toast.show_message("Copied to clipboard", shown, duration=1.5, fade=0.3)
        qapp.processEvents()
        assert toast.isVisible()
        assert toast.text() == "Copied to clipboard"
        assert toast.opacity() == 1.0
        assert not toast.isActiveWindow()
        assert toast.focusPolicy() == Qt.FocusPolicy.NoFocus

        # Start fading when hold expires.
        toast._begin_fade()
        now[0] += 0.15
        toast._step_fade()
        assert toast.isVisible()
        assert 0.0 < toast.opacity() < 1.0

        # End of fade hides the toast cleanly.
        now[0] += 0.2
        toast._step_fade()
        assert not toast.isVisible()
        assert toast.opacity() == 0.0
    finally:
        toast.dismiss()
        toast.deleteLater()
        qapp.processEvents()


def test_hover_and_toast_tunables_are_declared() -> None:
    declared = declarations()
    for item in (CAPTION_HOVER_ALPHA, TOAST_DURATION_SEC, TOAST_FADE_SEC):
        assert item.name in declared
    assert TOAST_DURATION_SEC.default == pytest.approx(1.5)
    assert current_toast() is None


def test_your_own_speech_has_its_save_and_copy_on_the_left(
    windows: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Your speech sits on the right with its header there (own_right, the
    default): the pill goes on the left of the caption so it never covers
    the text (the user, 2026-11-25); another caption keeps it on the right."""
    shown = window(windows)
    shown.canvas.repaint()
    line, _, rect = shown.canvas.placed[-2]
    mouse(shown, "move", rect.center(), held=False)
    qapp.processEvents()
    assert shown.canvas.engine.style.own_right
    theirs = shown.line_actions.geometry()
    assert theirs.center().x() > rect.center().x()

    yours = replace(line, by_you=True)
    placed = shown.placed
    monkeypatch.setattr(
        shown,
        "placed",
        lambda: [(yours if ln.key == line.key else ln, x, r) for ln, x, r in placed()],
    )
    shown._place_line_actions()
    mine = shown.line_actions.geometry()
    assert mine.center().x() < rect.center().x()
    assert mine.left() <= round(rect.left()) + 2


def test_the_save_and_copy_buttons_corners_follow_the_pills_on_the_scale(
    windows: CaptionWindows,
) -> None:
    """polyglotic-hq 999: the buttons' corners were 4 px - the pill's 6 less
    2 - off the interface's radii (the UI lab's design check) and not the
    pill's curve inside its 1 px border and 2 px margin. They're 3 now."""
    from tools.ui_lab.design import RADII

    from polyglotic_desktop.ui_next import caption_window as cw

    shown = window(windows)
    sheet = shown.line_actions.styleSheet()
    pill = sheet[: sheet.index("QToolButton {")]
    buttons = sheet[sheet.index("QToolButton {") :]
    assert f"border-radius: {cw.MARK_RADIUS}px" in pill
    row = shown.line_actions.layout()
    assert row is not None
    margins = row.contentsMargins()
    border = int(pill.split("border: ")[1].split("px")[0])
    inner = cw.MARK_RADIUS - border - margins.left()
    assert f"border-radius: {inner}px;" in buttons
    assert inner in RADII
