"""The finished caption lines a typing hold shares with the caption window."""

from polyglotic_desktop.core.listening.captions import CaptionKind, CaptionUpdate
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, TranscriptionRequest


class CaptionResults:
    """Follow the server's answers and the resulting lines for one held source.

    The raw answer settles an audio request. The display's projection supplies
    the words, including joins and continuations that show as a single line.
    """

    def __init__(self, source: SourceId) -> None:
        self._source = source
        self._answered: dict[CaptionId, float] = {}
        self._shown: dict[CaptionId, CaptionUpdate] = {}
        self._dropped: set[CaptionId] = set()

    def received(self, update: CaptionUpdate) -> None:
        if update.source_id != self._source or update.kind is CaptionKind.LIVE:
            return
        end = update.times.speech_end if update.times is not None else float("inf")
        for caption_id in (update.caption_id, *update.replaces):
            self._answered[caption_id] = max(
                end, self._answered.get(caption_id, float("-inf"))
            )

    def applied(self, update: CaptionUpdate) -> None:
        if update.source_id != self._source or update.kind is CaptionKind.LIVE:
            return
        for replaced in update.replaces:
            self._shown.pop(replaced, None)
        if update.kind is CaptionKind.FINISHED:
            self._shown[update.caption_id] = update
        else:
            self._shown.pop(update.caption_id, None)

    def dropped(self, caption_id: CaptionId) -> None:
        self._dropped.add(caption_id)

    def lines(
        self, requests: tuple[TranscriptionRequest, ...]
    ) -> tuple[CaptionUpdate, ...] | None:
        """The lines in audio order, or None while any request is outstanding."""
        if any(
            request.caption_id not in self._dropped
            and self._answered.get(request.caption_id, float("-inf"))
            < request.speech_end
            for request in requests
        ):
            return None
        positions = {request.caption_id: request.speech_start for request in requests}
        found: list[tuple[float, CaptionUpdate]] = []
        for line in self._shown.values():
            starts = [
                positions[cid]
                for cid in (line.caption_id, *line.replaces)
                if cid in positions
            ]
            if starts:
                found.append((min(starts), line))
        return tuple(line for _, line in sorted(found, key=lambda item: item[0]))
