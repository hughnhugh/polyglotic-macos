"""Wayland's GlobalShortcuts portal for the speaker hold key."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from polyglotic_desktop.core.listening.dictation_keys import DictationKey, Modifier
from polyglotic_desktop.core.listening.type_theirs import PORTAL_POLL_SEC
from polyglotic_desktop.platform.linux.hints import PORTAL, TIMEOUT, ask_dbus

log = logging.getLogger(__name__)
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
SHORTCUT_ID = "type-what-they-said"

_MODIFIERS = {
    Modifier.CTRL: "CTRL",
    Modifier.ALT: "ALT",
    Modifier.SHIFT: "SHIFT",
    Modifier.WIN: "LOGO",
}
_KEYSYMS = {
    "backspace": "BackSpace", "delete": "Delete", "down": "Down",
    "end": "End", "enter": "Return", "escape": "Escape", "home": "Home",
    "insert": "Insert", "left": "Left", "menu": "Menu", "page_down": "Page_Down",
    "page_up": "Page_Up", "pause": "Pause", "print_screen": "Print",
    "right": "Right", "scroll_lock": "Scroll_Lock", "space": "space",
    "tab": "Tab", "up": "Up",
}  # fmt: skip


def preferred_trigger(key: str) -> str | None:
    found = DictationKey.parse(key)
    if found is None or found.key is None or found.held_alone:
        return None
    named = _KEYSYMS.get(
        found.key, found.key if len(found.key) == 1 else found.key.upper()
    )
    return "+".join([*(_MODIFIERS[Modifier(m)] for m in found.parts[:-1]), named])


class HoldShortcut:
    """A portal-provided press and release, with one session per binding."""

    def __init__(
        self,
        key: str,
        down: Callable[[], None],
        up: Callable[[], None],
        other: Callable[[], None],
        *,
        description: str,
    ) -> None:
        self._trigger = preferred_trigger(key)
        self._down, self._up, self._other = down, up, other
        self._description = description
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self._trigger is None:
            return False
        try:
            ((kind, version),) = ask_dbus(
                "SESSION",
                *PORTAL,
                "org.freedesktop.DBus.Properties",
                "Get",
                (INTERFACE, "version"),
            )
        except (ImportError, KeyError, OSError, ValueError, TypeError):
            return False
        if kind != "u" or version < 1:
            return False
        self._thread = threading.Thread(target=self._run, name=SHORTCUT_ID, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(TIMEOUT + PORTAL_POLL_SEC.value)

    def _run(self) -> None:
        from jeepney import HeaderFields, MatchRule, message_bus
        from jeepney.io.blocking import Proxy, open_dbus_connection
        from jeepney.wrappers import DBusErrorResponse

        session: str | None = None
        held = False
        try:
            with open_dbus_connection(bus="SESSION", auth_timeout=TIMEOUT) as bus:
                rule = MatchRule(type="signal", sender=PORTAL[0])
                Proxy(message_bus, bus).AddMatch(rule)
                with bus.filter(rule) as signals:
                    token = "pg" + uuid.uuid4().hex
                    result = self._request(
                        bus,
                        signals,
                        "CreateSession",
                        "a{sv}",
                        (
                            {
                                "handle_token": ("s", token),
                                "session_handle_token": ("s", token),
                            },
                        ),
                    )
                    if result is None:
                        return
                    session = result["session_handle"][1]
                    try:
                        shortcut = (
                            SHORTCUT_ID,
                            {
                                "description": ("s", self._description),
                                "preferred_trigger": ("s", self._trigger),
                            },
                        )
                        result = self._request(
                            bus,
                            signals,
                            "BindShortcuts",
                            "oa(sa{sv})sa{sv}",
                            (
                                session,
                                [shortcut],
                                "",
                                {"handle_token": ("s", token + "bind")},
                            ),
                        )
                        if not result or not result.get("shortcuts", (None, ()))[1]:
                            return
                        for message in self._signals(bus, signals):
                            headers = message.header.fields
                            if headers.get(HeaderFields.interface) == SESSION:
                                if headers.get(HeaderFields.path) == session:
                                    break
                                continue
                            if headers.get(
                                HeaderFields.interface
                            ) != INTERFACE or message.body[:2] != (
                                session,
                                SHORTCUT_ID,
                            ):
                                continue
                            member = headers.get(HeaderFields.member)
                            if member == "Activated" and not held:
                                held = True
                                self._down()
                            elif member == "Deactivated" and held:
                                held = False
                                self._up()
                    finally:
                        self._call(bus, session, SESSION, "Close")
        except (DBusErrorResponse, KeyError, OSError, ValueError):
            log.info("The desktop did not provide a speaker shortcut")
        finally:
            if held and not self._stop.is_set():
                self._other()
                self._up()

    def _signals(self, bus: Any, signals: Any) -> Iterator[Any]:
        while not self._stop.is_set():
            try:
                yield bus.recv_until_filtered(signals, timeout=PORTAL_POLL_SEC.value)
            except TimeoutError:
                continue

    def _request(
        self, bus: Any, signals: Any, method: str, signature: str, args: tuple[Any, ...]
    ) -> dict[str, Any] | None:
        from jeepney import HeaderFields

        (handle,) = self._call(bus, PORTAL[1], INTERFACE, method, signature, args)
        for response in self._signals(bus, signals):
            headers = response.header.fields
            if (
                headers.get(HeaderFields.path) == handle
                and headers.get(HeaderFields.interface) == REQUEST
            ):
                status, result = response.body
                return dict(result) if status == 0 else None
        self._call(bus, handle, REQUEST, "Close")
        return None

    @staticmethod
    def _call(
        bus: Any,
        path: str,
        interface: str,
        method: str,
        signature: str | None = None,
        args: tuple[Any, ...] = (),
    ) -> tuple[Any, ...]:
        from jeepney import DBusAddress, new_method_call
        from jeepney.wrappers import unwrap_msg

        address = DBusAddress(path, bus_name=PORTAL[0], interface=interface)
        call = new_method_call(address, method, signature, args)
        return tuple(unwrap_msg(bus.send_and_get_reply(call, timeout=TIMEOUT)))
