"""Project the server's two audio IDs onto one reversible display line.

Only visible associations need a saved first answer. Audio, frame timings
and minutes keep their original IDs at the connection boundary.
"""

from collections.abc import Callable
from dataclasses import replace

from polyglotic_desktop.core.listening.captions import CaptionKind, CaptionUpdate
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.timing import CaptionId


class CaptionGroups:
    def __init__(
        self, history: CaptionHistory, refresh: Callable[[CaptionId], None]
    ) -> None:
        self._history = history
        self._refresh = refresh
        self._first: dict[CaptionId, CaptionUpdate] = {}
        self._released: dict[CaptionId, CaptionId] = {}
        """A combined reply already in flight cannot undo an independent correction."""

    def separate_for_check(self, cid: CaptionId) -> CaptionUpdate | None:
        """The saved first line, when a learner accepts one audio ID's recheck."""
        for child, first in self._first.items():
            if cid in (child, first.caption_id):
                del self._first[child]
                if cid == first.caption_id:
                    self._released[child] = cid
                    self._refresh(child)
                return first
        return None

    def project(self, update: CaptionUpdate) -> tuple[CaptionUpdate, ...]:
        """Updates for the history, word playout, cards and transcript."""
        cid = update.caption_id
        if self._history.dismissed(cid):
            return ()
        if update.kind is CaptionKind.LIVE:
            if cid in self._first or any(
                a.caption_id == cid for a in self._first.values()
            ):
                return ()  # a late draft cannot undo either finished stretch
            return (update,)

        out: list[CaptionUpdate] = []
        anchor = update.continues
        gone = set(update.replaces) - {cid}
        for child, parent in list(self._released.items()):
            if child in gone or self._history.caption(parent) is None:
                del self._released[child]
            elif child == cid:
                if anchor == parent:
                    return ()  # wait for the later audio's own answer
                del self._released[child]

        for child, first in list(self._first.items()):
            parent = first.caption_id
            if self._history.caption(parent) is None:
                del self._first[child]  # the line aged out
                continue
            if child == cid and anchor == parent and parent not in gone:
                continue  # another combined answer for this pair
            if child == cid or child in gone:
                del self._first[child]
                if parent != cid and parent not in gone:
                    out.append(first)
            elif parent == cid or parent in gone:
                if (
                    parent == cid
                    and update.kind is CaptionKind.FINISHED
                    and not gone
                    and update.clauses == first.clauses
                    and update.language == first.language
                    and update.languages_heard == first.languages_heard
                ):
                    return ()  # a repeated first answer, e.g. after a reconnect
                del self._first[child]
                update = replace(update, display_member=child)
                self._released[child] = parent
                self._refresh(child)  # the combined answer cannot stand for B alone

        if anchor is not None and self._history.dismissed(anchor):
            self._refresh(cid)
            return tuple(out)
        if anchor is not None and anchor != cid and anchor not in gone:
            update = self._combined(update, anchor)
        out.append(update)
        return tuple(out)

    def _combined(self, update: CaptionUpdate, anchor: CaptionId) -> CaptionUpdate:
        earlier = self._history.caption(anchor)
        if earlier is None or earlier.live or earlier.source_id != update.source_id:
            return update
        child = update.caption_id
        if child not in self._first:
            self._first[child] = CaptionUpdate(
                anchor,
                earlier.source_id,
                CaptionKind.FINISHED,
                earlier.clauses,
                earlier.language,
                earlier.languages_heard,
                respoken=earlier.respoken,
                pace_wpm=earlier.pace_wpm,
                display_member=child,
            )
        return replace(
            update,
            caption_id=anchor,
            continues=None,
            display_member=child,
            replaces=tuple(dict.fromkeys((child, *update.replaces))),
        )
