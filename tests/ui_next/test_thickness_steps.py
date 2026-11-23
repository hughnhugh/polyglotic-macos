"""Thickness offers only the steps the captions' faces draw (polyglotic-hq
532, item 5): every face the app carries is cut at Medium (Ma Shan Zheng
at Regular, its only weight), so Light and Regular drew what Medium draws
- the slider moved and the captions didn't change. A PC's own face with a
Light weight brings the light steps back."""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next import caption_faces
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.tone import THICKNESSES, offered


def test_the_steps_start_at_the_lightest_a_face_has() -> None:
    assert offered(500) == (500, 600, 700)  # the app's own faces
    assert offered(400) == (400, 500, 600, 700)
    assert offered(300) == THICKNESSES
    assert offered(200) == offered(350) == THICKNESSES  # nearer Light than not
    assert offered(600) == (500, 600, 700)  # Medium always offered


@pytest.fixture
def faces(qapp: QApplication) -> Iterator[list[LookPanel]]:
    caption_faces.load()
    made: list[LookPanel] = []
    yield made
    for panel in made:
        panel.deleteLater()
    qapp.processEvents()


PC = {
    "Noto Sans Devanagari": [400, 500, 700],  # a Linux PC's own, beside the app's
    "IBM Plex Sans": [300, 400, 500],  # the whole family installed on the PC
    "Some PC Sans": [300, 400, 600, 700],
    "Regular Only": [400],
    "Regular And Medium": [400, 500],
}
"""A font database as an OS might have it: the rule is tested on any OS
with this stub (532: Linux CI's Noto Sans Devanagari has a Regular)."""


def test_the_apps_own_faces_count_as_one_weight_whatever_the_os_has() -> None:
    """Each face the app carries or downloads is cut at one weight: another
    face of the PC's under its name never brings a lighter step."""
    for family in ("Noto Sans Devanagari", "IBM Plex Sans", "Ma Shan Zheng Captions"):
        found = caption_faces.lightest([family], weights_of=lambda f: PC.get(f, []))
        assert found == 500, family


def test_a_pcs_face_brings_what_it_has_below_what_medium_draws() -> None:
    def lightest(*families: str) -> int:
        return caption_faces.lightest(families, weights_of=lambda f: PC.get(f, []))

    assert lightest("Some PC Sans") == 300
    assert lightest("Regular Only") == 500  # Medium draws its Regular already
    assert lightest("Regular And Medium") == 400
    assert lightest("Not A Font On This PC") == 500
    assert lightest("Regular Only", "Some PC Sans") == 300


def test_the_apps_own_faces_have_nothing_lighter_than_medium(
    faces: list[LookPanel],
) -> None:
    for family in ("IBM Plex Sans", "Noto Sans SC Captions", "PT Sans"):
        assert caption_faces.lightest([family]) == 500, family
    assert caption_faces.lightest(["Not A Font On This PC"]) == 500


def test_with_the_apps_faces_light_and_regular_are_not_offered(
    faces: list[LookPanel],
) -> None:
    """Before, Light and Regular were offered and drew Medium."""
    view = LookView(CaptionLook(thickness=300))  # chosen before: drawn as Medium
    panel = LookPanel(view, notes=True)
    faces.append(panel)
    slider = panel.text.thickness
    assert THICKNESSES[slider.minimum()] == 500
    assert THICKNESSES[slider.value()] == 500  # what it draws
    assert panel.text.ends["look.thickness"][0].text() == "Medium"
    assert view.value.thickness == 300  # the choice itself is kept


def test_a_chosen_pc_face_brings_the_light_steps_back(
    faces: list[LookPanel], monkeypatch: pytest.MonkeyPatch
) -> None:
    """On any OS, with the font database stubbed (`PC`)."""
    monkeypatch.setattr(caption_faces, "weights", lambda f: PC.get(f, []))
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    faces.append(panel)
    assert THICKNESSES[panel.text.thickness.minimum()] == 500
    view.set_face("en", "Some PC Sans")
    assert panel.text.thickness.minimum() == 0
    assert panel.text.ends["look.thickness"][0].text() == "Light"
    view.set_face("hi", "Noto Sans Devanagari")  # the app's: nothing more
    view.set_face("en", None)
    assert THICKNESSES[panel.text.thickness.minimum()] == 500


@pytest.mark.skipif(sys.platform != "win32", reason="Segoe UI is Windows'")
def test_a_pc_face_with_a_light_weight_brings_the_light_steps(
    faces: list[LookPanel],
) -> None:
    assert caption_faces.lightest(["Segoe UI"]) == 300
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    faces.append(panel)
    view.set_face("en", "Segoe UI")
    assert panel.text.thickness.minimum() == 0
    assert panel.text.ends["look.thickness"][0].text() == "Light"
    view.set_face("en", None)
    assert THICKNESSES[panel.text.thickness.minimum()] == 500
