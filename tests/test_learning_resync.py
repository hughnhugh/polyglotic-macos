"""After the server's store is restored, this PC sends its learning state again (polyglotic-hq project 166).

A restore from a backup loses what was sent since the backup, and the app
sends only new events. The server now names its learning store's epoch in
`welcome` (`learning_epoch`); a new one makes `DataExchange` send the whole
learning state once - every status the learner set and every saved word,
each at its own time, in `learning` batches within the limits - and sync
from the start. Here, over a real outbox in memory, without a network.
"""

import itertools
import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from tests.test_exchange import (
    AT,
    ENGLISH,
    INSTALL,
    WORD,
    Heard,
    decode,
    deleted_at,
    types,
)
from tests.test_protocol import example

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.exchange import AWAITING_MAX, DataExchange
from polyglotic_desktop.core.shared import (
    EntryId,
    LearningEvent,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)

EPOCH = "b7e1c2d3-4f5a-4b6c-8d7e-9f0a1b2c3d4e"
RESTORED = "0c1d2e3f-4a5b-4c6d-8e7f-a0b1c2d3e4f5"
HOUR = timedelta(hours=1)


def word(n: int) -> EntryId:
    return EntryId(f"cedict:w{n:08d}")


class Rig:
    """The exchange, its outbox, and the learner's state on this PC."""

    def __init__(self, outbox: SqliteOutbox | None = None) -> None:
        self.outbox = outbox or SqliteOutbox(":memory:")
        self.state: list[LearningEvent] = []
        self.now = AT
        ids = (f"00000000-0000-4000-8000-{n:012d}" for n in itertools.count(1))
        self.exchange = DataExchange(
            self.outbox,
            self.outbox,
            Heard(),
            "cedict",
            whole_state=lambda: list(self.state),
            new_id=lambda: next(ids),
            clock=lambda: self.now,
        )

    def open(self, epoch: str | None, **limits: int) -> list[dict[str, Any]]:
        return decode(self.exchange.opened(INSTALL, protocol.Limits(**limits), epoch))

    def answer(self, messages: Sequence[dict[str, Any]]) -> None:
        for message in messages:
            if "batch" in message:
                self.exchange.heard(protocol.Received(batch=message["batch"]))


def resent(messages: Sequence[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """The (kind, entry, at) of every learning event in these messages."""
    return [
        (e["kind"], e["entry_id"], e["at"])
        for m in messages
        if m["type"] == "learning"
        for e in m["events"]
    ]


def an_install_that_has_synced(rig: Rig) -> None:
    """This PC as it was before the restore: an install, synced with the
    server whose epoch it knows, and its learning state."""
    rig.open(EPOCH)  # a new install: nothing from before it goes
    rig.exchange.heard(protocol.LearningState(cursor="120"))
    rig.exchange.closed()
    rig.now = AT + 24 * HOUR
    rig.state = [
        WordStatusChanged(WORD, WordStatus.LEARNING, AT + HOUR),
        WordSaved(WORD, AT + 2 * HOUR),
        WordStatusChanged(ENGLISH, WordStatus.KNOWN, AT + 3 * HOUR),
    ]


def test_a_new_epoch_sends_the_whole_state_once_and_syncs_from_the_start() -> None:
    rig = Rig()
    an_install_that_has_synced(rig)
    assert types(rig.open(EPOCH)) == ["learning_sync"]  # nothing to resend
    rig.exchange.closed()

    out = rig.open(RESTORED)
    assert types(out) == ["learning", "learning_sync"]
    assert out[-1] == {"type": "learning_sync"}  # the old cursor counted the old store
    assert resent(out) == [
        ("status", WORD, protocol.at(AT + HOUR)),
        ("saved", WORD, protocol.at(AT + 2 * HOUR)),
        ("status", ENGLISH, protocol.at(AT + 3 * HOUR)),
    ]
    assert not rig.exchange.settled()
    rig.answer(out)
    rig.exchange.heard(protocol.LearningState(cursor="3"))
    assert rig.exchange.settled()
    rig.exchange.closed()

    assert types(rig.open(RESTORED)) == ["learning_sync"]  # once only
    assert not rig.outbox.waiting()  # held in memory, never in the outbox


def test_a_resync_cut_short_goes_again_next_session() -> None:
    rig = Rig()
    an_install_that_has_synced(rig)
    first = rig.open(RESTORED)
    assert len(resent(first)) == 3
    rig.exchange.closed()  # before `received`
    again = rig.open(RESTORED)
    assert len(resent(again)) == 3
    rig.answer(again)
    rig.exchange.closed()
    assert resent(rig.open(RESTORED)) == []


def test_a_big_state_goes_in_batches_within_the_limits_a_few_at_a_time() -> None:
    rig = Rig()
    an_install_that_has_synced(rig)
    rig.state = [
        WordStatusChanged(
            word(n), WordStatus.KNOWN, AT + HOUR + n * timedelta(seconds=1)
        )
        for n in range(4_000)
    ]
    out = rig.open(RESTORED, learning_events=100)
    batches = [m for m in out if m["type"] == "learning"]
    assert len(batches) == AWAITING_MAX
    assert all(len(m["events"]) <= 100 for m in batches)
    assert all(len(json.dumps(m)) < 64 * 1024 for m in batches)
    sent = resent(out)
    while True:
        rig.answer(out)
        out = decode(rig.exchange.more())
        if not out:
            break
        sent += resent(out)
    assert len(sent) == 4_000 and len(set(sent)) == 4_000
    rig.exchange.heard(protocol.LearningState(cursor="1"))  # the sync's answer
    assert rig.exchange.settled()


def test_nothing_from_before_a_deletion_or_this_install_goes_again() -> None:
    """A deletion this PC applied stays applied - the restored server may
    not know of it, and the PC's own copy stays (the learner's choice) - and
    what's on this PC from before it became this install may be another
    account's."""
    rig = Rig()
    an_install_that_has_synced(rig)
    rig.exchange.heard(
        protocol.LearningState(
            cursor="130", deletion=deleted_at(AT + 2 * HOUR + timedelta(minutes=30))
        )
    )
    rig.exchange.closed()
    rig.state += [
        WordSaved(word(1), AT - HOUR),  # before this install
        WordStatusChanged(word(2), WordStatus.KNOWN, AT + 30 * HOUR),  # after it all
    ]
    out = rig.open(RESTORED)
    assert resent(out) == [
        ("status", ENGLISH, protocol.at(AT + 3 * HOUR)),
        ("status", word(2), protocol.at(AT + 30 * HOUR)),
    ]


def test_a_server_without_an_epoch_gets_nothing_again() -> None:
    rig = Rig()
    an_install_that_has_synced(rig)
    assert types(rig.open(None)) == ["learning_sync"]


def test_an_install_from_before_the_epoch_sends_everything_once() -> None:
    """An app updated to this version: its install has no start time kept
    (it was made before there was one), so the server's first epoch sends
    all of it once - its own account's, as nothing here says otherwise."""
    outbox = SqliteOutbox(":memory:")
    outbox.save_note("install_id", INSTALL)
    rig = Rig(outbox)
    rig.state = [
        WordSaved(WORD, AT - 100 * HOUR),
        WordLookedUp(WORD, AT - 99 * HOUR),  # never in the state, but say it were
    ]
    out = rig.open(EPOCH)
    assert [k for k, _, _ in resent(out)] == ["saved", "looked_up"]


def test_the_servers_welcome_names_its_epoch_and_an_older_ones_doesnt() -> None:
    welcome = protocol.decode(json.dumps(example("welcome")))
    assert isinstance(welcome, protocol.Welcome)
    assert welcome.learning_epoch == "b7e1c2d3-4f5a-4b6c-8d7e-9f0a1b2c3d4e"
    older = example("welcome")
    del older["learning_epoch"]
    welcome = protocol.decode(json.dumps(older))
    assert isinstance(welcome, protocol.Welcome) and welcome.learning_epoch is None
