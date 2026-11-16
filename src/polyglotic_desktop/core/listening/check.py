"""The "no captions?" check: five links from the connection to captions on screen.

Help's check (project 096; 087's wireframe 5.2) walks the chain in order
and stops at the first broken link, naming its likely fix:

1. signed in and connected;
2. something is ticked to caption (an app, everything the PC plays, the mic);
3. sound from it in the last 30 seconds - or, at once, that the OS doesn't
   allow the app to hear it (macOS' permissions: polyglotic-hq 411);
4. speech heard in that sound;
5. captions drawn - and not failing on the server (`failing`: several
   finished captions in a row answered `processing_failed`, as the caption
   windows and Home say; polyglotic-hq 184 saw five ticks beside "Captions
   failing on the server").

Every link is a fact the app already has - the connection's state, what is
ticked, when sound and speech were last heard per source, when a caption
was last drawn. None needs the server. This module is the rule, pure: it
takes the facts and returns each link's status and problem as codes; the
view words them. `summary` is what "Report a problem" attaches: ticks and
crosses and the kind of problem, never an app's name or any content.

Waiting to try again, the first link says why the server can't be reached
when that's known - as Home does (`core.listening.unreachable`;
polyglotic-hq 251) - and a full server says it's busy: the check said
"Connecting to the server..." for every cause, and "Not connected - quit
and start again" for a busy server, which comes back by itself.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.unreachable import Unreachable

SOUND_WINDOW = 30.0
"""Seconds: sound or speech older than this no longer counts as "now"."""
CAPTION_WINDOW = 60.0
"""Seconds: a caption drawn within this long ago counts as captions working."""
SPEECH_GRACE = 10.0
"""Seconds a caption may be on its way after speech was last heard."""


class Step(StrEnum):
    CONNECTED = "connected"
    TICKED = "ticked"
    SOUND = "sound"
    SPEECH = "speech"
    CAPTIONS = "captions"


class Status(StrEnum):
    OK = "ok"
    BROKEN = "broken"
    WAITING = "waiting"  # not known yet, or not checked: an earlier link comes first


class Problem(StrEnum):
    SIGN_IN_NEEDED = "sign_in_needed"
    UPDATE_NEEDED = "update_needed"
    PLUS_ENDED = "plus_ended"  # the server closed listening: Plus ended (185)
    NOT_CONNECTED = "not_connected"
    SERVER_UNREACHABLE = "server_unreachable"  # why: the link's `cause` (251)
    SERVER_BUSY = "server_busy"  # full: it tries again by itself (208, 251)
    NOTHING_TICKED = "nothing_ticked"
    APP_NOT_OPEN = "app_not_open"
    APP_QUIET = "app_quiet"
    SYSTEM_QUIET = "system_quiet"
    MIC_QUIET = "mic_quiet"
    SOUND_NOT_ALLOWED = "sound_not_allowed"  # the Mac's permission (411)
    MIC_NOT_ALLOWED = "mic_not_allowed"
    NO_SPEECH = "no_speech"
    PAUSED = "paused"
    OVERLAYS_HIDDEN = "overlays_hidden"
    NO_CAPTIONS = "no_captions"
    SERVER_FAILING = "server_failing"


@dataclass(frozen=True)
class Ticked:
    """A source chosen to caption: its id, its name for the learner's eyes
    (it stays on this PC) and what kind it is."""

    id: SourceId
    name: str
    kind: Literal["app", "system", "mic"]


@dataclass(frozen=True)
class SourceActivity:
    """What a source being captured has done, in monotonic seconds: when it
    started, and when sound and speech were first and last heard.
    `not_allowed`: its capture gets only silence because the learner hasn't
    allowed the app to hear it (`ports.capture.NOT_ALLOWED`: macOS'
    permissions, polyglotic-hq 411)."""

    started: float
    first_sound: float | None = None
    last_sound: float | None = None
    last_speech: float | None = None
    not_allowed: bool = False


@dataclass(frozen=True)
class Facts:
    now: float
    connection: str
    """A `ConnectionState` value: listening, connecting, waiting,
    server_busy, sign_in_needed, update_needed, plus_ended, moved,
    not_connected or stopped."""
    paused: bool
    overlays_hidden: bool
    ticked: Sequence[Ticked]
    activity: Mapping[SourceId, SourceActivity]
    last_caption: float | None
    """When a caption was last drawn, or None if none has been."""
    failing: bool = False
    """Captions are failing on the server now (`core.listening.failing`)."""
    unreachable: Unreachable | None = None
    """Waiting to try again: why the server can't be reached, if known."""


@dataclass(frozen=True)
class Link:
    step: Step
    status: Status
    problem: Problem | None = None
    source: str | None = None
    """The source the link is about, by name (on this PC only)."""
    cause: Unreachable | None = None
    """`SERVER_UNREACHABLE`: why the server can't be reached."""


def _within(now: float, then: float | None, seconds: float) -> bool:
    return then is not None and now - then <= seconds


def run_check(facts: Facts) -> tuple[Link, ...]:
    """Every link's status: the first one not OK says what is wrong, and
    those after it wait."""
    checks = (
        _connected,
        _ticked,
        _sound,
        _speech,
        _captions,
    )
    links: list[Link] = []
    for step, check in zip(Step, checks, strict=True):
        if links and links[-1].status is not Status.OK:
            links.append(Link(step, Status.WAITING))
        else:
            links.append(check(facts))
    return tuple(links)


def _connected(facts: Facts) -> Link:
    state = facts.connection
    if state == "listening":
        return Link(Step.CONNECTED, Status.OK)
    if state == "waiting" and facts.unreachable is not None:
        return Link(
            Step.CONNECTED,
            Status.BROKEN,
            Problem.SERVER_UNREACHABLE,
            cause=facts.unreachable,
        )
    if state == "server_busy":
        return Link(Step.CONNECTED, Status.BROKEN, Problem.SERVER_BUSY)
    if state in ("connecting", "waiting"):
        return Link(Step.CONNECTED, Status.WAITING)
    problem = {
        "sign_in_needed": Problem.SIGN_IN_NEEDED,
        "update_needed": Problem.UPDATE_NEEDED,
        "plus_ended": Problem.PLUS_ENDED,
    }.get(state, Problem.NOT_CONNECTED)
    return Link(Step.CONNECTED, Status.BROKEN, problem)


def _ticked(facts: Facts) -> Link:
    if facts.ticked:
        return Link(Step.TICKED, Status.OK, source=facts.ticked[0].name)
    return Link(Step.TICKED, Status.BROKEN, Problem.NOTHING_TICKED)


def _heard(facts: Facts, speech: bool) -> list[tuple[Ticked, SourceActivity]]:
    found = []
    for source in facts.ticked:
        act = facts.activity.get(source.id)
        if act is None:
            continue
        if _within(
            facts.now, act.last_speech if speech else act.last_sound, SOUND_WINDOW
        ):
            found.append((source, act))
    return found


def _sound(facts: Facts) -> Link:
    heard = _heard(facts, speech=False)
    if heard:
        return Link(Step.SOUND, Status.OK, source=heard[0][0].name)
    for source in facts.ticked:  # no waiting: it won't hear anything until allowed
        act = facts.activity.get(source.id)
        if act is not None and act.not_allowed:
            problem = (
                Problem.MIC_NOT_ALLOWED
                if source.kind == "mic"
                else Problem.SOUND_NOT_ALLOWED
            )
            return Link(Step.SOUND, Status.BROKEN, problem, source.name)
    for source in facts.ticked:
        act = facts.activity.get(source.id)
        if act is not None and facts.now - act.started < SOUND_WINDOW:
            return Link(Step.SOUND, Status.WAITING, source=source.name)
    source = facts.ticked[0]
    if facts.activity.get(source.id) is None and source.kind == "app":
        problem = Problem.APP_NOT_OPEN
    else:
        problem = {
            "app": Problem.APP_QUIET,
            "system": Problem.SYSTEM_QUIET,
            "mic": Problem.MIC_QUIET,
        }[source.kind]
    return Link(Step.SOUND, Status.BROKEN, problem, source.name)


def _speech(facts: Facts) -> Link:
    spoken = _heard(facts, speech=True)
    if spoken:
        return Link(Step.SPEECH, Status.OK, source=spoken[0][0].name)
    for source, act in _heard(facts, speech=False):
        if act.first_sound is not None and facts.now - act.first_sound < SOUND_WINDOW:
            return Link(Step.SPEECH, Status.WAITING, source=source.name)
    return Link(Step.SPEECH, Status.BROKEN, Problem.NO_SPEECH)


def _captions(facts: Facts) -> Link:
    if facts.failing:  # a caption drawn a minute ago isn't captions working
        return Link(Step.CAPTIONS, Status.BROKEN, Problem.SERVER_FAILING)
    if _within(facts.now, facts.last_caption, CAPTION_WINDOW):
        return Link(Step.CAPTIONS, Status.OK)
    latest = max(
        (a.last_speech for _, a in _heard(facts, speech=True) if a.last_speech),
        default=None,
    )
    if _within(facts.now, latest, SPEECH_GRACE):
        return Link(Step.CAPTIONS, Status.WAITING)
    if facts.paused:
        problem = Problem.PAUSED
    elif facts.overlays_hidden:
        problem = Problem.OVERLAYS_HIDDEN
    else:
        problem = Problem.NO_CAPTIONS
    return Link(Step.CAPTIONS, Status.BROKEN, problem)


def summary(links: Sequence[Link]) -> str:
    """The check's result as plain lines, for a report: each link's step
    and status, and the kind of problem. No names, no content."""
    lines = []
    for link in links:
        line = f"{link.step.value}: {link.status.value}"
        if link.problem is not None:
            cause = f": {link.cause.value}" if link.cause is not None else ""
            line += f" ({link.problem.value}{cause})"
        lines.append(line)
    return "\n".join(lines)
