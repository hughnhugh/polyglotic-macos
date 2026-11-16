"""The outbox on a thread of its own: the interface never waits on its disk.

`DataExchange` adds to the outbox on the caller's thread - the interface
thread for the user's consent choice, each of Learning's events and most
usage events - and each SQLite commit took 2 ms on a quiet disk and 60-84
ms while the disk was busy at start (polyglotic-hq project 136).
`BackgroundOutbox` hands each write to one worker thread, in order, and
returns at once, as `BackgroundLearningStore` does for the learning data.

A read - what's waiting, a note, the consent choice - waits for the writes
queued before it, so it sees them (the `Outbox` port's promise): a session
reads what to send on its own thread, and everything added before is in
it - a consent choice saved before the usage events that depend on it. The
outbox it wraps is opened, used and closed on that thread only.

A write that fails is logged - its type and place, never what it held -
and the next one goes on. When the app ends, what's queued is still
written: Python's thread pool runs a worker's queue to its end before the
interpreter stops (its own exit hook, ahead of `atexit`). `close` does the
same and closes the file. A write that comes after it is logged and not
written.
"""

import logging
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from polyglotic_desktop.ports.consent import ConsentChoice, ConsentStore
from polyglotic_desktop.ports.outbox import Outbox, Waiting

log = logging.getLogger(__name__)


class ClosableOutbox(Outbox, ConsentStore, Protocol):
    def close(self) -> None: ...


class BackgroundOutbox:
    """An `Outbox` and `ConsentStore` whose writes run on a worker thread, in order."""

    def __init__(self, open_outbox: Callable[[], ClosableOutbox]) -> None:
        """`open_outbox` opens the outbox on the worker thread; what it raises
        (a file that's locked or out of reach) is raised here."""
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="outbox")
        try:
            self._outbox = self._worker.submit(open_outbox).result()
        except BaseException:
            self._worker.shutdown()
            raise

    def close(self) -> None:
        """Waits for every queued write, then closes the outbox."""
        try:
            self._worker.submit(self._outbox.close)
        except RuntimeError:  # closed already, or the interpreter is ending
            return
        self._worker.shutdown(wait=True)

    def flush(self) -> None:
        """Waits for every write queued so far (tests, before reading the file)."""
        self._worker.submit(lambda: None).result()

    # -- reads: wait for the writes before them ----------------------------------------

    def waiting(self) -> Sequence[Waiting]:
        return self._worker.submit(self._outbox.waiting).result()

    def dropped(self) -> int:
        return self._worker.submit(self._outbox.dropped).result()

    def note(self, key: str) -> str | None:
        return self._worker.submit(self._outbox.note, key).result()

    def consent(self) -> ConsentChoice | None:
        return self._worker.submit(self._outbox.consent).result()

    # -- writes: queued, in order -------------------------------------------------------

    def add(self, item: Waiting, keep: int) -> None:
        self._write(self._outbox.add, item, keep)

    def remove(self, ids: Iterable[str]) -> None:
        self._write(self._outbox.remove, tuple(ids))  # the caller's may be a generator

    def remove_kind(self, kind: str) -> None:
        self._write(self._outbox.remove_kind, kind)

    def save_note(self, key: str, value: str | None) -> None:
        self._write(self._outbox.save_note, key, value)

    def save_consent(self, choice: ConsentChoice) -> None:
        self._write(self._outbox.save_consent, choice)

    def _write(self, save: Callable[..., None], *values: object) -> None:
        try:
            self._worker.submit(_logged, save, *values)
        except RuntimeError:  # after `close`, or as the interpreter ends
            log.warning("an outbox write came after it closed: not written")


def _logged(save: Callable[..., None], *values: object) -> None:
    try:
        save(*values)
    except Exception:
        log.exception("an outbox write failed")
