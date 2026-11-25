"""The app's protocol messages against the server's examples (decision 0011).

polyglotic-server owns protocol.md and its examples; `tests/protocol_examples/`
is a copy, written by `tools/protocol_examples.py` with a manifest of its
source. These tests check:
- the copy is exactly what the tool wrote (no hand edits);
- every example is either checked here or listed as not used by the app yet,
  so a new message from the server fails until someone decides;
- each message the app sends, built from the app's own values, is exactly
  its example;
- each message the app reads parses from its example into the right values,
  and what it doesn't know (fields, types, codes) is ignored.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from polyglotic_desktop.connection import learning, listening, protocol
from polyglotic_desktop.core.listening.captions import CaptionKind, Language
from polyglotic_desktop.core.listening.recheck import (
    Answer,
    FlagOutcome,
    LineFlagged,
    RecheckOutcome,
    RecheckRequest,
)
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
    WithdrawalReason,
    WithdrawCaption,
)
from polyglotic_desktop.core.shared import (
    EntryId,
    LearningEvent,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
    WordUnsaved,
)
from polyglotic_desktop.ports.capture import SourceCategory
from tools import protocol_examples

EXAMPLES = protocol_examples.COPY / "v1"

CHECKED = {
    # from the app
    "hello",
    "hello.resume",
    "hello.live_translation",
    "settings",
    "speech.live",
    "speech.live.numbered",
    "speech.finished",
    "speech.finished.cut",
    "speech.finished.joined",
    "speech.finished.own_targets",
    "speech.finished.original_only",
    "speech.finished.own_spoken_language",
    "withdraw",
    "recheck",
    "ping",
    "http/redeem.request",
    "http/feedback.request",
    "http/feedback.request.work_with_us",
    "http/problem_report.request",
    "learning",
    "learning_sync",
    "learning_delete",
    "exposures",
    "consent",
    "consent.agreement",
    "usage",
    # from the server
    "welcome",
    "welcome.resumed",
    "update_required",
    "auth_failed",
    "auth_failed.too_many_attempts",
    "server_busy",
    "too_many_sessions",
    "pong",
    "pace",
    "caption_update.live",
    "caption_update.live.trace",
    "live_translation",
    "allowance_update",
    "allowance_exhausted",
    "cross_border_consent_required",
    "registration_required",
    "caption_update.finished",
    "caption_update.finished.joined",
    "caption_update.finished.continuation",
    "caption_update.finished.mixed",
    "caption_update.finished.words",
    "caption_update.withdrawn",
    "recheck_result",
    "recheck_result.no_words",
    "recheck_result.best_unavailable",
    "recheck_result.try_later",
    "minutes",
    "notice",
    "notice.server_restarting",
    "error",
    "error.rate_limited",
    "error.consent_missing",
    "http/redeem.response",
    "http/redeem.error",
    "http/redeem.error.too_many_attempts",
    "http/redeem.error.code_starts_new_account",
    "http/redeem.error.subscription_ended",
    "http/feedback.response",
    "http/feedback.error",
    "http/problem_report.response",
    "http/problem_report.error",
    "received",
    "received.consent",
    "learning_state",
    "learning_deleted",
    "welcome.plan",
    "plan.plus",
    "plan.pass",
    "plan.ending",
    "plan.free",
    "plan.grace",
    "limit_reached",
    # planned maintenance (server decision 0066; polyglotic-hq 319)
    "welcome.maintenance",
    "maintenance",
    "maintenance.cleared",
    "server_busy.maintenance",
    "notice.maintenance_started",
}

NOT_USED_YET: set[str] = {
    # Free's day by the learner's clock: Free's minutes come later (169's S1b)
    "hello.utc_offset",
    # the download link's tag (server 0042, polyglotic-hq 195): the app
    # doesn't know its download's tag yet (195's proposal)
    "hello.ref",
    # 193's codes from a Plus email, redeemed while signed in: 185's proposal
    "http/redeem.error.subscription_running",
}


def example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (EXAMPLES / f"{name}.json").read_text(encoding="utf-8")
    )
    return data


# --- The copy ----------------------------------------------------------------


def test_the_copy_is_what_the_tool_wrote() -> None:
    commit, digests = protocol_examples.read_manifest()
    files = protocol_examples.copied_files()
    assert len(commit) == 40
    assert set(files) == set(digests), "files added to or removed from the copy by hand"
    for path, content in files.items():
        assert protocol_examples.digest(content) == digests[path], (
            f"{path} was edited by hand: run tools/protocol_examples.py copy"
        )


def test_every_example_is_checked_or_listed_as_not_used_yet() -> None:
    names = {
        Path(path).with_suffix("").as_posix().removeprefix("v1/")
        for path in protocol_examples.copied_files()
    }
    assert not CHECKED & NOT_USED_YET
    assert names == CHECKED | NOT_USED_YET, (
        "new or removed examples: check them here, or list them as not used yet"
    )


# --- From the app ------------------------------------------------------------

VIDEO = Source(SourceId("source-1"), SourceCategory.VIDEO)
CAPTION = CaptionId("6f1d2c3b-4a5e-4f60-8b7c-9d0e1f2a3b4c")
EARLIER = CaptionId("0a9b8c7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d")


def test_hello() -> None:
    hello = protocol.Hello(
        app_version="0.1.0",
        install_id="3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f",
        channel="win-x64-alpha",
        os="windows-11",
        auth=protocol.HelloAuth(
            device_token="pgd_EXAMPLE0DEVICE0TOKEN0NOT0REAL0xxxxxxxxxxxxx"
        ),
    )
    assert protocol.dump(hello) == example("hello")


def test_hello_resuming_a_lost_session() -> None:
    # server decision 0040 (polyglotic-hq 165): `resume`, optional
    hello = protocol.Hello(
        app_version="0.1.0",
        install_id="3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f",
        channel="win-x64-alpha",
        os="windows-11",
        auth=protocol.HelloAuth(
            device_token="pgd_EXAMPLE0DEVICE0TOKEN0NOT0REAL0xxxxxxxxxxxxx"
        ),
        resume="9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b",
    )
    assert protocol.dump(hello) == example("hello.resume")


def test_hello_requests_separate_translations() -> None:
    agreed = example("hello.live_translation")
    hello = protocol.Hello.model_validate(agreed)
    assert hello.live_translation is True and protocol.dump(hello) == agreed


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("live_translation", protocol.LiveTranslation),
        ("allowance_update", protocol.AllowanceUpdate),
        ("allowance_exhausted", protocol.AllowanceExhausted),
        ("cross_border_consent_required", protocol.CrossBorderConsentRequired),
        ("registration_required", protocol.RegistrationRequired),
    ],
)
def test_messages_from_the_live_translation_contract_snapshot(
    name: str, model: type[protocol.Message]
) -> None:
    assert isinstance(decoded(name), model)


def test_settings() -> None:
    chosen = ListeningSettings(
        targets=(Language("en"),),
        second_languages={Language("en"): Language("zh")},
        spelling_hints=("Polyglotic", "Wang Fang"),
    )
    assert protocol.dump(listening.settings(chosen, 2)) == example("settings")


@pytest.mark.parametrize(
    ("name", "request_"),
    [
        (
            "speech.live",
            TranscriptionRequest(
                CAPTION, SpeechKind.LIVE, VIDEO, 12.48, 14.02, section=0
            ),
        ),
        (
            "speech.finished",
            TranscriptionRequest(CAPTION, SpeechKind.FINISHED, VIDEO, 12.48, 15.31),
        ),
        (
            "speech.finished.joined",
            TranscriptionRequest(
                CAPTION, SpeechKind.FINISHED, VIDEO, 12.48, 18.9, replaces=(EARLIER,)
            ),
        ),
        (
            "speech.finished.cut",  # cut while the speech went on, both ends (291)
            TranscriptionRequest(
                CAPTION,
                SpeechKind.FINISHED,
                VIDEO,
                18.9,
                24.92,
                cut_before=True,
                cut_after=True,
            ),
        ),
    ],
)
def test_speech_headers(name: str, request_: TranscriptionRequest) -> None:
    assert protocol.dump(listening.speech_header(request_)) == example(name)


# --- Each source's own languages (the server's decision 0033) -----------------

TODAY = ListeningSettings(
    targets=(Language("en"),), second_languages={Language("en"): Language("zh")}
)
"""Today's interface: one set of languages, every source the same."""
OTHER = SourceId("source-2")


@pytest.mark.parametrize(
    ("name", "own"),
    [
        ("speech.finished", None),  # its languages are the session's
        ("speech.finished.own_targets", (Language("ja"),)),
        ("speech.finished.original_only", ()),
    ],
)
def test_a_sources_own_languages_go_on_its_speech(
    name: str, own: tuple[Language, ...] | None
) -> None:
    chosen = TODAY
    if own is not None:
        chosen = replace(TODAY, source_targets={VIDEO.id: own})
    request = TranscriptionRequest(CAPTION, SpeechKind.FINISHED, VIDEO, 12.48, 15.31)
    frame = listening.outgoing(request, b"OggS", chosen, 2)
    assert isinstance(frame, bytes)
    header, _ = protocol.read_speech_frame(frame)
    assert protocol.dump(header) == example(name)


def test_a_source_without_its_own_languages_names_them_when_others_differ() -> None:
    """On a server that knows `source.targets`, a source not named there
    would get every source's languages (the session's): so it names its own."""
    chosen = replace(TODAY, source_targets={OTHER: ()})
    assert listening.session_targets(chosen, 2) == ("en",)
    assert listening.own_targets(chosen, VIDEO.id, 2) is None  # the same: left out
    chosen = replace(TODAY, source_targets={OTHER: (Language("ja"),)})
    assert listening.session_targets(chosen, 2) == ("en", "ja")
    assert listening.own_targets(chosen, VIDEO.id, 2) == ("en",)
    assert listening.own_targets(chosen, OTHER, 2) == ("ja",)


def test_settings_carry_every_sources_languages_up_to_the_limit() -> None:
    """For a server from before 2026-11-07, which translates into these only."""
    chosen = replace(
        TODAY,
        second_languages={
            Language("en"): Language("zh"),
            Language("fr"): Language("en"),
        },
        source_targets={
            SourceId("app-1"): (Language("ja"),),
            SourceId("app-2"): (),
            SourceId("app-3"): (Language("fr"),),
        },
    )
    assert chosen.all_targets == ("en", "ja", "fr")
    sent = listening.settings(chosen, 2)
    assert sent.targets == ("en", "ja")
    # a second language only for a target sent: the server refuses others
    assert sent.second_languages == {"en": "zh"}
    assert listening.settings(chosen, 3).second_languages == {"en": "zh", "fr": "en"}
    # a source's own languages are held to the limit too
    many = replace(TODAY, source_targets={VIDEO.id: tuple(map(Language, "abc"))})
    assert listening.own_targets(many, VIDEO.id, 2) == ("a", "b")


def test_withdraw() -> None:
    withdrawal = WithdrawCaption(CAPTION, VIDEO, WithdrawalReason.MIC_BLEED)
    assert protocol.dump(listening.withdraw(withdrawal)) == example("withdraw")
    sent = listening.outgoing(withdrawal, None, TODAY, 2)
    assert isinstance(sent, str) and json.loads(sent) == example("withdraw")


def test_ping() -> None:
    assert protocol.dump(protocol.Ping()) == example("ping")


def test_redeem_request() -> None:
    request = protocol.RedeemRequest(
        invite_code="7KQM-X2PD-9VHT-C4RA",
        install_id="3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f",
        app_version="0.1.0",
        channel="win-x64-alpha",
        os="windows-11",
    )
    assert protocol.dump(request) == example("http/redeem.request")


@pytest.mark.parametrize(
    "name", ["http/feedback.request", "http/feedback.request.work_with_us"]
)
def test_feedback_request(name: str) -> None:
    # project 053; the app leaves out fields that are null
    sent = example(name)
    request = protocol.FeedbackRequest.model_validate(sent)
    assert protocol.dump(request) == {k: v for k, v in sent.items() if v is not None}
    assert "text" not in repr(request) or sent["text"] not in repr(request)


def test_feedback_answers() -> None:
    answer = protocol.validate(
        protocol.FeedbackResponse, example("http/feedback.response")
    )
    assert answer.id == example("http/feedback.response")["id"]
    error = protocol.validate(protocol.HttpError, example("http/feedback.error"))
    assert (error.error, error.retry_after) == ("too_many_attempts", 3600)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def same_instants(sent: dict[str, Any], expected: dict[str, Any]) -> bool:
    """`at` values compared as instants: protocol.md lets milliseconds be
    left out, and the examples do both."""
    if sent.keys() != expected.keys():
        return False
    return all(
        utc(sent[k]) == utc(expected[k]) if k == "at" else sent[k] == expected[k]
        for k in sent
    )


def test_learning_from_learnings_events() -> None:
    expected = example("learning")
    word, other, english = (
        EntryId("cedict:y7p98nwvxq"),
        EntryId("cedict:4r1kz0mq8d"),
        EntryId("ecdict:njx2am9103"),
    )
    events: list[LearningEvent] = [
        WordLookedUp(word, utc("2026-11-04T09:15:02.120Z")),
        WordSaved(word, utc("2026-11-04T09:15:05.480Z")),
        WordStatusChanged(word, WordStatus.LEARNING, utc("2026-11-04T09:15:05.480Z")),
        WordStatusChanged(other, WordStatus.KNOWN, utc("2026-11-04T09:16:40Z")),
        WordUnsaved(english, utc("2026-11-04T09:17:00Z")),
    ]
    ids = [e["id"] for e in expected["events"]]
    message = protocol.Learning(
        batch=expected["batch"],
        events=tuple(
            learning.learning_event(e, i) for e, i in zip(events, ids, strict=True)
        ),
    )
    sent = protocol.dump(message)
    assert sent.keys() == expected.keys() and sent["batch"] == expected["batch"]
    for mine, theirs in zip(sent["events"], expected["events"], strict=True):
        assert same_instants(mine, theirs), mine


def test_times_are_utc_with_milliseconds() -> None:
    assert protocol.at(utc("2026-11-04T09:16:40Z")) == "2026-11-04T09:16:40.000Z"
    local = datetime.fromisoformat("2026-11-04T20:15:02.120+11:00")
    assert protocol.at(local) == "2026-11-04T09:15:02.120Z"
    assert protocol.parse_at("2026-11-04T09:16:40Z") == utc("2026-11-04T09:16:40Z")


def test_learning_sync_and_delete() -> None:
    assert protocol.dump(protocol.LearningSync(since="1180")) == example(
        "learning_sync"
    )
    assert protocol.dump(protocol.LearningSync()) == {"type": "learning_sync"}
    assert protocol.dump(protocol.LearningDelete()) == example("learning_delete")


def test_exposures() -> None:
    expected = example("exposures")
    days = {
        date(2026, 11, 2): {"cedict:y7p98nwvxq": 4, "cedict:4r1kz0mq8d": 1},
        date(2026, 11, 3): {"cedict:y7p98nwvxq": 2, "cedict:gone00000x": 0},
    }
    message = protocol.Exposures(
        batch=expected["batch"],
        days=tuple(learning.exposure_day(d, c) for d, c in days.items()),
    )
    assert protocol.dump(message) == expected


def test_consent() -> None:
    expected = example("consent")
    consent = protocol.Consent(
        id=expected["id"],
        at=protocol.at(utc("2026-11-04T09:00:00Z")),
        usage=True,
        crashes=True,
        exposures=False,
    )
    assert protocol.dump(consent) == expected


def test_consent_with_the_agreement_accepted() -> None:
    expected = example("consent.agreement")
    consent = protocol.Consent(
        id=expected["id"],
        at=protocol.at(utc("2026-11-04T09:02:00Z")),
        usage=True,
        crashes=False,
        exposures=False,
        agreement=protocol.Agreement(
            version="tester-2026-11-08", at=protocol.at(utc("2026-11-04T09:01:30Z"))
        ),
    )
    assert protocol.dump(consent) == expected


def test_usage() -> None:
    expected = example("usage")
    events = tuple(
        protocol.UsageEvent(
            id=e["id"],
            name=e["name"],
            v=1,
            at=protocol.at(utc(e["at"])),
            props=e["props"],
        )
        for e in expected["events"]
    )
    message = protocol.Usage(batch=expected["batch"], events=events)
    assert protocol.dump(message) == expected


def test_a_speech_frame_is_length_header_audio() -> None:
    request = TranscriptionRequest(CAPTION, SpeechKind.LIVE, VIDEO, 12.48, 14.02, 0)
    audio = b"OggS fake audio"
    frame = listening.outgoing(request, audio, TODAY, 2)
    assert isinstance(frame, bytes)
    length = int.from_bytes(frame[:4], "big")
    assert json.loads(frame[4 : 4 + length]) == example("speech.live")
    assert frame[4 + length :] == audio
    header, back = protocol.read_speech_frame(frame)
    assert header == listening.speech_header(request) and back == audio
    assert length <= protocol.Limits().speech_header_bytes


def test_no_frame_without_audio() -> None:
    request = TranscriptionRequest(CAPTION, SpeechKind.FINISHED, VIDEO, 1.0, 2.0)
    assert listening.outgoing(request, None, TODAY, 2) is None


def test_speech_times_are_rounded_to_milliseconds() -> None:
    request = TranscriptionRequest(
        CAPTION, SpeechKind.FINISHED, VIDEO, 51234.5678912, 51236.0000004
    )
    header = listening.speech_header(request)
    assert (header.speech_start, header.speech_end) == (51234.568, 51236.0)


def test_secrets_and_text_stay_out_of_reprs() -> None:
    token = "pgd_EXAMPLE0DEVICE0TOKEN0NOT0REAL0xxxxxxxxxxxxx"
    hello = protocol.Hello(
        app_version="0.1.0",
        install_id="x",
        channel="win-x64-alpha",
        os="windows-11",
        auth=protocol.HelloAuth(device_token=token),
    )
    redeem = protocol.RedeemRequest(
        invite_code="7KQM-X2PD-9VHT-C4RA",
        install_id="x",
        app_version="0.1.0",
        channel="win-x64-alpha",
        os="windows-11",
    )
    caption = protocol.decode(json.dumps(example("caption_update.finished")))
    settings = protocol.validate(protocol.Settings, example("settings"))
    assert token not in repr(hello)
    assert "7KQM" not in repr(redeem)
    assert "你好" not in repr(caption) and "Hello" not in repr(caption)
    assert "Polyglotic" not in repr(settings)


# --- From the server ---------------------------------------------------------


# --- Each source's own spoken language (the server's decision 0051) ----------

CALL = Source(SourceId("source-2"), SourceCategory.CALL)


def test_a_sources_own_spoken_language_goes_on_its_speech() -> None:
    """A call heard as Mandarin beside a video detected: the session's is
    Detect (they differ), so the call names its own."""
    en, ja, zh = Language("en"), Language("ja"), Language("zh")
    chosen = ListeningSettings(
        targets=(en,),
        source_targets={CALL.id: (en,), VIDEO.id: (ja,)},
        source_spoken={CALL.id: zh, VIDEO.id: None},
    )
    request = TranscriptionRequest(
        CaptionId("2b7e4c19-8d3a-4f52-9e61-0c5d7a8b9f13"),
        SpeechKind.FINISHED,
        CALL,
        40.12,
        42.9,
    )
    frame = listening.outgoing(request, b"OggS", chosen, 2)
    assert isinstance(frame, bytes)
    header, _ = protocol.read_speech_frame(frame)
    assert protocol.dump(header) == example("speech.finished.own_spoken_language")


def test_a_sources_spoken_language_is_left_out_when_it_is_the_sessions() -> None:
    """As with one setting for every window, nothing changes on the wire;
    a source detected under a session naming one says "detect"."""
    zh = Language("zh")
    agreed = replace(TODAY, spoken_language=zh, source_spoken={VIDEO.id: zh})
    assert listening.own_spoken_language(agreed, VIDEO.id) is None
    assert listening.own_spoken_language(TODAY, VIDEO.id) is None  # none named
    detected = replace(agreed, source_spoken={VIDEO.id: None, OTHER: zh})
    assert listening.own_spoken_language(detected, VIDEO.id) == "detect"
    assert listening.own_spoken_language(detected, OTHER) is None


def test_a_recheck_asks_for_the_spoken_language_its_source_had() -> None:
    zh = Language("zh")
    chosen = replace(TODAY, source_spoken={CALL.id: zh})
    assert chosen.spoken_language_of(CALL.id) == zh
    assert chosen.spoken_language_of(VIDEO.id) is None  # the session's: Detect


def test_welcome_names_the_source_fields_the_server_uses() -> None:
    # `source_fields`: added 2026-11-09 (server decision 0051), optional
    newer = decoded("welcome")
    assert isinstance(newer, protocol.Welcome)
    assert "spoken_language" in newer.source_fields
    older = example("welcome")
    del older["source_fields"]
    welcome = protocol.decode(json.dumps(older))
    assert isinstance(welcome, protocol.Welcome) and welcome.source_fields == ()


def decoded(name: str) -> protocol.Message:
    message = protocol.decode(json.dumps(example(name)))
    assert message is not None
    return message


def test_welcome() -> None:
    welcome = decoded("welcome")
    assert isinstance(welcome, protocol.Welcome)
    assert welcome.protocol == 1 and welcome.min_app_version == "0.1.0"
    assert welcome.limits.ping_seconds == 25
    assert welcome.limits.speech_frame_bytes == 262_144
    assert welcome.live_interval_min is None
    # No flag is on (server #127, 2026-11-06). The server may list a flag that
    # is off: `{"word_times": false}` since server #336 (531, decision 0100).
    assert not any(welcome.features.values())


def test_welcome_reads_a_flag_that_is_off() -> None:
    # server #336 (polyglotic-hq 531, server decision 0100): the welcome says
    # the word timer's flag, off; the next copy of the examples carries it
    message = example("welcome")
    message["features"] = {"word_times": False}
    welcome = protocol.decode(json.dumps(message))
    assert isinstance(welcome, protocol.Welcome)
    assert welcome.features == {"word_times": False}


def test_welcome_says_whether_the_session_was_resumed() -> None:
    # `resumed`: added 2026-11-08 (server decision 0040), optional
    resumed = decoded("welcome.resumed")
    assert isinstance(resumed, protocol.Welcome) and resumed.resumed is True
    older = decoded("welcome")  # servers before it leave it out
    assert isinstance(older, protocol.Welcome) and older.resumed is False


def test_welcome_names_the_account_from_servers_that_send_it() -> None:
    # `account_id`: added 2026-11-05 (project 041, server #67), optional -
    # older servers leave it out
    newer = decoded("welcome")  # the server's example has it
    assert isinstance(newer, protocol.Welcome)
    assert newer.account_id == "4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e"
    older = example("welcome")
    del older["account_id"]
    welcome = protocol.decode(json.dumps(older))
    assert isinstance(welcome, protocol.Welcome) and welcome.account_id is None


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("update_required", protocol.UpdateRequired),
        ("auth_failed", protocol.AuthFailed),
        ("auth_failed.too_many_attempts", protocol.AuthFailed),
        ("server_busy", protocol.ServerBusy),
        ("too_many_sessions", protocol.TooManySessions),
        ("pong", protocol.Pong),
        ("pace", protocol.Pace),
        ("minutes", protocol.Minutes),
        ("notice", protocol.Notice),
        ("notice.server_restarting", protocol.Notice),
        ("notice.maintenance_started", protocol.Notice),
        ("server_busy.maintenance", protocol.ServerBusy),
        ("maintenance", protocol.Maintenance),
        ("maintenance.cleared", protocol.Maintenance),
        ("error", protocol.Error),
        ("error.rate_limited", protocol.Error),
        ("error.consent_missing", protocol.Error),
    ],
)
def test_server_messages_parse(name: str, model: type[protocol.Message]) -> None:
    message = decoded(name)
    assert isinstance(message, model)
    data = example(name)
    for key, value in protocol.dump(message).items():
        assert data[key] == value, key


def test_refusals_say_what_to_do() -> None:
    failed = decoded("auth_failed.too_many_attempts")
    assert isinstance(failed, protocol.AuthFailed)
    assert (failed.reason, failed.retry_after) == ("too_many_attempts", 420)
    busy = decoded("server_busy")
    assert isinstance(busy, protocol.ServerBusy) and busy.retry_after == 30


def test_a_numbered_speech_frame() -> None:
    """The frame's number in the caption timelines (perf.trace; the server's
    decision 0104)."""
    request = TranscriptionRequest(CAPTION, SpeechKind.LIVE, VIDEO, 12.48, 14.02, 0)
    frame = listening.outgoing(request, b"OggS fake audio", TODAY, 2, seq=41)
    assert isinstance(frame, bytes)
    length = int.from_bytes(frame[:4], "big")
    assert json.loads(frame[4 : 4 + length]) == example("speech.live.numbered")


def test_a_caption_updates_trace() -> None:
    message = decoded("caption_update.live.trace")
    assert isinstance(message, protocol.CaptionUpdate)
    assert message.trace is not None
    assert message.trace.seq == 41 and message.trace.waited_ms == 12
    assert message.trace.stages_ms["speech_model"] == 210
    assert message.trace.server_ms == 298
    assert [(u.seq, u.why) for u in message.trace.unanswered] == [
        (40, "overtaken_waiting")
    ]


def test_a_live_caption_update() -> None:
    message = decoded("caption_update.live")
    assert isinstance(message, protocol.CaptionUpdate)
    update = listening.caption_update(message)
    assert update.kind is CaptionKind.LIVE
    assert update.caption_id == CAPTION and update.source_id == "source-1"
    assert update.language == "zh" and update.languages_heard == ("zh",)
    (clause,) = update.clauses
    assert clause.original == "你好，今天天气"
    assert clause.translations == {"en": "Hello, today's weather"}
    (link,) = clause.links[Language("en")]
    assert clause.original[slice(*link.original)] == "你好"
    assert clause.translations[Language("en")][slice(*link.translation)] == "Hello"
    assert link.key and link.confidence == 0.91
    assert update.replaces == () and update.processing_ms == 286


def test_a_finished_caption_and_a_joined_one() -> None:
    finished = decoded("caption_update.finished")
    joined = decoded("caption_update.finished.joined")
    assert isinstance(finished, protocol.CaptionUpdate)
    assert isinstance(joined, protocol.CaptionUpdate)
    first, second = listening.caption_update(finished), listening.caption_update(joined)
    assert first.kind is second.kind is CaptionKind.FINISHED
    assert first.caption_id == second.caption_id == CAPTION
    assert first.replaces == () and second.replaces == (EARLIER,)
    assert len(second.clauses[0].links[Language("en")]) == 4
    # an older server's clauses say nothing of what their lines are written in
    assert first.clauses[0].written_in == {}


def test_a_mixed_caption_says_what_each_line_is_written_in() -> None:
    """Server decision 0097 (polyglotic-hq 497): a caption labelled
    Mandarin, its English clause's line under English in Chinese."""
    message = decoded("caption_update.finished.mixed")
    assert isinstance(message, protocol.CaptionUpdate)
    first, second = listening.caption_update(message).clauses
    en, zh = Language("en"), Language("zh")
    assert first.written_in == {en: zh} and second.written_in == {en: en}
    assert first.translations[en] == "这与我最初的预期不同。"
    (link, *_) = first.links[en]
    assert first.original[slice(*link.original)] == "I"
    assert first.translations[en][slice(*link.translation)] == "我"
    # null, as an optional field may be: nothing said
    data = example("caption_update.finished.mixed")
    data["clauses"][0]["written_in"] = None
    nulled = protocol.decode(json.dumps(data))
    assert isinstance(nulled, protocol.CaptionUpdate)
    assert listening.caption_update(nulled).clauses[0].written_in == {}


def test_a_caption_says_when_each_word_was_said() -> None:
    """Server decision 0099, this app's 0247 (polyglotic-hq 528): each word's
    span in its clause and its times on this app's own clock; an older
    server's clauses have none, and an update with them still shows as
    before (nothing reads them yet)."""
    message = decoded("caption_update.finished.words")
    assert isinstance(message, protocol.CaptionUpdate)
    assert message.clauses is not None
    (clause,) = message.clauses
    assert clause.words is not None
    assert [clause.original[slice(*w.original)] for w in clause.words] == list(
        "你好今天天气很好"
    )
    assert (clause.words[0].start, clause.words[-1].end) == (12.52, 14.84)
    starts = [w.start for w in clause.words]
    assert starts == sorted(starts)
    plain = decoded("caption_update.finished")
    assert isinstance(plain, protocol.CaptionUpdate) and plain.clauses is not None
    assert all(c.words is None for c in plain.clauses)
    timed, untimed = listening.caption_update(message), listening.caption_update(plain)
    assert timed.clauses[0].words
    assert timed.clauses[0].words[0].original == clause.words[0].original
    assert untimed.clauses[0].words == ()


def test_a_withdrawn_caption() -> None:
    message = decoded("caption_update.withdrawn")
    assert isinstance(message, protocol.CaptionUpdate)
    update = listening.caption_update(message)
    assert update.kind is CaptionKind.WITHDRAWN
    assert update.reason is WithdrawalReason.MIC_BLEED
    assert update.clauses == () and update.language is None


def test_redeem_responses() -> None:
    response = protocol.validate(
        protocol.RedeemResponse, example("http/redeem.response")
    )
    assert response.cohort == "alpha" and response.device_token.startswith("pgd_")
    error = protocol.validate(protocol.HttpError, example("http/redeem.error"))
    assert error.error == "invite_code_not_valid" and error.retry_after is None
    limited = protocol.validate(
        protocol.HttpError, example("http/redeem.error.too_many_attempts")
    )
    assert limited.retry_after == 600
    assert error.reason is None
    # the code's subscription ended before it was used (server #252, 258)
    ended = protocol.validate(
        protocol.HttpError, example("http/redeem.error.subscription_ended")
    )
    assert (ended.error, ended.reason) == (
        "invite_code_not_valid",
        "subscription_ended",
    )


def test_received() -> None:
    batch = decoded("received")
    assert isinstance(batch, protocol.Received)
    assert batch.batch == example("learning")["batch"] and batch.id is None
    consent = decoded("received.consent")
    assert isinstance(consent, protocol.Received)
    assert consent.id == example("consent")["id"] and consent.batch is None


def test_learning_state_names_the_latest_deletion() -> None:
    """polyglotic-server protocol.md (051): the server's example carries the
    account's latest deletion, and `deletion` is optional - missing for an
    account never deleted (the copy of the examples refreshed with it,
    polyglotic-hq project 059)."""
    data = example("learning_state")
    state = protocol.decode(json.dumps(data))
    assert isinstance(state, protocol.LearningState)
    assert state.deletion == protocol.DeletionState(
        generation=1, at="2026-11-04T08:00:00.000Z"
    )
    bare = {k: v for k, v in data.items() if k != "deletion"}
    never = protocol.decode(json.dumps(bare))
    assert isinstance(never, protocol.LearningState) and never.deletion is None


def test_learning_state_as_learnings_events() -> None:
    state = decoded("learning_state")
    assert isinstance(state, protocol.LearningState)
    assert (state.cursor, state.more) == ("1234", False)
    assert learning.from_state(state, "cedict") == [
        WordStatusChanged(
            EntryId("cedict:y7p98nwvxq"),
            WordStatus.LEARNING,
            utc("2026-11-04T09:15:05.480Z"),
        ),
        WordStatusChanged(
            EntryId("cedict:4r1kz0mq8d"), WordStatus.KNOWN, utc("2026-11-04T09:16:40Z")
        ),
        WordSaved(EntryId("cedict:y7p98nwvxq"), utc("2026-11-04T09:15:05.480Z")),
    ]
    # an account learning both languages: each takes its own dictionary's
    assert learning.from_state(state, "ecdict") == [
        WordUnsaved(EntryId("ecdict:njx2am9103"), utc("2026-11-04T09:17:00Z")),
    ]


def test_a_status_this_app_doesnt_know_is_left_out() -> None:
    data = example("learning_state")
    data["statuses"][0]["status"] = "mastered"
    data["saved_words"][0]["at"] = "yesterday"
    state = protocol.decode(json.dumps(data))
    assert isinstance(state, protocol.LearningState)
    kinds = [type(e).__name__ for e in learning.from_state(state, "cedict")]
    assert kinds == ["WordStatusChanged"]
    kinds = [type(e).__name__ for e in learning.from_state(state, "ecdict")]
    assert kinds == ["WordUnsaved"]


def test_learning_deleted() -> None:
    assert isinstance(decoded("learning_deleted"), protocol.LearningDeleted)


# --- What the app doesn't know -----------------------------------------------


def test_unknown_fields_are_ignored() -> None:
    data = example("caption_update.finished") | {"steadiness": 0.4}
    data["clauses"][0]["emphasis"] = [1, 2]
    message = protocol.decode(json.dumps(data))
    assert isinstance(message, protocol.CaptionUpdate)


def test_unknown_message_types_are_ignored() -> None:
    assert protocol.decode('{"type": "fireworks", "colour": "red"}') is None


def test_unknown_codes_are_kept_for_the_caller_to_ignore() -> None:
    withdrawn = example("caption_update.withdrawn") | {"reason": "laughter"}
    message = protocol.decode(json.dumps(withdrawn))
    assert isinstance(message, protocol.CaptionUpdate)
    assert listening.caption_update(message).reason is None
    notice = protocol.decode('{"type": "notice", "code": "new_moon"}')
    assert isinstance(notice, protocol.Notice) and notice.code == "new_moon"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[1, 2]",
        '{"no": "type"}',
        '{"type": "caption_update", "caption_id": "x", "kind": "live"}',
    ],
)
def test_unreadable_messages_raise_without_quoting_them(text: str) -> None:
    with pytest.raises(protocol.ProtocolError) as raised:
        protocol.decode(text)
    assert text not in str(raised.value)


def test_errors_name_fields_not_values() -> None:
    data = example("caption_update.live")
    data["clauses"][0]["translations"] = "a secret sentence"
    with pytest.raises(protocol.ProtocolError) as raised:
        protocol.decode(json.dumps(data))
    assert "secret" not in str(raised.value)
    assert "clauses.0.translations" in str(raised.value)
    assert raised.value.__cause__ is None


# --- "Looks wrong?" (project 101) ------------------------------------------------


def test_a_recheck_frame_is_its_example_then_the_held_audio() -> None:
    request = RecheckRequest(
        CAPTION, VIDEO, 12.48, 15.31, b"OggS held", None, (Language("en"),)
    )
    assert protocol.dump(listening.recheck_header(request)) == example("recheck")
    frame = listening.recheck_frame(request)
    length = int.from_bytes(frame[:4], "big")
    assert json.loads(frame[4 : 4 + length]) == example("recheck")
    assert frame[4 + length :] == b"OggS held"
    assert "OggS" not in repr(request)  # the audio stays out of reprs


def test_a_recheck_names_second_languages_only_for_its_targets() -> None:
    """A source's own languages may leave out a session target with a second
    language; the server refuses a second language for a non-target."""
    request = RecheckRequest(
        CAPTION,
        VIDEO,
        12.48,
        15.31,
        b"OggS held",
        None,
        (Language("ja"),),
        {Language("en"): Language("zh"), Language("ja"): Language("en")},
    )
    assert listening.recheck_header(request).second_languages == {"ja": "en"}


def test_a_checked_line_and_the_other_outcomes() -> None:
    message = decoded("recheck_result")
    assert isinstance(message, protocol.RecheckResult)
    result = listening.recheck_result(message)
    assert result.caption_id == CAPTION and result.outcome is RecheckOutcome.CHECKED
    (clause,) = result.clauses
    assert clause.original == "Mình đi ăn trước nha."
    assert clause.translations == {"en": "Let's go eat first."}
    assert result.language == "vi" and result.processing_ms == 2870
    for name, outcome, retry in (
        ("recheck_result.no_words", RecheckOutcome.CHECKED, None),
        ("recheck_result.best_unavailable", RecheckOutcome.BEST_UNAVAILABLE, None),
        ("recheck_result.try_later", RecheckOutcome.TRY_LATER, 40),
    ):
        other = decoded(name)
        assert isinstance(other, protocol.RecheckResult)
        got = listening.recheck_result(other)
        assert (got.outcome, got.retry_after, got.clauses) == (outcome, retry, ())


def test_an_outcome_this_app_doesnt_know_is_a_failure() -> None:
    for unknown in ("from_the_future", "not_held"):  # not_held is the app's own
        message = protocol.decode(
            json.dumps({**example("recheck_result"), "outcome": unknown})
        )
        assert isinstance(message, protocol.RecheckResult)
        result = listening.recheck_result(message)
        assert result.outcome is RecheckOutcome.FAILED and result.clauses == ()


def test_line_flagged_is_the_tracking_plans_properties() -> None:
    flagged = LineFlagged(
        Language("vi"), SourceCategory.CALL, FlagOutcome.DIFFERS, Answer.BEST_RIGHT
    )
    assert listening.line_flagged(flagged) == {
        "language": "vi",
        "source_category": "call",
        "outcome": "differs",
        "answer": "best_right",
    }
    unheld = LineFlagged(Language("vi"), None, FlagOutcome.NOT_HELD, None)
    assert listening.line_flagged(unheld) == {
        "language": "vi",
        "outcome": "not_held",
        "answer": "none",
    }


# --- The plan (polyglotic-hq 178; read since 185) ------------------------------------


def test_the_plan_in_welcome_and_as_its_own_message() -> None:
    welcome = protocol.decode(json.dumps(example("welcome.plan")))
    assert isinstance(welcome, protocol.Welcome) and welcome.plan is not None
    assert (welcome.plan.tier, welcome.plan.source, welcome.plan.until) == (
        "plus",
        "cohort",
        None,
    )
    older = protocol.decode(json.dumps(example("welcome")))
    assert isinstance(older, protocol.Welcome) and older.plan is None
    for name in ("plan.plus", "plan.pass", "plan.ending", "plan.free", "plan.grace"):
        plan = protocol.decode(json.dumps(example(name)))
        assert isinstance(plan, protocol.Plan), name
        assert plan.model_dump(mode="json") == example(name), name


def test_a_plan_with_codes_this_app_doesnt_know_is_still_read() -> None:
    newer = example("plan.grace") | {"status": "frozen", "tier": "family"}
    newer["message"] = {"code": "something_new", "action": "dance"}
    plan = protocol.decode(json.dumps(newer | {"colour": "red"}))
    assert isinstance(plan, protocol.Plan) and plan.status == "frozen"


def test_limit_reached_with_the_plan_as_it_is_now() -> None:
    """polyglotic-hq 193's `limit_reached` (read since 185)."""
    message = protocol.decode(json.dumps(example("limit_reached")))
    assert isinstance(message, protocol.LimitReached)
    assert (message.kind, message.source, message.action) == (
        "plus_ended",
        "cohort",
        "get_plus",
    )
    assert message.plan is not None and message.plan.status == "ended"
    assert message.model_dump(mode="json") == example("limit_reached")


def test_a_planned_maintenance_window_in_welcome_and_as_its_own_message() -> None:
    """Server decision 0066 (polyglotic-hq 319): the window and the server's
    time in `welcome`; set, moved or cleared as a `maintenance` message;
    a refusal for it says so and until when."""
    welcome = decoded("welcome.maintenance")
    assert isinstance(welcome, protocol.Welcome)
    assert welcome.server_time == "2026-11-15T03:12:45.120Z"
    assert welcome.maintenance is not None
    assert welcome.maintenance.ends_at == "2026-11-15T04:30:00Z"
    assert decoded("welcome").maintenance is None  # type: ignore[attr-defined]
    told = decoded("maintenance")
    assert isinstance(told, protocol.Maintenance) and told.window is not None
    cleared = decoded("maintenance.cleared")
    assert isinstance(cleared, protocol.Maintenance) and cleared.window is None
    busy = decoded("server_busy.maintenance")
    assert isinstance(busy, protocol.ServerBusy)
    assert (busy.reason, busy.until, busy.retry_after) == (
        "maintenance",
        "2026-11-15T04:30:00Z",
        120,
    )
    assert decoded("server_busy").reason is None  # type: ignore[attr-defined]


def test_finished_continuation_names_another_audio_id() -> None:
    wire = example("caption_update.finished.continuation")
    update = listening.caption_update(protocol.validate(protocol.CaptionUpdate, wire))
    assert update.continues == wire["continues"]
    assert update.caption_id != update.continues
    assert update.replaces == ()
