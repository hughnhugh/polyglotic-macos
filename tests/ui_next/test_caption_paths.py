"""Follow, Acquisition, Both in a caption window and the Timing panel
(polyglotic-hq 526, decision 0253)."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_lookup_card import AREA

from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import (
    FOLLOW_SAID_ALPHA,
    FOLLOW_SAID_SCALE,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import TimingPanel
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY
from polyglotic_desktop.ui_next.views.panels import Timing, TimingView


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, lambda: [AREA])
    found.set_captioned([("app", APP)])
    found.windows["app"].set_language("en")
    yield found
    found.close()


def test_follow_puts_the_translation_first_in_a_paced_mode(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.STEADY)
    both = window.canvas.engine.style
    assert not window.follows and window.canvas.ink.alpha == 1.0
    windows.set_path(ReadingPath.FOLLOW)
    assert window.follows
    style = window.canvas.engine.style
    assert style.text_px == pytest.approx(both.text_px * FOLLOW_SAID_SCALE)
    # the translation is larger than what was said was, in full ink
    assert (
        style.text_px * style.translation_factor
        > both.text_px * both.translation_factor
    )
    ink = window.canvas.ink
    assert ink.alpha == FOLLOW_SAID_ALPHA
    assert ink.alpha * ink.translation_alpha == pytest.approx(1.0)
    window.zone.ready()
    assert window.zone.engine.style.text_px == style.text_px  # the live zone too
    windows.set_timing(CaptionMode.WHOLE)  # the path is the paced modes'
    assert not window.follows
    assert window.canvas.engine.style.text_px == both.text_px
    assert window.canvas.ink.alpha == 1.0


def test_follow_needs_a_translation_to_lead(windows: CaptionWindows) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.STEADY)
    windows.set_path(ReadingPath.FOLLOW)
    window.set_language(ORIGINAL_ONLY)  # captions only
    assert not window.follows


def test_the_timing_panel_offers_the_path_in_the_paced_modes(
    qapp: QApplication,
) -> None:
    view = TimingView(Timing(CaptionMode.STEADY, 1.5))
    panel = TimingPanel(view)
    panel.show()
    try:
        assert panel.path_row.isVisible() and not panel.after_row.isVisible()
        assert [b.text() for b in panel.path.buttons] == [
            "Follow",
            "Both",
            "Acquisition",
        ]
        panel.path.choose(ReadingPath.ACQUISITION)
        assert view.value.path is ReadingPath.ACQUISITION
        assert panel.after_row.isVisible()
        panel.after.choose(3.0)
        assert view.value.translation_after == 3.0
        panel.mode.choose(CaptionMode.WHOLE)
        assert not panel.path_row.isVisible() and not panel.after_row.isVisible()
    finally:
        panel.close()


def test_follows_lines_are_whole_and_never_split_across_the_divider(
    qapp: QApplication,
) -> None:
    """The coordinator on 346's pictures, 2026-11-20: Follow's lines
    overlapped the divider, a caption's two lines either side of it. In
    the live zone each translation has what was said over it, no line is
    cut by the zone's top, and the transcript's captions end above it."""
    from tests.ui_next import test_two_zones as zones

    from polyglotic_desktop.core.listening.captions import CaptionKind
    from polyglotic_desktop.core.listening.playout import PlayoutRules

    found = CaptionWindows(None, MIC, lambda: [AREA])
    found.set_cards(False)  # the two zones: the card stack takes their place (0260)
    try:
        found.word_clock = zones.Clock()
        found.set_captioned([("app", APP)])
        found.set_playout(PlayoutRules(delay=0.0, hold_back=0))
        found.set_timing(CaptionMode.STEADY)
        found.set_path(ReadingPath.FOLLOW)
        window = found.windows["app"]
        window.set_language("fr")
        window.resize(1000, 420)
        assert window.follows
        for n in range(1, 10):
            zones.say(found, zones.spoken(n, CaptionKind.LIVE, 9))
            zones.say(found, zones.spoken(n))
            top = window.zone.clear_top
            lines = sorted(
                (rect.top() + row.top + row.layout.lineAt(k).y(), row.row.kind.value)
                for _, laid, rect in window.zone.placed
                for row in laid.rows
                for k in range(row.layout.lineCount())
            )
            shown = [(at, kind) for at, kind in lines if at >= top - 0.5]
            assert shown and shown[0][1] == "original", (n, shown[:3])
            assert not [at for at, _ in lines if at < top - 0.5 < at + 8], n
            divider = float(window.zone.y())
            assert all(r.bottom() <= divider + 0.5 for _, _, r in window.canvas.placed)
    finally:
        found.close()
