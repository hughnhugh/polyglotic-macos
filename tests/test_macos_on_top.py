"""The caption windows over full-screen apps and on every Space, on a Mac
(polyglotic-hq 429, decision 0201): the collection behaviour and the
activation policy as rules, the front watch's calls with stand-ins, and
the window list on a Mac itself. The windows themselves are proven on
GitHub's Mac (`tools.macos_parity_checks`): pytest's Qt is offscreen,
where a window has no `NSWindow`."""

import pytest

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.macos import on_top, window_list
from polyglotic_desktop.platform.macos.on_top import (
    ACCESSORY,
    CAN_JOIN_ALL_APPLICATIONS,
    CAN_JOIN_ALL_SPACES,
    FULL_SCREEN_AUXILIARY,
    FULL_SCREEN_NONE,
    FULL_SCREEN_PRIMARY,
    IGNORES_CYCLE,
    LEVEL,
    MOVE_TO_ACTIVE_SPACE,
    PARTICIPATES_IN_CYCLE,
    REGULAR,
    STATIONARY,
    FrontWatch,
    collection_behaviour,
    policy_for,
)

WANTED = (
    CAN_JOIN_ALL_SPACES
    | CAN_JOIN_ALL_APPLICATIONS
    | FULL_SCREEN_AUXILIARY
    | STATIONARY
    | IGNORES_CYCLE
)
TRANSIENT = 1 << 3  # NSWindowCollectionBehaviorTransient: not ours to touch


def test_a_caption_window_joins_every_space_and_full_screen_apps() -> None:
    assert collection_behaviour(0) == WANTED


@pytest.mark.parametrize(
    "conflicting",
    [
        MOVE_TO_ACTIVE_SPACE,
        FULL_SCREEN_PRIMARY,
        FULL_SCREEN_NONE,
        PARTICIPATES_IN_CYCLE,
    ],
)
def test_what_conflicts_is_cleared(conflicting: int) -> None:
    """macOS refuses a window that joins every Space and moves to the
    active one; a full-screen primary isn't an auxiliary."""
    assert collection_behaviour(conflicting) == WANTED


def test_what_else_qt_set_is_kept_and_setting_twice_changes_nothing() -> None:
    once = collection_behaviour(TRANSIENT | FULL_SCREEN_PRIMARY)
    assert once == WANTED | TRANSIENT
    assert collection_behaviour(once) == once


def test_the_level_is_above_full_screen_apps() -> None:
    """The screen saver's: the floating (3), status bar (25) and modal
    panel (8, Qt's always-on-top) levels stay below a full-screen app."""
    assert LEVEL == 1000


def test_the_app_is_in_the_dock_while_an_ordinary_window_shows() -> None:
    assert policy_for([LEVEL, 0]) == REGULAR  # Home, over the captions
    assert policy_for([0]) == REGULAR


def test_the_app_is_an_accessory_while_only_its_caption_windows_show() -> None:
    assert policy_for([LEVEL, LEVEL]) == ACCESSORY
    assert policy_for([8]) == ACCESSORY  # a Qt window not yet set
    assert policy_for([]) == ACCESSORY  # only the menu bar's icon


def test_the_watch_follows_the_windows_then_calls() -> None:
    calls: list[str] = []
    watch = FrontWatch(
        lambda: calls.append("changed"), follow=lambda: calls.append("follow")
    )
    watch._heard(0)
    assert calls == ["follow", "changed"]


def test_a_failing_call_never_reaches_macos() -> None:
    """The watch's calls come from macOS's notification centre: an error
    raised into it would end the app."""

    def fails() -> None:
        raise RuntimeError("no")

    calls: list[str] = []
    FrontWatch(fails, follow=fails)._heard(0)
    FrontWatch(lambda: calls.append("changed"), follow=fails)._heard(0)
    assert calls == ["changed"]


def test_a_mac_keeps_its_windows_on_top_whenever_asked() -> None:
    """Qt puts a window back at its own level when its flags change, so
    the interface's `keep_on_top` always sets them on a Mac."""
    assert on_top.MacOnTop().game_in_front()


def test_the_macs_record_has_its_on_top_and_front_watch() -> None:
    mac = os_adapters("darwin")
    assert mac.on_top is on_top.MacOnTop
    assert mac.foreground_watch is on_top.FrontWatch


def test_the_front_window_is_the_front_apps_first_ordinary_one() -> None:
    listed = [
        window_list.Listed(9, LEVEL, 100, (0, 0, 10, 10)),  # a caption window
        window_list.Listed(8, 25, 200, (0, 0, 10, 10)),  # the menu bar's
        window_list.Listed(7, 0, 300, (0, 0, 10, 10)),  # another app's
        window_list.Listed(6, 0, 200, (0, 0, 10, 10)),
        window_list.Listed(5, 0, 200, (0, 0, 10, 10)),
    ]
    assert window_list.front_window(listed, 200) == 6
    assert window_list.front_window(listed, 100) == 0  # no ordinary window
    assert window_list.front_window([], 200) == 0


@pytest.mark.macos_only
def test_the_window_list_reads_numbers_levels_and_owners() -> None:
    listed = window_list.on_screen()
    assert all(isinstance(w.number, int) and isinstance(w.layer, int) for w in listed)
    assert all(w.pid >= 0 for w in listed)
