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
SHEET = style.stylesheet(style.Theme())


def _px(value: str) -> int:
    return int(re.sub(r"px$", "", value))


def test_every_margin_colour_is_in_design_md() -> None:
    for prefix, palette in (("", MARGIN.dark), ("light-", MARGIN.light)):
        for token, value in vars(palette).items():
            name = prefix + token.lower().replace("_", "-")
            assert FRONT["colors"].get(name, "").lower() == value.lower(), name


def test_the_radii_are_the_stylesheets() -> None:
    sheet = {int(r) for r in re.findall(r"border-radius: (\d+)px", SHEET)}
    assert {_px(r) for r in FRONT["rounded"].values()} == sheet


def test_every_stylesheet_size_is_in_design_md() -> None:
    sizes = {_px(t["fontSize"]) for t in FRONT["typography"].values()}
    at_100 = {
        round(int(s) / style.text_scale())
        for s in re.findall(r"font-size: (\d+)px", SHEET)
    }
    assert at_100 <= sizes
