"""Recent speech: the audio of lately finished captions, held in memory.

Three features need a finished caption's audio after it was sent: "Looks
wrong?" (a re-run on the best model), clips for cards and, for alpha
testers, "Report a problem" (`held`, polyglotic-hq 275). The store keeps
each finished caption's Ogg Opus exactly as it was sent, by caption id,
with its start and end on the app's clock and its source's category.

- Memory only: nothing is written anywhere; `clear` empties it (listening
  data deleted), and it ends with the app.
- Held per source for `hold_seconds` of speech (2 minutes, decision 0027);
  `category_hold` overrides that per category (a video source's whole
  session, if the user agrees later). The oldest entries drop first.
- A joined caption's audio covers the whole joined stretch, so the
  captions it replaces are dropped when it arrives.
- `max_bytes` per source is a hard bound whatever the settings say.

Users see only `RecentSpeechPort`: audio by id, or None for "not held any
more".
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ports.capture import SourceCategory

HOLD_MINUTES: int = 2
HOLD_SECONDS = HOLD_MINUTES * 60.0
"""How long finished speech is held, per source (DECISIONS.md #42)."""
MAX_BYTES_PER_SOURCE = 4_000_000
"""About 25 minutes at Ogg Opus 24 kbps: a bound, never reached at 2 minutes."""


@dataclass(frozen=True, slots=True)
class HeldSpeech:
    """One finished caption's audio as sent, and where it came from."""

    caption_id: CaptionId
    source_id: SourceId
    category: SourceCategory
    start: float
    end: float
    audio: bytes


class RecentSpeechPort(Protocol):
    """What "Looks wrong?" and clips use."""

    def get(self, caption_id: CaptionId) -> HeldSpeech | None:
        """The caption's audio, or None: not held any more."""
        ...


class RecentSpeech:
    """The store. Call from one lock-holder at a time (the pipeline's)."""

    def __init__(
        self,
        clock: Callable[[], float],
        hold_seconds: float = HOLD_SECONDS,
        category_hold: Mapping[SourceCategory, float] | None = None,
        max_bytes: int = MAX_BYTES_PER_SOURCE,
    ) -> None:
        """`clock` is the app's clock (the one speech times are on)."""
        self._clock = clock
        self.hold_seconds = hold_seconds
        self.category_hold = dict(category_hold or {})
        self.max_bytes = max_bytes
        self._by_source: dict[SourceId, dict[CaptionId, HeldSpeech]] = {}

    def add(self, speech: HeldSpeech, replaces: tuple[CaptionId, ...] = ()) -> None:
        """Holds a finished caption's audio; drops the captions it replaces."""
        held = self._by_source.setdefault(speech.source_id, {})
        for old in replaces:
            held.pop(old, None)
        held.pop(speech.caption_id, None)
        held[speech.caption_id] = speech
        self._trim(speech.source_id)

    def get(self, caption_id: CaptionId) -> HeldSpeech | None:
        for source_id in list(self._by_source):
            self._trim(source_id)
            found = self._by_source.get(source_id, {}).get(caption_id)
            if found is not None:
                return found
        return None

    def held(self) -> tuple[HeldSpeech, ...]:
        """Everything held now, each source's oldest first: what "Report a
        problem" offers to send (polyglotic-hq 275)."""
        for source_id in list(self._by_source):
            self._trim(source_id)
        return tuple(s for held in self._by_source.values() for s in held.values())

    def size(self, source_id: SourceId | None = None) -> int:
        """Bytes held, for one source or all."""
        sources = [source_id] if source_id is not None else list(self._by_source)
        return sum(
            len(s.audio) for i in sources for s in self._by_source.get(i, {}).values()
        )

    def remove_source(self, source_id: SourceId) -> None:
        self._by_source.pop(source_id, None)

    def clear(self) -> None:
        self._by_source.clear()

    def _trim(self, source_id: SourceId) -> None:
        held = self._by_source.get(source_id)
        if not held:
            self._by_source.pop(source_id, None)
            return
        now = self._clock()
        total = sum(len(s.audio) for s in held.values())
        for caption_id, s in list(held.items()):  # oldest first
            hold = self.category_hold.get(s.category, self.hold_seconds)
            if now - s.end > hold or (total > self.max_bytes and len(held) > 1):
                total -= len(s.audio)
                del held[caption_id]
        if not held:
            del self._by_source[source_id]
