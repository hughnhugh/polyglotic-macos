"""What "Report a problem" offers from listening, for alpha testers (polyglotic-hq 275; decision 0067).

The tester sees each part, its size and a way to look, and sends it only
if it stays ticked (protocol.md, Problem reports):
- **the captions as shown** (`captions_as_shown`): those that changed in
  the last `CAPTION_MINUTES`, oldest first, each with its id and times,
  as the server's problem report carries them;
- **the speech held** (`speech_by_source`): each source's last 2 minutes
  of finished speech from the recent-speech store, exactly as it was sent
  for captioning - one part per source, so one can be left out;
- **other people's voices** (`SpeechPart.others_voices`): a call app's
  speech, or the mic's, can hold other people's voices; the dialog says
  so on that source's line.

Holds caption text and audio: never log it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ports.capture import SourceCategory

CAPTION_MINUTES = 5.0
"""How far back the captions go: "the last few minutes"."""
OTHER_VOICES = frozenset({SourceCategory.CALL, SourceCategory.MIC})
"""Sources whose speech can hold other people's voices."""


def _at(moment: datetime) -> str:
    """protocol.md's time format: UTC, milliseconds, `Z`."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    text = moment.astimezone(UTC).isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def caption_as_shown(caption: Caption) -> dict[str, object]:
    """One caption as protocol.md's problem report carries it."""
    languages = sorted({lang for c in caption.clauses for lang in c.translations})
    return {
        "caption_id": str(caption.caption_id),
        "source_id": str(caption.source_id),
        "by_you": caption.by_you,
        "live": caption.live,
        "language": caption.language,
        "started_at": _at(caption.started_at),
        "updated_at": _at(caption.updated_at),
        "original": caption.original,
        "translations": {lang: caption.translation(lang) for lang in languages},
        "checked": caption.checked,
    }


def captions_as_shown(
    captions: Sequence[Caption], now: datetime, minutes: float = CAPTION_MINUTES
) -> list[dict[str, object]]:
    """The captions that changed in the last `minutes`, oldest first."""
    since = now - timedelta(minutes=minutes)
    recent = [c for c in captions if c.updated_at >= since]
    return [caption_as_shown(c) for c in sorted(recent, key=lambda c: c.started_at)]


@dataclass(frozen=True)
class SpeechPart:
    """One source's held speech: the clips, oldest first."""

    source_id: SourceId
    category: SourceCategory
    clips: tuple[HeldSpeech, ...]

    @property
    def seconds(self) -> float:
        return sum(c.end - c.start for c in self.clips)

    @property
    def size(self) -> int:
        """Bytes of audio, as sent."""
        return sum(len(c.audio) for c in self.clips)

    @property
    def others_voices(self) -> bool:
        return self.category in OTHER_VOICES


def speech_by_source(held: Sequence[HeldSpeech]) -> list[SpeechPart]:
    """The held speech as one part per source, in the order sources first
    appear; each part's clips oldest first."""
    by_source: dict[SourceId, list[HeldSpeech]] = {}
    for clip in held:
        by_source.setdefault(clip.source_id, []).append(clip)
    return [
        SpeechPart(
            source_id,
            clips[-1].category,
            tuple(sorted(clips, key=lambda c: c.start)),
        )
        for source_id, clips in by_source.items()
    ]
