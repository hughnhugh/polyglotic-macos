"""No positioning settings on a caption window: it's moved by hand, and
keeps its place (the user's rehearsal feedback F8, polyglotic-hq 249,
2026-11-08: "you don't really need positioning settings for the captioning
window a bit redundant because you can move it manually")."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui_next.test_caption_window import (
    Store,
    _release_after,
    areas,
    place,
    window_of,
)
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui_next.caption_window import _Drag
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, ROWS, WINDOW_ROWS
from polyglotic_desktop.ui_next.views.placement import Edge, Preset, Rect


def test_no_position_row_in_any_popover() -> None:
    for rows in (ROWS, COLUMN_ROWS, WINDOW_ROWS):
        assert "position" not in rows


def test_no_position_controls(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        assert not [name for name in window.controls if "position" in name]
        window.hovered = True
        window._show_band(True)
        window.toggle_settings()
        popover = window.popover
        assert popover is not None
        words = [b.text() for b in popover.findChildren(QPushButton)]
        assert not any("Position" in w or "Bottom" in w for w in words)
    finally:
        window.close()


def test_a_window_moved_by_hand_keeps_its_place(qapp: QApplication) -> None:
    store = Store({"targets": ["en"]})
    first = CaptionWindows(store, MIC, areas)
    first.set_labels({s: SourceLabel(n, "#4dd0e1") for n, s in THREE}, "You")
    first.set_captioned(THREE[:1])
    (window,) = first.windows.values()
    window.move_by(_Drag(Edge.NONE, QPointF(), place(window)), 300, -300)
    moved = place(window)
    window.mouseReleaseEvent(_release_after(window, Preset.CUSTOM))
    first.save_now()
    first.close()
    again = CaptionWindows(store, MIC, areas)
    again.set_labels({s: SourceLabel(n, "#4dd0e1") for n, s in THREE}, "You")
    again.set_captioned(THREE[:1])
    (back,) = again.windows.values()
    assert place(back) == moved != Rect(480, 650, 960, 300)
    again.close()
