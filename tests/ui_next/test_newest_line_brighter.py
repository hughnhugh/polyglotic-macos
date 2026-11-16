"""The newest caption at full ink, the ones before it a step back - 253's
option B: no fade, no motion (the user's rehearsal feedback F21,
polyglotic-hq 249, 2026-11-08: "Not actually fade in and fade out but
visibly obvious from a subtle contrast different")."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_caption_window import window_of
from tools.ui_lab.checks import contrast
from tools.ui_lab.lab import SCENE

from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, Ink
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, high_contrast
from polyglotic_desktop.ui_next.views.arrivals import (
    OLDER_ALPHA,
    OLDER_TRANSLATION_ALPHA,
    Arrival,
    older_alphas,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook


def _inks(window: CaptionWindow, monkeypatch: pytest.MonkeyPatch) -> dict[int, Ink]:
    """Each caption painted, by its key: the ink it was drawn with."""
    drawn: dict[int, Ink] = {}
    paint = CaptionLayout.paint

    def recorded(self, painter, line, laid, at, ink, marks=None):
        drawn[line.key] = ink
        return paint(self, painter, line, laid, at, ink, marks)

    monkeypatch.setattr(CaptionLayout, "paint", recorded)
    window.canvas.repaint()
    monkeypatch.setattr(CaptionLayout, "paint", paint)
    return drawn


def test_the_newest_caption_is_full_and_older_ones_step_back(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = window_of(qapp, captions=12)
    try:
        assert window.look.arrival is Arrival.STEP_AND_SLIDE  # D: it steps too
        drawn = _inks(window, monkeypatch)
        newest = window.view.lines[-1].key
        assert len(drawn) >= 2
        assert (drawn[newest].alpha, drawn[newest].translation_alpha) == (1.0, 1.0)
        for key, ink in drawn.items():
            if key != newest:
                assert ink.alpha == OLDER_ALPHA
                assert ink.alpha * ink.translation_alpha == pytest.approx(
                    OLDER_TRANSLATION_ALPHA
                )
    finally:
        window.close()


def test_scrolled_back_every_caption_is_full_until_back_at_the_newest(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scrolled back, the learner is reading deliberately: every line at
    full ink (249's detail, taken with DECISIONS.md #104; 267). Back at the
    newest, the step returns."""
    window = window_of(qapp, captions=12)
    try:
        window.canvas.scroll_by(300)
        assert not window.view.scroll.following
        drawn = _inks(window, monkeypatch)
        assert len(drawn) >= 2
        assert {(ink.alpha, ink.translation_alpha) for ink in drawn.values()} == {
            (1.0, 1.0)
        }
        window.go_live()
        drawn = _inks(window, monkeypatch)
        newest = window.view.lines[-1].key
        assert all(ink.alpha == OLDER_ALPHA for k, ink in drawn.items() if k != newest)
    finally:
        window.close()


@pytest.mark.parametrize("arrival", list(Arrival))
def test_a_new_caption_arrives_at_full_ink_without_a_fade(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, arrival: Arrival
) -> None:
    """Both arrivals: the new caption is at full ink from its first frame
    (F21: "not fades"); the one before it steps back at once."""
    window = window_of(qapp, captions=3, look=CaptionLook(arrival=arrival))
    try:
        window.canvas.repaint()
        (new,) = finished_updates(1, start=3)
        window.view.apply(new)
        window.apply_changed(new_caption=True)
        drawn = _inks(window, monkeypatch)
        newest = window.view.lines[-1].key
        assert (drawn[newest].alpha, drawn[newest].translation_alpha) == (1.0, 1.0)
        assert drawn[newest - 1].alpha == OLDER_ALPHA
    finally:
        window.close()


def test_the_step_while_following() -> None:
    assert older_alphas(high_contrast=False, following=True) == (
        OLDER_ALPHA,
        OLDER_TRANSLATION_ALPHA,
    )


def test_none_while_scrolled_back() -> None:
    assert older_alphas(high_contrast=False, following=False) == (1.0, 1.0)


def test_none_with_windows_high_contrast(monkeypatch: pytest.MonkeyPatch) -> None:
    assert older_alphas(high_contrast=True, following=True) == (1.0, 1.0)
    assert not high_contrast()
    high = SimpleNamespace(
        contrastPreference=lambda: Qt.ContrastPreference.HighContrast
    )
    hints = SimpleNamespace(accessibility=lambda: high)
    fake = SimpleNamespace(styleHints=lambda: hints)
    monkeypatch.setattr(caption_window_module, "QGuiApplication", fake)
    assert high_contrast()


def _over(color: QColor, alpha: float, under: QColor) -> QColor:
    return QColor.fromRgbF(
        color.redF() * alpha + under.redF() * (1 - alpha),
        color.greenF() * alpha + under.greenF() * (1 - alpha),
        color.blueF() * alpha + under.blueF() * (1 - alpha),
    )


@pytest.mark.parametrize("scene", [SCENE.name(), "#f3f5f7"])  # the lab's; light video
def test_older_captions_keep_4_5_to_1_over_a_dark_or_light_video(scene: str) -> None:
    look = CaptionLook()
    panel = _over(QColor(look.background), look.opacity, QColor(scene))
    for colour, alpha in (
        (look.original, OLDER_ALPHA),
        (look.translation, OLDER_TRANSLATION_ALPHA),
    ):
        seen = _over(QColor(colour), alpha, panel)
        assert contrast(seen, panel) >= 4.5, (colour, scene)
