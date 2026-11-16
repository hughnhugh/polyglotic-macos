"""Outbox: what waits on this PC to be sent to the server.

Learning events, consent choices, usage events and daily exposure counts
are kept until the server says it has them (protocol.md: `received`), so
nothing is lost while the PC is offline, the server refuses a message, or
the app is closed. Bounded: past a limit per kind, the oldest go first,
and the outbox counts how many went.

What's kept is content-free by construction (entry IDs, times, counts,
the tracking plan's properties) - never audio, caption text or a saved
word's sentence. The connection decides what goes in and turns it into
protocol messages; `main` hands it an implementation.

A write may be done later, on another thread (the app's outbox writes on
a thread of its own, so the interface never waits on the disk): writes are
done in the order they're made, and a read sees every write made before it.
So a write returns nothing - what it dropped is counted in `dropped`.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Waiting:
    """One thing waiting to be sent. `kind` is the protocol message it
    goes in (`consent`, `learning_delete`, `learning`, `exposures`,
    `usage`); `id` is its own id (a UUID); `body` is its JSON."""

    kind: str
    id: str
    body: str


class Outbox(Protocol):
    def add(self, item: Waiting, keep: int) -> None:
        """Adds `item` at the back. If more than `keep` of its kind are
        then waiting, the oldest are dropped (counted in `dropped`)."""
        ...

    def waiting(self) -> Sequence[Waiting]:
        """Everything waiting, oldest first."""
        ...

    def remove(self, ids: Iterable[str]) -> None:
        """Forgets these items (the server has them)."""
        ...

    def remove_kind(self, kind: str) -> None:
        """Forgets every item of `kind` (consent withdrawn, data deleted)."""
        ...

    def dropped(self) -> int:
        """How many items have been dropped for room, ever."""
        ...

    def note(self, key: str) -> str | None:
        """A small value the connection keeps between runs (the learning
        sync cursor, the install the consent was sent for)."""
        ...

    def save_note(self, key: str, value: str | None) -> None:
        """Keeps `value` under `key`; None forgets it."""
        ...
