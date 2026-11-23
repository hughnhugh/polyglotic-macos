"""docs/design/DESIGN.md's tokens stay equal to the code's (polyglotic-hq
347): its colours to Margin's palettes in `ui/theme.py`, its radii and the
stylesheet's sizes to `ui_next/style.py`'s stylesheet. The code is the
source: change it, then DESIGN.md."""

import re
from pathlib import Path

import yaml

from polyglotic_desktop.ui.theme import MARGIN
from polyglotic_desktop.ui_next import style

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design" / "DESIGN.md"
FRONT = yaml.safe_load(DESIGN.read_text(encoding="utf-8").split("---")[1])


def _sheet() -> str:
    """The stylesheet at the text size now: each test begins at the design
    sizes, a factor of 1.0 (`tests/conftest.py`), where DESIGN.md's scale
    is. Built at import, it took the style's starting size - the app's
    Normal, 1.3 since decision 0244 - and divided by the test's 1.0 its
    sizes were 1.3 times the scale's (polyglotic-hq 524)."""
    return style.stylesheet(style.Theme())


def _px(value: str) -> int:
    return int(re.sub(r"px$", "", value))


def test_every_margin_colour_is_in_design_md() -> None:
    for prefix, palette in (("", MARGIN.dark), ("light-", MARGIN.light)):
        for token, value in vars(palette).items():
            name = prefix + token.lower().replace("_", "-")
            assert FRONT["colors"].get(name, "").lower() == value.lower(), name


def test_the_radii_are_the_stylesheets() -> None:
    sheet = {int(r) for r in re.findall(r"border-radius: (\d+)px", _sheet())}
    assert {_px(r) for r in FRONT["rounded"].values()} == sheet


def test_every_stylesheet_size_is_in_design_md() -> None:
    """DESIGN.md's type scale is the design sizes, at a text size factor of
    1.0; every size is multiplied by the text size as it's drawn
    (`style.px`: decisions 0084, 0244)."""
    sizes = {_px(t["fontSize"]) for t in FRONT["typography"].values()}
    sheet = _sheet()
    at_1 = {
        round(int(s) / style.text_scale())
        for s in re.findall(r"font-size: (\d+)px", sheet)
    }
    assert at_1 <= sizes


def test_the_caption_windows_corners_are_on_the_scale() -> None:
    """A caption window has no window stylesheet - its strip's buttons and
    a hovered word's box set their own corners - so nothing held them to
    the scale: both were 5 px (polyglotic-hq 376, 403)."""
    from polyglotic_desktop.ui_next import caption_window

    scale = {_px(r) for r in FRONT["rounded"].values()}
    assert _px(FRONT["rounded"]["small"]) == caption_window.MARK_RADIUS
    for look in (caption_window.band_style(), caption_window.notice_style()):
        assert {int(r) for r in re.findall(r"border-radius: (\d+)px", look)} <= scale
