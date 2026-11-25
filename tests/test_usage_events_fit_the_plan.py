"""Every usage event the app can send fits polyglotic-server's tracking plan (decision 0271).

The server keeps a usage event only if its name, version, every property
and every value are in its tracking plan (`docs/tracking-plan.yaml`); one
that isn't is dropped whole. Steady's and Calm's session summaries were
dropped that way after desktop decision 0246 renamed the caption modes,
and nothing here noticed (polyglotic-hq 556, 562). So this lists every
property and value the app can send - from its own enums and builders,
not by hand - and checks them against a copy of the server's plan
(`tests/tracking_plan/`, kept by `tools/tracking_plan.py`, as
`tools/protocol_examples.py` keeps the protocol examples).

A gap the server is closing in an open pull request waits in
`WAITING_FOR_THE_SERVER`, named by that pull request; refresh the copy once
it has merged, and the test says which to take out.
"""

import dataclasses
import json
import re
import typing
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import yaml
from tests.test_exchange import Heard
from tools.protocol_examples import digest
from tools.tracking_plan import MANIFEST, PLAN, read_manifest

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import USAGE, DataExchange
from polyglotic_desktop.connection.milestones import Milestones
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.recheck import Answer, FlagOutcome, LineFlagged
from polyglotic_desktop.core.listening.sources import (
    Capture,
    CaptureMode,
    known_app_id,
)
from polyglotic_desktop.core.listening.spoken import SPOKEN_LANGUAGES
from polyglotic_desktop.core.listening.summary import ListeningSessionEnded
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.perf.trace import Tracer
from polyglotic_desktop.perf.trace_summary import (
    HANG_CAUSES,
    SEGMENTS,
    Hang,
    SessionTimelines,
)
from polyglotic_desktop.platform.macos import categories as mac_categories
from polyglotic_desktop.platform.windows import categories as windows_categories
from polyglotic_desktop.ports.capture import SourceCategory

Props = dict[str, protocol.UsageValue]
Sent = tuple[str, Props]

WAITING_FOR_THE_SERVER: dict[str, str] = {
    "listening_session_ended.pace_them_mean isn't in the tracking plan": "server follow-up 828",
    "listening_session_ended.pace_them_peak isn't in the tracking plan": "server follow-up 828",
    **{
        f"listening_session_ended.pace_them_seconds_{band} isn't in the tracking plan": "server follow-up 828"
        for band in ("1_60", "61_120", "121_180", "181_240", "241_plus")
    },
    "listening_session_ended.pace_you_mean isn't in the tracking plan": "server follow-up 828",
    "listening_session_ended.pace_you_peak isn't in the tracking plan": "server follow-up 828",
    **{
        f"listening_session_ended.pace_you_seconds_{band} isn't in the tracking plan": "server follow-up 828"
        for band in ("1_60", "61_120", "121_180", "181_240", "241_plus")
    },
}
"""What the app sends that the copy of the plan doesn't take yet, and the
server pull request that adds it: each is dropped by a server without it."""

AT = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
OSES = ("windows-10", "windows-11", "macos-26")
"""`AppInfo.os` as the app can say it: Windows' two, and a Mac's form."""


# -- the plan, and the server's check of it -----------------------------------------


def plan() -> dict[str, Any]:
    events: dict[str, Any] = yaml.safe_load(PLAN.read_text(encoding="utf-8"))["events"]
    return events


# polyglotic-server's core/usage/tracking.py, `PlannedProperty.fits`
_PATTERNS = {
    "version": r"^\d+\.\d+\.\d+([.+-][0-9A-Za-z.-]+)?$",
    "language_code": r"^[a-z]{2,3}(-[a-z0-9]{2,8})*$",
    "country_code": r"^[A-Z][A-Z0-9]$",
    "os": r"^(windows|macos|linux|android|ios)-[1-9][0-9]{0,2}$",
    "channel": r"^(win|macos|linux|android|ios)-[a-z0-9]{2,12}-(alpha|beta|stable)$",
}


def fits(planned: dict[str, Any], value: object) -> bool:
    """Whether the server's check keeps `value` for a property planned so."""
    kind = planned["type"]
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "enum":
        return value in planned.get("values", ())
    if kind == "uuid":
        try:
            uuid.UUID(str(value))
        except ValueError:
            return False
        return isinstance(value, str)
    if kind in _PATTERNS:
        return isinstance(value, str) and re.match(_PATTERNS[kind], value) is not None
    raise AssertionError(f"a type this check doesn't know: {kind} (add it here)")


def problems(sent: list[Sent], v: int) -> set[str]:
    """What the server's check would refuse in what the app can send, as
    `problems()` in the server's core says it, one line each."""
    planned = plan()
    found: set[str] = set()
    for name, props in sent:
        event = planned.get(name)
        if event is None:
            found.add(f"{name} isn't in the tracking plan")
            continue
        if (event["v"], event["kind"], event["sent_by"]) != (v, "usage", "app"):
            found.add(f"{name} isn't a version {v} usage event sent by the app")
        properties: dict[str, Any] = event["properties"]
        for prop, value in props.items():
            if prop not in properties:
                found.add(f"{name}.{prop} isn't in the tracking plan")
            elif not fits(properties[prop], value):
                found.add(f"{name}.{prop} refuses {value!r}")
        for prop, spec in properties.items():
            if spec.get("required", True) and prop not in props:
                found.add(f"{name}.{prop} is required and missing")
    return found


# -- what the app can send, from its own enums and builders --------------------------


def _platforms() -> list[str]:
    return sorted({AppInfo("0.1.0", os).platform for os in OSES})


SUMMARY_VALUES: dict[str, list[Any]] = {
    "source_category": [*SourceCategory, None],
    "caption_mode": [m.usage_value for m in CaptionMode],
    "capture_mode": [m.value for m in CaptureMode],
    "known_app": sorted(
        {
            known_app_id(name)
            for name in windows_categories.known_names() | mac_categories.known_names()
        }
    ),
}
"""`ListeningSessionEnded`'s text fields and where their values come from."""

_SAMPLES: dict[type, Any] = {int: 3, float: 1.5, bool: True}


def _summary_fields() -> dict[str, list[Any]]:
    """Each of the summary's fields, and every value of it to send."""
    hints = typing.get_type_hints(ListeningSessionEnded)
    values: dict[str, list[Any]] = {}
    for field in dataclasses.fields(ListeningSessionEnded):
        if field.name in SUMMARY_VALUES:
            values[field.name] = SUMMARY_VALUES[field.name]
            continue
        kinds = [k for k in typing.get_args(hints[field.name]) if k is not type(None)]
        kind = kinds[0] if kinds else hints[field.name]
        assert kind in _SAMPLES, (
            f"ListeningSessionEnded.{field.name}: a {kind} with no fixed list here"
            " - add where its values come from to SUMMARY_VALUES"
        )
        values[field.name] = [_SAMPLES[kind]]
    return values


def session_summaries() -> Iterator[Sent]:
    fields = _summary_fields()
    full = ListeningSessionEnded(**{name: v[0] for name, v in fields.items()})
    for platform in _platforms():
        yield listening.SESSION_ENDED, listening.session_ended(full, platform)
    for name, values in fields.items():
        for value in values:
            yield (
                listening.SESSION_ENDED,
                listening.session_ended(replace(full, **{name: value})),
            )
    hints = typing.get_type_hints(ListeningSessionEnded)
    nothing: dict[str, Any] = {  # every field that can be None, None: left out
        name: None
        for name, hint in hints.items()
        if type(None) in typing.get_args(hint)
    }
    yield listening.SESSION_ENDED, listening.session_ended(replace(full, **nothing))


def timelines() -> Iterator[Sent]:
    """`caption_timeline_summarised` as the session builds it, from a
    summary with every segment, hang cause and hold - and as the client
    sends it, with the platform."""
    tracer = Tracer(clock=lambda: 100.0)
    found = SessionTimelines(tracer)
    found.started, found.stopped = 10.0, 100.0
    summary = found.summary
    summary.updates = summary.shown = 10
    for segment in (*SEGMENTS, "total"):
        summary.by_segment[segment] = [120.0, 340.0]
    summary.hangs = [Hang(1.0, 2.5, "app-1", cause, 1) for cause in HANG_CAUSES]
    summary.held.update({"mouse": 2, "gap": 1})
    for mode in [*(m.usage_value for m in CaptionMode), None]:
        for interval in (1.5, None):
            for platform in _platforms():
                props = listening.timeline_summarised(found, mode, interval)
                props["platform"] = platform  # as the client adds it
                yield listening.TIMELINE_SUMMARISED, props


def sources_selected() -> Iterator[Sent]:
    for mode in CaptureMode:
        for added in [*SourceCategory, None]:
            chosen = Capture(mode, apps=2, my_speech=True)
            yield listening.SOURCE_SELECTED, listening.source_selected(chosen, added)


def lines_flagged() -> Iterator[Sent]:
    base = LineFlagged(Language("zh"), SourceCategory.VIDEO, FlagOutcome.SAME, None)
    variants = [
        *(replace(base, language=language) for language in SPOKEN_LANGUAGES),
        *(replace(base, source_category=c) for c in [*SourceCategory, None]),
        *(replace(base, outcome=outcome) for outcome in FlagOutcome),
        *(replace(base, answer=answer) for answer in [*Answer, None]),
    ]
    for flagged in variants:
        yield listening.LINE_FLAGGED, listening.line_flagged(flagged)


def _usage_sent(outbox: SqliteOutbox) -> list[tuple[str, int, Props]]:
    found = []
    for item in outbox.waiting():
        if item.kind == USAGE:
            event = json.loads(item.body)
            found.append((event["name"], event["v"], event["props"]))
    return found


def _exchange() -> tuple[SqliteOutbox, DataExchange]:
    outbox = SqliteOutbox(":memory:")
    exchange = DataExchange(outbox, outbox, Heard(), "cedict")
    exchange.choose_consent(usage=True, crashes=False, exposures=False)
    return outbox, exchange


def milestones() -> Iterator[tuple[str, int, Props]]:
    """The install's milestones as the app sends them - through the
    exchange, as the outbox keeps them - on every channel and OS."""
    channels = typing.get_args(protocol.Channel)
    for os in OSES:
        for channel in channels:
            outbox, exchange = _exchange()
            first = Milestones(outbox, exchange, AppInfo("0.1.10", os, channel))
            first.started(fresh=True)
            first.caption_shown()
            later = Milestones(outbox, exchange, AppInfo("0.1.11", os, channel))
            later.started(fresh=False)
            yield from _usage_sent(outbox)


def feature_suggestions() -> Iterator[Sent]:
    """The successful-send callback's event, as the consent-aware exchange keeps it."""
    outbox, exchange = _exchange()
    exchange.usage("feature_suggested", {}, AT)
    for name, _version, props in _usage_sent(outbox):
        yield name, props


def built() -> list[Sent]:
    return [
        *session_summaries(),
        *timelines(),
        *sources_selected(),
        *lines_flagged(),
        *feature_suggestions(),
    ]


def exchange_version() -> int:
    """The version the exchange sends a usage event with."""
    outbox, exchange = _exchange()
    exchange.usage(listening.SOURCE_SELECTED, {}, AT)
    ((_, v, _),) = _usage_sent(outbox)
    return v


# -- the tests ------------------------------------------------------------------------


def test_a_feature_suggestion_count_keeps_the_usage_consent_gate() -> None:
    """The count never enters the outbox before the learner allows usage statistics."""
    outbox = SqliteOutbox(":memory:")
    exchange = DataExchange(outbox, outbox, Heard(), "cedict")
    exchange.usage("feature_suggested", {}, AT)
    assert _usage_sent(outbox) == []


def test_the_copy_of_the_plan_is_the_one_its_manifest_names() -> None:
    """Changed only by `tools/tracking_plan.py` (decision 0271)."""
    commit, sha = read_manifest()
    assert re.fullmatch(r"[0-9a-f]{40}", commit), MANIFEST
    assert digest(PLAN.read_bytes()) == sha, "run tools/tracking_plan.py copy"


def test_every_event_the_app_can_send_fits_the_plan() -> None:
    """Every property and value the builders make, and the milestones as
    the outbox keeps them: none the server would drop, beyond what waits
    for a server pull request."""
    v = exchange_version()
    sent = built()
    found = problems(sent, v)
    for name, version, props in milestones():
        found |= problems([(name, props)], version)
    new = sorted(found - WAITING_FOR_THE_SERVER.keys())
    assert new == [], "the server would drop these events whole: " + "; ".join(new)


def test_what_waits_for_the_server_still_waits() -> None:
    """A gap the refreshed copy closed is taken out of the list, so the
    list stays what still waits."""
    found = problems(built(), exchange_version())
    closed = sorted(WAITING_FOR_THE_SERVER.keys() - found)
    assert closed == [], "now in the plan - take them out: " + "; ".join(closed)


def test_the_check_refuses_what_the_server_refuses() -> None:
    """The check here is the server's: an unknown event, an unknown
    property, a value off its list, a wrong type and a missing property
    are each refused."""
    good = listening.source_selected(Capture(CaptureMode.APPS, 1, False))
    assert problems([(listening.SOURCE_SELECTED, good)], 1) == set()
    assert problems([("caption_text_sent", {})], 1)
    assert problems([(listening.SOURCE_SELECTED, {**good, "app_name": 1})], 1)
    assert problems([(listening.SOURCE_SELECTED, {**good, "capture_mode": "x"})], 1)
    assert problems([(listening.SOURCE_SELECTED, {**good, "apps": 1.5})], 1)
    assert problems([(listening.SOURCE_SELECTED, {**good, "apps": True})], 1)
    missing = {k: v for k, v in good.items() if k != "apps"}
    assert problems([(listening.SOURCE_SELECTED, missing)], 1)
    assert problems([(listening.SOURCE_SELECTED, good)], 2), "another version"


def test_the_summarys_text_fields_each_have_a_fixed_list() -> None:
    """A new text field in the summary has to say where its values come
    from, or this check couldn't list them (`SUMMARY_VALUES`)."""
    fields = _summary_fields()
    assert {"caption_mode", "known_app", "source_category"} <= fields.keys()
    assert "discord" in fields["known_app"]
