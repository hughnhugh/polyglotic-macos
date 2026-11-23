"""Made-up caption updates for the new interface's tests, from the
recorded conversation (`ui.recorded_captions`) - never real calls."""

import time
from collections.abc import Iterator
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
from polyglotic_desktop.ui_next.views.caption_window import JoinedChoices
from tools import busy_pc

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.words_page import WordsPage

EN = Language("en")
ZH = Language("zh")
OTHER_APP = SourceId("other-app")
SEPARATE = JoinedChoices(on=False, chosen=True)
"""The learner's own "Separate windows": windows start joined since
polyglotic-hq 554, and a test of windows on their own says so."""


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


def arriving(
    per_pass: int, source: SourceId = APP, start: int = 0
) -> Iterator[CaptionUpdate]:
    """New finished captions for a timed arrival of `per_pass` captions, for
    every try the budget judge may take: a warm-up pass and the timed one in
    each of `busy_pc.MOST_TRIES` tries - up to 4 on a busy runner, not 2
    (polyglotic-hq 577, 578: 40 for 10 arrivals ran out on a third try, and
    the test failed with StopIteration rather than its budget's reason).
    Made up front, so the timed arrivals don't time their making."""
    return iter(finished_updates(per_pass * 2 * busy_pc.MOST_TRIES, source, start))


def at_one_moment(window: "CaptionWindow") -> None:
    """`window` on a clock that stands still from now: the captions a test
    gives it arrive at one moment, as on a fast PC, and step into place.
    On a busy runner a pause of 0.1 s or more between two of them made the
    later one slide in - drawn below the window's foot, with nothing above
    it - and a point found on the words, or a press there, missed them
    (polyglotic-hq 578: the hold tests 3 runs in 9, the drag tests now and
    then, on GitHub's machines). A test of the motion moves its own clock."""
    still = time.monotonic()
    window.clock = lambda: still


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
