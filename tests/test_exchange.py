"""What waits to be sent, and the consent rules (connection.exchange), without a network.

`DataExchange` over a real outbox in memory: what goes out when a session
opens and in what order, batches within the server's limits, `received`
forgetting what the server has, resending after a session ends, usage and
exposures only with their consent, the learning sync cursor, deleting the
learning data, and a new install.
"""

import itertools
import json
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from tests.test_protocol import example

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.exchange import (
    AWAITING_MAX,
    EXPOSURE_ENTRIES,
    KEEP,
    DataExchange,
)
from polyglotic_desktop.core.shared import (
    EntryId,
    LearningEvent,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.outbox import Waiting

INSTALL = "3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f"
AT = datetime(2026, 11, 4, 9, 15, 2, 120000, tzinfo=UTC)
WORD = EntryId("cedict:y7p98nwvxq")
ENGLISH = EntryId("ecdict:njx2am9103")


class Heard:
    def __init__(self) -> None:
        self.arrived: list[LearningEvent] = []
        self.deleted = 0

    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        self.arrived.extend(events)

    def learning_deleted(self) -> None:
        self.deleted += 1


class Rig:
    def __init__(
        self, outbox: SqliteOutbox | None = None, dictionary: str = "cedict"
    ) -> None:
        self.outbox = outbox or SqliteOutbox(":memory:")
        self.heard = Heard()
        ids = (f"00000000-0000-4000-8000-{n:012d}" for n in itertools.count(1))
        self.exchange = DataExchange(
            self.outbox,
            self.outbox,
            self.heard,
            dictionary,
            new_id=lambda: next(ids),
            clock=lambda: self.now,
        )
        self.now = AT  # this PC's clock
        self.woken = 0
        self.exchange.wake = self._wake

    def _wake(self) -> None:
        self.woken += 1

    def open(
        self, install: str = INSTALL, account: str | None = None, **limits: int
    ) -> list[dict[str, Any]]:
        return decode(
            self.exchange.opened(install, protocol.Limits(**limits), None, account)
        )

    def more(self) -> list[dict[str, Any]]:
        return decode(self.exchange.more())

    def answer(self, messages: list[dict[str, Any]]) -> None:
        """The server's `received` for each, as it would answer."""
        for message in messages:
            if message["type"] == "consent":
                self.exchange.heard(protocol.Received(id=message["id"]))
            elif "batch" in message:
                self.exchange.heard(protocol.Received(batch=message["batch"]))


def decode(messages: list[str]) -> list[dict[str, Any]]:
    return [json.loads(m) for m in messages]


def types(messages: list[dict[str, Any]]) -> list[str]:
    return [m["type"] for m in messages]


def test_consent_goes_first_then_learning_then_usage_then_the_sync() -> None:
    rig = Rig()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.exchange.learning(WordSaved(WORD, AT))
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    sent = rig.open()
    assert types(sent) == ["consent", "learning", "usage", "learning_sync"]
    consent, learning, usage, sync = sent
    assert consent | {"id": "x"} == example("consent") | {
        "id": "x",
        "at": "2026-11-04T09:15:02.120Z",
        "usage": True,
        "crashes": False,
    }
    assert [e["kind"] for e in learning["events"]] == ["looked_up", "saved"]
    assert {e["entry_id"] for e in learning["events"]} == {WORD}
    assert [e["name"] for e in usage["events"]] == ["caption_rated"]
    assert sync == {"type": "learning_sync"}
    assert rig.woken == 4


def test_the_agreement_accepted_goes_with_every_consent_after_it() -> None:
    """polyglotic-hq 185: the tester agreement accepted at start goes with
    the consent, as the server's example has it - and with every later
    choice and a new install's resend, so the server's latest record
    always names it."""
    rig = Rig()
    agreed = Agreement("tester-2026-11-08", datetime(2026, 11, 4, 9, 1, 30, tzinfo=UTC))
    rig.exchange.choose_consent(
        usage=True, crashes=False, exposures=False, agreement=agreed
    )
    [first, _] = rig.open()
    assert first | {"id": "x", "at": "y"} == example("consent.agreement") | {
        "id": "x",
        "at": "y",
    }
    rig.answer([first])
    rig.exchange.closed()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    assert rig.exchange.consent is not None
    assert rig.exchange.consent.agreement == agreed
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
    for again in rig.open(install=other)[:-1]:
        assert again["agreement"] == {
            "version": "tester-2026-11-08",
            "at": "2026-11-04T09:01:30.000Z",
        }


def test_a_choice_before_any_agreement_sends_none() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    consent, _ = rig.open()
    assert "agreement" not in consent


def test_lookups_and_saves_are_learning_data_not_usage_events() -> None:
    """polyglotic-hq DECISIONS.md #20 (accepted 2026-11-05): usage
    statistics count lookups and saves once per listening session, in its
    summary - no usage event per lookup or save."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.exchange.learning(WordLookedUp(WORD, AT))
    rig.exchange.learning(WordSaved(WORD, AT))
    assert [w.kind for w in rig.outbox.waiting()] == ["consent", "learning", "learning"]
    assert types(rig.open()) == ["consent", "learning", "learning_sync"]


def test_received_forgets_and_whats_unanswered_goes_again_next_session() -> None:
    rig = Rig()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    rig.exchange.learning(WordSaved(WORD, AT))
    (learning, _sync) = rig.open()
    rig.exchange.closed()  # the connection dropped before `received`
    (again, _sync) = rig.open()
    assert (
        again["events"] == learning["events"]
    )  # same event ids: the server ignores repeats
    assert again["batch"] != learning["batch"]
    rig.answer([again])
    assert not rig.exchange.has_waiting()
    rig.exchange.closed()
    assert types(rig.open()) == ["learning_sync"]


def test_settled_once_everything_is_answered() -> None:
    rig = Rig()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    sent = rig.open()
    assert not rig.exchange.settled()
    rig.answer(sent)
    assert not rig.exchange.settled()  # learning_state still to come
    rig.exchange.heard(
        protocol.LearningState(cursor="7", more=False, statuses=(), saved_words=())
    )
    assert rig.exchange.settled()


def test_nothing_optional_without_consent() -> None:
    rig = Rig()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    assert not rig.exchange.usage("listening_session_ended", {"captions": 3}, AT)
    assert not rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})
    rig.exchange.choose_consent(usage=False, crashes=True, exposures=False)
    assert not rig.exchange.usage("listening_session_ended", {"captions": 3}, AT)
    assert types(rig.open()) == ["consent", "learning", "learning_sync"]


def test_saying_no_drops_what_waits_of_that_kind() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=True)
    assert rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    assert rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    sent = rig.open()
    assert types(sent) == ["consent", "consent", "learning_sync"]
    assert [m["usage"] for m in sent[:2]] == [True, False]  # the history, in order


def test_exposures_with_their_own_consent() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    days: dict[date, dict[str, int]] = {
        date(2026, 11, 3): {WORD: 2},
        date(2026, 11, 2): {WORD: 4, "cedict:x": 0},
    }
    assert rig.exchange.exposures(days)
    (_consent, exposures, _sync) = rig.open()
    assert exposures["days"] == [
        {"date": "2026-11-02", "counts": {WORD: 4}},
        {"date": "2026-11-03", "counts": {WORD: 2}},
    ]


def test_a_day_too_big_for_one_message_goes_in_parts() -> None:
    """project 034: the server keeps counts per install, day and entry, so a
    day that doesn't fit 64 KiB goes in parts - before, it was cut to its
    most-heard entries and the rest were lost."""
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    big = {f"cedict:{n:010d}": 1 + n % 7 for n in range(EXPOSURE_ENTRIES)}
    small: dict[str, int] = {WORD: 3}
    assert rig.exchange.exposures({date(2026, 11, 3): big, date(2026, 11, 4): small})
    sent = [m for m in rig.open() if m["type"] == "exposures"]
    sizes = [len(json.dumps(m, separators=(",", ":"))) for m in sent]
    assert len(sent) > 1 and max(sizes) <= 65_536  # the server's text message limit
    days = [day for m in sent for day in m["days"]]
    parts = [d["counts"] for d in days if d["date"] == "2026-11-03"]
    assert len(parts) > 1 and all(len(p) <= EXPOSURE_ENTRIES for p in parts)
    assert {e: n for p in parts for e, n in p.items()} == big  # nothing lost
    assert sum(len(p) for p in parts) == len(big)  # nor sent twice
    assert [d["counts"] for d in days if d["date"] == "2026-11-04"] == [small]


def test_parts_also_keep_to_the_entries_a_day_a_message() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    many = {f"c:{n}": 1 for n in range(EXPOSURE_ENTRIES + 1)}  # short: fits 64 KiB
    assert rig.exchange.exposures({date(2026, 11, 3): many})
    sent = [m for m in rig.open() if m["type"] == "exposures"]
    parts = [d["counts"] for m in sent for d in m["days"]]
    assert sorted(len(p) for p in parts) == [1, EXPOSURE_ENTRIES]


def test_batches_stay_within_the_count_and_the_message_size() -> None:
    rig = Rig()
    for n in range(1200):
        rig.exchange.learning(
            WordStatusChanged(EntryId(f"cedict:{n:010d}"), WordStatus.KNOWN, AT)
        )
    sent = [m for m in rig.open() if m["type"] == "learning"]
    sizes = [len(json.dumps(m, separators=(",", ":"))) for m in sent]
    assert all(len(m["events"]) <= 500 for m in sent)
    assert max(sizes) <= 65_536  # the server's text message limit
    assert sum(len(m["events"]) for m in sent) == 1200
    small = Rig()
    for _ in range(10):
        small.exchange.learning(WordLookedUp(WORD, AT))
    batches = [m for m in small.open(learning_events=4) if m["type"] == "learning"]
    assert [len(m["events"]) for m in batches] == [4, 4, 2]


def test_a_few_messages_await_an_answer_at_a_time() -> None:
    rig = Rig()
    for n in range(AWAITING_MAX + 3):
        rig.exchange.learning(WordLookedUp(EntryId(f"cedict:{n:010d}"), AT))
    first = [m for m in rig.open(learning_events=1) if m["type"] == "learning"]
    assert len(first) == AWAITING_MAX
    assert rig.more() == []
    rig.answer(first[:2])
    assert len(rig.more()) == 2


def test_the_outbox_is_bounded_oldest_first_with_a_count() -> None:
    outbox = SqliteOutbox(":memory:")
    rig = Rig(outbox)
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    for n in range(KEEP["usage"] + 5):
        rig.exchange.usage("caption_rated", {"thumbs": "up" if n else "down"}, AT)
    usage = [w for w in outbox.waiting() if w.kind == "usage"]
    assert len(usage) == KEEP["usage"] and outbox.dropped() == 5
    assert all('"up"' in w.body for w in usage)  # the first, "down", went


def test_learning_sync_keeps_its_cursor_and_asks_again_while_more() -> None:
    rig = Rig()
    assert rig.open()[-1] == {"type": "learning_sync"}
    state = protocol.decode(json.dumps(example("learning_state") | {"more": True}))
    assert isinstance(state, protocol.LearningState)
    rig.exchange.heard(state)
    assert len(rig.heard.arrived) == 3  # the example's CC-CEDICT entries
    assert rig.more() == [{"type": "learning_sync", "since": "1234"}]
    rig.exchange.heard(protocol.LearningState(cursor="1300"))
    assert rig.more() == []
    rig.exchange.closed()
    assert rig.open()[-1] == {"type": "learning_sync", "since": "1300"}


def state(cursor: str, *entry_ids: str) -> protocol.LearningState:
    """A `learning_state` with each entry known and saved."""
    at = "2026-11-04T09:15:05.480Z"
    return protocol.LearningState(
        cursor=cursor,
        statuses=tuple(
            protocol.StatusState(entry_id=e, status="known", at=at) for e in entry_ids
        ),
        saved_words=tuple(
            protocol.SavedState(entry_id=e, saved=True, at=at) for e in entry_ids
        ),
    )


def test_only_the_open_languages_entries_arrive() -> None:
    """An account learning Chinese and English: a `learning_state` carries
    both dictionaries' entries. Only the open learning data's dictionary's
    are handed over - the other language's stay on the server, untouched,
    for a PC learning it."""
    for dictionary, kept in (("cedict", "cedict:y7p98nwvxq"), ("ecdict", ENGLISH)):
        rig = Rig(dictionary=dictionary)
        rig.open()
        rig.exchange.heard(state("7", "cedict:y7p98nwvxq", ENGLISH))
        assert {e.entry_id for e in rig.heard.arrived} == {kept}
        assert [type(e) for e in rig.heard.arrived] == [WordStatusChanged, WordSaved]
        assert rig.more() == []  # nothing goes back about the other's


def test_each_language_syncs_from_its_own_cursor() -> None:
    """The cursor is kept per dictionary: entries of the other language
    passed over while one was open still arrive when the learner switches
    to it (at the next start, a new exchange over the same outbox)."""
    outbox = SqliteOutbox(":memory:")
    chinese = Rig(outbox, "cedict")
    assert chinese.open()[-1] == {"type": "learning_sync"}
    chinese.exchange.heard(state("50", "cedict:y7p98nwvxq", ENGLISH))
    chinese.exchange.closed()

    english = Rig(outbox, "ecdict")  # switched on the Languages page
    assert english.open()[-1] == {"type": "learning_sync"}  # from the start
    english.exchange.heard(state("60", "cedict:y7p98nwvxq", ENGLISH))
    assert {e.entry_id for e in english.heard.arrived} == {ENGLISH}
    english.exchange.closed()
    assert english.open()[-1] == {"type": "learning_sync", "since": "60"}

    chinese = Rig(outbox, "cedict")  # and back
    assert chinese.open()[-1] == {"type": "learning_sync", "since": "50"}


def test_deleting_or_a_new_install_syncs_every_language_from_the_start() -> None:
    outbox = SqliteOutbox(":memory:")
    for dictionary, cursor in (("cedict", "50"), ("ecdict", "60")):
        rig = Rig(outbox, dictionary)
        rig.open()
        rig.exchange.heard(protocol.LearningState(cursor=cursor))
        rig.exchange.closed()
    rig.exchange.delete_learning()  # learning English: the server deletes both
    assert types(rig.open()) == ["learning_delete"]  # the sync waits for it
    rig.exchange.heard(protocol.LearningDeleted())
    assert rig.more() == [{"type": "learning_sync"}]
    assert Rig(outbox, "cedict").open() == [{"type": "learning_sync"}]

    for dictionary, cursor in (("cedict", "70"), ("ecdict", "80")):
        rig = Rig(outbox, dictionary)
        rig.open()
        rig.exchange.heard(protocol.LearningState(cursor=cursor))
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
    assert Rig(outbox, "ecdict").open(install=other)[-1] == {"type": "learning_sync"}
    assert Rig(outbox, "cedict").open(install=other)[-1] == {"type": "learning_sync"}


def test_deleting_the_learning_data() -> None:
    rig = Rig()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    first = rig.open()
    rig.exchange.heard(protocol.LearningState(cursor="9"))
    rig.answer(first)
    rig.exchange.learning(WordSaved(WORD, AT))  # not sent yet: dropped by the deletion
    rig.exchange.delete_learning()
    rig.now = AT + timedelta(seconds=1)
    rig.exchange.learning(WordLookedUp(WORD, rig.now))  # after it: kept
    rig.exchange.closed()
    sent = rig.open()
    assert types(sent) == ["learning_delete"]  # the sync and the lookup wait for it
    rig.exchange.heard(protocol.LearningDeleted())
    assert rig.heard.deleted == 1
    assert rig.more() == [{"type": "learning_sync"}]  # from the start
    assert [w.kind for w in rig.outbox.waiting()] == ["learning"]
    rig.exchange.heard(protocol.LearningState(cursor="1", deletion=deleted_at(AT)))
    (learning,) = rig.more()
    assert [e["kind"] for e in learning["events"]] == ["looked_up"]


# -- a deletion reaches every device (polyglotic-server protocol.md, 051) ------

HOUR = timedelta(hours=1)


def deleted_at(at: datetime, generation: int = 1) -> protocol.DeletionState:
    return protocol.DeletionState(generation=generation, at=protocol.at(at))


def test_a_deletion_made_elsewhere_drops_what_waits_from_before_it_and_syncs_again() -> (
    None
):
    """Another PC (or a phone) deleted the learning data: what waits here
    from before the deletion would bring it back - dropped, never sent; and
    the cursor may be past change numbers handed out again - synced from
    the start. This PC's own copy stays (the learner deletes it here if
    they want)."""
    rig = Rig()
    rig.open()
    rig.exchange.heard(protocol.LearningState(cursor="50"))
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))  # offline: waiting
    rig.exchange.learning(WordLookedUp(WORD, AT + HOUR))  # after the deletion
    learning, sync = rig.open()
    assert sync == {"type": "learning_sync", "since": "50"}
    rig.exchange.heard(protocol.LearningState(cursor="61", deletion=deleted_at(AT)))
    assert [w.kind for w in rig.outbox.waiting()] == ["learning"]
    (kept,) = rig.outbox.waiting()
    assert '"looked_up"' in kept.body
    assert rig.more() == [{"type": "learning_sync"}]  # from the start, once
    rig.exchange.heard(protocol.LearningState(cursor="62", deletion=deleted_at(AT)))
    assert rig.more() == []  # already applied
    rig.answer([learning])
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))  # republished, say: stale
    assert not rig.exchange.has_waiting()
    rig.exchange.learning(WordSaved(WORD, AT + HOUR))
    assert [w.kind for w in rig.outbox.waiting()] == ["learning"]


def test_deleting_asks_for_the_sync_at_once_to_learn_its_number() -> None:
    """In a session that has already synced (listening, say), the deleting
    PC asks for `learning_sync` as soon as the deletion is answered, so it
    learns the deletion's number and time at once - not at the next
    session (polyglotic-hq project 059, Low 3)."""
    rig = Rig()
    rig.open()
    rig.exchange.heard(protocol.LearningState(cursor="9"))
    assert rig.more() == []
    rig.exchange.delete_learning()
    assert types(rig.more()) == ["learning_delete"]
    rig.exchange.heard(protocol.LearningDeleted())
    assert rig.more() == [{"type": "learning_sync"}]  # from the start


SKEW = timedelta(seconds=60)  # this PC's clock, behind the server's
MS = timedelta(milliseconds=1)


def sent_times(messages: list[dict[str, Any]]) -> list[str]:
    return [e["at"] for m in messages if m["type"] == "learning" for e in m["events"]]


def test_learning_made_after_deleting_here_counts_as_after_it_whatever_the_clock() -> (
    None
):
    """polyglotic-hq project 059, Low 3: the deletion's time is the
    server's clock, events carry this PC's. On a PC a minute behind, a word
    saved in the minute after deleting was stamped before the deletion and
    dropped - by the server (which still answered `received`) and here.
    Now what this PC does after it asked to delete waits until it knows
    the deletion's time, and goes stamped just after it if its clock put it
    at or before - each a millisecond after the last, so the latest still
    wins. Something stamped before the request (republished with its old
    time) is still from before."""
    rig = Rig()
    rig.open()
    rig.exchange.heard(protocol.LearningState(cursor="9"))
    rig.now = AT - SKEW - timedelta(seconds=10)  # the server's AT - 10s
    rig.exchange.delete_learning()
    assert types(rig.more()) == ["learning_delete"]
    rig.exchange.learning(WordSaved(WORD, AT - SKEW + timedelta(seconds=30)))
    rig.exchange.learning(
        WordStatusChanged(WORD, WordStatus.KNOWN, AT - SKEW + timedelta(seconds=31))
    )
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))  # republished: from before
    assert rig.more() == []  # held until the deletion's time is known
    rig.exchange.heard(protocol.LearningDeleted())  # the server deleted at AT
    assert rig.more() == [{"type": "learning_sync"}]
    rig.exchange.heard(protocol.LearningState(cursor="1", deletion=deleted_at(AT)))
    sent = rig.more()
    assert sent_times(sent) == [protocol.at(AT + MS), protocol.at(AT + 2 * MS)]
    rig.answer(sent)
    rig.now = AT - SKEW + timedelta(seconds=40)  # still behind: still after it
    rig.exchange.learning(WordLookedUp(WORD, rig.now))
    rig.exchange.learning(WordSaved(WORD, AT + HOUR))  # past the deletion: as it is
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))  # from before: dropped
    assert sent_times(rig.more()) == [
        protocol.at(AT + 3 * MS),
        protocol.at(AT + HOUR),
    ]


def test_what_waits_while_offline_after_deleting_here_is_after_it_too() -> None:
    """Deleted while offline: the request waits, and so does everything
    done after it - the server records the deletion when it arrives, later
    than all of it - and none of it is lost. Kept across closing the app."""
    outbox = SqliteOutbox(":memory:")
    rig = Rig(outbox)
    rig.now = AT - 2 * HOUR
    rig.exchange.delete_learning()
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))
    rig = Rig(outbox)  # the app closed and opened again
    rig.exchange.learning(WordSaved(WORD, AT - 3 * HOUR))  # republished: from before
    assert types(rig.open()) == ["learning_delete"]
    rig.exchange.heard(protocol.LearningDeleted())
    assert rig.more() == [{"type": "learning_sync"}]
    rig = Rig(outbox)  # closed again before the answer
    assert rig.open() == [{"type": "learning_sync"}]
    rig.exchange.heard(protocol.LearningState(cursor="1", deletion=deleted_at(AT)))
    assert sent_times(rig.more()) == [protocol.at(AT + MS)]


def test_learning_made_after_a_deletion_from_elsewhere_counts_as_after_it() -> None:
    """Another PC's deletion, applied here by a PC whose clock is behind:
    what was waiting from before it is dropped, as before; what this PC
    does once it has applied it is after it, whatever its clock."""
    rig = Rig()
    rig.open()
    rig.now = AT - SKEW + timedelta(seconds=5)  # 5s after the deletion
    rig.exchange.learning(WordSaved(WORD, rig.now))  # before hearing: dropped
    rig.exchange.heard(protocol.LearningState(cursor="61", deletion=deleted_at(AT)))
    assert not rig.exchange.has_waiting()
    rig.now += timedelta(seconds=1)
    rig.exchange.learning(WordSaved(WORD, rig.now))
    rig.exchange.learning(WordSaved(WORD, AT - HOUR))  # republished: from before
    assert sent_times(rig.more()) == [protocol.at(AT + MS)]


def test_an_older_server_naming_no_deletion_releases_what_was_held() -> None:
    """A server before 051 answers `learning_deleted` but names no
    deletion in `learning_state`: what was held goes as it is."""
    rig = Rig()
    rig.exchange.delete_learning()
    rig.now = AT + timedelta(seconds=1)
    rig.exchange.learning(WordSaved(WORD, rig.now))
    assert types(rig.open()) == ["learning_delete"]
    rig.exchange.heard(protocol.LearningDeleted())
    rig.more()
    rig.exchange.heard(protocol.LearningState(cursor="1"))
    assert sent_times(rig.more()) == [protocol.at(rig.now)]


def test_exposure_days_up_to_the_deletion_are_dropped() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})
    rig.answer(rig.open())
    rig.exchange.exposures({date(2026, 11, 4): {WORD: 3}})  # the deletion's day
    rig.exchange.heard(protocol.LearningState(cursor="5", deletion=deleted_at(AT)))
    assert not rig.exchange.has_waiting()
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}, date(2026, 11, 5): {WORD: 1}})
    (day,) = rig.outbox.waiting()
    assert '"2026-11-05"' in day.body


def test_a_newer_deletion_applies_again_and_a_new_install_starts_afresh() -> None:
    rig = Rig()
    rig.open()
    rig.exchange.heard(protocol.LearningState(cursor="5", deletion=deleted_at(AT)))
    rig.exchange.heard(protocol.LearningState(cursor="6"))  # synced from the start
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT + HOUR))
    rig.open()
    later = deleted_at(AT + 2 * HOUR, generation=2)
    rig.exchange.heard(protocol.LearningState(cursor="9", deletion=later))
    assert not rig.exchange.has_waiting()  # the save was from before the second
    rig.exchange.closed()
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"  # another account, say
    rig.open(install=other)
    rig.exchange.learning(WordSaved(WORD, AT))  # its own: not this account's deletion
    assert rig.exchange.has_waiting()


def test_deleting_here_drops_the_exposure_days_waiting_too() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    rig.answer(rig.open())
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})
    rig.exchange.delete_learning()
    assert [w.kind for w in rig.outbox.waiting()] == ["learning_delete"]


def test_a_new_install_sends_its_consent_again_and_syncs_from_the_start() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=True, exposures=False)
    sent = rig.open()
    rig.answer(sent)
    rig.exchange.heard(protocol.LearningState(cursor="50"))
    rig.exchange.closed()
    assert rig.open() == [{"type": "learning_sync", "since": "50"}]
    rig.exchange.closed()
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
    consent, sync = rig.open(install=other)
    assert consent["type"] == "consent" and consent["id"] != sent[0]["id"]
    assert (consent["usage"], consent["at"]) == (True, sent[0]["at"])
    assert sync == {"type": "learning_sync"}


def test_signing_out_drops_what_waits_so_the_next_account_gets_none_of_it() -> None:
    """Project 042, Low 12: learning and usage events made before signing
    out went to whichever account signed in next on this PC. Dropped; the
    consent choice is this PC's and goes to the next account as a new
    install's."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=True)
    rig.answer(rig.open())
    rig.exchange.heard(protocol.LearningState(cursor="50"))
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT))  # offline, say: never sent
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})

    assert [w.kind for w in rig.outbox.waiting()] == ["learning", "exposures"]
    rig.exchange.drop_waiting()

    assert not rig.exchange.has_waiting()
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"  # the next sign-in's
    consent, sync = rig.open(install=other)
    assert consent["type"] == "consent" and consent["usage"] is True
    assert sync == {"type": "learning_sync"}  # from the start
    assert rig.exchange.consent is not None


MINE = "4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e"
ANOTHER = "9b1d3f5a-7c9e-4b2d-8f0a-6c8e0a2c4e6f"


def test_another_account_gets_nothing_of_the_last_ones() -> None:
    """polyglotic-hq 208: an account can change without signing out - the
    server refusing this PC's token, then a new invite code; or, before
    server #205, "I have a code" opening a new account. Signing out's
    safeguard runs when the session opens: what waited is dropped and the
    session starts as a new install's, before anything is sent."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=True)
    rig.answer(rig.open(account=MINE))
    rig.exchange.heard(protocol.LearningState(cursor="50"))
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT))  # offline, say: never sent
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 2}})
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)

    consent, sync = rig.open(account=ANOTHER)  # the same install id

    assert consent["type"] == "consent" and consent["usage"] is True
    assert sync == {"type": "learning_sync"}  # from the start
    assert [w.kind for w in rig.outbox.waiting()] == ["consent"]  # the new one


def test_the_account_last_listened_as_is_known_before_a_session_opens() -> None:
    """polyglotic-hq 223: Account quotes the account's ID, which came only
    from a session's `welcome` - so a start refused at `hello` (Plus has
    ended) showed none. What the last `welcome` said is kept, across a
    restart, until signing out."""
    outbox = SqliteOutbox(":memory:")
    rig = Rig(outbox)
    assert rig.exchange.account is None
    rig.answer(rig.open(account=MINE))
    rig.exchange.closed()
    assert Rig(outbox).exchange.account == MINE  # the next start: no session yet
    rig.exchange.drop_waiting()  # signing out
    assert rig.exchange.account is None


def test_the_same_account_keeps_what_waits() -> None:
    rig = Rig()
    rig.answer(rig.open(account=MINE))
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT))
    assert types(rig.open(account=MINE)) == ["learning", "learning_sync"]


def test_a_server_that_doesnt_name_the_account_changes_nothing() -> None:
    rig = Rig()
    rig.answer(rig.open(account=MINE))
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT))
    assert types(rig.open(account=None)) == ["learning", "learning_sync"]
    rig.exchange.closed()
    rig.exchange.learning(WordSaved(WORD, AT))
    assert types(rig.open(account=MINE)) == ["learning", "learning_sync"]


def test_after_signing_out_the_next_account_gets_whats_made_since() -> None:
    """Signing out drops what waited already; what's made after it waits for
    whoever signs in next, as before 208."""
    rig = Rig()
    rig.answer(rig.open(account=MINE))
    rig.exchange.closed()
    rig.exchange.drop_waiting()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    other = "9f8e7d6c-5b4a-4321-8fed-cba987654321"  # the next sign-in's
    assert types(rig.open(install=other, account=ANOTHER)) == [
        "learning",
        "learning_sync",
    ]


def test_after_signing_out_the_same_install_id_starts_as_a_new_install() -> None:
    """polyglotic-hq 288: the install id outlives signing out now (decision
    0080), so the same code signs this PC in again. A new install id no
    longer marks whoever signs in next; signing out does - else they got no
    consent, and a resync would send learning from before signing out (maybe
    another account's)."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=True)
    rig.answer(rig.open(account=MINE))
    rig.exchange.heard(protocol.LearningState(cursor="50"))
    rig.exchange.closed()
    rig.exchange.drop_waiting()  # signing out

    consent, sync = rig.open(account=ANOTHER)  # the same install id
    assert consent["type"] == "consent" and consent["usage"] is True
    assert sync == {"type": "learning_sync"}  # from the start
    rig.answer([consent])
    rig.exchange.heard(protocol.LearningState(cursor="7"))
    rig.exchange.closed()
    # once: the next session is this install's, as any is
    assert rig.open(account=ANOTHER) == [{"type": "learning_sync", "since": "7"}]


def test_whats_made_after_signing_out_waits_for_the_next_sign_in() -> None:
    rig = Rig()
    rig.exchange.drop_waiting()
    rig.exchange.learning(WordLookedUp(WORD, AT))
    assert types(rig.open()) == ["learning", "learning_sync"]


def test_consent_missing_sends_the_consent_again() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.answer(rig.open())
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    (usage,) = rig.more()
    rig.exchange.heard(protocol.Error(code="consent_missing"))
    (consent,) = rig.more()
    assert consent["type"] == "consent" and consent["usage"] is True
    rig.exchange.closed()
    assert types(rig.open()) == ["consent", "usage", "learning_sync"]
    assert usage["type"] == "usage"


def test_consent_missing_names_the_batch_which_goes_again_once_consent_is_in() -> None:
    """project 034: the server names the refused batch. It stops holding a
    place among the messages awaiting an answer, and goes again after the
    consent sent again is received - once a session."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.answer(rig.open())
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    (usage,) = rig.more()
    refused = protocol.Error(code="consent_missing", batch=usage["batch"])
    rig.exchange.heard(refused)
    (consent,) = rig.more()  # the usage waits for the consent
    assert consent["type"] == "consent"
    rig.answer([consent])
    (again,) = rig.more()
    assert again["type"] == "usage" and again["events"] == usage["events"]
    rig.exchange.heard(protocol.Error(code="consent_missing", batch=again["batch"]))
    # refused again: not sent again this session, and the consent went today
    assert rig.more() == []
    rig.exchange.heard(protocol.LearningState(cursor="1"))
    assert rig.exchange.settled()  # a sync session can close; it waits for the next
    rig.exchange.closed()
    assert types(rig.open()) == ["usage", "learning_sync"]


def test_a_refused_batch_frees_its_place_for_learning_data() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.answer(rig.open(usage_events=1))
    for n in range(AWAITING_MAX):
        rig.exchange.usage("caption_rated", {"thumbs": "up", "n": n}, AT)
    usage = rig.more()
    assert len(usage) == AWAITING_MAX  # one event a batch: every place taken
    rig.exchange.learning(WordLookedUp(WORD, AT))
    assert rig.more() == []
    rig.exchange.heard(protocol.Error(code="consent_missing", batch=usage[0]["batch"]))
    (consent,) = rig.more()  # in the refused batch's place (before: no place at all)
    rig.answer([consent])
    assert types(rig.more()) == ["learning"]
    rig.answer(usage[1:2])
    (again,) = rig.more()
    assert again["events"] == usage[0]["events"]  # the refused event, again


# --- polyglotic-hq 311: two choices at one instant ------------------------------------


class ServerBefore311:
    """What the server did with consent and usage before polyglotic-hq 311
    (v0.1.2, live on 2026-11-14): the latest choice is the one with the
    latest `at` - of two at the same millisecond, the first stored - and
    usage is kept only if it says yes."""

    def __init__(self) -> None:
        self.choices: list[dict[str, Any]] = []
        self.kept: list[str] = []  # usage event ids

    def answer(self, message: dict[str, Any]) -> protocol.Message | None:
        if message["type"] == "consent":
            self.choices.append(message)
            return protocol.Received(id=message["id"])
        if message["type"] == "usage":
            latest = max(self.choices, key=lambda c: c["at"], default=None)
            if latest is None or not latest["usage"]:
                return protocol.Error(code="consent_missing", batch=message["batch"])
            self.kept += [e["id"] for e in message["events"]]
            return protocol.Received(batch=message["batch"])
        if message["type"] == "learning_sync":
            return protocol.LearningState(cursor="1")
        return None


def a_session(rig: Rig, server: ServerBefore311) -> list[dict[str, Any]]:
    """One session: what the app sends, each answered as `server` answers
    it, until nothing more goes; everything sent."""
    sent: list[dict[str, Any]] = []
    out = rig.open()
    while out:
        sent += out
        for message in out:
            answer = server.answer(message)
            if answer is not None:
                rig.exchange.heard(answer)
        out = rig.more()
    rig.exchange.closed()
    return sent


def test_a_new_choice_is_dated_after_the_one_it_replaces_whatever_the_clock_says() -> (
    None
):
    rig = Rig()
    rig.now = AT + timedelta(microseconds=900)  # 09:15:02.120900
    first = rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    assert first.at == rig.now
    # the next tick of a coarse clock: the same millisecond
    second = rig.exchange.choose_consent(usage=True, crashes=True, exposures=False)
    assert protocol.at(second.at) == "2026-11-04T09:15:02.121Z"
    rig.now = AT - timedelta(hours=1)  # the clock set back
    third = rig.exchange.choose_consent(usage=False, crashes=True, exposures=False)
    assert protocol.at(third.at) == "2026-11-04T09:15:02.122Z"
    rig.now = AT + timedelta(minutes=5)  # a clock ahead of them all: as it says
    fourth = rig.exchange.choose_consent(usage=True, crashes=True, exposures=False)
    assert fourth.at == rig.now
    sent = [m for m in rig.open() if m["type"] == "consent"]
    assert [m["at"] for m in sent] == [
        "2026-11-04T09:15:02.120Z",
        "2026-11-04T09:15:02.121Z",
        "2026-11-04T09:15:02.122Z",
        "2026-11-04T09:20:02.120Z",
    ]


def test_an_alpha_testers_first_run_counts_on_a_server_before_311() -> None:
    """The first run's choice (usage off), then "diagnostics on" for an alpha
    tester, on one clock tick: the second goes a millisecond later, so even
    the server before 311 takes it as the latest."""
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    rig.exchange.choose_consent(usage=True, crashes=True, exposures=False)
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    server = ServerBefore311()
    a_session(rig, server)
    assert [c["usage"] for c in server.choices] == [False, True]
    assert len(server.kept) == 1


def test_the_affected_pcs_tie_on_a_server_before_311_the_choice_goes_once_a_day(
    tmp_path: Any,
) -> None:
    """The PC as it was on 2026-11-14: both choices kept at one instant, on
    the PC and on the server, which takes the "off". This app can't change
    that (the choices are the user's, at the time they were made); it
    sends the latest once a day instead of every session - the server's
    fix (311) is what lets the usage in."""
    outbox = SqliteOutbox(tmp_path / "outbox.sqlite")
    server = ServerBefore311()
    for choice_id, usage in (("first-run", False), ("diagnostics-on", True)):
        # as the app before 311 kept and sent them
        outbox.save_consent(ConsentChoice(choice_id, AT, usage, usage, False))
        message = {"id": choice_id, "at": protocol.at(AT), "usage": usage}
        server.choices.append(message)
    rig = Rig(outbox)
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    first = a_session(rig, server)  # this app's first: a new install here
    # its choice as a new install's, then once for consent_missing - both as
    # the user made it, at the instant it was made
    assert [m["at"] for m in first if m["type"] == "consent"] == [protocol.at(AT)] * 2
    for session in range(1, 13):  # a sync session every ten minutes, two hours
        rig.now = AT + timedelta(minutes=10 * session)
        sent = a_session(rig, server)
        assert "usage" in types(sent)  # tried, refused
        assert "consent" not in types(sent)  # not again today
    assert server.kept == []
    rig.now = AT + timedelta(days=1)  # a day after: once more, the same choice
    sent = a_session(rig, server)
    assert [m["at"] for m in sent if m["type"] == "consent"] == [protocol.at(AT)]
    assert server.kept == []  # the tie stays: the server's fix lets it in
    assert len(server.choices) == 2 + 2 + 1  # one a day, not two a session


def test_consent_missing_sends_nothing_for_what_the_choice_no_longer_allows() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=True)
    rig.answer(rig.open())
    rig.exchange.exposures({date(2026, 11, 3): {WORD: 4}})
    (exposures,) = rig.more()
    rig.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    (consent,) = rig.more()  # the "no"
    rig.answer([consent])
    # the batch sent before it, refused: the "no" doesn't allow it, so the
    # choice doesn't go again (before 311 it did, whatever was refused)
    refused = protocol.Error(code="consent_missing", batch=exposures["batch"])
    rig.exchange.heard(refused)
    assert rig.more() == []


def test_the_consent_goes_again_once_a_day_for_each_install() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.answer(rig.open())
    rig.exchange.heard(protocol.Error(code="consent_missing"))  # no batch named
    (again,) = rig.more()
    rig.answer([again])
    rig.exchange.closed()
    rig.open()
    rig.exchange.heard(protocol.Error(code="consent_missing"))
    assert rig.more() == []  # this install's, today
    rig.exchange.closed()
    other = "6f1d2c3b-4a59-4e8f-9a0b-1c2d3e4f5a6b"  # a new invite code
    opened = rig.open(install=other)
    assert types(opened) == ["consent", "learning_sync"]  # as a new install's
    rig.answer(opened)
    rig.exchange.heard(protocol.Error(code="consent_missing"))
    resent = rig.more()
    assert types(resent) == ["consent"]  # another install's first time
    rig.answer(resent)
    rig.exchange.closed()
    rig.now = AT - timedelta(hours=2)  # the clock set back: not held back by it
    assert types(rig.open(install=other)) == ["learning_sync"]
    rig.exchange.heard(protocol.Error(code="consent_missing"))
    assert types(rig.more()) == ["consent"]


@pytest.mark.parametrize("kind", ["consent", "learning", "usage"])
def test_whats_kept_survives_closing_the_app(tmp_path: Any, kind: str) -> None:
    path = tmp_path / "outbox.sqlite"
    rig = Rig(SqliteOutbox(path))
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.exchange.learning(WordSaved(WORD, AT))
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    rig.outbox.close()
    after = Rig(SqliteOutbox(path))
    assert after.exchange.consent is not None and after.exchange.consent.usage
    assert kind in types(after.open())


def test_words_that_arrive_while_the_dictionary_is_out_arrive_again_once_whole() -> (
    None
):
    """A word saved on another PC while this PC's dictionary is out
    (polyglotic-hq 199) is left out - it can't be described - yet the
    cursor moves past it. The first start with the dictionary whole again
    syncs it from the start, once; the other language's cursor is kept."""
    outbox = SqliteOutbox(":memory:")
    english = Rig(outbox, "ecdict")
    english.open()
    english.exchange.heard(state("40", ENGLISH))
    english.exchange.closed()

    out = Rig(outbox)
    out.exchange.dictionary_out()
    out.open()
    out.exchange.heard(state("50", "cedict:y7p98nwvxq"))  # left out here
    out.exchange.dictionary_out()  # found again mid-session: noted once
    out.exchange.closed()

    still = Rig(outbox)
    still.exchange.dictionary_out()  # still out at the next start
    assert still.open()[-1] == {"type": "learning_sync", "since": "50"}
    still.exchange.heard(state("60"))
    still.exchange.closed()

    whole = Rig(outbox)
    whole.exchange.dictionary_whole()  # repaired
    assert whole.open()[-1] == {"type": "learning_sync"}  # from the start
    whole.exchange.heard(state("70", "cedict:y7p98nwvxq"))
    assert {e.entry_id for e in whole.heard.arrived} == {"cedict:y7p98nwvxq"}
    whole.exchange.closed()

    again = Rig(outbox)
    again.exchange.dictionary_whole()
    assert again.open()[-1] == {"type": "learning_sync", "since": "70"}  # once
    assert Rig(outbox, "ecdict").open()[-1] == {
        "type": "learning_sync",
        "since": "40",
    }


def test_a_dictionary_never_out_keeps_its_cursor() -> None:
    outbox = SqliteOutbox(":memory:")
    first = Rig(outbox)
    first.open()
    first.exchange.heard(state("50"))
    first.exchange.closed()
    second = Rig(outbox)
    second.exchange.dictionary_whole()
    assert second.open()[-1] == {"type": "learning_sync", "since": "50"}


def test_new_learning_data_syncs_from_the_start_once() -> None:
    """Learning data on this PC started afresh - its file set aside because
    it couldn't be read (polyglotic-hq 206) - gets what the server keeps
    back: the cursor, kept in the outbox, is forgotten once. Another
    language's cursor is kept."""
    outbox = SqliteOutbox(":memory:")
    english = Rig(outbox, "ecdict")
    english.open()
    english.exchange.heard(state("40", ENGLISH))
    english.exchange.closed()
    first = Rig(outbox)
    first.open()
    first.exchange.heard(state("50", WORD))
    first.exchange.closed()

    new = Rig(outbox)
    new.exchange.learning_data_new()
    assert new.open()[-1] == {"type": "learning_sync"}  # from the start
    new.exchange.heard(state("60", WORD))
    assert {e.entry_id for e in new.heard.arrived} == {WORD}
    new.exchange.closed()

    again = Rig(outbox)
    assert again.open()[-1] == {"type": "learning_sync", "since": "60"}  # once
    assert Rig(outbox, "ecdict").open()[-1] == {
        "type": "learning_sync",
        "since": "40",
    }


def test_rows_this_version_cant_read_are_dropped_counted_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """polyglotic-hq 557 (529's B2): a learning event, exposure day or usage
    event another version wrote that this one can't read raised at every
    session's open, and the listening session stopped. Each is dropped from
    the outbox and counted (`unreadable_dropped`); the rest still go, and
    the log says the kind and how many - never what they held."""
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=True)
    rig.exchange.learning(WordLookedUp(WORD, AT))
    rig.exchange.usage("caption_rated", {"thumbs": "up"}, AT)
    secret = '{"entry_id": "cedict:secret", "kind": "from_the_future"}'
    for kind, item_id in (("learning", "l-bad"), ("usage", "u-bad")):
        rig.outbox.add(Waiting(kind, item_id, secret), 100)
    rig.outbox.add(Waiting("exposures", "e-bad", "not JSON at all"), 100)
    with caplog.at_level(logging.WARNING, logger="polyglotic_desktop.connection"):
        sent = rig.open()
    assert types(sent) == ["consent", "learning", "usage", "learning_sync"]
    assert len(sent[1]["events"]) == 1 and len(sent[2]["events"]) == 1
    assert {w.id for w in rig.outbox.waiting()}.isdisjoint({"l-bad", "u-bad", "e-bad"})
    assert rig.outbox.note("unreadable_dropped") == "3"
    said = [r.getMessage() for r in caplog.records]
    assert "1 waiting learning item(s) this version can't read dropped (1 ever)" in said
    assert "1 waiting usage item(s) this version can't read dropped (3 ever)" in said
    assert not any("secret" in line for line in said)


def test_rows_dropped_unread_go_in_the_next_summary_once() -> None:
    """polyglotic-hq 566: the listening session's summary counts the rows
    dropped unread since the last summary - those dropped as the app
    started, before any listening, too - each once. Kept in the outbox's
    notes, so a restart of the app doesn't lose or repeat them."""
    rig = Rig()
    assert rig.exchange.take_unreadable() == 0
    for item_id in ("l-bad", "l-worse"):
        rig.outbox.add(Waiting("learning", item_id, "not JSON at all"), 100)
    rig.open()  # a sync session as the app starts drops them
    assert rig.exchange.take_unreadable() == 2
    assert rig.exchange.take_unreadable() == 0
    assert Rig(rig.outbox).exchange.take_unreadable() == 0  # the app started again
    rig.outbox.save_note("unreadable_dropped", "1")  # the notes started again
    assert rig.exchange.take_unreadable() == 0
    rig.outbox.save_note("unreadable_dropped", "4")
    assert rig.exchange.take_unreadable() == 3


@pytest.mark.parametrize("kept", ["{not JSON", '["a list"]', "null", '{"cedict": 40}'])
def test_damaged_cursors_start_again_once_and_the_session_opens(
    kept: str, caplog: pytest.LogCaptureFixture
) -> None:
    """polyglotic-hq 566 (from 557): the cursors are JSON in the outbox's
    notes, read with no try. One damaged on disk raised at every session's
    open - after decision 0266 every minute, for good. It is cleared and
    said once by its name, and the dictionary syncs from the start."""
    outbox = SqliteOutbox(":memory:")
    first = Rig(outbox)
    first.open()
    first.exchange.heard(state("50"))
    first.exchange.closed()
    outbox.save_note("learning_cursors", kept)
    rig = Rig(outbox)
    with caplog.at_level(logging.WARNING, logger="polyglotic_desktop.connection"):
        assert rig.open()[-1] == {"type": "learning_sync"}  # from the start
        rig.exchange.heard(state("60"))
        rig.exchange.closed()
        assert Rig(outbox).open()[-1] == {"type": "learning_sync", "since": "60"}
    said = [r.getMessage() for r in caplog.records]
    assert said == [
        "the outbox's learning_cursors note couldn't be read; started again"
    ]


@pytest.mark.parametrize("kept", ["[not JSON", '{"cedict": 1}', "null", "[1, 2]"])
def test_damaged_dictionaries_out_start_again_and_every_cursor_with_them(
    kept: str, caplog: pytest.LogCaptureFixture
) -> None:
    """566: the dictionaries out since their last sync, damaged, raised as
    the app started (`dictionary_whole`) and at every open. Which were out
    is lost, so every dictionary syncs from the start, once: none misses a
    word saved elsewhere while it was out."""
    outbox = SqliteOutbox(":memory:")
    english = Rig(outbox, "ecdict")
    english.open()
    english.exchange.heard(state("40", ENGLISH))
    english.exchange.closed()
    outbox.save_note("learning_dictionaries_out", kept)
    rig = Rig(outbox)
    with caplog.at_level(logging.WARNING, logger="polyglotic_desktop.connection"):
        rig.exchange.dictionary_whole()
        assert rig.open()[-1] == {"type": "learning_sync"}
        rig.exchange.dictionary_out()  # noted again as it should be
        rig.exchange.closed()
    assert Rig(outbox, "ecdict").open()[-1] == {"type": "learning_sync"}
    assert outbox.note("learning_dictionaries_out") == '["cedict"]'
    said = [r.getMessage() for r in caplog.records]
    assert said == [
        "the outbox's learning_dictionaries_out note couldn't be read; started again"
    ]
