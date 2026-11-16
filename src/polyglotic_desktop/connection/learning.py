"""Learning's values to and from protocol messages.

Out: Learning's published events (`core.shared`'s `LearningEvent`s - entry
IDs and times) become `learning` events, each with an id of its own so the
server can ignore one it already has. In: a `learning_state` becomes the
same core events, for Learning to apply - a status as `WordStatusChanged`,
a saved word as `WordSaved` or `WordUnsaved` - for the entries of the
learning data's own dictionary only (an entry ID's dictionary is before
its colon; the other language's entries stay on the server for a PC
learning it). Daily exposure counts become `exposures` days. No learning
rules here - only the translation between the two vocabularies.
"""

from collections.abc import Mapping
from datetime import date
from typing import Literal

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.core.shared import (
    EntryId,
    LearningEvent,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
    WordUnsaved,
)


def learning_event(event: LearningEvent, event_id: str) -> protocol.LearningEvent:
    """One of Learning's events as a `learning` event with id `event_id`."""
    at = protocol.at(event.at)
    if isinstance(event, WordStatusChanged):
        return protocol.LearningEvent(
            id=event_id,
            kind="status",
            entry_id=event.entry_id,
            at=at,
            status=event.status.value,
        )
    kind: Literal["looked_up", "saved", "unsaved"]
    if isinstance(event, WordLookedUp):
        kind = "looked_up"
    elif isinstance(event, WordSaved):
        kind = "saved"
    else:
        kind = "unsaved"
    return protocol.LearningEvent(
        id=event_id, kind=kind, entry_id=event.entry_id, at=at
    )


def dictionary_of(entry_id: str) -> str:
    """The dictionary an entry ID belongs to: what comes before its colon
    (protocol.md: `cedict:y7p98nwvxq`)."""
    return entry_id.partition(":")[0]


def from_state(state: protocol.LearningState, dictionary: str) -> list[LearningEvent]:
    """A `learning_state` as Learning's events: each status and saved word
    of `dictionary`'s entries in its current state, with the time it was
    set. An account learning two languages gets both dictionaries' entries;
    the other one's are left out (they belong in the other language's
    learning data), as is a status this app doesn't know or a time it
    can't read."""
    events: list[LearningEvent] = []
    for status in state.statuses:
        if dictionary_of(status.entry_id) != dictionary:
            continue
        if status.status not in WordStatus:
            continue
        try:
            at = protocol.parse_at(status.at)
        except ValueError:
            continue
        events.append(
            WordStatusChanged(EntryId(status.entry_id), WordStatus(status.status), at)
        )
    for saved in state.saved_words:
        if dictionary_of(saved.entry_id) != dictionary:
            continue
        try:
            at = protocol.parse_at(saved.at)
        except ValueError:
            continue
        kind = WordSaved if saved.saved else WordUnsaved
        events.append(kind(EntryId(saved.entry_id), at))
    return events


def exposure_day(day: date, counts: Mapping[str, int]) -> protocol.ExposureDay:
    """A finished UTC day's counts; entries at 0 or below left out (the
    server takes 1 to 10,000)."""
    return protocol.ExposureDay(
        date=day.isoformat(),
        counts={entry: min(n, 10_000) for entry, n in sorted(counts.items()) if n > 0},
    )
