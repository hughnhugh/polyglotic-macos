"""The ten colour presets as caption windows, each a state with its golden
(polyglotic-hq 248's section 6, Q7 A; 248's B6, built by 261): a window
of finished captions in the preset's colours and panel, photographed over
the stand-in video - the checks judge its text's contrast as seen - and
the change to it from Classic (Classic's: from Broadcast) timed (a click:
50 ms) - and each with its top bar showing (`_bar`), so the contrast check
reads the bar's words on every preset (polyglotic-hq 272: white icons were
1.05:1 on Paper's cream; the icons themselves are checked in
tests/ui_next/test_bar_readable_on_every_panel.py)."""

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtWidgets import QWidget

from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.presets import PRESETS, ColourPreset
from tools.ui_lab.caption_window import hovered, window
from tools.ui_lab.lab import Lab, State


def look_of(preset: ColourPreset) -> CaptionLook:
    return replace(
        CaptionLook(),
        original=preset.original,
        translation=preset.translation,
        background=preset.background,
        opacity=preset.opacity,
    )


def preset_window(preset: ColourPreset) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        shown = window(lab, captions=6)
        before = PRESETS[1] if preset is PRESETS[0] else PRESETS[0]
        looks = [look_of(before), look_of(preset)]
        lab.time(
            "preset",
            lambda: shown.set_look(looks[shown.look == looks[0]]),
            repeat=6,
            budget=budgets.CLICK,
        )
        shown.set_look(looks[1])
        lab.pump()
        return shown

    return run


def preset_bar(preset: ColourPreset) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        shown = window(lab, captions=6)
        shown.set_look(look_of(preset))
        hovered(lab, shown)
        return shown

    return run


STATES = [
    State(f"ui_next.preset_{preset.key}", preset_window(preset), gated=True, scene=True)
    for preset in PRESETS
] + [
    State(
        f"ui_next.preset_{preset.key}_bar", preset_bar(preset), gated=True, scene=True
    )
    for preset in PRESETS
]
