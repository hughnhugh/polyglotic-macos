"""Each caption's delay, and the caption log's lines: where a caption's time went.

polyglotic-hq 271 (the user, 2026-11-10: "Make there a way to measure /
display how long each translation takes. Total MS from speech start/finish
to server processing"; "Make sure the app has server / client logs that
you can analyse"). Two uses of the same times:

- **A caption's delay** (`CaptionDelay`): from the start and from the end
  of its speech to the moment it's shown, and the server's share - what
  the caption windows show under a caption when the learner asks
  (`show_delay`, off by default).
- **The caption log** (`line`): one line per caption event - speech sent,
  its answer, shown, dropped and why - under the caption's id, which the
  server's caption log (`polyglotic_server.captions`) uses too. Written
  by whoever sees the event (the session, the caption feed) to the logger
  `CAPTION_LOG`; `main` gives it a file of its own.

**Content-free.** A line holds the caption's id (random), the event, the
speech's kind and live section, the source's category, the caption mode,
seconds of audio, bytes, counts of characters and clauses, and
milliseconds. Never caption text, audio, an app's name or a source's id.

Times are seconds on the app's monotonic clock, the speech times' own;
nothing here reads it.
"""

from dataclasses import dataclass

from polyglotic_desktop.core.listening.captions import CaptionUpdate, SpeechTimes

CAPTION_LOG = "polyglotic_desktop.captions"
"""The caption log's logger."""


@dataclass(frozen=True, slots=True)
class CaptionDelay:
    """How long a caption update took to show, in seconds: from its
    speech's start and end, and the server's share of it (None: the server
    didn't say)."""

    from_start: float
    from_end: float
    server: float | None


def delay(update: CaptionUpdate, shown: float) -> CaptionDelay | None:
    """The delay of `update`, shown at `shown` - None when its speech's
    times aren't known (an update this session didn't send the speech of)."""
    times = update.times
    if times is None:
        return None
    server = None if update.processing_ms is None else update.processing_ms / 1000
    return CaptionDelay(shown - times.speech_start, shown - times.speech_end, server)


def milliseconds(seconds: float) -> int:
    return round(seconds * 1000)


def line(event: str, caption_id: str, **fields: object) -> str:
    """A caption log line: `caption <event> id=<id>` then each field given,
    in order, as `name=value`; a field that's None is left out."""
    said = [f"{name}={value}" for name, value in fields.items() if value is not None]
    return " ".join(["caption", event, f"id={caption_id}", *said])


def answered_fields(
    update: CaptionUpdate, times: SpeechTimes | None
) -> dict[str, object]:
    """An answer's sizes and times for the log: counts and milliseconds only."""
    fields: dict[str, object] = {"kind": update.kind.value}
    if update.reason is not None:
        fields["reason"] = update.reason.value
    if update.clauses:
        fields["chars"] = sum(len(clause.original) for clause in update.clauses)
        fields["clauses"] = len(update.clauses)
        fields["translated"] = sum(1 for c in update.clauses if c.translations)
    fields["server_ms"] = update.processing_ms
    if times is not None:
        fields["round_trip_ms"] = milliseconds(times.received - times.sent)
        fields["since_end_ms"] = milliseconds(times.received - times.speech_end)
        fields["since_start_ms"] = milliseconds(times.received - times.speech_start)
    return fields
