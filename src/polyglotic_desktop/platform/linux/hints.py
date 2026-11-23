"""What a Linux desktop says about itself over D-Bus (polyglotic-hq 546's
slice 4, 571): whether it prefers light or dark, and whether the connection
is metered - `ports/system.py`'s `LightTaskbar` and `OsAdapters.metered`,
through jeepney, as the keyring (`secret_service.py`) asks.

- **Light or dark:** the settings portal's `org.freedesktop.appearance`
  `color-scheme` (xdg-desktop-portal, on every current desktop: 0 no
  preference, 1 dark, 2 light). The tray's icon is drawn for the panel it
  sits on (`light_panel`): GNOME's top bar is dark in both of GNOME's
  styles, so there it's always the dark panel's icon; KDE's, Xfce's and
  LXQt's panels follow the desktop's colours, so there the icon is the
  light panel's when the desktop prefers light. Anywhere else, or when no
  portal answers: dark, as before.
- **Metered:** NetworkManager's `Metered` on the system bus - 1 (yes) or 3
  (guessed yes: a phone's hotspot) is metered; anything else, or no
  NetworkManager, isn't, as before. A dictionary pack then asks before it
  downloads, and an update found waits for the learner (decision 0122).

Each answer is asked with a short timeout on whatever thread asks - the
tray asks every 10 seconds, on the interface's - so a desktop that doesn't
answer can't hold the app. The bus is handed in (`ask`), so tests never
touch the PC's.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

log = logging.getLogger(__name__)

TIMEOUT = 0.5
"""Seconds an answer may take: the portal's or NetworkManager's."""

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
SETTINGS = "org.freedesktop.portal.Settings"
APPEARANCE, COLOR_SCHEME = "org.freedesktop.appearance", "color-scheme"
NO_PREFERENCE, PREFERS_DARK, PREFERS_LIGHT = 0, 1, 2

NETWORK_MANAGER = ("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager")
METERED = (1, 3)
"""`NMMetered`: yes, and guessed yes."""

PANELS_THAT_FOLLOW = ("KDE", "XFCE", "LXQT")
"""Desktops whose panel takes the desktop's light or dark
(`XDG_CURRENT_DESKTOP`'s names)."""

Ask = Callable[[str, str, str, str, str, tuple[Any, ...]], Any]
"""(bus, service, path, interface, method, its arguments) -> the reply's
body; raises when there's no answer."""


def ask_dbus(
    bus: str,
    service: str,
    path: str,
    interface: str,
    method: str,
    args: tuple[Any, ...],
) -> Any:
    """`Ask` on the session or system bus, through jeepney: a connection
    for the one question (a few milliseconds), the reply within `TIMEOUT`."""
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection

    signature = "ss" if method in ("ReadOne", "Read", "Get") else ""
    address = DBusAddress(path, bus_name=service, interface=interface)
    with open_dbus_connection(bus=bus, auth_timeout=TIMEOUT) as connection:
        message = new_method_call(address, method, signature, args)
        return connection.send_and_get_reply(message, timeout=TIMEOUT).body


def _variant(value: Any) -> Any:
    """A D-Bus variant's value (jeepney gives `(signature, value)`), unwrapped
    as often as it's wrapped: the portal's old `Read` wraps it twice."""
    while isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        value = value[1]
    return value


def color_scheme(ask: Ask = ask_dbus) -> int | None:
    """The portal's `color-scheme` (0, 1 or 2); None if no portal answers.
    `ReadOne` (portal version 2, 2023), else the older `Read`."""
    for method in ("ReadOne", "Read"):
        try:
            body = ask("SESSION", *PORTAL, SETTINGS, method, (APPEARANCE, COLOR_SCHEME))
        except Exception as error:  # noqa: BLE001 - no answer is "doesn't say"
            log.debug("the settings portal's %s: %s", method, error)
            continue
        value = _variant(body[0]) if body else None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def prefers(ask: Ask = ask_dbus) -> str | None:
    """ "light" or "dark" as the desktop prefers; None if it has no
    preference or doesn't say."""
    scheme = color_scheme(ask)
    if scheme == PREFERS_LIGHT:
        return "light"
    if scheme == PREFERS_DARK:
        return "dark"
    return None


def light_panel(environ: Mapping[str, str] | None = None, ask: Ask = ask_dbus) -> bool:
    """`LightTaskbar` on Linux: whether the panel the tray sits in is light -
    on a desktop whose panel follows its colours, when it prefers light."""
    env = os.environ if environ is None else environ
    desktops = env.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if not any(name in PANELS_THAT_FOLLOW for name in desktops):
        return False  # GNOME's top bar, and the rest: dark
    return prefers(ask) == "light"


def metered(ask: Ask = ask_dbus) -> bool:
    """Whether NetworkManager calls the connection metered (yes, or guessed
    yes); not where it doesn't say."""
    try:
        body = ask("SYSTEM", *NETWORK_MANAGER, "org.freedesktop.DBus.Properties", "Get",
                   (NETWORK_MANAGER[0], "Metered"))  # fmt: skip
    except Exception as error:  # noqa: BLE001 - no NetworkManager: not metered
        log.debug("NetworkManager's Metered: %s", error)
        return False
    value = _variant(body[0]) if body else None
    return isinstance(value, int) and value in METERED


__all__ = ["color_scheme", "light_panel", "metered", "prefers"]
