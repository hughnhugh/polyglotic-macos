"""What a Linux desktop says about itself over D-Bus (polyglotic-hq 571):
light or dark from the settings portal, and a metered connection from
NetworkManager - each through a bus handed in, so these run on any OS.
`POLYGLOTIC_LINUX_DESKTOP=1` also asks a real session's portal
(`.github/workflows/linux-manners.yml`)."""

import os
import sys
from typing import Any

import pytest

from polyglotic_desktop import main
from polyglotic_desktop.platform.linux import hints


class Bus:
    """`hints.Ask`: answers by method, or raises as a bus with no such
    service does; every question kept."""

    def __init__(self, **answers: Any) -> None:
        self.answers = answers
        self.asked: list[tuple[Any, ...]] = []

    def __call__(self, *question: Any) -> Any:
        self.asked.append(question)
        method = question[4]
        if method not in self.answers:
            raise ConnectionError(f"{method}: no such service")
        return self.answers[method]


def test_the_portal_says_light_dark_or_nothing() -> None:
    assert hints.prefers(Bus(ReadOne=(("u", 2),))) == "light"
    assert hints.prefers(Bus(ReadOne=(("u", 1),))) == "dark"
    assert hints.prefers(Bus(ReadOne=(("u", 0),))) is None  # no preference
    assert hints.prefers(Bus()) is None  # no portal


def test_the_portal_is_asked_for_the_appearance_s_colour_scheme() -> None:
    bus = Bus(ReadOne=(("u", 1),))
    hints.color_scheme(bus)
    assert bus.asked == [
        (
            "SESSION",
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "ReadOne",
            ("org.freedesktop.appearance", "color-scheme"),
        )
    ]


def test_an_older_portal_answers_through_read_its_value_wrapped_twice() -> None:
    """Portal version 1 (before 2023) has no ReadOne; its Read wraps the
    value in a second variant."""
    assert hints.color_scheme(Bus(Read=(("v", ("u", 2)),))) == 2


def test_an_answer_of_another_type_is_no_answer() -> None:
    assert hints.color_scheme(Bus(ReadOne=(("s", "dark"),))) is None
    assert hints.color_scheme(Bus(ReadOne=(("b", True),))) is None


LIGHT = Bus(ReadOne=(("u", 2),))


@pytest.mark.parametrize(
    ("desktop", "light"),
    [
        ("KDE", True),
        ("XFCE", True),
        ("LXQt", True),
        ("ubuntu:GNOME", False),  # its top bar is dark in both styles
        ("GNOME", False),
        ("X-Cinnamon", False),
        ("", False),
    ],
)
def test_the_panel_is_light_only_where_it_follows_a_light_desktop(
    desktop: str, light: bool
) -> None:
    assert hints.light_panel({"XDG_CURRENT_DESKTOP": desktop}, LIGHT) is light


def test_a_dark_or_silent_desktop_has_a_dark_panel() -> None:
    kde = {"XDG_CURRENT_DESKTOP": "KDE"}
    assert hints.light_panel(kde, Bus(ReadOne=(("u", 1),))) is False
    assert hints.light_panel(kde, Bus(ReadOne=(("u", 0),))) is False
    assert hints.light_panel(kde, Bus()) is False


@pytest.mark.parametrize(
    ("value", "metered"),
    [(0, False), (1, True), (2, False), (3, True), (4, False)],
)
def test_network_manager_s_yes_and_guessed_yes_are_metered(
    value: int, metered: bool
) -> None:
    bus = Bus(Get=(("u", value),))
    assert hints.metered(bus) is metered
    assert bus.asked[0][:5] == (
        "SYSTEM",
        "org.freedesktop.NetworkManager",
        "/org/freedesktop/NetworkManager",
        "org.freedesktop.DBus.Properties",
        "Get",
    )
    assert bus.asked[0][5] == ("org.freedesktop.NetworkManager", "Metered")


def test_without_network_manager_the_connection_is_not_metered() -> None:
    assert hints.metered(Bus()) is False


def test_linux_s_adapters_ask_the_desktop() -> None:
    """Before 571 the panel was always dark and the connection never
    metered on Linux (`light_panel`, `not_metered`)."""
    found = main.linux_adapters()
    assert found.light_taskbar is hints.light_panel
    assert found.metered is hints.metered


real = pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("POLYGLOTIC_LINUX_DESKTOP") != "1",
    reason="a Linux desktop session (GitHub's runners)",
)


@real
def test_a_real_session_s_portal_answers_quickly() -> None:
    """The session made by the workflow has the portal with a preference
    set (`POLYGLOTIC_COLOR_SCHEME`: prefer-light or prefer-dark)."""
    wanted = os.environ.get("POLYGLOTIC_COLOR_SCHEME", "")
    found = hints.prefers()
    assert found == {"prefer-light": "light", "prefer-dark": "dark"}.get(wanted), found


@real
def test_a_real_system_bus_without_network_manager_is_not_metered() -> None:
    assert hints.metered() is False
