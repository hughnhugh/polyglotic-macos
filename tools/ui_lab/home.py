"""The new main window and Home's states (polyglotic-hq project 109's
structure, sections 5, 7 and 10.5), held to their budgets: the app picker
with 0, 1 and 3 apps, with one app and everything else the PC plays
(polyglotic-hq DECISIONS.md #59), and with everything the PC plays; Home at the
window's minimum (760 x 520) and wide (1600 x 900), neither with a
horizontal scrollbar; a page switch cold and warm; a theme change; signed
out, paused, and a notice on the banner (109's section 7) - the dictionary out
(199), the learning data set aside at the start and found damaged since
(206); a planned maintenance window the day before and during it, its
times in the PC's zone, named (319, 542).

Built as `main` builds it - the settings (in memory), made-up apps with
sound, the caption windows, the panels and `main.Hub`.
"""

from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from PySide6.QtWidgets import QScrollArea, QWidget

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.main import Hub, Panels, follow_settings
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ports.capture import (
    PlayingApp,
    SoundDevice,
    SoundDevices,
    SourceCategory,
)
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.learning import LearningDataProblem, SetAsideLearningData
from polyglotic_desktop.ui import theme as todays_theme
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import maintenance as maintenance_words
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.main_window import roomy_size
from tools.ui_lab.caption_window import PLANNED, _areas, in_lab_zone
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.lookup import sample_tools

APPS = [
    PlayingApp(1, "Discord", True, SourceCategory.CALL, "Discord"),
    PlayingApp(2, "Video Player", False, SourceCategory.VIDEO),
    PlayingApp(3, "Web Browser", False, SourceCategory.BROWSER),
    PlayingApp(4, "Spotify", True, SourceCategory.OTHER),
    PlayingApp(5, "Steam", False, SourceCategory.GAME),
]
WIDE = (1600, 900)
NORMAL = (1000, 740)
"""At 100 % text size; at another (`--text-size`), scaled with it."""


def scaled(size: tuple[int, int]) -> tuple[int, int]:
    """`size` at the text size the lab runs at (`style.px`)."""
    return style.px(size[0]), style.px(size[1])


class MadeUpApps:
    def playing_apps(self) -> list[PlayingApp]:
        return list(APPS)


class NoApps(MadeUpApps):
    def playing_apps(self) -> list[PlayingApp]:
        return []


class QuietApps:
    """Apps with sound open, none playing: a first run's usual PC."""

    def playing_apps(self) -> list[PlayingApp]:
        return [replace(app, playing=False) for app in APPS[1:3]]


class Memory:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = dict(values)

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: Mapping[str, object]) -> None:
        self.values = dict(values)


class _Sources:
    """`main`'s sources, as far as the caption windows need them."""

    per_app = True
    sample_shown = False

    def app_id(self, name: str) -> object:
        return f"app-{name}"

    def shown(self) -> dict[object, tuple[str, str]]:
        return {f"app-{a.name}": (a.name, a.title) for a in APPS}


DEVICES = SoundDevices(
    (
        SoundDevice("{out-2}", "Headphones (USB Headset)"),
        SoundDevice("{out-1}", "Speakers (Realtek Audio)"),
    ),
    (
        SoundDevice("{in-2}", "Headset Microphone (USB Headset)"),
        SoundDevice("{in-1}", "Microphone Array (Realtek Audio)"),
    ),
    "{out-1}",
    "{in-1}",
)
"""Made-up speakers and mics for Home's Sound (polyglotic-hq 372): none of
the PC's own is listed in a picture."""


def hub(
    lab: Lab,
    settings: dict[str, object],
    size: tuple[int, int] | None = None,
    apps: MadeUpApps | QuietApps | None = None,
    tools: LearningTools | None = None,
) -> Hub:
    desktop = DesktopApp(Memory(settings), tools, apps or MadeUpApps())
    windows = CaptionWindows(None, MIC, _areas)
    panels = Panels(desktop.settings, windows)
    assert desktop.apps is not None
    built = Hub(desktop, windows, panels, desktop.apps, per_app=True)
    built.list_devices = lambda: DEVICES  # Home's Sound (372): made up
    follow_settings(windows, desktop, _Sources())  # type: ignore[arg-type]
    desktop.settings.changed.connect(
        lambda: follow_settings(windows, desktop, _Sources())  # type: ignore[arg-type]
    )
    for window in windows.windows.values():
        window.hide()  # Home is the subject; the windows are elsewhere
    built.window.resize(*(size or scaled(NORMAL)))
    built.window.show()
    lab.pump()

    def close() -> None:
        windows.close()
        built.close()
        desktop.close()

    lab.closing.append(close)
    return built


def no_horizontal_scrollbar(built: Hub) -> None:
    for page in built.window.findChildren(QScrollArea):
        if page.isVisible():
            bar = page.horizontalScrollBar()
            assert not bar.isVisible(), f"a horizontal scrollbar: {page.objectName()}"


def picker_none(lab: Lab) -> QWidget:
    """Nothing chosen: a learner who stopped everything (a new learner
    captions everything the PC plays since 484: `everything`)."""
    built = hub(lab, {"whole_system": False})
    no_horizontal_scrollbar(built)
    return built.window


def picker_no_apps(lab: Lab) -> QWidget:
    built = hub(lab, {"whole_system": False}, apps=NoApps())
    no_horizontal_scrollbar(built)
    return built.window


def sample(lab: Lab) -> QWidget:
    """Nothing playing on a first run: Home offers the sample (176), and
    says "Stop the sample" while it's on."""
    built = hub(lab, {"learning": "zh", "whole_system": False}, apps=QuietApps())

    def turn(on: bool) -> None:
        built.sample_on = on
        built.follow()

    built.sample = turn
    built.follow()
    button = built.home.picker_card.sample_button
    for _ in range(10):
        lab.time("click", button.click)  # on, then off
    no_horizontal_scrollbar(built)
    return built.window


def sample_ended(lab: Lab) -> QWidget:
    """The sample played to its end (203's item 5, option B; polyglotic-hq
    208): offered again, with the next step - an app of the learner's own.
    Its window stays for lookups (not drawn here)."""
    built = hub(lab, {"learning": "zh", "whole_system": False}, apps=QuietApps())
    built.sample = lambda on: None
    built.sample_ended = True
    built.follow()
    no_horizontal_scrollbar(built)
    return built.window


def start_with_windows(lab: Lab) -> QWidget:
    """After a good session: "Start Polyglotic with Windows?", once (176)."""
    built = hub(lab, {"apps": ["Discord"]})
    built.home.offer_start_with_windows()
    lab.pump()
    no_horizontal_scrollbar(built)
    return built.window


def update_ready(lab: Lab) -> QWidget:
    """An update downloaded (polyglotic-hq 299): a quiet card under the
    state - "Version X is ready", what's new in two lines, Restart now and
    Later."""
    built = hub(lab, {"apps": ["Discord"], "level_line_dismissed": True})
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.home.show_update(
        "0.1.6",
        (
            (
                "Hear a word: the speaker beside Close on a word's card says it "
                "aloud in one of Windows' own…"
            ),
            (
                "Text size: Settings > App > Text size makes Polyglotic's own "
                "words smaller or larger."
            ),
        ),
    )
    lab.pump()
    assert built.home.update_card.isVisible(), "the update card isn't shown"
    no_horizontal_scrollbar(built)
    return built.window


def update_metered(lab: Lab) -> QWidget:
    """An update found on a metered connection (polyglotic-hq 345): not
    downloaded by itself - its size, why it waits, Download anyway and
    Later."""
    built = hub(lab, {"apps": ["Discord"], "level_line_dismissed": True})
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.home.show_update(
        "0.1.7",
        (
            (
                "What's new after an update: the first time Polyglotic starts "
                "after it updates, Home says what changed in the new version in…"
            ),
        ),
        metered_size=91_960_000,
    )
    lab.pump()
    assert built.home.download_anyway.isVisible(), "Download anyway isn't shown"
    no_horizontal_scrollbar(built)
    return built.window


def whats_new(lab: Lab) -> QWidget:
    """After an update (polyglotic-hq 345): what's new in this version on
    Home, in three lines, the version skipped named, All the changes and
    Close - once, until it's closed."""
    built = hub(lab, {"apps": ["Discord"], "level_line_dismissed": True})
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.home.show_whats_new(
        "0.1.7",
        (
            (
                "What's new after an update: the first time Polyglotic starts after "
                "it updates, Home says what changed in the new version in a few lines,…"
            ),
            (
                "Russian's dictionary: learn Russian on the Learning page and its card "
                "offers the dictionary to download (about 13 MB; 62 MB once unpacked)."
            ),
            "A metered connection doesn't download an update by itself.",
        ),
        ("0.1.6",),
    )
    lab.pump()
    assert built.home.whats_new_card.isVisible(), "What's new isn't shown"
    no_horizontal_scrollbar(built)
    return built.window


def picker_one(lab: Lab) -> QWidget:
    built = hub(lab, {"apps": ["Discord"], "caption_mic": True})
    built.desktop.set_connection(ConnectionState.LISTENING)
    lab.time(
        "language_chip",
        lambda: built.picker.set_translate_into(
            "Discord",
            "ja" if built.picker.value.captioned[0].translate_into != "ja" else "en",
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    lab.time(
        "mic_mark",
        lambda: built.picker.set_show_mic(
            "Discord", not built.picker.value.captioned[0].show_mic
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    return built.window


def picker_full(lab: Lab) -> QWidget:
    built = hub(lab, {"apps": ["Discord", "Video Player"], "targets": ["en"]})

    def add_then_remove() -> None:
        if len(built.picker.value.captioned) < 3:
            built.picker.add("Web Browser")
        else:
            built.picker.remove("Web Browser")

    lab.time("add_or_stop_an_app", add_then_remove, repeat=6, budget=budgets.CLICK)
    if len(built.picker.value.captioned) < 3:
        built.picker.add("Web Browser")
    lab.pump()
    assert built.picker.value.full
    windows = built.windows.windows
    windows["Video Player"].set_language("")  # Original only
    windows["Discord"].set_show_mic(True)
    lab.pump()
    return built.window


def everything_else(lab: Lab) -> QWidget:
    """One app and everything else (project 139): its row after the app's,
    the switch on, "1 app + everything else", and the Add list greyed with
    the reason."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    lab.time(
        "everything_else_switch",
        lambda: built.picker.set_everything_else(
            not built.picker.value.everything_else
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    if not built.picker.value.everything_else:
        built.picker.set_everything_else(True)
    lab.pump()
    assert built.picker.value.everything_else and built.picker.value.full
    for window in built.windows.windows.values():
        window.hide()  # Home is the subject
    return built.window


def everything(lab: Lab) -> QWidget:
    """Everything the PC plays - a new learner's first launch (484): what
    it takes in, a call's voices too, and the apps playing to caption one
    instead with one click."""
    built = hub(lab, {})
    built.desktop.set_connection(ConnectionState.LISTENING)
    return built.window


def at_minimum(lab: Lab) -> QWidget:
    """Narrowed from its usual size to the least it opens at (960 x 680
    times the text size, 248; `roomy_size` - no longer its minimum, which
    is `at_floor`'s, polyglotic-hq 586): nothing scrolls sideways."""
    built = hub(lab, {"apps": ["Discord", "Video Player", "Web Browser"]})
    built.window.resize(*roomy_size())
    lab.pump()
    assert (built.window.width(), built.window.height()) == roomy_size()
    no_horizontal_scrollbar(built)
    return built.window


def wide(lab: Lab) -> QWidget:
    built = hub(lab, {"apps": ["Discord", "Video Player"]}, scaled(WIDE))
    no_horizontal_scrollbar(built)
    column = built.home.picker_card.width()
    assert column <= style.px(720), column
    return built.window


def page_switches(lab: Lab) -> QWidget:
    built = hub(lab, {"apps": ["Discord"]})
    order = ["account", "settings", "help"]
    for key in order:  # each page shown for the first time
        lab.time(
            "page_switch_cold",
            partial(built.window.go_to, key),
            budget=budgets.PAGE_SWITCH_COLD,
        )
    built.window.go_to("home")
    lab.pump()
    for _ in range(3):
        for key in [*order, "home"]:
            lab.time(
                "page_switch_warm",
                partial(built.window.go_to, key),
                budget=budgets.PAGE_SWITCH_WARM,
            )
    built.window.go_to("home")
    lab.pump()
    return built.window


def _theme(mode: str, name: str) -> style.Theme:
    palette = todays_theme.palette(mode, name)
    family = todays_theme.THEMES[name].heading_family
    return style.Theme(asdict(palette), family, dark=mode == "dark")


def theme_change(lab: Lab) -> QWidget:
    built = hub(lab, {"apps": ["Discord", "Video Player"]})
    looks = [
        ("light", "margin"),
        ("dark", "glaze"),
        ("light", "signal"),
        ("dark", "margin"),
    ]
    window = built.window
    for mode, name in looks * 2:
        lab.time(
            "theme",
            partial(window.set_theme, _theme(mode, name)),
            budget=budgets.THEME,
        )
    # chosen where it's chosen: Settings on show, the window's biggest page;
    # then a page not shown since, restyled as it's shown - a first show
    # in that theme (polyglotic-hq 355)
    for mode, name in looks * 2:
        window.go_to("settings")
        lab.pump()
        lab.time(
            "theme_on_settings",
            partial(window.set_theme, _theme(mode, name)),
            budget=budgets.THEME,
        )
        lab.time(
            "page_after_theme",
            partial(window.go_to, "home"),
            budget=budgets.PAGE_SWITCH_COLD,
        )
    window.set_theme(_theme("light", "margin"))
    window.go_to("home")
    lab.pump()
    return window


def signed_out(lab: Lab) -> QWidget:
    """Not signed in - you need an invite code from us, with Sign in; the
    picker and the panels as usable as ever (settings are on this PC)."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    desktop = built.desktop
    states = iter([ConnectionState.SIGN_IN_NEEDED, ConnectionState.LISTENING] * 6)
    lab.time(
        "state_change",
        lambda: desktop.set_connection(next(states)),
        repeat=11,  # ends signed out
        budget=budgets.CLICK,
    )
    no_horizontal_scrollbar(built)
    return built.window


def paused(lab: Lab) -> QWidget:
    """Paused, with how to resume, and Resume."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    built.desktop.set_connection(ConnectionState.LISTENING)
    lab.time("pause", built.desktop.pause.toggle, repeat=11, budget=budgets.CLICK)
    return built.window


def server_busy(lab: Lab) -> QWidget:
    """The server is at capacity. The status stays put while the connection retries."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    desktop = built.desktop
    desktop.set_connection(ConnectionState.LISTENING)
    states = iter([ConnectionState.SERVER_BUSY, ConnectionState.LISTENING] * 6)
    lab.time(
        "state_change",
        lambda: desktop.set_connection(next(states), 24.0),
        repeat=11,  # ends busy
        budget=budgets.CLICK,
    )
    no_horizontal_scrollbar(built)
    return built.window


def unreachable(why: Unreachable, lab: Lab) -> QWidget:
    """Waiting to try again, and why the server can't be reached: what's
    wrong, whose side it's on and what to do, then the countdown - in
    place of a bare "Reconnecting" (polyglotic-hq 251). Timed between two
    causes, not through Listening: two drops would put "Connection
    unstable" on the banner."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    desktop = built.desktop
    desktop.set_connection(ConnectionState.LISTENING)
    other = Unreachable.OFFLINE if why is not Unreachable.OFFLINE else Unreachable.DOWN
    causes = iter([why, other] * 6)

    def change() -> None:
        desktop.set_connection(ConnectionState.WAITING, 8.0, next(causes))

    lab.time("state_change", change, repeat=11, budget=budgets.CLICK)  # ends on why
    no_horizontal_scrollbar(built)
    return built.window


def maintenance(when: datetime, lab: Lab) -> QWidget:
    """A planned maintenance window (319): the day before, Home's banner;
    during it, its title (and so the tray's) and no banner beside it -
    the times in the PC's zone, named once a line (542)."""
    in_lab_zone(lab)
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]})
    built.home.state._wall_clock = lambda: when
    built.set_maintenance(PLANNED)
    lab.closing.append(lambda: maintenance_words.hold(None))  # held for the windows
    desktop = built.desktop
    if when < PLANNED.starts_at:
        desktop.set_connection(ConnectionState.LISTENING)
    else:
        desktop.set_connection(ConnectionState.WAITING, 120.0, Unreachable.MAINTENANCE)
    lab.pump()
    no_horizontal_scrollbar(built)
    return built.window


def notice(lab: Lab) -> QWidget:
    """Listening at a busy time: the banner in the caption windows' words."""
    built = hub(
        lab, {"apps": ["Discord"], "targets": ["en"], "caption_mode_chosen": "live"}
    )
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.desktop.set_minutes(41, None)

    def busy() -> None:
        built.busy = False
        built.set_busy(True)

    lab.time("notice", busy, repeat=6, budget=budgets.CLICK)
    return built.window


LEVEL_SET_ASIDE: dict[str, object] = {
    "apps": ["Discord"],
    "targets": ["en"],
    "caption_mode_chosen": "live",
    "level_line_dismissed": True,  # the banner is the subject, not the level
}
"""Listening to Discord, the level line put off: the banners' states."""


def level_line(lab: Lab) -> QWidget:
    """No level set yet - the first run doesn't ask (polyglotic-hq 293):
    one quiet line under the state asks for it."""
    built = hub(lab, {"apps": ["Discord"], "targets": ["en"]}, tools=sample_tools())
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.desktop.set_minutes(41, None)
    lab.pump()
    assert built.home.level_line.isVisible(), "the level line isn't shown"
    no_horizontal_scrollbar(built)
    return built.window


def dictionary_out(lab: Lab) -> QWidget:
    """Listening, the learner's dictionary damaged: the banner says so and
    how to fix it (polyglotic-hq 199)."""
    built = hub(
        lab,
        LEVEL_SET_ASIDE,
        tools=sample_tools(DictionaryProblem.DAMAGED),
    )
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.desktop.set_minutes(41, None)
    lab.pump()
    return built.window


SET_ASIDE = SetAsideLearningData(
    Path("C:/Users/learner/AppData/Roaming/Polyglotic")
    / "learning.sqlite.damaged-20261108T063000Z",
    LearningDataProblem.DAMAGED,
)
"""Made-up learning data set aside, where the app keeps it on Windows."""


def learning_set_aside(lab: Lab) -> QWidget:
    """Listening, the learner's learning data set aside at the start: the
    banner says so, names the file and says the words are coming back
    (polyglotic-hq 206)."""
    tools = sample_tools()
    tools.learning_set_aside = SET_ASIDE  # as `main` hands the store's over
    built = hub(
        lab,
        LEVEL_SET_ASIDE,
        tools=tools,
    )
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.desktop.set_minutes(41, None)
    lab.pump()
    return built.window


def learning_unsaved(lab: Lab) -> QWidget:
    """Listening, the learner's learning data found damaged since the start:
    the banner says nothing is kept until a restart, which brings the words
    back (polyglotic-hq 206)."""
    tools = sample_tools()
    built = hub(
        lab,
        LEVEL_SET_ASIDE,
        tools=tools,
    )
    built.desktop.set_connection(ConnectionState.LISTENING)
    built.desktop.set_minutes(41, None)
    tools.learning_damaged.emit(SET_ASIDE)  # as from the store's thread
    lab.pump()
    return built.window


STATES = [
    State(f"ui_next.w4_{name}", run, gated=True)
    for name, run in (
        ("picker_none", picker_none),
        ("picker_no_apps", picker_no_apps),
        ("sample", sample),
        ("sample_ended", sample_ended),
        ("start_with_windows", start_with_windows),
        ("update_ready", update_ready),
        ("update_metered", update_metered),
        ("whats_new", whats_new),
        ("picker_one", picker_one),
        ("picker_full", picker_full),
        ("everything_else", everything_else),
        ("everything", everything),
        ("home_minimum", at_minimum),
        ("home_wide", wide),
        ("page_switches", page_switches),
        ("theme_change", theme_change),
        ("signed_out", signed_out),
        ("paused", paused),
        ("server_busy", server_busy),
        # the server can't be reached: ours, and no telling whose (251)
        ("server_down", partial(unreachable, Unreachable.DOWN)),
        ("cant_reach", partial(unreachable, Unreachable.NO_ANSWER)),
        ("notice", notice),
        # planned maintenance (319): the evening before, and during it (542)
        (
            "maintenance_ahead",
            partial(maintenance, datetime(2026, 11, 20, 9, tzinfo=UTC)),
        ),
        (
            "maintenance_during",
            partial(maintenance, datetime(2026, 11, 20, 19, 30, tzinfo=UTC)),
        ),
        ("dictionary_out", dictionary_out),
        ("learning_set_aside", learning_set_aside),
        ("learning_unsaved", learning_unsaved),
        ("level_line", level_line),
    )
]
