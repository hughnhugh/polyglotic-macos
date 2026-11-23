"""The Strip is gone (the user's live testing, polyglotic-hq 272: "The
strip toggle feels bad, probably remove that"): no Panel | Strip in any
window's settings, and a window - or a joined window - saved as a Strip
opens as a panel, at its saved size."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import SEPARATE
from tests.ui_next.test_caption_window import Store
from tests.ui_next.test_joined_window import THREE, areas, joined

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_popover import (
    COLUMN_ROWS,
    ROWS,
    WINDOW_ROWS,
)
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY

SAVED_AS_STRIP: dict[str, object] = {
    "targets": ["en"],
    STORED_KEY: {
        "windows": {
            "a": {"mode": "strip", "position": "custom", "geometry": [100, 700, 700, 64]},
            "b": {"mode": "strip"},
            "c": {"mode": "panel"},
        },
        "last": {"mode": "strip"},
        "joined": {"on": False, "mode": "strip"},
    },
}  # fmt: skip


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(Store(SAVED_AS_STRIP), MIC, areas)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    found.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
    found.set_captioned(THREE)
    qapp.processEvents()
    yield found
    found.close()


def test_no_window_offers_panel_or_strip(windows: CaptionWindows) -> None:
    assert "mode" not in ROWS + COLUMN_ROWS + WINDOW_ROWS
    for window in windows.windows.values():
        assert "strip" not in window.controls and "panel" not in window.controls
    windows.join()
    assert not {"strip", "panel"} & set(joined(windows).controls)


def test_a_window_saved_as_a_strip_opens_as_a_panel_at_its_place(
    windows: CaptionWindows,
) -> None:
    first = windows.windows["a"]
    g = first.geometry()  # a panel's height, grown up from the Strip's bottom
    assert (g.x(), g.y(), g.width(), g.height()) == (100, 464, 700, 300)
    windows.join()  # a joined window saved as a Strip, too
    window = joined(windows)
    assert window.height() >= 120
    assert all(c.height() == window.height() for c in window.columns)


def test_the_choices_saved_again_have_no_mode(windows: CaptionWindows) -> None:
    windows.save_now()
    store = windows._store
    assert isinstance(store, Store)
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict)
    assert all("mode" not in each for each in saved["windows"].values())
    assert "mode" not in saved["joined"]
