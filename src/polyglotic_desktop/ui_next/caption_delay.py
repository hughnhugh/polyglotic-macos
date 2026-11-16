"""Each caption's delay, as the words on the line above it.

polyglotic-hq 271 (the user, 2026-11-10: "Make there a way to measure /
display how long each translation takes. Total MS from speech start/finish
to server processing"): with "Show each caption's delay" on (the tray; off
by default), a caption's label says how long after its speech started and
ended it showed, and how much of that was the server's -
"3.6 s from start · 1.3 s from end · server 0.41 s". For a caption still
being spoken, its latest live update's. The numbers are
`core.listening.delays`'; the caption log has the same ones.
"""

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.delays import CaptionDelay


def _tr(text: str) -> str:
    return QApplication.translate("CaptionDelay", text)


def delay_text(took: CaptionDelay) -> str:
    """`took` in the interface's language and number format."""
    locale = QLocale()
    said = _tr("{start} s from start · {end} s from end").format(
        start=locale.toString(max(took.from_start, 0.0), "f", 1),
        end=locale.toString(max(took.from_end, 0.0), "f", 1),
    )
    if took.server is None:
        return said
    server = _tr("server {seconds} s").format(
        seconds=locale.toString(took.server, "f", 2)
    )
    return f"{said} · {server}"
