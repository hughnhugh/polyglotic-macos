"""Three recommended looks, each a whole look in one click (polyglotic-hq
532; the user, preview 1, 2026-11-18: "this theme and settings are nice,
this should be a recommended preset, paper should be another, broadcast
another" - and "make a stand out one the default and customisable (should
have recommended presets)")."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.display import ReadingColour, ReadingSize
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.settings import AppSettings, with_changed
from polyglotic_desktop.ui_next import fonts
from polyglotic_desktop.ui_next.colour_controls import RecommendedTiles
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, TextEdge
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    LOOKS,
    LOOKS_BY_KEY,
    VIDEOS,
    _mix,
    contrast,
    look_of,
    preset_of,
    with_look,
)


def test_the_three_in_the_users_order() -> None:
    assert [look.key for look in LOOKS] == ["quiet", "paper", "broadcast"]


def test_quiet_is_the_users_picture() -> None:
    """The Look panel in the user's picture of preview 1: Quiet's colours,
    contrast and vibrance at the top, Semibold, a soft shadow - with the
    readings grey and Chinese in calligraphy (532)."""
    quiet = with_look(CaptionLook(), "quiet")
    colours = preset_of(quiet)
    assert colours is not None and colours.key == "quiet"
    assert (quiet.contrast, quiet.vibrance, quiet.thickness) == (100, 100, 600)
    assert quiet.edge is TextEdge.SHADOW
    assert quiet.reading_colour is ReadingColour.GREY
    # its picture's pinyin size; Small's is 11 px at the first text size
    assert quiet.reading_size is ReadingSize.MEDIUM
    assert dict(quiet.faces)["zh"] == "Ma Shan Zheng Captions"  # the calligraphy
    assert fonts.FACES[dict(quiet.faces)["zh"]].kind == fonts.CALLIGRAPHY


def test_each_sets_the_whole_look_and_nothing_else() -> None:
    mine = CaptionLook(
        show_source=False,
        reading_lines=("zh", "en"),
        faces=(("ja", "Klee One Captions"), ("zh", "KaiTi")),
        fade_after=8.0,
    )
    for look in LOOKS:
        made = with_look(mine, look.key)
        assert look_of(made) is look
        assert (made.original, made.translation, made.background) == (
            look.preset.original,
            look.preset.translation,
            look.preset.background,
        )
        assert made.opacity == look.opacity and made.thickness == look.thickness
        assert made.reading_size is look.reading_size
        # Chinese's faces set; another language's as the learner chose it
        assert dict(made.faces)["ja"] == "Klee One Captions"
        assert {code for code, _ in look.faces} == {"zh", "zh-hant"}
        assert (made.show_source, made.reading_lines, made.fade_after) == (
            False,
            ("zh", "en"),
            8.0,
        )


def test_changed_after_it_is_no_longer_that_look_but_keeps_the_rest() -> None:
    view = LookView(CaptionLook())
    view.set_recommended("broadcast")
    assert look_of(view.value) is LOOKS_BY_KEY["broadcast"]
    view.set_contrast(40)
    assert look_of(view.value) is None
    assert view.value.background == LOOKS_BY_KEY["broadcast"].preset.background
    assert view.value.reading_size is ReadingSize.MEDIUM


def test_turning_a_recommended_look_off_restores_every_changed_setting() -> None:
    mine = CaptionLook(
        original="#cfe8ff",
        translation="#a5f28a",
        background="#2d1f2f",
        opacity=0.73,
        contrast=20,
        vibrance=40,
        thickness=400,
        edge=TextEdge.OUTLINE,
        reading_size=ReadingSize.SMALL,
        reading_colour=ReadingColour.SAME,
        faces=(("zh", "KaiTi"), ("zh-hant", "MingLiU")),
    )
    view = LookView(mine)
    view.set_recommended("quiet")
    assert view.value != mine
    view.set_recommended("quiet")
    assert view.value == mine


def test_reclick_after_an_edit_reapplies_then_turns_the_look_off() -> None:
    mine = CaptionLook(contrast=20, opacity=0.73)
    view = LookView(mine)
    view.set_recommended("quiet")
    view.set_contrast(40)
    view.set_recommended("quiet")
    assert look_of(view.value) is LOOKS_BY_KEY["quiet"]
    view.set_recommended("quiet")
    assert view.value.contrast == mine.contrast
    assert view.value.opacity == mine.opacity


def test_an_active_look_can_be_turned_off_after_a_restart() -> None:
    mine = CaptionLook(opacity=0.73, thickness=400)
    first = LookView(mine)
    first.set_recommended("quiet")

    restarted = LookView(first.value, recommended_before=first.recommended_before)
    restarted.set_recommended("quiet")

    assert restarted.value == mine


def test_an_invalid_stored_look_snapshot_is_dropped_before_startup() -> None:
    value = AppSettings.from_stored(
        {
            "recommended_look_before": {
                "opacity": "nearly solid",
                "setting_removed_by_a_later_version": 1,
            }
        }
    )

    assert value.recommended_look_before == {}
    assert caption_look(value) == caption_look(AppSettings())


def test_switching_recommended_looks_keeps_the_original_snapshot() -> None:
    mine = CaptionLook(background="#2d1f2f", thickness=400)
    view = LookView(mine)
    view.set_recommended("quiet")
    view.set_recommended("paper")
    view.set_recommended("paper")
    assert view.value == mine


def test_a_new_install_is_none_of_them() -> None:
    """Classic stays the default look (248's Q7 A); the three are offered."""
    assert look_of(CaptionLook()) is None
    assert look_of(caption_look(AppSettings())) is None


def test_every_faces_family_is_one_the_app_knows() -> None:
    for look in LOOKS:
        for code, family in look.faces:
            assert family in fonts.CHOICES[fonts.script(code)], (look.key, family)


@pytest.mark.parametrize("key", [look.key for look in LOOKS])
def test_each_looks_text_reads_on_its_panel_over_any_video(key: str) -> None:
    """4.5:1 for both rows on the panel at the look's opacity over a light
    and a black video (284's rule for the presets)."""
    chosen = LOOKS_BY_KEY[key]
    preset = chosen.preset
    for video in VIDEOS:
        seen = _mix(video, preset.background, chosen.opacity)
        for text in (preset.original, preset.translation):
            assert contrast(text, seen) >= AA_TEXT, (chosen.key, video, text)


def test_picking_one_is_saved_as_the_learners_choice() -> None:
    """A look's settings count as changed (`AppSettings.changed`): they stay
    when a default moves later; untouched ones follow it."""
    before = AppSettings()
    look = with_look(caption_look(before), "paper")
    after = with_changed(before, replace(before, **look_settings(look)))  # type: ignore[arg-type]
    assert {"background_color", "caption_contrast", "caption_faces"} <= set(
        after.changed
    )
    assert "reading_colour" not in after.changed  # Paper's is the default's
    assert caption_look(after).faces == look.faces


# -- in Qt -------------------------------------------------------------------------


@pytest.fixture
def made(qapp: QApplication) -> Iterator[list[object]]:
    found: list[object] = []
    yield found
    for widget in found:
        widget.deleteLater()  # type: ignore[attr-defined]
    qapp.processEvents()


def test_a_click_sets_the_look_and_shows_it_chosen(made: list[object]) -> None:
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    made.append(panel)
    tiles = panel.recommended
    assert not any(tile.isChecked() for tile in tiles.tiles.values())
    tiles.tiles["quiet"].click()
    assert look_of(view.value) is LOOKS_BY_KEY["quiet"]
    assert tiles.tiles["quiet"].isChecked()
    assert panel.presets.tiles["quiet"].isChecked()  # its colours, too
    assert panel.text.thickness_now() == "Semibold"
    tiles.tiles["quiet"].click()
    assert view.value == CaptionLook()
    assert not tiles.tiles["quiet"].isChecked()
    tiles.tiles["quiet"].click()
    view.set_thickness(500)  # changed after: none chosen, the colours still Quiet
    assert not any(tile.isChecked() for tile in tiles.tiles.values())
    assert panel.presets.tiles["quiet"].isChecked()


def test_each_tile_says_what_it_sets(made: list[object]) -> None:
    tiles = RecommendedTiles()
    made.append(tiles)
    for key, tile in tiles.tiles.items():
        assert tile.objectName() == f"look.recommended.{key}"
        assert tile.toolTip() and tile.accessibleDescription() == tile.toolTip()
        assert tile.text() in ("Quiet", "Paper", "Broadcast")


def test_a_looks_downloaded_faces_are_asked_for(
    qapp: QApplication, tmp_path: Path
) -> None:
    """A look sets a face without Look's row, which asks for a face picked
    there: the captioned languages' chosen faces are asked for too, with
    their defaults - Paper's Polyglotic Kai, Traditional's LXGW WenKai TC."""
    from polyglotic_desktop.main import FontDelivery
    from polyglotic_desktop.ui_next.views.panels import DownloadsView

    delivery = FontDelivery(tmp_path, object(), DownloadsView())  # type: ignore[arg-type]
    paper = with_look(CaptionLook(), "paper")
    delivery.follow(("zh", "zh-hant", "en"), dict(paper.faces))
    asked = [pack for pack, _ in delivery._waiting]
    assert asked == ["polyglotickai", "lxgwwenkaitc"]  # Ma Shan Zheng is here
    delivery.follow(("zh",), dict(paper.faces))  # once a run
    assert len(delivery._waiting) == 2
    delivery.deleteLater()
