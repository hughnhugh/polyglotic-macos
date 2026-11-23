"""A joined window stays where it is put and resizes from every edge
(polyglotic-hq 586; the user, 2026-11-21: "Conversation mode can't even be
resized"). On a private desktop a bottom centre joined window sat at the
screen's left - placed again from its first column's centre, half its width
left - so it couldn't widen. The joined minimum now fits each column's
three chip icons (polyglotic-hq 635)."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_joined_window import Store

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import to_rect
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.views.placement import Preset, Rect
from polyglotic_desktop.ui_next.views.preset_menu import PresetItem, PresetMenu

QHD = Rect(0, 0, 2560, 1392)  # 2560 x 1440 without its taskbar
SECOND_APP = SourceId("app-2")
THIRD_APP = SourceId("app-3")
ITEMS = (
    PresetItem("everyday", "Everyday"),
    PresetItem("conversation", "Conversation"),
    PresetItem("video", "Video, film & TV"),
)


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(Store({"targets": ["en"]}), MIC, lambda: [QHD])
    found.set_labels(
        {
            APP: SourceLabel("Discord", "#4dd0e1"),
            SECOND_APP: SourceLabel("Video Player", "#a5d66f"),
            THIRD_APP: SourceLabel("Web Browser", "#f5a97f"),
        },
        "You",
    )
    yield found
    found.close()


def joined(windows: CaptionWindows) -> JoinedWindow:
    assert windows.joined_window is not None
    return windows.joined_window


def test_a_second_app_joining_keeps_a_bottom_centre_window_centred(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.set_captioned([("a", APP)])
    qapp.processEvents()
    first = to_rect(windows.windows["a"].geometry())
    assert first.centre[0] == QHD.centre[0]
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    qapp.processEvents()
    window = joined(windows)
    assert window.choices.preset is Preset.BOTTOM_CENTRE
    assert to_rect(window.geometry()).centre[0] == QHD.centre[0]  # was x 0
    windows.set_captioned([("a", APP), ("b", SECOND_APP), ("c", THIRD_APP)])
    qapp.processEvents()
    assert to_rect(joined(windows).geometry()).centre[0] == QHD.centre[0]


def test_the_joined_minimum_fits_all_icons_for_any_preset(
    windows: CaptionWindows,
    qapp: QApplication,
) -> None:
    style.use_app_text_size("normal")
    windows.set_captioned([("a", APP), ("b", SECOND_APP), ("c", THIRD_APP)])
    windows.set_presets(PresetMenu(ITEMS, "everyday"))
    qapp.processEvents()
    window = joined(windows)
    everyday = window.minimumWidth()
    assert everyday == window._minimum().width
    windows.set_presets(PresetMenu(ITEMS, "conversation"))
    window.resize(everyday, window.height())
    window.show_bands(True)
    qapp.processEvents()
    assert (
        window.width() == window.minimumWidth() == window._minimum().width == everyday
    )
    windows.set_reporting(True)
    windows.set_show_mic_everywhere(True)
    window.resize(window.minimumWidth(), window.height())
    qapp.processEvents()
    assert window.width() == window.minimumWidth() == window._minimum().width
    for column in window.columns:
        assert all(
            chip.isVisible()
            for chip in (column.chip, column.preset_chip, column.timing_chip)
        )
