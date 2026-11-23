"""Exercise Windows' UTF-16 adapter in a textbox on a private desktop.

The send callback delivers the events inside Qt, without injecting
desktop input. The server reply and audio are fixtures.
"""

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from tests.ui.fakes import MemorySettingsStore
from tests.ui.test_dictating import StandInMic

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.dictation import Dictation
from polyglotic_desktop.core.listening.sources import TYPE_THEIRS
from polyglotic_desktop.core.listening.timing import TranscriptionRequest
from polyglotic_desktop.core.listening.type_theirs import THEIRS_SOURCE, theirs_text
from polyglotic_desktop.platform.windows.text_input import (
    INPUT,
    KEYEVENTF_KEYUP,
    type_text,
    window_is_ours,
)
from polyglotic_desktop.ui.dictation import Dictating
from polyglotic_desktop.ui.settings import Settings


def check(shot: Path | None) -> None:
    app = QApplication([])
    edit = QPlainTextEdit()
    edit.setWindowTitle("Type what they said · private-desktop test")
    edit.resize(560, 160)
    edit.show()
    app.setActiveWindow(edit)
    edit.setFocus()
    app.processEvents()
    assert app.focusWidget() is edit
    handle = int(edit.winId())
    assert window_is_ours(handle)

    def send(count: int, events: "ctypes.Array[INPUT]", _size: int) -> int:
        focused = app.focusWidget()
        assert focused is edit
        units = b"".join(
            event.u.ki.wScan.to_bytes(2, "little")
            for event in events
            if not event.u.ki.dwFlags & KEYEVENTF_KEYUP
        )
        QApplication.sendEvent(
            focused,
            QKeyEvent(
                QEvent.Type.KeyPress,
                0,
                Qt.KeyboardModifier.NoModifier,
                units.decode("utf-16-le"),
            ),
        )
        return count

    requests: list[TranscriptionRequest] = []
    mic = StandInMic()
    now = 100.0
    settings = Settings(MemorySettingsStore())
    own = True
    typing = Dictating(
        settings,
        mic,
        lambda request, _audio: requests.append(request),
        lambda text: type_text(text, send=send),
        lambda: handle if app.focusWidget() is edit else 0,
        lambda _key: False,
        lambda _wanted: True,
        clock=lambda: now,
        holds=Dictation(source=THEIRS_SOURCE, text_of=lambda u: theirs_text(u, None)),
        from_speakers=True,
        window_is_ours=lambda hwnd: own and window_is_ours(hwnd),
    )
    try:
        typing.key_down()
        now += 2
        typing.key_up()
        assert not requests and not edit.toPlainText()

        own = False  # treat the test widget as the other app for this delivery
        typing.key_down()
        now += 2
        typing.key_up()
        mic.last_piece(102.0, 104.0)
        [request] = requests
        typing.answered(
            CaptionUpdate(
                request.caption_id,
                TYPE_THEIRS,
                CaptionKind.FINISHED,
                (Clause("Good morning. Café déjà vu."),),
            )
        )
        app.processEvents()
        assert edit.toPlainText() == "Good morning. Café déjà vu. "
        if shot is not None:
            assert edit.grab().save(str(shot))
    finally:
        typing.stop()
        edit.close()


if __name__ == "__main__":
    check(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
