"""The caption windows' ten colour presets and exact colours (polyglotic-hq
248's section 6 and Q7 A; the user's F11 and F16; 261): a matched set in
a click, any colour changed after it - from its swatches, as a hex value,
or picked - and every preset's text readable on its own panel."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next import colour_controls
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    PRESETS,
    contrast,
    hex_colour,
    preset_of,
)

MADE: list[QWidget] = []
"""Panels a test made, deleted at its end (`deleted`)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each panel deleted when its test ends, not at the interpreter's exit,
    where a panel still bound to its view can crash the run (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            shiboken6.delete(made)


def made(panel: LookPanel) -> LookPanel:
    MADE.append(panel)
    return panel


def test_ten_presets_in_248s_order_classic_first_and_the_default() -> None:
    assert [p.key for p in PRESETS] == [
        "classic",
        "broadcast",
        "teletext",
        "ember",
        "violet",
        "forest",
        "paper",
        "quiet",
        "high_contrast",
        "clear",
    ]
    classic = preset_of(CaptionLook())  # a new install's look
    assert classic is PRESETS[0]
    assert classic.opacity == CaptionLook().opacity


@pytest.mark.parametrize("preset", PRESETS, ids=[p.key for p in PRESETS])
def test_every_presets_text_is_at_least_4_5_to_1_on_its_panel(preset: object) -> None:
    """WCAG 2.2's 1.4.3 for normal text (B6): fails if a preset is edited
    below it. 248's contrast.py's values, against the panel drawn solid."""
    from polyglotic_desktop.ui_next.views.presets import ColourPreset

    assert isinstance(preset, ColourPreset)
    for text in (preset.original, preset.translation):
        assert contrast(text, preset.background) >= AA_TEXT, (preset.key, text)


def test_the_rows_brightness_gaps_are_248s() -> None:
    """248's 6.1: the rows must differ in brightness or warmth. The
    ratios are 248's table's (said vs translation, 1.1-2.3)."""
    ratios = {p.key: round(contrast(p.original, p.translation), 1) for p in PRESETS}
    assert ratios["clear"] == 2.3 and ratios["paper"] == 2.1
    assert min(ratios.values()) == ratios["high_contrast"] == 1.1


def test_contrast_is_wcags() -> None:
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert contrast("#ffd76e", "#0a0c10") == pytest.approx(14.2, abs=0.05)  # 248's


def test_a_colour_reads_as_typed() -> None:
    assert hex_colour("#FFD76E") == "#ffd76e"
    assert hex_colour(" ffd76e ") == "#ffd76e"
    assert hex_colour("#fd7") == "#ffdd77"
    for wrong in ("", "#ffd76", "yellow", "#ggg000", "#ffd76e0"):
        assert hex_colour(wrong) is None, wrong


def test_a_preset_sets_its_colours_and_opacity_and_a_change_makes_it_custom() -> None:
    view = LookView(CaptionLook())
    view.set_preset("ember")
    ember = PRESETS[3]
    value = view.value
    assert (value.original, value.translation, value.background) == (
        ember.original,
        ember.translation,
        ember.background,
    )
    assert value.opacity == ember.opacity
    view.set_opacity(0.6)  # the slider still moves: still Ember
    assert preset_of(view.value) is ember
    view.set_colour("translation", "#FF8800")
    assert view.value.translation == "#ff8800"
    assert preset_of(view.value) is None and view.started_from == "ember"
    with pytest.raises(ValueError):
        view.set_colour("translation", "orange")


def test_the_tiles_choose_a_preset_and_show_custom_from_it(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = made(LookPanel(view, notes=True))
    tiles = panel.presets.tiles
    assert len(tiles) == 11 and tiles["custom"].isHidden()
    assert tiles["classic"].isChecked()
    assert all(tiles[p.key].toolTip() for p in PRESETS)  # what each suits
    tiles["violet"].click()
    assert preset_of(view.value) is PRESETS[4] and tiles["violet"].isChecked()
    panel.colours["original"].swatches.chosen.emit("#cfe8ff")  # a swatch
    assert not tiles["custom"].isHidden() and tiles["custom"].isChecked()
    assert "Violet" in tiles["custom"].toolTip()
    assert not any(tiles[p.key].isChecked() for p in PRESETS)
    tiles["paper"].click()
    assert tiles["custom"].isHidden() and tiles["paper"].isChecked()


def test_an_exact_colour_typed_or_picked(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = LookView(CaptionLook())
    panel = made(LookPanel(view, notes=True))
    translation = panel.colours["translation"]
    translation.hex.setText("#7FE3FF")
    translation.hex.editingFinished.emit()
    assert view.value.translation == "#7fe3ff"
    translation.hex.setText("not a colour")
    translation.hex.editingFinished.emit()
    assert translation.hex.text() == "#7fe3ff"  # put back
    asked: list[str] = []

    def picked(colour: str, parent: object, title: str) -> str | None:
        asked.append(title)
        return "#123456"

    monkeypatch.setattr(colour_controls, "pick_colour", picked)
    panel.colours["background"].pick.click()
    assert view.value.background == "#123456"
    assert asked == ["Pick a colour: The panel"]
    monkeypatch.setattr(colour_controls, "pick_colour", lambda *_: None)  # Cancel
    panel.colours["background"].pick.click()
    assert view.value.background == "#123456"


def test_a_label_colour_is_made_readable_on_a_light_panel() -> None:
    """An app's label colour is picked for dark panels: on Paper's cream it
    fell to 1.45:1 (the lab's contrast check, 261). On a dark panel it's
    kept as it is."""
    from polyglotic_desktop.ui_next.views.presets import readable_on

    cyan, cream, dark = "#4dd0e1", "#f6f1e6", "#0a0c10"
    assert contrast(cyan, cream) < AA_TEXT
    darker = readable_on(cyan, cream)
    assert contrast(darker, cream) >= AA_TEXT and darker != "#000000"
    assert readable_on(cyan, dark) == cyan


def test_a_caption_windows_labels_are_readable_in_paper(qapp: QApplication) -> None:
    from dataclasses import replace

    from tests.ui_next.test_caption_window import window_of

    from polyglotic_desktop.core.listening.sources import SourceLabel

    paper = next(p for p in PRESETS if p.key == "paper")
    look = replace(
        CaptionLook(),
        original=paper.original,
        translation=paper.translation,
        background=paper.background,
        opacity=paper.opacity,
    )
    window = window_of(qapp, captions=3, look=look)
    try:
        cyan = SourceLabel("Discord", "#4dd0e1")  # picked for a dark panel
        window.set_labels({window.source: cyan}, "You")
        colours = [line.label_color for line in window.view.lines]
        assert colours and all(colours)  # each with its app's colour
        colours.append(window.canvas.ink.label.name())  # a label without one
        assert all(contrast(c, paper.background) >= AA_TEXT for c in colours)
    finally:
        window.close()


def test_the_tiles_put_fewer_to_a_row_when_narrow(qapp: QApplication) -> None:
    from polyglotic_desktop.ui_next.colour_controls import PresetTiles

    tiles = PresetTiles()
    tiles.resize(700, 200)
    tiles.show()
    qapp.processEvents()
    assert tiles.columns == PresetTiles.COLUMNS
    tiles.resize(260, 400)  # a transcript's rail
    qapp.processEvents()
    assert tiles.columns == 2
    assert tiles.minimumSizeHint().width() < 260
    tiles.close()


def test_a_preset_clicked_again_stays_chosen(qapp: QApplication) -> None:
    """A second click on the chosen tile (a double-click, or a check that
    it took) kept the colours but left no tile chosen: Qt unticks a ticked
    button, and the look didn't change to tick it again (269)."""
    view = LookView(CaptionLook())
    panel = made(LookPanel(view, notes=True))
    tiles = panel.presets.tiles
    tiles["ember"].click()
    assert tiles["ember"].isChecked()
    tiles["ember"].click()
    assert tiles["ember"].isChecked() and preset_of(view.value).key == "ember"  # type: ignore[union-attr]
    assert [k for k, t in tiles.items() if t.isChecked()] == ["ember"]


VIDEOS = ("#f3f5f7", "#000000")
"""A light video and a black one: the worst for light and for dark text."""


def _over(colour: str, share: float, under: str) -> str:
    """`colour` drawn at `share` over `under`, as "#rrggbb"."""
    a, b = colour.lstrip("#"), under.lstrip("#")
    mixed = (
        round(int(a[i : i + 2], 16) * share + int(b[i : i + 2], 16) * (1 - share))
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{c:02x}" for c in mixed)


@pytest.mark.parametrize("preset", PRESETS, ids=[p.key for p in PRESETS])
@pytest.mark.parametrize("video", VIDEOS)
def test_every_presets_captions_are_aa_over_a_light_or_dark_video(
    preset: object, video: str
) -> None:
    """The judge for the themes' contrast (polyglotic-hq 284; the user's
    live testing, 270: "not high contrast enough, not visible enough"):
    what was said and its translation, the newest caption and an older one
    stepped back (`views.arrivals`), at 4.5:1 against the preset's panel at
    its own opacity over the video. Failed for Ember (4.4), Paper (4.4)
    and Quiet (2.0) before 284 raised their panels."""
    from polyglotic_desktop.ui_next.views.arrivals import (
        OLDER_ALPHA,
        OLDER_TRANSLATION_ALPHA,
    )
    from polyglotic_desktop.ui_next.views.presets import ColourPreset

    assert isinstance(preset, ColourPreset)
    panel = _over(preset.background, preset.opacity, video)
    for text, older in (
        (preset.original, OLDER_ALPHA),
        (preset.translation, OLDER_TRANSLATION_ALPHA),
    ):
        for ink in (1.0, older):
            seen = _over(text, ink, panel)
            assert contrast(seen, panel) >= AA_TEXT, (preset.key, text, ink)
