"""Each caption timing, and every caption-window control whose name doesn't
say enough, explains itself on hover, in plain words (the user's rehearsal
feedback F22, polyglotic-hq 249, 2026-11-08: "there should be tooltips for
each of timings")."""

from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_transcript_window import DISCORD, made_up

from polyglotic_desktop.core.listening.timing import (
    OFFERED_MODES,
    CaptionMode,
    default_caption_mode,
)
from polyglotic_desktop.ui_next import help_page
from polyglotic_desktop.ui_next.caption_window import timing_name, timing_tip
from polyglotic_desktop.ui_next.panels import TimingPanel
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.panels import Timing, TimingView
from polyglotic_desktop.ui_next.views.transcript import TranscriptChoices


def test_each_timing_says_what_it_does() -> None:
    tips = {mode: timing_tip(mode) for mode in OFFERED_MODES}
    assert len(set(tips.values())) == 4
    for mode, tip in tips.items():
        assert tip and tip != timing_name(mode)
    assert len({timing_name(mode) for mode in OFFERED_MODES}) == 4
    assert "half a second" in tips[CaptionMode.WHOLE]  # what 145 measured
    assert "one by one" in tips[CaptionMode.STEADY]
    # Quick preview, retired, reads as Steady wherever a name is still asked
    assert timing_name(CaptionMode.PREVIEW) == timing_name(CaptionMode.STEADY)


def test_the_windows_controls_say_what_they_do(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        for mode in OFFERED_MODES:
            assert window.controls[mode.value].toolTip() == timing_tip(mode)
        assert CaptionMode.PREVIEW.value not in window.controls
        for name in ("settings", "all_settings", "transcript"):
            control = window.controls[name]
            assert control.toolTip() and control.toolTip() != control.text(), name
        assert window.pill.toolTip()
        window.hovered = True
        window._show_band(True)
        window.toggle_settings()
        popover = window.popover
        assert popover is not None
        assert popover.translation_match.toolTip()
        popover.close()
        window.toggle_languages()
        assert window.languages is not None
        assert window.languages.language.toolTip()
        window.languages.close()
        # the timings are the bar's timing chip's now (593), each with its tip
        assert window.timing_chip.toolTip()
        window.timing_chip.click()
        timings = window.timings
        assert timings is not None
        whole = timings.findChild(QPushButton, "timings.timing.steady")
        assert whole is not None and whole.toolTip() == timing_tip(CaptionMode.WHOLE)
    finally:
        window.close()


def test_the_timing_panel_s_choices_say_what_they_do(qapp: QApplication) -> None:
    panel = TimingPanel(TimingView(Timing(CaptionMode.STEADY, 1.5)))
    assert [b.toolTip() for b in panel.mode.buttons] == [
        timing_tip(mode) for mode in OFFERED_MODES
    ]


def test_timing_choices_stay_visible_when_narrow(
    qapp: QApplication,
) -> None:
    panel = TimingPanel(TimingView(Timing(CaptionMode.CALM)))
    try:
        panel.resize(490, panel.sizeHint().height())
        panel.show()
        qapp.processEvents()
        assert all(panel.mode.rect().contains(b.geometry()) for b in panel.mode.buttons)
    finally:
        panel.close()
        panel.deleteLater()


def test_a_transcript_s_timing_menu_says_what_each_does(qapp: QApplication) -> None:
    window = TranscriptWindow("Discord.exe", made_up(), DISCORD, TranscriptChoices())
    try:
        for mode, action in window.timing_actions.items():
            assert action.toolTip() == timing_tip(mode)
        menu = window.buttons["timing"].menu()
        assert menu is not None and menu.toolTipsVisible()
    finally:
        window.close()


def test_the_default_timing_is_named_first_wherever_it_s_chosen(
    qapp: QApplication,
) -> None:
    """Help and Settings start with Instant and then list the other modes."""
    default = default_caption_mode()
    assert default is CaptionMode.INSTANT
    spectrum = list(OFFERED_MODES)
    panel = TimingPanel(TimingView(Timing(default, 1.5)))
    assert [b.text() for b in panel.mode.buttons] == [timing_name(m) for m in spectrum]
    assert all("experimental" not in b.text().casefold() for b in panel.mode.buttons)
    panel.deleteLater()
    [said] = [
        text
        for title, text in help_page.questions()
        if title == "When do captions appear?"
    ]
    assert said.startswith(f"{timing_name(default)}, the default:")
    places = [said.index(timing_name(mode)) for mode in spectrum]
    assert places == sorted(places)
    assert "Settings > Timing" in said  # Home's panel went in 261, a section in 304


def test_settings_timing_marks_the_presets_recommendation_and_moves_at_once(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.ui_next.views.preset_menu import (
        PresetItem,
        PresetMenu,
        PresetsView,
    )

    items = (
        PresetItem("everyday", "Everyday"),
        PresetItem("conversation", "Conversation"),
        PresetItem("video", "Video, film & TV"),
        PresetItem("learning", "Learning"),
        PresetItem("own1", "Anime", own=True, parent="video"),
        PresetItem("own2", "Freeform", own=True, parent=None),
    )
    presets = PresetsView(PresetMenu(items, "everyday"))
    view = TimingView(Timing(CaptionMode.INSTANT))
    panel = TimingPanel(view, presets=presets)
    try:
        buttons = dict(zip(OFFERED_MODES, panel.mode.buttons, strict=True))
        assert buttons[CaptionMode.INSTANT].property("recommended") is True
        assert not any(
            buttons[m].property("recommended")
            for m in OFFERED_MODES
            if m is not CaptionMode.INSTANT
        )
        assert (
            buttons[CaptionMode.INSTANT]
            .toolTip()
            .startswith("Recommended for Everyday: ")
        )
        assert (
            "Recommended for Everyday: "
            in buttons[CaptionMode.INSTANT].accessibleName()
        )

        presets.follow(PresetMenu(items, "video"))
        assert [b.text() for b in panel.mode.buttons] == [
            "Instant",
            "Scrolling",
        ]
        instant, delayed = panel.mode.buttons
        assert instant.property("recommended") is True
        assert not delayed.property("recommended")
        assert instant.toolTip().startswith("Recommended for Video, film & TV: ")
        assert "Recommended for Video, film & TV: " in instant.accessibleName()
        panel.mode.choose(CaptionMode.SCROLLING)
        assert view.value.mode is CaptionMode.SCROLLING

        presets.follow(PresetMenu(items, "own1"))
        instant = panel.mode.buttons[0]
        assert instant.property("recommended") is True
        assert instant.toolTip().startswith("Recommended for Anime: ")

        # Saved preset with no parent shows none
        presets.follow(PresetMenu(items, "own2"))
        assert not any(b.property("recommended") for b in panel.mode.buttons)
    finally:
        panel.close()
        panel.deleteLater()
