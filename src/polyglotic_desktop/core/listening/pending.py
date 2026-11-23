"""Speech waiting to be sent, latest wins: live updates never queue up.

`CaptionTiming` can decide faster than speech can be sent (a slow upload, a
reconnect). `PendingSpeech` holds what's waiting, by the proof of
concept's rule (`SegmentExecutor` in `overlay_core`):
- finished captions and withdrawals go first, in order;
- only the newest live update per caption and live section waits - a newer
  one replaces it and takes its turn at the back;
- a finished caption, or a withdrawal, cancels the pending live updates of
  the captions it covers (itself and those it replaces);
- **bounded while the connection is down** (polyglotic-hq project 165):
  finished speech waits at most `WAIT_MAX_SEC` of speech time - from its
  end to the end of the newest speech decided since - and older is dropped
  as newer speech comes, so a long outage neither grows without end nor
  floods the server with minutes-old captions when it's back (its 32
  frames waiting and 240 s of finished speech a minute). Speech that waited
  less than that goes out in order. Memory only.
- **nothing held through a planned maintenance window** (polyglotic-hq
  319): while the server is away for a window the app knows (`hold`),
  what waits is dropped and so is what comes - after it every app would
  otherwise send up to two minutes of old speech at once (320 measured
  finished captions' p95 at 7.7 s at capacity), and speech from before the
  window is no use to the learner by then. Nothing is reordered: captions
  start again, in order, with what's said once the server is back.

Each item carries a payload the caller chooses (such as the encoded
audio); core never looks inside it. Finished speech dropped is counted
(`dropped`) and its captions kept until taken (`take_dropped`): their live
captions end with what they show, rather than staying provisional for good
(polyglotic-hq 557, 529's B3).
"""

from collections import deque

from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    Decision,
    SpeechKind,
    TranscriptionRequest,
)

WAIT_MAX_SEC = 120.0
"""How much newer speech finished speech may wait behind before it's dropped
(the server resumes a lost session for as long: its decision 0040)."""


class PendingSpeech[P]:
    """Decisions waiting to be sent, each with its payload."""

    def __init__(self, wait_max_sec: float = WAIT_MAX_SEC) -> None:
        self._first: deque[tuple[Decision, P]] = deque()
        self._live: dict[tuple[CaptionId, int | None], tuple[Decision, P]] = {}
        self._wait_max_sec = wait_max_sec
        self._newest = float("-inf")  # the end of the newest speech put
        self.dropped = 0
        """Finished speech dropped for waiting too long (or held through a
        planned maintenance window), all told."""
        self._dropped_ids: list[CaptionId] = []
        """Their captions, since `take_dropped`."""
        self._holding = True

    def put(self, decision: Decision, payload: P) -> None:
        if not self._holding:  # a planned maintenance window: not kept
            self._count_dropped(decision)
            return
        if isinstance(decision, TranscriptionRequest):
            self._newest = max(self._newest, decision.speech_end)
        if (
            isinstance(decision, TranscriptionRequest)
            and decision.kind is SpeechKind.LIVE
        ):
            key = (decision.caption_id, decision.section)
            # Back of the line: its turn is by when it was last updated.
            self._live.pop(key, None)
            self._live[key] = (decision, payload)
            return
        covered = {decision.caption_id}
        if isinstance(decision, TranscriptionRequest):
            covered.update(decision.replaces)
        for key in [k for k in self._live if k[0] in covered]:
            del self._live[key]
        self._first.append((decision, payload))
        self._drop_stale()  # what waits stays within WAIT_MAX_SEC, taken or not

    def take(self) -> tuple[Decision, P] | None:
        """The next decision to send, or None if nothing is waiting."""
        self._drop_stale()
        if self._first:
            return self._first.popleft()
        if self._live:
            return self._live.pop(next(iter(self._live)))
        return None

    def _drop_stale(self) -> None:
        oldest = self._newest - self._wait_max_sec
        kept: deque[tuple[Decision, P]] = deque()
        for decision, payload in self._first:
            if (
                isinstance(decision, TranscriptionRequest)
                and decision.speech_end < oldest
            ):
                self._count_dropped(decision)
                continue
            kept.append((decision, payload))
        self._first = kept

    def hold(self, holding: bool) -> None:
        """False: the server is away for a planned maintenance window -
        what waits is dropped, and so is what comes, until True again."""
        self._holding = holding
        if not holding:
            for decision, _ in self._first:
                self._count_dropped(decision)
            self.clear()

    def _count_dropped(self, decision: Decision) -> None:
        if (
            isinstance(decision, TranscriptionRequest)
            and decision.kind is SpeechKind.FINISHED
        ):
            self.dropped += 1
            self._dropped_ids.append(decision.caption_id)

    def take_dropped(self) -> list[CaptionId]:
        """The captions whose finished speech was dropped since last asked,
        in order: their finished captions won't come."""
        taken, self._dropped_ids = self._dropped_ids, []
        return taken

    def clear(self) -> None:
        """Everything waiting dropped: nothing of it is to be sent."""
        self._first.clear()
        self._live.clear()

    def __len__(self) -> int:
        return len(self._first) + len(self._live)
