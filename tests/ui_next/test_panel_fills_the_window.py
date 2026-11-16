"""A caption window's panel is the size the learner set: it doesn't grow
with the text, and a joined window's columns are one panel (the user's
live testing, polyglotic-hq 272: "window resizes / flickers ...
particularly evident when there are joint windows and there is flicker of
one of caption windows")."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates, live_update
from tests.ui_next.test_caption_window import areas, window_of

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import Canvas
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows

SECOND_APP = SourceId("app-2")


@pytest.fixture
def panels(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    """Each window's panel tops, as its paints drew them."""
    drawn: dict[str, list[float]] = {}
    panel = Canvas._panel

    def noted(canvas: Canvas, painter: object, top: float, bottom: float) -> None:
        drawn.setdefault(canvas.owner.key, []).append(top)
        panel(canvas, painter, top, bottom)  # type: ignore[arg-type]

    monkeypatch.setattr(caption_window_module.Canvas, "_panel", noted)
    return drawn


def test_the_panel_fills_the_window_from_its_first_caption(
    qapp: QApplication, panels: dict[str, list[float]]
) -> None:
    window = window_of(qapp, captions=1)
    try:
        assert not window.hovered and not window.band_shown
        for words in range(3):  # a live caption growing under it
            window.receive(live_update(f"live-{words}"))
            window.canvas.repaint()
        assert panels[window.key] and set(panels[window.key][-3:]) == {0.0}
    finally:
        window.close()


@pytest.fixture
def joined(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas)
    found.set_labels(
        {APP: SourceLabel("Chrome", "#a5d66f"), SECOND_APP: SourceLabel("Discord", "#4dd0e1")},
        "You",
    )  # fmt: skip
    found.set_captioned([("a", APP), ("b", SECOND_APP)])
    found.join()
    yield found
    found.close()


def test_a_quiet_column_beside_one_with_captions_shows_its_panel(
    qapp: QApplication, joined: CaptionWindows, panels: dict[str, list[float]]
) -> None:
    window = joined.joined_window
    assert window is not None
    talking, quiet = (joined.windows[k] for k in ("a", "b"))
    for column in (talking, quiet):
        column._intro_until = None  # past its first seconds
    for update in finished_updates(2, APP):
        joined.apply(update)
    qapp.processEvents()
    quiet.canvas.repaint()
    assert not quiet.view.lines
    assert panels.get("b", [])[-1:] == [0.0]  # the whole column, not a hole
