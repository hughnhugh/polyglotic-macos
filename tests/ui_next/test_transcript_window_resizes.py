"""A transcript window opens larger than its minimum on any screen and at
any text size, and opens at the size the learner left it (polyglotic-hq
586, as the main window: at Windows' 150 % and the app's Larger or Largest
its minimum, 520 x 320 times the text size, was taller than a 1080p
laptop's work area at 150 %, so it opened at its minimum and no edge made it
smaller)."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_joined_window import Store

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import TranscriptChoices

SCREENS = {
    "2560x1440": Rect(0, 0, 2560, 1392),
    "1920x1080": Rect(0, 0, 1920, 1032),
    "laptop_150": Rect(0, 0, 1280, 672),  # 1920 x 1080 at 150 %
}


class Opened:
    """An app's caption window and its transcript, on `area`."""

    def __init__(self, store: Store, area: Rect) -> None:
        self.windows = CaptionWindows(store, MIC, lambda: [area])
        self.windows.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
        self.windows.set_captioned([("a", APP)])
        self.transcripts = Transcripts(self.windows, store, areas=lambda: [area])

    def close(self) -> None:
        self.transcripts.close()
        self.windows.close()


@pytest.fixture
def store() -> Iterator[Store]:
    yield Store({"targets": ["en"]})


@pytest.mark.parametrize("screen", list(SCREENS))
@pytest.mark.parametrize("app_size", list(style.APP_TEXT_SIZES))
@pytest.mark.parametrize("windows_size", [1.0, 1.5])
def test_it_opens_larger_than_its_minimum(
    qapp: QApplication, store: Store, screen: str, app_size: str, windows_size: float
) -> None:
    style.use_text_scale(windows_size)
    style.use_app_text_size(app_size)
    area = SCREENS[screen]
    opened = Opened(store, area)
    try:
        opened.transcripts.show("a")
        qapp.processEvents()
        shown = opened.transcripts.shown["a"]
        assert shown.minimumWidth() < shown.width(), (shown.size(), area)
        assert shown.minimumHeight() < shown.height(), (shown.size(), area)
        assert shown.height() <= area.height and shown.width() <= area.width
    finally:
        opened.close()


def test_it_opens_at_the_size_left(qapp: QApplication, store: Store) -> None:
    opened = Opened(store, SCREENS["1920x1080"])
    try:
        opened.transcripts.show("a")
        qapp.processEvents()
        shown = opened.transcripts.shown["a"]
        shown.resize(900, 640)
        qapp.processEvents()
        assert shown.choices.size == (900, 640)
    finally:
        opened.close()  # saved as it closes
    again = Opened(store, SCREENS["1920x1080"])
    try:
        again.transcripts.show("a")
        qapp.processEvents()
        shown = again.transcripts.shown["a"]
        assert (shown.width(), shown.height()) == (900, 640)
    finally:
        again.close()


def test_its_size_is_kept_with_its_choices() -> None:
    kept = TranscriptChoices(text_size=1.2, rail_open=True, size=(900, 640))
    assert TranscriptChoices.from_stored(kept.to_stored()) == kept
    assert "size" not in TranscriptChoices().to_stored()  # as before 586
    for wrong in ([900], [900, "640"], [0, 640], [True, 640], "900x640", None):
        found = TranscriptChoices.from_stored({"text_size": 1.0, "size": wrong})
        assert found.size is None
