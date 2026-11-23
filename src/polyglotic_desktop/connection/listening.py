"""Listening's values to and from protocol messages.

Out: the timing rules' decisions (`core.listening.timing`) become speech
frames and `withdraw` messages; the user's `ListeningSettings` become
`settings`; a session's summary becomes the `listening_session_ended`
usage event's properties. In: `caption_update` becomes core's
`CaptionUpdate`. No caption rules here - only the translation between the
two vocabularies.

Each source's own target languages (the server's decision 0033) go on its
speech as `source.targets` - left out when they are the session's anyway,
so with today's one set of languages nothing changes on the wire - and
`settings.targets` carries every language any source uses, up to the
server's limit, so a server from before 2026-11-07, which ignores
`source.targets`, still translates each source into its languages. On
such a server a source set to "Original only" is translated all the same:
what the window shows is the interface's to choose.

Each source's own spoken language (the server's decision 0051) goes on its
speech as `source.spoken_language` - left out when it is the session's
anyway - and `settings.spoken_language` is the one language every source
names, or "detect" when they differ (core's `agreed_language`), so a
server from before 2026-11-09, which ignores the field, hears each source
as near its setting as one language allows. The
server says in `welcome.source_fields` whether it uses the field; the
caption windows say when it doesn't.

"Looks wrong?" (project 101): a `RecheckRequest` becomes a binary recheck
frame, `recheck_result` core's `RecheckResult`, and a closed comparison's
`LineFlagged` the `line_flagged` usage event's properties.
"""

from dataclasses import asdict, replace
from typing import Literal

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordClass,
    WordLink,
)
from polyglotic_desktop.core.listening.recheck import (
    LineFlagged,
    RecheckOutcome,
    RecheckRequest,
    RecheckResult,
)
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Capture, SourceId
from polyglotic_desktop.core.listening.summary import ListeningSessionEnded
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    Decision,
    TranscriptionRequest,
    WithdrawalReason,
    WithdrawCaption,
)
from polyglotic_desktop.perf.trace_summary import SessionTimelines, usage_properties
from polyglotic_desktop.ports.capture import SourceCategory

CODEC: Literal["ogg_opus"] = "ogg_opus"  # decision 0005: one Ogg Opus stream per frame


def session_targets(chosen: ListeningSettings, limit: int) -> tuple[Language, ...]:
    """The session's `settings.targets`: every language a source may be
    translated into (`all_targets`), at most `limit` (`welcome.limits.targets`)."""
    return chosen.all_targets[:limit]


def own_targets(
    chosen: ListeningSettings, source: SourceId, limit: int
) -> tuple[Language, ...] | None:
    """A source's `source.targets`: its languages (at most `limit`), or None
    when they are the session's anyway - the field left out, as before."""
    own = chosen.targets_of(source)[:limit]
    return None if own == session_targets(chosen, limit) else own


def own_spoken_language(chosen: ListeningSettings, source: SourceId) -> str | None:
    """A source's `source.spoken_language`: its own ("detect" for Detect),
    or None when it is the session's anyway - the field left out, as
    before."""
    own = chosen.spoken_language_of(source)
    if own == chosen.spoken_language:
        return None
    return own or "detect"


def speech_header(
    request: TranscriptionRequest,
    targets: tuple[Language, ...] | None = None,
    spoken_language: str | None = None,
    seq: int | None = None,
) -> protocol.SpeechHeader:
    """The header of the speech frame for a transcription request; `targets`
    its source's own target languages (`own_targets`), and `spoken_language`
    its own spoken language (`own_spoken_language`) - None to leave either
    out; `seq` the frame's number in the caption timelines (perf.trace)."""
    return protocol.SpeechHeader(
        caption_id=request.caption_id,
        kind=request.kind.value,
        section=request.section,
        source=protocol.Source(
            id=request.source.id,
            category=request.source.category.value,
            targets=targets,
            spoken_language=spoken_language,
        ),
        speech_start=round(request.speech_start, 3),
        speech_end=round(request.speech_end, 3),
        replaces=request.replaces,
        codec=CODEC,
        cut_before=request.cut_before or None,
        cut_after=request.cut_after or None,
        seq=seq,
    )


def withdraw(withdrawal: WithdrawCaption) -> protocol.Withdraw:
    """The app takes back a caption it decided was mic bleed."""
    if withdrawal.reason is not WithdrawalReason.MIC_BLEED:
        raise ValueError("the app withdraws captions only for mic bleed")
    return protocol.Withdraw(caption_id=withdrawal.caption_id)


def outgoing(
    decision: Decision,
    speech: bytes | None,
    chosen: ListeningSettings,
    limit: int,
    seq: int | None = None,
) -> bytes | str | None:
    """What to send for one of the timing rules' decisions: a binary speech
    frame - in its source's languages under `chosen`, at most `limit`,
    numbered `seq` - or a `withdraw` text message. None for a transcription
    request without audio (the source's buffer no longer had it)."""
    if isinstance(decision, WithdrawCaption):
        return protocol.encode(withdraw(decision))
    if speech is None:
        return None
    targets = own_targets(chosen, decision.source.id, limit)
    spoken = own_spoken_language(chosen, decision.source.id)
    return protocol.speech_frame(speech_header(decision, targets, spoken, seq), speech)


def settings(chosen: ListeningSettings, limit: int) -> protocol.Settings:
    """`settings`, with every source's languages as `targets`, at most
    `limit`, and second languages only for those (the server refuses
    others)."""
    targets = session_targets(chosen, limit)
    return protocol.Settings(
        spoken_language=chosen.spoken_language or "detect",
        targets=targets,
        second_languages={
            str(k): str(v) for k, v in chosen.second_languages.items() if k in targets
        },
        spelling_hints=chosen.spelling_hints,
        translate_live=chosen.translate_live,
        join_pause_fragments=True,
    )


SOURCE_SELECTED = "source_selected"
"""The tracking plan's event for the learner changing what to caption
(version 1; redefined for the new interface by polyglotic-hq project 134)."""


def source_selected(
    chosen: Capture, added: SourceCategory | None = None
) -> dict[str, protocol.UsageValue]:
    """The learner's choice as `source_selected`'s properties: the mode,
    how many apps are picked, whether their own speech is captioned, and
    the category of an app just added (never its name; left out if none
    was, or for categories an app isn't)."""
    props: dict[str, protocol.UsageValue] = {
        "capture_mode": chosen.mode.value,
        "apps": chosen.apps,
        "my_speech": chosen.my_speech,
    }
    if added is not None and added not in NOT_AN_APP:
        props["source_category"] = added.value
    return props


NOT_AN_APP = frozenset({SourceCategory.SYSTEM, SourceCategory.MIC})


SESSION_ENDED = "listening_session_ended"
"""The tracking plan's event for a session's summary (version 1)."""


NO_SOURCE = "none"
"""The tracking plan's `source_category` for a session with no captions."""


def session_ended(
    summary: ListeningSessionEnded, platform: str | None = None
) -> dict[str, protocol.UsageValue]:
    """A session's summary as `listening_session_ended`'s properties - the
    tracking plan's names and types; an optional one that's None is left
    out, and no source category is `none`. `platform`: the app's
    (`windows`), the plan's optional property since 051."""
    props: dict[str, protocol.UsageValue] = {}
    if platform is not None:
        props["platform"] = platform
    for name, value in asdict(summary).items():
        if name == "source_category" and value is None:
            props[name] = NO_SOURCE
        elif isinstance(value, SourceCategory):
            props[name] = value.value
        elif value is not None:
            props[name] = value
    return props


TIMELINE_SUMMARISED = "caption_timeline_summarised"
"""The tracking plan's event for where a listening session's caption time
went (version 1; polyglotic-hq 543): usage statistics, beside
`listening_session_ended`."""


def timeline_summarised(
    timelines: SessionTimelines,
    caption_mode: str | None,
    live_interval: float | None,
    platform: str | None = None,
) -> dict[str, protocol.UsageValue]:
    """A session's caption timelines as `caption_timeline_summarised`'s
    properties: whole milliseconds and counts (perf.trace_summary), the
    caption mode, the live-update interval and the session's length."""
    props: dict[str, protocol.UsageValue] = {
        "caption_mode": caption_mode or "steady",
        "listening_seconds": round(timelines.seconds(), 1),
    }
    if live_interval is not None:
        props["live_interval_seconds"] = live_interval
    if platform is not None:
        props["platform"] = platform
    props.update(usage_properties(timelines.summary, timelines.stalls()))
    return props


def caption_update(message: protocol.CaptionUpdate) -> CaptionUpdate:
    """A `caption_update` as core's caption update. A withdrawal reason this
    app doesn't know becomes None."""
    reason = None
    if message.reason is not None and message.reason in WithdrawalReason:
        reason = WithdrawalReason(message.reason)
    return CaptionUpdate(
        caption_id=CaptionId(message.caption_id),
        source_id=SourceId(message.source_id),
        kind=CaptionKind(message.kind),
        clauses=tuple(_clause(c) for c in message.clauses or ()),
        language=Language(message.language) if message.language else None,
        languages_heard=tuple(Language(x) for x in message.languages_heard or ()),
        replaces=tuple(CaptionId(c) for c in message.replaces or ()),
        continues=CaptionId(message.continues)
        if message.kind == "finished" and message.continues
        else None,
        reason=reason,
        processing_ms=message.processing_ms,
        established=max(0, message.established or 0) if message.kind == "live" else 0,
    )


class LiveTranslations:
    """Only a translation of the current original revision can enter a window."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._waiting: dict[tuple[str, str], tuple[int, CaptionUpdate]] = {}

    def original(self, update: CaptionUpdate, seq: int | None) -> None:
        source = update.source_id
        for gone in (*update.replaces, update.caption_id):
            self._waiting.pop((source, gone), None)
        if update.kind is CaptionKind.LIVE and seq is not None:
            self._waiting[source, update.caption_id] = seq, update
            if len(self._waiting) > self._limit:
                del self._waiting[next(iter(self._waiting))]

    def translated(self, message: protocol.LiveTranslation) -> CaptionUpdate | None:
        key = (message.source_id, message.caption_id)
        waiting = self._waiting.get(key)
        if waiting is None or waiting[0] != message.seq:
            return None
        original = waiting[1]
        if len(original.clauses) != len(message.clauses):
            return None
        del self._waiting[key]
        clauses = tuple(
            replace(
                source,
                translations={Language(k): v for k, v in target.translations.items()},
                written_in={
                    Language(k): Language(v) for k, v in target.written_in.items()
                },
                links={},
            )
            for source, target in zip(original.clauses, message.clauses, strict=True)
        )
        # Only the original measures speech latency. The translation changes
        # that caption in place without advancing the speech timeline twice.
        return replace(original, clauses=clauses, times=None)


def _word_class(value: str | None) -> WordClass | None:
    if value is None:
        return None
    try:
        return WordClass(value)
    except ValueError:
        return None


def _clause(clause: protocol.Clause) -> Clause:
    return Clause(
        original=clause.original,
        translations={Language(k): v for k, v in clause.translations.items()},
        links={
            Language(k): tuple(
                WordLink(
                    link.original,
                    link.translation,
                    link.key,
                    link.confidence,
                    _word_class(link.original_pos),
                    _word_class(link.translation_pos),
                )
                for link in links
            )
            for k, links in clause.links.items()
        },
        written_in={
            Language(k): Language(v) for k, v in (clause.written_in or {}).items()
        },
    )


def recheck_header(request: RecheckRequest) -> protocol.RecheckHeader:
    """The header of a recheck frame: the line's caption id, source and
    speech times as first sent, and the languages to check it in - with
    second languages only for those (the server refuses others)."""
    return protocol.RecheckHeader(
        caption_id=request.caption_id,
        source=protocol.Source(
            id=request.source.id, category=request.source.category.value
        ),
        speech_start=round(request.speech_start, 3),
        speech_end=round(request.speech_end, 3),
        spoken_language=request.spoken_language or "detect",
        targets=request.targets,
        second_languages={
            str(k): str(v)
            for k, v in request.second_languages.items()
            if k in request.targets
        },
        codec=CODEC,
    )


def recheck_frame(request: RecheckRequest) -> bytes:
    return protocol.recheck_frame(recheck_header(request), request.audio)


_FROM_SERVER = {
    RecheckOutcome.CHECKED,
    RecheckOutcome.BEST_UNAVAILABLE,
    RecheckOutcome.TRY_LATER,
    RecheckOutcome.FAILED,
}


def recheck_result(message: protocol.RecheckResult) -> RecheckResult:
    """A `recheck_result` as core's. An outcome this app doesn't know from
    the server is a failure (versioning rule 1)."""
    outcome = RecheckOutcome.FAILED
    if message.outcome in _FROM_SERVER:
        outcome = RecheckOutcome(message.outcome)
    checked = outcome is RecheckOutcome.CHECKED
    return RecheckResult(
        caption_id=CaptionId(message.caption_id),
        outcome=outcome,
        clauses=tuple(_clause(c) for c in message.clauses or ()) if checked else (),
        language=Language(message.language) if message.language else None,
        languages_heard=tuple(Language(x) for x in message.languages_heard or ()),
        retry_after=message.retry_after,
        processing_ms=message.processing_ms,
    )


LINE_FLAGGED = "line_flagged"
"""The tracking plan's event for a closed comparison (version 1)."""


def line_flagged(flagged: LineFlagged) -> dict[str, protocol.UsageValue]:
    """A closed comparison as `line_flagged`'s properties: no answer is
    `none`; no source category (the audio wasn't held) is left out."""
    props: dict[str, protocol.UsageValue] = {
        "language": str(flagged.language),
        "outcome": flagged.outcome.value,
        "answer": flagged.answer.value if flagged.answer else "none",
    }
    if flagged.source_category is not None:
        props["source_category"] = flagged.source_category.value
    return props
