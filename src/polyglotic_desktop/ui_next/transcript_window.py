"""W2, the transcript window: one app's finished captions this session
(polyglotic-hq project 109's structure, section 3; the user, 2026-11-06:
"a different transcript per app", and its settings in the window).

A normal window - title bar, taskbar entry - in the new interface's
window theme (`ui_next.style`: today's theme's colours, which `main`
hands over), dressed by a stylesheet of its own. Its parts:
- **the app strip:** the app's dot and label (and the mic mark while its
  caption window shows my speech); its caption window's language (or
  Original only) and the session's timing - the same controls as the
  caption window's; A- / A+ for this transcript's own text size; search;
  Copy all; Save transcript as…; Settings. Below `FOLD_BELOW` px, Copy
  all and Save as… fold into "…".
- **the list** (`TranscriptList`): painted on the caption layout engine,
  only the lines that show laid out - 1,000 lines listed, never a document
  rebuilt (today's took 87-116 ms per caption; project 108). Each line:
  its time, "You" for my speech, the language spoken, "checked by the
  best model" - then what was said and its translation, saved words in
  their category's colour, search matches marked. Follows the newest
  line until scrolled back ("Back to live · N new"); right-click copies a
  line - as Copy all
  writes it, what was said alone, or its translation alone (333).
  **Selecting** (polyglotic-hq 343): a drag across lines and within them
  selects what was said and translations as they show (`anchor`, `head`:
  places in the text, so lines scrolled away stay selected; above or below
  the list, a drag scrolls); Shift-click extends it; Ctrl+C, Ctrl+A and
  the right-click menu - Copy, Select all, in place of the line's while
  something is selected - copy it (`views.transcript.selected_text`).
  **The lookup:**
  the word under the mouse - by the word split - is drawn softly behind
  and looked up in the card every caption window shares (`lookup_card`,
  owned by `CaptionWindows`) once the mouse rests; a click pins it, on
  release, unless the mouse dragged (today's transcript: hover to look
  up, click to keep it open).
- **the settings rail** (`SettingsRail`): slides in from the right and
  narrows the list; below 700 px wide it opens as a popover instead. It
  holds the session's three panels (`ui_next.panels`: Languages - with
  "This window", its caption window's language and Show my speech here -
  Timing and Look), made the first time the rail opens.
- **the foot:** "N lines · following", "· scrolled back", "N matches"; past
  the lines listed, that Copy all and Save have them all (137); and,
  while not searching, that the transcript is gone when the app quits
  unless it's saved - it's kept this session only (polyglotic-hq 228);
  the list itself says "Nothing yet - finished captions collect here." or
  "No matches." (today's wording).

**Its own layout cache** (decided in project 116, 110's open question):
a transcript and its caption window never lay out a line at the same
width, text size and style - the transcript has its own text size, its
own width (less its rail), its own type (theme colours, 16 px, a heading
per line) and only finished captions - so a shared cache would have no
hits, while its keys would need the view in them and the two windows'
evictions would be tied. Each surface keeps its own (`CaptionLayout`),
of `LINES_LAID_OUT` lines (polyglotic-hq 239).

Holds caption text: never log it.
"""

import bisect
import logging
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, tzinfo
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QLocale,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QContextMenuEvent,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QHideEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QShortcut,
    QShowEvent,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.lookups import LookupContext, lookup_context
from polyglotic_desktop.core.learning.saved_words import Category, SavedSpan
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.display import RowKind, clause_versions
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.offers import Use, offered
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode
from polyglotic_desktop.core.listening.transcript import (
    as_csv,
    as_srt,
    as_text,
    translation_text,
)
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next import reading_lines, style, wheel
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
    Mark,
    char_under,
    span_rects,
)
from polyglotic_desktop.ui_next.caption_marks import Learner
from polyglotic_desktop.ui_next.caption_selection import word_rects
from polyglotic_desktop.ui_next.caption_window import (
    Marked,
    live_tip,
    notice_text,
    timing_name,
    timing_tip,
)
from polyglotic_desktop.ui_next.copying import (
    COPIED_MS,
    TYPING,
    copied,
    say_copied,
    selection_menu,
)
from polyglotic_desktop.ui_next.languages import (
    in_sentence,
    language_name,
    shown_name,
    spoken_names,
    target_languages,
)
from polyglotic_desktop.ui_next.lookup_card import (
    LookupCard,
    better_voice_steps,
    dismiss_text,
    never_again_text,
    no_voice_steps,
)
from polyglotic_desktop.ui_next.os_words import hotkeys_here
from polyglotic_desktop.ui_next.save_folder import SaveFolder
from polyglotic_desktop.ui_next.selection_reading import SAID_NOW, SelectionReading
from polyglotic_desktop.ui_next.sentence_card import (
    save_to_text,
    saved_to_text,
    say_it_text,
    side_text,
)
from polyglotic_desktop.ui_next.toast import show_toast
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    CaptionLook,
    Notice,
    stepped,
)
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.lookup import WordAt, with_counterpart
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.scroll import Anchor, Placed
from polyglotic_desktop.ui_next.views.sentences import (
    Selected,
    SideAloud,
    selected_sentence,
    sides_aloud,
    worth_saving,
)
from polyglotic_desktop.ui_next.views.speech import Say
from polyglotic_desktop.ui_next.views.tone import vibrant
from polyglotic_desktop.ui_next.views.transcript import (
    MIN_SIZE,
    MOST_OF_AREA,
    RAIL_WIDTH,
    Spot,
    Transcript,
    TranscriptChoices,
    match_spans,
    rail_inline,
    selected_pieces,
    selected_spans,
    selected_text,
)

PAD = 16
"""Pixels around the lines."""
GAP = 14
"""Pixels between lines, at text size 1.0."""
HEADING_GAP = 3
"""Pixels between a line's heading and what was said, at text size 1.0."""
HEADING_PX = 12
SELECTED = 0.35
"""Selected text's background: the focus colour, this opaque (343)."""
WHEEL_STEP = 60
"""Pixels scrolled per notch of the mouse wheel."""
FOLD_BELOW = 820
"""Narrower than this, Copy all and Save as… fold into "…" and Settings
shows its gear alone: the strip fits down to the minimum, 520 px."""
RAIL_SLIDE_MS = 160
LINES_LAID_OUT = 300
"""Lines whose layouts - what was said and its heading - a transcript
keeps, the least recently shown dropped first: several screens of the
1,000 it lists, even at the smallest text on a tall window (about 50 a
screen). A line scrolled back to past them is laid out again as it shows,
as a resize lays out every line in view (polyglotic-hq 239: kept for all
2,500 lines, the layouts grew the app about 15 KB a line, all evening)."""
STYLE = CaptionStyle(
    text_px=16.0,
    row_gap=2.0,
    clause_gap=5.0,
    weight=QFont.Weight.Normal,
)
"""The transcript's type: a page to read, not captions over a video."""
YOU = "#7c9cff"
""""You" (my speech), as everywhere."""


def _tr(text: str) -> str:
    return QApplication.translate("TranscriptWindow", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("TranscriptWindow", text, None, n)


log = logging.getLogger(__name__)


def not_saved(name: str) -> str:
    """What Save transcript as... says when the file couldn't be written:
    open in another program (Excel locks a CSV it has open), or a folder
    that can't be written to."""
    return _tr(
        "Couldn't save {name}. It may be open in another program, or the "
        "folder may be read-only - close it or pick another folder, and "
        "try again."
    ).format(name=name)


@dataclass(frozen=True, slots=True)
class TranscriptColors:
    """The colours the list paints with ("#rrggbb"), from the window theme
    (`of`): by default today's Margin, dark. `light`: a light theme -
    bright colours (saved words', "You") drawn darker to read on it."""

    background: str = "#11151d"
    surface: str = "#181d27"
    surface_2: str = "#1f2532"
    surface_3: str = "#232b3a"
    border: str = "#2a3140"
    text: str = "#e9ecf1"
    dim: str = "#a3abb9"
    faint: str = "#8c95a5"
    accent: str = "#e9ecf1"
    accent_text: str = "#11151d"
    success: str = "#6fcf97"
    focus: str = "#ff8fbe"
    marker: str = "#5c2440"
    light: bool = False

    def readable(self, color: str) -> QColor:
        """A bright colour as it reads on this theme."""
        found = QColor(color)
        return found.darker(170) if self.light else found

    @classmethod
    def of(cls, theme: style.Theme) -> "TranscriptColors":
        """The colours of a window theme."""
        return cls(
            background=theme["BG"],
            surface=theme["SURFACE"],
            surface_2=theme["SURFACE_2"],
            surface_3=theme["SURFACE_3"],
            border=theme["BORDER"],
            text=theme["TEXT"],
            dim=theme["TEXT_DIM"],
            faint=theme["TEXT_FAINT"],
            accent=theme["ACCENT"],
            accent_text=theme["ACCENT_TEXT"],
            success=theme["SUCCESS"],
            focus=theme["FOCUS"],
            marker=theme["MARKER"],
            light=not theme.dark,
        )


def stylesheet(theme: style.Theme) -> str:
    """The window's own stylesheet - scoped to it, never the app's: the new
    interface's (`style.stylesheet`, which the panels in its rail need),
    and the transcript's own parts."""
    c = TranscriptColors.of(theme)
    return (
        style.stylesheet(theme)
        + f"""
QWidget#transcript_window {{ background: {c.background}; }}
QWidget#transcript_window\\.strip {{ border-bottom: 1px solid {c.border}; }}
QWidget#transcript_window\\.strip QToolButton {{ background: transparent;
  border: 1px solid transparent; border-radius: 6px; padding: 3px 6px; }}
QWidget#transcript_window\\.strip QToolButton:hover {{ background: {c.surface_2}; }}
QWidget#transcript_window\\.strip QToolButton:checked {{ background: {c.surface_3}; }}
QWidget#transcript_window\\.strip QToolButton[chip="true"] {{ border: 1px solid {c.border}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#transcript_window\\.back_to_live {{ background: {c.accent};
  color: {c.accent_text}; border: none; border-radius: 10px; padding: 3px 14px;
  font-weight: 600; }}
QLabel#transcript_window\\.notice {{ background: {c.surface}; border: 1px solid {c.border};
  border-radius: 9px; padding: 2px 12px; }}
QLabel[foot="true"] {{ color: {c.dim}; font-size: {style.px(12)}px; }}
QLineEdit#transcript_window\\.search {{ placeholder-text-color: {c.dim}; }}
QScrollArea#transcript_window\\.rail {{ background: {c.background}; border: none;
  border-left: 1px solid {c.border}; }}
QWidget#transcript_window\\.rail_column {{ background: {c.background}; }}
"""
    )


# -- the list ------------------------------------------------------------------------------


def _rect(rect: QRect) -> Rect:
    return Rect(rect.x(), rect.y(), rect.width(), rect.height())


@dataclass(frozen=True, slots=True)
class _Heading:
    """A line's heading laid out: what it says, and its layout."""

    said: tuple[object, ...]
    layout: QTextLayout
    height: float
    you: tuple[int, int] | None
    checked: tuple[int, int] | None


class TranscriptList(QWidget):
    """A transcript's lines, painted: only those that show are laid out."""

    copy_wanted = Signal(int, str)
    """A line's key and what of it to copy: "both" (as Copy all writes
    it), "said" (what was said) or "translation" (polyglotic-hq 333)."""
    text_step = Signal(int)
    """Ctrl+wheel: the text a step bigger (1) or smaller (-1)."""
    scrolled = Signal()

    def __init__(
        self,
        transcript: Transcript,
        colors: TranscriptColors,
        learner: Learner | None = None,
        you: SourceLabel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("transcript_window.list")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.transcript = transcript
        self.colors = colors
        self.learner = learner
        self.you = you or SourceLabel("You", YOU)
        self.tone = (0, 0)
        """The caption windows' contrast and vibrance (`set_tone`; 481)."""
        self.zone: tzinfo | None = None  # None: this PC's time zone
        self.engine = CaptionLayout(STYLE, lines_kept=LINES_LAID_OUT)
        self._readings = reading_lines.sources(learner) if learner else None
        """Where its rows' reading lines come from (369): every word's, or
        only those past what the learner knows."""
        self.placed: list[tuple[Line, QRectF]] = []
        """The lines the last paint drew, and where (heading and rows)."""
        self.drawn: list[tuple[Line, LaidLine, QPointF]] = []
        """The lines the last paint drew: their rows, and where they start."""
        self.card: LookupCard | None = None
        """The lookup card every caption window and transcript shares."""
        self.say_it: SelectionReading | None = None
        """Reads the selection aloud from its menu (polyglotic-hq 495)."""
        self.said_now: dict[int, list[Words]] = {}
        """The word being read aloud, by line key: lit behind it."""
        self.hovered: Marked | None = None
        """The word under the mouse: drawn softly behind, looked up."""
        self.hovered_line: int | None = None
        """The caption block under the mouse (for Ctrl+C with no selection)."""
        self.anchor: Spot | None = None
        """Where the selection starts (343): a press, or Shift-click's other
        end."""
        self.head: Spot | None = None
        """Where it ends: where the mouse is dragged to."""
        self._press: QPointF | None = (
            None  # the left button down here: a click or a drag
        )
        self._dragging = False
        self.shown = 0
        self._drawn_revision = -1
        self._headings: OrderedDict[int, _Heading] = OrderedDict()
        self._saved: dict[int, tuple[object, list[list[Mark]]]] = {}
        self._formats: dict[tuple[str, str], QTextCharFormat] = {}
        self._syncing = False
        self.bar = QScrollBar(Qt.Orientation.Vertical, self)
        self.bar.setObjectName("transcript_window.scrollbar")
        self.bar.setCursor(Qt.CursorShape.ArrowCursor)
        self.bar.valueChanged.connect(self._bar_moved)

    # -- measuring --------------------------------------------------------------------

    def _width(self) -> int:
        return max(1, self.width() - 2 * PAD - self.bar.width())

    def _scale(self) -> float:
        return self.transcript.text_size

    def _gap(self) -> float:
        return GAP * self._scale()

    def _laid(self, line: Line) -> LaidLine:
        return self.engine.laid(line, self._width(), self._scale())

    def _height(self, line: Line) -> float:
        heading = self._heading(line)
        return heading.height + HEADING_GAP * self._scale() + self._laid(line).height

    def _view_height(self) -> float:
        return max(1.0, self.height() - 2.0 * PAD)

    def _heading(self, line: Line) -> _Heading:
        """The heading over `line`: its time, "You", the language spoken
        and "checked by the best model" - laid out once per line, text size
        and what it says."""
        px = max(8, round(HEADING_PX * min(self._scale(), 1.6)))
        said = (
            line.started_at,
            line.by_you,
            line.heard,
            line.checked,
            line.respoken,
            px,
            self.you,
        )
        found = self._headings.get(line.key)
        if found is not None and found.said == said:
            self._headings.move_to_end(line.key)
            return found
        found = self._headings[line.key] = self._lay_heading(line, said, px)
        if len(self._headings) > LINES_LAID_OUT:
            self._headings.popitem(last=False)
        return found

    def _lay_heading(self, line: Line, said: tuple[object, ...], px: int) -> _Heading:
        time = line.started_at.astimezone(self.zone)
        parts = [f"{time:%H:%M:%S}"]
        you = checked = None
        at = len(parts[0])
        if line.by_you:
            at += 3
            you = (at, at + len(self.you.name))
            parts.append(self.you.name)
            at = you[1]
        if line.respoken:  # said again by the learner, for its app (567)
            words = _tr("re-spoken")
            parts.append(words)
            at += 3 + len(words)
        heard = spoken_names(str(lang) for lang in line.heard if lang)
        if heard:
            parts.append(heard)
            at += 3 + len(heard)
        if line.checked:
            words = _tr("checked by the best model")
            at += 3
            checked = (at, at + len(words))
            parts.append(words)
        font = QFont()
        font.setFamilies(style.UI_FAMILIES)
        font.setPixelSize(px)
        layout = QTextLayout(" · ".join(parts), font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.NoWrap)
        layout.setTextOption(option)
        layout.setCacheEnabled(True)
        layout.beginLayout()
        text_line = layout.createLine()
        text_line.setLineWidth(100_000)
        text_line.setPosition(QPointF(0, 0))
        layout.endLayout()
        return _Heading(said, layout, text_line.height(), you, checked)

    # -- marks, drawn at paint time -----------------------------------------------------

    def marks(self, line: Line, row: int) -> Sequence[Mark]:
        """A row's marks: saved words in their category's colour, and where
        the search matches."""
        saved = self._saved.get(line.key)
        if saved is None or saved[0] is not line.rows:
            if len(self._saved) > LINES_LAID_OUT:
                self._saved.clear()
            saved = (line.rows, self._saved_marks(line))
            if self.learner is None or self.learner.ready:
                self._saved[line.key] = saved  # else found again once it is
        rows = saved[1]
        found = list(rows[row]) if row < len(rows) else []
        search = self.transcript.search_pattern
        if search is not None and row < len(line.rows):
            marker = self._format("match", self.colors.marker)
            found += [
                (a, b, marker) for a, b in match_spans(line.rows[row].text, search)
            ]
        return found

    def _saved_marks(self, line: Line) -> list[list[Mark]]:
        """Saved words in their category's colour (today's transcript)."""
        marks: list[list[Mark]] = [[] for _ in line.rows]
        learner = self.learner
        if learner is None or not learner.ready:
            return marks
        for index, row in enumerate(line.rows):
            # each row by its own language's learning data (DECISIONS #110)
            ours = learner.of(row.language)
            vocabulary = ours.vocabulary
            if not vocabulary.saved_words:
                continue
            spans_found: list[SavedSpan] = vocabulary.saved_spans(
                row.text, ours.words_in(row.text)
            )
            for span in spans_found:
                saved = vocabulary.saved_word(span.entry_id)
                category = vocabulary.category(saved.category_id) if saved else None
                if category is not None:
                    marks[index].append(
                        (
                            span.start,
                            span.end,
                            self._format("saved", self._vivid(category.color)),
                        )
                    )
        return marks

    def _vivid(self, color: str) -> str:
        """`color` at the caption windows' vibrance (481)."""
        return vibrant(color, self.tone[1])

    def _format(self, kind: str, color: str) -> QTextCharFormat:
        found = self._formats.get((kind, color))
        if found is None:
            found = QTextCharFormat()
            if kind == "match":
                found.setBackground(QColor(color))
            else:
                found.setForeground(self.colors.readable(color))
            self._formats[(kind, color)] = found
        return found

    def learning_changed(self, what: str) -> None:
        """Saved words or their colours changed: drawn again (not for
        exposures, which change with every finished caption). A word known
        now or new again: its pinyin goes or comes, with Past what you
        know (369)."""
        if what == Changed.SAVED_WORDS.value:
            self._saved.clear()
            self.update()
        style = self.engine.style
        if what in (Changed.STATUSES.value, Changed.LEVEL.value) and (
            style.follows_known
        ):
            self._lay_out_again(style)

    def set_reading(self, look: CaptionLook) -> None:
        """The caption windows' reading lines, here too: pinyin above
        Chinese, its size, and every word or only the words past what the
        learner knows (369, decision 0155)."""
        style = replace(
            STYLE,
            reading_lines=frozenset(look.reading_lines),
            reading_share=reading_lines.SHARES[look.reading_size],
            reading_past=look.reading_past,
            respelling_past=look.respelling_past,
            reading_system=look.reading_system,
            japanese_reading=look.japanese_reading,
        )
        if style != self.engine.style:
            self._lay_out_again(style)

    def set_tone(self, look: CaptionLook) -> None:
        """The caption windows' contrast and vibrance, here too (481): the
        rows' ink soft or crisp on the window's background, saved words and
        "You" in their colours at the vibrance."""
        tone = (look.contrast, look.vibrance)
        if tone != self.tone:
            self.tone = tone
            self._formats.clear()
            self.update()

    def dictionary_ready(self) -> None:
        """The dictionary's word split is read: lines laid out before it
        without their pinyin are laid out again with it."""
        if self.engine.style.reading_lines:
            self._lay_out_again(self.engine.style)

    def _lay_out_again(self, style: CaptionStyle) -> None:
        readings = (
            self._readings(
                style.reading_past, style.respelling_past, style.japanese_reading
            )
            if self._readings
            else None
        )
        self.engine = CaptionLayout(style, lines_kept=LINES_LAID_OUT, readings=readings)
        self.update()

    def set_colors(self, colors: TranscriptColors) -> None:
        self.colors = colors
        self._formats.clear()
        self._saved.clear()
        self.update()

    # -- what shows ---------------------------------------------------------------------

    def changed(self) -> None:
        """The transcript changed: repaint, if what it shows did."""
        if self.transcript.revision != self._drawn_revision:
            self.update()

    def _placed(self) -> list[Placed[Line]]:
        return self.transcript.scroll.placed(
            self.transcript.lines, self._height, self._view_height(), self._gap()
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        with spans.span("transcript.paint"):
            self._paint()

    def _paint(self) -> None:
        colors = self.colors
        lines = self.transcript.lines
        placed = self._placed()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(colors.background))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.save()
        painter.setClipRect(QRectF(0, PAD, self.width(), self._view_height()))
        ink = Ink(
            QColor(colors.text),
            QColor(colors.dim),
            QColor(colors.faint),
            1.0,
            panel=colors.background,
            contrast=self.tone[0],
        )
        width = self._width()
        self.placed, self.drawn = [], []
        for item in placed:
            line = item.line
            heading = self._heading(line)
            top = PAD + item.top
            painter.setPen(QColor(colors.faint))
            heading.layout.draw(
                painter, QPointF(PAD, top), self._heading_marks(heading)
            )
            laid = self._laid(line)
            rows_top = top + heading.height + HEADING_GAP * self._scale()
            at = QPointF(PAD, rows_top)
            if self.hovered is not None and self.hovered.key == line.key:
                self._paint_hovered(painter, laid, at, self.hovered)
            self._paint_selected(painter, line, laid, at)
            self._paint_said_now(painter, line, laid, at)
            self.engine.paint(painter, line, laid, at, ink, self.marks)
            self.drawn.append((line, laid, at))
            self.placed.append(
                (line, QRectF(PAD, top, width, rows_top - top + laid.height))
            )
        painter.restore()
        if not lines:
            self._paint_empty(painter)
        painter.end()
        self.shown = len(placed)
        self._drawn_revision = self.transcript.revision
        self._sync_bar(lines, placed)

    def _heading_marks(self, heading: _Heading) -> list[QTextLayout.FormatRange]:
        found = []
        for span, color, bold in (
            (heading.you, self.colors.readable(self._vivid(self.you.color)), True),
            (heading.checked, QColor(self.colors.success), False),
        ):
            if span is None:
                continue
            format_ = QTextCharFormat()
            format_.setForeground(color)
            if bold:
                format_.setFontWeight(QFont.Weight.DemiBold)
            selection = QTextLayout.FormatRange()
            selection.start, selection.length = span[0], span[1] - span[0]
            selection.format = format_
            found.append(selection)
        return found

    def _paint_selected(
        self, painter: QPainter, line: Line, laid: LaidLine, at: QPointF
    ) -> None:
        """Behind the selected text of `line`, if any."""
        if self.anchor is None or self.head is None:
            return
        spans = selected_spans(line, self.anchor, self.head)
        if not spans:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        selected = QColor(self.colors.focus)
        selected.setAlphaF(SELECTED)
        painter.setBrush(selected)
        rows = {row.index: row for row in laid.rows}
        for index, begin, end in spans:
            row = rows.get(index)
            if row is None:
                continue
            for rect in span_rects(row.layout, begin, end):
                painter.drawRect(rect.translated(at.x(), at.y() + row.top))

    def _paint_said_now(
        self, painter: QPainter, line: Line, laid: LaidLine, at: QPointF
    ) -> None:
        """Behind the word being read aloud, if it's in `line` (495)."""
        words = self.said_now.get(line.key)
        if not words:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SAID_NOW)
        for box in word_rects(laid, words):
            painter.drawRoundedRect(box.translated(at), 6, 6)

    def _paint_hovered(
        self, painter: QPainter, laid: LaidLine, at: QPointF, marked: Marked
    ) -> None:
        """Behind the word under the mouse: a soft highlight."""
        row = next((r for r in laid.rows if r.index == marked.row), None)
        if row is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colors.surface_3))
        for rect in span_rects(row.layout, marked.start, marked.end):
            box = rect.translated(at.x(), at.y() + row.top).adjusted(-2, 0, 2, 0)
            painter.drawRoundedRect(box, 6, 6)  # the scale's small corner

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QColor(self.colors.dim))
        font = QFont()
        font.setFamilies(style.UI_FAMILIES)
        font.setPixelSize(style.px(14))
        painter.setFont(font)
        painter.drawText(
            QRectF(PAD, PAD, self._width(), self._view_height()),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            _tr("No matches.")
            if self.transcript.search_pattern is not None
            else _tr("Nothing yet - finished captions collect here."),
        )

    # -- scrolling ----------------------------------------------------------------------

    def _sync_bar(self, lines: Sequence[Line], placed: list[Placed[Line]]) -> None:
        """The scroll bar, in lines: where the top line shown is, of all."""
        maximum = max(0, len(lines) - len(placed))
        if self.transcript.scroll.following or not placed:
            value = maximum
        else:
            first = bisect.bisect_left(lines, placed[0].line.key, key=lambda ln: ln.key)
            value = min(first, maximum)
        self.bar.setVisible(maximum > 0)
        if (self.bar.maximum(), self.bar.value(), self.bar.pageStep()) == (
            maximum,
            value,
            max(1, len(placed)),
        ):
            return
        self._syncing = True
        self.bar.setRange(0, maximum)
        self.bar.setPageStep(max(1, len(placed)))
        self.bar.setValue(value)
        self._syncing = False

    def _bar_moved(self, value: int) -> None:
        if self._syncing:
            return
        lines = self.transcript.lines
        scroll = self.transcript.scroll
        if value >= self.bar.maximum() or not lines:
            scroll.follow()
        else:
            scroll.anchor = Anchor(lines[value].key, 0.0)
        self.update()
        self.scrolled.emit()

    def scroll_by(self, dy: float) -> None:
        """Back to older lines if `dy` is positive, towards the newest if not."""
        with spans.span("transcript.scroll_step"):
            self.transcript.scroll.scroll_by(
                dy,
                self.transcript.lines,
                self._height,
                self._view_height(),
                self._gap(),
            )
            self.update()
        self.scrolled.emit()

    def go_to_oldest(self) -> None:
        lines = self.transcript.lines
        if lines:
            self.transcript.scroll.anchor = Anchor(lines[0].key, 0.0)
            self.update()
            self.scrolled.emit()

    # -- events ---------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        width = self.bar.sizeHint().width()
        self.bar.setGeometry(self.width() - width - 2, 2, width, self.height() - 4)

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if notches:
                self.text_step.emit(1 if notches > 0 else -1)
        elif notches:
            self.scroll_by(notches * WHEEL_STEP * self._scale())
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        page = self._view_height() - 40
        key = event.key()
        reading = self.say_it
        if (
            key == Qt.Key.Key_Escape
            and reading is not None
            and reading.reading is not None
            and reading.reading[0] is self
        ):
            reading.stop()  # Esc stops it reading (495)
        elif event.matches(QKeySequence.StandardKey.Copy) and self.copy_by_key():
            event.accept()
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
        elif key == Qt.Key.Key_PageUp:
            self.scroll_by(page)
        elif key == Qt.Key.Key_PageDown:
            self.scroll_by(-page)
        elif key == Qt.Key.Key_Up:
            self.scroll_by(WHEEL_STEP)
        elif key == Qt.Key.Key_Down:
            self.scroll_by(-WHEEL_STEP)
        elif key == Qt.Key.Key_Home:
            self.go_to_oldest()
        elif key == Qt.Key.Key_End:
            self.transcript.go_live()
            self.update()
            self.scrolled.emit()
        else:
            super().keyPressEvent(event)

    def line_at(self, y: float) -> Line | None:
        for line, rect in self.placed:
            if rect.top() <= y < rect.bottom() + self._gap():
                return line
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._press is not None:  # the left button is down: a drag selects
            far = (pos - self._press).manhattanLength()
            self._dragging = self._dragging or far >= QApplication.startDragDistance()
            if self._dragging:
                self._drag_to(pos)
            return
        line = self.line_at(pos.y())
        self.hovered_line = line.key if line is not None else None
        word = self._marked_at(pos)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if word is not None
            else Qt.CursorShape.ArrowCursor
        )
        self._hover(word)

    def leaveEvent(self, event: QEvent) -> None:
        self.hovered_line = None
        self._hover(None)

    def hideEvent(self, event: QHideEvent) -> None:
        """Its transcript window closed or hid: a card pinned from here goes
        too (polyglotic-hq 133)."""
        if self.card is not None:
            self.card.closed_with(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """The left button starts a selection - Shift extends the one there
        is; a click without a drag looks the word up, on release."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = event.position()
        spot = self.spot_at(pos)
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if shift and self.anchor is not None and spot is not None:
            self.head = spot
            self.update()
            return
        self._press, self._dragging = pos, False
        self.anchor = self.head = spot
        if self.say_it is not None:  # a new selection: no more reading it
            self.say_it.stop_for(self)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            super().mouseReleaseEvent(event)
            return
        dragged, self._press, self._dragging = self._dragging, None, False
        if dragged:
            return
        word = self._marked_at(event.position())
        found = self.word_at(word) if word is not None else None
        if found is not None and self.card is not None:
            self.card.pin(found, self)  # a click keeps the lookup up, as today

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """A double-click on a word selects it whole, as in a caption window
        (395); its first click already looked it up. Qt's own handler sends
        the press again, and its release pinned the word a second time - two
        lookups, and the second one turns a word assumed known new
        (polyglotic-hq 397, 400). Anywhere else: a press, as before."""
        word = None
        if event.button() == Qt.MouseButton.LeftButton:
            word = self._marked_at(event.position())
        if word is None:
            self.mousePressEvent(event)
            return
        self._press, self._dragging = None, False
        self.anchor = (word.key, word.row, word.start)
        self.head = (word.key, word.row, word.end)
        self.update()

    def _drag_to(self, pos: QPointF) -> None:
        """The selection's end follows the mouse; above or below the list,
        it scrolls a step."""
        if pos.y() < PAD:
            self.scroll_by(WHEEL_STEP * self._scale())
        elif pos.y() > self.height() - PAD:
            self.scroll_by(-WHEEL_STEP * self._scale())
        spot = self.spot_at(pos)
        if spot is not None and self.anchor is not None:
            self.head = spot
            self.update()

    # -- selecting and copying (343) ------------------------------------------------------

    def spot_at(self, pos: QPointF) -> Spot | None:
        """The place in the text drawn nearest `pos`: on the nearest line
        of text (by height, then by width), between the characters the
        mouse is between."""
        best: tuple[tuple[float, float], Spot] | None = None
        for line, laid, at in self.drawn:
            for row in laid.rows:
                origin = QPointF(at.x(), at.y() + row.top)
                for i in range(row.layout.lineCount()):
                    text_line = row.layout.lineAt(i)
                    rect = text_line.naturalTextRect().translated(origin)
                    down = max(rect.top() - pos.y(), 0.0, pos.y() - rect.bottom())
                    across = max(rect.left() - pos.x(), 0.0, pos.x() - rect.right())
                    if best is None or (down, across) < best[0]:
                        index = text_line.xToCursor(pos.x() - origin.x())
                        best = ((down, across), (line.key, row.index, index))
        return best[1] if best is not None else None

    def hasSelectedText(self) -> bool:
        return bool(self.selectedText())

    def selectedText(self) -> str:
        """What's selected: what was said and translations as they show,
        each row on a line of its own, in order."""
        if self.anchor is None or self.head is None:
            return ""
        return selected_text(self.transcript.lines, self.anchor, self.head)

    def copy_selection(self) -> None:
        """What's selected to the clipboard - nowhere else."""
        text = self.selectedText()
        if text:
            QGuiApplication.clipboard().setText(text)

    def copy_by_key(self) -> bool:
        """Ctrl+C (Cmd+C on macOS): copy selected text, or the hovered caption
        when nothing is selected (polyglotic-hq 950)."""
        if self.hasSelectedText():
            self.copy_selection()
            say_copied(None, self)
            return True
        if self.hovered_line is not None:
            self.copy_wanted.emit(self.hovered_line, "both")
            return True
        return False

    def _copy_chosen(self) -> None:
        """The selection menu's Copy: copied, and "Copied" by the mouse
        (Ctrl+C says nothing, as anywhere)."""
        if self.hasSelectedText():
            self.copy_selection()
            say_copied(QCursor.pos(), self)

    def sentence_selected(self) -> Selected | None:
        """What's selected, as a sentence to save (polyglotic-hq 459)."""
        if self.anchor is None or self.head is None:
            return None
        pieces = selected_pieces(self.transcript.lines, self.anchor, self.head)
        return selected_sentence(pieces, self._speaker)

    def _speaker(self, line: Line) -> str:
        if line.by_you:
            return self.you.name
        window = self.window()
        label = getattr(window, "label", None)
        return label.name if isinstance(label, SourceLabel) else ""

    def _add_save_sentence(self, menu: QMenu) -> None:
        """The selection menu's "Save sentence to", a category each, when
        what's selected is more than a word (459): into the learning data
        of the language it was spoken in."""
        found = self.sentence_selected()
        if self.learner is None or found is None or not worth_saving(found):
            return
        vocabulary = self.learner.of(found.language).vocabulary
        into = menu.addMenu(save_to_text())
        for category in vocabulary.categories:

            def save(_: bool = False, chosen: Category = category) -> None:
                vocabulary.save_sentence(
                    found.parts,
                    found.original,
                    found.translation,
                    chosen.id,
                    found.translation_language,
                )
                said = saved_to_text(chosen.name)
                show_toast(said, self, QCursor.pos())

            into.addAction(category.name, save)

    def use_say_it(self, reading: SelectionReading | None) -> None:
        """The selection menu's Say it reads through `reading`; the word it
        says lights here (polyglotic-hq 495)."""
        if self.say_it is not None:
            self.say_it.lit.disconnect(self._said_now)
        self.say_it = reading
        if reading is not None:
            reading.lit.connect(self._said_now)

    def _said_now(self, owner: object, words: dict[int, list[Words]]) -> None:
        if owner is self and words != self.said_now:
            self.said_now = words
            self.update()

    def _add_say_it(self, menu: QMenu) -> None:
        """The selection menu's "Say it": a language each - what was said,
        its translation - or Stop while one is read (495)."""
        reading = self.say_it
        if reading is None or self.anchor is None or self.head is None:
            return
        pieces = selected_pieces(self.transcript.lines, self.anchor, self.head)
        sides = sides_aloud(pieces)
        if not sides:
            return
        into = menu.addMenu(say_it_text())
        for side in reading.ordered(sides):
            state = reading.state(self, side)

            def say(_: bool = False, chosen: SideAloud = side) -> None:
                reading.toggle(self, chosen)
                language = reading.notice_for(self)
                if language is not None:
                    self.better_voice(reading, language)

            action = into.addAction(side_text(state, side.language), say)
            if state is Say.NO_VOICE:
                action.setToolTip(no_voice_steps(side.language, reading.system_voice()))
        into.setToolTipsVisible(True)

    def better_voice(self, reading: SelectionReading, language: str) -> QMessageBox:
        """Read in a basic voice (polyglotic-hq 518): how to add a better
        one, "Don't show again" for the language and Dismiss - a box over
        the transcript, which has the keyboard already (no caption window's
        to keep)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(say_it_text())
        box.setText(better_voice_steps(language))
        box.setCheckBox(QCheckBox(never_again_text(language), box))
        box.addButton(dismiss_text(), QMessageBox.ButtonRole.AcceptRole)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def done(_result: int) -> None:
            ticked = box.checkBox().isChecked()
            if reading.notice_for(self) is not None:
                reading.dismiss(ticked)

        box.finished.connect(done)
        box.open()
        return box

    def select_all(self) -> None:
        """Every line listed (a search's matches while searching)."""
        lines = self.transcript.lines
        if not lines:
            return
        last = lines[-1]
        end = len(last.rows[-1].text) if last.rows else 0
        self.anchor = (lines[0].key, 0, 0)
        self.head = (last.key, max(0, len(last.rows) - 1), end)
        self.update()

    # -- the lookup ---------------------------------------------------------------------

    def _marked_at(self, pos: QPointF) -> Marked | None:
        """The word under `pos`, by the word split - None for none, or with
        no lookup to show it in."""
        learner = self.learner
        if learner is None or self.card is None:
            return None
        for line, laid, at in self.drawn:
            rows = [(row, QPointF(at.x(), at.y() + row.top)) for row in laid.rows]
            found = char_under(rows, pos)
            if found is None:
                continue
            row, _, index = found
            text = row.row.text
            span = (
                learner.word_at(text, index, row.row.language)
                if 0 <= index < len(text)
                else None
            )
            if span is None or span[0] >= span[1]:
                return None
            return Marked(line.key, row.index, *span)
        return None

    def _hover(self, word: Marked | None) -> None:
        """The word under the mouse, highlighted and looked up after the
        card's hover delay - or nothing."""
        if word != self.hovered:
            self.hovered = word
            self.update()
        card = self.card
        if card is None:
            return
        if word is None:
            card.unhover()
            return
        if card.showing((word.key, word.row, word.start, word.end)):
            card.hover_kept()
            return
        if card.pinned:
            return
        found = self.word_at(word)
        if found is not None:
            card.hover(found)

    def word_at(self, marked: Marked) -> WordAt | None:
        """What the lookup needs for `marked`: the word, its context (its
        clause's row and translation) and where it is on the screen."""
        for line, laid, at in self.drawn:
            if line.key != marked.key:
                continue
            row = next((r for r in laid.rows if r.index == marked.row), None)
            if row is None:
                return None
            origin = QPointF(at.x(), at.y() + row.top)
            text = row.row.text
            caption = self.transcript.captions.caption(line.key)
            context = (
                lookup_context(text, clause_versions(caption, row.row.clause))
                if caption is not None and row.row.clause < len(caption.clauses)
                else LookupContext(text)
            )
            context = with_counterpart(
                context, caption, line.rows, row.index, (marked.start, marked.end)
            )
            rects = [
                r.translated(origin)
                for r in span_rects(row.layout, marked.start, marked.end)
            ]
            if not rects:
                return None
            box = rects[0]
            for rect in rects[1:]:
                box = box.united(rect)
            reading = QRectF(0, box.top(), self.width(), box.height())
            screen = self.screen()
            area = (
                _rect(screen.availableGeometry())
                if screen is not None
                else Rect(0, 0, 1920, 1040)
            )
            return WordAt(
                text[marked.start : marked.end],
                context,
                (marked.start, marked.end),
                self._on_screen(box),
                self._on_screen(reading),
                area,
                (marked.key, marked.row, marked.start, marked.end),
                row.row.language,
                self.transcript.captions.fallbacks,
            )
        return None

    def _on_screen(self, rect: QRectF) -> Rect:
        top_left = self.mapToGlobal(rect.topLeft().toPoint())
        return Rect(
            top_left.x(), top_left.y(), round(rect.width()), round(rect.height())
        )

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.menu_at(event.pos().y())
        if menu is not None:
            menu.exec(event.globalPos())

    def menu_at(self, y: float) -> QMenu | None:
        """The right-click menu: with text selected, Copy (it) and Select
        all (343); else the line's at `y` (`line_menu`), if there's one."""
        if self.hasSelectedText():
            menu = selection_menu(self, self._copy_chosen, self.select_all)
            self._add_save_sentence(menu)
            self._add_say_it(menu)
            return menu
        line = self.line_at(y)
        return self.line_menu(line) if line is not None else None

    def line_menu(self, line: Line) -> QMenu:
        """A line's right-click menu: Copy, Copy what was said and Copy the
        translation (with one shown)."""
        menu = QMenu(self)
        menu.addAction(_tr("Copy"), lambda: self.copy_wanted.emit(line.key, "both"))
        menu.addAction(
            _tr("Copy what was said"),
            lambda: self.copy_wanted.emit(line.key, "said"),
        )
        if any(row.kind is RowKind.TRANSLATION for row in line.rows):
            menu.addAction(
                _tr("Copy the translation"),
                lambda: self.copy_wanted.emit(line.key, "translation"),
            )
        return menu


# -- the settings rail -------------------------------------------------------------------


class SettingsRail(QScrollArea):
    """The transcript's settings: the session's panels - Languages (with
    "This window"), Timing and Look - one under another."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transcript_window.rail")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        column_widget = QWidget()
        column_widget.setObjectName("transcript_window.rail_column")
        self.column = QVBoxLayout(column_widget)
        self.column.setContentsMargins(12, 12, 12, 12)
        self.column.setSpacing(12)
        self.column.addStretch(1)
        self.setWidget(column_widget)
        self.panels: list[QWidget] = []
        wheel.guard(self)  # the wheel scrolls the rail, never a setting (304)

    def add_panel(self, panel: QWidget) -> None:
        """A panel under the others (each its own card)."""
        self.column.insertWidget(len(self.panels), panel)
        self.panels.append(panel)


class _AppTag(QWidget):
    """The app's colour dot and label, and the mic mark while its caption
    window shows my speech."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.label = SourceLabel("", YOU)
        self.mic = False
        self.color = "#e9ecf1"
        self._font = QFont()
        self._font.setFamilies(style.UI_FAMILIES)
        self._font.setPixelSize(style.px(13))
        self._font.setWeight(QFont.Weight.DemiBold)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(style.px(48))

    def restyle(self) -> None:
        """At the text size now."""
        self._font.setPixelSize(style.px(13))
        self.setMinimumWidth(style.px(48))
        self.updateGeometry()

    def show_label(self, label: SourceLabel, mic: bool, color: str) -> None:
        self.label, self.mic, self.color = label, mic, color
        self.setToolTip(
            _tr("{app} - shows my speech").format(app=label.name) if mic else label.name
        )
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        width = 16 + QFontMetrics(self._font).horizontalAdvance(self.label.name[:28])
        return QSize(width + (20 if self.mic else 0) + 4, style.px(26))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.label.color))
        painter.drawEllipse(QRectF(2, self.height() / 2 - 4.5, 9, 9))
        painter.setPen(QColor(self.color))
        painter.setFont(self._font)
        metrics = QFontMetrics(self._font)
        room = self.width() - 16 - (20 if self.mic else 0)
        name = metrics.elidedText(self.label.name, Qt.TextElideMode.ElideRight, room)
        painter.drawText(
            QRectF(16, 0, room, self.height()), Qt.AlignmentFlag.AlignVCenter, name
        )
        if self.mic:  # a small microphone: the window shows my speech
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(YOU))
            x = 16 + metrics.horizontalAdvance(name) + 8
            mid = self.height() / 2
            painter.drawRoundedRect(QRectF(x, mid - 7, 6, 9), 3, 3)
            painter.drawRect(QRectF(x + 2.5, mid + 3, 1, 3))
            painter.drawRect(QRectF(x - 1, mid + 6, 8, 1))
        painter.end()


# -- the window -----------------------------------------------------------------------


class TranscriptWindow(QWidget):
    """One app's transcript window. `choices` are what it remembers (text
    size, rail); its caption window's choices and the session's are shown
    by `follow`, and asked for through its signals."""

    changed = Signal()
    """Its choices changed (text size, rail open)."""
    language_wanted = Signal(str)
    """Its caption window's language (ORIGINAL_ONLY: none), from the strip."""
    timing_wanted = Signal(str)

    def __init__(
        self,
        key: str,
        transcript: Transcript,
        label: SourceLabel,
        choices: TranscriptChoices,
        theme: style.Theme | None = None,
        learner: Learner | None = None,
        you: SourceLabel | None = None,
        card: LookupCard | None = None,
        panels: Sequence[Callable[[], QWidget]] = (),
        save_folder: SaveFolder | None = None,
    ) -> None:
        """`theme`: the window theme (default: the new interface's now);
        `card`: the lookup card the caption windows share (none: no lookup);
        `panels`: what makes each of the session's panels for its rail -
        made one per turn of the event loop once the window shows
        (`_prepare_rail`), or all at once if the rail opens first;
        `save_folder`: where Save transcript as... opens (none: Documents,
        this window's last save remembered while it's open)."""
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("transcript_window")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.key = key
        self.transcript = transcript
        self.label = label
        self.choices = choices
        self.theme = theme or style.current()
        self.colors = TranscriptColors.of(self.theme)
        self._makers = list(panels)
        self._preparing = False
        self._predrawn = 0  # steps of drawing the rail unseen done (of 2)
        self.translate_into = (
            str(transcript.target) if transcript.target else ORIGINAL_ONLY
        )
        self.save_folder = save_folder or SaveFolder()
        self.timing = CaptionMode.WHOLE
        self.notice_shown: Notice | None = None
        self.animate = True  # the rail slides (off in the lab and tests)
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(RAIL_SLIDE_MS)
        self._slide.valueChanged.connect(self._rail_width)
        self._slide.finished.connect(self._slid)
        self._area: Rect | None = None  # the work area it opened on (`keep_to`)
        self._keep_minimum()
        self.setWindowTitle(_tr("{app} - Transcript").format(app=label.name))

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_strip())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.list = TranscriptList(transcript, self.colors, learner, you, self)
        self.list.card = card
        self.list.copy_wanted.connect(self._copy_line)
        self.list.text_step.connect(self.step_text)
        self.list.scrolled.connect(self.refresh)
        body.addWidget(self.list, 1)
        self.rail = SettingsRail(self)
        self.rail.setFixedWidth(0)
        self.rail.hide()
        body.addWidget(self.rail)
        self.body = body
        column.addLayout(body, 1)
        self.foot = QLabel(self)
        self.foot.setObjectName("transcript_window.foot")
        self.foot.setProperty("foot", True)
        self.foot.setWordWrap(True)  # narrow, the longest foot takes two lines
        self.foot.setContentsMargins(PAD, 4, PAD, 6)
        column.addWidget(self.foot)

        self.pill = QPushButton(self.list)
        self.pill.setObjectName("transcript_window.back_to_live")
        self.pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pill.clicked.connect(self.go_live)
        self.pill.setToolTip(live_tip(""))
        self.pill.hide()
        self.notice = QLabel(self.list)
        self.notice.setObjectName("transcript_window.notice")
        self.notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.notice.hide()

        self.popover_open = False
        """The rail floats over the list's right (narrower than 700 px)."""

        search = QShortcut(QKeySequence.StandardKey.Find, self)
        search.activated.connect(self.search.setFocus)
        self.setStyleSheet(stylesheet(self.theme))
        self.resize(720, 520)
        self.show_label(label, False)
        self._sync_strip()
        self.refresh()

    # -- the app strip --------------------------------------------------------------

    def _tool(
        self, name: str, text: str, tip: str = "", chip: bool = False
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(f"transcript_window.{name}")
        button.setText(text)
        button.setToolTip(tip or text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("chip", chip)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.buttons[name] = button
        return button

    def _build_strip(self) -> QWidget:
        strip = QWidget(self)
        strip.setObjectName("transcript_window.strip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(6)
        self.buttons: dict[str, QToolButton] = {}
        self._copied_shown = QTimer(self)  # Copy all's "✓ Copied", a moment
        self._copied_shown.setSingleShot(True)
        self._copied_shown.timeout.connect(self._copied_done)
        self.tag = _AppTag(strip)
        row.addWidget(self.tag)
        language = self._tool("language", "", chip=True)
        language.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        language_menu = QMenu(language)
        group = QActionGroup(language_menu)
        self.language_actions: dict[str, QAction] = {}
        for code, name in [
            (ORIGINAL_ONLY, _tr("Original only (no translation)")),
            *((str(c), language_name(str(c))) for c in target_languages()),
        ]:
            action = language_menu.addAction(name)
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(
                lambda _=False, c=code: self.language_wanted.emit(c)
            )
            self.language_actions[code] = action
        language.setMenu(language_menu)
        row.addWidget(language)
        timing = self._tool(
            "timing", "", _tr("Caption timing - for every window"), True
        )
        timing.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        timing_menu = QMenu(timing)
        group = QActionGroup(timing_menu)
        self.timing_actions: dict[CaptionMode, QAction] = {}
        for mode in (*OFFERED_MODES, CaptionMode.SCROLLING):
            action = timing_menu.addAction(timing_name(mode))
            action.setToolTip(timing_tip(mode))  # what it does (F22, 249)
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(
                lambda _=False, m=mode: self.timing_wanted.emit(m.value)
            )
            action.setVisible(mode is not CaptionMode.SCROLLING)
            self.timing_actions[mode] = action
        timing_menu.setToolTipsVisible(True)
        timing.setMenu(timing_menu)
        row.addWidget(timing)
        smaller = self._tool(
            "smaller", "A-", hotkeys_here(_tr("Smaller text (Ctrl+wheel)"))
        )
        smaller.clicked.connect(lambda: self.step_text(-1))
        row.addWidget(smaller)
        bigger = self._tool(
            "bigger", "A+", hotkeys_here(_tr("Bigger text (Ctrl+wheel)"))
        )
        bigger.clicked.connect(lambda: self.step_text(1))
        row.addWidget(bigger)
        self.search = QLineEdit(strip)
        self.search.setObjectName("transcript_window.search")
        self.search.setPlaceholderText(_tr("Search the transcript"))
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName(_tr("Search the transcript"))
        clear = self.search.findChild(QToolButton)
        if clear is not None:  # the field's own x: named, and reached by Tab
            clear.setAccessibleName(_tr("Clear the search"))
            clear.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.search.setMinimumWidth(90)
        self.search.textChanged.connect(self.set_search)
        row.addWidget(self.search, 1)
        copy = self._tool("copy", _tr("Copy all"))
        copy.clicked.connect(self._copy_all_clicked)
        row.addWidget(copy)
        save = self._tool(
            "save",
            _tr("Save transcript as…"),
            _tr("Save the finished captions as text, subtitles (SRT) or CSV"),
        )
        save.clicked.connect(self.save_as)
        row.addWidget(save)
        more = self._tool("more", "…", _tr("Copy all, Save transcript as…"))
        more.setAccessibleName(_tr("More: Copy all, Save transcript as…"))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more)
        more_menu.addAction(_tr("Copy all"), self._copy_all_chosen)
        more_menu.addAction(_tr("Save transcript as…"), self.save_as)
        more.setMenu(more_menu)
        more.hide()
        row.addWidget(more)
        settings = self._tool("settings", "⚙ " + _tr("Settings"), _tr("Settings"))
        settings.setAccessibleName(_tr("Settings"))
        settings.setCheckable(True)
        settings.clicked.connect(self.toggle_rail)
        row.addWidget(settings)
        return strip

    def _sync_strip(self) -> None:
        """The strip shows the caption window's language and the timing."""
        code = self.translate_into
        chip = self.buttons["language"]
        chip.setText(f"{code.upper() if code else _tr('Original only')} ▾")
        chip.setToolTip(
            in_sentence(_tr("Translate into: {language}"), language=language_name(code))
            if code
            else _tr("Original only - no translation")
        )
        action = self.language_actions.get(code)
        if action is not None:
            action.setChecked(True)
        self.buttons["timing"].setText(f"{timing_name(self.timing)} ▾")
        self.timing_actions[self.timing].setChecked(True)
        self.buttons["settings"].setChecked(self._rail_showing())

    def _fold(self) -> None:
        """Copy all and Save as… on the strip, or folded into "…" - and
        Settings its gear alone."""
        narrow = self.width() < style.px(FOLD_BELOW)
        if narrow == self.buttons["more"].isVisible():
            return
        self.buttons["copy"].setVisible(not narrow)
        self.buttons["save"].setVisible(not narrow)
        self.buttons["more"].setVisible(narrow)
        self.buttons["settings"].setText("⚙" if narrow else "⚙ " + _tr("Settings"))

    # -- what it shows ----------------------------------------------------------------

    def show_label(self, label: SourceLabel, show_mic: bool) -> None:
        """The app's label (name and colour), and whether its caption
        window shows my speech."""
        if label != self.label:
            self.label = label
            self.setWindowTitle(_tr("{app} - Transcript").format(app=label.name))
        self.tag.show_label(label, show_mic, self.colors.text)

    def follow(
        self,
        label: SourceLabel,
        translate_into: str,
        show_mic: bool,
        timing: CaptionMode,
        you: SourceLabel,
        *,
        video: bool = False,
    ) -> None:
        """Its caption window's choices and the session's, as they are now."""
        self.show_label(label, show_mic)
        self.translate_into = translate_into
        self.timing = timing
        choices = offered(Use.WATCHING).timings if video else OFFERED_MODES
        for mode, action in self.timing_actions.items():
            action.setVisible(mode in choices)
            action.setToolTip(timing_tip(mode, video=video))
        if you != self.list.you:
            self.list.you = you
            self.list.update()
        self._sync_strip()
        self.refresh()

    def set_notice(self, notice: Notice | None) -> None:
        """The session's state over the list's top (Paused, Reconnecting, ...)."""
        self.notice_shown = notice
        if notice is None:
            self.notice.hide()
        else:
            self.notice.setText(notice_text(notice, None))
            self.notice.adjustSize()
            self.notice.show()
        self._place_overlays()

    def set_theme(self, theme: style.Theme) -> None:
        """The window theme changed: dressed and painted in it."""
        if theme == self.theme:
            return
        self.theme, self.colors = theme, TranscriptColors.of(theme)
        self.setStyleSheet(stylesheet(theme))
        self.list.set_colors(self.colors)
        self.tag.show_label(self.label, self.tag.mic, self.colors.text)

    def restyle(self) -> None:
        """At the text size now (Windows' changed while it ran): dressed
        again, its minimum and the rail at it, the strip folded to fit."""
        self.setStyleSheet(stylesheet(self.theme))
        self._keep_minimum()
        self.tag.restyle()
        if self.rail.width() > 0:
            self.rail.setFixedWidth(style.px(RAIL_WIDTH))
        self.notice.adjustSize()  # measured again, at the text size now
        self.pill.adjustSize()  # (placed by the resize)
        self.resizeEvent(QResizeEvent(self.size(), self.size()))
        self.list.update()

    def refresh(self) -> None:
        """After the transcript changed: the foot, Back to live, a repaint."""
        foot = self.transcript.foot()
        if foot.searching:
            text = _trn("%Ln match(es)", foot.count)
            if foot.earlier:  # the list's lines are searched, not the earlier
                text += " " + _trn("in the newest %Ln line(s)", foot.listed)
        elif not foot.count:
            text = ""  # the list says "Nothing yet - ..."
        elif foot.earlier:  # more kept than listed: say where they are (137)
            text = _tr(
                "the newest {n} of {total} lines · all in Copy all and Save"
            ).format(
                n=QLocale().toString(foot.count),
                total=QLocale().toString(foot.count + foot.earlier),
            )
        else:
            text = _trn("%Ln line(s)", foot.count)
        if foot.count:
            text += " · " + (
                _tr("following") if foot.following else _tr("scrolled back")
            )
        if foot.count and not foot.searching:  # this session only (228)
            text += " · " + _tr("gone when you quit, unless you save it")
        if text != self.foot.text():
            self.foot.setText(text)
        if foot.following:
            self.pill.hide()
        else:
            self.pill.setText(
                _tr("Back to live · {n} new").format(n=foot.new)
                if foot.new
                else _tr("Back to live")
            )
            self.pill.adjustSize()
            self.pill.show()
        self._place_overlays()
        self.list.changed()

    def _place_overlays(self) -> None:
        width = self.list.width() - self.list.bar.width()
        if self.pill.isVisible():
            self.pill.move(
                (width - self.pill.width()) // 2,
                self.list.height() - self.pill.height() - 10,
            )
        if self.notice.isVisible():
            self.notice.move((width - self.notice.width()) // 2, 6)

    # -- the learner's choices ----------------------------------------------------------

    def set_search(self, query: str) -> None:
        with spans.span("transcript.search"):
            self.transcript.search(query)
            self.refresh()

    def set_text_size(self, size: float) -> None:
        """This transcript's own text size: live, the window keeps its size."""
        with spans.span("transcript.text_size"):
            self.transcript.set_text_size(size)
            if self.transcript.text_size == self.choices.text_size:
                return
            self.choices = replace(self.choices, text_size=self.transcript.text_size)
            self.refresh()
        self.changed.emit()

    def step_text(self, steps: int) -> None:
        self.set_text_size(stepped(self.transcript.text_size, steps))

    def go_live(self) -> None:
        self.transcript.go_live()
        self.refresh()

    def set_live_keys(self, keys: str) -> None:
        """Back to live's hotkey as the OS writes it ("" none), on its tip
        (polyglotic-hq 567)."""
        self.pill.setToolTip(live_tip(keys))

    # -- the rail -------------------------------------------------------------------------

    def _rail_showing(self) -> bool:
        return self.popover_open or (
            rail_inline(self.width(), style.text_scale()) and self.choices.rail_open
        )

    def toggle_rail(self) -> None:
        """Settings: the rail slides in or out - or, narrower than 700 px,
        opens as a popover over the list."""
        with spans.span("transcript.rail"):
            if rail_inline(self.width(), style.text_scale()):
                self.choices = replace(
                    self.choices, rail_open=not self.choices.rail_open
                )
                self._show_rail(self.choices.rail_open, self.animate)
                self.changed.emit()
            elif self.popover_open:
                self.close_popover()
            else:
                self._open_popover()
            self._sync_strip()

    def _show_rail(self, shown: bool, animate: bool) -> None:
        """The rail beside the list, or not; sliding, if `animate`."""
        if self.popover_open:
            self.close_popover()
        if shown:
            self._fill_rail()
        self._slide.stop()
        target = style.px(RAIL_WIDTH) if shown else 0
        if shown:
            self.rail.show()
        if not animate:
            self._rail_width(target)
            self._slid()
            return
        self._slide.setStartValue(self.rail.width() if self.rail.isVisible() else 0)
        self._slide.setEndValue(target)
        self._slide.start()

    def _fill_rail(self) -> None:
        """Every panel not made yet, now: the rail is opening."""
        while self._makers:
            self._make_panel()

    def _make_panel(self) -> None:
        with spans.span("transcript.rail_panel"):
            panel = self._makers.pop(0)()
            self.rail.add_panel(panel)
            panel.ensurePolished()  # dressed now, not when the rail opens

    def _prepare_rail(self) -> None:
        """One step of making the rail ready, then the next on the next turn
        of the event loop: each panel made, the rail laid out at the size it
        opens at, then its first screenful drawn once out of sight. No one
        slot does it all (a fresh process's first Look panel reads the
        system's fonts), and the first click on Settings only shows it."""
        self._preparing = False
        if self._makers:
            self._make_panel()
        elif self._predrawn < 2:
            self._predraw_rail()
        else:
            return
        if self._makers or self._predrawn < 2:
            self._preparing = True
            QTimer.singleShot(0, self, self._prepare_rail)

    def _predraw_rail(self) -> None:
        """The rail sized as it will open and laid out (the first call), then
        its first screenful drawn once, unseen (the second): its words
        wrapped at the width they'll show at, its glyphs ready. A hidden
        rail takes no room beside the list, whatever its width."""
        if not self.rail.panels or self.rail.isVisible():
            self._predrawn = 2
            return
        column = self.rail.widget()
        if column is None:
            self._predrawn = 2
            return
        if self._predrawn == 0:
            with spans.span("transcript.rail_layout"):
                self.rail.ensurePolished()
                self.rail.setFixedWidth(style.px(RAIL_WIDTH))
                self.rail.resize(style.px(RAIL_WIDTH), max(1, self.list.height()))
                QApplication.sendEvent(
                    self.rail, QResizeEvent(self.rail.size(), QSize())
                )  # the scroll area places its viewport and column now
                layout = column.layout()
                if layout is not None:
                    layout.activate()
        else:
            with spans.span("transcript.rail_predraw"):
                shown = min(column.height(), max(1, self.list.height()))
                column.grab(QRect(0, 0, column.width(), shown))
        self._predrawn += 1

    def _rail_width(self, width: object) -> None:
        self.rail.setFixedWidth(int(width))  # type: ignore[call-overload]

    def _slid(self) -> None:
        if self.rail.width() == 0:
            self.rail.hide()

    def _open_popover(self) -> None:
        """The rail over the list's right, under the strip: the same widget,
        taken out of the row beside the list - never given another parent,
        which would dress its panels afresh."""
        self._slide.stop()
        self._fill_rail()
        self.body.removeWidget(self.rail)
        self.rail.setFixedWidth(style.px(RAIL_WIDTH))
        self.popover_open = True
        self._place_popover()
        self.rail.show()
        self.rail.raise_()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)  # a press elsewhere closes it

    def _place_popover(self) -> None:
        column = self.rail.widget()
        wanted = column.sizeHint().height() if column is not None else 0
        height = min(self.list.height(), max(200, wanted))
        width = style.px(RAIL_WIDTH)
        self.rail.setGeometry(self.width() - width, self.list.y(), width, height)

    def close_popover(self) -> None:
        """The popover closed; the rail back beside the list, hidden."""
        if not self.popover_open:
            return
        self.popover_open = False
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.rail.hide()
        self.rail.setFixedWidth(0)
        self.body.addWidget(self.rail)
        self._sync_strip()

    def _in_rail(self, widget: QObject) -> bool:
        """`widget` is the rail or inside it - a list one of its choices
        drops down included."""
        found: QObject | None = widget
        while found is not None:
            if found is self.rail:
                return True
            found = found.parent()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            self.popover_open
            and event.type() == QEvent.Type.MouseButtonPress
            and not self._in_rail(watched)
            and watched is not self.buttons["settings"]
        ):
            self.close_popover()
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.popover_open:
            self.close_popover()
            return
        if (
            event.key() == Qt.Key.Key_Escape
            and self.search.hasFocus()
            and self.search.text()
        ):  # Esc in the search clears it: every line again (polyglotic-hq 133)
            self.search.clear()
            return
        if (
            event.matches(QKeySequence.StandardKey.Copy)
            and not event.isAutoRepeat()
            and not isinstance(QApplication.focusWidget(), TYPING)
            and self.list.copy_by_key()
        ):
            event.accept()
            return
        super().keyPressEvent(event)

    # -- copy and save -------------------------------------------------------------------

    def _export(self, captions: list[Caption], kind: str) -> str:
        languages = self.transcript.languages()
        seconds = self.transcript.seconds()
        names = {str(code): shown_name(str(code)) for code in languages}
        you = self.list.you.name
        if kind == "srt":
            return as_srt(captions, languages, self.transcript.started_at, seconds)
        # the times the list shows: this PC's (the exports' own default is
        # UTC, as stored)
        zone = self.list.zone or datetime.now().astimezone().tzinfo
        if kind == "csv":
            # its "source" column names the app - or "You" - on every row: it
            # was always empty, so two apps' saved files couldn't be told
            # apart (polyglotic-hq 184, 203; 062's #86 put it there)
            sources = {
                caption.source_id: you if caption.by_you else self.label.name
                for caption in captions
            }
            return as_csv(captions, languages, zone, sources, seconds)
        return as_text(
            captions,
            languages,
            names,
            you,
            zone,
            seconds=seconds,
            respoken=_tr("re-spoken"),
        )

    def text(self) -> str:
        """What Copy all copies: the whole session's lines (or, searching,
        the matches shown), as text."""
        return self._export(self.transcript.captions_kept(), "text")

    def copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self.text())

    def _copy_all_clicked(self) -> None:
        """Copy all on the strip: copied, and the button says "✓ Copied" for
        a moment, as the lookup card's Copy does (polyglotic-hq 333, 360) -
        never narrower meanwhile, so the strip doesn't shift under the mouse."""
        self.copy_all()
        button = self.buttons["copy"]
        button.setMinimumWidth(button.sizeHint().width())
        button.setText(f"✓ {copied()}")
        self._copied_shown.start(COPIED_MS)

    def _copy_all_chosen(self) -> None:
        """Copy all in "…": copied, and "Copied" by the mouse (the menu has
        closed)."""
        self.copy_all()
        say_copied(QCursor.pos(), self)

    def _copied_done(self) -> None:
        button = self.buttons["copy"]
        button.setText(_tr("Copy all"))
        button.setMinimumWidth(0)

    def _copy_line(self, key: int, part: str = "both") -> None:
        """A line's right-click Copy: as Copy all writes it ("both"), what
        was said alone ("said") or its translation alone ("translation")."""
        line = next((ln for ln in self.transcript.lines if ln.key == key), None)
        if line is None:
            return
        captions = self.transcript.captions.captions_of([line])
        if part == "said":
            text = "\n".join(caption.original for caption in captions)
        elif part == "translation":
            languages = self.transcript.languages()
            seconds = self.transcript.seconds()
            text = "\n".join(translation_text(c, languages, seconds) for c in captions)
        else:
            text = self._export(captions, "text")
        if text:
            QGuiApplication.clipboard().setText(text)
            say_copied(QCursor.pos(), self)

    def save_as(self) -> bool:
        """Save transcript as...: Windows' save dialog, opening in the folder
        saved to last or Documents - never the install folder an update
        replaces (polyglotic-hq 244) - and the transcript written where it
        says, or a message saying why it couldn't be. True if it was saved
        (Quit's question goes on then: polyglotic-hq 334)."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            _tr("Save transcript"),
            self.save_folder.start("transcript.txt"),
            _tr("Text (*.txt);;Subtitles (*.srt);;Spreadsheet (*.csv)"),
        )
        if not path:
            return False
        try:
            self.save_to(Path(path))
        except OSError as problem:
            log.warning("Transcript not saved: %s", type(problem).__name__)
            QMessageBox.warning(
                self, _tr("Save transcript"), not_saved(Path(path).name)
            )
            return False
        self.save_folder.saved(Path(path))
        return True

    def save_to(self, path: Path) -> None:
        """The transcript - the whole session's, or as searched - saved to
        `path`: text, SRT or CSV by its extension."""
        suffix = path.suffix.lower()
        kind = {".srt": "srt", ".csv": "csv"}.get(suffix, "text")
        content = self._export(self.transcript.captions_kept(), kind)
        # CSV with a byte-order mark, so Excel reads it as UTF-8
        encoding = "utf-8-sig" if kind == "csv" else "utf-8"
        path.write_text(content, encoding=encoding, newline="")
        self.transcript.mark_saved()  # Quit needn't ask (334)

    # -- events ---------------------------------------------------------------------------

    def keep_to(self, area: Rect) -> None:
        """On the work area `area`: its minimum kept to it (`_keep_minimum`)."""
        self._area = area
        self._keep_minimum()

    def _keep_minimum(self) -> None:
        """Its minimum at the text size now (MIN_SIZE times it), but never
        more than MOST_OF_AREA of its work area: at a large text size on a
        small screen the minimum was taller than the screen, and the window
        opened at it - arrows on every edge, none moving (polyglotic-hq
        586, as the main window's)."""
        width, height = style.px(MIN_SIZE.width), style.px(MIN_SIZE.height)
        if self._area is not None:
            width = min(width, round(self._area.width * MOST_OF_AREA))
            height = min(height, round(self._area.height * MOST_OF_AREA))
        self.setMinimumSize(width, height)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self.isVisible() and not self.isMaximized() and not self.isMinimized():
            size = (self.width(), self.height())
            if size != self.choices.size:  # opened at it next time (586)
                self.choices = replace(self.choices, size=size)
                self.changed.emit()
        self._fold()
        inline = rail_inline(self.width(), style.text_scale())
        if self.popover_open:
            if inline:
                self.close_popover()
            else:
                self._place_popover()
        if not inline and not self.popover_open and self.rail.isVisible():
            self._slide.stop()
            self._rail_width(0)
            self.rail.hide()
        elif inline and self.choices.rail_open and not self.rail.isVisible():
            self._show_rail(True, animate=False)
        self._sync_strip()
        self._place_overlays()

    def hideEvent(self, event: QHideEvent) -> None:
        self.close_popover()

    def showEvent(self, event: QShowEvent) -> None:
        if rail_inline(self.width(), style.text_scale()) and self.choices.rail_open:
            self._show_rail(True, animate=False)
        elif self._makers and not self._preparing:
            self._preparing = True
            QTimer.singleShot(0, self, self._prepare_rail)
        self.refresh()
