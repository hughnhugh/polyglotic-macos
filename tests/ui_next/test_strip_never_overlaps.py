"""No item on a caption window's strip covers another, nor does the notice
line - the word hint - at any width (polyglotic-hq 586, found by 584: in a
732 px window under Video, "Click any word to look it up" sat over the
preset chip "Video, film & TV": the hint's gap was measured to the buttons,
not the chip before them). The window can't be made narrower than its
strip's items need side by side."""

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import (
    MIN_PANEL,
    CaptionWindow,
    least_size,
    word_hint,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetItem, PresetMenu

ITEMS = (
    PresetItem("everyday", "Everyday"),
    PresetItem("conversation", "Conversation"),
    PresetItem("video", "Video, film & TV"),
)


def on_window(window: CaptionWindow, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(window, widget.rect().topLeft()), widget.size())


def strip_items(window: CaptionWindow) -> list[QWidget]:
    items: list[QWidget] = [window.tag, window.chip, window.preset_chip]
    items += [window.timing_chip, window.mic_button]  # 593's / 651's
    items += list(window.buttons.values())
    return [item for item in items if not item.isHidden()]


@pytest.mark.parametrize("app_size", ["smaller", "normal", "largest"])
@pytest.mark.parametrize("preset", ["everyday", "conversation", "video"])
def test_nothing_on_the_strip_covers_anything_else(
    qapp: QApplication, app_size: str, preset: str
) -> None:
    style.use_app_text_size(app_size)
    window = window_of(qapp, captions=0)
    try:
        window.set_presets(PresetMenu(ITEMS, preset))
        window.set_respeaking(True, "Right Ctrl")  # its button too (593)
        window.set_reporting(True)
        window.set_show_mic(True)
        window.set_hint(word_hint())
        window.hovered = True
        window._show_band(True)
        least = window._minimum().width
        for width in range(least, 1301):
            window.resize(width, 300)
            assert window.notice.isVisible()
            items = strip_items(window)
            places = [on_window(window, item) for item in items]
            for i, (item, place) in enumerate(zip(items, places, strict=True)):
                assert window.band.geometry().contains(place), (width, item)
                if item is not window.tag:  # the label is what shortens
                    assert item.width() >= item.sizeHint().width(), (width, item)
                for other, there in zip(items[i + 1 :], places[i + 1 :], strict=True):
                    assert not place.intersects(there), (width, item, other)
            notice = window.notice.geometry()
            for item, place in zip(items, places, strict=True):
                assert not notice.intersects(place), (width, preset, item)
    finally:
        window.close()
        window.deleteLater()


def test_the_preset_icon_counts_in_the_minimum_at_any_label_width(
    qapp: QApplication,
) -> None:
    style.use_app_text_size("normal")
    window = window_of(qapp)
    try:
        window.set_presets(PresetMenu(ITEMS, "everyday"))
        everyday = window.strip_least()
        window.set_presets(PresetMenu(ITEMS, "video"))
        assert window.strip_least() == everyday
        least = least_size(MIN_PANEL).width
        assert window._minimum().width == max(least, window.strip_least())
        window.hovered = True
        window._show_band(True)
        window.resize(window.strip_least(), 300)
        assert window.preset_chip.isVisible()
        assert not window.preset_chip.icon().isNull()
        window.resize(window.strip_least() - 1, 300)
        assert window.timing_chip.isHidden()
    finally:
        window.close()
        window.deleteLater()
