"""How new captions arrive, offered in Settings > Captions > Behaviour -
Slide in (step and slide, the default) or Appear (the step) - for every
window (polyglotic-hq 267, DECISIONS.md #104; Settings > Captions is
261's)."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.main import look_settings
from polyglotic_desktop.ui_next.controls import Segmented
from polyglotic_desktop.ui_next.panels import BehaviourPanel, ResetCard
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView


def test_behaviour_offers_slide_in_or_appear_slide_in_first(qapp: QApplication) -> None:
    panel = BehaviourPanel(LookView(CaptionLook()), notes=True)
    try:
        choice = panel.findChild(Segmented, "look.arrival")
        assert choice is panel.arrival
        assert [b.text() for b in choice.buttons] == ["Slide in", "Appear"]
        assert choice.value() == Arrival.STEP_AND_SLIDE.value  # the default
    finally:
        panel.deleteLater()


def test_a_choice_changes_every_window_s_look_and_is_kept(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = BehaviourPanel(view, notes=True)
    try:
        panel.arrival.changed.emit(Arrival.STEP.value)  # Appear clicked
        assert view.value.arrival is Arrival.STEP
        assert look_settings(view.value)["caption_arrival"] == "step"
        view.follow(CaptionLook(arrival=Arrival.STEP_AND_SLIDE))  # the settings, saved
        assert panel.arrival.value() == Arrival.STEP_AND_SLIDE.value
    finally:
        panel.deleteLater()


def test_reset_brings_back_slide_in(qapp: QApplication) -> None:
    view = LookView(CaptionLook(arrival=Arrival.STEP))
    panel, reset = BehaviourPanel(view), ResetCard(view)
    try:
        reset.reset.click()
        assert view.value.arrival is Arrival.STEP_AND_SLIDE
        assert panel.arrival.value() == Arrival.STEP_AND_SLIDE.value
    finally:
        panel.deleteLater()
        reset.deleteLater()
