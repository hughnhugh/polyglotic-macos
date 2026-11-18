"""The caption windows over full-screen apps and on every Space, on a Mac
(polyglotic-hq 429, decision 0201): the collection behaviour and the
activation policy as rules, the front watch's calls with stand-ins, and
the window list on a Mac itself. The windows themselves are proven on
GitHub's Mac (`tools.macos_full_screen_checks`): pytest's Qt is offscreen,
where a window has no `NSWindow`."""

import contextlib

import pytest

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.macos import on_top, window_list
from polyglotic_desktop.platform.macos.on_top import (
    ABOVE,
    CAN_JOIN_ALL_APPLICATIONS,
    CAN_JOIN_ALL_SPACES,
    FULL_SCREEN_AUXILIARY,
    FULL_SCREEN_NONE,
    FULL_SCREEN_PRIMARY,
    IGNORES_CYCLE,
    LEVEL,
    MOVE_TO_ACTIVE_SPACE,
    PARTICIPATES_IN_CYCLE,
    POP_UP_MENU_LEVEL,
    QT_ON_TOP_LEVEL,
    STATIONARY,
    FrontWatch,
    Panel,
    collection_behaviour,
    lifted,
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


def test_a_popover_tip_sign_or_menu_goes_above_the_caption_windows() -> None:
    """Qt makes a caption window's settings popover at its window's level
    (the screen saver's), and the caption windows are ordered to the front
    at every caption: at the same level the popover went behind its window
    (the user, 2026-11-18: "caption settings modal is behind overlay /
    caption window"; 515). Every panel showing at an always-on-top level
    that isn't a caption window, the joined window or the card goes one
    level higher; a dialog and a plain tool window stay where they are."""
    caption, card = Panel(1, 11, LEVEL), Panel(2, 12, LEVEL)
    popover = Panel(3, 13, LEVEL)  # made with its caption window as parent
    sign = Panel(4, 14, QT_ON_TOP_LEVEL)
    menu = Panel(5, 15, POP_UP_MENU_LEVEL)
    dialog, floating = Panel(6, 16, 0), Panel(7, 17, 3)
    already = Panel(8, 18, ABOVE)
    showing = [caption, card, popover, sign, menu, dialog, floating, already]
    assert lifted(showing, {11, 12}) == [3, 4, 5, 8]
    assert ABOVE > LEVEL


def test_put_on_top_orders_the_windows_then_lifts_the_rest_above(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caption windows set and ordered front first, bottom first; then
    the popover - at `ABOVE` - ordered front over them. A window handed
    once (a caption window, the card) is never lifted by a later call that
    hands only the card (`_card_on_top`)."""
    done: list[tuple[str, int, int]] = []
    numbers = {101: 11, 102: 12, 103: 13}  # NSWindow -> its number
    showing = [Panel(101, 11, LEVEL), Panel(102, 12, LEVEL), Panel(103, 13, LEVEL)]
    monkeypatch.setattr(on_top, "window_of", lambda view: view + 100)
    monkeypatch.setattr(on_top, "_number", lambda window, _s: numbers[window])
    monkeypatch.setattr(on_top, "panels_showing", lambda: showing)

    def set_(window: int, level: int = LEVEL) -> bool:
        done.append(("set", window, level))
        return False

    monkeypatch.setattr(on_top, "above_everything", set_)
    monkeypatch.setattr(
        on_top.objc,
        "send",
        lambda window, selector, **_k: done.append((selector, window, 0)),
    )
    monkeypatch.setattr(on_top.objc, "pool", contextlib.nullcontext)
    mac = on_top.MacOnTop(accessory=lambda: True)
    mac.put_on_top([1, 2])  # a caption window, then the card
    assert done == [
        ("set", 101, LEVEL),
        ("orderFrontRegardless", 101, 0),
        ("set", 102, LEVEL),
        ("orderFrontRegardless", 102, 0),
        ("set", 103, ABOVE),  # the popover
        ("orderFrontRegardless", 103, 0),
    ]
    done.clear()
    mac.put_on_top([2])  # the card alone: the caption window isn't lifted
    assert [d for d in done if d[0] == "set"] == [
        ("set", 102, LEVEL),
        ("set", 103, ABOVE),
    ]


def test_the_watch_calls_and_a_failing_call_never_reaches_macos() -> None:
    """The watch's calls come from macOS's notification centre: an error
    raised into it would end the app."""
    calls: list[str] = []
    FrontWatch(lambda: calls.append("changed"))._heard(0)
    assert calls == ["changed"]

    def fails() -> None:
        raise RuntimeError("no")

    FrontWatch(fails)._heard(0)  # logged, not raised


def test_a_mac_keeps_its_windows_on_top_whenever_asked() -> None:
    """Qt puts a window back at its own level when its flags change, so
    the interface's `keep_on_top` always sets them on a Mac."""
    assert on_top.MacOnTop(accessory=lambda: True).game_in_front()


def test_made_the_app_becomes_an_accessory(caplog: pytest.LogCaptureFixture) -> None:
    """Before the interface makes any caption window: a window first shown
    while the app is in the Dock never joins a full-screen app's Space
    (429's run 2)."""
    asked: list[bool] = []

    def accessory() -> bool:
        asked.append(True)
        return True

    on_top.MacOnTop(accessory=accessory)
    assert asked == [True]
    on_top.MacOnTop(accessory=lambda: False)
    assert "kept the app in the Dock" in caplog.text


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


def test_macos_never_resizes_a_caption_window_itself() -> None:
    """Qt makes a frameless window resizable: macOS then resized a caption
    window from a press just inside its edge before the app heard of it -
    to 1 px wide, and never remembered (GitHub's Mac, 515). Cleared, the
    app's own edges resize it; a panel is non-activating as before."""
    qt_made = 2 | 4 | on_top.RESIZABLE  # closable, miniaturizable, resizable: 14
    assert on_top.style_mask(qt_made, panel=True) == 2 | 4 | on_top.NONACTIVATING_PANEL
    assert on_top.style_mask(qt_made, panel=False) == 2 | 4
    once = on_top.style_mask(qt_made | on_top.NONACTIVATING_PANEL, panel=True)
    assert on_top.style_mask(once, panel=True) == once  # set once, left alone after
