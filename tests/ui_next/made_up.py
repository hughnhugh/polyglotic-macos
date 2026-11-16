"""Made-up caption updates for the new interface's tests, from the
recorded conversation (`ui.recorded_captions`) - never real calls."""

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.recorded_captions import APP, recorded_captions

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.words_page import WordsPage

EN = Language("en")
ZH = Language("zh")
OTHER_APP = SourceId("other-app")


def finished_updates(
    count: int, source: SourceId = APP, start: int = 0
) -> list[CaptionUpdate]:
    """`count` finished captions from `source`, each with its own id,
    cycling through the conversation's finished lines from the app."""
    pool = [
        update
        for _, update in recorded_captions()
        if update.kind is CaptionKind.FINISHED and update.source_id == APP
    ]
    return [
        replace(
            pool[n % len(pool)],
            caption_id=CaptionId(f"{source}-{n:05d}"),
            source_id=source,
            replaces=(),
        )
        for n in range(start, start + count)
    ]


def live_update(caption_id: str, source: SourceId = APP) -> CaptionUpdate:
    """A live update: the first finished line, still being spoken."""
    first = finished_updates(1, source)[0]
    return replace(first, caption_id=CaptionId(caption_id), kind=CaptionKind.LIVE)


def withdrawn(caption_id: str, source: SourceId = APP) -> CaptionUpdate:
    return CaptionUpdate(CaptionId(caption_id), source, CaptionKind.WITHDRAWN)


def tab_stops(window: QWidget) -> list[QWidget]:
    """The widgets Tab visits in `window`, in order - as Qt's chain walks
    them (the UI lab's keyboard check reads the same chain)."""
    stops: list[QWidget] = []
    seen: set[int] = set()
    current = window.nextInFocusChain()
    while (
        current is not None
        and current is not window
        and id(current) not in seen
        and len(seen) < 5000
    ):
        seen.add(id(current))
        if (
            current.focusPolicy() & Qt.FocusPolicy.TabFocus
            and current.isVisibleTo(window)
            and current.isEnabled()
            and current.focusProxy() is None
        ):
            stops.append(current)
        current = current.nextInFocusChain()
    return stops


def export_written(page: "WordsPage") -> None:
    """Words' export written on its own thread and said (polyglotic-hq
    273): waits for the thread, then for its answer on this one."""
    exporting = page.first.exporting
    if exporting is not None:
        exporting.join(timeout=30)
    for _ in range(100):
        if page.first.exporting is None:
            return
        QApplication.processEvents()
    raise AssertionError("the export wasn't said")
