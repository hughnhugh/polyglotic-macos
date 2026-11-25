"""Presets for use cases (polyglotic-hq 556): the bar's preset chip and its
dropdown open, on Custom as a new learner has it and on Conversation;
Video's subtitles along the bottom of a stand-in screen, as the preset
puts every window there; and Settings > Presets on Video, with what it
changes. Saving on purpose (587): the chip and dropdown with changes not
saved, Undo on a window's notice line after a switch, and Settings' preset
line as it is, with changes not saved, and naming a new preset. The menus
are made from real settings (`ui.use_presets`), as `main` makes them."""

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows, undo_line
from polyglotic_desktop.ui_next.preset_popover import preset_name, undo_note
from polyglotic_desktop.ui_next.presets_card import change_words
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, TextEdge
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.preset_menu import (
    PresetItem,
    PresetMenu,
    PresetsView,
    Show,
    Undo,
)
from tools.ui_lab import pages
from tools.ui_lab.caption_window import AREA, LABELS, _areas, _Together, hovered, window
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.new_parts import finished


def menu_of(value: AppSettings) -> PresetMenu:
    """The menu `main` would make of `value` (`main.preset_menu`), the
    look's word links and readings from the settings themselves."""
    items = tuple(
        PresetItem(
            key,
            value.preset_names.get(key) or preset_name(key),
            key not in use_presets.ORDER,
            use_presets.parent_of(value, key) if key not in use_presets.ORDER else None,
        )
        for key in use_presets.keys(value)
    )
    show = (
        Show.ORIGINAL
        if not value.show_translation
        else Show.TRANSLATION
        if not value.show_original
        else Show.BOTH
    )
    return PresetMenu(
        items,
        value.preset,
        show,
        links=value.word_links != WordLinks.OFF.value,
        quiet=value.quiet_view,
        readings=value.preset != use_presets.VIDEO,  # a new learner's: on
        changes=change_words(use_presets.differences(value, value.preset)),
        can_add=use_presets.can_add(value),
        edited=len(use_presets.edits(value)),
        restorable=use_presets.restorable(value, value.preset),
    )


def on(key: str) -> AppSettings:
    return use_presets.chosen(AppSettings(), key)


def edited() -> AppSettings:
    """Learning, with three of its settings changed and not saved (587)."""
    return replace(
        on(use_presets.LEARNING), word_links="hover", fade_after=6.0, opacity=0.5
    )


def dropdown(
    key: str, my_speech: bool = False, changed: bool = False
) -> Callable[[Lab], QWidget]:
    """A window's bar with its preset chip, the dropdown open under it -
    `changed`: Learning with changes not saved, the chip's dot and the
    dropdown's first steps (587)."""

    def run(lab: Lab) -> QWidget:
        value = edited() if changed else on(key)
        look = replace(CaptionLook(), word_links=WordLinks(value.word_links))
        shown = window(lab, look=look, show_mic=my_speech)
        menu = menu_of(value)
        shown.set_presets(replace(menu, readings=bool(shown.look.reading_lines)))
        hovered(lab, shown)

        def toggle() -> None:
            shown.toggle_presets()

        for _ in range(6):  # open, close, open, ...: each a click
            lab.time("presets_dropdown", toggle, budget=budgets.CLICK)
        shown.toggle_presets()
        lab.pump()
        opened = shown.presets
        assert opened is not None
        lab.closing.append(shown.close)
        return _Together([shown, opened])

    return run


class _Screen(QWidget):
    """A stand-in screen: a film's frame, bright sky to dark ground, the
    size of the work area, with the windows where they are on it - scaled
    to half, as the picture of a whole screen is."""

    SCALE = 0.5

    def __init__(self, windows: list[CaptionWindow], area: Rect = AREA) -> None:
        super().__init__()
        self.windows = windows
        self.resize(round(area.width * self.SCALE), round(area.height * self.SCALE))

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        return [
            (
                each,
                QPoint(round(each.x() * self.SCALE), round(each.y() * self.SCALE)),
                1.0,
            )
            for each in self.windows
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        sky = QLinearGradient(QPointF(0, 0), QPointF(0, self.height()))
        sky.setColorAt(0.0, QColor("#cfe3f2"))
        sky.setColorAt(0.55, QColor("#e8c48f"))
        sky.setColorAt(0.75, QColor("#5b4a3a"))
        sky.setColorAt(1.0, QColor("#1d1b19"))
        painter.fillRect(self.rect(), sky)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for each in self.windows:
            picture = each.grab()
            at = QPoint(round(each.x() * self.SCALE), round(each.y() * self.SCALE))
            painter.drawPixmap(
                at,
                picture.scaled(
                    round(each.width() * self.SCALE),
                    round(each.height() * self.SCALE),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        painter.end()


QHD = Rect(0, 0, 2560, 1400)
"""A 1440p screen's work area, its taskbar left out."""


def subtitles(
    area: Rect = AREA, mode: CaptionMode = CaptionMode.INSTANT
) -> Callable[[Lab], QWidget]:
    """Video, film & TV on a screen with work area `area` (1080p's or
    1440p's): the window along its bottom, wide, its text 4.5 % of the
    screen's height, showing its offered timing, no source or language line, no panel
    and an outline round the letters (556)."""

    def run(lab: Lab) -> QWidget:
        return _subtitles(lab, area, mode)

    return run


def _subtitles(lab: Lab, area: Rect, mode: CaptionMode) -> QWidget:
    value = on(use_presets.VIDEO)
    windows = CaptionWindows(None, MIC, lambda: [area])
    windows.set_labels(LABELS, "You")
    windows.set_look(
        replace(
            CaptionLook(),
            show_language=value.show_language,
            show_source=value.show_source,
            edge=TextEdge(value.caption_edge),
            word_links=WordLinks.OFF,
        )
    )
    windows.set_presets(menu_of(value))
    windows.set_captioned([("Video Player.exe", APP)])
    shown = windows.windows["Video Player.exe"]
    shown.opacity_wanted.emit(0.0)  # the window's cog is set to a clear panel
    windows.set_timing(mode)
    lab.time(
        "subtitles_on",
        lambda: windows.set_subtitles((value.subtitle_size, value.subtitle_width)),
        budget=budgets.CLICK,
    )
    # Photograph the settled subtitles. Give each synthetic caption its
    # reading interval on the window's clock before the next arrives.
    now = shown.clock()
    windows.word_clock = shown.clock = lambda: now
    for update in finished(2):
        now = max(now, shown.read_until() or now)
        windows.apply(update)
        for _ in range(40):  # two seconds of paints at 20 Hz, including the handover
            now += 0.05
            windows.release_words()
            shown.check_card_room()
            shown.canvas.grab()
    lab.pump()
    shown.canvas.repaint()
    lab.closing.append(windows.close)
    return _Screen([shown], area)


def subtitles_back(lab: Lab) -> QWidget:
    """And back: the window where the learner had it, at its own size,
    when another preset is picked."""
    value = on(use_presets.VIDEO)
    windows = CaptionWindows(None, MIC, _areas)
    windows.set_labels(LABELS, "You")
    windows.set_captioned([("Video Player.exe", APP)])
    shown = windows.windows["Video Player.exe"]
    shown.always_shown = True
    for update in finished(12):
        windows.apply(update)
    windows.set_subtitles((value.subtitle_size, value.subtitle_width))
    lab.pump()
    lab.time("subtitles_off", lambda: windows.set_subtitles(None), budget=budgets.CLICK)
    lab.pump()
    lab.closing.append(windows.close)
    return _Screen([shown])


def undo_after_a_switch(lab: Lab) -> QWidget:
    """A window's notice line after Learning, with changes not saved, was
    left for Conversation: what went, and Undo (587)."""
    shown = window(lab)
    menu = replace(
        menu_of(on(use_presets.CONVERSATION)), undo=(Undo.SWITCHED, "Learning")
    )
    shown.set_presets(menu)
    shown.show_notice(undo_line(undo_note(menu)), 8.0)
    lab.pump()
    lab.closing.append(shown.close)
    return shown


def preset_line(
    value: Callable[[], AppSettings], naming: bool = False
) -> Callable[[Lab], QWidget]:
    """Settings > Presets with the preset line (587): `value`'s preset, as
    saved or with changes not saved - and `naming`, Save as new preset…'s
    name field."""

    def run(lab: Lab) -> QWidget:
        view = PresetsView(menu_of(value()))
        shown = pages.settings("presets", presets=view)(lab)
        if naming:
            view.naming.change(True)
            lab.pump()
        return shown

    return run


def settings_presets(lab: Lab) -> QWidget:
    """Settings > Presets, Video in use: the presets, and what it changes."""
    value = on(use_presets.VIDEO)
    value = replace(value, word_links="arrows")  # a learner's change in it, say
    value = use_presets.saved_into(value)
    view = PresetsView(menu_of(value))
    return pages.settings("presets", presets=view)(lab)


def settings_timing_video(lab: Lab) -> QWidget:
    """Settings > Timing, Video in use: Instant is selected and carries
    the quiet Recommended tag (638)."""
    from polyglotic_desktop.ui_next.views.panels import Timing, TimingView

    value = on(use_presets.VIDEO)
    view = PresetsView(menu_of(value))
    return pages.settings(
        "timing", presets=view, timing=TimingView(Timing(value.caption_mode))
    )(lab)


STATES = [
    State(f"ui_next.{name}", run, gated=True, scene=scene)
    for name, run, scene in (
        ("w1_presets", dropdown(use_presets.EVERYDAY), True),
        ("w1_presets_conversation", dropdown(use_presets.CONVERSATION, True), True),
        ("w1_subtitles", subtitles(), False),
        ("w1_subtitles_1440p", subtitles(QHD, CaptionMode.SCROLLING), False),
        ("w1_subtitles_back", subtitles_back, False),
        ("w4_settings_presets", settings_presets, False),
        ("w4_settings_timing_video", settings_timing_video, False),
        ("w1_presets_edited", dropdown(use_presets.LEARNING, changed=True), True),
        ("w1_presets_undo", undo_after_a_switch, True),
        ("w4_preset_line", preset_line(lambda: on(use_presets.LEARNING)), False),
        ("w4_preset_line_edited", preset_line(edited), False),
        ("w4_preset_line_save_as", preset_line(edited, naming=True), False),
    )
]
