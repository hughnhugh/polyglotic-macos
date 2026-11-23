"""Protocol version 1's messages, as polyglotic-server's docs/protocol.md defines them.

The messages of a listening or sync session, as typed models (pydantic),
and the binary speech frame: the opening exchange, speech and captions,
learning data both ways, consent, exposures and usage; and the HTTP
bodies beside them: redeeming an invite code, sending feedback. Every
model is checked against the server's examples (tests/test_protocol.py,
decision 0011).

- **From the app, exact:** the fields and values the server accepts, so the
  app never sends something it would refuse.
- **From the server, lenient:** fields the app doesn't know are ignored
  (versioning rule 1), and codes it doesn't know (a `notice`, an `error`, a
  withdrawn caption's `reason`) are kept as strings for the caller to
  ignore, so a newer server can't break an older app.

Privacy: device tokens, invite codes, caption text and spelling hints are
kept out of every model's `repr`, and `ProtocolError` never quotes what it
couldn't read.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

PROTOCOL = 1

Channel = Literal[
    "win-x64-alpha",
    "win-x64-beta",
    "win-x64-stable",
    "macos-arm64-alpha",
    "macos-arm64-beta",
    "macos-arm64-stable",
    "linux-x64-alpha",
    "linux-x64-beta",
    "linux-x64-stable",
]
MacOs = Annotated[str, StringConstraints(pattern=r"^macos-[1-9][0-9]{0,2}$")]
"""`macos-<major version>` (`macos-26`), as protocol.md's `os` allows."""
LinuxOs = Annotated[str, StringConstraints(pattern=r"^linux-[1-9][0-9]{0,2}$")]
"""`linux-<the kernel's major version>` (`linux-6`), as protocol.md's `os`
allows (the server's own smoke test says hello as `linux-6`)."""
Os = Literal["windows-10", "windows-11"] | MacOs | LinuxOs
Purpose = Literal["listen", "sync"]
Category = Literal[
    "browser", "video", "call", "game", "music", "system", "other", "mic"
]
Status = Literal["new", "learning", "known", "ignored"]
UsageValue = bool | int | float | str
"""A usage event's property: numbers, IDs and fixed lists, never free text
(the tracking plan's types)."""


def at(moment: datetime) -> str:
    """A time as protocol.md writes it: RFC 3339 in UTC, milliseconds, `Z`
    (`2026-11-04T09:15:02.120Z`). Naive times are taken as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    text = moment.astimezone(UTC).isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def parse_at(text: str) -> datetime:
    """A protocol time (`...Z`, milliseconds optional) as an aware datetime."""
    return datetime.fromisoformat(text).astimezone(UTC)


class ProtocolError(ValueError):
    """A message from the server that can't be read. Says which message and
    fields, never their values."""


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


# --- From the app ------------------------------------------------------------


class HelloAuth(Message):
    device_token: str = Field(repr=False)


class Hello(Message):
    type: Literal["hello"] = "hello"
    protocol: int = PROTOCOL
    app_version: str
    install_id: str
    channel: Channel
    os: Os
    purpose: Purpose = "listen"
    auth: HelloAuth
    resume: str | None = None
    """The listening session lost to the network, to resume (server
    decision 0040); left out on a first connection."""
    time_zone: str | None = None
    """IANA time zone for the account's allowance refill."""
    live_translation: bool | None = None
    """Project 694's optional listening capability, including on resume."""


class Settings(Message):
    """`spelling_hints` are for recognition only: never logged."""

    type: Literal["settings"] = "settings"
    spoken_language: str = "detect"
    targets: tuple[str, ...]
    second_languages: dict[str, str] = {}
    spelling_hints: tuple[str, ...] = Field(default=(), repr=False)
    translate_live: bool = True
    join_pause_fragments: bool = False


class Source(Message):
    """`targets`: the source's own target languages (the server's decision
    0033) - None leaves it out, so the session's `settings.targets` apply;
    empty: not translated ("Original only"). `spoken_language`: the
    language the source's speech is in, or "detect" (the server's decision
    0051) - None leaves it out, so the session's `settings.spoken_language`
    applies."""

    id: str
    category: Category
    targets: tuple[str, ...] | None = None
    spoken_language: str | None = None


class SpeechHeader(Message):
    """The JSON header of a binary speech frame."""

    type: Literal["speech"] = "speech"
    caption_id: str
    kind: Literal["live", "finished"]
    section: int | None = None
    source: Source
    speech_start: float
    speech_end: float
    replaces: tuple[str, ...] = ()
    codec: Literal["ogg_opus", "pcm_s16le"] = "ogg_opus"
    sample_rate: Literal[16000] = 16000
    cut_before: bool | None = None
    """The source's speech was cut at `speech_start` while it went on: no
    margin there (the server's decision 0058). None: left out (false)."""
    cut_after: bool | None = None
    """The speech goes on after `speech_end`: no margin there, and the
    caption's text is left open at its end. None: left out (false)."""
    seq: int | None = None
    """The app's number for this frame in the session: the answer's
    `trace` names it (the server's decision 0104; perf.trace)."""


class RecheckHeader(Message):
    """The JSON header of a binary recheck frame: a flagged line's speech,
    sent again to be checked on the best models (the server's decision
    0031). Its audio is the line's, as first sent: never logged."""

    type: Literal["recheck"] = "recheck"
    caption_id: str
    source: Source
    speech_start: float
    speech_end: float
    spoken_language: str = "detect"
    targets: tuple[str, ...]
    second_languages: dict[str, str] = {}
    codec: Literal["ogg_opus", "pcm_s16le"] = "ogg_opus"
    sample_rate: Literal[16000] = 16000


class Withdraw(Message):
    type: Literal["withdraw"] = "withdraw"
    caption_id: str
    reason: Literal["mic_bleed"] = "mic_bleed"


class Ping(Message):
    type: Literal["ping"] = "ping"


class LearningEvent(Message):
    """Entry IDs and times only - never the sentence around the word.
    `status` goes with kind `status`, and only there."""

    id: str
    kind: Literal["looked_up", "saved", "unsaved", "status"]
    entry_id: str
    at: str
    status: Status | None = None


class Learning(Message):
    type: Literal["learning"] = "learning"
    batch: str
    events: tuple[LearningEvent, ...]


class LearningSync(Message):
    """`since`: the last `learning_state`'s cursor, or None for everything
    (left out of the message, which the server reads as null)."""

    type: Literal["learning_sync"] = "learning_sync"
    since: str | None = None


class LearningDelete(Message):
    type: Literal["learning_delete"] = "learning_delete"


class ExposureDay(Message):
    """One finished UTC day's counts per entry ID: no times within the
    day, no order, no sentences, no app."""

    date: str
    counts: dict[str, int]


class Exposures(Message):
    type: Literal["exposures"] = "exposures"
    batch: str
    days: tuple[ExposureDay, ...]


class Agreement(Message):
    """The tester agreement accepted on this PC (since 2026-11-08,
    polyglotic-hq 185): its version and when."""

    version: str
    at: str


class Consent(Message):
    type: Literal["consent"] = "consent"
    id: str
    at: str
    usage: bool
    crashes: bool
    exposures: bool
    agreement: Agreement | None = None  # left out when None (an older choice)


class UsageEvent(Message):
    id: str
    name: str
    v: int
    at: str
    props: dict[str, UsageValue]


class Usage(Message):
    type: Literal["usage"] = "usage"
    batch: str
    events: tuple[UsageEvent, ...]


class RedeemRequest(Message):
    """`POST /v1/redeem`'s body."""

    invite_code: str = Field(repr=False)
    install_id: str
    app_version: str
    channel: Channel
    os: Os


FeedbackKind = Literal["problem", "suggestion", "question", "work_with_us"]


class FeedbackRequest(Message):
    """`POST /v1/feedback`'s body: the user's own words to us, kept out of
    `repr` like caption text (so is the reply address and the log)."""

    id: str
    at: str
    kind: FeedbackKind
    text: str = Field(repr=False, max_length=5000)
    reply_to: str | None = Field(default=None, repr=False, max_length=254)
    app_version: str
    os: Os
    os_version: str = Field(max_length=32)
    session_id: str | None = None
    log: str | None = Field(default=None, repr=False, max_length=512 * 1024)


class ReportCaption(Message):
    """A caption as the app showed it, in a problem report (protocol.md,
    Problem reports): caption text, kept out of `repr`."""

    caption_id: str
    source_id: str
    by_you: bool = False
    live: bool = False
    language: str | None = None
    started_at: str
    updated_at: str
    original: str = Field(repr=False, max_length=5000)
    translations: dict[str, str] = Field(default_factory=dict, repr=False)
    checked: bool = False


class ReportSpeech(Message):
    """One finished caption's audio, as sent for captioning: base64 Ogg Opus."""

    caption_id: str
    source_id: str
    category: Category
    speech_start: float
    speech_end: float
    codec: Literal["ogg_opus"] = "ogg_opus"
    data: str = Field(repr=False)


class ProblemReportRequest(Message):
    """`POST /v1/problem-reports`'s body (polyglotic-hq 275): what the tester
    left ticked. Everything they wrote or that was said is kept out of
    `repr`."""

    id: str
    at: str
    text: str = Field(default="", repr=False, max_length=5000)
    app_version: str
    os: Os
    os_version: str = Field(max_length=32)
    session_id: str | None = None
    log: str | None = Field(default=None, repr=False, max_length=512 * 1024)
    settings: dict[str, Any] | None = Field(default=None, repr=False)
    facts: dict[str, Any] | None = Field(default=None, repr=False)
    captions: list[ReportCaption] | None = Field(
        default=None, repr=False, max_length=500
    )
    speech: list[ReportSpeech] | None = Field(default=None, repr=False, max_length=500)


class ProblemReportResponse(Message):
    id: str


# --- From the server ---------------------------------------------------------


class FeedbackResponse(Message):
    """`POST /v1/feedback`'s answer: stored."""

    id: str


class Limits(Message):
    """The limits the app follows (protocol.md, "Limits"); defaults are
    version 1's values."""

    speech_frame_bytes: int = 262_144
    speech_header_bytes: int = 4096
    text_message_bytes: int = 65_536
    messages_per_second: int = 20
    targets: int = 2
    spelling_hints: int = 100
    spelling_hint_chars: int = 64
    learning_events: int = 500
    usage_events: int = 100
    speech_seconds_per_minute: int = 600
    ping_seconds: int = 25


class PlanNext(Message):
    """What happens to the plan at `at`: the tier then, and why."""

    at: str
    tier: str
    reason: str


class PlanMessage(Message):
    """The one billing line the server says the app may show, by code."""

    code: str
    at: str | None = None
    action: str | None = None


class PlanState(Message):
    """The account's plan as the server states it (protocol.md, `plan`;
    server decision 0039): the app shows it and never decides it. Codes are
    kept as strings - one this app doesn't know is shown as plainly as it
    can be, never refused (versioning rule 1)."""

    tier: str
    source: str
    status: str
    until: str | None = None
    next: PlanNext | None = None
    paid_at: str | None = None
    period: str | None = None
    free_minutes: float | None = None
    message: PlanMessage | None = None
    actions: tuple[str, ...] = ()


class LimitReached(Message):
    """Listening stops because the account's Plus ended (protocol.md,
    `limit_reached`; polyglotic-hq 193): at a listening `hello`, in place of
    `welcome`, or after the caption in flight - then close 4009. `plan`: the
    plan as it is now. Codes are kept as strings (versioning rule 1)."""

    type: Literal["limit_reached"] = "limit_reached"
    kind: str
    ended_at: str | None = None
    source: str | None = None
    reason: str | None = None
    action: str | None = None
    plan: PlanState | None = None


class Plan(PlanState):
    """The plan again, whenever it changes while a session is open."""

    type: Literal["plan"] = "plan"


class AllowanceUpdate(Message):
    type: Literal["allowance_update"] = "allowance_update"
    allowance_percent: int = Field(strict=True, ge=0, le=100)
    percent_left: int | None = Field(None, strict=True, ge=0, le=100)
    resets_at: datetime | None = None

    @property
    def left(self) -> int:
        """The percentage left: `percent_left` (the open beta's round 2),
        or the older `allowance_percent` from a server before it."""
        return (
            self.percent_left
            if self.percent_left is not None
            else self.allowance_percent
        )


class AllowanceExhausted(Message):
    type: Literal["allowance_exhausted"] = "allowance_exhausted"
    allowance_percent: Literal[0] = 0
    resets_at: datetime | None = None

    @property
    def left(self) -> int:
        return 0


class RegistrationRequired(Message):
    type: Literal["registration_required"] = "registration_required"


class CrossBorderConsentRequired(Message):
    type: Literal["cross_border_consent_required"] = "cross_border_consent_required"
    wording_version: str


class MaintenanceWindow(Message):
    """A planned maintenance window (server decision 0066): listening is
    refused from `starts_at` until `ends_at` - protocol.md's times, UTC."""

    starts_at: str
    ends_at: str


class Maintenance(Message):
    """The planned maintenance window was set, moved or cleared (None)
    while the session is open (servers of 2026-11-14 on; polyglotic-hq 319)."""

    type: Literal["maintenance"] = "maintenance"
    window: MaintenanceWindow | None = None


class Welcome(Message):
    type: Literal["welcome"] = "welcome"
    protocol: int
    server_version: str
    min_app_version: str
    session_id: str
    cohort: str
    channel: str
    features: dict[str, bool | int | str] = {}
    minutes_left: float | None = None
    limits: Limits = Limits()
    live_interval_min: float | None = None
    account_id: str | None = None  # from servers of 2026-11-05 on; opaque
    learning_epoch: str | None = None  # from servers of 2026-11-07 on (166); opaque
    resumed: bool = False  # `hello.resume` taken (servers of 2026-11-08 on)
    plan: PlanState | None = None  # from servers of 2026-11-08 on (178)
    # the optional `source` fields of a speech header the server uses (its
    # decision 0051); from servers of 2026-11-09 on (263) - none before
    source_fields: tuple[str, ...] = ()
    # the server's time, and the planned maintenance window that stands (its
    # decision 0066); from servers of 2026-11-14 on (319) - neither before
    server_time: str | None = None
    maintenance: MaintenanceWindow | None = None


class UpdateRequired(Message):
    type: Literal["update_required"] = "update_required"
    min_app_version: str


class AuthFailed(Message):
    type: Literal["auth_failed"] = "auth_failed"
    reason: str
    retry_after: int | None = None


class ServerBusy(Message):
    type: Literal["server_busy"] = "server_busy"
    retry_after: int
    # "maintenance": a planned window, ending at `until` - not a full server
    # (servers of 2026-11-14 on; polyglotic-hq 319)
    reason: str | None = None
    until: str | None = None


class TooManySessions(Message):
    type: Literal["too_many_sessions"] = "too_many_sessions"
    limit: int
    retry_after: int


class Pong(Message):
    type: Literal["pong"] = "pong"


class Pace(Message):
    """Live updates at most every `live_interval_min` seconds (None: as the
    user chose)."""

    type: Literal["pace"] = "pace"
    live_interval_min: float | None = None


class Link(Message):
    original: tuple[int, int]
    translation: tuple[int, int]
    key: bool
    confidence: float
    original_pos: str | None = None
    translation_pos: str | None = None


class WordTime(Message):
    """When a word of a clause's original was said (server decision 0099,
    this app's 0247): its span in the original, and `start` and `end` in
    seconds on this app's own clock - the one its speech frames'
    `speech_start` is on."""

    original: tuple[int, int]
    start: float
    end: float


class Clause(Message):
    original: str = Field(repr=False)
    translations: dict[str, str] = Field(default={}, repr=False)
    links: dict[str, tuple[Link, ...]] = {}
    # each translation's own language, keyed as `translations` (server
    # decision 0097; optional, additive - an older server sends none)
    written_in: dict[str, str] | None = None
    # when each word of `original` was said, in order (server decision
    # 0099; optional, additive - no server sends it yet). Read by nothing
    # yet: polyglotic-hq 526's spoken pace will (decision 0247)
    words: tuple[WordTime, ...] | None = Field(default=None, repr=False)


class UnansweredSpeech(Message):
    """A numbered live update the server won't answer, and why."""

    seq: int
    why: str


class UpdateTrace(Message):
    """Where an answer's server time went (the server's decision 0104):
    whole milliseconds, counts and the app's frame numbers only."""

    seq: int
    waited_ms: int = 0
    queued: int = 0
    stages_ms: dict[str, int] = {}
    server_ms: int = 0
    unanswered: tuple[UnansweredSpeech, ...] = ()


class CaptionUpdate(Message):
    """Carries caption text: never logged."""

    type: Literal["caption_update"] = "caption_update"
    caption_id: str
    source_id: str
    kind: Literal["live", "finished", "withdrawn"]
    reason: str | None = None
    language: str | None = None
    languages_heard: tuple[str, ...] | None = None
    clauses: tuple[Clause, ...] | None = None
    replaces: tuple[str, ...] | None = None
    continues: str | None = None
    processing_ms: int | None = None
    established: int | None = None
    """Live updates: characters of the clauses' originals, counted in order,
    the server says are established (polyglotic-server decision 0095)."""
    trace: UpdateTrace | None = None
    """For a frame the app numbered (`SpeechHeader.seq`), from a server
    since 2026-11-20: where its server time went (perf.trace)."""


class TranslatedClause(Message):
    translations: dict[str, str] = Field(repr=False)
    written_in: dict[str, str] = Field(default={}, repr=False)


class LiveTranslation(Message):
    type: Literal["live_translation"] = "live_translation"
    source_id: str
    caption_id: str
    seq: int
    clauses: tuple[TranslatedClause, ...] = Field(repr=False)


class RecheckResult(Message):
    """The answer to a recheck. `outcome` is kept as a string: one this app
    doesn't know is taken as a failure. Carries caption text: never logged."""

    type: Literal["recheck_result"] = "recheck_result"
    caption_id: str
    outcome: str
    language: str | None = None
    languages_heard: tuple[str, ...] | None = None
    clauses: tuple[Clause, ...] | None = None
    reason: str | None = None
    retry_after: int | None = None
    processing_ms: int | None = None


class Minutes(Message):
    type: Literal["minutes"] = "minutes"
    used: float
    left: float | None = None
    period: str = ""


class Notice(Message):
    type: Literal["notice"] = "notice"
    code: str


class Error(Message):
    """`caption_id` when it's about a speech frame, with `kind` - the
    frame's own, "live" or "finished" - from a server since 2026-11-11
    (its decision 0052; any other value is read as not said); `batch` when
    it's about a `usage` or `exposures` message (`consent_missing`, since
    S2b)."""

    type: Literal["error"] = "error"
    code: str
    fatal: bool = False
    caption_id: str | None = None
    kind: str | None = None

    batch: str | None = None
    retry_after: int | None = None


class Received(Message):
    """A `learning`, `exposures` or `usage` message is stored (`batch`), or
    a `consent` (`id`): the app can forget what it kept for it."""

    type: Literal["received"] = "received"
    batch: str | None = None
    id: str | None = None


class StatusState(Message):
    """`status` is kept as a string: one this app doesn't know is ignored."""

    entry_id: str
    status: str
    at: str


class SavedState(Message):
    entry_id: str
    saved: bool
    at: str


class DeletionState(Message):
    """The account's latest deletion of its learning data, from any of its
    devices: its number (from 1) and when, by the server's clock."""

    generation: int
    at: str


class LearningState(Message):
    """The answer to `learning_sync`: each entry changed since, once, in its
    current state; ask again with `cursor` while `more`. `deletion`: the
    account's latest deletion (None: never deleted, or an older server)."""

    type: Literal["learning_state"] = "learning_state"
    cursor: str
    more: bool = False
    statuses: tuple[StatusState, ...] = ()
    saved_words: tuple[SavedState, ...] = ()
    deletion: DeletionState | None = None


class LearningDeleted(Message):
    type: Literal["learning_deleted"] = "learning_deleted"


class RedeemResponse(Message):
    device_token: str = Field(repr=False)
    cohort: str


class HttpError(Message):
    error: str
    retry_after: int | None = None
    reason: str | None = None
    """Why, where the error has more than one cause the app tells apart:
    `subscription_ended` on `invite_code_not_valid` (server #252,
    polyglotic-hq 256). Unknown reasons are read as none."""


FROM_SERVER: dict[str, type[Message]] = {
    "welcome": Welcome,
    "update_required": UpdateRequired,
    "auth_failed": AuthFailed,
    "server_busy": ServerBusy,
    "too_many_sessions": TooManySessions,
    "pong": Pong,
    "pace": Pace,
    "caption_update": CaptionUpdate,
    "live_translation": LiveTranslation,
    "recheck_result": RecheckResult,
    "minutes": Minutes,
    "notice": Notice,
    "error": Error,
    "received": Received,
    "learning_state": LearningState,
    "learning_deleted": LearningDeleted,
    "plan": Plan,
    "limit_reached": LimitReached,
    "allowance_update": AllowanceUpdate,
    "allowance_exhausted": AllowanceExhausted,
    "registration_required": RegistrationRequired,
    "cross_border_consent_required": CrossBorderConsentRequired,
    "maintenance": Maintenance,
}
"""The server's messages this app reads; others are ignored (versioning
rule 1)."""


# --- Reading and writing -----------------------------------------------------


def dump(message: Message) -> dict[str, Any]:
    """A message as JSON-ready data, `type` first; fields that are None are
    left out (a finished caption's speech has no `section`)."""
    return message.model_dump(mode="json", exclude_none=True)


def encode(message: Message) -> str:
    """A message from the app, as a WebSocket text frame (or an HTTP body)."""
    return json.dumps(dump(message), ensure_ascii=False, separators=(",", ":"))


def decode(text: str | bytes) -> Message | None:
    """A text frame from the server as its message, or None if it's of a
    type this app doesn't read. Raises ProtocolError if it isn't a message,
    or a known type's fields aren't valid."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ProtocolError("a text frame that isn't JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        raise ProtocolError("a text frame without a message type")
    model = FROM_SERVER.get(data["type"])
    if model is None:
        return None
    return validate(model, data)


def validate[M: Message](model: type[M], data: object) -> M:
    """`data` as a `model`, or ProtocolError naming the fields that are wrong
    (never their values: they could be caption text or a token)."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        fields = sorted(
            {".".join(str(part) for part in e["loc"]) or "-" for e in error.errors()}
        )
        raise ProtocolError(
            f"{model.__name__} not valid: {', '.join(fields)}"
        ) from None


def speech_frame(header: SpeechHeader, audio: bytes) -> bytes:
    """A binary speech frame: the header's length (4 bytes, big-endian), the
    header as UTF-8 JSON, then the audio. Each frame stands alone."""
    encoded = encode(header).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded + audio


def recheck_frame(header: RecheckHeader, audio: bytes) -> bytes:
    """A binary recheck frame: a speech frame's shape, with a recheck's header."""
    encoded = encode(header).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded + audio


def read_speech_frame(frame: bytes) -> tuple[SpeechHeader, bytes]:
    """A speech frame's header and audio (the server's side; for tests and
    test servers)."""
    if len(frame) < 4:
        raise ProtocolError("a speech frame shorter than its length")
    length = int.from_bytes(frame[:4], "big")
    if not 0 < length <= len(frame) - 4:
        raise ProtocolError("a speech frame whose header length doesn't fit")
    header = validate(SpeechHeader, json.loads(frame[4 : 4 + length]))
    return header, frame[4 + length :]
