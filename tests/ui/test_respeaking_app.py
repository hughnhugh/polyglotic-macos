"""Re-speaking in the running app (ui.respeaking, decision 0274;
polyglotic-hq 567): the key's hold opens the mic, its pieces go to the
session as the other source's captions, which come back to the feed
marked re-spoken; one key for both, a tap then a hold; the sign's words;
and Settings > Dictation's controls. Stand-ins for the mic, the session and
the key: nothing is pressed, heard or sent."""

from collections.abc import Callable, Iterator

import pytest
import shiboken6
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.dictation import TAIL_SEC
from polyglotic_desktop.core.listening.respeaking import TAP_GAP_SEC
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.main import QtListener
from polyglotic_desktop.ports.capture import MicPiece, SourceCategory
from polyglotic_desktop.ui.app import ConnectionState
from polyglotic_desktop.ui.respeaking import Respeaking, SharedKey
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next.dictation_sign import DictationSign, respeaking_said
from polyglotic_desktop.ui_next.hotkeys_card import DictationForOthersCard
from polyglotic_desktop.ui_next.os_words import pc_or_mac

CALL = Source(SourceId("app-1"), SourceCategory.CALL)


def test_a_look_choice_is_recorded_even_when_reading_lines_follow_the_default() -> None:
    settings = Settings(MemorySettingsStore({}))
    settings.update(opacity=0.95, changed=settings.value.changed)

    restarted = AppSettings.from_stored(settings.value.to_stored())

    assert "opacity" in settings.value.changed
    assert restarted.opacity == 0.95


def test_the_last_own_respeak_key_survives_sharing_and_a_restart() -> None:
    chosen = AppSettings(
        respeak_key="", last_respeak_key="f9", changed=("respeak_key",)
    )

    restarted = AppSettings.from_stored(chosen.to_stored())

    assert restarted.respeak_key == "" and restarted.last_respeak_key == "f9"


class StandInMic:
    def __init__(self) -> None:
        self.on_piece: Callable[[MicPiece], None] | None = None
        self.hold = 0
        self.opened = 0
        self.closed: float | None = None
        self.dropped = 0

    def open(self, hold: int, on_piece: Callable[[MicPiece], None]) -> None:
        self.hold, self.on_piece, self.closed = hold, on_piece, None
        self.opened += 1

    def close(self, tail: float) -> None:
        self.closed = tail

    def drop(self) -> None:
        self.dropped += 1

    def level(self) -> float:
        return 0.4

    def last_piece(self, start: float, end: float) -> None:
        assert self.on_piece is not None
        self.on_piece(MicPiece(self.hold, start, end, b"ogg", True))


class Rig:
    def __init__(self, whose: tuple[Source, str] | None = (CALL, "Discord")) -> None:
        self.settings = Settings(MemorySettingsStore({"legacy_respeaking": True}))
        self.mic = StandInMic()
        self.sent: list[tuple[TranscriptionRequest, bytes]] = []
        self.now = 100.0
        self.esc = False
        self.whose = whose
        self.available = True
        self.signs: list[tuple[str, str]] = []
        self.mic_held: list[tuple[bool, float]] = []
        self.respeaking = Respeaking(
            self.settings,
            self.mic,
            lambda request, speech: self.sent.append((request, speech)),
            lambda: self.whose,
            lambda name: name == "escape" and self.esc,
            clock=lambda: self.now,
            mic_held=lambda held, tail: self.mic_held.append((held, tail)),
            available=lambda _source: self.available,
        )
        self.respeaking.sign_changed.connect(
            lambda state, _level, whose: self.signs.append((state, whose))
        )
        self.respeaking.connection_changed(ConnectionState.LISTENING)

    def hold(self, seconds: float) -> None:
        self.respeaking.key_down()
        QApplication.processEvents()
        self.now += seconds
        self.respeaking.key_up()
        QApplication.processEvents()


@pytest.fixture
def rig(qapp: QApplication) -> Iterator[Rig]:
    made = Rig()
    yield made
    made.respeaking.stop()
    shiboken6.delete(made.respeaking)


def test_a_hold_is_sent_as_theirs_and_its_caption_comes_back_marked(
    rig: Rig, qapp: QApplication
) -> None:
    rig.respeaking.key_down()
    qapp.processEvents()
    assert rig.mic.opened == 1 and rig.mic_held == [(True, 0.0)]
    assert rig.signs[-1] == ("listening", "Discord")
    rig.now += 2.0
    rig.respeaking.key_up()
    qapp.processEvents()
    assert rig.mic.closed == TAIL_SEC and rig.mic_held[-1] == (False, TAIL_SEC)
    assert rig.signs[-1] == ("working", "Discord")
    rig.mic.last_piece(100.0, 102.2)
    qapp.processEvents()
    ((request, speech),) = rig.sent
    assert request.source == CALL and request.kind is SpeechKind.FINISHED
    assert speech == b"ogg"
    assert rig.respeaking.is_respoken(request.caption_id)
    rig.respeaking.answered(
        CaptionUpdate(
            request.caption_id, CALL.id, CaptionKind.FINISHED, (Clause("明天见"),)
        )
    )
    qapp.processEvents()
    assert rig.signs[-1] == ("idle", "Discord")  # captioned: the caption shows


def test_with_nothing_else_captioned_the_mic_stays_closed(qapp: QApplication) -> None:
    rig = Rig(whose=None)
    try:
        rig.hold(2.0)
        assert rig.mic.opened == 0 and rig.sent == []
        assert rig.signs[-1][0] == "no_source"
    finally:
        shiboken6.delete(rig.respeaking)


def test_not_connected_it_says_so_at_the_press(rig: Rig, qapp: QApplication) -> None:
    rig.respeaking.connection_changed(ConnectionState.WAITING)
    rig.hold(2.0)
    assert rig.mic.opened == 0 and rig.signs[-1][0] == "no_server"


def test_off_the_key_does_nothing(rig: Rig, qapp: QApplication) -> None:
    rig.settings.update(legacy_respeaking=False)
    rig.hold(2.0)
    assert rig.mic.opened == 0 and rig.signs == []


def test_a_shortcut_with_it_drops_the_hold_quietly(
    rig: Rig, qapp: QApplication
) -> None:
    rig.respeaking.key_down()
    qapp.processEvents()
    rig.respeaking.key_other()
    rig.respeaking.key_up()
    qapp.processEvents()
    assert rig.mic.dropped == 1 and rig.sent == []
    assert rig.signs[-1][0] == "idle"


class Held:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name, self.calls = name, calls

    def key_down(self) -> None:
        self.calls.append(f"{self.name} down")

    def key_up(self) -> None:
        self.calls.append(f"{self.name} up")

    def key_other(self) -> None:
        self.calls.append(f"{self.name} other")


def test_one_key_for_both_a_tap_then_a_hold_re_speaks(qapp: QApplication) -> None:
    calls: list[str] = []
    now = [10.0]
    settings = Settings(MemorySettingsStore({"legacy_respeaking": True}))
    settings.update(respeak_key="")
    key = SharedKey(
        Held("dictate", calls), Held("respeak", calls), settings, lambda: now[0]
    )
    key.down()
    now[0] += 2.0
    key.up()
    assert calls == ["dictate down", "dictate up"]  # dictation, as before
    calls.clear()
    key.down()
    now[0] += 0.1
    key.up()  # a tap: dictation's hold dropped quietly
    now[0] += TAP_GAP_SEC / 2
    key.down()
    now[0] += 2.0
    key.up()
    assert calls == [
        "dictate down",
        "dictate other",
        "dictate up",
        "respeak down",
        "respeak up",
    ]
    calls.clear()
    settings.update(respeak_key="f9")  # its own key: this one only dictates
    key.down()
    now[0] += 0.1
    key.up()
    assert calls == ["dictate down", "dictate up"]  # a tap says it's too short


def test_the_listener_marks_re_spoken_captions_before_the_feed(
    qapp: QApplication,
) -> None:
    desktop = make_app()
    try:
        listener = QtListener(desktop, None)
        heard: list[CaptionId] = []
        listener.respoken = lambda caption_id: caption_id == CaptionId("r1")
        listener.heard = lambda update: heard.append(update.caption_id)
        for caption_id in ("r1", "theirs"):
            listener.caption_updated(
                CaptionUpdate(
                    CaptionId(caption_id),
                    CALL.id,
                    CaptionKind.FINISHED,
                    (Clause("明天见"),),
                )
            )
        qapp.processEvents()
        marked = {c.caption_id: c.respoken for c in desktop.feed.history.captions}
        assert marked == {CaptionId("r1"): True, CaptionId("theirs"): False}
        assert heard == [CaptionId("r1"), CaptionId("theirs")]
    finally:
        desktop.close()


def test_the_sign_says_whose_and_why_not(qapp: QApplication) -> None:
    sign = DictationSign()
    try:
        sign.show_respeaking("listening", 0.3, "Discord")
        assert (
            sign.text == "Re-speaking for Discord - let go to caption"
            and sign.listening
        )
        sign.show_respeaking("no_source")
        assert sign.text == "Nothing else is being captioned to re-speak for"
        sign.show_respeaking("idle")
        assert not sign.isVisible()
        assert respeaking_said("respoken") == ""
        assert respeaking_said("no_server") == "Not connected to the server"
    finally:
        sign.close()
        shiboken6.delete(sign)


def test_held_sign_fits_beside_its_window_without_taking_input(
    qapp: QApplication,
) -> None:
    anchor, sign = QWidget(), DictationSign()
    try:
        area = anchor.screen().availableGeometry()
        anchor.setGeometry(
            area.left(), area.top(), area.width() // 2, area.height() // 3
        )
        anchor.show()
        sign.show_respeaking("listening", 0.5, "Long source name " * 80, anchor)
        assert (
            sign.geometry().top()
            > anchor.mapToGlobal(QPoint(0, anchor.height() - 1)).y()
        )
        assert area.contains(sign.geometry())
        assert sign.accessibleName() == sign.text
        assert sign.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert sign.windowFlags() & Qt.WindowType.WindowTransparentForInput
    finally:
        sign.close()
        anchor.close()
        shiboken6.delete(sign)
        shiboken6.delete(anchor)


def test_own_key_default_migrates_only_unmodified_shared_bindings() -> None:
    assert AppSettings().type_theirs and AppSettings().respeak_key == "f8"
    assert not AppSettings().legacy_respeaking
    assert AppSettings.from_stored({"respeak_key": ""}).respeak_key == "f8"
    assert (
        AppSettings.from_stored(
            {"respeak_key": "", "changed": ["respeak_key"]}
        ).respeak_key
        == ""
    )
    assert AppSettings.from_stored({"hotkeys": {"copy": "f8"}}).respeak_key == ""
    assert AppSettings.from_stored({"dictation_key": "f8"}).respeak_key == ""
    assert AppSettings.from_stored({"respeak_key": "f9"}).respeak_key == "f9"
    assert AppSettings.from_stored({"respeak_key": "a"}).respeak_key == "f8"


def test_dictation_for_others_turns_it_off_and_gives_it_its_own_key(
    qapp: QApplication,
) -> None:
    card = DictationForOthersCard()
    try:
        changes: list[dict[str, object]] = []
        wanted: list[str] = []
        card.respeak_changes.connect(changes.append)
        card.respeak_key_wanted.connect(wanted.append)
        card.show_dictation(True, "right_ctrl")
        card.show_respeaking(True, "")
        assert card.respeak_how.text() == pc_or_mac(
            "Tap Right Ctrl, then hold it while they speak. Held without a tap, it dictates.",
            "Tap Right ⌘, then hold it while they speak. Held without a tap, it dictates.",
        )
        card.respeak.switch.click()
        assert changes == [{"type_theirs": False}]
        card.respeak_way.choose("own")
        assert card.respeak_box.listening  # press its key now
        card.respeak_box.stop()
        card._pressed("right_ctrl")  # dictation's
        assert card.respeak_note.text() == (
            "Dictate has that key: clear it there, or choose another."
        )
        card.hotkeys = {"lock": None}
        card._pressed("ctrl+c")
        assert card.respeak_note.text().startswith(
            pc_or_mac("Every program uses that one", "Every app uses that one")
        )
        card._pressed("insert")
        assert wanted == ["insert"]
        card.show_respeaking(True, "insert")
        assert card.respeak_way.value() == "own" and card.respeak_box.text() == "Insert"
        card.respeak_way.choose("shared")
        assert changes[-1] == {"respeak_key": ""}
        card.show_respeaking(True, "")  # the settings update comes back to the card
        stored = AppSettings(
            respeak_key="", last_respeak_key="insert", changed=("respeak_key",)
        ).to_stored()
        restarted = AppSettings.from_stored(stored)
        card.show_respeaking(
            True, restarted.respeak_key, last_own=restarted.last_respeak_key
        )
        card.respeak_way.choose("own")
        assert wanted[-1] == "insert"  # its learner-chosen key survives the restart
        card.not_taken("insert")
        assert card.respeak_box.listening  # another app has it: listen for a new key
    finally:
        shiboken6.delete(card)


def test_the_key_pins_the_watched_source_for_the_entire_hold(rig: Rig) -> None:
    system = Source(SourceId("system"), SourceCategory.SYSTEM)
    rig.whose = (system, "Everything the PC plays")
    rig.respeaking.key_down()
    rig.whose = (CALL, "Discord")
    rig.now += 2.0
    rig.respeaking.key_up()
    rig.mic.last_piece(100.0, 102.0)
    ((request, _speech),) = rig.sent
    assert request.source == system


def test_repeated_key_down_while_held_stays_steady_and_captions_once(
    rig: Rig, qapp: QApplication
) -> None:
    """Repeated key-down events during a single hold keep the sign steady and send one caption."""
    rig.respeaking.key_down()
    qapp.processEvents()
    for _ in range(4):
        rig.now += 0.2
        rig.respeaking.key_down()
        qapp.processEvents()
    assert rig.mic.opened == 1
    assert rig.signs == [("listening", "Discord")]
    rig.now += 1.0
    rig.respeaking.key_up()
    qapp.processEvents()
    assert rig.signs[-1] == ("working", "Discord")
    rig.mic.last_piece(100.0, 102.0)
    qapp.processEvents()
    assert len(rig.sent) == 1


def test_stale_escape_before_hold_does_not_cancel(qapp: QApplication) -> None:
    """A stale Escape press recorded before F8 went down is cleared on key-down."""
    reads = iter([True, False, False])
    settings = Settings(MemorySettingsStore({"legacy_respeaking": True}))
    mic = StandInMic()
    sent: list[tuple[TranscriptionRequest, bytes]] = []
    respeaking = Respeaking(
        settings,
        mic,
        lambda request, speech: sent.append((request, speech)),
        lambda: (CALL, "Discord"),
        lambda name: name == "escape" and next(reads, False),
        clock=lambda: 100.0,
    )
    try:
        respeaking.connection_changed(ConnectionState.LISTENING)
        respeaking.key_down()
        qapp.processEvents()
        respeaking._esc.timeout.emit()
        assert mic.opened == 1 and mic.dropped == 0
    finally:
        respeaking.stop()
        shiboken6.delete(respeaking)


def test_untouched_re_speaking_moves_to_on_but_explicit_off_stays() -> None:
    stored = {"respeaking": False, "changed": []}
    assert Settings(MemorySettingsStore(stored)).value.type_theirs
    stored["changed"] = ["respeaking"]
    assert not Settings(MemorySettingsStore(stored)).value.type_theirs
    assert not AppSettings.from_stored({"respeaking": False}).type_theirs
    assert not AppSettings.from_stored({"respeaking": True}).legacy_respeaking


def test_a_shortcut_does_not_prime_the_shared_key(qapp: QApplication) -> None:
    calls: list[str] = []
    now = [10.0]
    key = SharedKey(
        Held("dictate", calls),
        Held("respeak", calls),
        Settings(MemorySettingsStore({"respeak_key": "", "changed": ["respeak_key"]})),
        lambda: now[0],
    )
    key.down()
    key.other()
    now[0] += 0.1
    key.up()
    now[0] += 0.1
    key.down()
    assert calls == ["dictate down", "dictate other", "dictate up", "dictate down"]


def test_a_source_closed_during_a_hold_receives_no_speech(rig: Rig) -> None:
    rig.respeaking.key_down()
    rig.now += 2.0
    rig.respeaking.key_up()
    rig.available = False
    rig.mic.last_piece(100.0, 102.0)
    assert rig.sent == [] and rig.signs[-1][0] == "no_source"
