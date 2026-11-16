"""Finished speech not yet answered: kept in memory a short while, sent again after a reconnect.

protocol.md: the server answers every finished speech frame with a
`caption_update` (finished or withdrawn) or an `error` naming its
`caption_id`; it keeps nothing between sessions, so "speech for a caption
that was in flight is sent again as finished speech if it matters". The
app can't tell what was in flight when a connection dropped - only what
hasn't been answered (project 022, point 2). So each finished speech
frame is kept from just before it's sent until its answer comes; those
still unanswered when a session ends go first on the next one.

Bounded: a frame is kept at most `KEEP_SEC` from when it was first sent
(a caption later than that is no longer worth showing; as long as the
server keeps a lost session to resume - its decision 0040 - and as long as
finished speech waits unsent, `core.listening.pending`), and `MAX_BYTES` in all,
oldest dropped first. **Memory only** - speech is never written to disk.
Live updates aren't kept: the next one, or the finished caption, takes
their place.

**Given up** (polyglotic-hq 271): the server answers a session's finished
speech in the order it came, so a frame still unanswered when one sent
after it is answered was lost there, not late. Such a frame - overtaken -
is forgotten once it has waited `give_up_after`, and so is any frame older
than `KEEP_SEC`: neither will be answered, and waiting for them held
"Connection unstable" up for good on a connection that was fine.

**Handed over** (polyglotic-hq 277): when what's captured changes, the app
stops its listening session and opens another at once, and the server
closes the old one as the new one's `hello` arrives - so the old one's
wait for its last answers ends at once. What it still has unanswered
(`hand_over`) is taken on by the new one (`take_on`) and sent again
there, as after a reconnect.
"""

import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

KEEP_SEC = 120.0
MAX_BYTES = 4 << 20  # about 25 minutes of speech at project 016's ~2.6 kB/s


@dataclass(slots=True)
class _Kept:
    frame: bytes
    first_sent: float
    overtaken: bool = False  # speech sent after it has been answered


@dataclass(frozen=True, slots=True)
class Handed:
    """A finished speech frame one session sent and never had answered,
    for the next to send: its caption, the frame, and when first sent."""

    caption_id: str
    frame: bytes
    first_sent: float


class GivenUp(StrEnum):
    """Why finished speech stopped being waited for, unanswered."""

    OVERTAKEN = "overtaken"  # speech sent after it was answered: lost there
    TOO_OLD = "too_old"  # older than a caption is worth showing


class UnansweredSpeech:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        keep_sec: float = KEEP_SEC,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._clock = clock
        self._keep_sec = keep_sec
        self._max_bytes = max_bytes
        self._kept: OrderedDict[str, _Kept] = OrderedDict()
        self._bytes = 0

    def sending(self, caption_id: str, replaces: Iterable[str], frame: bytes) -> None:
        """A finished speech frame is about to be sent. A joined caption's
        frame replaces any earlier one for the same caption, and those of
        the captions it takes in."""
        first_sent = self._clock()
        earlier = self._forget(caption_id)
        if earlier is not None:
            first_sent = earlier.first_sent
        for replaced in replaces:
            self._forget(replaced)
        self._kept[caption_id] = _Kept(frame, first_sent)
        self._bytes += len(frame)
        while self._bytes > self._max_bytes and self._kept:
            oldest = next(iter(self._kept))
            self._forget(oldest)

    def answered(self, caption_id: str, replaces: Iterable[str] = ()) -> None:
        """A finished or withdrawn caption update, or an error answering
        finished speech, for `caption_id` (and the captions it replaces).
        An error naming a caption may be refusing one of its live updates
        instead: the session decides which (`connection.session`)."""
        if caption_id in self._kept:
            for earlier, kept in self._kept.items():
                if earlier == caption_id:
                    break
                kept.overtaken = True
        self._forget(caption_id)
        for replaced in replaces:
            self._forget(replaced)

    def withdrawn(self, caption_id: str) -> None:
        """The app withdraws the caption: the server answers nothing more
        for it, so its finished speech isn't waited for."""
        self._forget(caption_id)

    def give_up(self, after: float) -> list[tuple[str, GivenUp]]:
        """Forgets the frames that won't be answered - overtaken and
        waiting `after` seconds or more, or older than the keep time - and
        returns each caption's id and why."""
        now = self._clock()
        given_up: list[tuple[str, GivenUp]] = []
        for caption_id, kept in list(self._kept.items()):
            waited = now - kept.first_sent
            if waited > self._keep_sec:
                given_up.append((caption_id, GivenUp.TOO_OLD))
            elif kept.overtaken and waited >= after:
                given_up.append((caption_id, GivenUp.OVERTAKEN))
            else:
                continue
            self._forget(caption_id)
        return given_up

    def give_up_all(self) -> list[str]:
        """Every frame still unanswered, forgotten: a planned maintenance
        window has begun, and none is worth sending after it (polyglotic-hq
        319). Their captions' ids, oldest first."""
        ids = list(self._kept)
        self._kept.clear()
        self._bytes = 0
        return ids

    def hand_over(self) -> list[Handed]:
        """Every frame still unanswered and recent enough, oldest first,
        for another session to send - and forgotten here: this session
        is over."""
        now = self._clock()
        handed = [
            Handed(caption_id, kept.frame, kept.first_sent)
            for caption_id, kept in self._kept.items()
            if now - kept.first_sent <= self._keep_sec
        ]
        self._kept.clear()
        self._bytes = 0
        return handed

    def take_on(self, handed: Iterable[Handed]) -> None:
        """Frames a session before this one sent and never had answered,
        kept here as if sent here - after what's kept, since they're sent
        after it - and from when they were first sent."""
        for frame in handed:
            self._forget(frame.caption_id)
            self._kept[frame.caption_id] = _Kept(frame.frame, frame.first_sent)
            self._bytes += len(frame.frame)
        while self._bytes > self._max_bytes and self._kept:
            self._forget(next(iter(self._kept)))

    def to_send_again(self) -> list[bytes]:
        """On a new session: the frames still unanswered and recent enough,
        oldest first (they stay kept until answered)."""
        now = self._clock()
        for caption_id, kept in list(self._kept.items()):
            if now - kept.first_sent > self._keep_sec:
                self._forget(caption_id)
        for kept in self._kept.values():
            kept.overtaken = False  # sent afresh: the new session's order counts
        return [kept.frame for kept in self._kept.values()]

    def waiting_since(self) -> float | None:
        """When the oldest frame still unanswered was first sent (None: none
        is) - how long the server has kept the learner waiting."""
        return min((kept.first_sent for kept in self._kept.values()), default=None)

    def __len__(self) -> int:
        return len(self._kept)

    def __contains__(self, caption_id: object) -> bool:
        """Whether the caption's finished speech is kept: sent (or being
        sent) and not yet answered."""
        return caption_id in self._kept

    def _forget(self, caption_id: str) -> _Kept | None:
        kept = self._kept.pop(caption_id, None)
        if kept is not None:
            self._bytes -= len(kept.frame)
        return kept
