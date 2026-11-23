"""The speaker hold from key press through a finished caption and typing."""

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app
from tests.ui.test_dictating import OTHER_WINDOW, WINDOW, StandInMic

from polyglotic_desktop.core.listening.caption_hold import CaptionResults
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.dictation import Dictation, Said
from polyglotic_desktop.core.listening.sources import (
    MIC,
    TYPE_THEIRS,
    WHOLE_SYSTEM,
    Source,
    SourceId,
)
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.core.listening.type_theirs import (
    THEIRS_SOURCE,
    TypeWhat,
    shown_text,
    theirs_text,
)
from polyglotic_desktop.main import QtListener, listening_settings, typed_target
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ui.dictation import Dictating, HeldCaptions
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next.dictation_sign import DictationSign
from polyglotic_desktop.ui_next.os_words import pc_or_mac

SPANISH = Language("es")


def test_speaker_source_detects_language_and_translates_only_when_requested() -> None:
    original = AppSettings(targets=("es", "it"), spoken_language="ja")
    settings = listening_settings(original)
    assert settings.targets_of(TYPE_THEIRS) == ()
    assert settings.spoken_language_of(TYPE_THEIRS) is None
    assert not settings.original_only
    settings = listening_settings(
        AppSettings(targets=("es", "it"), type_what=TypeWhat.TRANSLATION)
    )
    assert settings.targets_of(TYPE_THEIRS) == (SPANISH,)


@pytest.mark.parametrize(
    ("what", "at_release", "at_answer", "audio", "expected", "reported"),
    [
        (TypeWhat.ORIGINAL, WINDOW, WINDOW, "speech", "Good morning. ", Said.TYPED),
        (TypeWhat.TRANSLATION, WINDOW, WINDOW, "speech", "Buenos días. ", Said.TYPED),
        (TypeWhat.ORIGINAL, OTHER_WINDOW, OTHER_WINDOW, "speech", "", Said.OWN_WINDOW),
        (TypeWhat.ORIGINAL, WINDOW, OTHER_WINDOW, "speech", "", Said.OWN_WINDOW),
        (TypeWhat.ORIGINAL, WINDOW, WINDOW, "silent", "", Said.NOTHING_HEARD),
        (TypeWhat.ORIGINAL, WINDOW, WINDOW, "withdrawn", "", Said.NOTHING_HEARD),
        (TypeWhat.ORIGINAL, 0, 0, "speech", "Good morning. ", Said.COPIED),
    ],
)
def test_speaker_hold(
    qapp: QApplication,
    what: TypeWhat,
    at_release: int,
    at_answer: int,
    audio: str,
    expected: str,
    reported: Said,
) -> None:
    settings = Settings(MemorySettingsStore({"type_what": what, "targets": ["es"]}))
    capture = StandInMic()
    requests: list[TranscriptionRequest] = []
    typed: list[str] = []
    copied: list[str] = []
    now = 100.0
    window = WINDOW
    sessions: list[bool] = []
    desktop = make_app()
    listener = QtListener(desktop, None)
    shown = DictationSign()
    sign: list[str] = []

    def type_text(text: str) -> bool:
        typed.append(text)
        return True

    def session(wanted: bool) -> bool:
        sessions.append(wanted)
        return True

    dictating = Dictating(
        settings,
        capture,
        lambda request, _speech: requests.append(request),
        type_text,
        lambda: window,
        lambda _key: False,
        session,
        clock=lambda: now,
        holds=Dictation(
            source=THEIRS_SOURCE,
            text_of=lambda u: theirs_text(u, typed_target(settings.value)),
        ),
        from_speakers=True,
        window_is_ours=lambda handle: handle == OTHER_WINDOW,
        copy_text=copied.append if reported is Said.COPIED else None,
    )
    listener.typed_theirs = dictating.answered
    received: list[CaptionUpdate] = []
    desktop.feed.received.connect(received.append)

    def show(state: str, level: float) -> None:
        sign.append(state)
        shown.show_state(state, level, speakers=True)

    dictating.sign_changed.connect(show)
    try:
        dictating.key_down()
        assert shown.text == pc_or_mac(
            "Listening to the PC - let go to type it",
            "Listening to the Mac - let go to type it",
        )
        assert shown.level == 0.4
        dictating.key_down()  # key repeat neither reopens nor renews a hold
        assert sessions == [True] and capture.hold == 1
        assert not requests and not typed
        now += 2
        window = at_release
        dictating.key_up()
        if at_release != OTHER_WINDOW:
            assert capture.closed == 0
            capture.last_piece(100, 102, speech=None if audio == "silent" else b"ogg")
        if requests:
            [request] = requests
            assert (
                request.kind is SpeechKind.FINISHED and request.source == THEIRS_SOURCE
            )
            window = at_answer
            listener.caption_updated(
                CaptionUpdate(
                    request.caption_id,
                    TYPE_THEIRS,
                    CaptionKind.WITHDRAWN
                    if audio == "withdrawn"
                    else CaptionKind.FINISHED,
                    ()
                    if audio == "withdrawn"
                    else (Clause("Good morning.", {SPANISH: "Buenos días."}),),
                )
            )
        qapp.processEvents()
        assert not received
        assert bool(requests) == (at_release != OTHER_WINDOW and audio != "silent")
        assert typed == ([expected] if reported is Said.TYPED else [])
        assert copied == ([expected] if reported is Said.COPIED else [])
        assert sign[-1] == reported
        if reported is Said.NOTHING_HEARD:
            assert shown.text == "Didn't hear anyone"
    finally:
        dictating.stop()
        shiboken6.delete(dictating)
        shiboken6.delete(settings)
        shiboken6.delete(shown)
        shiboken6.delete(desktop)


@pytest.mark.parametrize(
    ("source", "category", "speakers", "translation", "cancel"),
    (
        (WHOLE_SYSTEM, SourceCategory.SYSTEM, True, None, False),
        (SourceId("app-1"), SourceCategory.VIDEO, True, SPANISH, False),
        (MIC, SourceCategory.MIC, False, None, False),
        (MIC, SourceCategory.MIC, False, None, True),
    ),
)
def test_hold_types_the_same_result_used_by_the_caption_feed(
    qapp: QApplication,
    source: SourceId,
    category: SourceCategory,
    speakers: bool,
    translation: Language | None,
    cancel: bool,
) -> None:
    desktop = make_app()
    listener = QtListener(desktop, None)
    recorder = StandInMic()
    now = 100.0
    closed: list[float] = []
    typed: list[str] = []
    ready = False
    escape = False
    request = TranscriptionRequest(
        CaptionId("line"), SpeechKind.FINISHED, Source(source, category), 100.0, 102.5
    )
    shared = HeldCaptions(
        CaptionResults(source),
        lambda _end: (request,) if ready else None,
        lambda: closed.append(now),
        lambda: 0.4,
        lambda lines: shown_text(lines, translation),
    )

    def should_not_send(_request: TranscriptionRequest, _audio: bytes) -> None:
        pytest.fail("caption typing recorded a second clip")

    def type_text(text: str) -> bool:
        typed.append(text)
        return True

    typing = Dictating(
        desktop.settings,
        recorder,
        should_not_send,
        type_text,
        lambda: WINDOW,
        lambda key: key == "escape" and escape,
        lambda _wanted: True,
        clock=lambda: now,
        from_speakers=speakers,
        share_captions=lambda _start: shared,
    )
    desktop.feed.received.connect(typing.caption_received)
    desktop.feed.applied.connect(typing.caption_applied)
    desktop.feed.dropped.connect(typing.caption_dropped)

    def emit(kind: CaptionKind, words: str) -> None:
        listener.caption_updated(
            CaptionUpdate(
                request.caption_id,
                source,
                kind,
                (Clause(words, {SPANISH: "Buenos días."}),),
                times=SpeechTimes(100.0, 102.5, now, now),
            )
        )
        qapp.processEvents()

    try:
        typing.key_down()
        emit(CaptionKind.LIVE, "Good")
        provisional = desktop.feed.history.caption(request.caption_id)
        assert provisional is not None and provisional.live
        assert recorder.hold == 0 and typed == []
        now += 2
        typing.key_up()
        ready = True
        escape = cancel
        typing._read_esc()
        assert typed == []

        emit(CaptionKind.FINISHED, "Good morning.")
        typing._read_esc()
        shown = desktop.feed.history.caption(request.caption_id)
        assert shown is not None and not shown.live
        assert shown.by_you == (source == MIC)
        assert shown.translation(SPANISH) == "Buenos días."
        expected = (
            shown.original if translation is None else shown.translation(translation)
        )
        assert typed == ([] if cancel else [expected + " "])
        assert closed == [now]
    finally:
        typing.stop()
        shiboken6.delete(typing)
        shiboken6.delete(desktop)
