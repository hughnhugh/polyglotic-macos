r"""Real input on a Linux desktop the job made, from GitHub's runner
(polyglotic-hq 570): keys pressed and the mouse moved and clicked through
the session's own compositor, as a person's would arrive - so they reach
whichever window the compositor gives them to, Wayland or X11. Never a
person's session: only one `tools/linux_session.sh` started.

- GNOME (mutter): its RemoteDesktop D-Bus API, a session of its own, with a
  screen cast of the monitor for the mouse's place (547's harness);
- KDE (KWin, started with KWIN_WAYLAND_NO_PERMISSION_CHECKS=1): its
  fake-input Wayland protocol, spoken over the Wayland socket;
- a bare X server (Xvfb): XTest, which the X server itself turns into
  input.

`Input.make(screen)` picks one for `LINUX_SESSION_SCREEN` ("gnome", "kde",
anything else: XTest). Keys are the kernel's codes (`KEY`), a combination
pressed in order and let go in reverse (`press`).
"""

from __future__ import annotations

import ctypes
import os
import socket
import struct
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

KEY = {
    "ctrl": 29, "alt": 56, "shift": 42, "super": 125, "esc": 1, "enter": 28,
    "l": 38, "p": 25, "h": 35,
}  # fmt: skip
"""The kernel's key codes (linux/input-event-codes.h) the checks press."""
BTN_LEFT = 0x110
FAKE_INPUT_OPS = {
    "authenticate": 0,
    "button": 2,
    "pointer_motion_absolute": 9,
    "keyboard_key": 10,
}
"""fake-input.xml's request numbers, where the file isn't installed."""


def runner_only() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith(
        "linux"
    ):
        sys.exit("570: this runs only on GitHub's Linux runners")


class Input:
    """Keys and the mouse through one way in."""

    @staticmethod
    def make(screen: str | None = None) -> Input:
        runner_only()
        which = screen or os.environ.get("LINUX_SESSION_SCREEN", "xvfb")
        if which == "gnome":
            return MutterInput()
        if which == "kde":
            return KWinInput()
        return XTestInput()

    def key(self, code: int, down: bool) -> None:
        raise NotImplementedError

    def move(self, x: float, y: float) -> None:
        raise NotImplementedError

    def button(self, down: bool) -> None:
        raise NotImplementedError

    def press(self, *names: str) -> None:
        """A combination: each key down in order, then up in reverse."""
        codes = [KEY[name] for name in names]
        for code in codes:
            self.key(code, True)
            time.sleep(0.03)
        for code in reversed(codes):
            self.key(code, False)
            time.sleep(0.03)

    def click(self, x: float, y: float) -> None:
        self.move(x, y)
        time.sleep(0.1)
        self.button(True)
        time.sleep(0.05)
        self.button(False)


class MutterInput(Input):
    RD = "org.gnome.Mutter.RemoteDesktop"
    SC = "org.gnome.Mutter.ScreenCast"

    def __init__(self) -> None:
        from jeepney import DBusAddress, MatchRule, Properties, message_bus
        from jeepney.io.blocking import open_dbus_connection
        from jeepney.wrappers import unwrap_msg

        self.bus = open_dbus_connection(bus="SESSION")
        rd, sc = self.RD, self.SC
        (self.session,) = self._call("/org/gnome/Mutter/RemoteDesktop", rd, rd,
                                     "CreateSession")  # fmt: skip
        props = Properties(
            DBusAddress(self.session, bus_name=rd, interface=f"{rd}.Session")
        )
        ((_, session_id),) = unwrap_msg(
            self.bus.send_and_get_reply(props.get("SessionId"), timeout=10)
        )
        (cast,) = self._call("/org/gnome/Mutter/ScreenCast", sc, sc, "CreateSession",
                             "a{sv}", ({"remote-desktop-session-id": ("s", session_id)},))  # fmt: skip
        (self.stream,) = self._call(cast, sc, f"{sc}.Session", "RecordMonitor", "sa{sv}",
                                    ("", {"cursor-mode": ("u", 1)}))  # fmt: skip
        rule = MatchRule(type="signal", interface=f"{sc}.Stream",
                         member="PipeWireStreamAdded", path=self.stream)  # fmt: skip
        unwrap_msg(self.bus.send_and_get_reply(message_bus.AddMatch(rule), timeout=10))
        with self.bus.filter(rule) as added:
            self._call(self.session, rd, f"{rd}.Session", "Start")
            self.bus.recv_until_filtered(added, timeout=15)

    def _call(self, path: str, name: str, interface: str, method: str,
              signature: str | None = None, body: tuple[Any, ...] = ()) -> tuple[Any, ...]:  # fmt: skip
        from jeepney import DBusAddress, new_method_call
        from jeepney.wrappers import unwrap_msg

        address = DBusAddress(path, bus_name=name, interface=interface)
        message = new_method_call(address, method, signature, body)
        return tuple(unwrap_msg(self.bus.send_and_get_reply(message, timeout=15)))

    def key(self, code: int, down: bool) -> None:
        self._call(self.session, self.RD, f"{self.RD}.Session", "NotifyKeyboardKeycode",
                   "ub", (code, down))  # fmt: skip

    def move(self, x: float, y: float) -> None:
        self._call(self.session, self.RD, f"{self.RD}.Session", "NotifyPointerMotionAbsolute",
                   "sdd", (self.stream, float(x), float(y)))  # fmt: skip

    def button(self, down: bool) -> None:
        self._call(self.session, self.RD, f"{self.RD}.Session", "NotifyPointerButton",
                   "ib", (BTN_LEFT, down))  # fmt: skip


def _wayland_socket(path: str) -> socket.socket:
    """The compositor's Wayland socket, connected: Linux's alone."""
    if sys.platform == "win32":
        raise OSError("a Wayland socket: Linux only")
    connected = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connected.connect(path)
    return connected


def _wl_string(text: str) -> bytes:
    raw = text.encode() + b"\0"
    return struct.pack("<I", len(raw)) + raw + b"\0" * (-len(raw) % 4)


class KWinInput(Input):
    """KDE's fake-input protocol, version 4 (keys came in 4)."""

    XML = Path("/usr/share/plasma-wayland-protocols/fake-input.xml")

    def __init__(self) -> None:
        path = os.path.join(
            os.environ["XDG_RUNTIME_DIR"], os.environ["WAYLAND_DISPLAY"]
        )
        self.sock = _wayland_socket(path)
        self.buf = b""
        self.next_id = 1
        self.ops = self._opcodes()
        registry = self._new_id()
        self._send(1, 1, struct.pack("<I", registry))  # wl_display.get_registry
        found: dict[str, tuple[int, int]] = {}
        for obj, op, body in self._roundtrip():
            if obj == registry and op == 0:
                name = struct.unpack_from("<I", body)[0]
                size = struct.unpack_from("<I", body, 4)[0]
                interface = body[8 : 8 + size - 1].decode()
                version = struct.unpack_from("<I", body, 8 + size + (-size % 4))[0]
                found[interface] = (name, version)
        name, version = found["org_kde_kwin_fake_input"]
        self.version = min(version, 4)
        self.fake = self._new_id()
        self._send(registry, 0, struct.pack("<I", name) + _wl_string("org_kde_kwin_fake_input")
                   + struct.pack("<II", self.version, self.fake))  # fmt: skip
        self._send(self.fake, self.ops["authenticate"],
                   _wl_string("polyglotic-570") + _wl_string("checks"))  # fmt: skip
        self._roundtrip()

    def _opcodes(self) -> dict[str, int]:
        if self.XML.exists():
            interface = ET.parse(self.XML).getroot().find("interface")
            if interface is not None:
                return {
                    r.get("name", ""): i
                    for i, r in enumerate(interface.findall("request"))
                }
        return dict(FAKE_INPUT_OPS)

    def _new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _send(self, obj: int, op: int, body: bytes) -> None:
        self.sock.sendall(struct.pack("<II", obj, ((8 + len(body)) << 16) | op) + body)

    def _roundtrip(self) -> list[tuple[int, int, bytes]]:
        done = self._new_id()
        self._send(1, 0, struct.pack("<I", done))  # wl_display.sync
        events: list[tuple[int, int, bytes]] = []
        self.sock.settimeout(10)
        while True:
            while len(self.buf) < 8:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise RuntimeError("the compositor closed the connection")
                self.buf += chunk
            obj, word = struct.unpack_from("<II", self.buf)
            size, op = word >> 16, word & 0xFFFF
            while len(self.buf) < size:
                self.buf += self.sock.recv(65536)
            body, self.buf = self.buf[8:size], self.buf[size:]
            if obj == 1 and op == 0:
                raise RuntimeError(f"wayland error: {body!r}")
            if obj == done and op == 0:
                return events
            events.append((obj, op, body))

    def key(self, code: int, down: bool) -> None:
        self._send(
            self.fake, self.ops["keyboard_key"], struct.pack("<II", code, int(down))
        )
        self._roundtrip()

    def move(self, x: float, y: float) -> None:
        fixed = struct.pack("<ii", round(x * 256), round(y * 256))
        self._send(self.fake, self.ops["pointer_motion_absolute"], fixed)
        self._roundtrip()

    def button(self, down: bool) -> None:
        self._send(
            self.fake, self.ops["button"], struct.pack("<II", BTN_LEFT, int(down))
        )
        self._roundtrip()


class XTestInput(Input):
    """XTest on the X server `DISPLAY` names: X key codes are the kernel's
    plus 8."""

    def __init__(self) -> None:
        self.x11 = ctypes.CDLL("libX11.so.6")
        self.xtst = ctypes.CDLL("libXtst.so.6")
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong,
        ]  # fmt: skip
        self.xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong,
        ]  # fmt: skip
        self.xtst.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong,
        ]  # fmt: skip
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise OSError("XTest: no X server")

    def key(self, code: int, down: bool) -> None:
        self.xtst.XTestFakeKeyEvent(self.display, code + 8, int(down), 0)
        self.x11.XFlush(self.display)

    def move(self, x: float, y: float) -> None:
        self.xtst.XTestFakeMotionEvent(self.display, -1, round(x), round(y), 0)
        self.x11.XFlush(self.display)

    def button(self, down: bool) -> None:
        self.xtst.XTestFakeButtonEvent(self.display, 1, int(down), 0)
        self.x11.XFlush(self.display)
