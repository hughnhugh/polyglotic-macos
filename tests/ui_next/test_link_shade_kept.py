"""A word link's shade is worked out once for inks a hundredth apart
(polyglotic-hq 590): the card stack draws its rows at alphas seldom the
same twice as cards glide and recede, and each new alpha cost a contrast
search at every paint - 44 % of a glide's paint time on a 5600X. Rounded
down, the shade still reads at the ink it's drawn at."""

import pytest
from PySide6.QtGui import QColor

from polyglotic_desktop.ui_next import caption_layout
from polyglotic_desktop.ui_next.caption_layout import LINK_CONTRAST, Ink, link_ink
from polyglotic_desktop.ui_next.views.presets import _mix, contrast

PANEL = "#1b2431"
"""A panel no other test draws on: its shades aren't kept already."""


def gliding(start: float) -> list[QColor]:
    """A row's ink through half a hundredth of a glide's fade, 50 frames
    a ten-thousandth apart (`SHADE_ALPHA_STEP` is a hundredth)."""
    rows = []
    for n in range(50):
        row = QColor("#ffffff")
        row.setAlphaF(start + n * 0.0001)
        rows.append(row)
    return rows


def test_a_glides_inks_share_one_contrast_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    searched = []
    real = caption_layout.readable_through

    def counted(*args: object) -> str:
        searched.append(args)
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(caption_layout, "readable_through", counted)
    ink = Ink(panel=PANEL, panel_opacity=0.72)
    for row in gliding(0.6025):
        link_ink(QColor("#e040fb"), ink, row)
    assert len(searched) == 1


def test_the_shade_reads_at_the_ink_drawn() -> None:
    ink = Ink(panel=PANEL, panel_opacity=1.0)
    for row in gliding(0.8025):
        drawn = link_ink(QColor("#7c4dff"), ink, row)
        seen = _mix(PANEL, drawn.name(), row.alphaF())
        assert contrast(seen, PANEL) >= LINK_CONTRAST
