r"""What a person sees on a Linux desktop, from GitHub's runner (polyglotic-hq
550): the window manager's own picture of its headless screen - GNOME's
(mutter's ScreenCast, one frame through PipeWire) or KDE's (KWin's
ScreenShot2) - with the app's windows over a full-screen window, as the
compositor drew them. Never a person's screen: only the virtual screen of
a session the job itself made (547's harness, `tools/linux_session.sh`).

    python -m tools.linux_desktop_pictures fullscreen          # the window beneath
    python -m tools.linux_desktop_pictures serve DIR gnome|kde # pictures on request

`fullscreen`: a stand-in for a full-screen video or game - a native
Wayland window (QT_QPA_PLATFORM=wayland), full screen and focused - until
it's ended.

`serve`: for each `DIR/<name>.want` the tour writes (`tools/app_tour.py`,
when POLYGLOTIC_DESK_PICTURES names DIR), the screen's picture as
`DIR/<name>.png`; a picture that can't be taken is `DIR/<name>.failed`
with why. Ends when `DIR/stop` appears.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCREENCAST = "org.gnome.Mutter.ScreenCast"
SCREENSHOT = "org.kde.KWin.ScreenShot2"


def runner_only() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith(
        "linux"
    ):
        sys.exit("550: this runs only on GitHub's Linux runners")


class Session:
    """The session bus, for the window manager's own picture calls."""

    def __init__(self) -> None:
        from jeepney.io.blocking import open_dbus_connection

        # KWin hands the picture back through a file descriptor
        self.bus = open_dbus_connection(bus="SESSION", enable_fds=True)

    def call(
        self,
        path: str,
        name: str,
        interface: str,
        method: str,
        signature: str | None = None,
        body: tuple[Any, ...] = (),
    ) -> tuple[Any, ...]:
        from jeepney import DBusAddress, new_method_call
        from jeepney.wrappers import unwrap_msg

        address = DBusAddress(path, bus_name=name, interface=interface)
        message = new_method_call(address, method, signature, body)
        return tuple(unwrap_msg(self.bus.send_and_get_reply(message, timeout=20)))

    def gnome(self, path: Path) -> None:
        """One frame of mutter's virtual monitor, through PipeWire."""
        from jeepney import MatchRule, message_bus
        from jeepney.wrappers import unwrap_msg

        here = "/org/gnome/Mutter/ScreenCast"
        (session,) = self.call(here, SCREENCAST, SCREENCAST, "CreateSession",
                               "a{sv}", ({},))  # fmt: skip
        try:
            (stream,) = self.call(
                session, SCREENCAST, f"{SCREENCAST}.Session", "RecordMonitor",
                "sa{sv}", ("", {"cursor-mode": ("u", 0)}),
            )  # fmt: skip
            rule = MatchRule(
                type="signal",
                interface=f"{SCREENCAST}.Stream",
                member="PipeWireStreamAdded",
                path=stream,
            )
            unwrap_msg(
                self.bus.send_and_get_reply(message_bus.AddMatch(rule), timeout=10)
            )
            with self.bus.filter(rule) as added:
                self.call(session, SCREENCAST, f"{SCREENCAST}.Session", "Start")
                node = int(self.bus.recv_until_filtered(added, timeout=15).body[0])
            subprocess.run(
                ["gst-launch-1.0", "-q", "-e", "pipewiresrc", f"path={node}",
                 "num-buffers=3", "!", "videoconvert", "!", "pngenc", "snapshot=true",
                 "!", "filesink", f"location={path}"],
                check=True, timeout=30, stdout=subprocess.DEVNULL,
            )  # fmt: skip
        finally:
            self.call(session, SCREENCAST, f"{SCREENCAST}.Session", "Stop")

    def kde(self, path: Path) -> None:
        """KWin's picture of its whole workspace (started with
        KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 by the session)."""
        from PySide6.QtGui import QImage

        read, write = os.pipe()
        try:
            (found,) = self.call(
                "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2", SCREENSHOT,
                "CaptureWorkspace", "a{sv}h", ({"include-cursor": ("b", False)}, write),
            )  # fmt: skip
        finally:
            os.close(write)
        data = b""
        try:
            while True:
                ready, _, _ = select.select([read], [], [], 10)
                if not ready:
                    raise TimeoutError("KWin stopped writing the picture")
                chunk = os.read(read, 1 << 20)
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(read)
        meta = {key: value[1] for key, value in found.items()}
        image = QImage(
            data,
            meta["width"],
            meta["height"],
            meta["stride"],
            QImage.Format(meta["format"]),
        )
        image.copy().save(str(path))


def serve(folder: Path, desktop: str) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    session = Session()
    take = session.gnome if desktop == "gnome" else session.kde
    while not (folder / "stop").exists():
        for want in sorted(folder.glob("*.want")):
            name = want.stem
            try:
                take(folder / f"{name}.png")
            except Exception as error:  # noqa: BLE001 - said in the folder
                (folder / f"{name}.failed").write_text(
                    f"{type(error).__name__}: {error}"
                )
            want.unlink(missing_ok=True)
        time.sleep(0.2)
    return 0


def fullscreen() -> int:
    """A full-screen Wayland window, focused: a video or a game beneath."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
    from PySide6.QtWidgets import QApplication, QWidget

    class Beneath(QWidget):
        def paintEvent(self, _event: object) -> None:
            painter = QPainter(self)
            ground = QLinearGradient(0, 0, 0, self.height())
            ground.setColorAt(0, QColor(28, 64, 110))
            ground.setColorAt(1, QColor(10, 18, 34))
            painter.fillRect(self.rect(), ground)
            painter.setPen(QColor(220, 230, 245))
            painter.setFont(QFont("Noto Sans", 28))
            painter.drawText(
                self.rect().adjusted(0, 80, 0, 0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "A full-screen video, focused (a Wayland app)",
            )
            painter.end()

    app = QApplication(sys.argv[:1])
    window = Beneath()
    window.setWindowTitle("A full-screen video")
    window.showFullScreen()
    window.activateWindow()
    print(f"fullscreen: {QApplication.platformName()} {window.width()}x{window.height()}",
          flush=True)  # fmt: skip
    return app.exec()


def main(argv: list[str]) -> int:
    runner_only()
    if argv[:1] == ["fullscreen"]:
        return fullscreen()
    if len(argv) == 3 and argv[0] == "serve" and argv[2] in ("gnome", "kde"):
        return serve(Path(argv[1]), argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
