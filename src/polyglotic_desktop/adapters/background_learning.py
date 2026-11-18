"""The learning store on a thread of its own: Learning's saves never wait
on the disk.

`Vocabulary` (core) saves each change through the `LearningStore` port as
it happens - an exposure count per finished caption, a word's status, a
saved word - and each SQLite write took 2.5-13 ms on the interface thread
(polyglotic-hq projects 108 and 110). `BackgroundLearningStore` hands each
write to one worker thread, in order, and returns at once. A read (the
snapshot at start, the daily counts for sharing) waits for the writes
queued before it, so it sees them. The store it wraps is opened, used and
closed on that thread only.

A write that fails is logged - its type and place, never what it held -
and the next one goes on, as the app went on after a failed write before.
When the app ends, what's queued is still written: Python's thread pool
runs a worker's queue to its end before the interpreter stops (its own
exit hook, ahead of `atexit`). `close` does the same and closes the store;
a write after it is logged and not written, as the outbox's is.

**A store found damaged after the start** (polyglotic-hq 206) - a save or
a read failing on SQLite's "damaged" or "not a database" - is out for the
rest of the session: it's set aside at once (`set_aside_now`), kept as it
was, nothing more is written to it, reads answer nothing, and
`on_damaged` is told once, with where it went. It's logged once, not per
save. What Learning holds stays in memory for the session, and its events
still go to the outbox for the server; the next start begins a new store,
which syncs back what the server keeps.
"""

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

from polyglotic_desktop.adapters.sqlite_learning import is_damage
from polyglotic_desktop.ports.learning import (
    LearningSnapshot,
    LearningStore,
    SetAsideLearningData,
    StoredAnkiExport,
    StoredCategory,
    StoredCoverage,
    StoredCurriculumWord,
    StoredDeckWord,
    StoredExposures,
    StoredLevel,
    StoredLineChange,
    StoredListening,
    StoredLoadWord,
    StoredLookups,
    StoredSavedWord,
    StoredSentence,
    StoredSetWord,
    StoredStatus,
    StoredStatusChange,
)

log = logging.getLogger(__name__)
T = TypeVar("T")


class ClosableLearningStore(LearningStore, Protocol):
    def close(self) -> None: ...

    def set_aside_now(self) -> SetAsideLearningData | None: ...

    def set_aside_copies(self) -> Sequence[Path]: ...

    def delete_set_aside(self) -> int: ...


class BackgroundLearningStore:
    """A `LearningStore` whose writes run on a worker thread, in order."""

    def __init__(self, open_store: Callable[[], ClosableLearningStore]) -> None:
        """`open_store` opens the store on the worker thread; what it raises
        (an unreadable file) is raised here."""
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="learning-store")
        try:
            self._store = self._worker.submit(open_store).result()
        except BaseException:
            self._worker.shutdown()
            raise
        self.on_damaged: Callable[[SetAsideLearningData | None], None] | None = None
        """Told once, on the store's thread, when the store is found damaged
        after the start: where it was set aside (None: it couldn't be)."""
        self.on_deleted: Callable[[], None] | None = None
        """Told on the store's thread once the learner's learning data on
        this PC is deleted, with the files set aside from it - those that
        could be (polyglotic-hq 213)."""
        self.on_not_deleted: Callable[[], None] | None = None
        """Told on the store's thread, after `on_deleted`, when a deletion
        left some of it on this PC: the store couldn't be emptied (busy,
        out of room - not damage, which sets it aside to be deleted), or a
        file set aside from it couldn't be deleted (in use). With several
        languages, each store says so for itself (polyglotic-hq 306)."""
        self.out = False
        """Found damaged: nothing more is written this session."""

    def close(self) -> None:
        """Waits for every queued write, then closes the store."""
        try:
            self._worker.submit(self._store.close)
        except RuntimeError:  # closed already, or the interpreter is ending
            return
        self._worker.shutdown(wait=True)

    def flush(self) -> None:
        """Waits for every write queued so far (tests, before reading the file)."""
        self._worker.submit(lambda: None).result()

    # -- reads: wait for the writes before them ----------------------------------------

    def load(self) -> LearningSnapshot:
        return self._read(self._store.load, LearningSnapshot(None, [], [], [], []))

    def daily_exposures(self, day: date) -> Mapping[str, int]:
        return self._read(lambda: self._store.daily_exposures(day), {})

    def exposure_days(self) -> Sequence[date]:
        return self._read(self._store.exposure_days, [])

    def status_changes(self) -> Sequence[StoredStatusChange]:
        return self._read(self._store.status_changes, [])

    def line_changes(self) -> Sequence[StoredLineChange]:
        return self._read(self._store.line_changes, [])

    def days_to_hand_over(self) -> Sequence[date]:
        return self._read(self._store.days_to_hand_over, [])

    def saved_sentences(self) -> Sequence[StoredSentence]:
        return self._read(self._store.saved_sentences, [])

    def _read(self, read: Callable[[], T], nothing: T) -> T:
        """`read` on the store's thread, or `nothing` once it's out."""

        def guarded() -> T:
            if self.out:
                return nothing
            try:
                return read()
            except Exception as error:
                if not is_damage(error):
                    raise
                self._found_damaged()
                return nothing

        return self._worker.submit(guarded).result()

    # -- writes: queued, in order -------------------------------------------------------

    def save_level(self, level: StoredLevel) -> None:
        self._write(self._store.save_level, level)

    def clear_level(self) -> None:
        self._write(self._store.clear_level)

    def save_status(self, status: StoredStatus) -> None:
        self._write(self._store.save_status, status)

    def save_category(self, category: StoredCategory) -> None:
        self._write(self._store.save_category, category)

    def delete_category(self, category_id: str) -> None:
        self._write(self._store.delete_category, category_id)

    def save_word(self, word: StoredSavedWord) -> None:
        self._write(self._store.save_word, word)

    def delete_word(self, entry_id: str) -> None:
        self._write(self._store.delete_word, entry_id)

    def save_sentence(self, sentence: StoredSentence) -> None:
        self._write(self._store.save_sentence, sentence)

    def delete_sentence(self, sentence_id: str) -> None:
        self._write(self._store.delete_sentence, sentence_id)

    def save_deck_word(self, word: StoredDeckWord) -> None:
        self._write(self._store.save_deck_word, word)

    def delete_deck_word(self, entry_id: str) -> None:
        self._write(self._store.delete_deck_word, entry_id)

    def save_anki_exports(self, exports: Iterable[StoredAnkiExport]) -> None:
        self._write(self._store.save_anki_exports, tuple(exports))

    def save_load_words(self, words: Sequence[StoredLoadWord]) -> None:
        self._write(self._store.save_load_words, tuple(words))

    def delete_load_words(self, entry_ids: Sequence[str]) -> None:
        self._write(self._store.delete_load_words, tuple(entry_ids))

    def save_curriculum_words(self, words: Sequence[StoredCurriculumWord]) -> None:
        self._write(self._store.save_curriculum_words, tuple(words))

    def delete_curriculum_words(self, entry_ids: Sequence[str]) -> None:
        self._write(self._store.delete_curriculum_words, tuple(entry_ids))

    def add_status_changes(self, changes: Sequence[StoredStatusChange]) -> None:
        self._write(self._store.add_status_changes, tuple(changes))

    def add_line_change(self, change: StoredLineChange) -> None:
        self._write(self._store.add_line_change, change)

    def save_set_words(self, words: Sequence[StoredSetWord]) -> None:
        self._write(self._store.save_set_words, tuple(words))

    def delete_set_words(self, name: str, entry_ids: Sequence[str]) -> None:
        self._write(self._store.delete_set_words, name, tuple(entry_ids))

    def save_lookups(self, lookups: StoredLookups) -> None:
        self._write(self._store.save_lookups, lookups)

    def forget_entry(self, entry_id: str) -> None:
        self._write(self._store.forget_entry, entry_id)

    def save_exposures(
        self, counts: Sequence[StoredExposures], daily: Mapping[date, Mapping[str, int]]
    ) -> None:
        # copies: the caller may change its own after this returns
        self._write(
            self._store.save_exposures,
            tuple(counts),
            {day: dict(changes) for day, changes in daily.items()},
        )

    def mark_handed_over(self, days: Iterable[date]) -> None:
        self._write(self._store.mark_handed_over, tuple(days))

    def forget_daily_exposures(self, days: Iterable[date]) -> None:
        self._write(self._store.forget_daily_exposures, tuple(days))

    def add_coverage(self, changes: Iterable[StoredCoverage]) -> None:
        self._write(self._store.add_coverage, tuple(changes))

    def add_listening(self, listened: Iterable[StoredListening]) -> None:
        self._write(self._store.add_listening, tuple(listened))

    def delete_learning_data(self) -> None:
        self._submit(self._delete_learning_data)

    def _delete_learning_data(self) -> None:
        """Emptied, and the files set aside from it deleted (polyglotic-hq
        207) - those too once it's out: the file set aside this session
        holds the data the learner asked to delete, as does one set aside
        because this very deletion found it damaged. What's left on this PC
        afterwards - the store not emptied, a file set aside still there -
        is told (`on_not_deleted`, polyglotic-hq 306)."""
        emptied = self._emptied()
        if self.out:
            try:
                self._store.delete_set_aside()
            except Exception:
                log.exception("deleting the learning data set aside failed")
        try:
            left = not emptied or bool(self._store.set_aside_copies())
        except Exception:
            log.exception("looking for what the deletion left failed")
            left = True
        if self.on_deleted is not None:
            try:
                self.on_deleted()
            except Exception:
                log.exception("telling of the deletion failed")
        if left:
            log.warning("the learning data on this PC wasn't all deleted")
            if self.on_not_deleted is not None:
                try:
                    self.on_not_deleted()
                except Exception:
                    log.exception("telling what the deletion left failed")

    def _emptied(self) -> bool:
        """The store emptied (`delete_learning_data`): True, or found damaged
        - set aside, to be deleted with the others; False when it failed
        otherwise (busy, out of room), its data still in it."""
        if self.out:
            return True  # set aside already: its copy is deleted with the others
        try:
            self._store.delete_learning_data()
        except Exception as error:
            if is_damage(error):
                self._found_damaged()
                return True
            log.exception("deleting the learning data failed")
            return False
        return True

    def set_aside_copies(self) -> int:
        """How many files are set aside from the store, beside it - for the
        delete's confirmation. Waits for the writes queued before it."""
        return self._worker.submit(lambda: len(self._store.set_aside_copies())).result()

    def _write(self, save: Callable[..., None], *values: object) -> None:
        self._submit(self._logged, save, *values)

    def _submit(self, work: Callable[..., None], *values: object) -> None:
        try:
            self._worker.submit(work, *values)
        except RuntimeError:  # after `close`, or as the interpreter ends
            # as the outbox does: an uncaught error here, at quit, was a
            # "crash" the next start offered to report (polyglotic-hq 203)
            log.warning("a learning save came after the store closed: not written")

    def _logged(self, save: Callable[..., None], *values: object) -> None:
        if self.out:
            return
        try:
            save(*values)
        except Exception as error:
            if is_damage(error):
                self._found_damaged()
            else:
                log.exception("a learning save failed")

    def _found_damaged(self) -> None:
        """On the store's thread: out for the session, set aside, and said
        once."""
        self.out = True
        log.warning("the learning data was found damaged: nothing more is saved")
        try:
            aside = self._store.set_aside_now()
        except OSError as error:
            log.warning("it couldn't be set aside (%s)", type(error).__name__)
            aside = None
        if self.on_damaged is not None:
            try:
                self.on_damaged(aside)
            except Exception:
                log.exception("telling of the damage failed")
