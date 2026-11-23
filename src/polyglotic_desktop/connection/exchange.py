"""Learning data, consent, usage and exposures: kept until the server has them, sent on any session.

protocol.md: the app keeps `learning`, `exposures` and `usage` messages
until the server answers `received` for their batch, and `consent` until
`received` for its id, and sends them again after a reconnect (the server
ignores what it already has). `DataExchange` does that through the
`Outbox` port, so what's waiting survives going offline, refusals and
closing the app:
- **in** (any thread): the user's consent choices, Learning's events,
  usage events, finished days' exposure counts, a request to delete the
  learning data;
- **out** (on a session's thread): when a session opens, everything
  waiting - consent first, then a deletion, learning events, exposures,
  usage - in batches within `welcome.limits`, then `learning_sync` from
  the kept cursor; more as answers come back (a few messages awaiting an
  answer at a time); `learning_state` and `learning_deleted` go to the
  app's `ExchangeListener`.

The learning data open on this PC is one language's - one dictionary's
entries (`learning.sqlite` for Chinese, `learning-en.sqlite` for
English). An account learning both gets both dictionaries' entries in
`learning_state`, so only the open dictionary's are handed over, and the
sync cursor is kept per dictionary: entries passed over while one
language was open still arrive when the learner switches to the other.
Nothing is sent back about the entries passed over, so the other
language's statuses and saved words stay as they are on the server.

**A deletion reaches every device** (polyglotic-server protocol.md, project
051): each `learning_state` names the account's latest deletion of its
learning data, from whichever device. One this PC hasn't applied yet
drops what waits from before it - learning events dated at or before it,
exposure days up to its UTC date - and syncs again from the start (a
cursor from before a deletion may skip changes made after it); nothing
from before it is sent afterwards either. The learner's copy on this PC
stays: deleting it is their choice, here as on the PC the deletion came
from.

**What this PC does after a deletion is after it, whatever its clock**
(project 061, from 059's Low 3; decision 0023). The deletion's time is
the server's clock, a learning event's this PC's: on a PC whose clock is
behind, an event made just after the deletion is stamped before it, and
the server drops it. So "after" is judged by this PC's own clock, from
when it asked to delete (on the PC that deleted) or when it applied the
deletion (on any other): an event made since then is sent stamped just
after the deletion if its own stamp is at or before it - each a
millisecond after the last so raised, so the latest still wins. On the
PC that deleted, learning events wait from the request until the
deletion's time is known (it asks for `learning_sync` as soon as the
deletion is answered), so a request waiting offline loses nothing done
meanwhile either. What's left: another device's events made after the
deletion but before it heard of it, stamped before it by a slow clock,
are still dropped.

**After the server's store is restored, this PC sends its learning state
again** (polyglotic-hq project 166; protocol.md, `welcome.learning_epoch`).
A restore from a backup loses what was sent since the backup, and only new
events are sent - so a `welcome` naming an epoch other than the one kept
for the open dictionary makes this PC send its whole learning state once
(`whole_state`: every status the learner set, every saved word, each at
its own time) in `learning` batches as usual, and sync that dictionary
from the start (its cursor counted the old store's changes). The epoch is
kept only once every batch is `received`; a resync cut short goes again
next session (the server keeps the latest `at` and ignores an id it has,
so sending twice is harmless). It is held in memory, not in the outbox,
so it never pushes out what waits there. What's sent follows the deletion
rules above - nothing from before the latest deletion - and is only what
this PC did since it became this install: learning data on the PC from
before a new invite code may be another account's. Lookups and exposure
days aren't sent again: this PC doesn't keep them once they're sent.

**New learning data on this PC syncs from the start** (polyglotic-hq
206). The cursors are kept in the outbox, apart from the learning data, so
a learning data file started afresh - its old one set aside because it
couldn't be read, or deleted by hand - would otherwise get only what
changed since. `learning_data_new` forgets the open dictionary's cursor at
the start, and the session's `learning_sync` brings back what the server
keeps: every status the learner set and every saved word (a word in the
deck is `learning`). What it doesn't keep - a saved word's sentence and
category, the line a word went into the deck with, exposure counts, the
level, what was exported to Anki - stays in the file set aside.

**What arrives while this PC's dictionary is out arrives again once it's
whole** (polyglotic-hq 199). A word saved on another PC is described from
this PC's dictionary; while it's out (missing or damaged), the word is
left out, yet the cursor moves past it. So the dictionary being out is
noted (`dictionary_out`), and the first start with it whole again
(`dictionary_whole`) syncs that dictionary from the start, once: what was
left out arrives, and what's here already isn't applied again (the
latest `at` wins; a saved word already saved is kept).

Consent rules here, so nothing optional leaves the PC without it: usage
events are kept only while the user says yes to usage statistics, and
exposure counts only while they say yes to sharing them; saying no drops
what's waiting of that kind. Learning events and consent are service data,
sent whatever was chosen (protocol.md). A new install id (a new invite
code) gets the consent again and syncs from the start - and so does a
session after signing out: the install id outlives signing out now
(polyglotic-hq 288, decision 0080), yet whoever signs in next may be
another account.

**A new consent choice is dated after the one it replaces, and goes again
at most once a day** (polyglotic-hq 311, decision 0102). The server takes
the choice with the latest `at` as the latest; two choices one clock tick
apart (an alpha tester's first run, then "diagnostics on") had the same
millisecond, and the server kept the first. So a new choice is dated at
least a millisecond after the one it replaces, whatever the clock says.
And `consent_missing` sends the choice again only if it allows what was
refused, once a day for the install: sent every session, it grew one
install's history on the server by two choices a sync session.

**Another account, however it came, gets nothing of the last one's**
(polyglotic-hq 208). Signing out drops what waits (`drop_waiting`), but an
account can change without it: the server refusing this PC's token
(`auth_failed`), then a new invite code; or a code that opened a new
account while signed in (203's item 1, before server #205). So the
account each `welcome` names is noted, and a session opening on a
different one runs signing out's safeguard first - what waited is dropped
- and starts as a new install, before anything is sent.

**A row this version can't read is dropped and counted** (polyglotic-hq
557, 529's B2; decision 0266). Learning events, exposure days and usage
events are read back from the outbox to send; one written by another
version that this one can't read (a field it doesn't know, a value it
won't take) raised at every session's open, and the listening session
stopped for good. Such a row is dropped from the outbox, logged by kind
and count, and counted in the outbox's notes (`unreadable_dropped`) - and
in the next listening session's summary (`take_unreadable`, polyglotic-hq
566), so it's seen without a tester's log.

**A note it can't read starts again, said once** (polyglotic-hq 566, from
557). The cursors and the dictionaries out are JSON in the outbox's notes;
one damaged on disk raised wherever it was read - as the app started
(`dictionary_whole`) and at every session's open, which after decision
0266 tries again every minute, for good. Now such a note is cleared and
logged by its name: the cursors forgotten (each dictionary syncs from the
start, once), and with the dictionaries out every cursor too, since which
were out is lost.

Logs counts and kinds only - never entry IDs, props or the token.
"""

import json
import logging
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, TypeVar

from pydantic import BaseModel

from polyglotic_desktop.connection import learning, protocol
from polyglotic_desktop.core.shared import LearningEvent
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice, ConsentStore
from polyglotic_desktop.ports.outbox import Outbox, Waiting

log = logging.getLogger(__name__)

_Row = TypeVar("_Row", bound=BaseModel)

CONSENT = "consent"
DELETE = "learning_delete"
LEARNING = "learning"
EXPOSURES = "exposures"
USAGE = "usage"
ORDER = (CONSENT, DELETE, LEARNING, EXPOSURES, USAGE)
"""The order things go out in when a session opens: the consent before the
usage it allows, a deletion before the events that come after it."""

KEEP = {CONSENT: 50, DELETE: 1, LEARNING: 10_000, EXPOSURES: 186, USAGE: 1_000}
"""At most this many of each kind wait on the PC; past it, the oldest go.
Exposures wait as days or parts of days: two months of days, in up to
three parts each."""

EXPOSURE_ENTRIES = 5_000
"""protocol.md: at most this many entries of one day in a message."""

AWAITING_MAX = 8
"""Messages awaiting `received` at once: more go as answers come, so a
long wait offline doesn't burst past the server's message rate."""

ROOM_BYTES = 1024
"""Kept free under `limits.text_message_bytes` when filling a batch."""

_INSTALL = "install_id"  # the install the cursors and consent belong to
_CURSORS = "learning_cursors"  # JSON: dictionary -> its learning_sync cursor
_DELETION = "learning_deletion"  # JSON: the account's latest deletion applied here
_ASKED = "learning_delete_asked"  # when this PC asked to delete, until it's applied
_AFTER = "learning_after_deletion"  # JSON: see _After
_EPOCHS = "learning_epochs"  # JSON: dictionary -> the server epoch it was resent to
_INSTALLED = "install_started"  # when this PC became this install (its clock)
_OUT = "learning_dictionaries_out"  # JSON: dictionaries out since their last sync
_ACCOUNT = "account_id"  # the account what waits belongs to, from `welcome`
_SIGNED_OUT = "signed_out"  # signed out since this install last had a session
_UNREADABLE = "unreadable_dropped"  # rows this version couldn't read, dropped ever
_UNREADABLE_TOLD = "unreadable_told"  # how many of those a summary has counted
_AGAIN = "consent_sent_again"  # JSON: the install, and when, after consent_missing

RAISED = timedelta(milliseconds=1)
"""How far past the deletion (or the last event so raised) an event this
PC made after it is stamped, when its clock put it at or before: the
protocol's times are to the millisecond. A new consent choice is dated at
least this far past the one it replaces, too."""

AGAIN_EVERY = timedelta(days=1)
"""The consent goes again after `consent_missing` at most once in this long
for an install (polyglotic-hq 311): 24 hours by this PC's clock, not a
calendar day, so no time zone enters."""


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class _After:
    """From when this PC's learning events count as after the latest
    deletion (`since`, by this PC's clock), and the latest time one of them
    is stamped with past it (`floor`: the deletion's time, then each event
    raised past it)."""

    since: datetime
    floor: datetime


class ExchangeListener(Protocol):
    """What the server's answers mean for the app, on a session's thread."""

    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        """Statuses and saved words as the server has them (from another
        PC, too): apply them without publishing them again."""
        ...

    def learning_deleted(self) -> None:
        """The server has deleted the learning data."""
        ...


class DataExchange:
    def __init__(
        self,
        outbox: Outbox,
        consents: ConsentStore,
        listener: ExchangeListener,
        dictionary: str,
        *,
        whole_state: Callable[[], Sequence[LearningEvent]] = lambda: (),
        new_id: Callable[[], str] = _new_id,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """`dictionary` is the open learning data's (`cedict` or `ecdict`):
        only its entries are taken from `learning_state`, and it syncs from
        its own cursor. `whole_state` gives that learning data's every
        learner-set status and saved word, for sending again after the
        server's store was restored (called on a session's thread)."""
        self._outbox = outbox
        self._consents = consents
        self._listener = listener
        self._dictionary = dictionary
        self._whole_state = whole_state
        self._new_id = new_id
        self._clock = clock
        self._lock = threading.RLock()
        self._consent = consents.consent()
        self._limits = protocol.Limits()
        self._awaiting: dict[str, list[str]] = {}  # batch or consent id -> item ids
        self._sent: set[str] = set()  # item ids awaiting an answer
        self._refused: list[str] = []  # refused for want of consent, held back
        self._released = False  # refused items already sent again this session
        self._sync_wanted = False  # a learning_sync to send
        self._syncing = False  # learning_sync sent, its learning_state not in
        self._synced_from: str | None = None  # that learning_sync's cursor
        self._deleted = _deletion(outbox.note(_DELETION))  # applied here
        self._asked = _moment(outbox.note(_ASKED))  # this PC's, not yet applied
        self._after = _after(outbox.note(_AFTER))
        self._resync: list[Waiting] = []  # the learning state to send again
        self._resyncing: set[str] = set()  # its batches awaiting `received`
        self._resync_epoch: str | None = None  # the epoch it's sent for
        self.wake: Callable[[], None] = lambda: None
        """Called (outside the lock) when something new waits; the
        connection opens a session or tells the open one."""

    # --- From the app, any thread ------------------------------------------------

    @property
    def consent(self) -> ConsentChoice | None:
        return self._consent

    @property
    def account(self) -> str | None:
        """The account this PC last listened as, noted from `welcome` and
        kept across restarts; None before the first session, or since
        signing out. Account shows it before a session opens - a start
        whose `hello` is refused because Plus has ended opens none, and
        the learner was left with no ID to quote (polyglotic-hq 223)."""
        noted = self._outbox.note(_ACCOUNT)
        return noted if isinstance(noted, str) else None

    def choose_consent(
        self,
        usage: bool,
        crashes: bool,
        exposures: bool,
        agreement: Agreement | None = None,
    ) -> ConsentChoice:
        """The user's choices (first run, or settings): kept, sent to the
        server, and followed at once - a "no" drops what's waiting.
        `agreement`: the tester agreement just accepted; None keeps the one
        accepted before, so every choice says which agreement this PC is
        under (polyglotic-hq 185). Dated after the choice it replaces,
        whatever the clock says (`_dated_after`)."""
        with self._lock:
            at = self._clock()
            if self._consent is not None:
                at = _dated_after(self._consent.at, at)
                if agreement is None:
                    agreement = self._consent.agreement
            choice = ConsentChoice(
                self._new_id(), at, usage, crashes, exposures, agreement
            )
            self._consents.save_consent(choice)
            self._consent = choice
            self._add(CONSENT, choice.id, _consent_message(choice))
            if not usage:
                self._outbox.remove_kind(USAGE)
            if not exposures:
                self._outbox.remove_kind(EXPOSURES)
        self.wake()
        return choice

    def learning(self, event: LearningEvent) -> None:
        """One of Learning's events, to send as learning data. Not a usage
        event: lookups and saves are counted in the listening session's
        summary (polyglotic-hq DECISIONS.md #20)."""
        with self._lock:
            at = self._stamp(event.at)
            if at is None:
                return  # from before a deletion: it would bring the data back
            event_id = self._new_id()
            message = learning.learning_event(event, event_id)
            if at != event.at:  # made after the deletion, by a clock behind
                message = message.model_copy(update={"at": protocol.at(at)})
            self._add(LEARNING, event_id, message)
        self.wake()

    def usage(
        self, name: str, props: Mapping[str, protocol.UsageValue], at: datetime
    ) -> bool:
        """A usage event from the tracking plan (version 1), kept to send
        only if the user said yes to usage statistics; whether it was."""
        with self._lock:
            kept = self._usage(name, props, at)
        if kept:
            self.wake()
        return kept

    def exposures(self, days: Mapping[date, Mapping[str, int]]) -> bool:
        """Finished UTC days' exposure counts, kept to send only if the user
        said yes to sharing them; whether they were. A day too big for one
        message waits in parts."""
        with self._lock:
            if self._consent is None or not self._consent.exposures:
                return False
            room = self._limits.text_message_bytes - ROOM_BYTES
            for day, counts in sorted(days.items()):
                if self._deleted is not None and day <= _utc_day(self._deleted[1]):
                    continue  # partly or wholly from before the deletion
                exposure_day = learning.exposure_day(day, counts)
                for part in _parts(exposure_day, room):
                    self._add(EXPOSURES, self._new_id(), part)
        self.wake()
        return True

    def delete_learning(self) -> None:
        """The user deletes their learning data from the server: learning
        events and exposure days not yet sent are dropped (they'd only add
        it back), the request waits like the rest, and syncing starts again
        from the beginning - for every language: the server deletes the
        account's learning data in all of them (protocol.md). Learning
        events made from now wait until the deletion's time is known."""
        with self._lock:
            self._outbox.remove_kind(LEARNING)
            self._outbox.remove_kind(EXPOSURES)
            self._add(DELETE, self._new_id(), protocol.LearningDelete())
            self._outbox.save_note(_CURSORS, None)
            self._asked = self._clock()
            self._outbox.save_note(_ASKED, self._asked.isoformat())
        self.wake()

    def dictionary_out(self) -> None:
        """The open dictionary is out (missing or damaged, polyglotic-hq
        199): words saved elsewhere that arrive now can't be taken in, so
        the next start with it whole syncs it from the start. Any thread."""
        with self._lock:
            out = self._dictionaries_out()
            if self._dictionary not in out:
                out.add(self._dictionary)
                self._outbox.save_note(_OUT, json.dumps(sorted(out)))

    def dictionary_whole(self) -> None:
        """At the start, with the open dictionary whole: if it was out since
        its last sync, its cursor is forgotten - this session's
        `learning_sync` asks for its whole learning state, once. Call it
        before a session opens."""
        with self._lock:
            out = self._dictionaries_out()
            if self._dictionary not in out:
                return
            self._sync_from_the_start()
            out.discard(self._dictionary)
            self._outbox.save_note(_OUT, json.dumps(sorted(out)) if out else None)

    def learning_data_new(self) -> None:
        """At the start, when the open dictionary's learning data on this
        PC is new - created now, or its file set aside because it couldn't
        be read (polyglotic-hq 206): its cursor is forgotten, so this
        session's `learning_sync` asks for the whole learning state, once,
        and what the server keeps comes back. Call it before a session
        opens."""
        with self._lock:
            self._sync_from_the_start()

    def _sync_from_the_start(self) -> None:
        """The open dictionary's cursor forgotten (the lock held)."""
        cursors = self._cursors()
        if cursors.pop(self._dictionary, None) is not None:
            self._outbox.save_note(_CURSORS, json.dumps(cursors, sort_keys=True))

    def _dictionaries_out(self) -> set[str]:
        """The dictionaries out since their last sync. A note that can't be
        read is started again, and every cursor with it: whichever were
        out sync from the start (`_started_again`)."""
        kept = self._outbox.note(_OUT)
        if not kept:
            return set()
        found = _loaded(kept)
        if isinstance(found, list) and all(isinstance(d, str) for d in found):
            return set(found)
        self._started_again(_OUT)
        self._outbox.save_note(_CURSORS, None)
        return set()

    def has_connected(self) -> bool:
        """This PC has had a session with the server, as some install -
        not a new install (the install milestone, project 134)."""
        return self._outbox.note(_INSTALL) is not None

    def has_waiting(self) -> bool:
        """Something waits to be sent."""
        return bool(self._outbox.waiting())

    def drop_waiting(self) -> None:
        """Signing out: everything waiting is dropped - learning events,
        exposures, usage, a deletion, the consent message - so none of it
        goes to whichever account signs in next on this PC (polyglotic-hq
        project 042, Low 12). The consent *choice* stays: it's this PC's,
        and goes to the next account as a new install's. Call it with no
        session open."""
        with self._lock:
            self._drop_waiting()
            self._outbox.save_note(_ACCOUNT, None)  # whoever signs in next
            # the install id outlives signing out (decision 0080): whoever
            # signs in next is still a new install here
            self._outbox.save_note(_SIGNED_OUT, "1")
        log.info("signed out: what waited is dropped")

    def _drop_waiting(self) -> None:
        for kind in ORDER:
            self._outbox.remove_kind(kind)
        self._forget_session()
        self._outbox.save_note(_CURSORS, None)
        self._outbox.save_note(_EPOCHS, None)
        self._forget_deletion()
        self._asked = None  # its request was dropped with the rest
        self._outbox.save_note(_ASKED, None)

    # --- From a session, on its thread -------------------------------------------

    def opened(
        self,
        install_id: str,
        limits: protocol.Limits,
        learning_epoch: str | None = None,
        account_id: str | None = None,
    ) -> list[str]:
        """A session is open (after `welcome`): the messages to send first.
        `learning_epoch` and `account_id` are `welcome`'s (None from a
        server without them)."""
        with self._lock:
            self._forget_session()
            self._limits = limits
            if self._another_account(account_id):
                self._drop_waiting()
                log.info("another account: what waited is dropped")
                self._new_install(install_id)
            elif (
                self._outbox.note(_INSTALL) != install_id
                or self._outbox.note(_SIGNED_OUT) is not None
            ):
                self._new_install(install_id)
            if account_id is not None:
                self._outbox.save_note(_ACCOUNT, account_id)
            if (
                learning_epoch is not None
                and self._epochs().get(self._dictionary) != learning_epoch
            ):
                self._start_resync(learning_epoch)
            self._sync_wanted = True
            return self._next()

    def more(self) -> list[str]:
        """Messages for whatever has come in since."""
        with self._lock:
            return self._next()

    def heard(self, message: protocol.Message) -> None:
        """A message from the server; answers to send are in `more`."""
        arrived: list[LearningEvent] | None = None
        deleted = False
        with self._lock:
            if isinstance(message, protocol.Received):
                key = message.batch or message.id
                ids = self._awaiting.pop(key, None) if key else None
                if key in self._resyncing:  # held in memory, not the outbox
                    self._resyncing.discard(key)
                    self._resync_sent()
                elif ids:
                    self._outbox.remove(ids)
                    self._sent.difference_update(ids)
                if message.id is not None:
                    self._consent_in()
            elif isinstance(message, protocol.LearningState):
                self._keep_cursor(message.cursor)
                arrived = learning.from_state(message, self._dictionary)
                self._syncing = False
                self._sync_wanted = message.more
                new = message.deletion is not None and self._apply(message.deletion)
                if new and self._synced_from is not None:  # again, from the start
                    self._outbox.save_note(_CURSORS, None)
                    self._sync_wanted = True
                if not new and self._asked is not None and not self._delete_waiting():
                    self._release()  # answered, yet no new deletion named
            elif isinstance(message, protocol.Error):
                if message.code == "consent_missing":
                    self._consent_missing(message.batch)
            elif isinstance(message, protocol.LearningDeleted):
                ids = self._awaiting.pop(DELETE, [])
                self._outbox.remove(ids)
                self._sent.difference_update(ids)
                self._sync_wanted = True  # to learn the deletion's number now
                deleted = True
        if arrived:
            self._listener.learning_arrived(arrived)
        if deleted:
            self._listener.learning_deleted()

    def closed(self) -> None:
        """The session ended: what awaited an answer goes again next time."""
        with self._lock:
            self._forget_session()
            self._sync_wanted = False

    def settled(self) -> bool:
        """Nothing waits to be sent and nothing awaits an answer (a sync
        session can close)."""
        with self._lock:
            if self._awaiting or self._syncing or self._sync_wanted or self._resync:
                return False
            return all(w.id in self._sent for w in self._outbox.waiting())

    # --- Inside the lock ------------------------------------------------------------

    def _forget_session(self) -> None:
        self._awaiting.clear()
        self._sent.clear()
        self._resync.clear()  # not kept as sent: it goes again next session
        self._resyncing.clear()
        self._resync_epoch = None
        self._refused.clear()
        self._released = False
        self._syncing = False

    def _add(self, kind: str, item_id: str, message: protocol.Message) -> None:
        self._outbox.add(Waiting(kind, item_id, protocol.encode(message)), KEEP[kind])

    def _usage(
        self, name: str, props: Mapping[str, protocol.UsageValue], at: datetime
    ) -> bool:
        if self._consent is None or not self._consent.usage:
            return False
        event_id = self._new_id()
        event = protocol.UsageEvent(
            id=event_id, name=name, v=1, at=protocol.at(at), props=dict(props)
        )
        self._add(USAGE, event_id, event)
        return True

    def _consent_missing(self, batch: str | None) -> None:
        """The server has no consent for this install that allows what was
        sent (its record lost, say): the latest choice goes again, if it
        allows what was refused - at most once a day for the install
        (`AGAIN_EVERY`; polyglotic-hq 311: an app sending it every session
        grew one install's history by two choices a sync session). The
        refused batch, named since S2b, stops awaiting an answer - it would
        hold one of AWAITING_MAX places until the session ended - and its
        items are held back until the server has a consent, then sent once
        more; refused again, they wait for the next session (no loop with a
        server that keeps refusing). An error that names no batch (an older
        server): what it refused waits for the next session."""
        ids = self._awaiting.pop(batch, None) if batch else None
        if ids:
            self._refused.extend(ids)  # still in _sent: not sent again yet
        waiting = self._outbox.waiting()
        if self._consent is None or any(w.kind == CONSENT for w in waiting):
            return
        refused = {w.kind for w in waiting if w.id in ids} if ids else None
        if not _allows(self._consent, refused) or not self._may_send_again():
            return
        self._send_consent_again(self._consent)
        log.info(
            "the server has no consent allowing what was sent: the choice goes"
            " again (at most once a day)"
        )

    def _may_send_again(self) -> bool:
        """Whether the consent may go again for `consent_missing` now - not
        within `AGAIN_EVERY` of the last time, for this install - noting it
        if so. A last time ahead of this PC's clock (the clock set back)
        doesn't hold it back."""
        install = self._outbox.note(_INSTALL)
        now = self._clock()
        last = _sent_again(self._outbox.note(_AGAIN), install)
        if last is not None and last <= now < last + AGAIN_EVERY:
            return False
        noted = {"install": install, "at": now.isoformat()}
        self._outbox.save_note(_AGAIN, json.dumps(noted))
        return True

    def _consent_in(self) -> None:
        """The server has a consent: what it refused for want of one goes
        again, once a session."""
        if self._refused and not self._released:
            self._sent.difference_update(self._refused)
            self._refused.clear()
            self._released = True

    def _send_consent_again(self, consent: ConsentChoice) -> None:
        again = ConsentChoice(
            self._new_id(),
            consent.at,
            consent.usage,
            consent.crashes,
            consent.exposures,
            consent.agreement,
        )
        self._add(CONSENT, again.id, _consent_message(again))

    def _another_account(self, account_id: str | None) -> bool:
        """The session's account isn't the one what waits belongs to. None
        either way - a server that doesn't say, or nothing noted yet (an
        app before 208, or signed out since) - isn't another account."""
        noted = self._outbox.note(_ACCOUNT)
        return None not in (account_id, noted) and account_id != noted

    def _new_install(self, install_id: str) -> None:
        """A new install (first sign-in, a new invite code, or signed in
        again after signing out): the server may know nothing of it yet -
        its consent goes again, and learning syncs from the start."""
        self._outbox.save_note(_INSTALL, install_id)
        self._outbox.save_note(_SIGNED_OUT, None)
        self._outbox.save_note(_INSTALLED, self._clock().isoformat())
        self._outbox.save_note(_CURSORS, None)
        self._outbox.save_note(_EPOCHS, None)
        self._forget_deletion()  # the deletions applied were another account's
        if self._consent is not None and not any(
            w.kind == CONSENT for w in self._outbox.waiting()
        ):
            self._send_consent_again(self._consent)

    def _next(self) -> list[str]:
        waiting: dict[str, list[Waiting]] = defaultdict(list)
        for item in self._outbox.waiting():
            if item.id not in self._sent:
                waiting[item.kind].append(item)
        out: list[str] = []
        for kind in ORDER:
            if kind == LEARNING and self._asked is not None:
                continue  # until this PC's deletion's time is known: _stamp
            items = waiting[kind]
            while items and len(self._awaiting) < AWAITING_MAX:
                made = self._message(kind, items)
                if made is None:  # none left it could read: dropped
                    break
                key, taken, message = made
                del items[: len(taken)]
                self._awaiting[key] = [w.id for w in taken]
                self._sent.update(w.id for w in taken)
                out.append(message)
        held = self._asked is not None or DELETE in self._awaiting
        while self._resync and not held and len(self._awaiting) < AWAITING_MAX:
            made = self._message(LEARNING, self._resync)
            if made is None:
                break
            key, taken, message = made
            del self._resync[: len(taken)]
            self._awaiting[key] = [w.id for w in taken]
            self._resyncing.add(key)
            out.append(message)
        if self._sync_wanted and not self._syncing and DELETE not in self._awaiting:
            since = self._cursors().get(self._dictionary)
            out.append(protocol.encode(protocol.LearningSync(since=since)))
            self._sync_wanted = False
            self._syncing = True
            self._synced_from = since
        return out

    def _start_resync(self, epoch: str) -> None:
        """The server's store is new to this dictionary's learning data
        (restored, recreated, or first seen): its whole state goes again,
        and it syncs from the start."""
        installed = _moment(self._outbox.note(_INSTALLED))
        items: list[Waiting] = []
        for event in self._whole_state():
            if installed is not None and event.at <= installed:
                continue  # from before this install: maybe another account's
            at = self._again_at(event.at)
            if at is None:
                continue  # from before a deletion: it would bring the data back
            event_id = self._new_id()
            message = learning.learning_event(event, event_id)
            if at != event.at:
                message = message.model_copy(update={"at": protocol.at(at)})
            items.append(Waiting(LEARNING, event_id, protocol.encode(message)))
        self._resync = items
        self._resync_epoch = epoch
        cursors = self._cursors()
        cursors.pop(self._dictionary, None)  # it counted the old store's changes
        self._outbox.save_note(_CURSORS, json.dumps(cursors, sort_keys=True))
        log.info(
            "the server's learning store is new to this PC: %d status(es) and"
            " saved word(s) go again",
            len(items),
        )
        self._resync_sent()

    def _resync_sent(self) -> None:
        """Once every batch of the resync is received, its epoch is kept."""
        if self._resync or self._resyncing or self._resync_epoch is None:
            return
        epochs = self._epochs() | {self._dictionary: self._resync_epoch}
        self._outbox.save_note(_EPOCHS, json.dumps(epochs, sort_keys=True))
        self._resync_epoch = None

    def _epochs(self) -> dict[str, str]:
        """Each dictionary's server epoch its whole state was last sent to."""
        kept = self._outbox.note(_EPOCHS)
        try:
            epochs = json.loads(kept) if kept else {}
        except ValueError:
            return {}
        return epochs if isinstance(epochs, dict) else {}

    def _again_at(self, at: datetime) -> datetime | None:
        """The time a status or saved word set at `at` is sent again with:
        as `_stamp`, without raising the floor - None from before the latest
        deletion, just past the deletion if this PC set it after applying
        the deletion but by a clock behind the server's."""
        if self._asked is not None:
            return at if at > self._asked else None
        if self._deleted is None or at > self._deleted[1]:
            return at
        if self._after is not None and at > self._after.since:
            return self._deleted[1] + RAISED
        return None

    def _stamp(self, at: datetime) -> datetime | None:
        """The time one of this PC's learning events, made now and stamped
        `at` by its clock, is sent with; None if it's from before the
        latest deletion (it would bring the deleted data back)."""
        if self._asked is not None:  # this PC's own, its time not known yet
            return at if at > self._asked else None
        if self._deleted is None:
            return at
        if self._after is None:  # applied by an app from before 061
            return at if at > self._deleted[1] else None
        if at <= self._deleted[1] and at <= self._after.since:
            return None
        return self._raised(at)

    def _raised(self, at: datetime) -> datetime:
        """`at`, or - made after the deletion by this PC's clock, but at or
        before it (or the last event raised past it) - a millisecond after."""
        after = self._after
        if after is None or at > after.floor:
            return at
        self._after = _After(after.since, after.floor + RAISED)
        self._save_after()
        return self._after.floor

    def _apply(self, deletion: protocol.DeletionState) -> bool:
        """A deletion of the learning data named by the server: if it's one
        this PC hasn't applied, it is kept, and what waits from before it is
        dropped; whether it was new. After the deletion this PC asked for
        (its request answered), what waits was all done after the request:
        it's kept, stamped after the deletion where it needs to be."""
        kept = json.dumps(deletion.model_dump())
        found = _deletion(kept)
        if found is None or (
            self._deleted is not None and found[0] <= self._deleted[0]
        ):
            return False
        own = self._asked if not self._delete_waiting() else None
        self._deleted = found
        self._outbox.save_note(_DELETION, kept)
        self._after = _After(own or self._clock(), found[1])
        self._save_after()
        stale = [w.id for w in self._outbox.waiting() if self._from_before(w, own)]
        self._outbox.remove(stale)
        self._sent.difference_update(stale)
        if own is not None:
            self._release()
        log.info(
            "a deletion of the learning data (number %d%s) applied:"
            " %d waiting item(s) from before it dropped",
            found[0],
            ", this PC's" if own is not None else "",
            len(stale),
        )
        return True

    def _from_before(self, item: Waiting, own: datetime | None) -> bool:
        """A waiting learning event or exposure day from before the deletion
        - for this PC's own, a learning event from before it asked."""
        if self._deleted is None:
            return False
        try:
            if item.kind == LEARNING:
                event = protocol.LearningEvent.model_validate_json(item.body)
                return _time(event.at) <= (own or self._deleted[1])
            if item.kind == EXPOSURES:
                day = protocol.ExposureDay.model_validate_json(item.body)
                return date.fromisoformat(day.date) <= _utc_day(self._deleted[1])
        except ValueError:
            return False  # unreadable: dropped and counted as it's sent (`_read`)
        return False

    def _release(self) -> None:
        """This PC's deletion is applied (or the server named none): the
        learning events held since it asked go, each stamped as `_stamp`
        says, in the order they were made."""
        self._asked = None
        self._outbox.save_note(_ASKED, None)
        held = [
            w
            for w in self._outbox.waiting()
            if w.kind == LEARNING and w.id not in self._sent
        ]
        self._outbox.remove(w.id for w in held)
        unreadable = []
        for item in held:
            try:
                event = protocol.LearningEvent.model_validate_json(item.body)
            except ValueError:
                unreadable.append(item)  # removed above: not added again
                continue
            at = self._stamp(_time(event.at)) or _time(event.at)
            event = event.model_copy(update={"at": protocol.at(at)})
            self._outbox.add(
                Waiting(LEARNING, item.id, protocol.encode(event)), KEEP[LEARNING]
            )
        self._count_unreadable(unreadable, removed=True)

    def _delete_waiting(self) -> bool:
        return any(w.kind == DELETE for w in self._outbox.waiting())

    def _save_after(self) -> None:
        after = self._after
        kept = None
        if after is not None:
            kept = json.dumps(
                {"since": after.since.isoformat(), "floor": after.floor.isoformat()}
            )
        self._outbox.save_note(_AFTER, kept)

    def _forget_deletion(self) -> None:
        """The deletions applied here were another account's (a new install,
        signing out). A request this PC is still to send stays its own."""
        self._deleted = None
        self._outbox.save_note(_DELETION, None)
        self._after = None
        self._save_after()

    def _cursors(self) -> dict[str, str]:
        """Each dictionary's cursor from its last `learning_state`. A note
        that can't be read is started again: each dictionary syncs from the
        start (`_started_again`)."""
        kept = self._outbox.note(_CURSORS)
        if not kept:
            return {}
        found = _loaded(kept)
        if isinstance(found, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in found.items()
        ):
            return found
        self._started_again(_CURSORS)
        return {}

    def _started_again(self, note: str) -> None:
        """A note of the exchange's own that can't be read - damaged on disk,
        say - is cleared, and logged once by its name, never what it held:
        read at every session's open, it failed each one, and after decision
        0266 every minute for good (polyglotic-hq 566)."""
        self._outbox.save_note(note, None)
        log.warning("the outbox's %s note couldn't be read; started again", note)

    def _keep_cursor(self, cursor: str) -> None:
        cursors = self._cursors() | {self._dictionary: cursor}
        self._outbox.save_note(_CURSORS, json.dumps(cursors, sort_keys=True))

    def _message(
        self, kind: str, items: list[Waiting]
    ) -> tuple[str, list[Waiting], str] | None:
        """The next message of `kind` from the front of `items`: the key its
        answer comes back under, the items it carries, and the message.
        Items this version can't read are dropped from `items` and the
        outbox (`_read`); None if that leaves none."""
        first = items[0]
        if kind == CONSENT:
            return first.id, [first], first.body
        if kind == DELETE:
            return DELETE, [first], first.body
        batch = self._new_id()
        message: protocol.Message
        if kind == LEARNING:
            taken, events = self._read(
                items, self._limits.learning_events, protocol.LearningEvent
            )
            message = protocol.Learning(batch=batch, events=tuple(events))
        elif kind == EXPOSURES:  # protocol.md: 31 days a message
            taken, days = self._read(items, 31, protocol.ExposureDay)
            message = protocol.Exposures(batch=batch, days=tuple(days))
        else:
            taken, usage = self._read(
                items, self._limits.usage_events, protocol.UsageEvent
            )
            message = protocol.Usage(batch=batch, events=tuple(usage))
        if not taken:
            return None
        return batch, taken, protocol.encode(message)

    def _read(
        self, items: list[Waiting], count: int, row: type[_Row]
    ) -> tuple[list[Waiting], list[_Row]]:
        """As many items from the front of `items` as one message takes
        (`_fill`), each read as `row`. One this version can't read - written
        by another version, say - is dropped from `items` and the outbox and
        counted, and the message filled again without it: at every session's
        open it failed the session (decision 0266)."""
        while True:
            taken = self._fill(items, count)
            read: list[_Row] = []
            unreadable: list[Waiting] = []
            for item in taken:
                try:
                    read.append(row.model_validate_json(item.body))
                except ValueError:  # pydantic's ValidationError, bad JSON too
                    unreadable.append(item)
            if not unreadable:
                return taken, read
            for item in unreadable:
                items.remove(item)
            self._count_unreadable(unreadable)

    def _count_unreadable(self, rows: list[Waiting], removed: bool = False) -> None:
        """`rows` couldn't be read: dropped from the outbox (unless `removed`
        already), logged by kind and count - never what they held - and
        counted in the outbox's notes."""
        if not rows:
            return
        if not removed:
            self._outbox.remove(w.id for w in rows)
        ever = _count(self._outbox.note(_UNREADABLE)) + len(rows)
        self._outbox.save_note(_UNREADABLE, str(ever))
        log.warning(
            "%d waiting %s item(s) this version can't read dropped (%d ever)",
            len(rows),
            rows[0].kind,
            ever,
        )

    def take_unreadable(self) -> int:
        """Rows this version couldn't read and dropped since this was last
        called: counted in the listening session's summary (polyglotic-hq
        566). From the outbox's notes, so rows dropped as the app started,
        in a sync session before any listening, go in the next summary.
        Any thread."""
        with self._lock:
            ever = _count(self._outbox.note(_UNREADABLE))
            told = _count(self._outbox.note(_UNREADABLE_TOLD))
            if ever == told:
                return 0
            self._outbox.save_note(_UNREADABLE_TOLD, str(ever))
            return max(0, ever - told)  # none if the notes started again

    def _fill(self, items: list[Waiting], count: int) -> list[Waiting]:
        """As many items from the front as one message takes: at most
        `count`, and within the server's text message size (500 status
        events alone would be over it)."""
        room = self._limits.text_message_bytes - ROOM_BYTES
        taken: list[Waiting] = []
        size = 0
        for item in items[:count]:
            size += len(item.body.encode("utf-8")) + 1
            if taken and size > room:
                break
            taken.append(item)
        return taken


def _loaded(kept: str) -> object:
    """A note's JSON; None if it can't be read."""
    try:
        found: object = json.loads(kept)
    except (ValueError, RecursionError):
        return None
    return found


def _time(at: str) -> datetime:
    return datetime.fromisoformat(at).astimezone(UTC)


def _count(kept: str | None) -> int:
    """A count as kept in a note; 0 for none, or one that can't be read."""
    return int(kept) if kept and kept.isdigit() else 0


def _utc_day(at: datetime) -> date:
    return at.astimezone(UTC).date()


def _deletion(kept: str | None) -> tuple[int, datetime] | None:
    """A deletion as kept (or named): its number and time; None for none,
    or for one that can't be read."""
    if not kept:
        return None
    try:
        found = protocol.DeletionState.model_validate_json(kept)
        return found.generation, _time(found.at)
    except ValueError:
        return None


def _moment(kept: str | None) -> datetime | None:
    """A time as kept in a note; None for none, or one that can't be read."""
    if not kept:
        return None
    try:
        return datetime.fromisoformat(kept).astimezone(UTC)
    except ValueError:
        return None


def _after(kept: str | None) -> _After | None:
    """`_After` as kept; None for none, or one that can't be read."""
    if not kept:
        return None
    try:
        found = json.loads(kept)
        since, floor = _moment(found["since"]), _moment(found["floor"])
    except (ValueError, TypeError, KeyError):
        return None
    return _After(since, floor) if since and floor else None


def _dated_after(replaced: datetime, now: datetime) -> datetime:
    """A new consent choice's time: `now`, unless that is at or before the
    millisecond of the choice it replaces - then a millisecond after that
    (polyglotic-hq 311, decision 0102). The server takes the latest `at`
    as the latest choice, and the protocol's times are to the millisecond:
    on Windows, Python 3.12's clock moves in ticks of about 15.6 ms, so the
    first run's choice and an alpha tester's "diagnostics on" straight
    after it were dated the same, and the server kept the "off"."""
    floor = _to_the_millisecond(replaced) + RAISED
    return now if _to_the_millisecond(now) >= floor else floor


def _to_the_millisecond(moment: datetime) -> datetime:
    """`moment` as the protocol sends it (`protocol.at` cuts, not rounds)."""
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000)


def _allows(choice: ConsentChoice, refused: set[str] | None) -> bool:
    """Whether `choice` allows any of the kinds the server refused (None:
    it didn't say which - an older server)."""
    allowed = {USAGE} if choice.usage else set()
    allowed |= {EXPOSURES} if choice.exposures else set()
    return bool(allowed if refused is None else allowed & refused)


def _sent_again(kept: str | None, install: str | None) -> datetime | None:
    """When the consent last went again for `consent_missing` on `install`,
    as kept; None for another install's, none, or one that can't be read."""
    if not kept:
        return None
    try:
        found = json.loads(kept)
        if found["install"] != install:
            return None
        return _moment(found["at"])
    except (ValueError, TypeError, KeyError):
        return None


def _consent_message(choice: ConsentChoice) -> protocol.Consent:
    agreed = choice.agreement
    return protocol.Consent(
        id=choice.id,
        at=protocol.at(choice.at),
        usage=choice.usage,
        crashes=choice.crashes,
        exposures=choice.exposures,
        agreement=(
            protocol.Agreement(version=agreed.version, at=protocol.at(agreed.at))
            if agreed is not None
            else None
        ),
    )


def _parts(day: protocol.ExposureDay, room: int) -> list[protocol.ExposureDay]:
    """A day's counts in parts that each fit one message - at most `room`
    bytes and EXPOSURE_ENTRIES entries. The server keeps each count per
    install, day and entry, so the parts add up to the day (protocol.md,
    S2b); a day that fits is one part, an empty day none."""
    parts: list[protocol.ExposureDay] = []
    empty = len(protocol.encode(protocol.ExposureDay(date=day.date, counts={})))
    counts: dict[str, int] = {}
    size = empty
    for entry, count in day.counts.items():
        # "entry":count, - as encode writes it (UTF-8, no spaces)
        item = len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        item += len(str(count)) + 2
        if counts and (size + item > room or len(counts) >= EXPOSURE_ENTRIES):
            parts.append(protocol.ExposureDay(date=day.date, counts=counts))
            counts, size = {}, empty
        counts[entry] = count
        size += item
    if counts:
        parts.append(protocol.ExposureDay(date=day.date, counts=counts))
    if len(parts) > 1:
        log.info("a day's exposure counts go in %d parts", len(parts))
    return parts
