"""Selecting and copying in a caption window (polyglotic-hq 358, on 340's
design and 343's shared pieces; the user, 2026-11-15: "I want drag and
select and ctrl c / right click to copy. Should be able to freely copy all
texts across all caption interface"; DECISIONS.md #159; decision 0150).

- **Where:** a selection is two places in the window's captions
  (`core.listening.selection`), never lines on the screen - so it is the
  same words after a resize, in today's layout or the New layout, and as
  captions arrive. `shown` gives the captions as the window shows them
  (its rows, a live caption's trailing "…" left off); `place_at` the place
  nearest the mouse; `held_rects` where the held words are drawn.
- **Kept** (`HeldSelection`) from the drag's release until a click
  elsewhere or Esc - in this app, through an event filter; over another
  app (a game), by reading Windows' key state while it's held (`keys`,
  read, not taken: Esc and a mouse button, as the lookup card does).
- **Copied** by a right-click on it (`copying.copy_quietly`: no menu,
  never the keyboard, "Copied" by the mouse), or by Ctrl+C while one of
  this app's windows has the keyboard - the caption window itself never
  takes it, so a game in front keeps it.

Only the clipboard: nothing selected or copied is logged, sent or kept.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.display import LIVE_TRAIL, RowKind
from polyglotic_desktop.core.listening.selection import (
    Place,
    Selection,
    selected,
    selected_text,
)
from polyglotic_desktop.ui_next.caption_layout import LaidLine
from polyglotic_desktop.ui_next.copying import copy_key_is_ours, copy_quietly
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.sentences import Piece

if TYPE_CHECKING:
    from polyglotic_desktop.ports.system import KeyState

POLL_MS = 40
"""How often Windows' key state is read while a selection is held (the
lookup card's)."""
PADDING = (-3.0, 0.0, 3.0, 0.0)
"""Around each run of held words, as around a hovered word."""

Placed = Sequence[tuple[Line, LaidLine, QRectF]]
"""What a canvas last drew: each line, laid out, and where."""


@dataclass(frozen=True, slots=True)
class ShownClause:
    """A clause's text on each side, as its rows show it."""

    original: str = ""
    translation: str = ""

    def text(self, side: RowKind) -> str:
        return self.original if side is RowKind.ORIGINAL else self.translation


@dataclass(frozen=True, slots=True)
class ShownCaption:
    key: int
    clauses: tuple[ShownClause, ...]


def shown(lines: Sequence[Line]) -> list[ShownCaption]:
    """`lines`' captions as the window shows them: each clause's rows -
    the translation shown (its second language's, where the target has
    none), no original with Original hidden - without a live caption's
    trailing "…"."""
    found = []
    for line in lines:
        texts: dict[int, dict[RowKind, str]] = {}
        for row in line.rows:
            text = row.text.removesuffix(LIVE_TRAIL) if line.live else row.text
            texts.setdefault(row.clause, {})[row.kind] = text
        count = max(texts, default=-1) + 1
        clauses = tuple(
            ShownClause(
                texts.get(n, {}).get(RowKind.ORIGINAL, ""),
                texts.get(n, {}).get(RowKind.TRANSLATION, ""),
            )
            for n in range(count)
        )
        found.append(ShownCaption(line.key, clauses))
    return found


def place_at(placed: Placed, pos: QPointF, top: float) -> Place | None:
    """The place in the drawn text nearest `pos`: on the nearest line of
    text (above or below it, the nearest by height; beside it, by width),
    between the characters the mouse is between. Lines above `top` (under
    the band) aren't drawn, so aren't there. None with no text drawn."""
    best: tuple[tuple[float, float], Place] | None = None
    for line, laid, rect in placed:
        for row in laid.rows:
            layout = row.layout
            origin = QPointF(rect.x(), rect.y() + row.top)
            length = len(row.row.text.removesuffix(LIVE_TRAIL))
            for n in range(layout.lineCount()):
                text_line = layout.lineAt(n)
                box = QRectF(
                    origin.x() + text_line.x(),
                    origin.y() + text_line.y(),
                    text_line.naturalTextWidth(),
                    text_line.height(),
                )
                if box.bottom() <= top:
                    continue
                down = max(box.top() - pos.y(), 0.0, pos.y() - box.bottom())
                across = max(box.left() - pos.x(), 0.0, pos.x() - box.right())
                if best is not None and (down, across) >= best[0]:
                    continue
                char = text_line.xToCursor(pos.x() - origin.x())
                place = Place(
                    line.key,
                    row.row.clause,
                    min(row.source_index(char), row.start + length),
                    row.row.kind,
                )
                best = ((down, across), place)
    return best[1] if best is not None else None


def held_words(lines: Sequence[Line], selection: Selection) -> dict[int, list[Words]]:
    """The words `selection` holds in `lines`, by line key."""
    found: dict[int, list[Words]] = {}
    for key, words in selected(shown(lines), selection):
        found.setdefault(key, []).append(words)
    return found


def held_pieces(lines: Sequence[Line], selection: Selection) -> list[Piece]:
    """The rows `selection` holds in `lines`, each with its selected
    characters, in reading order: what `views.sentences` saves
    (polyglotic-hq 459)."""
    by_key = {line.key: line for line in lines}
    found: list[Piece] = []
    for key, words in selected(shown(lines), selection):
        line = by_key[key]
        row = next(
            (r for r in line.rows if (r.clause, r.kind) == (words.clause, words.side)),
            None,
        )
        if row is not None:
            found.append((line, row, words.start, words.end))
    return found


def word_rects(laid: LaidLine, words: Sequence[Words]) -> list[QRectF]:
    """Where `words` of a line laid out as `laid` are drawn, from its top
    left: a rectangle per line of text each run of them is on."""
    rows = {(row.row.clause, row.row.kind): row for row in laid.rows}
    found = []
    for each in words:
        row = rows.get((each.clause, each.side))
        if row is None:
            continue
        for rect in row.rectangles(each.start, each.end):
            found.append(rect.translated(0.0, row.top).adjusted(*PADDING))
    return found


def held_rects(placed: Placed, selection: Selection) -> list[QRectF]:
    """Where the held words are drawn now, in the canvas."""
    held = held_words([line for line, _, _ in placed], selection)
    return [
        rect.translated(where.x(), where.y())
        for line, laid, where in placed
        for rect in word_rects(laid, held.get(line.key, ()))
    ]


class HeldSelection(QObject):
    """A caption window's selection, from the drag's release until a click
    elsewhere or Esc: copied by a right-click on it or by Ctrl+C. `window`
    is the caption window (or column) it's in; `captions` gives the
    window's captions as shown, oldest first; `copy_is_cards` says the
    lookup card has Ctrl+C now (pinned, by a phrase from this selection);
    `changed` repaints it."""

    def __init__(
        self,
        window: QWidget,
        captions: Callable[[], list[ShownCaption]],
        keys: "KeyState | None",
        copy_is_cards: Callable[[], bool],
        changed: Callable[[], None],
    ) -> None:
        super().__init__(window)
        self.window = window
        self.captions = captions
        self.keys = keys
        self.copy_is_cards = copy_is_cards
        self.changed = changed
        self.selection: Selection | None = None
        """What's selected: drawn while it's dragged, then held."""
        self.keeps: list[QWidget] = []
        """Windows of its own whose clicks don't let go of it: the card
        that saves it as a sentence (polyglotic-hq 459)."""
        self.watching = False
        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self._look_at_keys)

    def draw(self, selection: Selection) -> None:
        """`selection` being dragged out: drawn, not yet held."""
        if selection != self.selection:
            self.selection = selection
            self.changed()

    def hold(self, selection: Selection | None = None) -> None:
        """The drag let go of: `selection` (or the one drawn) held until a
        click elsewhere or Esc."""
        if selection is not None:
            self.draw(selection)
        if self.selection is None or self.watching:
            return
        self.watching = True
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        if self.keys is not None:
            for name in ("escape", "mouse"):
                self.keys(name)  # forget the presses of the drag itself
            self._poll.start()

    def clear(self) -> None:
        if self.watching:
            self.watching = False
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._poll.stop()
        if self.selection is not None:
            self.selection = None
            self.changed()

    def text(self) -> str:
        if self.selection is None:
            return ""
        return selected_text(self.captions(), self.selection)

    def copy(self, at: QPoint) -> bool:
        """The held words to the clipboard, "Copied" by `at` (on the
        screen); False with none held."""
        text = self.text()
        if not text:
            return False
        copy_quietly(text, at, self.window)
        return True

    def _over_window(self, at: QPoint) -> bool:
        return self.window.rect().contains(self.window.mapFromGlobal(at))

    def _look_at_keys(self) -> None:
        """Over another app (a game has the keyboard): Esc, or a click
        that isn't on this app's windows, lets go of it."""
        keys = self.keys
        if keys is None or self.selection is None:
            return
        if keys("escape"):
            self.clear()
            return
        if keys("mouse"):
            at = QCursor.pos()
            if not self._over_window(at) and QApplication.widgetAt(at) is None:
                self.clear()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """While held, in this app: Esc and a click on another of its
        windows let go of it; Ctrl+C copies it."""
        kind = event.type()
        if kind == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape:
                self.clear()
            elif copy_key_is_ours(event) and not self.copy_is_cards():
                return self.copy(QCursor.pos())
        elif (
            kind == QEvent.Type.MouseButtonPress
            and isinstance(watched, QWidget)
            and watched is not self.window
            and not self.window.isAncestorOf(watched)
            and watched.window() not in self.keeps
        ):
            self.clear()
        return False
