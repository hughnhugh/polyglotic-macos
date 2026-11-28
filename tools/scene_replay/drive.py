"""The instrument: real caption surfaces, offscreen, on the patched clock.

One run plays one caption stream (`streams.py`) into one surface set up one
way (`Setup`), at 60 frames a second of made-up time, and reads back after
every paint what the surface says it placed (`frames.Frame`).

Nothing is forced. Time moves a frame; the timers that fall due ring; the
stream's updates for that moment are received; Qt delivers the paints the
window asked for with `update()`. A frame that the window did not repaint
is, on a screen, the frame before, and that is what is recorded.

What this reads is where each row and character is, and how opaque a row
is. It does not read colours, underlines, marks, link curves, the fades
the paint works out for itself at the top edge, or anything the pointer
does; `REPORT.md` of polyglotic-hq project 982 lists what it cannot see.
"""

import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_WINDOWS_FONTS = Path("C:/Windows/Fonts")
if _WINDOWS_FONTS.is_dir():  # as the UI lab does: the fonts the app draws with
    os.environ.setdefault("QT_QPA_FONTDIR", str(_WINDOWS_FONTS))

import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QRectF
from PySide6.QtGui import QTextLayout
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.listening import history
from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.display import LongLines
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui_next import caption_layout, caption_window
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcript_window import PAD as LIST_PAD
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import Transcript, TranscriptChoices
from tools.scene_replay.clock import START, Hands
from tools.scene_replay.frames import FRAME, Char, Frame, Row, Surface, q
from tools.scene_replay.streams import FIRST, OTHER, Stream

SURFACES = (
    "panel",
    "cards",
    "zones",
    "joined",
    "video-instant",
    "video-scrolling",
    "transcript",
)
"""The surfaces a stream is played into. `panel` is a caption window in
Instant; `cards` and `zones` are Steady with and without its card stack;
`joined` is two caption windows as one, the stream in its first column."""

NARROW = (360, 690)
"""The narrow window, in px: 969's width, where a caption overflows onto a
second line pair."""

TAIL = 4.0
"""Seconds played after a stream's last update, so the last arrival, its
fade and its reading hold have all ended."""

AREA = Rect(0, 0, 1920, 1040)
SECOND = SourceId("app-2")
LABELS = {
    FIRST: SourceLabel("Video Player", "#4dd0e1"),
    SECOND: SourceLabel("Web Browser", "#a5d66f"),
}
DAY = datetime(2026, 11, 27, 9, 30, tzinfo=UTC)
"""The transcript's made-up day: its headings show times."""

PATHS = {
    "_flowed": "B the composer",
    "_poured": "the pour",
    "_laid_row_text": "A clause rows",
    "_subtitle_tracks": "C Video tracks",
}
"""`CaptionLayout`'s methods that mark which layout path laid a line out
(827's SPEC, section 1.1). Clause rows are told apart by whether Qt may
wrap them."""


@dataclass(frozen=True)
class Setup:
    surface: str = "panel"
    readings: bool = False
    narrow: bool = False
    paired: bool = False
    """Long lines: Display new lines (otherwise Grouped)."""

    @property
    def name(self) -> str:
        parts = [self.surface]
        parts += ["readings"] if self.readings else []
        parts += ["narrow"] if self.narrow else []
        parts += ["paired"] if self.paired else []
        return "+".join(parts)

    @staticmethod
    def named(name: str) -> "Setup":
        surface, *flags = name.split("+")
        if surface not in SURFACES or set(flags) - {"readings", "narrow", "paired"}:
            raise ValueError(f"no setup called {name}")
        return Setup(surface, "readings" in flags, "narrow" in flags, "paired" in flags)


def app() -> QApplication:
    found = QApplication.instance() or QApplication([])
    assert isinstance(found, QApplication)
    if not found.property("interface_language"):
        from polyglotic_desktop.ui.interface_language import install

        found.setProperty("interface_language", "en")
        install(found, "en")
    return found


@lru_cache(maxsize=512)
def _glyphs_at(
    layout: QTextLayout, positions: tuple[float, ...]
) -> tuple[tuple[int, int, QRectF], ...]:
    flags = QTextLayout.GlyphRunRetrievalFlag
    result = []
    for run in layout.glyphRuns(
        0,
        -1,
        flags.RetrieveGlyphIndexes
        | flags.RetrieveGlyphPositions
        | flags.RetrieveStringIndexes,
    ):
        font = run.rawFont()
        for char, glyph, pos in zip(
            run.stringIndexes(), run.glyphIndexes(), run.positions(), strict=True
        ):
            box = font.boundingRect(glyph).translated(pos)
            if not box.isEmpty():
                result.append((char, glyph, box))
    return tuple(result)


def glyphs(layout: QTextLayout) -> tuple[tuple[int, int, QRectF], ...]:
    """Ink boxes for the glyphs Qt shaped, with their UTF-16 offsets. The
    positions are part of the key: a spring can move a wrapped line on the
    same layout object."""
    positions = tuple(layout.lineAt(i).y() for i in range(layout.lineCount()))
    return _glyphs_at(layout, positions)


def _short(text: str) -> str:
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:8]


class _Paints(QObject):
    """Notes which surfaces Qt painted since it was last asked."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint:
            self.count += 1
        return False


class Stage:
    """One surface, set up, on the patched clock."""

    def __init__(self, stream: Stream, setup: Setup, hands: Hands) -> None:
        self.stream, self.setup, self.hands = stream, setup, hands
        self.app = app()
        self.windows: list[CaptionWindow] = []
        self.group: CaptionWindows | None = None
        self.transcript: TranscriptWindow | None = None
        self.paints = _Paints()
        size = NARROW if setup.narrow else (stream.width, stream.height)
        if setup.surface == "transcript":
            self._open_transcript(size)
        elif setup.surface == "joined":
            self._open_joined(size)
        else:
            self._open_window(size)
        for _, widget in self.canvases():
            widget.installEventFilter(self.paints)
        self.settle()

    # --- building ---

    def _open_window(self, size: tuple[int, int]) -> None:
        window = CaptionWindow(
            "Video Player.exe",
            FIRST,
            WindowChoices(show_mic=True),
            LABELS[FIRST],
            mic=OTHER,
            areas=lambda: [AREA],
        )
        self.windows.append(window)
        self.top: QWidget = window
        self._dress(window)
        window.resize(*size)
        window.show()

    def _open_joined(self, size: tuple[int, int]) -> None:
        group = CaptionWindows(None, OTHER, lambda: [AREA])
        group.clock = self.hands
        group.set_labels(LABELS, "You")
        group.set_captioned([("first", FIRST), ("second", SECOND)])
        self.group = group
        self.windows.extend(group.windows.values())
        for window in self.windows:
            self._dress(window)
        group.join()
        assert group.joined_window is not None
        self.top = group.joined_window
        self.top.resize(size[0] * len(self.windows), size[1])

    def _open_transcript(self, size: tuple[int, int]) -> None:
        hands = self.hands
        found = Transcript(
            FIRST,
            Language("en"),
            mic=OTHER,
            show_mic=True,
            clock=lambda: DAY + timedelta(seconds=hands.now - START),
        )
        window = TranscriptWindow(
            "Video Player.exe", found, LABELS[FIRST], TranscriptChoices()
        )
        window.animate = False
        window.list.zone = UTC
        if self.setup.readings:
            stream = self.stream
            window.list._readings = lambda *_: stream.readings(True)
            window.list.set_reading(replace(CaptionLook(), reading_lines=("zh", "ja")))
        self.transcript = window
        self.top = window
        window.resize(max(size[0], 480), max(size[1], 420))
        window.show()

    def _dress(self, window: CaptionWindow) -> None:
        setup, stream = self.setup, self.stream
        window.clock = self.hands
        made_up = setup.readings
        window._readings = lambda *_: stream.readings(made_up)
        look = window.look
        if setup.readings:
            look = replace(look, reading_lines=("zh", "ja"))
        window.set_look(look)
        if setup.paired:
            window.set_presets(
                replace(window.preset_menu, long_lines=LongLines.DISPLAY_NEW_LINES)
            )
        if setup.surface in ("cards", "zones"):
            window.set_cards(setup.surface == "cards")
            window.set_timing(CaptionMode.STEADY)
        elif setup.surface.startswith("video"):
            window.set_video(True)
            window.set_timing(
                CaptionMode.SCROLLING
                if setup.surface == "video-scrolling"
                else CaptionMode.INSTANT
            )
        else:
            window.set_timing(CaptionMode.INSTANT)

    # --- playing ---

    def receive(self, update: CaptionUpdate) -> None:
        if self.transcript is not None:
            self.transcript.transcript.apply(update)
            self.transcript.refresh()
        elif self.group is not None:
            self.group.apply(update)
        else:
            self.windows[0].receive(update)

    def settle(self) -> None:
        """Let Qt deliver what was posted: the paints asked for, no more."""
        self.app.sendPostedEvents()
        self.app.processEvents()

    def canvases(self) -> list[tuple[str, QWidget]]:
        if self.transcript is not None:
            return [("list", self.transcript.list)]
        found: list[tuple[str, QWidget]] = []
        for n, window in enumerate(self.windows):
            prefix = f"col{n}." if self.group is not None else ""
            found.append((prefix + "panel", window.canvas))
            found.append((prefix + "zone", window.zone))
        return found

    def close(self) -> None:
        if self.group is not None:
            self.group.close()
        else:
            self.top.close()
            shiboken6.delete(self.top)
        self.settle()

    # --- reading ---

    def frame(self, n: int) -> Frame:
        surfaces = []
        rows: list[Row] = []
        for name, widget in self.canvases():
            if widget.isHidden():
                continue
            origin = widget.mapTo(self.top, QPoint(0, 0))
            if self.transcript is not None:
                lst: Any = widget
                top = float(LIST_PAD)
                foot = LIST_PAD + float(lst._view_height())
                page = [
                    (line, laid, QRectF(at.x(), at.y(), 0, 0), 1.0)
                    for line, laid, at in getattr(lst, "drawn", ())
                ]
            else:
                canvas: Any = widget
                top, foot = float(canvas.clear_top), float(canvas.height())
                page = [(ln, laid, rect, 1.0) for ln, laid, rect in canvas.placed]
                page.extend(canvas.turning)
            surfaces.append(
                Surface(
                    name,
                    q(origin.y() + top),
                    q(origin.y() + foot),
                    q(widget.width()),
                    q(widget.height()),
                )
            )
            seen: dict[tuple[int, str, int, int], int] = {}
            for line, laid, rect, scale in page:
                for row in laid.rows:
                    rows.append(
                        _row(name, line, row, rect, scale, origin, top, foot, seen)
                    )
        bursts = sum(int(getattr(w, "bursts", 0)) for w in self.windows)
        return Frame(n, tuple(surfaces), tuple(rows), bursts)


def _row(
    surface: str,
    line: Any,
    row: Any,
    rect: QRectF,
    scale: float,
    origin: QPoint,
    top: float,
    foot: float,
    seen: dict[tuple[int, str, int, int], int],
) -> Row:
    layout = row.layout
    kind = str(row.row.kind.value)
    visual = int(getattr(row, "visual_line", 0))
    ident = (line.key, kind, row.row.clause, visual)
    nth = seen[ident] = seen.get(ident, -1) + 1
    lines = [layout.lineAt(i) for i in range(layout.lineCount())]
    inks = [part.naturalTextRect() for part in lines]
    row_top = rect.y() + scale * (row.top + (lines[0].y() if lines else 0.0))
    left = rect.x() + min((ink.x() for ink in inks), default=0.0)
    chars = []
    ink = QRectF()
    for cursor, glyph, box in glyphs(layout):
        y = rect.y() + scale * (row.top + box.top())
        if top <= y < foot:
            ink = ink.united(
                QRectF(rect.x() + box.left(), y, box.width(), scale * box.height())
            )
            chars.append(
                Char(
                    row.source_index(cursor),
                    glyph,
                    q(origin.x() + rect.x() + box.left()),
                    q(origin.y() + y),
                )
            )
    # Qt hands back a layout's glyph runs (one per font it fell back to) in
    # an order that changes from one launch to the next; the page does not.
    chars.sort(key=lambda char: (char.index, char.left, char.top, str(char.glyph)))
    readings = []
    for reading in (*getattr(row, "above", ()), *getattr(row, "below", ())):
        y = rect.y() + scale * (row.top + reading.y)
        if top <= y < foot:
            readings.append(
                Char(
                    getattr(row, "start", 0) + reading.start,
                    _short(reading.text),
                    q(origin.x() + rect.x() + reading.x),
                    q(origin.y() + y),
                )
            )
    return Row(
        surface,
        line.key,
        kind,
        row.row.clause,
        visual,
        nth,
        len(lines),
        q(origin.y() + row_top),
        q(origin.x() + left),
        q(max((ink.width() for ink in inks), default=0.0)),
        q(scale * sum(part.height() for part in lines)),
        q(float(getattr(row, "opacity", 1.0))),
        q(scale),
        (
            q(origin.x() + ink.left()),
            q(origin.y() + ink.top()),
            q(origin.x() + ink.right()),
            q(origin.y() + ink.bottom()),
        )
        if chars
        else (0, 0, 0, 0),
        tuple(chars),
        tuple(readings),
    )


@contextmanager
def _paths_seen() -> Iterator[set[str]]:
    """Which layout paths run while this is open."""
    seen: set[str] = set()
    with ExitStack() as stack:
        for method, path in PATHS.items():
            real = getattr(CaptionLayout, method, None)
            if real is None:
                continue

            def noted(
                self: Any,
                *args: Any,
                __real: Callable[..., Any] = real,
                __path: str = path,
                **kwargs: Any,
            ) -> Any:
                if __path.startswith("A"):
                    wraps = kwargs.get("wrap", True)
                    seen.add(__path + (" (Qt may wrap)" if wraps else " (one line)"))
                else:
                    seen.add(__path)
                return __real(self, *args, **kwargs)

            stack.enter_context(patch.object(CaptionLayout, method, noted))
        yield seen


@contextmanager
def staged(stream: Stream, setup: Setup) -> Iterator[tuple[Stage, set[str]]]:
    """A stage for `stream` set up as `setup`, the clock and the PC's own
    choices (reduced motion, high contrast) patched while it is open."""
    hands = Hands()
    with ExitStack() as stack:
        stack.enter_context(hands.patched())
        for module in (caption_window, caption_layout):
            for name in ("reduced_motion", "high_contrast"):
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, return_value=False))
        stack.enter_context(  # a caption's label shows when it was heard
            patch.object(
                history,
                "_utc_now",
                lambda: DAY + timedelta(seconds=hands.now - START),
            )
        )
        seen = stack.enter_context(_paths_seen())
        stage = Stage(stream, setup, hands)
        try:
            yield stage, seen
        finally:
            stage.close()
            _glyphs_at.cache_clear()


def play(
    stream: Stream,
    setup: Setup,
    *,
    each: Callable[[Stage, int], None] | None = None,
    paths: set[str] | None = None,
) -> Iterator[Frame]:
    """Every frame of `stream` on a stage set up as `setup`. `each` runs
    after a frame is read (a picture is taken there)."""
    with staged(stream, setup) as (stage, seen):
        hands = stage.hands
        events = list(stream.events)
        frames = round((stream.seconds + TAIL) / FRAME) + 1
        last: Frame | None = None
        painted = -1
        for n in range(frames):
            now = n * FRAME
            hands.advance(START + now)
            while events and events[0][0] <= now + 1e-8:
                stage.receive(events.pop(0)[1])
            stage.settle()
            if last is None or stage.paints.count != painted:
                painted = stage.paints.count
                last = stage.frame(n)
            else:
                last = replace(last, n=n)
            yield last
            if each is not None:
                each(stage, n)
        if paths is not None:
            paths.update(seen)
