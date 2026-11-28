"""Dictation in the running app (ui.dictation.Dictating, decision 0073):
the key's hold opens the mic, its pieces go to the session, the answers
are typed into the window they were meant for - with stand-ins for the
mic, the session, typing and the keyboard, nothing pressed or typed. And
what `main` adds: dictation's languages on the session, its answers kept
out of the caption feed; the sign's words; the settings read leniently."""

from collections.abc import Callable, Iterator

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.dictation import (
    ANSWER_WITHIN_SEC,
    DICTATION_SOURCE,
    TAIL_SEC,
    Said,
)
from polyglotic_desktop.core.listening.sources import DICTATION, MIC
from polyglotic_desktop.core.listening.timing import SpeechKind, TranscriptionRequest
from polyglotic_desktop.main import DictationKeyHeld, QtListener, listening_settings
from polyglotic_desktop.ports.capture import MicPiece
from polyglotic_desktop.ui.app import ConnectionState
from polyglotic_desktop.ui.dictation import Dictating
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next.dictation_sign import (
    LONGER_SAID_MS,
    SAID_MS,
    DictationSign,
    said_text,
)

WINDOW, OTHER_WINDOW = 0x100, 0x200


class StandInMic:
    def __init__(self) -> None:
        self.on_piece: Callable[[MicPiece], None] | None = None
        self.hold = 0
        self.closed: float | None = None
        self.dropped = 0

    def open(self, hold: int, on_piece: Callable[[MicPiece], None]) -> None:
        self.hold, self.on_piece, self.closed = hold, on_piece, None

    def close(self, tail: float) -> None:
        self.closed = tail

    def drop(self) -> None:
        self.dropped += 1

    def level(self) -> float:
        return 0.4

    def last_piece(
        self, start: float, end: float, speech: bytes | None = b"ogg"
    ) -> None:
        assert self.on_piece is not None
        self.on_piece(MicPiece(self.hold, start, end, speech, True))


class Rig:
    """`Dictating` on stand-ins, its clock set by hand."""

    def __init__(self, signed_in: bool = True, **settings: object) -> None:
        self.settings = Settings(MemorySettingsStore({"dictation": True, **settings}))
        self.mic = StandInMic()
        self.sent: list[tuple[TranscriptionRequest, bytes]] = []
        self.typed: list[str] = []
        self.types = True
        self.window = WINDOW
        self.esc = False
        self.allowed = True
        self.sessions: list[bool] = []
        self.signed_in = signed_in
        self.now = 100.0
        self.signs: list[str] = []
        self.mic_held: list[tuple[bool, float]] = []
        self.forgotten = 0
        self.dictating = Dictating(
            self.settings,
            self.mic,
            lambda request, speech: self.sent.append((request, speech)),
            self._type,
            lambda: self.window,
            lambda name: name == "escape" and self.esc,
            self._session,
            clock=lambda: self.now,
            mic_held=lambda held, tail: self.mic_held.append((held, tail)),
            forget_unsent=self._forget,
            typing_allowed=lambda: self.allowed,
        )
        self.dictating.sign_changed.connect(
            lambda state, _level: self.signs.append(state)
        )

    def _forget(self) -> None:
        self.forgotten += 1

    def _type(self, text: str) -> bool:
        if self.types:
            self.typed.append(text)
        return self.types

    def _session(self, wanted: bool) -> bool:
        self.sessions.append(wanted)
        return self.signed_in

    def hold(self, seconds: float) -> None:
        self.dictating.key_down()
        self.now += seconds
        self.dictating.key_up()

    def answer(
        self,
        *originals: str,
        kind: CaptionKind = CaptionKind.FINISHED,
        language: str = "en",
    ) -> None:
        request, _ = self.sent[-1]
        self.dictating.answered(
            CaptionUpdate(
                request.caption_id,
                DICTATION,
                kind,
                tuple(Clause(o) for o in originals),
                language=Language(language),
                processing_ms=70,
            )
        )

    def close(self) -> None:
        self.dictating.stop()
        shiboken6.delete(self.dictating)
        shiboken6.delete(self.settings)


@pytest.fixture
def rig(qapp: QApplication) -> Iterator[Rig]:
    made = Rig()
    yield made
    made.close()


def test_a_hold_is_sent_when_let_go_and_typed_when_answered(rig: Rig) -> None:
    rig.dictating.key_down()
    assert rig.sessions == [True]  # a listening session asked for at the press
    assert rig.mic.hold == 1
    assert rig.signs[-1] == "listening"
    rig.now += 2.0
    rig.dictating.key_up()
    assert rig.mic.closed == TAIL_SEC
    assert rig.signs[-1] == "working"
    rig.mic.last_piece(99.8, 102.2)
    [(request, speech)] = rig.sent
    assert request.source == DICTATION_SOURCE and request.kind is SpeechKind.FINISHED
    assert (request.speech_start, request.speech_end, speech) == (99.8, 102.2, b"ogg")
    rig.answer("Hello there.")
    assert rig.typed == ["Hello there. "]
    assert rig.signs[-1] == "typed"
    assert rig.dictating.session_wanted  # for a minute after
    rig.now += 61.0
    assert not rig.dictating.session_wanted


def test_off_the_key_does_nothing(qapp: QApplication) -> None:
    rig = Rig(dictation=False)
    try:
        rig.hold(2.0)
        assert rig.mic.hold == 0 and rig.sessions == [] and rig.signs == []
    finally:
        rig.close()


def test_signed_out_it_says_so_and_opens_no_mic(qapp: QApplication) -> None:
    rig = Rig(signed_in=False)
    try:
        rig.hold(2.0)
        assert rig.mic.hold == 0
        assert rig.signs[-1] == Said.SIGN_IN.value
    finally:
        rig.close()


def test_a_stray_tap_drops_the_mic(rig: Rig) -> None:
    rig.hold(0.1)
    assert rig.mic.dropped == 1 and rig.mic.closed is None
    assert rig.signs[-1] == Said.TOO_SHORT.value


def test_mic_use_is_reported_for_the_hold_and_the_tail(rig: Rig) -> None:
    """The hold reports its microphone use for selection reading.
    at once again for a hold dropped, a tap, Esc or a shortcut."""
    rig.dictating.key_down()
    assert rig.mic_held == [(True, 0.0)]
    rig.now += 2.0
    rig.dictating.key_up()
    assert rig.mic_held[-1] == (False, TAIL_SEC)  # as the mic closes
    rig.hold(0.1)  # a stray tap
    assert rig.mic_held[-2:] == [(True, 0.0), (False, 0.0)]
    rig.dictating.key_down()
    rig.esc = True
    rig.dictating._read_esc()
    assert rig.mic_held[-2:] == [(True, 0.0), (False, 0.0)]
    rig.esc = False
    rig.dictating.key_down()
    rig.dictating.key_other()  # Right Ctrl + C
    assert rig.mic_held[-2:] == [(True, 0.0), (False, 0.0)]
    rig.dictating.key_up()
    rig.dictating.key_down()
    rig.dictating.stop()  # turned off with the key down
    assert rig.mic_held[-1] == (False, 0.0)


def test_the_server_out_of_reach_is_said_at_once_not_after_10_s(rig: Rig) -> None:
    """QA batch 6 (D10): with the server down the sign said "Working..."
    for 10 s. Now the session's state says no answer can come, and the
    sign says so at once; what waited to be sent is dropped (299)."""
    rig.dictating.connection_changed(ConnectionState.CONNECTING)  # the press's
    rig.hold(1.5)
    rig.mic.last_piece(0.0, 1.7)
    assert rig.signs[-1] == "working" and len(rig.sent) == 1
    rig.dictating.connection_changed(ConnectionState.WAITING)  # refused at once
    assert rig.signs[-1] == Said.NO_SERVER.value
    assert rig.forgotten == 1
    rig.answer("Too late.")  # if one came after all: ignored
    assert rig.typed == []
    # and a press while it's out of reach opens no mic and says so
    held = rig.mic.hold
    rig.dictating.key_down()
    assert rig.mic.hold == held and rig.signs[-1] == Said.NO_SERVER.value
    rig.dictating.key_up()
    # back: dictation works again
    rig.dictating.connection_changed(ConnectionState.LISTENING)
    rig.dictating.key_down()
    assert rig.mic.hold == held + 1 and rig.signs[-1] == "listening"


def test_a_hold_under_way_is_dropped_when_the_server_cant_be_reached(
    rig: Rig,
) -> None:
    rig.dictating.key_down()
    rig.dictating.connection_changed(ConnectionState.WAITING)
    assert rig.mic.dropped == 1 and rig.mic_held[-1] == (False, 0.0)
    assert rig.signs[-1] == Said.NO_SERVER.value
    rig.dictating.key_up()  # nothing sent when the key comes up
    assert rig.sent == []


def test_signed_out_by_the_server_says_sign_in(rig: Rig) -> None:
    rig.dictating.key_down()
    rig.dictating.connection_changed(ConnectionState.SIGN_IN_NEEDED)
    assert rig.signs[-1] == Said.SIGN_IN.value


def test_connecting_and_listening_are_waited_for(rig: Rig) -> None:
    for state in (ConnectionState.CONNECTING, ConnectionState.LISTENING):
        rig.dictating.connection_changed(state)
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.dictating.connection_changed(ConnectionState.LISTENING)
    assert rig.signs[-1] == "working" and rig.forgotten == 0


def test_text_goes_only_to_the_window_it_was_meant_for(rig: Rig) -> None:
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.window = OTHER_WINDOW  # the learner clicked elsewhere meanwhile
    rig.answer("Not here.")
    assert rig.typed == []
    assert rig.signs[-1] == Said.WINDOW_CHANGED.value


def test_typing_refused_is_said(rig: Rig) -> None:
    rig.types = False
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.answer("Refused.")
    assert rig.signs[-1] == Said.NOT_TYPED.value


def test_typing_the_os_hasnt_allowed_says_so(rig: Rig) -> None:
    """A Mac without the Accessibility permission (polyglotic-hq 438): the
    sign says it isn't allowed, not that it couldn't type there - and it
    stays up longer, as something to do."""
    rig.types, rig.allowed = False, False
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.answer("Refused.")
    assert rig.signs[-1] == Said.NOT_ALLOWED.value
    assert "Settings > Dictation" in said_text(Said.NOT_ALLOWED.value)


def test_the_sign_keeps_not_allowed_up_longer(qapp: QApplication) -> None:
    sign = DictationSign()
    try:
        sign.show_state(Said.NOT_ALLOWED.value)
        assert sign.isVisible()
        assert sign._hide_later.interval() == LONGER_SAID_MS > SAID_MS
        sign.show_state(Said.NOTHING_HEARD.value)
        assert sign._hide_later.interval() == SAID_MS
    finally:
        shiboken6.delete(sign)


def test_esc_cancels_and_the_late_answer_is_ignored(rig: Rig) -> None:
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.esc = True
    rig.dictating._read_esc()  # the timer's read
    assert rig.signs[-1] == Said.CANCELLED.value
    assert rig.mic.dropped == 1
    rig.answer("Too late.")
    assert rig.typed == []


def test_a_shortcut_with_the_key_drops_the_hold_quietly(rig: Rig) -> None:
    """Right Ctrl + C (polyglotic-hq 289): another key with a key held
    alone - the mic dropped, nothing sent, nothing said."""
    rig.dictating.key_down()
    assert rig.signs[-1] == "listening"
    rig.now += 0.4
    rig.dictating.key_other()
    assert rig.mic.dropped == 1 and rig.mic.closed is None
    assert rig.signs[-1] == "idle"
    rig.now += 0.5
    rig.dictating.key_up()  # Right Ctrl let go
    assert rig.sent == [] and rig.signs[-1] == "idle"
    rig.hold(1.0)  # the next hold is dictation again
    rig.mic.last_piece(0.0, 1.2)
    rig.answer("Again.")
    assert rig.typed == ["Again. "]


def test_a_shortcut_keeps_the_hold_before_coming(rig: Rig) -> None:
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.dictating.key_down()
    rig.dictating.key_other()  # the new hold was a shortcut
    rig.answer("First.")  # the one before still comes
    assert rig.typed == []  # ...once the key is up
    rig.dictating.key_up()
    assert rig.typed == ["First. "]


def test_text_is_never_typed_while_the_key_is_held(rig: Rig) -> None:
    """With Ctrl (or Alt, Win) part of the key, text typed while it's held
    would land with it down (polyglotic-hq 289): it waits for the key to
    come up."""
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.dictating.key_down()  # a second hold, while the first's on its way
    rig.answer("First.")
    assert rig.typed == []
    rig.now += 1.0
    rig.dictating.key_up()
    assert rig.typed == ["First. "]  # as the key came up
    rig.mic.last_piece(1.0, 2.2)
    rig.answer("Second.")
    assert rig.typed == ["First. ", "Second. "]


def test_esc_drops_text_waiting_for_the_key(rig: Rig) -> None:
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.dictating.key_down()
    rig.answer("First.")
    rig.esc = True
    rig.dictating._read_esc()
    rig.dictating.key_up()
    assert rig.typed == []


def test_a_piece_from_a_cancelled_hold_is_not_sent(rig: Rig) -> None:
    rig.hold(1.0)
    rig.esc = True
    rig.dictating._read_esc()  # before the mic's tail ended
    rig.mic.last_piece(0.0, 1.2)
    assert rig.sent == []


def test_nothing_heard_and_no_answer_are_said(rig: Rig) -> None:
    rig.hold(1.0)
    rig.mic.last_piece(0.0, 1.2)
    rig.answer(kind=CaptionKind.WITHDRAWN)
    assert rig.signs[-1] == Said.NOTHING_HEARD.value
    rig.hold(1.0)
    rig.mic.last_piece(2.0, 3.2)
    rig.now += ANSWER_WITHIN_SEC + 1
    rig.dictating._check_overdue()  # the timer's check
    assert rig.signs[-1] == Said.NO_ANSWER.value
    assert rig.forgotten == 1  # what still waited to be sent: dropped (299)


def test_australian_spelling_follows_the_setting(qapp: QApplication) -> None:
    rig = Rig(dictation_australian=True)
    try:
        rig.hold(1.0)
        rig.mic.last_piece(0.0, 1.2)
        rig.answer("My favorite color.")
        assert rig.typed == ["My favourite colour. "]
    finally:
        rig.close()


def test_english_set_is_typed_as_english_whatever_the_label(qapp: QApplication) -> None:
    rig = Rig(dictation_language="en", dictation_australian=True)
    try:
        rig.hold(1.0)
        rig.mic.last_piece(0.0, 1.2)
        rig.answer("My favorite color.", language="zh")  # the server's label
        assert rig.typed == ["My favourite colour. "]
    finally:
        rig.close()


def test_every_language_the_speech_model_takes_is_offered_by_name(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
    from polyglotic_desktop.ui_next.languages import dictation_choices

    choices = dictation_choices(DICTATION_LANGUAGES, own=["ja"])
    assert choices[0] == ("ja", "Japanese")  # the learner's own first (293)
    names = dict(choices)
    assert names["zh"] == "Mandarin (Simplified characters)"  # says its script
    assert names["yue"] == "Cantonese (Hong Kong characters)"
    assert len(choices) == 30
    assert all(name != code for code, name in choices)  # each one named
    rest = [name for _, name in choices[1:]]
    assert rest == sorted(rest)  # then by name: nothing pinned (293)
    taiwan = dictation_choices(DICTATION_LANGUAGES, own=["zh-hant", "en"])
    assert [code for code, _ in taiwan[:2]] == ["zh", "en"]  # Mandarin, either script


# -- what main adds ------------------------------------------------------------------


def test_dictation_is_a_source_of_its_own_on_the_session_only_when_on() -> None:
    off = listening_settings(AppSettings(dictation=False))
    assert DICTATION not in off.source_targets
    assert DICTATION in listening_settings(AppSettings()).source_targets  # on: 478
    on = listening_settings(
        AppSettings(dictation=True, dictation_language="zh", spoken_language="en")
    )
    assert on.targets_of(DICTATION) == ()  # never translated
    assert on.spoken_language_of(DICTATION) == Language("zh")
    assert on.spoken_language == Language("en")  # the session's own, unchanged
    assert not on.original_only
    detect = listening_settings(AppSettings(dictation=True))
    assert DICTATION in detect.source_spoken
    assert detect.spoken_language_of(DICTATION) is None


def test_the_tray_names_the_key_on_dictations_line(qapp: QApplication) -> None:
    """polyglotic-hq 289: at the line's right, as a hotkey is shown."""
    desktop = make_app()
    try:
        desktop.show_dictation_key("Ctrl + Alt + D")
        assert desktop.dictation.text() == "Dictation (preview)\tCtrl + Alt + D"
        assert desktop.dictation.toolTip().startswith("Hold Ctrl + Alt + D and speak")
    finally:
        desktop.close()
        shiboken6.delete(desktop)


def test_dictations_answers_never_reach_the_caption_feed(qapp: QApplication) -> None:
    from polyglotic_desktop.core.listening.timing import CaptionId

    desktop = make_app()
    try:
        listener = QtListener(desktop, None)
        dictated: list[CaptionUpdate] = []
        listener.dictated = dictated.append
        yours = CaptionUpdate(
            CaptionId("a"), MIC, CaptionKind.FINISHED, (Clause("Hi"),)
        )
        typed = CaptionUpdate(
            CaptionId("b"), DICTATION, CaptionKind.FINISHED, (Clause("Hi"),)
        )
        listener.caption_updated(yours)
        listener.caption_updated(typed)
        qapp.processEvents()
        shown = [c.caption_id for c in desktop.feed.history.captions]
        assert shown == [CaptionId("a")]  # the dictation's never a caption
        assert dictated == [typed]
    finally:
        desktop.close()
        shiboken6.delete(desktop)


def test_dictation_settings_are_read_leniently() -> None:
    assert AppSettings().dictation is True  # on for a new learner (478; off in 283)
    assert AppSettings().dictation_key == "right_ctrl"  # polyglotic-hq 289
    for kept in ("insert", "ctrl+alt+d", "ctrl+win", "pause", "space"):
        assert AppSettings.from_stored({"dictation_key": kept}).dictation_key == kept
    read = AppSettings.from_stored(
        {
            "dictation": True,
            "dictation_key": "f9",
            "dictation_language": "yue",
            "dictation_australian": True,
        }
    )
    assert (read.dictation, read.dictation_key, read.dictation_language) == (
        True,
        "f9",
        "yue",
    )
    assert AppSettings.from_stored(read.to_stored()) == read
    bad = AppSettings.from_stored(
        {
            "dictation": "yes",
            "dictation_key": "unknown",
            "dictation_language": "Klingon",
        }
    )
    assert (bad.dictation, bad.dictation_key, bad.dictation_language) == (
        True,  # the default (478)
        "right_ctrl",
        None,
    )
    assert AppSettings.from_stored({"dictation_key": 7}).dictation_key == "right_ctrl"


# -- the sign ------------------------------------------------------------------------


def test_the_sign_says_listening_working_and_why_nothing_was_typed(
    qapp: QApplication,
) -> None:
    sign = DictationSign()
    try:
        sign.show_state("listening", 0.5)
        assert sign.isVisible() and sign.text == "Listening" and sign.listening
        sign.show_state("working")
        assert sign.text == "Working…" and not sign.listening
        sign.show_state(Said.NOTHING_HEARD.value)
        assert sign.isVisible() and sign.text == "Didn't catch that"
        sign.show_state(Said.TYPED.value)  # typed: nothing to say
        assert not sign.isVisible()
        for said in Said:
            if said not in (Said.TYPED, Said.OWN_WINDOW, Said.COPIED):
                assert said_text(said.value), said
    finally:
        shiboken6.delete(sign)


def test_the_sign_names_the_key_and_says_it_when_dictation_is_turned_on(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 289: "Hold Right Ctrl..." - the key chosen, in words."""
    assert said_text(Said.TOO_SHORT.value) == "Hold the key while you speak"
    assert (
        said_text(Said.TOO_SHORT.value, "Ctrl + Alt + D")
        == "Hold Ctrl + Alt + D while you speak"
    )
    sign = DictationSign()
    try:
        sign.show_hint()  # no key named yet: nothing
        assert not sign.isVisible()
        sign.key = "Right Ctrl"
        sign.show_hint()
        assert sign.isVisible() and sign.text == "Hold Right Ctrl and speak"
        assert not sign.listening
        sign.show_state(Said.TOO_SHORT.value)
        assert sign.text == "Hold Right Ctrl while you speak"
        sign.show_state("listening", 0.2)
        sign.show_hint()  # never over a hold
        assert sign.text == "Listening"
    finally:
        shiboken6.delete(sign)


# -- the key taken from the OS (main.DictationKeyHeld; polyglotic-hq 289) ------------


class StandInKey:
    """The OS's key: started, stopped, and whether another program has it."""

    def __init__(self, key: str, taken_by_others: set[str], log: list[str]) -> None:
        self.key, self._others, self._log = key, taken_by_others, log

    def start(self) -> bool:
        self._log.append(f"take {self.key}")
        return self.key not in self._others

    def stop(self) -> None:
        self._log.append(f"let go {self.key}")


def test_the_key_is_taken_while_on_and_let_go_while_settings_listens() -> None:
    log: list[str] = []
    held = DictationKeyHeld(lambda key: StandInKey(key, set(), log))
    assert not held.follow(False, "right_ctrl") and log == []  # off: nothing
    assert held.follow(True, "right_ctrl")
    assert log == ["take right_ctrl"] and held.held_as == "right_ctrl"
    assert not held.follow(True, "right_ctrl")  # unchanged: not taken again
    held.box_listening = True
    assert held.follow(True, "right_ctrl")
    assert log[-1] == "let go right_ctrl" and held.held_as is None
    held.box_listening = False
    held.follow(True, "right_ctrl")
    assert log[-1] == "take right_ctrl"
    held.stop()
    assert log[-1] == "let go right_ctrl"


def test_a_key_pressed_is_kept_only_if_no_other_program_has_it() -> None:
    log: list[str] = []
    held = DictationKeyHeld(lambda key: StandInKey(key, {"f9"}, log))
    held.follow(True, "right_ctrl")
    # free: held now, and the settings' change then takes nothing again
    assert held.try_key("ctrl+alt+d", on=True)
    assert log == ["take right_ctrl", "let go right_ctrl", "take ctrl+alt+d"]
    assert not held.follow(True, "ctrl+alt+d")
    # another program has it: let go, and the key before taken again
    assert not held.try_key("f9", on=True)
    assert log[-3:] == ["let go ctrl+alt+d", "take f9", "let go f9"]
    assert held.follow(True, "ctrl+alt+d")
    assert log[-1] == "take ctrl+alt+d" and not held.taken
    # off: tried, then let go - nothing held
    assert held.try_key("ctrl+shift+f9", on=False)
    assert log[-2:] == ["take ctrl+shift+f9", "let go ctrl+shift+f9"]
    assert held.held_as is None


def test_a_key_another_program_took_since_is_said() -> None:
    log: list[str] = []
    held = DictationKeyHeld(lambda key: StandInKey(key, {"f9"}, log))
    held.follow(True, "f9")
    assert held.taken and held.held_as == "f9"
