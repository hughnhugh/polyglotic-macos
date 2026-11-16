"""Caption windows the learner hid: how long each still listens
(polyglotic-hq 335, decision 0128).

A hidden caption window's app is still captioned - its speech still goes
to the server - so a window hidden and forgotten would load the server for
ever (the user's feedback 18, 2026-11-13). Each window has its own timer:
hidden for the learner's limit (`PAUSE_CHOICES`: 5, 15 or 60 minutes, or
never), its listening pauses - nothing of its app is sent - until it's
shown again, which starts it again by itself. A window that is shown is
never paused - nor one whose transcript is open (`read`): its captions are
being read there, and its limit counts from when the transcript closes.

While a hidden window still listens and its app's speech is being
captioned, it's "captioning while hidden" (`Sight.CAPTIONING`), for Home
and the tray to say; and speech starting in it (`captioned` returns True)
is when a learner who asked for it gets the window back.

Plain Python on a clock the caller reads (`now`, in seconds): no Qt, no
timers of its own. Keyed by the window's key (its app's name, on this PC
only).
"""

from dataclasses import dataclass, field
from enum import StrEnum

PAUSE_CHOICES: tuple[int | None, ...] = (5, 15, 60, None)
"""How long a hidden window may listen, in minutes; None: never paused."""
PAUSE_AFTER_MIN = 15
"""The default limit (the user's feedback 18: "15 minutes maybe")."""
QUIET_SEC = 30.0
"""Speech this long apart is talk starting again: a hidden window is
captioning while hidden until this long after its app's last caption, and
speech starts in it at a caption this long after the last one - or after
it was hidden, so a window hidden mid-speech isn't brought straight back."""


class Sight(StrEnum):
    """A caption window as the learner would find it."""

    SHOWN = "shown"
    HIDDEN = "hidden"
    """Hidden, listening, nothing of its app captioned lately."""
    CAPTIONING = "captioning"
    """Hidden, listening, and its app's speech is being captioned."""
    PAUSED = "paused"
    """Hidden past the limit: nothing of its app is sent until it's shown."""


@dataclass
class _Hidden:
    since: float
    paused_after: int | None = None  # minutes: paused; None: listening
    read_at: float | None = None  # its transcript was last seen open

    @property
    def unseen_since(self) -> float:
        """When the learner last had its captions in front of them."""
        return self.since if self.read_at is None else max(self.since, self.read_at)


@dataclass
class HiddenWindows:
    """Each hidden window's timer, from `hide` to `show`, ticked by
    `tick`."""

    limit: int | None = PAUSE_AFTER_MIN
    """Minutes a hidden window listens; None: never paused. A new limit
    counts from when each window was hidden; a window paused already stays
    paused until it's shown."""
    _hidden: dict[str, _Hidden] = field(default_factory=dict)
    _captioned_at: dict[str, float] = field(default_factory=dict)

    def hide(self, key: str, now: float) -> None:
        """The window is hidden from `now` - unless it was already."""
        self._hidden.setdefault(key, _Hidden(now))

    def show(self, key: str) -> bool:
        """The window is shown: its timer goes. Whether it was paused - its
        listening starts again."""
        found = self._hidden.pop(key, None)
        return found is not None and found.paused_after is not None

    def read(self, key: str, now: float) -> bool:
        """The hidden window's transcript is open at `now`: its captions
        are being read there, so its limit counts from now. Whether it was
        paused - its listening starts again."""
        found = self._hidden.get(key)
        if found is None:
            return False
        was_paused = found.paused_after is not None
        found.read_at = now
        found.paused_after = None
        return was_paused

    def forget(self, key: str) -> None:
        """The window closed: its app isn't captioned any more."""
        self._hidden.pop(key, None)
        self._captioned_at.pop(key, None)

    def tick(self, now: float) -> frozenset[str]:
        """The windows paused at `now`: hidden for the limit, and not
        paused before."""
        if self.limit is None:
            return frozenset()
        due = self.limit * 60.0
        paused: set[str] = set()
        for key, hidden in self._hidden.items():
            if hidden.paused_after is None and now - hidden.unseen_since >= due:
                hidden.paused_after = self.limit
                paused.add(key)
        return frozenset(paused)

    def next_due(self, now: float) -> float | None:
        """Seconds until the next window is paused (0: one is due now);
        None while none would be."""
        if self.limit is None:
            return None
        due = [
            hidden.unseen_since + self.limit * 60.0 - now
            for hidden in self._hidden.values()
            if hidden.paused_after is None
        ]
        return max(0.0, min(due)) if due else None

    def captioned(self, key: str, now: float) -> bool:
        """A caption of the window's own app arrived at `now`. Whether
        speech started in it while hidden and listening: the first caption
        QUIET_SEC after the last one, and after it was hidden."""
        before = self._captioned_at.get(key)
        self._captioned_at[key] = now
        hidden = self._hidden.get(key)
        if hidden is None or hidden.paused_after is not None:
            return False
        quiet_since = hidden.since if before is None else max(before, hidden.since)
        return now - quiet_since >= QUIET_SEC

    def sight(self, key: str, now: float) -> Sight:
        hidden = self._hidden.get(key)
        if hidden is None:
            return Sight.SHOWN
        if hidden.paused_after is not None:
            return Sight.PAUSED
        last = self._captioned_at.get(key)
        if last is not None and last >= hidden.since and now - last < QUIET_SEC:
            return Sight.CAPTIONING
        return Sight.HIDDEN

    def paused(self) -> dict[str, int]:
        """The windows paused now, each with the limit it was paused after
        (minutes)."""
        return {
            key: hidden.paused_after
            for key, hidden in self._hidden.items()
            if hidden.paused_after is not None
        }

    @property
    def any_hidden(self) -> bool:
        return bool(self._hidden)
