"""W1, the caption window: one app's captions over that app (polyglotic-hq
project 109's structure, section 2; the interaction specs 10.1-10.4).

A frameless, always-on-top, translucent window that never takes the
focus: a click on it leaves the app underneath active (a full-screen game
can minimise when it loses focus) - `Qt.WindowDoesNotAcceptFocus`, which
on Windows is `WS_EX_NOACTIVATE` on its native window (checked on a real
window, 2026-11-07), and shown without activating. Its parts:
- **the canvas** (`Canvas`): the captions, newest at the bottom, painted
  from the caption layout engine; the panel behind them; the listening
  mark; the empty text;
- **the hover strip**: 28 px over the top of the canvas, shown 80 ms after
  the mouse comes over an unlocked window and gone 300 ms after it leaves.
  It is drawn over the captions - nothing moves (108's bug 4) - and covers
  whole rows: a label or row it would cut isn't drawn (113). It holds
  the source's name, dot and mic mark, the language, preset and timing
  chips, re-speak when offered, a capped plan's usage ring beside the mic
  (`usage`, polyglotic-hq 684: it stays at every step), and the lock,
  report, settings and close icons. As space runs out the name elides and the chips shorten, then
  the name becomes a dot and the chips become icons (polyglotic-hq 635).
  The gear opens the same dropdowns for chips that have overflowed.
- **the first window's set-up** (`caption_set_up`, 465): the first
  caption window on a PC asks its three language choices in it, once,
  never blocking - its first caption closes it; as a joined window's
  column too, and joining or separating doesn't end it (554);
- **the settings popover** (`settings_popover`) beside the settings
  button: Translate into (or Original only), Show my speech here, the
  timing, Text size (A- / A+), All caption settings...,
  Copy all captions, Open transcript, Join
  windows, Stop captioning - no Position: it's moved by hand (the user's
  rehearsal feedback F8, 249). Every control is one named action (`controls`) the
  strip or the popover draws;
- **copying** (polyglotic-hq 333): the settings' Copy all captions (its
  Copy the newest caption went in polyglotic-hq 339), and a right-click on a caption copies that one - finished captions, as the
  transcript's Copy writes them (time, "You" on the learner's own, what
  was said, its translation), to the clipboard and nowhere else; the
  notice line says it was copied. The window never has the keyboard, so
  there's no key for it; and **selecting** (polyglotic-hq 358, decision
  0150; `caption_selection`): a drag from a word out of its clause and
  side selects across lines, clauses and captions, kept until a click
  elsewhere or Esc, copied by a right-click on it or Ctrl+C while one of
  the app's windows has the keyboard;
- **the notice line** over the top band (under the header if both show);
  **Back to live · N new** over the bottom band while scrolled back;
- **the lookup** (`lookup_card`, one card every window shares): the word
  under the mouse - by the word split - is drawn softly behind, with its
  word links (links "On hover"); resting on it shows its lookup; a press
  on it looks it up (pinned), and a drag from it within its clause and
  side selects a phrase (pinned, and held as a selection; one worth saving
  as a sentence gets the sentence card at the mouse instead of a lookup:
  `sentence_card`, 522, whose "Look it up" opens it, 533) - a press on a
  word never moves the window (109's
  10.3).

Every edge and corner resizes, anchored to the opposite one (centred
presets symmetric); a drag anywhere else moves it, snapping to the
presets; both are clamped to the work area, and every step lays out again
in the same frame (`views.placement`). Text size changes live and the
window keeps its size; Ctrl+wheel steps it too.

A window is a stack of captions the size the learner set (the Strip, a
window whose height followed the newest caption, went in polyglotic-hq
272: "The strip toggle feels bad, probably remove that").

**Nothing moves under the mouse** (109's rule): while the mouse is on a
caption's words in an unlocked window, the view holds - so a click a
moment late still lands on the word that was under it (polyglotic-hq
145). Captions are never held for it (583, the user, 2026-11-21: "The
mouse shouldn't hold up delivery"): they come in past the view, Back to
live counts them, and the view goes live in one glide `VIEW_GRACE_SEC`
after the mouse comes off the words or leaves. Over the panel around the
text, the hover band or an edge nothing holds (polyglotic-hq 554).

After `fade_after` seconds of quiet it fades out, and comes back with the
next caption - or when the mouse rests on it (109's "fades to 0 except in
hover"). A faded window is invisible to the mouse too: Windows passes the
mouse through to what's underneath, so it hears nothing (polyglotic-hq
141). While it's faded and unlocked it looks where the mouse is instead,
every `POINT_POLL_MS`; resting on it for `POINT_REST` looks brings it back
(a mouse passing over doesn't). Locked, it stays click-through and faded.

In a joined window (`joined_window`, 109's 2a) the same window is a
column: a child widget of the joined window, with its own captions,
scroll-back, label, language, text size, my speech and strip (without
lock, which is the window's), while the place, the drags,
the notice line and the fade are the joined window's (`host`).

The window says what the learner did through its signals; `CaptionWindows`
saves its choices and passes on what concerns the session. Holds caption
text: never log it.
"""

import bisect
import logging
import math
import time
import unicodedata
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QEnterEvent,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QHideEvent,
    QMouseEvent,
    QPaintEngine,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QTextLayout,
    QTextLine,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.learning.lookups import LookupContext, lookup_context
from polyglotic_desktop.core.learning.saved_words import CategoryId
from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    ReadingColour,
    RowKind,
    WordLinks,
    clause_versions,
)
from polyglotic_desktop.core.listening.established import CORRECTION_SEC
from polyglotic_desktop.core.listening.playout import ReadingPath, each_character
from polyglotic_desktop.core.listening.selection import Place, Selection
from polyglotic_desktop.core.listening.sources import (
    DICTATION,
    MIC,
    WHOLE_SYSTEM,
    SourceId,
    SourceLabel,
)
from polyglotic_desktop.core.listening.timing import (
    MAX_WAIT_FOR_TEXT_SEC,
    OFFERED_MODES,
    CaptionId,
    CaptionMode,
)
from polyglotic_desktop.core.listening.transcript import as_text
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.core.shared.open_beta import UsageMeter
from polyglotic_desktop.perf import spans, trace
from polyglotic_desktop.ui_next import maintenance as maintenance_words
from polyglotic_desktop.ui_next import reading_lines, style
from polyglotic_desktop.ui_next.above_all import ABOVE_ALL, set_click_through
from polyglotic_desktop.ui_next.caption_delay import delay_text
from polyglotic_desktop.ui_next.caption_layout import (
    LINK_GAP_PX,
    LINK_PX,
    QUIET_SCALE,
    QUIET_TRANSLATION,
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
    LaidRow,
    char_under,
    dots_below,
    reserve_translation_space,
    row_room,
    row_text_width,
)
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks, Panel, link_colour
from polyglotic_desktop.ui_next.caption_selection import (
    HeldSelection,
    held_pieces,
    held_rects,
    held_words,
    place_at,
    shown,
    word_rects,
)
from polyglotic_desktop.ui_next.caption_set_up import CaptionSetUp
from polyglotic_desktop.ui_next.caption_surface import PAD, CaptionSurface
from polyglotic_desktop.ui_next.glyphs import Glyph, icon, paint, text_width
from polyglotic_desktop.ui_next.languages import (
    in_sentence,
    language_name,
    shown_name,
    spoken_name,
    spoken_names,
)
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.os_words import (
    hotkeys_here,
    on_a_mac,
    pc_mac_or_linux,
    pc_or_mac,
)
from polyglotic_desktop.ui_next.preset_popover import PresetPopover
from polyglotic_desktop.ui_next.preset_popover import chip_label as preset_chip_label
from polyglotic_desktop.ui_next.preset_popover import chip_name as preset_chip_name
from polyglotic_desktop.ui_next.resize_handle import CURSORS, GRIP, PanelResizeCursor
from polyglotic_desktop.ui_next.selection_reading import SAID_NOW, SelectionReading
from polyglotic_desktop.ui_next.sentence_card import SentenceCard
from polyglotic_desktop.ui_next.settings_popover import (
    COLUMN_ROWS,
    KEYBOARD_BAR_ROWS,
    LANGUAGE_ROWS,
    ROWS,
    KeyState,
    SettingsPopover,
)
from polyglotic_desktop.ui_next.spoken_nudge import SpokenNudge
from polyglotic_desktop.ui_next.strip_tips import StripTips
from polyglotic_desktop.ui_next.timing_popover import (
    TimingPopover,
    timing_name,
    timing_tip,
)
from polyglotic_desktop.ui_next.timing_popover import chip_label as timing_chip_label
from polyglotic_desktop.ui_next.timing_popover import chip_name as timing_chip_name
from polyglotic_desktop.ui_next.unlock_spot import UnlockSpot
from polyglotic_desktop.ui_next.usage import LOW_COLOUR, UsageRing
from polyglotic_desktop.ui_next.video import VIDEO_MARGIN, Video, subtitle_height
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.app_choices import AppChoice
from polyglotic_desktop.ui_next.views.arrivals import (
    ENTRY_GAP_PX,
    Motion,
    ease_out,
    effective,
    older_alphas,
    pace_of,
    slide_seconds,
)
from polyglotic_desktop.ui_next.views.caption_window import (
    TRANSLATION_SIZES,
    CaptionLook,
    Notice,
    Notices,
    TextEdge,
    WindowChoices,
    intro_seconds,
    shows,
    stepped,
    stepped_translation,
)
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_TEXT_SIZES,
    CAPTION_WINDOW_LINES,
    CaptionLines,
    Labels,
    Line,
    LineDisplay,
)
from polyglotic_desktop.ui_next.views.card_window_defaults import (
    CARD_BAR_PX,
    CARD_CLEAR_PX,
    CARD_READ_SEC,
    CARD_STEP_SEC,
    CARD_WAIT_SEC,
    OWN_SUBTITLE_ROOM,
    OWN_SUBTITLE_SIZE,
    TRANSLATION_WAIT_SEC,
    TRANSLATION_WIDTH_RATIO,
    VIEW_GRACE_SEC,
)
from polyglotic_desktop.ui_next.views.cards import (
    CARD,
    FLAT_ENOUGH,
    FLAT_SHARE,
    SMEAR,
    TO_SPARE,
    Deck,
    Glide,
    drum,
    drum_room,
)
from polyglotic_desktop.ui_next.views.dwell import (
    MEANT_PACE,
    MEANT_PACE_SPACED,
    OTHER_HOLDS,
    SAID_PACE,
    SAID_PACE_SPACED,
    Reading,
    need,
)
from polyglotic_desktop.ui_next.views.flow import FlowOptions, Open, flow_options
from polyglotic_desktop.ui_next.views.lab import (
    Fill,
    Join,
    Loading,
    Unfinished,
    by_place,
    changes_at,
    clause_gap,
    ink_between,
    newness,
)
from polyglotic_desktop.ui_next.views.lab import (
    older_translation as older_translation_ink,
)
from polyglotic_desktop.ui_next.views.lookup import Learner, WordAt, with_counterpart
from polyglotic_desktop.ui_next.views.pacing import Pacing
from polyglotic_desktop.ui_next.views.placement import Edge, Preset, Rect, Size
from polyglotic_desktop.ui_next.views.preset_menu import PresetMenu, Show
from polyglotic_desktop.ui_next.views.presets import contrast, readable_on
from polyglotic_desktop.ui_next.views.respeaking import MIC_METER_WIDTH
from polyglotic_desktop.ui_next.views.reveal import Reveal
from polyglotic_desktop.ui_next.views.scroll import Anchor, Placed
from polyglotic_desktop.ui_next.views.sentences import (
    selected_sentence,
    sides_aloud,
    worth_saving,
)
from polyglotic_desktop.ui_next.views.tone import (
    caption_text_colour,
    reading_weight,
    vibrant,
)
from polyglotic_desktop.ui_next.views.zones import PAUSE_SEC, Zones
from polyglotic_desktop.ui_next.word_classes import legend_html

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.joined_window import JoinedWindow

log = logging.getLogger(__name__)

WINDOW_FLAGS = (
    Qt.WindowType.Tool
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    # a click on it never takes the focus from the app underneath
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | ABOVE_ALL  # Linux: above a focused full-screen window too (550)
)
"""A caption window's (and a joined window's) window flags."""
NOTICE_GAP = 8
"""The least room between the notice line and the strip's label and
buttons either side of it; half of it between the line and the captions
under it."""
MARK_RADIUS = 6
"""The corners of a word's box under the mouse and of the strip's buttons:
the interface's small radius (`style`'s small buttons and list items, the
transcript's hovered word). Both were 5 px, on no scale (polyglotic-hq
376, 403)."""
BAND_HEIGHT = 28
"""The hover band over the top of the canvas, in pixels at 100 % text size:
it grows with Windows' text size (`band_height`), as does all the window's
chrome - its captions keep the window's own text size (A- / A+)."""


def band_height() -> int:
    """The hover band's height at the text size now."""
    return style.px(BAND_HEIGHT)


def least_size(least: Size) -> Size:
    """A window's minimum (`MIN_PANEL`) at the text size now:
    wide enough for its hover band."""
    return Size(style.px(least.width), least.height)


STRIP = ("links", "lock", "report", "settings", "stop")
"""The hover strip's buttons at its right, after the preset chip.
Word links opens its class legend on hover (polyglotic-hq 731).
Report a problem is shown for alpha testers (275)."""
BAND_IN_MS = 80
BAND_OUT_MS = 300
STILL_OVER_MS = 250
"""While the mouse is over a window, how often it checks the mouse is
still there: Windows can lose the leave (after locking and unlocking it,
polyglotic-hq 272). The idle timers' floor (`perf.budgets.IDLE_TIMER`)."""
BAND_ALPHA = 0.6
"""The band's panel: the canvas shows through it at 40 %."""
MIN_PANEL = Size(320, 120)
"""At 100 % text size: the width holds the hover band, so it grows with
the text size (`least_size`); the height holds captions, at their own."""
FADE_SEC = 0.375
FRAME_MS = 16
POINT_POLL_MS = 100
"""How often a faded window looks whether the mouse is on it."""
POINT_REST = 2
"""Looks in a row the mouse is on a faded window before it comes back
(100-200 ms): resting on it, not passing over."""
MARK_LENGTH = 56.0
MARK_THICK = 4.0
"""The listening mark, a loading bar (the user's word for it, F33): this
long and thick at 100 % text size, growing with it to 160 % - easy to see
at a glance, and thin enough to stay quiet in the padding under the text
(polyglotic-hq 267; it was three 4 px dots, 25 px across)."""
MARK_PERIOD = 1.4
"""Seconds for the bar's lit part to sweep across it once."""
MARK_LIT = 0.36
"""The share of the bar lit as it sweeps."""
MARK_TRACK_ALPHA = 0.22
MARK_LIT_ALPHA = 0.8
"""The bar's track, faint, and its lit part, in the window's original
colour."""
MARK_STILL_ALPHA = 0.7
"""The bar with Windows' animations off (reduced motion): three still
dashes along it, an ellipsis, at this ink - no sweep (260)."""
LOCKED_SEC = 4.0
FIRST_LOCKED_SEC = 12.0
"""How long the first lock says at length how to unlock (Linux, 570)."""
"""How long a window says how to unlock it, on locking; then only its
corner says the hotkey, faintly (F10, 249)."""
LOCKED_ALPHA = 0.55
"""The locked corner's words: faint, to be seen when looked for."""
LOCK_SPOT_AROUND = 10
"""How far past the locked corner's lock and hotkey resting the mouse
offers Unlock (`UnlockSpot`, polyglotic-hq 398)."""
FEW_ROWS = 3
"""At this many text rows or fewer, A+ says how to get more."""
GLYPH_PX, MIC_PX = 12, 11
"""The band's icons' and the label's mic's sizes at 100 % text size
(`glyphs`: drawn, the sizes Windows' icon font had there)."""
TEXT = "#e9ecf2"
TEXT_DIM = "#a0a8b6"
ACCENT = "#7c9cff"
ACCENT_TEXT = "#0d1220"
CORRECTION = "#f0a070"
"""A quiet correction's words (polyglotic-hq 494, decision 0228): warm, as
487's mock-up had them, and readable on the look's panel - held a moment,
then eased back into the row's own colour over `CORRECTION_SEC`."""
AROUND = (-PAD, -6.0, PAD, 8.0)
"""How far around a line's rows what's drawn with it reaches: a hovered
word's highlight, a dotted mark under its last row."""
HOVERED = QColor(255, 255, 255, 46)
"""Behind the word under the mouse (today's), on a dark panel - on a light
one (Paper's) the same in black (`shade`): white there was invisible."""
QUIET_HOVERED = 14
"""The quiet view's word under the mouse and its partner (477): under a
third of `HOVERED`'s tint - lit quietly, and a blue word still reads on it
(at 24, 4.2:1 in the UI lab)."""
SELECTED = QColor(124, 156, 255, 90)
"""Behind a phrase being dragged across."""
HIT_TESTED = QColor(0, 0, 0, 1)
"""Under an unlocked window's panel, to its square corners: Windows passes
the mouse through a translucent window's pixels that have no alpha at all,
and the panel's rounded corners left a third of each corner's resize zone
(`placement.CORNER_ZONE`) bare - a press on a window's very corner reached
the app underneath instead (the user, 2026-11-16, polyglotic-hq 398:
"sometimes I can't modify caption window size"; measured on a private
desktop). One step of alpha is too little to see."""
COPIED_SEC = 1.5
"""How long the notice line says what was copied (polyglotic-hq 333)."""


def _tr(text: str) -> str:
    return QApplication.translate("CaptionWindow", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("CaptionWindow", text, None, n)


def live_tip(keys: str) -> str:
    """Back to live's tip: what it does, and its hotkey while it has one
    ("Ctrl+Alt+J": polyglotic-hq 567) - pressed anywhere, it does the same
    in every window and transcript."""
    text = _tr("Back to the newest captions")
    return f"{text} ({keys})" if keys else text


def mic_button_tip(on: bool) -> str:
    return _tr("Caption what I say: on") if on else _tr("Caption what I say: off")


def quiet_tip() -> str:
    """The quiet view's button's words on hover (477)."""
    return _tr(
        "Quiet view on or off: captions in quiet grey and gold, only your chosen "
        "words in blue, no underlines - point at a word to see its partner"
    )


def high_contrast() -> bool:
    """Whether the learner asked Windows for high contrast (Qt's contrast
    preference): then no caption steps back (F21)."""
    hints = QGuiApplication.styleHints()  # held: its accessibility() is its child
    preference = hints.accessibility().contrastPreference()
    return preference is Qt.ContrastPreference.HighContrast


def reduced_motion() -> bool:
    """Whether the learner turned Windows' animation effects off (Qt's
    motion preference, from `SPI_GETCLIENTAREAANIMATION` on Windows): then
    the listening mark stands still (polyglotic-hq 260)."""
    hints = QGuiApplication.styleHints()  # held: its accessibility() is its child
    preference = hints.accessibility().motionPreference()
    return preference is Qt.MotionPreference.ReducedMotion


LOADING_PERIOD = 1.2
"""Seconds for the Lab's dots to light up in turn, or its ellipsis to
pulse, once (284)."""
DOT_PX = 3.0
"""A dot's radius at 100 % text size (the bar is 4 px thick)."""


def paint_loading(
    painter: QPainter,
    loading: Loading,
    at: QPointF,
    scale: float,
    color: QColor,
    now: float | None,
    newest_live: bool = False,
) -> QRect:
    """The listening mark - speech heard, its caption on its way - as the
    Lab says (`Loading`; 270's FEEDBACK.md line 27): the bar (today's), three
    dots lighting up in turn, or an ellipsis. With the ellipsis, a newest
    caption still being spoken says it by its own trailing "…" (the
    display's `LIVE_TRAIL`), so nothing more is drawn; with none, an
    ellipsis stands where the bar would. `at`: the bar's top left; `now`:
    the clock, None to stand still (Windows' animations off, a preview).
    Where it was drawn, for repainting it alone."""
    left, top = at.x(), at.y()
    thick = MARK_THICK * scale
    if loading is Loading.BAR:
        return paint_bar(painter, left, top, scale, color, now)
    phase = 0.0 if now is None else now / LOADING_PERIOD
    if loading is Loading.DOTS:
        return paint_dots(painter, left, top + thick / 2, scale, color, phase)
    if newest_live:
        return QRect()
    return paint_ellipsis(painter, left, top + thick, scale, color, phase)


def paint_bar(
    painter: QPainter, left: float, top: float, scale: float, color: QColor,
    now: float | None,
) -> QRect:  # fmt: skip
    """The loading bar, its lit part sweeping slowly across a faint track
    (`mark_lit`) - or, standing still (`now` None: Windows' animations
    off), three still dashes along it (260). Never text."""
    length, thick = MARK_LENGTH * scale, MARK_THICK * scale
    color = QColor(color)
    painter.setPen(Qt.PenStyle.NoPen)

    def part(start: float, end: float, alpha: float) -> None:
        color.setAlphaF(alpha)
        painter.setBrush(color)
        x, width = left + start * length, (end - start) * length
        painter.drawRoundedRect(QRectF(x, top, width, thick), thick / 2, thick / 2)

    if now is None:
        dash = 0.25  # three dashes and two gaps of half a dash
        for i in range(3):
            part(i * dash * 1.5, i * dash * 1.5 + dash, MARK_STILL_ALPHA)
    else:
        part(0.0, 1.0, MARK_TRACK_ALPHA)
        start, end = mark_lit(now / MARK_PERIOD)
        if end > start:
            part(start, end, MARK_LIT_ALPHA)
    return QRectF(left - 2, top - 2, length + 4, thick + 4).toAlignedRect()


def dot_inks(phase: float) -> tuple[float, float, float]:
    """The three dots' ink at `phase` (0..1, one cycle): each lights up in
    turn, then fades back to the track's."""
    inks = []
    for i in range(3):
        t = (phase - i / 3.0) % 1.0
        lit = max(0.0, 1.0 - 2.0 * t)
        inks.append(MARK_TRACK_ALPHA + (MARK_LIT_ALPHA - MARK_TRACK_ALPHA) * lit)
    return inks[0], inks[1], inks[2]


def paint_dots(
    painter: QPainter, left: float, middle: float, scale: float, color: QColor,
    phase: float,
) -> QRect:  # fmt: skip
    """The Lab's three dots, from `left`, centred on `middle`; still at
    phase 0 (Windows' animations off: the first lit)."""
    radius = DOT_PX * scale
    painter.setPen(Qt.PenStyle.NoPen)
    for i, ink in enumerate(dot_inks(phase)):
        dot = QColor(color)
        dot.setAlphaF(ink)
        painter.setBrush(dot)
        centre = QPointF(left + radius + i * radius * 3.2, middle)
        painter.drawEllipse(centre, radius, radius)
    width = radius * 2 + 2 * radius * 3.2
    return QRectF(
        left - 2, middle - radius - 2, width + 4, 2 * radius + 4
    ).toAlignedRect()


def paint_ellipsis(
    painter: QPainter, left: float, bottom: float, scale: float, color: QColor,
    phase: float,
) -> QRect:  # fmt: skip
    """The Lab's ellipsis where the bar would be, its ink pulsing gently;
    still at phase 0."""
    font = QFont(painter.font())
    font.setPixelSize(max(8, round(18 * scale)))
    font.setWeight(QFont.Weight.Bold)
    ink = QColor(color)
    pulse = 0.5 + 0.5 * math.cos(2 * math.pi * phase)
    ink.setAlphaF(MARK_TRACK_ALPHA + (MARK_LIT_ALPHA - MARK_TRACK_ALPHA) * pulse)
    painter.setPen(ink)
    painter.setFont(font)
    metrics = QFontMetrics(font)
    width = metrics.horizontalAdvance("…")
    baseline = bottom
    painter.drawText(QPointF(left, baseline), "…")
    return QRectF(
        left - 2, baseline - metrics.ascent() - 2, width + 4, metrics.height() + 4
    ).toAlignedRect()


def mark_lit(phase: float) -> tuple[float, float]:
    """The listening mark's lit part at `phase` (0..1, one sweep), as where
    it starts and ends along the bar (0..1): it comes in at the left, eases
    across and goes out at the right."""
    t = phase % 1.0
    eased = t * t * (3.0 - 2.0 * t)  # smoothstep: slow at the ends
    start = -MARK_LIT + (1.0 + MARK_LIT) * eased
    return max(0.0, start), min(1.0, start + MARK_LIT)


LABEL_CONTRAST = 7.0
"""A label's colour against the look's panel at least: WCAG's 7:1 for small
type, so it still clears 4.5:1 drawn a little faint over a panel that
isn't quite solid (Paper's: 94 %) - 261."""


def one_layout(look: CaptionLook) -> FlowOptions | None:
    """The one layout's options for `look` (polyglotic-hq 340, decision
    0132), if the Lab's New layout is on - None: today's clause rows and
    pour."""
    lab = look.lab
    if not lab.flow:
        return None
    return flow_options(
        lab.fill, lab.join, look.show_original, lab.run_on, lab.aligned, lab.placing
    )


RUN_ON_MOST = 12
"""Captions that run on start a line of their own at least this often -
at each caption whose key is a multiple of it, so where a run starts never
changes as captions come and old ones go. It bounds the work: a caption's
place follows from every caption before it in its run, and a resize step
composes the runs in view, not the window's 150 captions (6.5 ms of the
frame's 8, measured in 340). It also brings the label back, every dozen
captions or so, and reads as a paragraph's end."""


SETTLED_STEPS = 3
"""Steady's settled transcript dims over this many captions (526's
DESIGN.md 5.3: gradual, not one step)."""
ZONE_GAP = 6
ZONE_TOP = 2.0
"""The live zone's text starts this far under its top, where the line
that ends the transcript is drawn."""
"""Between the settled transcript and the live zone, in px."""
FOLLOW_SAID_SCALE = 0.82
FOLLOW_TRANSLATION_SCALE = 1.3
FOLLOW_SAID_ALPHA = 0.68
"""Follow (decision 0253): the translation leads - what was said is drawn
this much smaller and fainter, and the translation this much larger than
its share of it (so a little larger than what was said was), in full ink.
0.68 keeps what was said at 4.5:1 on the default panel."""
AHEAD_ALPHA = 0.5
"""Karaoke (Steady's words ahead): how faint the words still waiting for
their moment are drawn - a live caption's text past what is established
(`Ink.live_alpha` there, 0.85 otherwise). Faint enough that the word
lighting up is the event; still legible to a reader who looks ahead:
4.5:1 against Everyday's panel over a white scene, and against Video's
outline (0.38 until polyglotic-hq 584: 2.6:1 over a white scene)."""


def settled_look(look: CaptionLook) -> CaptionLook:
    """How Steady's settled transcript is laid out: the translation below
    its caption (526's DESIGN.md 5.3) - unless the Lab's New layout is on,
    which is then the learner's choice."""
    lab = look.lab
    if lab.flow:
        return look
    return replace(
        look, lab=replace(lab, flow=True, fill=Fill.STACKED, join=Join.SPACE)
    )


def zone_look(look: CaptionLook) -> CaptionLook:
    """How Steady's live zone is laid out: line by line, a space between
    clauses, each caption from the start of a line. Captions ran on as one
    paragraph until 548's pictures (2026-11-20): once the caption before
    had settled, the next began in the middle of a line."""
    return replace(
        look,
        lab=replace(
            look.lab, flow=True, fill=Fill.PAIRED, run_on=False, join=Join.SPACE
        ),
    )


def card_look(look: CaptionLook) -> CaptionLook:
    """How Steady's cards are laid out (decision 0260): each card a line
    pair - what was said over its translation - its clauses side by side,
    a space between them. The deck made each card to fit one line."""
    return replace(
        look,
        lab=replace(
            look.lab, flow=True, fill=Fill.PAIRED, run_on=False, join=Join.SPACE
        ),
    )


def runs_on(before: Line, line: Line) -> bool:
    """Whether `line` carries on in the line pair `before` ended in, where
    the one layout runs captions on: both finished or still being spoken
    captions of the same source and speaker, under the same label - `before`
    finished, so its end no longer moves - and neither Quick preview's
    line; and not the caption a new run starts at (`RUN_ON_MOST`)."""
    return (
        line.key % RUN_ON_MOST != 0
        and not before.live
        and not before.provisional
        and not line.provisional
        and before.source == line.source
        and before.by_you == line.by_you
        # the same label, or none: the language named once (526) is not
        # named again on the captions that follow
        and (not line.label or before.label == line.label)
        and (not line.label or before.label_color == line.label_color)
        and before.model is not None
        and line.model is not None
    )


def caption_style(
    look: CaptionLook,
    translation_size: float | None = None,
    mine_only: bool = False,
) -> CaptionStyle:
    """The caption layout's style for `look`: its font, and a word link's
    underline - with room under each row while links are underlined (F14) -
    and the Lab's (284): which text still being spoken is italic, the
    underline's thickness if it's set there, the spacing, and how your own
    speech looks (305). A window's own `translation_size` (655): its
    translation's independent scale (None: follow the caption's size).
    `mine_only`: the window captions the mic alone - your speech on the right
    there would be every line, like a chat with no one, so it stays on the
    left."""
    lab = look.lab
    unfinished = lab.unfinished
    flow = one_layout(look)
    style = CaptionStyle(
        family=look.font,
        faces=look.faces,
        weight=QFont.Weight(look.thickness),
        reading_weight=QFont.Weight(reading_weight(look.thickness)),
        link_px=LINK_PX[look.link_line] if lab.link_px is None else lab.link_px,
        row_gap=lab.row_gap,
        clause_gap=clause_gap(lab.row_gap),
        caption_gap=lab.caption_gap,
        link_gap=LINK_GAP_PX[look.link_gap],
        link_room=look.show_original
        and look.word_links in (WordLinks.COLOURS, WordLinks.ARROWS),
        arrows=look.show_original
        and look.word_links is WordLinks.ARROWS
        # poured: no facing rows to join (309) - the one layout joins any (340)
        and (lab.fill is Fill.CLAUSES or flow is not None),
        italic_provisional=unfinished in (Unfinished.AS_NOW, Unfinished.ITALIC),
        italic_live=unfinished is Unfinished.ITALIC,
        translation_size=translation_size,
        own_right=lab.own_right and not mine_only,
        own_tint=lab.own_tint,
        own_bar=lab.own_bar,
        own_label=lab.own_label,
        fill=lab.fill,
        join=lab.join,
        flow=flow,
        reading_lines=frozenset(look.reading_lines),
        reading_share=reading_lines.SHARES[look.reading_size],
        reading_past=look.reading_past,
        respelling_past=look.respelling_past,
        reading_system=look.reading_system,
    )
    if look.quiet:  # every line italic, a size step bigger, a reading over each
        # word - and never a link's underline or curve, whatever word links say
        return replace(
            style,
            text_px=style.text_px * QUIET_SCALE,
            translation_factor=style.translation_factor * QUIET_TRANSLATION,
            italic_all=True,
            reading_past=False,
            link_room=False,
            arrows=False,
        )
    return style


def shown_links(look: CaptionLook) -> WordLinks:
    """How `look`'s captions carry their word links: the quiet view's are
    there for the hover alone (477), drawn quietly; else as chosen."""
    return WordLinks.HOVER if look.quiet else look.word_links


def marks_panel(look: CaptionLook) -> Panel:
    """What `look`'s marks are drawn on: saved words readable on its panel,
    and told apart from its rows' own colours (305)."""
    return Panel(
        look.background,
        look.original,
        look.translation,
        load=look.lab.load and not look.quiet,
        palette=look.lab.load_colours,
        quiet=look.quiet,
        quiet_words=look.quiet_words,
        marks_in=look.marks_in,
        opacity=look.opacity,
        vibrance=look.vibrance,
    )


UNFINISHED_ALPHAS = {
    Unfinished.AS_NOW: (Ink.provisional_alpha, Ink.live_alpha),
    Unfinished.SAME: (1.0, 1.0),
    Unfinished.DIMMER: (Ink.provisional_alpha, Ink.provisional_alpha),
    Unfinished.ITALIC: (1.0, 1.0),
    Unfinished.COLOUR: (1.0, 1.0),
}
"""How faint text still being spoken is drawn - a provisional line, a live
caption - for each of the Lab's choices (284)."""


def unfinished_ink(ink: Ink, look: CaptionLook) -> Ink:
    """`ink` with text still being spoken drawn as the Lab says: fainter,
    or in the theme's accent, readable on the look's panel (284)."""
    unfinished = look.lab.unfinished
    provisional, live = UNFINISHED_ALPHAS[unfinished]
    colour = None
    if unfinished is Unfinished.COLOUR:
        colour = QColor(readable_on(ACCENT, look.background))
    return replace(
        ink, provisional_alpha=provisional, live_alpha=live, unfinished=colour
    )


def look_ink(ink: Ink, look: CaptionLook) -> Ink:
    """`ink` as the look draws it: text still being spoken as the Lab says
    (`unfinished_ink`), pinyin in the colour chosen and linked words in
    their link's colour, readable on the panel (polyglotic-hq 395) - not
    while Learning load colours the words by how well they're known (489:
    its colours and the link's would fight over the same word). The
    quiet view (477): every line in Quick preview's grey and gold, with
    nothing in a link's colour. Its contrast and vibrance (481): `toned`."""
    if look.quiet:
        return toned(
            replace(
                ink,
                reading_colour=ReadingColour.SAME,
                said_in_link_colours=False,
                translation_in_link_colours=False,
                panel=look.background,
                panel_opacity=look.opacity,
                quiet=True,
            ),
            look,
        )
    return toned(
        replace(
            unfinished_ink(ink, look),
            reading_colour=look.reading_colour,
            reading=QColor(look.reading_custom),
            # Learning load colours the words themselves (489): a link is
            # its bar under the word then, not the word's colour
            said_in_link_colours=look.said_in_link_colours and not look.lab.load,
            translation_in_link_colours=(
                look.translation_in_link_colours and not look.lab.load
            ),
            panel=look.background,
            panel_opacity=look.opacity,
        ),
        look,
    )


def toned(ink: Ink, look: CaptionLook) -> Ink:
    """`ink` at the look's contrast and vibrance (`views.tone`; 481): its
    colours - what was said, the translation (the quiet view's gold), a
    reading's picked colour, text still being spoken's - at the vibrance;
    the contrast for the layout to draw every line's ink at
    (`caption_layout.drawn_ink`). Word links' colours keep theirs: no
    vibrance keeps every two told apart (`caption_marks.LINK_COLORS`)."""
    if (look.contrast, look.vibrance, look.edge) == (0, 0, TextEdge.NONE):
        return ink

    def vivid(colour: QColor | None) -> QColor | None:
        if colour is None:
            return None
        return QColor(vibrant(colour.name(), look.vibrance))

    def row(colour: QColor) -> QColor:
        return QColor(
            caption_text_colour(colour.name(), look.background, look.vibrance)
        )

    return replace(
        ink,
        original=row(ink.original),
        translation=row(ink.translation),
        reading=vivid(ink.reading),
        unfinished=vivid(ink.unfinished),
        contrast=look.contrast,
        vibrance=look.vibrance,
        edge=look.edge,
    )


def spoken_in(heard: Sequence[str]) -> str:
    """What a caption's line says was spoken: "Mandarin + English" (`Labels.
    spoken`). One function, not a new lambda each time: labels made again
    from an unchanged look compare equal, and the view keeps its lines - a
    new lambda each time rebuilt every caption's line on each step of a
    look drag (polyglotic-hq 367)."""
    return spoken_names(str(language) for language in heard)


def reading_hint(language: str = "zh") -> str:
    """Said once, on a finished caption with Chinese or Japanese in it, to
    a learner with its dictionary and its reading line off (369, decision
    0155; 511) - under Readings, its own section since 470."""
    if language == "ja":
        return _tr("Furigana above Japanese: turn it on in Settings, under Readings")
    return _tr("Pinyin above Chinese: turn it on in Settings, under Readings")


HINTED_LINES = ("zh", "ja")
"""The reading lines the one-time hint tells of (`reading_hint`)."""


READING_HINT_SEC = 10.0
"""How long the pinyin hint shows."""


def word_hint() -> str:
    """Said once, on the first finished caption a window shows, until the
    learner's first lookup (polyglotic-hq 160: people didn't find that the
    words are clickable; 176)."""
    return _tr("Click any word to look it up")


def whose_captions(source: SourceId, name: str) -> str:
    """An empty window's second line: whose captions will appear in it -
    for everything the PC plays, a new learner's first window (polyglotic-hq
    484), that anything it plays is captioned there ("Everything the PC
    plays's captions" doesn't read)."""
    if source == WHOLE_SYSTEM:
        return pc_or_mac(
            _tr("Anything the PC plays is captioned here"),
            _tr("Anything the Mac plays is captioned here"),
        )
    return _tr("{app}'s captions appear here").format(app=name)


def notice_text(notice: Notice, retry_in: int | None) -> str:
    """The notice line's wording (087 section 5.5) - the same words on
    every caption window, the joined window, a transcript and Home's
    banner. A busy time: the server slows live updates (`pace`), so
    "slowed" where 087 drew "paused", and "busy time" for any hour.
    Stopped says what to do, in Home's words (polyglotic-hq 235); so do
    Not signed in (Home has Sign in) and Update needed (Home says which
    step, as the update goes - polyglotic-hq 237)."""
    if notice is Notice.RECONNECTING and retry_in:
        return _tr("Reconnecting - trying again in {n} s").format(n=retry_in)
    if notice in _COUNTED and retry_in:
        return _COUNTED[notice]().format(n=retry_in)
    if notice is Notice.MAINTENANCE:  # until when, as Home's title (563)
        until = maintenance_words.notice_until()
        if until is not None:
            return until
    return {
        Notice.PAUSED: _tr("Paused"),
        Notice.RECONNECTING: _tr("Reconnecting"),
        Notice.SERVER_BUSY: _tr("Polyglotic is busy — try again in a few minutes"),
        Notice.NOT_SIGNED_IN: _tr("Not signed in - sign in on Home"),
        Notice.UPDATE_NEEDED: _tr("Update needed - captions paused; see Home"),
        Notice.STOPPED: pc_mac_or_linux(
            _tr("Stopped - quit from the tray and start again"),
            _tr("Stopped - quit from the menu bar and start again"),
            # Linux: GNOME has no tray without an extension (571)
            _tr("Stopped - quit Polyglotic and start it again"),
        ),
        Notice.PLUS_ENDED: _tr("Plus has ended - captions stopped; see Home"),
        Notice.ALLOWANCE_EXHAUSTED: _tr("You’ve used your listening allowance"),
        Notice.CROSS_BORDER_CONSENT_REQUIRED: _tr(
            "Consent is needed to start listening"
        ),
        Notice.MINUTES_USED: _tr("Today's free minutes are used - more at midnight"),
        Notice.FAILING: _tr("Captions failing on the server - still trying"),
        Notice.UNSTABLE: _tr("Connection unstable - captions may come late"),
        Notice.BUSY: _tr("Busy time - live updates slowed; captions continue"),
        Notice.OFFLINE: _tr("No internet? Can't reach Polyglotic's server"),
        Notice.CANT_REACH: _tr("Can't reach Polyglotic's server"),
        Notice.SERVER_RESTARTING: _tr("Polyglotic's server is restarting"),
        Notice.SERVER_PROBLEM: _tr("Polyglotic's server has a problem"),
        Notice.BLOCKED: _tr("Connection blocked by this network - see Home"),
        Notice.NOT_SECURE: _tr("Can't connect securely - see Home"),
        Notice.CLOCK: pc_or_mac(
            _tr("Check this PC's date and time - see Home"),
            _tr("Check this Mac's date and time - see Home"),
        ),
        Notice.TOO_MANY_SESSIONS: pc_or_mac(
            _tr("Open on too many of your PCs - see Home"),
            _tr("Open on too many of your computers - see Home"),
        ),
        Notice.TOO_MANY_TRIES: _tr("Too many sign-in tries"),
        Notice.MAINTENANCE: _tr(
            "Planned maintenance - captions come back by themselves"
        ),
    }[notice]


_COUNTED: dict[Notice, Callable[[], str]] = {
    Notice.OFFLINE: lambda: _tr(
        "No internet? Can't reach Polyglotic's server - trying again in {n} s"
    ),
    Notice.CANT_REACH: lambda: _tr(
        "Can't reach Polyglotic's server - trying again in {n} s"
    ),
    Notice.SERVER_RESTARTING: lambda: _tr(
        "Polyglotic's server is restarting - trying again in {n} s"
    ),
    Notice.SERVER_PROBLEM: lambda: _tr(
        "Polyglotic's server has a problem - trying again in {n} s"
    ),
    Notice.TOO_MANY_TRIES: lambda: _tr(
        "Too many sign-in tries - trying again in {n} s"
    ),
}
"""Why the server can't be reached, counting down to the next try
(polyglotic-hq 251)."""


def locked_text(keys: str) -> str:
    """What a window says when it's locked: how to unlock it - with the
    hotkey as it is now, or where else to, if the hotkey doesn't work here
    (another app has it, or none was registered: the user's rehearsal
    feedback F10, 249; polyglotic-hq 398)."""
    if keys:
        return _tr("Locked - {keys} to unlock").format(keys=keys)
    return pc_mac_or_linux(
        _tr("Locked - unlock on Home or from the tray"),
        _tr("Locked - unlock on Home or from the menu bar"),
        _tr("Locked - unlock on Home"),  # Linux: Home is always there (571)
    )


def first_locked_text(keys: str) -> str:
    """What the first lock on Linux says (polyglotic-hq 546, 570): how to
    unlock again, at more length - the lock in the corner, where resting
    the mouse offers Unlock, and the hotkey where it works; or Home, which
    the app launcher always opens (some Linux desktops have no tray)."""
    if keys:
        return _tr(
            "Locked: clicks now pass through. To unlock, press {keys} or rest the"
            " mouse on the lock in this corner"
        ).format(keys=keys)
    return _tr(
        "Locked: clicks now pass through. To unlock, rest the mouse on the lock"
        " in this corner, or use Home"
    )


def lock_tip(keys: str) -> str:
    """The strip's lock button's tip (a caption window's and a joined
    window's): its hotkey, Ctrl+Alt+L, while that works; without it, how
    to unlock again - read before locking (polyglotic-hq 398)."""
    if keys:
        return hotkeys_here(
            _tr("Lock - clicks pass through to what's underneath, Ctrl+Alt+L")
        )
    return pc_mac_or_linux(
        _tr(
            "Lock - clicks pass through to what's underneath. To unlock, rest the"
            " mouse on the lock in the corner, or use Home or the tray"
        ),
        _tr(
            "Lock - clicks pass through to what's underneath. To unlock, rest the mouse"
            " on the lock in the corner, or use Home or the menu bar"
        ),
        _tr(
            "Lock - clicks pass through to what's underneath. To unlock, rest the mouse"
            " on the lock in the corner, or use Home"
        ),
    )


def preset_name(preset: Preset) -> str:
    return {
        Preset.BOTTOM_LEFT: _tr("Bottom left"),
        Preset.BOTTOM_CENTRE: _tr("Bottom centre"),
        Preset.TOP_CENTRE: _tr("Top centre"),
        Preset.CUSTOM: _tr("Where I put it"),
    }[preset]


def restore_minimised(window: QWidget) -> Callable[[], None]:
    """What brings back a caption or joined window Windows minimised: out of
    the minimised state, and shown, still without activating it."""

    def restore() -> None:
        if window.isMinimized() and window.isVisible():
            # hidden and shown again, as Ctrl+Alt+H twice: shown without
            # activating it - Qt's restore (setWindowState) activated it, on
            # a real window (272), which a full-screen game can lose to
            window.hide()
            window.setWindowState(
                window.windowState() & ~Qt.WindowState.WindowMinimized
            )
            window.show()

    return restore


def to_qrect(rect: Rect) -> QRect:
    return QRect(rect.x, rect.y, rect.width, rect.height)


def to_rect(rect: QRect) -> Rect:
    return Rect(rect.x(), rect.y(), rect.width(), rect.height())


def work_areas() -> list[Rect]:
    """Each screen's work area (the taskbar excluded), the primary first."""
    primary = QGuiApplication.primaryScreen()
    screens = QGuiApplication.screens()
    ordered = [primary, *(s for s in screens if s is not primary)] if primary else []
    return [to_rect(s.availableGeometry()) for s in ordered]


@dataclass(frozen=True)
class Marked:
    """Characters `[start, end)` of row `row` of the line `key`."""

    key: int
    row: int
    start: int
    end: int


@dataclass
class _Selecting:
    """A press on a word: a click looks it up; a drag within its clause
    and side selects a phrase from it, a drag beyond (`across`) selects
    across lines, clauses and captions (358) - character by character,
    never snapped to words (polyglotic-hq 395). `anchor`: the character
    pressed on; `press`: where; `moved`: whether the mouse has gone
    `QApplication.startDragDistance()` from there (till then, a click)."""

    word: Marked
    anchor: int
    press: QPointF = field(default_factory=QPointF)
    across: bool = False
    moved: bool = False


def drag_distance() -> int:
    """How far the mouse goes from a press before it's a drag, not a
    click: the platform's own (`QApplication.startDragDistance`)."""
    return QApplication.startDragDistance()


def _wordlike(char: str) -> bool:
    """Not a space or punctuation - what a dragged-out phrase is trimmed to."""
    return (
        not char.isspace()
        and not unicodedata.category(char).startswith("P")
        and char != "…"
    )


@dataclass
class _Drag:
    """A press being dragged: resizing `edges` (none: moving) from `start`
    (the window's place then) at the mouse's `origin`."""

    edges: Edge
    origin: QPointF
    start: Rect
    snapped: Preset = Preset.CUSTOM
    moved: bool = False


def say_resized(window: str, drag: _Drag, place: Rect, least: Size) -> None:
    """A resize drag's outcome in the log - sizes and edges only, no caption
    or app (polyglotic-hq 586: the user's "Conversation mode can't even be
    resized" wasn't seen on a private desktop, so the next try says what
    happened): the edges dragged, the size before and after, and the
    least it may be."""
    start = drag.start
    log.info(
        "%s resized at %s: %d x %d to %d x %d (least %d x %d)%s",
        window,
        drag.edges.name,
        start.width,
        start.height,
        place.width,
        place.height,
        least.width,
        least.height,
        " - unchanged"
        if (start.width, start.height) == (place.width, place.height)
        else "",
    )


@dataclass
class _TranslationSlot:
    rows: tuple[str, ...]
    until: float | None
    spaces: dict[int, float] = field(default_factory=dict)
    bare: float = 0.0
    room: float = 0.0
    filled_at: int | None = None


class Canvas(CaptionSurface):
    """The window's captions and what's painted with them. Takes no mouse
    of its own: the window has it (resizing, moving, hovering)."""

    def __init__(self, window: "CaptionWindow", view: CaptionLines) -> None:
        super().__init__(view, parent=window)
        self.owner = window
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.placed: list[tuple[Line, LaidLine, QRectF]] = []
        """The lines the last paint drew, laid out, and where."""
        self.turning: list[tuple[Line, LaidLine, QRectF, float]] = []
        self._covered: dict[int, tuple[bool, float]] = {}
        self._drawn: set[int] = set()
        """The cards the last paint drew turned away on the drum, and how
        much each is squashed: drawn, never pointed at (decision 0260)."""
        self._runs: tuple[int, dict[int, tuple[Line, ...]]] | None = None
        self._entered: (
            tuple[tuple[int, int, float], CaptionStyle, dict[int, Open | None]] | None
        ) = None
        """Captions that run on: each line's run for the view's revision,
        and what each found open at a width and style (`_entry`)."""
        self.hovered: Marked | None = None
        """The word under the mouse: drawn behind, with its word links."""
        self.selection: Marked | None = None
        """A phrase being dragged across."""
        self._held: dict[int, list[Words]] = {}
        """The words the window's selection holds in the lines being drawn
        (`CaptionWindow.held`), by line key - drawn behind them."""
        self.said_now: dict[int, list[Words]] = {}
        """The word being read aloud (Say it, polyglotic-hq 495), by line key."""
        self.video = Video()
        self.tracks_visible = False
        self.track_read_until: float | None = None
        self._own_line: Line | None = None
        self._own_until = 0.0
        self.subtitle_timer = QTimer(self, singleShot=True)
        self.subtitle_timer.timeout.connect(self.update)
        self.clear_top = float(PAD)
        """Where the last paint's captions started (below the band, if shown)."""
        self.mark_rect: QRect | None = None
        self._dirty = QRectF()
        """What the paint under way was asked to draw: lines outside it are
        placed, not painted (a hovered word repaints its line alone)."""
        self._panel_kept: tuple[tuple[object, ...], QPixmap] | None = None
        """The panel's picture and what it was drawn for (`_panel`)."""
        self.at_rest: dict[tuple[int, int], float] = {}
        """Where the last paint's rows sit at rest, before any slide - each
        row's top on the screen, by its line's key and row index: what the
        next arrival measures against (`rest_rows`). Noted only while the
        window slides."""

    # -- a new caption's lines, one at a time (views.reveal; 309) ---------------------

    def lines_shown(self, line: Line) -> int | None:
        """How many of `line`'s lines of text show now; None: all of them
        (always, unless the Lab's Gap between new lines holds some back)."""
        owner = self.owner
        if not owner.reveal.pending or not self.view.scroll.following:
            return None
        return owner.reveal.shown(line.key)

    def lines_in_view(self) -> Sequence[Line]:
        """The view's lines with any text showing: a new caption none of
        whose lines has come yet isn't there - nor, while the mouse holds
        the view, a card dealt since (`CaptionWindow.view_held`)."""
        lines = self._lines()
        held = self.owner.view_held()
        if held is not None:
            lines = [line for line in lines if line.key <= held]
        if not self.owner.reveal.pending:
            return lines
        return [line for line in lines if self.lines_shown(line) != 0]

    def _lines(self) -> Sequence[Line]:
        """The view's lines this canvas shows: all of them - with Steady's
        two zones, those that have settled (`views.zones`; the live zone
        shows the rest)."""
        if self.owner.video_enabled and not self.owner._mine_only():
            return [line for line in self.view.lines if not line.by_you]
        zones = self.owner.zones
        if zones is None:
            return self.view.lines
        return [line for line in self.view.lines if line.key in zones.settled]

    def own_subtitle(self) -> Line | None:
        """The newest mic caption in Video's independent top strip."""
        if (
            not self.owner.video_enabled
            or self.owner._mine_only()
            or not self.owner.choices.show_mic
        ):
            return None
        line = next(
            (
                line
                for line in reversed(self.view.lines)
                if line.by_you and self.video.is_current(line)
            ),
            None,
        )
        previous, self._own_line = self._own_line, line
        if line is not None and (
            previous is None or line.key != previous.key or line.rows != previous.rows
        ):
            text = " ".join(row.text for row in line.rows)
            self._own_until = self.owner.clock() + need(
                text, MEANT_PACE.value, MEANT_PACE_SPACED.value
            )
        return line if self.owner.clock() < self._own_until else None

    def _own_subtitle_font(self) -> QFont:
        font = QFont(style.ui_font())
        font.setPixelSize(
            max(
                1,
                round(
                    self.engine.style.text_px
                    * self.view.text_size
                    * OWN_SUBTITLE_SIZE.value
                ),
            )
        )
        # Fit the two-line strip above a full pair where possible. A very
        # shallow window can page the pair, but still needs one complete row.
        available = max(0, PAD + self._seen_height() - band_height())
        original = row_room(self.engine, RowKind.ORIGINAL, self.view.text_size)
        translation = row_room(self.engine, RowKind.TRANSLATION, self.view.text_size)
        room = max(
            0.0,
            min(
                available * OWN_SUBTITLE_ROOM.value,
                available - max(original, translation),
            ),
        )
        height = QFontMetrics(font).height()
        if 2 * height > room:
            font.setPixelSize(max(1, int(font.pixelSize() * room / (2 * height))))
        return font

    def _own_subtitle_height(self) -> int:
        return 2 * QFontMetrics(self._own_subtitle_font()).height()

    def _paint_own_subtitle(self, painter: QPainter) -> bool:
        line = self.own_subtitle()
        if line is None:
            return False
        copy = self.video.own_words(line, self.owner.clock(), self.owner.card_split)
        label = self.owner.labels.you
        painter.save()
        painter.setFont(self._own_subtitle_font())
        painter.setPen(QColor(line.label_color or label.color))
        metrics = painter.fontMetrics()
        strip = QRectF(PAD, band_height(), self._width(), self._own_subtitle_height())
        painter.setClipRect(strip, Qt.ClipOperation.IntersectClip)
        painter.fillRect(strip, QColor(self.owner.look.background))
        for text in (
            label.name + "  " + copy.original
            if self.owner.preset_menu.show is not Show.TRANSLATION and copy.original
            else "",
            copy.translation
            if self.owner.preset_menu.show is not Show.ORIGINAL
            else "",
        ):
            if text:
                area = QRectF(strip.x(), strip.y(), strip.width(), metrics.height())
                painter.drawText(
                    area,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    metrics.elidedText(
                        text, Qt.TextElideMode.ElideRight, self._width()
                    ),
                )
            strip.translate(0, metrics.height())
        painter.restore()
        return copy.writing

    def _all_placed(self) -> list[tuple[Line, LaidLine, QRectF]]:
        """Every caption drawn in the window and where: its own - and,
        with two zones, the live zone's (what a hover or a click finds)."""
        return self.owner.placed()

    def _carries_on(self, before: Line, line: Line) -> bool:
        """Whether `line` runs on from `before` here (`runs_on`)."""
        return runs_on(before, line)

    def _view_height(self) -> float:
        """The height the scroll fills: the room for text - less the live
        zone's, with two zones; with cards, less the room kept for a card
        made ahead, and more by what the drum holds above its flat part."""
        if self.owner.deck is None:
            return max(1.0, super()._view_height() - self.owner.zone_room())
        room = self._seen_height() - self.owner.held_top()
        return max(1.0, room) + self._rolled()

    def _seen_height(self) -> float:
        """The room for text on the screen: with cards, above Back to
        live while it shows - it never covers a card."""
        owner = self.owner
        if self.tracks_visible and not owner.pill.isVisible() and not owner.band_shown:
            return max(1.0, self.height() - VIDEO_MARGIN - PAD)
        taken = owner.zone_room() + owner.pill_room()
        return max(1.0, super()._view_height() - taken)

    def _rolled(self) -> float:
        """How much more of the list the drum shows than a flat list
        would, in px (`views.cards.drum_room`); 0 without cards."""
        if self.owner.deck is None or not self.owner.view.scroll.following:
            return 0.0  # scrolled back: a flat list, every card readable
        return drum_room(self._seen_height())

    def _height(self, line: Line, laid: LaidLine | None = None) -> float:
        """How much further down `line` takes the text: its height as far
        as it shows - and, where captions run on, the gap above it or, for
        one that carries on, less the line pair it shares with the caption
        before (`_above`)."""
        if laid is None:
            laid = self._laid(line)
        return max(0.0, self._tall(line, laid) + self._above(line, laid))

    def _tall(self, line: Line, laid: LaidLine | None = None) -> float:
        """`line`'s height from its own top, as far as it shows."""
        if laid is None:
            laid = self._laid(line)
        owner = self.owner
        if owner.deck is not None and owner.video_enabled:
            return owner.card_height(line, laid.height)
        if owner.deck is None:
            shown = self.lines_shown(line)
            if shown is not None and shown < len(laid.breaks):
                return laid.breaks[shown - 1] if shown > 0 else 0.0
        return laid.height

    # -- captions that run on (the one layout; polyglotic-hq 340) --------------------

    def _entry(self, line: Line, width: int) -> Open | None:
        """The line pair the caption before `line` left open at `width`,
        if `line` carries on in it (`runs_on`) - None unless the Lab's
        Captions run on is on. A caption's place follows from those before
        it in its run, so the run is followed from its start: each one's
        open pair composed (arithmetic over widths measured once, kept by
        the engine), none laid out. Only the runs asked about - those in
        view - are followed."""
        if not self._running_on():
            return None
        view = self.view
        engine = self.engine
        runs = self._runs
        if runs is None or runs[0] != view.revision:
            # each line's run, as far as it: found once per change of the view
            found: dict[int, tuple[Line, ...]] = {}
            run: tuple[Line, ...] = ()
            for each in self._lines():
                carries = bool(run) and self._carries_on(run[-1], each)
                run = (*run, each) if carries else (each,)
                found[each.key] = run
            runs = self._runs = (view.revision, found)
        run = runs[1].get(line.key, ())
        if len(run) < 2:
            return None
        stamp = (view.revision, width, view.text_size)
        kept = self._entered
        if kept is None or kept[0] != stamp or kept[1] is not engine.style:
            kept = self._entered = (stamp, engine.style, {})
        entries = kept[2]
        if line.key not in entries:
            left: Open | None = None
            for each in run:
                entries[each.key] = left
                left = engine.left_open(each, width, view.text_size, left)
        return entries[line.key]

    def _laid(self, line: Line) -> LaidLine:
        width = self._width()
        owner = self.owner
        if owner.host is not None and owner.deck is not None:
            laid = self.engine.laid_card(line, width, self.view.text_size)
        else:
            laid = self.laid_at(line, width)
        if not owner.video_enabled:
            laid = owner.reserve_translation(line, laid, self.engine.style)
        return laid

    def _running_on(self) -> bool:
        options = self.engine.style.flow
        return options is not None and options.run_on and options.share

    def _gap(self) -> float:
        """Between one caption and the next, for the scroll - none where
        captions run on: there each line's own room above it is part of
        how far it takes the text (`_above`), since one that carries on
        has none."""
        return 0.0 if self._running_on() else super()._gap()

    def _above(self, line: Line, laid: LaidLine | None = None) -> float:
        """Where captions run on: how far below where the scroll places it
        `line` is drawn - the gap between captions, for one that starts a
        line of its own (but the oldest); less than nothing for one that
        carries on: the line pair the caption before left open, which its
        first text is on. 0 where they don't."""
        if not self._running_on():
            return 0.0
        lead = (self._laid(line) if laid is None else laid).lead
        if lead:
            return -lead
        lines = self._lines()
        if lines and lines[0].key == line.key:
            return 0.0
        return super()._gap()

    def _positioned(
        self, line: Line, placed_top: float, laid: LaidLine | None = None
    ) -> tuple[Line, LaidLine, float]:
        """Where `line` is drawn, for where the scroll placed it - with
        cards, in the flat list the drum then turns (`_rolled`)."""
        held = self.owner.held_top()
        if laid is None:
            laid = self._laid(line)
        top = PAD + held + placed_top + self._above(line, laid) - self._rolled()
        return line, laid, top

    # -- measuring at a width --------------------------------------------------------

    def laid_at(self, line: Line, width: int) -> LaidLine:
        return self.engine.laid(
            line, width, self.view.text_size, self._entry(line, width)
        )

    def rows_that_fit(self) -> float:
        """About how many rows of text the window shows at its text sizes -
        a row the mean of what was said's and its translation's."""
        text = self.view.text_size
        trans = (
            self.engine.style.translation_size
            if self.engine.style.translation_size is not None
            else text
        )
        mean = (text + trans) / 2 if self.view.target is not None else text
        row = self.engine.style.text_px * mean * 1.35
        return self._view_height() / row

    # -- painting ---------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        with spans.span("caption_window.paint"):
            trace.tracer().painted()  # what was put in a view shows now
            self._dirty = QRectF(event.rect())
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self._paint_panel(painter)
            if self.owner.band_shown:
                self._paint_band(painter)
            painter.end()
            self._drawn_revision = self.view.revision

    def hold(self) -> None:
        """The cards' look or mode is about to change: where the rows
        stand is noted, and the next paint glides the stack from there to
        its new place (`CaptionWindow._settle`) - what was read isn't
        moved in one frame, and nothing flashes (polyglotic-hq 552)."""
        owner = self.owner
        if owner.deck is None or not self.view.lines or not owner.sliding:
            return
        if owner._held_rows is None:
            owner._held_rows = self.rest_rows()

    def _panel(self, painter: QPainter, top: float, bottom: float) -> None:
        """The panel behind the captions, drawn from its picture: the
        rounded, translucent rectangle is drawn once for its size, colour,
        edge and the screen's scale, and each paint copies it (polyglotic-hq
        406: Qt took 1.0 ms to draw a 900 x 460 one on CI's Linux runner and
        0.26 ms on Windows, every live update; copying it 0.05-0.07 ms)."""
        look = self.owner.look
        whole = self.owner.band_shown or self.owner.hovered
        opacity = max(look.opacity, 0.55) if whole else look.opacity
        color = QColor(look.background)
        color.setAlphaF(opacity)
        edge = shade(self.owner.bar, 46) if whole else None
        left, right = self._sides()
        if not self.owner.locked:  # every corner takes the mouse (398)
            painter.fillRect(self.rect(), HIT_TESTED)
        divider = shade(self.owner.bar, 38) if left else None
        width = self.width()
        area = QRectF(-left, top, width + left + right, bottom - top)
        if not copies_exactly(painter):
            # painted scaled (the UI lab's screen of windows) or recorded
            # (its design check reads the shapes): drawn there, as it was
            draw_panel(painter, area, color, edge, divider)
            return
        ratio = painter.device().devicePixelRatioF()
        drawn = (
            width, top, bottom, ratio, color.rgba(),
            edge.rgba() if edge else None, left, right,
            divider.rgba() if divider else None,
        )  # fmt: skip
        kept = self._panel_kept
        if kept is None or kept[0] != drawn:
            if self.owner.host is not None and self.owner.host.dragging:
                # The next drag step has another size. Draw the three panels
                # straight onto the window instead of allocating three pixmaps.
                draw_panel(painter, area, color, edge, divider)
                return
            picture = panel_picture(
                QSize(width, math.ceil(bottom)), ratio, area, color, edge, divider
            )
            kept = self._panel_kept = (drawn, picture)
        painter.drawPixmap(QPointF(0.0, 0.0), kept[1])

    def forget_panel(self) -> None:
        """The panel's picture let go (the window hidden): drawn again when
        it shows."""
        self._panel_kept = None

    def _sides(self) -> tuple[float, float]:
        """How far the panel runs on past the left and right edges: a joined
        window's column runs on under its neighbours, so only the window's
        outer corners are round."""
        inner_left, inner_right = self.owner.inner_sides()
        return (16.0 if inner_left else 0.0), (16.0 if inner_right else 0.0)

    def _measure_positions(
        self,
    ) -> tuple[list[Placed[Line]], dict[int, LaidLine]]:
        """Keep each layout used to measure the scroll so it can be drawn."""
        measured: dict[int, LaidLine] = {}

        def height(line: Line) -> float:
            laid = measured[line.key] = self._laid(line)
            return self._height(line, laid)

        placed = self.view.scroll.placed(
            self.lines_in_view(), height, self._view_height(), self._gap()
        )
        return placed, measured

    def _list_positions(self) -> tuple[list[tuple[Line, LaidLine, float]], float]:
        placed, measured = self._measure_positions()
        self.owner._settle()
        offset, entry = self._motion()
        # A moving list still shows text above its final resting page.
        # Keep those lines until they actually leave the viewport.
        if offset and placed:
            placed = self._run_on(placed, offset)
        shown = self._moved(
            [
                self._positioned(item.line, item.top, measured.get(item.line.key))
                for item in placed
            ],
            offset,
            entry,
        )
        self.shown = len(placed)
        return shown, offset

    def _paint_panel(self, painter: QPainter) -> None:
        view = self.view
        width = self._width()
        listening = self.owner.mark_showing
        # the whole panel, the size the learner set: one that hugged the text
        # grew as live text came, and in a joined window a quiet column had
        # none - one column bobbing beside the others (the user's "window
        # resizes / flickers", polyglotic-hq 272). A window with nothing to
        # show is faded out, panel and all (`views.caption_window.shows`).
        self._panel(painter, 0, self.height())
        asked = max(self.owner.question_foot(), self.owner.notice_foot())
        cards = self.owner.deck is not None
        drummed = cards and view.scroll.following
        if self.owner.video_enabled:
            self._paint_video(painter, asked, listening)
            return
        foot = PAD + self._seen_height()
        shown, offset = self._list_positions()
        if cards:
            # The drum fades whole cards as they pass the toolbar or question.
            top = max(band_height() + 1.0 if self.owner.band_shown else 0.0, asked)
        else:
            # List captions clear whole rows, including the marks under them.
            under = self._under(shown)
            top = (
                self._clear_of_band(shown, under)
                if self.owner.band_shown
                else self._clear_of(shown, float(PAD), under)
            )
            if asked > top:
                top = self._clear_of(shown, asked, under)
            flow = self.engine.style.flow
            if flow is not None and flow.split:
                top = self._whole_pairs(shown, top, under)
        if self.owner.zones is not None and view.scroll.following:
            # the transcript above the live zone shows whole captions: one
            # whose start is cut off there isn't drawn (a translation
            # stood alone at the top of 346's picture, 2026-11-20). With
            # nothing being read the newest is drawn as far as it fits: it
            # may be taller than the window. Above the live zone it waits
            # for room instead (the lab's picture, the same day)
            reading = self.owner.zone_room() > 0.0
            for _, laid, y in shown if reading else shown[:-1]:
                if y < top - 0.5:
                    top = max(top, y + laid.height)
        self.clear_top = top
        painter.save()
        painter.setClipRect(QRectF(0, top, self.width(), max(0.0, foot - top)))
        self._drawn = {line.key for line, _, _ in self.placed}
        self.placed = []
        self.turning = []
        seen = self._seen_height()
        limit = self.owner.card_limit if cards else None
        whole = self._dirty.contains(QRectF(self.rect()))  # a part: its lines
        # B (F21, 253): the newest caption full, those before it a step back -
        # the preview line, newer still, full too; scrolled back, all full.
        # The Lab: how far back, and captions new for a while full too (284)
        lab = self.owner.look.lab
        lab_quiet = self.owner.look.quiet
        # the settled transcript above Steady's live zone dims step by step
        # (526's DESIGN.md 5.3), unless the Lab asks for more steps
        steps = lab.older_steps
        if (self.owner.zones is not None or cards) and steps < SETTLED_STEPS:
            steps = SETTLED_STEPS
            lab = replace(lab, older_steps=steps)
        older, older_translation = older_alphas(
            high_contrast(),
            view.scroll.following,
            (lab.older, older_translation_ink(lab.older)),
        )
        newest = next(
            (line.key for line in reversed(self._lines()) if not line.provisional),
            None,
        )
        # step by step (the Lab's, 305): each caption's place back from the
        # newest - by place, so it changes only when a caption comes
        places = (
            {
                key: back
                for back, key in enumerate(
                    reversed(
                        [line.key for line in self._lines() if not line.provisional]
                    )
                )
            }
            if steps > 1
            else None
        )
        now = self.owner.clock()
        veil = self.owner.veil(now) if cards else 1.0
        chosen = self.owner.held.selection
        self._held = held_words([ln for ln, _, _ in shown], chosen) if chosen else {}
        stack_foot = -math.inf
        for place, (line, laid, y) in enumerate(shown):
            squash = turned = 1.0
            if drummed:
                tall = self._tall(line, laid)
                y, squash, turned = drum(y - PAD, tall, seen)
                y += PAD
                # Keep nearly flat text sharp. Start turning from full height:
                # snapping from 1 to FLAT_ENOUGH moved the translation a frame
                # before the rest of the card had travelled that far (617).
                squash = min(1.0, squash / FLAT_ENOUGH)
                if y + tall > PAD + seen:  # coming in at the foot: it fades in
                    turned *= max(0.0, min(1.0, (PAD + seen - y) / max(1.0, tall)))
                previous_foot = stack_foot
                stack_foot = max(stack_foot, y + tall * squash)
                if self.owner.card_offset(line.key, offset) < offset:
                    # Cards that arrived behind a held view are already at
                    # their final positions. Each fades in as the moving
                    # cards clear its own top, including their translations.
                    over = previous_foot - y - CARD_CLEAR_PX.value
                    clear = 1.0 - over / max(1.0, 0.08 * tall)
                    turned *= max(0.0, min(1.0, clear))
                if limit is not None and len(shown) - place > limit:
                    turned = 0.0  # subtitles: so many cards, no more
                if turned <= 0.02 or squash < SMEAR:
                    continue  # gone, or a smear
                # what comes to stand at the top (the toolbar, a question)
                # never cuts a card or removes one at full ink: it fades
                # out, and back in after - but the newest is always there
                covered = y < top - 0.5 and place < len(shown) - 1
                turned *= self._cover(line.key, covered, now)
                if turned <= 0.02:
                    continue
            elif limit is not None and len(shown) - place > limit:
                continue
            elif cards:
                # scrolled back: every card at full ink. The cards stand
                # from the foot up (`CaptionWindow._held_at`), so only the
                # top can cut one: that card shows only while the stack
                # glides past, fading. At the oldest cards they stand from
                # the top, and the foot cuts the last like any list's.
                tall = self._tall(line, laid)
                rest = y - offset
                if rest < max(top, PAD) - 0.5:
                    turned = min(1.0, abs(offset) / max(1.0, 0.75 * tall))
                    if turned <= 0.02:
                        continue
            elif not any(
                y + row.top + row.layout.boundingRect().height() > top + 0.01
                for row in laid.rows
            ):
                continue  # every row above the top: none drawn (W3)
            if cards and veil < 1.0:
                turned *= veil
                if turned <= 0.02:
                    continue
            at = QPointF(PAD, y)
            alpha = translation = 1.0
            # the quiet view is a step back throughout: none further (477) - on
            # a light panel the two together fell under what can be read
            if newest is not None and line.key < newest and not lab_quiet:
                new = newness(self.owner.age_of(line.key, now), lab)
                if places is not None:
                    back = places.get(line.key, steps)
                    new = max(new, by_place(back, lab))
                alpha = ink_between(older, new)
                translation = ink_between(older_translation, new) / alpha
            ink = self.ink
            if alpha < 1.0 or translation != 1.0:
                ink = replace(self.ink, alpha=alpha, translation_alpha=translation)
            correction = self.owner.correction_colour(line.key, now, ink.original)
            if correction is not None:  # a quiet correction (494)
                ink = replace(ink, correction=correction)
            if line.live and self.owner.faint_ahead:  # karaoke's waiting words
                ink = replace(ink, live_alpha=AHEAD_ALPHA)
            if turned < 1.0:  # fainter through its colours: an outline stays
                ink = replace(ink, alpha=ink.alpha * turned)  # solid (584)
            height = self._tall(line, laid)
            rect = QRectF(at.x(), at.y(), width, height)
            asked = whole or self._dirty.intersects(rect.adjusted(*AROUND))
            if asked:  # else outside what this paint redraws: placed, not painted
                highlighted = (
                    line.key in self._held
                    or line.key in self.said_now
                    or (self.hovered is not None and self.hovered.key == line.key)
                    or (self.selection is not None and self.selection.key == line.key)
                )
                part = height < laid.height - 0.01
                if part:
                    painter.save()
                    painter.setClipRect(
                        QRectF(0.0, y, float(self.width()), height),
                        Qt.ClipOperation.IntersectClip,
                    )
                if squash < 1.0:  # a card turning away on the drum
                    painter.save()
                    painter.translate(0.0, y)
                    painter.scale(1.0, squash)
                    flat = QPointF(at.x(), 0.0)
                    if highlighted:
                        self._paint_marked(painter, line, laid, flat)
                    self.engine.paint(painter, line, laid, flat, ink, self.marks)
                    painter.restore()
                else:
                    if highlighted:
                        self._paint_marked(painter, line, laid, at)
                    self.engine.paint(painter, line, laid, at, ink, self.marks)
                if part:
                    painter.restore()
            if squash == 1.0 and turned > 0.5:
                self.placed.append((line, laid, rect))
            else:  # a card turned away isn't pointed at: drawn, not placed
                self.turning.append((line, laid, rect, squash))
        painter.restore()
        if not view.lines:
            self._paint_empty(painter)
        self.mark_rect = self._paint_mark(painter) if listening else None
        self._paint_locked(painter)

    def _paint_video(self, painter: QPainter, asked: float, listening: bool) -> None:
        owner = self.owner
        now = owner.clock()
        anchor = self.view.scroll.anchor
        frozen = anchor is None and owner.view_held() is not None
        lines = self._lines()
        selection = owner.held.selection
        self._held = held_words(lines, selection) if selection else {}
        top = max(
            VIDEO_MARGIN,
            band_height() if owner.band_shown else 0,
            band_height() + self._own_subtitle_height()
            if owner.choices.show_mic
            else 0,
            asked,
        )
        self.placed = self.video.paint(
            painter,
            self.engine,
            self.ink,
            self.marks,
            self._paint_marked,
            lines,
            self.view.text_size,
            self.width(),
            self.height(),
            now,
            top,
            VIDEO_MARGIN + (owner.pill_room() if anchor is not None else 0),
            anchor=anchor.key if anchor is not None else None,
            frozen=frozen,
            split=owner.card_split,
            scrolling=owner.timing is CaptionMode.SCROLLING,
            sides=owner.video_sides(),
            animate=effective(owner.look.arrival, reduced_motion()).slides,
            languages=owner.video_languages(),
            lines_shown=owner.preset_menu.video_lines_shown,
        )
        self.tracks_visible = anchor is None and not frozen
        flow = self.video.flow
        until = flow.read_until if flow is not None and self.tracks_visible else None
        if until != self.track_read_until:
            self.track_read_until = until
            owner.wake_frames()
        self.clear_top = top
        self.turning = []
        self.shown = len(self.placed)
        if not self.placed and not self.view.lines:
            self._paint_empty(painter)
        self.mark_rect = self._paint_mark(painter) if listening else None
        self._paint_locked(painter)
        own_writing = self._paint_own_subtitle(painter)
        if own_writing or (self.tracks_visible and flow is not None and flow.animating):
            self.subtitle_timer.start(FRAME_MS)
        elif self.own_subtitle() is not None:
            self.subtitle_timer.start(max(1, math.ceil((self._own_until - now) * 1000)))
        else:
            self.subtitle_timer.stop()

    # -- arriving: step and slide (views.arrivals; polyglotic-hq 253, 267) ------------

    def _cover(self, key: int, covered: bool, now: float) -> float:
        """The ink of card `key`, `covered` or not by what stands at the
        top now: eased over `COVER_FADE_SEC` either way."""
        was = self._covered.get(key)
        if was is None:
            if not covered:
                return 1.0
            # first seen covered: was it drawn before? then it fades
            was = (False, now - COVER_FADE_SEC) if key in self._drawn else (True, -1e9)
        if was[0] != covered:
            done = min(1.0, max(0.0, (now - was[1]) / COVER_FADE_SEC))
            was = (covered, now - (1.0 - done) * COVER_FADE_SEC)
        self._covered[key] = was
        share = min(1.0, max(0.0, (now - was[1]) / COVER_FADE_SEC))
        if not covered and share >= 1.0:
            del self._covered[key]
            return 1.0
        if len(self._covered) > 200:
            self._covered.clear()
        return 1.0 - share if covered else share

    def covering(self) -> bool:
        """A card is fading under what covers it, or back: frames go on."""
        now = self.owner.clock()
        return any(now - since < COVER_FADE_SEC for _, since in self._covered.values())

    def _run_on(self, placed: list[Placed[Line]], offset: float) -> list[Placed[Line]]:
        """`placed` and the lines beyond it that show while the stack is
        drawn `offset` px from its place: no empty band where it came from."""
        lines = self.lines_in_view()
        gap = self._gap()
        keys = [line.key for line in lines]
        out = list(placed)
        if offset > 0.0:  # drawn lower: older cards show above
            at = keys.index(out[0].line.key) if out[0].line.key in keys else 0
            y = out[0].top
            while at > 0 and y + offset > -self._rolled():
                at -= 1
                y -= self._height(lines[at]) + gap
                out.insert(0, Placed(lines[at], y))
        else:  # drawn higher: newer cards show below
            last = out[-1].line.key
            at = keys.index(last) if last in keys else len(keys) - 1
            y = out[-1].top + self._height(out[-1].line) + gap
            foot = self._view_height()
            while at < len(lines) - 1 and y + offset < foot:
                at += 1
                out.append(Placed(lines[at], y))
                y += self._height(lines[at]) + gap
        return out

    def _motion(self) -> tuple[float, dict[int, float]]:
        """How far below its place the text in view is drawn now, and each
        new line's entry beyond that (its key -> px) - none unless the
        window slides (`CaptionWindow.sliding`)."""
        owner = self.owner
        if not owner.sliding:
            return 0.0, {}
        now = owner.clock()
        if owner.deck is not None:  # the cards' one glide (`views.cards.Glide`)
            return owner.glide.to(now), {}
        motion = owner.motion
        gap = ENTRY_GAP_PX * self.view.text_size
        entries = {key: gap * motion.entry(key, now) for key in motion.entries}
        return motion.offset(now), {k: px for k, px in entries.items() if px > 0.0}

    def _moved(
        self,
        shown: list[tuple[Line, LaidLine, float]],
        offset: float,
        entry: dict[int, float],
    ) -> list[tuple[Line, LaidLine, float]]:
        """`shown` (each line's top at rest) where it's drawn now - its rest
        places noted first (`at_rest`) when the window slides."""
        if not self.owner.sliding:
            return shown
        self.at_rest = self._rows_of(shown)
        if not offset and not entry:
            return shown
        # a caption that runs on shares a line with the one before: it
        # arrives in place, not from below
        if self.owner.deck is not None:
            near = self.owner.card_offset
            return [(ln, laid, y + near(ln.key, offset)) for ln, laid, y in shown]
        return [
            (ln, laid, y + offset + (0.0 if laid.lead else entry.get(ln.key, 0.0)))
            for ln, laid, y in shown
        ]

    def _rows_of(
        self, shown: list[tuple[Line, LaidLine, float]]
    ) -> dict[tuple[int, int], float]:
        """Each row's top on the screen, by its line's key and row index."""
        top = float(self.mapToGlobal(QPoint(0, 0)).y())
        return {
            (line.key, row.index): top + y + row.top
            for line, laid, y in shown
            for row in laid.rows
        }

    def scroll_by(self, dy: float) -> None:
        if dy:
            super().scroll_by(dy)
            self.view.scroll.sticky = not self.view.scroll.following

    def rest_rows(self) -> dict[tuple[int, int], float]:
        """Where each row in view sits at rest now - every row's top on the
        screen - for an arrival to measure how far the text rose since the
        last paint (`at_rest`)."""
        placed, measured = self._measure_positions()
        return self._rows_of(
            [
                self._positioned(item.line, item.top, measured[item.line.key])
                for item in placed
            ]
        )

    def _paint_marked(
        self, painter: QPainter, line: Line, laid: LaidLine, at: QPointF
    ) -> None:
        """Behind the words selected (`CaptionWindow.held`), the hovered
        word and a phrase being dragged out: a soft highlight - under the
        text, so its word links and marks still show; and the hovered
        word's word links - it and its counterpart in the link's colour
        (links "On hover", and on hover with Colours or Arrows)."""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SELECTED)
        for box in word_rects(laid, self._held.get(line.key, ())):
            painter.drawRoundedRect(box.translated(at), 6, 6)
        painter.setBrush(SAID_NOW)
        for box in word_rects(laid, self.said_now.get(line.key, ())):
            painter.drawRoundedRect(box.translated(at), 6, 6)
        painter.setBrush(SELECTED)
        hovered_tint = shade(self.owner.bar, HOVERED.alpha())
        quiet_tint = shade(self.owner.bar, QUIET_HOVERED)
        if self.owner.look.quiet:  # softer: the blue reads on it (477)
            hovered_tint = quiet_tint
        for marked, color in ((self.hovered, hovered_tint), (self.selection, SELECTED)):
            if marked is not None and marked.key == line.key:
                self._fill(painter, laid, at, marked, color)
        hovered = self.hovered
        look = self.owner.look
        if (
            hovered is None
            or hovered.key != line.key
            or shown_links(look) is WordLinks.OFF
        ):
            return
        for partner, link in linked_with(line, hovered):
            if look.quiet:  # quietly: as softly as the word pointed at (477)
                tint = quiet_tint
            else:
                tint = QColor(link_colour(self.owner.marks.panel, link))
                tint.setAlphaF(0.4)
            self._fill(painter, laid, at, partner, tint)

    @staticmethod
    def _fill(
        painter: QPainter, laid: LaidLine, at: QPointF, marked: Marked, color: QColor
    ) -> None:
        row = next((r for r in laid.rows if r.index == marked.row), None)
        if row is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for rect in row.rectangles(marked.start, marked.end):
            box = rect.translated(at.x(), at.y() + row.top).adjusted(-3, 0, 3, 0)
            if row.above:  # its pinyin with it (369)
                box.setTop(box.top() - row.band)
            painter.drawRoundedRect(box, MARK_RADIUS, MARK_RADIUS)

    # -- words under the mouse -----------------------------------------------------------

    def line_area(self, key: int) -> QRect | None:
        """Where line `key` was last drawn, with what's drawn just around its
        rows (a hovered word's highlight, dots under a row): what a change
        to that line alone repaints. None if it wasn't drawn."""
        for line, _, rect in self._all_placed():
            if line.key == key:
                return rect.adjusted(*AROUND).toAlignedRect()
        return None

    def hit(self, pos: QPointF) -> tuple[Line, LaidRow, QPointF, int] | None:
        """The character under `pos`: its line, row, the row's top left
        (in the canvas) and its index in the row's text - or None."""
        if pos.y() < self.clear_top:
            return None  # under the band: not drawn
        for line, laid, rect in self._all_placed():
            if not rect.top() <= pos.y() < rect.bottom():
                continue
            rows = ((row, QPointF(rect.x(), rect.y() + row.top)) for row in laid.rows)
            found = char_under(rows, pos)
            if found is not None:
                return (found[0].painted_from or line, *found)
            # else the next caption's, where they share a line pair (run-on)
        return None

    def shown_row(
        self, key: int, index: int, span: tuple[int, int] | None = None
    ) -> tuple[Line, LaidRow, QPointF] | None:
        """The drawn fragment of the row and span, with its top left."""
        for line, laid, rect in self._all_placed():
            if line.key == key:
                for row in laid.rows:
                    if row.index == index and (
                        span is None
                        or (
                            row.start < span[1]
                            and span[0] < row.start + len(row.row.text)
                        )
                    ):
                        return (
                            row.painted_from or line,
                            row,
                            QPointF(rect.x(), rect.y() + row.top),
                        )
        return None

    def row_of(self, key: int, clause: int, side: RowKind) -> LaidRow | None:
        """The drawn row of line `key` showing `clause` on `side`."""
        for line, laid, _ in self._all_placed():
            if line.key == key:
                for row in laid.rows:
                    if (row.row.clause, row.row.kind) == (clause, side):
                        return row
        return None

    def char_at(self, row: LaidRow, origin: QPointF, pos: QPointF) -> int:
        """The character of `row` nearest `pos` - a drag needn't stay on it."""
        layout = row.layout
        lines = [layout.lineAt(i) for i in range(layout.lineCount())]
        if not lines:
            return 0
        text_line = next(
            (li for li in lines if pos.y() < origin.y() + li.y() + li.height()),
            lines[-1],
        )
        index = text_line.xToCursor(
            pos.x() - origin.x(), QTextLine.CursorPosition.CursorOnCharacter
        )
        return min(row.source_index(index), row.start + max(0, len(row.row.text) - 1))

    def line_rect(self, row: LaidRow, origin: QPointF, start: int, end: int) -> QRectF:
        """The text lines of `row` that characters `[start, end)` are on,
        across the canvas: the row being read."""
        rects = row.rectangles(start, end)
        top = min((r.top() for r in rects), default=0.0)
        bottom = max((r.bottom() for r in rects), default=0.0)
        return QRectF(0, origin.y() + top, self.width(), bottom - top)

    def _under(self, lines: Sequence[tuple[Line, LaidLine, float]] = ()) -> float:
        """The one layout (340): how far under a line of text its word
        links' bars reach - and a new word's dots, links or not, in the
        `lines` drawn (polyglotic-hq 402) - so a line cut off at the top
        takes them with it: none are left over the first line that shows.
        0 in today's layouts."""
        style = self.engine.style
        if style.flow is None:
            return 0.0
        dots = max(
            (dots_below(row.layout) for _, laid, _ in lines for row in laid.rows),
            default=0.0,
        )
        under = dots + 1.0 if dots else 0.0
        if not style.link_room:
            return under
        return max(under, (style.link_gap + style.link_px) * self.view.text_size + 1.0)

    @staticmethod
    def _whole_pairs(
        shown: list[tuple[Line, LaidLine, float]], top: float, under: float
    ) -> float:
        """The one layout, line by line (340): `top` moved below a line
        whose other half - the line above it, in the other language - is
        cut off there, so a translation never shows without what was said.
        Captions that run on share lines, so the pairs are found across
        them: a caption's first line is the upper of a pair."""
        uppers: list[float] = []
        lowers: list[tuple[float, float]] = []
        for _, laid, y in shown:
            lines = [
                (y + row.top + row.layout.lineAt(n).y(), row)
                for row in laid.rows
                for n in range(row.layout.lineCount())
            ]
            if not lines:
                continue
            upper = min(lines, key=lambda item: item[0])[1].row.kind
            for at, row in lines:
                if row.row.kind is upper:
                    uppers.append(at)
                else:
                    lowers.append((at, row.layout.lineAt(0).height()))
        for at, height in sorted(lowers):
            if at < top - 0.01:
                continue
            above = max((u for u in uppers if u < at - 0.01), default=None)
            if above is not None and above < top - 0.01:
                top = max(top, at + height + under)
        return top

    @staticmethod
    def _clear_of_band(
        shown: list[tuple[Line, LaidLine, float]], under: float = 0.0
    ) -> float:
        """Where captions start while the hover band shows: below every
        label and row it would cut, so it covers whole rows - none peeks
        out half under it. `shown`: each line drawn, laid out, and its top."""
        return Canvas._clear_of(shown, band_height() + 1.0, under)

    @staticmethod
    def _clear_of(
        shown: list[tuple[Line, LaidLine, float]], edge: float, under: float = 0.0
    ) -> float:
        """Where captions start below `edge` - the band's foot, or the
        panel's top: below every label and row that starts above it, so
        only whole rows show. `shown`: each line drawn, laid out, and its
        top."""
        top = edge
        for n, (_, laid, y) in enumerate(shown):
            if y >= edge:
                break
            newest = n == len(shown) - 1
            if laid.label is not None and laid.rows:
                top = max(top, y + laid.rows[0].top)  # the label, and its gap
            for row in laid.rows:
                if y + row.top >= edge:
                    break
                if newest or laid.poured:
                    # the newest caption by its wrapped lines: a row taller
                    # than the window is never whole, and skipping it whole
                    # left a long sentence's window blank (polyglotic-hq 278)
                    # - and a poured caption always: its rows run on, so
                    # only its lines are whole or not (309)
                    top = max(
                        top,
                        Canvas._clear_of_lines(
                            row.layout, y + row.top, edge, under if laid.poured else 0.0
                        ),
                    )
                else:
                    top = max(top, y + row.top + row.layout.boundingRect().height())
        return top

    @staticmethod
    def _clear_of_lines(
        layout: QTextLayout, at: float, edge: float, under: float = 0.0
    ) -> float:
        """Below every wrapped line of a row at `at` that starts above `edge`
        - and `under` more: what is drawn under such a line."""
        top = edge
        for n in range(layout.lineCount()):
            line = layout.lineAt(n)
            if at + line.y() >= edge:
                break
            top = max(top, at + line.y() + line.height() + under)
        return top

    def _paint_band(self, painter: QPainter) -> None:
        """The hover band's panel, over the top of the captions - those it
        covers aren't drawn (`_clear_of_band`); the panel shows through."""
        color = QColor(self.owner.look.background)
        color.setAlphaF(BAND_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        left, right = self._sides()
        painter.drawRoundedRect(
            QRectF(1 - left, 1, self.width() - 2 + left + right, band_height()), 11, 11
        )

    def _paint_empty(self, painter: QPainter) -> None:
        """With nothing to read yet: "Waiting for audio…" ("Listening…" once
        speech is heard) and whose captions will appear - from the moment its
        app is chosen until its first captions (polyglotic-hq 272), in the
        window's own colour (`whose_captions`)."""
        look = self.owner.look
        waiting = QColor(readable_on(look.original, look.background, LABEL_CONTRAST))
        whose = QColor(waiting)
        whose.setAlphaF(0.75)
        font = QFont(self.font())
        font.setPixelSize(style.px(15))
        font.setWeight(QFont.Weight.DemiBold)
        small = QFont(self.font())
        small.setPixelSize(style.px(13))
        width = self.width() - 2 * PAD
        middle = self.height() / 2
        tall = QFontMetrics(font).height()
        painter.setPen(waiting)
        painter.setFont(font)
        painter.drawText(
            QRectF(PAD, middle - tall, width, tall),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            _tr("Listening…") if self.owner.mark_showing else _tr("Waiting for audio…"),
        )
        painter.setPen(whose)
        painter.setFont(small)
        painter.drawText(
            QRectF(PAD, middle + 2, width, tall),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            whose_captions(self.owner.source, self.owner.label.name),
        )

    def _paint_mark(self, painter: QPainter) -> QRect:
        """The listening mark under the newest caption, as the Lab says
        (`paint_loading`, 284). In the window's original colour."""
        scale = min(self.view.text_size, 1.6)
        thick = MARK_THICK * scale
        still = reduced_motion()
        lines = self.view.lines
        return paint_loading(
            painter,
            self.owner.look.lab.loading,
            QPointF(PAD + 3, self.height() - PAD / 2 - thick / 2 - 1),
            scale,
            QColor(self.owner.look.original),
            None if still else time.monotonic(),
            newest_live=bool(lines) and lines[-1].live,
        )

    def _locked_parts(self) -> tuple[QRectF, QRectF, QFont] | None:
        """Locked: where its corner's lock and hotkey go (the hotkey's
        empty without one) and the hotkey's font - the joined window's last
        column only; None otherwise."""
        owner = self.owner
        host = owner.host
        if not owner.locked or (host is not None and host.columns[-1:] != [owner]):
            return None
        font = QFont(self.font())
        font.setPixelSize(style.px(12))
        keys = owner.unlock_keys
        width = QFontMetrics(font).horizontalAdvance(keys) if keys else 0
        side = style.px(GLYPH_PX)
        gap = 4 if keys else 0
        right = self.width() - PAD
        middle = self.height() - PAD / 2
        lock = QRectF(right - width - gap - side, middle - side / 2, side, side)
        return lock, QRectF(right - width, middle - side, width, 2 * side), font

    def lock_spot(self) -> QRect | None:
        """Where resting the mouse offers Unlock: the corner's lock and
        hotkey, with room around them, out to the window's corner (398)."""
        parts = self._locked_parts()
        if parts is None:
            return None
        lock, keys, _ = parts
        spot = lock.united(keys) if keys.width() else QRectF(lock)
        spot.adjust(-LOCK_SPOT_AROUND, -LOCK_SPOT_AROUND, 0, 0)
        spot.setRight(self.width())
        spot.setBottom(self.height())
        return spot.toAlignedRect() & self.rect()

    def _paint_locked(self, painter: QPainter) -> None:
        """Locked: a lock and the hotkey that unlocks, faint, in the bottom
        right corner, in the padding under the captions (F10, 249) - the
        joined window's last column only."""
        parts = self._locked_parts()
        if parts is None:
            return
        lock, at, font = parts
        owner = self.owner
        color = QColor(owner.bar.text)
        color.setAlphaF(LOCKED_ALPHA)
        paint(painter, Glyph.LOCK, lock, color)
        keys = owner.unlock_keys
        if keys:
            painter.setPen(color)
            painter.setFont(font)
            painter.drawText(
                at, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, keys
            )


class ZoneCanvas(Canvas):
    """Steady's live zone (`views.zones`; polyglotic-hq 526, decision
    0251): the captions that haven't settled, run on as one paragraph -
    line by line, each line's translation under it - its last lines at the
    foot of the window, in full ink. The same view, layout engine, marks
    and hover as the canvas above it; its own style (`zone_look`)."""

    def __init__(self, window: "CaptionWindow", view: CaptionLines) -> None:
        super().__init__(window, view)
        self._made_for: tuple[object, ...] = ()
        self._line: tuple[object, float, float] | None = None
        self.lines_tall = 0.0
        """The height of the zone's own lines (`Zones.live_lines` of
        them): it is taller while a caption that began above them is
        still read (`CaptionWindow._place_zone`)."""

    def ready(self) -> None:
        """Its layout follows the window's: made again when that changes."""
        owner = self.owner
        stamp = (owner.canvas.engine, owner.look, owner.choices.translation_size)
        made = self._made_for
        if len(made) != 3 or any(a is not b for a, b in zip(stamp, made, strict=True)):
            self._made_for = stamp
            self.engine = owner._engine(
                owner.path_style(
                    caption_style(
                        zone_look(owner.look),
                        owner.choices.translation_size,
                        owner._mine_only(),
                    )
                )
            )
        self.ink = owner.canvas.ink
        self.marks = owner.marks

    def _lines(self) -> Sequence[Line]:
        return self.view.lines  # a caption's place follows from those before it

    def _all_placed(self) -> list[tuple[Line, LaidLine, QRectF]]:
        return self.placed

    def lines_in_view(self) -> Sequence[Line]:
        zones = self.owner.zones
        if zones is None:
            return ()
        return [line for line in self.view.lines if line.key not in zones.settled]

    def lines_shown(self, line: Line) -> int | None:
        return None

    def _view_height(self) -> float:
        return float(self.height())

    def _carries_on(self, before: Line, line: Line) -> bool:
        zones = self.owner.zones
        ended = zones is not None and before.key in zones.ended
        return not ended and runs_on(before, line)

    def walk(self) -> list[tuple[Line, LaidLine, float]]:
        """The live captions and where each is drawn, newest first: the
        newest's last line at the foot, the rest above it, as far as the
        zone's top."""
        self.ready()
        found = []
        foot = float(self.height())
        gap = self._gap()
        for line in reversed(self.lines_in_view()):
            top = foot - self._height(line)
            found.append((line, self._laid(line), top + self._above(line)))
            foot = top - gap
            if foot <= 0.0:
                break
        return found

    def needed(self) -> float:
        """How tall the zone's captions are together, each whole."""
        self.ready()
        lines = self.lines_in_view()
        if not lines:
            return 0.0
        return sum(self._height(line) for line in lines) + self._gap() * (
            len(lines) - 1
        )

    def whole_from(self, walked: list[tuple[Line, LaidLine, float]]) -> float:
        """Where the zone's text starts: below every line of text its top
        would cut through, and with whole pairs - a line and its
        translation - only. The paragraph's labels and gaps aren't a whole
        number of lines, so the zone's top seldom falls between two (the
        coordinator on 346's pictures, 2026-11-20: half a line showed at
        the divider)."""
        shown = walked[::-1]  # top to bottom, as `_clear_of` reads them
        under = self._under(shown)
        top = self._clear_of(shown, ZONE_TOP, under)
        # and no translation without what was said over it: the zone is
        # line by line, what was said the upper of each pair
        lines = sorted(
            (
                (y + row.top + row.layout.lineAt(n).y(), n, row)
                for _, laid, y in shown
                for row in laid.rows
                for n in range(row.layout.lineCount())
            ),
            key=lambda found: found[0],
        )
        if any(row.row.kind is RowKind.ORIGINAL for _, _, row in lines):
            for at, n, row in lines:
                foot = at + row.layout.lineAt(n).height()
                if foot <= top + 0.01:
                    continue  # above where the text starts
                if row.row.kind is RowKind.ORIGINAL:
                    break
                top = max(top, foot + under)
        return top

    def rolled_out(self) -> list[int]:
        """The live captions that have left the zone: every line of theirs
        is above where its text starts (and those older than the oldest
        one drawn)."""
        if self.height() <= 0:
            return []
        walked = self.walk()
        drawn = {line.key for line, _, _ in walked}
        grown = self.height() - self.lines_tall
        # grown to hold a whole caption: it has left when all of it is
        # above the zone's own lines; else where the text starts
        top = grown if grown > 0.5 else self.whole_from(walked)
        gone = [
            line.key
            for line, laid, y in walked
            if y + laid.height <= top + 0.5 and not line.live
        ]
        oldest = min(drawn, default=0)
        gone += [
            line.key
            for line in self.lines_in_view()
            if line.key not in drawn and line.key < oldest
        ]
        return gone

    def gap_after(self) -> float:
        """The gap under a caption's last line pair: to the next caption,
        which starts a line of its own (decision 0257) - the Lab's space
        between captions, or a clause's where that is wider (559: it was
        a clause's alone, a 66 line for a pitch of 68, and 32 short at the
        Lab's widest space between captions)."""
        style = self.engine.style
        return max(style.clause_gap, style.caption_gap) * self.view.text_size

    def line_height(self) -> float:
        """One line of the zone's paragraph - what was said, its reading
        and its translation - at the view's text size: the tallest laid
        out lately, else the last one known, else a guess from the style."""
        self.ready()
        tall = 0.0
        after = self.gap_after()
        for line in list(self.lines_in_view())[-3:]:
            # The pitch is kept as captions change. A temporary translation
            # slot can span several rows and would keep the zone too tall.
            laid = self.laid_at(line, self._width())
            ends = (0.0, *laid.breaks)
            tall = max([tall, *(b - a for a, b in pairwise(ends))])
            # a line pair from its top to the next one's: what was said, its
            # reading, its translation and the gap under them (the breaks
            # alone gave a pair less its gap: a zone 2.2 pairs tall)
            texts = sorted(
                (
                    (
                        row.top + row.layout.lineAt(n).y(),
                        row.layout.lineAt(n).height(),
                        row,
                    )
                    for row in laid.rows
                    for n in range(row.layout.lineCount())
                ),
                key=lambda found: found[0],
            )
            said = [at for at, _, row in texts if row.row.kind is RowKind.ORIGINAL]
            tops = said or [at for at, _, _ in texts]
            tall = max([tall, *(b - a for a, b in pairwise(tops))])
            if tops:
                foot = max(at + height for at, height, _ in texts)
                tall = max(tall, foot - tops[-1] + after)
        kept = self._line
        if (
            kept is not None
            and kept[0] is self.engine
            and kept[1] == self.view.text_size
        ):
            tall = max(tall, kept[2])  # never shorter while it reads: nothing jumps
        if tall > 0.0:
            self._line = (self.engine, self.view.text_size, tall)
            return tall
        style = self.engine.style
        text = self.view.text_size
        trans = style.translation_size if style.translation_size is not None else text
        rows = text + trans + (0.5 * text if style.reading_lines else 0.0)
        return style.text_px * 1.4 * rows

    def paintEvent(self, event: QPaintEvent) -> None:
        with spans.span("caption_window.paint_zone"):
            owner = self.owner
            main = owner.canvas
            self.hovered, self.selection = main.hovered, main.selection
            self.said_now = main.said_now
            walked = self.walk()
            chosen = owner.held.selection
            self._held = (
                held_words([ln for ln, _, _ in walked], chosen) if chosen else {}
            )
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.fillRect(  # where the transcript above ends
                QRectF(PAD, 0.0, self.width() - 2.0 * PAD, 1.0), shade(owner.bar, 38)
            )
            top = self.clear_top = self.whole_from(walked)
            painter.setClipRect(QRectF(0.0, top, self.width(), self.height() - top))
            now = owner.clock()
            self.placed = []
            for line, laid, y in walked:
                at = QPointF(PAD, y)
                ink = self.ink
                correction = owner.correction_colour(line.key, now, ink.original)
                if correction is not None:
                    ink = replace(ink, correction=correction)
                if line.live and owner.faint_ahead:  # karaoke's waiting words
                    ink = replace(ink, live_alpha=AHEAD_ALPHA)
                self._paint_marked(painter, line, laid, at)
                self.engine.paint(painter, line, laid, at, ink, self.marks)
                self.placed.append(
                    (line, laid, QRectF(PAD, y, self._width(), laid.height))
                )
            painter.end()
            self.shown = len(walked)
            self._drawn_revision = self.view.revision


def linked_with(line: Line, marked: Marked) -> list[tuple[Marked, int]]:
    """The word links touching `marked`: each linked word, on its row and
    the other row of its clause, with its link's number."""
    if marked.row >= len(line.rows):
        return []
    row = line.rows[marked.row]
    numbers = {
        w.link for w in row.links if w.start < marked.end and marked.start < w.end
    }
    if not numbers:
        return []
    return [
        (Marked(marked.key, index, w.start, w.end), w.link)
        for index, other in enumerate(line.rows)
        if other.clause == row.clause
        for w in other.links
        if w.link in numbers
    ]


def language_chip_label(spoken: str | None, target: Language | None) -> str:
    """The bar's language chip (465): what its app speaks - Detect, or
    the language named - and what it's translated into."""
    #: Short, on a caption window's bar: the language heard (or "Detect")
    #: and the one its captions are translated into
    return _tr("{spoken} → {translation}").format(
        spoken=spoken_name(spoken) if spoken else _tr("Detect"),
        translation=language_name(str(target)) if target else _tr("Original only"),
    )


def chip_text(spoken: str | None, target: Language | None, open_: bool = False) -> str:
    return dropdown_label(language_chip_label(spoken, target) + " ", open_)


def dropdown_label(label: str, open_: bool) -> str:
    label = style.button_text(label)
    return f"{label} {'▴' if open_ else '▾'}"


STRIP_GAP_PX = 3
"""Pixels between adjacent strip items, at least 0. Matches the button gaps."""
SHORT_SOURCE_PX = 40
"""Source-name text to keep before changing tier, at 100% text size.
From 0 px (dot alone) to the natural name width. Leaves a readable prefix."""
SHORT_PRESET_PX = 44
"""Maximum short preset text width, in px at 100% text size.
At least enough for an ellipsis. Leaves space for timing's full label."""


class StripLabels(StrEnum):
    FULL = "full"
    SHORT = "short"
    ICONS = "icons"


class SourceTag(QWidget):
    """The source's dot and name, quiet-view theme and mic mark.

    The name shortens first, then only the dot and mic mark fit.
    """

    NOTE_MIN = 40
    """The label is shortened to no less than this before the note goes."""
    DOT_WIDTH = 14
    """Pixels for the 8 px dot and its inset, at least 10 px so it fits."""
    END_PAD = 4
    """Pixels after the source tag's content, at least 0."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.label = SourceLabel("", ACCENT)
        self.mic = False
        self.note = ""
        self.dot_only = False
        self.ink = bar_ink(CaptionLook().background)
        """Its words' colours, on its window's panel."""
        self._font = style.ui_font()
        self._font.setWeight(QFont.Weight.DemiBold)
        self._note_font = style.ui_font()
        self.restyle()

    def restyle(self) -> None:
        """Its fonts at the text size now."""
        self._font.setPixelSize(style.px(12))
        self._note_font.setPixelSize(style.px(12))  # never under 12 px (the UI lab)
        self.updateGeometry()
        self.update()

    def show_label(self, label: SourceLabel, mic: bool, note: str = "") -> None:
        if (label, mic, note) == (self.label, self.mic, self.note):
            return
        self.label, self.mic, self.note = label, mic, note
        self.setToolTip(f"{label.name} - {note}" if note else label.name)
        self.setAccessibleName(label.name)
        self.updateGeometry()
        self.update()

    def show_dot(self, dot_only: bool) -> None:
        if self.dot_only != dot_only:
            self.dot_only = dot_only
            self.updateGeometry()
            self.update()

    @property
    def dot_width(self) -> int:
        return self.DOT_WIDTH + self.END_PAD

    @property
    def name_width(self) -> int:
        return QFontMetrics(self._font).horizontalAdvance(self.label.name)

    @property
    def mic_width(self) -> int:
        return style.px(18) if self.mic else 0

    def short_width(self) -> int:
        return self.icon_width() + min(self.name_width, style.px(SHORT_SOURCE_PX))

    def icon_width(self) -> int:
        return self.dot_width + self.mic_width

    def tip_at(self, at: QPoint) -> str:
        """What its hover label says at `at`: on the mic mark, that my speech
        is shown here (polyglotic-hq 395); elsewhere the source's label."""
        if self.mic and at.x() >= self.width() - self.mic_width:
            return _tr(
                "Your speech is shown here: your microphone is sent for your "
                "captions only while this is on"
            )
        return self.toolTip()

    def _note_width(self) -> int:
        if not self.note:
            return 0
        return 10 + QFontMetrics(self._note_font).horizontalAdvance(self.note)

    def sizeHint(self) -> QSize:
        width = self.icon_width()
        if not self.dot_only:
            width += self.name_width + self._note_width()
        return QSize(width, style.px(22))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.label.color))
        painter.drawEllipse(QRectF(2, self.height() / 2 - 4, 8, 8))
        if self.dot_only and not self.mic:
            painter.end()
            return
        mic = self.mic_width
        room = self.width() - self.dot_width - mic
        note = 0 if self.dot_only else self._note_width()
        metrics = QFontMetrics(self._font)
        if note and room - note < min(
            self.NOTE_MIN, metrics.horizontalAdvance(self.label.name)
        ):
            note = 0  # too narrow for both: the label alone
        painter.setPen(QColor(self.ink.text))
        painter.setFont(self._font)
        name = metrics.elidedText(
            "" if self.dot_only else self.label.name,
            Qt.TextElideMode.ElideRight,
            room - note,
        )
        painter.drawText(
            QRectF(self.DOT_WIDTH, 0, room - note, self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            name,
        )
        if note:
            painter.setPen(QColor(self.ink.dim))
            painter.setFont(self._note_font)
            painter.drawText(
                QRectF(
                    self.DOT_WIDTH + metrics.horizontalAdvance(name) + 10,
                    0,
                    note,
                    self.height(),
                ),
                Qt.AlignmentFlag.AlignVCenter,
                self.note,
            )
        if self.mic:
            side = style.px(MIC_PX)
            area = QRectF(self.width() - mic, 0, mic - 2, self.height())
            box = QRectF(0, 0, side, side)
            box.moveCenter(area.center())
            paint(painter, Glyph.MIC, box, QColor(self.ink.accent))
        painter.end()


def notice_style() -> str:
    """The notice line's look, at the text size now."""
    return (
        f"background: rgba(25,29,36,0.92); color: {TEXT}; border: 1px solid #262b34;"
        f" border-radius: 9px; padding: 2px 12px; font-size: {style.px(12)}px;"
    )


def laid_width(widget: QWidget) -> int:
    """How wide the strip's layout makes `widget`: its size hint, or its
    least width where that's more (`fit_glyph`'s buttons: 10 px more at
    100 %, so the strip's sums came short - polyglotic-hq 593)."""
    return max(widget.sizeHint().width(), widget.minimumWidth())


def fit_glyph(button: QToolButton, side: int) -> None:
    """`button`'s icon `side` pixels square, the button as wide as Windows'
    icon font made it (its words' size, `px(12)`), so the band keeps its
    layout."""
    button.setIconSize(QSize(side, side))
    button.setMinimumWidth(0)
    margins = button.sizeHint().width() - side
    button.setMinimumWidth(margins + text_width(style.px(12)))


BAR_CONTRAST = 4.5
"""The top bar's words and icons against the panel's colour at least: WCAG's
4.5:1 for text, so its icons clear 1.4.11's 3:1 with room for the game
showing through a panel that isn't quite solid (polyglotic-hq 272: white
icons on Paper's cream were 1.05:1, "impossible to see")."""


@dataclass(frozen=True, slots=True)
class BarInk:
    """The colours of a window's own chrome on its panel - the top bar's
    words and icons, the hover behind its buttons and the locked corner -
    following the panel's colour (`bar_ink`)."""

    text: str
    dim: str
    disabled: str
    accent: str
    shade: str
    """"r,g,b" of what lightens or darkens a button under the mouse:
    white on a dark panel, black on a light one."""


@lru_cache(maxsize=64)  # read on every paint: a panel colour or two (355)
def bar_ink(background: str) -> BarInk:
    """The chrome's colours on a panel of `background` ("#rrggbb"): the
    usual light ones on a dark panel, darkened until readable on a light
    one."""
    light = contrast("#000000", background) > contrast("#ffffff", background)
    return BarInk(
        text=readable_on(TEXT, background, BAR_CONTRAST),
        dim=readable_on(TEXT_DIM, background, BAR_CONTRAST),
        disabled=readable_on(TEXT_DIM, background, 3.0),
        accent=readable_on(ACCENT, background, 3.0),
        shade="0,0,0" if light else "255,255,255",
    )


class MicButton(QToolButton):
    """The bar's own-speech switch: lit with a live level meter while on,
    dim with a slash while off."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("caption_window.band.mic")
        self.setProperty("mic", True)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.level: float | None = None
        self._side = style.px(GLYPH_PX)
        self._pad = style.px(4)
        self._gap = style.px(2)
        self._track = style.px(MIC_METER_WIDTH.value)
        self._width = self._pad * 2 + self._side + self._gap + self._track

    def set_ink(self, ink: BarInk, side: int) -> None:
        self._side = side
        self._pad = style.px(4)
        self._gap = style.px(2)
        self._track = style.px(MIC_METER_WIDTH.value)
        self._width = self._pad * 2 + side + self._gap + self._track
        self.setFixedWidth(self._width)
        self._on = icon(Glyph.MIC, ink.accent, side)
        self._off = icon(Glyph.MIC_OFF, ink.dim, side)
        self._accent = QColor(ink.accent)
        self._dim = QColor(ink.disabled)
        self._track_idle = QColor(ink.disabled)
        self._track_idle.setAlphaF(0.35)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._width, super().sizeHint().height())

    def show_level(self, level: float | None) -> None:
        shown = level if self.isChecked() else None
        if shown != self.level:
            self.level = shown
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        top = (self.height() - self._side) // 2
        if self.isChecked():
            left = self._pad
            self._on.paint(painter, QRect(left, top, self._side, self._side))
            meter_x = left + self._side + self._gap
            speaking = self.level is not None and self.level > 0.0
            painter.fillRect(
                meter_x,
                top,
                self._track,
                self._side,
                self._dim if speaking else self._track_idle,
            )
            if speaking and self.level is not None:
                fill = max(1, round(self.level * self._side))
                painter.fillRect(
                    meter_x, top + self._side - fill, self._track, fill, self._accent
                )
        else:
            left = (self.width() - self._side) // 2
            self._off.paint(painter, QRect(left, top, self._side, self._side))
        painter.end()


def shade(ink: BarInk, alpha: int) -> QColor:
    """What lightens or darkens on the panel at `alpha` (0-255): white on a
    dark panel, black on a light one (`BarInk.shade`) - a hovered word, the
    hovered window's edge, a joined window's dividers."""
    red, green, blue = (int(c) for c in ink.shade.split(","))
    return QColor(red, green, blue, alpha)


def draw_panel(
    painter: QPainter,
    area: QRectF,
    color: QColor,
    edge: QColor | None,
    divider: QColor | None,
) -> None:
    """A caption window's panel over `area` (a joined window's column's
    runs on past its inner sides): a rounded rectangle in `color`, with a 1
    px `edge` if one, and a 1 px `divider` down the window's own left side
    from the column before, if one."""
    painter.setBrush(color)
    painter.setPen(QPen(edge, 1) if edge is not None else Qt.PenStyle.NoPen)
    painter.drawRoundedRect(area.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
    if divider is not None:
        painter.setPen(QPen(divider, 1))
        painter.drawLine(QPointF(0.5, area.top() + 1), QPointF(0.5, area.bottom() - 1))


def copies_exactly(painter: QPainter) -> bool:
    """Whether a picture copied with `painter` lands pixel for pixel: Qt's
    own raster drawing, at the screen's scale alone and moved by whole
    pixels - a window's own paint. A window drawn smaller (the UI lab's
    screen of windows: the scale is in the device's transform, not the
    painter's own) or a painter recording what's drawn rather than
    drawing it gets the drawing itself."""
    engine = painter.paintEngine()
    if engine is None or engine.type() is not QPaintEngine.Type.Raster:
        return False
    ratio = painter.device().devicePixelRatioF()
    to_device = painter.deviceTransform()
    return (
        to_device.type() in UNTURNED
        and to_device.m11() == ratio
        and to_device.m22() == ratio
        and to_device.dx() == round(to_device.dx())
        and to_device.dy() == round(to_device.dy())
    )


UNTURNED = (
    QTransform.TransformationType.TxNone,
    QTransform.TransformationType.TxTranslate,
    QTransform.TransformationType.TxScale,
)


def panel_picture(
    size: QSize,
    ratio: float,
    area: QRectF,
    color: QColor,
    edge: QColor | None,
    divider: QColor | None,
) -> QPixmap:
    """The panel (`draw_panel`) drawn once into a transparent picture
    `size` wide and high at the screen's scale `ratio`: copied onto a
    window painted at that scale, the same pixels as drawn there."""
    picture = QPixmap(math.ceil(size.width() * ratio), math.ceil(size.height() * ratio))
    picture.setDevicePixelRatio(ratio)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_panel(painter, area, color, edge, divider)
    painter.end()
    return picture


def band_style(ink: BarInk | None = None) -> str:
    """The hover band's buttons' look, at the text size now, in `ink` (the
    default panel's if None)."""
    ink = ink or bar_ink(CaptionLook().background)
    shade = ink.shade
    return f"""
QToolButton {{ background: transparent; color: {ink.text}; border: 1px solid transparent;
  border-radius: {MARK_RADIUS}px; padding: 0 6px; font-size: {style.px(12)}px;
  min-height: {style.px(20)}px; }}
QToolButton:hover {{ background: rgba({shade},0.16); }}
QToolButton:checked {{ background: rgba({shade},0.24); }}
QToolButton[mic="true"]:checked {{ background: rgba({shade},0.12); }}
QToolButton[mic="true"]:checked:hover {{ background: rgba({shade},0.20); }}
QToolButton:checked:disabled {{ background: rgba({shade},0.08); }}
QToolButton[chip="true"] {{ border: 1px solid rgba({shade},0.35); }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
"""


CARDS_KEPT_MOST = 3
GLIDE_MOST = 3.0
"""The most the card stack is ever drawn below its place, in cards: what
comes faster than that is caught up with at once."""
HOME_CARDS_MOST = 6
"""Back to live slides past this many cards at most, at the glide's own
pace (`GLIDE_FASTEST`): from further back it starts this far from home."""
VEIL_SEC = 0.3
"""Back to live from further than it slides: the view fades out and in,
this long in all."""
COVER_FADE_SEC = 0.3
"""A card that something at the top of the window comes to cover (the
toolbar, a question) fades out over this long, and back in after."""


def card_bar_style() -> str:
    return (
        f"QScrollBar:vertical {{ background: transparent; width: {CARD_BAR_PX.value}px; margin: 0; }}"
        "QScrollBar::handle:vertical { background: rgba(255,255,255,0.30);"
        " border-radius: 3px; min-height: 24px; }"
        "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.55); }"
        "QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page,"
        " QScrollBar::sub-page { background: transparent; height: 0; }"
    )


def pill_style() -> str:
    """Back to live's look, at the text size now."""
    return (
        f"QPushButton {{ background: {ACCENT}; color: {ACCENT_TEXT}; border: none;"
        f" border-radius: 9px; padding: 3px 14px; font-size: {style.px(12)}px;"
        " font-weight: 600; }"
    )


class CaptionWindow(QWidget):
    """One app's caption window. `choices` are what it remembers; `look`,
    the timing, second languages, labels, paused, the notice and the
    listening mark are the session's, set by `CaptionWindows`."""

    changed = Signal()
    """Its choices changed (place, text size, mode, language, my speech)."""
    language_changed = Signal()
    mic_changed = Signal()
    lock_wanted = Signal()
    unlock_wanted = Signal()
    """Its Unlock, shown while locked when the mouse rests on its lock
    (`unlock_spot`, polyglotic-hq 398): every window unlocks."""
    hide_wanted = Signal()
    stop_wanted = Signal()
    report_wanted = Signal()
    """An alpha tester's "Report a problem" (polyglotic-hq 275)."""
    """Close: stop captioning this app (= untick it)."""
    transcript_wanted = Signal()
    all_settings_wanted = Signal()
    """All caption settings...: Settings > Captions in the main window."""
    links_wanted = Signal(bool, tuple)
    """The strip's word links button: on or off, for every window (F9) -
    the whole learning view, with the reading lines of this window's
    languages (`readings`; 446)."""
    quiet_wanted = Signal(bool, tuple)
    """The strip's quiet view button: on or off, for every window, with the
    reading lines of this window's languages (`readings`; 477)."""
    quiet_word_wanted = Signal(str, bool)
    """The settings popover's chosen words for the quiet view: one of them
    (`ChosenWords`' value) ticked or not, for every window (477)."""
    fill_wanted = Signal(bool)
    """The strip's filled lines button: on or off, for every window (372)."""
    aligned_wanted = Signal(bool)
    """The strip's parts lined up button: on or off, for every window (372)."""
    said_colours_wanted = Signal(bool)
    """The popover's "Colour linked words in what was said": on or off, for
    every window (431)."""
    translation_colours_wanted = Signal(bool)
    """The popover's "Colour linked words in the translation" (431)."""
    timing_wanted = Signal(str)
    path_wanted = Signal(str)
    """The translation's timing picked on the timing chip - a
    `ReadingPath`'s value (Learning's after or with: polyglotic-hq 593)."""
    join_wanted = Signal()
    """Join windows: every caption window into one, a column each (109's 2a)."""
    app_wanted = Signal(str)
    """An app's name, from its settings: caption it here instead (F12, 249)."""
    spoken_declined = Signal(str)
    """Not now, to always hearing its app as a language (its code): never
    asked again for this window (317)."""
    spoken_unanswered = Signal(str)
    """The question about a language (its code) went by itself, unanswered:
    not asked again until the app starts again (350)."""
    second_wanted = Signal(str, str)
    """Its settings' "When they already speak ...": a translation language
    and the language its lines already in it are shown in ("": left as they
    are) - by translation language, so for every window with it (263)."""
    start_like_this_wanted = Signal(bool)
    """Its languages' "Start new windows like this", on or off (465)."""
    lyrics_wanted = Signal(bool)
    """A music player's "Lyrics" switch, on or off: songs mode for every
    music player heard on Detect (polyglotic-hq 595, decision 0287)."""
    ask_set_up_wanted = Signal(bool)
    """Its languages' "Ask when a window opens", on or off: the set-up
    again on every window that opens, or never (478)."""
    set_up_done = Signal(bool)
    """Its set-up went: Start captions, or its first caption came (465) -
    with "Use as my default" chosen in it, or not (478)."""
    # the bar's preset dropdown (polyglotic-hq 556, `preset_popover`)
    preset_wanted = Signal(str)
    """A preset picked (its key: "video", "own1")."""
    lines_wanted = Signal(str)
    """The dropdown's Show: a `Show`'s value - both, original, translation."""
    video_lines_wanted = Signal(int)
    readings_wanted = Signal(bool, tuple)
    """Its Readings, on or off, with this window's languages' (`readings`)."""
    """Its My speech: in every window, or in none."""
    customise_wanted = Signal()
    """Customise presets…: Settings > Presets."""
    preset_step = Signal(str)
    """A step on the chosen preset (polyglotic-hq 587): "save", "save_as",
    "discard", "restore", "rename", "delete" - from its dropdown - or
    "undo", from the notice line's Undo."""

    def __init__(
        self,
        key: str,
        source: SourceId,
        choices: WindowChoices,
        label: SourceLabel,
        look: CaptionLook | None = None,
        index: int = 0,
        mic: SourceId | None = None,
        areas: Callable[[], list[Rect]] = work_areas,
        keys: KeyState | None = None,
        learner: Learner | None = None,
        card: LookupCard | None = None,
    ) -> None:
        """`keys`: whether Esc or a mouse button is held anywhere (from
        `platform`, by way of `main`), for closing the settings popover;
        `learner`: the learning tools (highlights, the words under the
        mouse); `card`: the lookup card every window shares."""
        super().__init__(None, WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # on a Mac a tool window hides while the app isn't active - and the
        # app is never active while the learner is in another (polyglotic-hq 429)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setObjectName(f"caption_window.{index}")
        self.setFont(style.ui_font())  # its own words, painted or not
        self.setMouseTracking(True)
        self.key, self.source, self.index = key, source, index
        self.choices = choices
        self._wheel_zoom_ratio: float | None = None
        """Keep the ratio through successive steps, which save whole percentages."""
        self.label = label
        self._batching_settings = False
        self.look = look or CaptionLook()
        self.mic = mic
        self.timing = CaptionMode.WHOLE
        self.second_languages: Mapping[Language, Language] = {}
        self.spoken_fallback = False
        """Its spoken language can't be used as it is: the server takes one
        for every window (one from before 2026-11-09), and another window
        names a different one - so its app is heard as Detect (263)."""
        self.music_player = False
        """Its app is a known music player (`CaptionWindows.music_player`):
        its settings offer the Lyrics switch while it hears Detect (595)."""
        self.labels = Labels()
        self.windows = 1  # caption windows there are (for Join windows)
        self.host: JoinedWindow | None = None
        """The joined window it's a column of, or None: a window of its own."""
        self.locked = False
        self.reporting = False
        """Whether the strip offers "Report a problem" (an alpha tester's, 275)."""
        self.unlock_keys = "Ctrl+Alt+L"
        """The hotkey that unlocks, as it is now ("" if another app has it):
        said on locking (`set_locked`), and faintly while locked."""
        self.app_choices: Callable[[], list[AppChoice]] = list
        """The apps this window can caption instead (`views.app_choices`):
        none for a window that isn't one app's (everything, the mic)."""
        self.recent_spoken: Callable[[], tuple[str, ...]] = tuple
        """The spoken languages the learner named last, newest first
        (`CaptionWindows.recent_spoken`): first in its settings' list."""
        self.hovered = False  # the mouse over it, unlocked
        self.band_shown = False
        self.always_shown = False  # never fades, nothing slides (the lab)
        self.clock: Callable[[], float] = time.perf_counter
        """The arrivals' clock (the lab steps it to photograph frames).
        On Windows / Python 3.12, monotonic() advances in 15.625-ms ticks:
        successive paints could get the same position and then a double step."""
        self.motion = Motion()
        """Arrivals sliding into place (step and slide)."""
        self._slid = False
        """Something slid at the last frame: the next paints it at rest."""
        self._corrections: dict[int, tuple[object, float]] = {}
        """Lines showing a quiet correction (decision 0228): what it
        recolours and since when (`clock`)."""
        self._corrected = False
        """A correction showed at the last frame: the next paints it gone."""
        self._known: set[int] | None = None
        """The captions' keys it has shown (None: none yet - the first
        captions a window opens with don't arrive, they're there)."""
        self._last_caption_at: float | None = None
        """When the last new caption arrived (`clock`): the speech's pace."""
        self._arrived: dict[int, float | None] | None = None
        """When each caption in view arrived as text (`clock`), by its key -
        a preview line from when it became its finished caption; None for
        the ones it opened with. How new each is (the Lab's New for)."""
        self._newness_drawn: tuple[tuple[int, float], ...] = ()
        self.listening = False  # speech heard, its caption not here yet
        self.speaking = False
        """Speech under way now (the session's listening mark): an arrival
        while it is slides quicker - the next caption is on its way."""
        self.notices = Notices()
        self._areas = areas
        self.keys = keys
        self.learner = learner
        self.card = card
        self._selecting: _Selecting | None = None
        self.popover: SettingsPopover | None = None
        self.bar_controls: SettingsPopover | None = None
        self.languages: SettingsPopover | None = None
        self.presets: PresetPopover | None = None
        """The bar's preset dropdown (polyglotic-hq 556), made when first opened."""
        self.timings: TimingPopover | None = None
        """The bar's timing dropdown (polyglotic-hq 593), made when first opened."""
        self.respeaking = False
        self._respeak_key = ""
        self._respeak_hold_only = False
        """Re-speaking is on (`settings.respeaking`): its bar shows the
        microphone light, unless it captions the mic (593)."""
        self.preset_menu = PresetMenu()
        """The presets as `main` last said (`set_presets`)."""
        """What the bar's language chip opens (465; made when first opened)."""
        self.set_up: CaptionSetUp | None = None
        """The first window's set-up while it's asked (465)."""
        self.resize_hint: PanelResizeCursor | None = None
        self._drag: _Drag | None = None
        self._seen = -1  # the newest line's key when last following
        self._alpha = 1.0
        self._last_activity = 0.0
        self._intro_until: float | None = None
        """When its first seconds end (`introduce`); None once over."""
        self._last_tick = time.monotonic()
        self.pointer: Callable[[], QPoint] = QCursor.pos
        """Where the mouse is on the screen (a test's own)."""
        self.unlock_spot = UnlockSpot(
            self,
            self._lock_spot,
            lambda: self.pointer(),
            self.unlock_wanted.emit,
            pill_style,
            WINDOW_FLAGS,
        )
        """Locked, the mouse resting on its lock shows Unlock there (398)."""
        self.pointed = False
        """The mouse rests on it while it's faded, or shown for that."""
        self.pacing = Pacing()
        """Captions arriving together, let in the Lab's gap apart (284)."""
        self.reveal = Reveal()
        """A new caption's lines still to show, one at a time (the Lab's
        Gap between new lines, 309)."""
        self._revealed: set[int] | None = None
        """The captions the reveal has been told of (None: none yet - the
        ones the window opens with are there)."""
        self._reveal_timer = QTimer(self, singleShot=True)
        self._reveal_timer.timeout.connect(self._show_next_line)
        self.longest_wait = MAX_WAIT_FOR_TEXT_SEC
        """The longest wait for text (decision 0068; `CaptionWindows`'): no
        caption waits longer than this for the gap."""
        self._pace_timer = QTimer(self, singleShot=True)
        self._pace_timer.timeout.connect(self._let_paced)
        self._holding = False
        self._hold_timer = QTimer(self, singleShot=True)
        self._hold_timer.timeout.connect(self._resume_hover)
        self._resume_through: int | None = None
        self._resume_timer = QTimer(self, singleShot=True)
        self._resume_timer.timeout.connect(self._show_resumed_lines)
        self._view_held: int | None = None
        """The mouse on the words, with cards: the newest card shown then -
        the view stops there, the cards after it are dealt past the view
        and Back to live counts them (583)."""
        self._mouse_anchor: Anchor | None = None
        """The same without cards: the scroll held where the view stood."""
        self._pointed_looks = 0
        self.setWindowTitle(_tr("{app} captions").format(app=label.name))

        self._video_enabled = False
        view = CaptionLines(
            self._sources(),
            choices.target,
            keep=CAPTION_WINDOW_LINES,
            second=self._second(),
            options=self._options(),
            cuts=self.look.lab.fill is Fill.PAIRED,
            yours=(mic,) if mic else (),
            text_size=choices.text_size,
            sizes=CAPTION_TEXT_SIZES,
        )
        self.sentence_card: SentenceCard | None = None
        """Offers a selection to save as a sentence (polyglotic-hq 459):
        made the first time one is."""
        self.say_it: SelectionReading | None = None
        """Reads a selection aloud from its card (polyglotic-hq 495):
        `main`'s, by way of `CaptionWindows.use_say_it`."""
        self.held = HeldSelection(
            self,
            lambda: shown(self.view.lines),
            keys,
            lambda: self.card is not None and self.card.pinned,
            self._held_changed,
        )
        """What's selected across its captions, and kept (358)."""
        self.zones: Zones | None = None
        """Steady's two zones (`views.zones`), while the window shows its
        captions that way: a paced mode, with `two_zones` on."""
        self.two_zones = True
        """Whether a paced mode shows two zones here (the learner's)."""
        self.path = ReadingPath.BOTH
        """What is read first here in a paced mode (decision 0253)."""
        self.faint_ahead = False
        """Karaoke: a live caption's words past what is established are
        the words waiting for their moment, drawn faint (`AHEAD_ALPHA`)."""
        self.canvas = Canvas(self, view)
        self._readings = reading_lines.sources(learner) if learner else None
        """Where its rows' reading lines come from (369): every word's, or
        only those past what the learner knows."""
        self.canvas.engine = self._engine(
            caption_style(self.look, choices.translation_size, self._mine_only())
        )
        self.canvas.ink = self._ink()
        self.zone = ZoneCanvas(self, view)
        self.zone.hide()
        self.cards_on = True
        """Whether a paced mode shows the card stack here (decision 0260;
        the learner's `steady_cards`)."""
        self.deck: Deck | None = None
        """The cards the captions are dealt onto, while they are
        (`views.cards`); None: captions as they come."""
        self.glide = Glide()
        self._card_limit: int | None = None
        self._reading_hold: float | None = None
        """At most how long a new card is held while the card it would
        take out of reading isn't read (`views.dwell`; None: off - a new
        card waits only `CARD_WAIT_SEC` for the line before it)."""
        self._reading: dict[int, Reading] = {}
        """The newest cards as shown: when, and what (`views.dwell`)."""
        self.card_split: Callable[[str], Sequence[tuple[int, int]]] = each_character
        """A run of Chinese as words (the learner's dictionary's split)."""
        """Subtitles: only this many of the newest cards are drawn."""
        self._dealt: dict[CaptionId, CaptionUpdate] = {}
        """Each caption's latest update shown, to deal again at another
        width or text size - the newest `CAPTION_WINDOW_LINES`."""
        self._dealt_at: dict[CaptionId, tuple[float, float]] = {}
        """When each of them first came, and last."""
        self._dealt_for: tuple[object, ...] = ()
        self._deals = 0
        self._old_deck: Deck | None = None
        """The deck put away at the last change of mode: its cards are
        still shown, as they stood."""
        self._kept_back: dict[CaptionId, CaptionUpdate] = {}
        """New cards kept back a moment: the line before them is still new
        (`_deal`, `check_card_room`)."""
        self._kept_until = 0.0
        self._card_since = 0.0
        self._translated_at = -1e9
        self._pending_since: float | None = None
        self._lag: dict[int, float] = {}
        """The cards that came while the stack had yet to rise for them:
        each stands in its place and the stack glides up from under it -
        a new line never rides the glide (`card_offset`)."""
        self._held_rows: dict[tuple[int, int], float] | None = None
        self._veil_at: float | None = None
        self._veil = QTimer(self)
        self._veil.setSingleShot(True)
        self._veil.setTimerType(Qt.TimerType.PreciseTimer)
        self._veil.timeout.connect(self._come_home)
        self._dwell = QTimer(self)
        self._dwell.setSingleShot(True)
        self._dwell.timeout.connect(self.check_card_room)
        self._bare_heights: dict[int, float | None] = {}
        """Source height while awaiting a translation. None for a card that
        needs no translation in the current language, even after it scrolls away."""
        self._translation_slots: dict[int, _TranslationSlot] = {}
        self._translation_expiry = QTimer(self, singleShot=True)
        self._translation_expiry.setTimerType(Qt.TimerType.PreciseTimer)
        self._translation_expiry.timeout.connect(self._close_translation_gaps)
        self._translation_row_height = 0.0
        self._slot_for: tuple[object, ...] = ()
        self._plain_tall = 0.0
        self._zone_pause = QTimer(self)
        self._zone_pause.setSingleShot(True)
        self._zone_pause.setInterval(int(PAUSE_SEC * 1000))
        self._zone_pause.timeout.connect(self._zone_paused)
        self.marks = CaptionMarks(learner)
        self.marks.set_look(
            self.look.word_links, self.look.introductions, marks_panel(self.look)
        )
        self.canvas.marks = self.marks
        self._build_controls()
        self._build_band()
        self.pill = QPushButton(self)
        self.pill.setObjectName("caption_window.back_to_live")
        self.pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pill.setStyleSheet(pill_style())
        self.pill.clicked.connect(self.go_live)
        self.pill.setToolTip(live_tip(""))
        self.pill.hide()
        self.scroll_bar = QScrollBar(Qt.Orientation.Vertical, self)
        """The cards' scroll bar, in cards (decision 0260): shown once
        there are more than the window holds."""
        self.scroll_bar.setObjectName("caption_window.scrollbar")
        self.scroll_bar.setCursor(Qt.CursorShape.ArrowCursor)
        self.scroll_bar.setStyleSheet(card_bar_style())
        self.scroll_bar.valueChanged.connect(self._bar_moved)
        self.scroll_bar.installEventFilter(self)
        self.scroll_bar.hide()
        self._bar_syncing = False
        self.notice = QLabel(self)
        self.notice.setObjectName("caption_window.notice")
        self.notice.setStyleSheet(notice_style())
        self.notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.notice.hide()
        self._notice_foot = 0.0
        """Where the captions were last told to start, under the notice."""
        self.nudge: SpokenNudge | None = None
        """Once Detect has heard one language steadily: "Always hear it as
        ...?" (`suggest_spoken`; made when first asked)."""

        self._band_in = QTimer(self, singleShot=True, interval=BAND_IN_MS)
        self._band_in.timeout.connect(lambda: self._show_band(True))
        self._band_out = QTimer(self, singleShot=True, interval=BAND_OUT_MS)
        self._band_out.timeout.connect(self._band_left)
        self._still_over = QTimer(self, interval=STILL_OVER_MS)
        self._still_over.timeout.connect(self._check_still_over)
        # the fade, the notice and the listening mark: a frame timer while any
        # of them moves, stopped when nothing does; woken when one is due
        self._tick_timer = QTimer(self, interval=FRAME_MS)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.timeout.connect(self._tick)
        self._wake_timer = QTimer(self, singleShot=True)
        self._wake_timer.timeout.connect(self._wake)
        self._point_timer = QTimer(self, interval=POINT_POLL_MS)
        self._point_timer.timeout.connect(self._look_for_pointer)

        self.setGeometry(to_qrect(self._start_place()))
        self._configure_view()
        self._refresh()
        self.introduce()

    # -- what it shows ------------------------------------------------------------------

    @property
    def view(self) -> CaptionLines:
        return self.canvas.view

    @property
    def alpha(self) -> float:
        """How faded it is: 1.0 shown, 0.0 faded out (a joined window shows
        while any column does)."""
        return self._alpha

    def introduce(self) -> None:
        """Shows itself for the fade-after time from now, then fades as an
        idle window does (polyglotic-hq DECISIONS.md #56): when Reset
        position (or joining, or separating) puts it somewhere new, so the
        learner sees that it's there and where. With nothing to read yet it
        shows anyway, waiting for audio (`views.caption_window.shows`)."""
        now = time.monotonic()
        self._intro_until = now + intro_seconds(self.look.fade_after)
        self._last_activity = now
        self.canvas.update()
        self._wake()

    @property
    def mark_showing(self) -> bool:
        """The listening mark: speech heard and its finished caption not
        here yet (in every timing: polyglotic-hq 260), while following
        live."""
        return self.listening and self.view.scroll.following

    def _sources(self) -> tuple[SourceId, ...]:
        if self.choices.show_mic and self.mic is not None:
            return (self.source, self.mic)
        return (self.source,)

    def readings(self) -> tuple[str, ...]:
        """The reading lines the one click turns on for its languages - "zh"
        for a Chinese window: its spoken language chosen, heard in what it
        shows, its translation's or its second language's (446: the one
        click puts pinyin over a Chinese window's words) - only those it
        turns on (`reading_lines.ONE_CLICK`; 511)."""
        choices = self.choices
        named = (choices.spoken_language, choices.target, self._second())
        heard = (each for line in self.canvas.lines_in_view() for each in line.heard)
        found = {reading_lines.language_of(each) for each in (*named, *heard)}
        return tuple(sorted(each for each in found if each in reading_lines.ONE_CLICK))

    def _second(self) -> Language | None:
        target = self.choices.target
        return self.second_languages.get(target) if target else None

    def _options(self) -> DisplayOptions:
        look = self.look
        return DisplayOptions(
            self.video_enabled or look.show_original,
            shown_links(look),
            look.link_detail,
            preview=look.preview,
            trail=not self.timing.paced and not self.video_enabled,
        )

    def _ink(self) -> Ink:
        look = self.look
        label = readable_on(Ink().label.name(), look.background, LABEL_CONTRAST)
        ink = Ink(QColor(look.original), QColor(look.translation), QColor(label))
        ink = look_ink(ink, look)
        if self.follows:  # the translation in full ink, what was said back
            ink = replace(
                ink, alpha=FOLLOW_SAID_ALPHA, translation_alpha=1.0 / FOLLOW_SAID_ALPHA
            )
        return ink

    @property
    def follows(self) -> bool:
        """Follow is the path here now: a paced mode, with a translation."""
        return (
            self.path is ReadingPath.FOLLOW
            and self.timing.paced
            and self.choices.target is not None
            and self.look.show_original
        )

    def set_path(self, path: ReadingPath) -> None:
        """What is read first (the learner's, Settings > Timing)."""
        if path is self.path:
            return
        self.canvas.hold()
        self.path = path
        self._path_changed()
        self._fit_band()  # the timing chip's dropdown ticks it
        self._refresh_popovers()

    def _path_changed(self) -> None:
        """The path, or whether it applies, changed: laid out and inked again."""
        style = self._style()
        if style != self.canvas.engine.style:
            self.canvas.engine = self._engine(style)
        self.canvas.ink = self._ink()
        self._refresh()
        self.zone.update()

    def path_style(self, style: CaptionStyle) -> CaptionStyle:
        """`style` as the path draws it: Follow's sizes."""
        if not self.follows:
            return style
        return replace(
            style,
            text_px=style.text_px * FOLLOW_SAID_SCALE,
            translation_factor=style.translation_factor * FOLLOW_TRANSLATION_SCALE,
        )

    @contextmanager
    def batch_settings(self) -> Iterator[None]:
        """Apply all line and layout choices together before the next paint."""
        outer = self._batching_settings
        self._batching_settings = True
        try:
            yield
        finally:
            self._batching_settings = outer
            if not outer:
                self._configure_view()
                self._place_zone()
                self._refresh()

    def _configure_view(self) -> None:
        if self._batching_settings:
            return
        zoned = self.zones is not None or (self.cards_on and self.timing.paced)

        # each app's colour, readable on the panel: they're picked for dark
        # panels, and Paper's is cream (261)
        panel = self.look.background

        def readable(label: SourceLabel) -> SourceLabel:
            return replace(label, color=readable_on(label.color, panel, LABEL_CONTRAST))

        labels = self.labels
        display = LineDisplay(
            self.choices.target,
            self._second(),
            self._options(),
            replace(
                labels,
                sources={key: readable(each) for key, each in labels.sources.items()},
                you=readable(labels.you),
                show_source=self.look.show_source,
                show_language=self.look.show_language,
                # Steady's layout names it when it changes (526)
                language_once=self.zones is not None
                or (self.cards_on and self.timing.paced),
                # and a card, being a line, its source too (decision 0260)
                source_once=self.cards_on and self.timing.paced,
                spoken=spoken_in,
                delay=delay_text if self.look.show_delay else None,
                #: on a caption the learner said again for the other person (567)
                respoken=_tr("re-spoken"),
            ),
            cuts=zoned or self.look.lab.fill is Fill.PAIRED,
            models=zoned or self.canvas.engine.style.flow is not None,
        )
        self.view.set_display(display)

    def receive(self, update: CaptionUpdate) -> bool:
        """A caption update: into the window now - never kept for the
        mouse; while it's on the words the view holds instead (`_hold`).
        True if it changed what shows now."""
        seq = None if update.times is None else update.times.seq
        if not self.video_enabled and (
            self.look.lab.arrival_gap > 0.0 or len(self.pacing)
        ):
            if update.source_id not in self.view.sources:
                return False
            self.pacing.add(update, self.clock())
            shown = self._let_paced()
            if self.pacing.waits(update):
                trace.tracer().held(seq, "gap")
            return shown
        if not self._into_view(update):
            return False
        self.apply_changed(new_caption=True)
        return True

    def _into_view(self, update: CaptionUpdate) -> bool:
        """`update` into the window's view - True if what shows changed -
        and marked in the caption timelines: it shows at the next paint
        (perf.trace). A transcript's lines collect it too, unseen: only a
        window marks it."""
        if update.times is not None and update.source_id in self.view.sources:
            trace.tracer().windowed(update.times.seq)
        if update.source_id not in self.view.sources:
            return self.view.apply(update)
        changed = False
        if self.deck is None:
            old = self._old_deck
            if old is not None:  # a caption joined after the cards were put away
                if self.video_enabled and old.owns(update.caption_id):
                    self.canvas.video.retain_in_history(
                        update.source_id, update.caption_id
                    )
                for gone in (update.caption_id, *update.replaces):
                    if old.owns(gone):
                        withdrawn = CaptionUpdate(
                            gone, update.source_id, CaptionKind.WITHDRAWN
                        )
                        for card in old.show(withdrawn, self.clock()):
                            changed = self.view.apply(card) or changed
            if (
                self.video_enabled
                and update.kind is CaptionKind.FINISHED
                and any(clause.translations for clause in update.clauses)
            ):
                self.canvas.video.final.intersection_update(
                    (line.source, line.caption_id) for line in self.view.lines
                )
                self.canvas.video.final.add((update.source_id, update.caption_id))
            return (
                self.view.apply(
                    update,
                    hold_live_translation=self.video_enabled,
                )
                or changed
            )
        self._remember_dealt(update)
        if not self.deck.owns(update.caption_id):
            # shown as it came until now (the mode changed mid-caption): the
            # cards take its place - never the draft beside its final lines
            for raw in (update.caption_id, *update.replaces):
                if any(line.caption_id == raw for line in self.view.lines):
                    left = CaptionUpdate(raw, update.source_id, CaptionKind.WITHDRAWN)
                    changed = self.view.apply(left) or changed
        newest = self.view.lines[-1].key if self.view.lines else -1
        # New cards can present a ready pair together. A translation of
        # an existing card lands while the stack is at rest.
        self.deck.reveal = not self.sliding or self._quiet(self.clock())
        dealt = self.deck.show(update, self.clock())
        shown = {line.caption_id for line in self.view.lines[-12:]}
        # a card dealt again in the place of one shown takes its place at
        # once: kept back, the stack lost a card and got it back (583)
        again = any(
            card.kind is CaptionKind.WITHDRAWN and card.caption_id in shown
            for card in dealt
        )
        for card in dealt:
            changed = self._deal(card, at_once=again) or changed
        arrived = bool(self.view.lines and self.view.lines[-1].key != newest)
        if arrived:
            self._card_since = self.clock()
        self._note_reading()
        self.check_card_room(turning=arrived and self.sliding)
        return changed

    def _deal(self, card: CaptionUpdate, at_once: bool = False) -> bool:
        """`card` into the view - True if what shows changed. A new card
        that would push a line written under `CARD_READ_SEC` ago is kept
        back until then, `CARD_WAIT_SEC` at most (`check_card_room` shows
        it): a line isn't pushed while it is being read."""
        key = card.caption_id
        if card.kind is CaptionKind.WITHDRAWN:
            self._kept_back.pop(key, None)
            return self.view.apply(card)
        if key in self._kept_back:
            self._kept_back[key] = card
            return False
        lines = self.view.lines
        if lines and lines[-1].caption_id == key:
            before = lines[-1]
            changed = self.view.apply(card)
            if changed and self.view.lines:
                current = self.view.lines[-1]
                old = [r.text for r in before.rows if r.kind is RowKind.TRANSLATION]
                new = [r.text for r in current.rows if r.kind is RowKind.TRANSLATION]
                if new and new != old:
                    self._translated_at = self.clock()
            return changed
        if (
            at_once
            or not lines
            or not self.sliding
            or not self.view.scroll.following
            or any(line.caption_id == key for line in lines[-12:])
        ):
            return self.view.apply(card)
        now = self.clock()
        if not self._kept_back:
            until = self._card_due(now)
            if until <= now:
                self._card_since = now  # a burst's next card waits for this one
                return self.view.apply(card)
            self._kept_until = until
        self._kept_back[key] = card
        return False

    def _show_kept(self, most: int | None = None) -> bool:
        """The cards kept back, shown - True if there were any: the oldest
        alone if `most` are left at most (a burst comes in a card at a
        time, each on its own glide - 553: "three cards fade in at once")."""
        kept = self._kept_back
        if not kept:
            return False
        count = len(kept) if most is None else max(1, len(kept) - most)
        for key in list(kept)[:count]:
            self.view.apply(kept.pop(key))
        self._card_since = self.clock()
        self._note_reading()
        return True

    def _quiet(self, now: float) -> bool:
        """Whether a translation can land between card arrivals."""
        deck = self.deck
        if self.glide.moving(now):
            return False
        # On "Translation with it", unseen words alone need no delay. A
        # translation can land in its reserved row while the view is still.
        return self.path is ReadingPath.BOTH or deck is None or not deck.coming(now)

    def set_reading_hold(self, most: float | None) -> None:
        """Hold a new card at most `most` seconds while the card it would
        take out of reading isn't read (`views.dwell`) - the window runs
        behind the speech and catches up in the next pause. None: off."""
        self._reading_hold = most

    def _card_due(self, now: float) -> float:
        """When a new card may come: once the line before it has stood
        `CARD_READ_SEC` - `CARD_WAIT_SEC` at most - or, with the reading
        hold on, once the card it takes out of reading is read too, the
        hold at most."""
        until = max(
            self._card_since + CARD_READ_SEC.value,
            self._translated_at + CARD_WAIT_SEC.value,
        )
        hold = self.reading_hold
        if hold is None:
            return min(until, now + CARD_WAIT_SEC.value)
        # nor while the newest card is still being read: it steps back
        front = self._read_by(self.view.lines[-1].key) if self.view.lines else -1e9
        return min(max(until, front, self._read_by(self._leaving())), now + hold)

    def _next_due(self, now: float) -> float:
        """A card shown out of those kept back: when the next may come."""
        step = now + CARD_STEP_SEC.value
        hold = self.reading_hold
        if hold is None:
            return step
        front = self._read_by(self.view.lines[-1].key) if self.view.lines else -1e9
        return max(step, min(max(front, self._read_by(self._leaving())), now + hold))

    def _read_by(self, key: int | None) -> float:
        reading = self._reading.get(key) if key is not None else None
        return reading.read_by() if reading is not None else -1e9

    def _leaving(self) -> int | None:
        """The card a new one would take out of reading."""
        cards = [ln for ln in self.view.lines if ln.caption_id.startswith(CARD)]
        if self.card_limit is not None:
            count = self.card_limit
        else:
            flat = FLAT_SHARE.value * self.canvas._seen_height()
            count = max(1, int(flat / self._card_pitch()))
        return cards[-count].key if len(cards) >= count else None

    def _note_reading(self) -> None:
        """The newest cards as shown now: when each first showed, when its
        words last grew and when its translation landed (`views.dwell`)."""
        if self.deck is None:
            return
        now = self.clock()
        seen = self._reading
        keep: dict[int, Reading] = {}
        for line in self.view.lines[-8:]:
            if not line.caption_id.startswith(CARD):
                continue
            said = " ".join(
                row.text for row in line.rows if row.kind is RowKind.ORIGINAL
            )
            meant = " ".join(
                row.text for row in line.rows if row.kind is RowKind.TRANSLATION
            )
            was = seen.get(line.key)
            if was is None:
                awaited = self.view.target is not None and not self._untranslated(line)
                was = Reading(now, now, said, "", None, awaited)
            if said != was.said:
                was.said, was.last = said, now
            if meant and meant != was.meant:
                was.meant, was.landed = meant, now
            keep[line.key] = was
        self._reading = keep

    def read_until(self) -> float | None:
        """When the cards drawn now are all read (`views.dwell`) - None
        without cards."""
        if self.video_enabled:
            return self.canvas.track_read_until
        if self.deck is None or not self._reading:
            return None
        count = self.card_limit or len(self.canvas.placed) or 1
        cards = [ln for ln in self.view.lines if ln.caption_id.startswith(CARD)]
        return max((self._read_by(line.key) for line in cards[-count:]), default=None)

    def still_read(self) -> bool:
        """A card drawn now isn't read yet: the window doesn't fade (585:
        translations faded before they were read)."""
        until = self.read_until()
        return until is not None and until > self.clock()

    def check_card_room(self, *, turning: bool = False) -> None:
        """The stack's two quiet moments (decision 0261).

        A new card can arrive with its translation. A pending translation
        of a card already shown lands when the stack is still. The
        reading path decides whether to wait for an expected card, with
        `TRANSLATION_WAIT_SEC` as the upper bound.

        A new card kept back so as not to push a line just written
        (`_deal`) is shown when its moment comes. The stack moves only when
        a card arrives: no room is opened ahead (553's third recording:
        "the stack rises with nothing arriving")."""
        deck = self.deck
        if deck is None:
            self._dwell.stop()
            return
        now = self.clock()
        again = 0.0
        if deck.pending():
            if self._pending_since is None:
                self._pending_since = now
            late = now - self._pending_since >= TRANSLATION_WAIT_SEC.value
            if late or (not turning and self._quiet(now)):
                self._pending_since = None
                for card in deck.flush():
                    self._deal(card)  # a translation on a kept card waits with it
                self._last_activity = time.monotonic()  # a fade starts again
                self._note_reading()
                self._refresh()
                self._note_arrivals()
                self._wake()
            else:
                again = 0.06
        else:
            self._pending_since = None
        if self._kept_back:
            wait = self._kept_until - now
            held = self.view.scroll.following and self.sliding
            if wait <= 0.0 or not held:
                self._show_kept(CARDS_KEPT_MOST - 1 if held else None)
                self.apply_changed(new_caption=True)
                self._kept_until = self._next_due(now)
                wait = self._kept_until - now
            if self._kept_back:
                again = wait if not again else min(again, wait)
        if again:
            self._dwell.start(int(again * 1000) + 15)

    # -- Steady's cards (views.cards; polyglotic-hq 552, decision 0260) -----------------

    def hear(self, update: CaptionUpdate) -> None:
        """A caption update as the server sent it, before the playout
        shows any of it: the deck sizes its cards by it."""
        if self.deck is not None and update.source_id in self.view.sources:
            self.deck.hear(update, self.clock())
            self.check_card_room()

    def set_cards(self, on: bool) -> None:
        """Whether a paced mode shows the card stack here."""
        self.cards_on = on
        self._use_zones()

    def set_video(self, enabled: bool) -> None:
        if self._video_enabled != enabled:
            canvas = self.canvas
            canvas.subtitle_timer.stop()
            self.let_in()
            if enabled:
                self._pace_timer.stop()
                while (
                    update := self.pacing.next(self.clock(), 0.0, 0.0, self._is_new)
                ) is not None:
                    self._into_view(update)
            self._video_enabled = enabled
            canvas.video = Video()
            canvas.tracks_visible = False
            canvas.track_read_until = None
            canvas._own_line = None
            if enabled:
                self._translation_expiry.stop()
                self._translation_slots.clear()
                self.view.scroll.follow()
                canvas.video.enter(self.view.lines)
            self._configure_view()
        style = self._style()
        if style != self.canvas.engine.style:
            self.canvas.engine = self._engine(style)
        self._refresh_popovers()
        self._refresh()

    @property
    def video_enabled(self) -> bool:
        """The caption window is using Video's renderer."""
        return self._video_enabled

    @property
    def card_limit(self) -> int | None:
        return self._card_limit

    @property
    def reading_hold(self) -> float | None:
        if self._reading_hold is not None:
            return self._reading_hold
        hold = OTHER_HOLDS.get(self.preset_menu.chosen)
        return (hold.value or None) if hold else None

    def set_card_limit(self, cards: int | None) -> None:
        """Subtitles: only the newest `cards` cards are drawn (None: as
        many as the window holds)."""
        self._card_limit = cards
        self.canvas.update()

    def _remember_dealt(self, update: CaptionUpdate) -> None:
        dealt = self._dealt
        for gone in update.replaces:
            dealt.pop(gone, None)
        if update.kind is CaptionKind.WITHDRAWN:
            dealt.pop(update.caption_id, None)
            return
        dealt[update.caption_id] = update
        now = self.clock()
        first = self._dealt_at.get(update.caption_id, (now, now))[0]
        self._dealt_at[update.caption_id] = (first, now)
        for gone in self._dealt_at.keys() - dealt.keys():
            del self._dealt_at[gone]
        while len(dealt) > CAPTION_WINDOW_LINES:
            del dealt[next(iter(dealt))]

    def _measure(self, text: str, translation: bool) -> float:
        side = RowKind.TRANSLATION if translation else RowKind.ORIGINAL
        return row_text_width(self.canvas.engine, text, side, self.view.text_size)

    def _dealt_stamp(self) -> tuple[object, ...]:
        return (
            self.canvas._width(),
            self.view.text_size,
            self.choices.translation_size,
        )

    def _new_deck(self) -> None:
        self._deals += 1  # a withdrawn card's id is never shown again
        self.deck = Deck(
            float(self.canvas._width()),
            self._measure,
            self.card_split,
            prefix=f"{self._deals}.",
        )
        self._dealt_for = self._dealt_stamp()
        self._bare_heights.clear()
        self._translation_slots.clear()
        self._plain_tall = 0.0

    def _deal_again(self) -> None:
        """The cards dealt again from the captions shown - the text size
        or the faces changed, so what fits a card did. At rest at once:
        nothing glides for it. Only the width changed (a resize): the same
        cards, laid out again (`_lay_out_again`)."""
        if self.deck is None or self._dealt_for == self._dealt_stamp():
            return
        if self._dealt_for and self._dealt_for[1:] == self._dealt_stamp()[1:]:
            self._lay_out_again()
            return
        view = self.view
        for line in view.lines:
            if line.caption_id.startswith(CARD):  # captions shown as they came stay
                view.apply(
                    CaptionUpdate(line.caption_id, line.source, CaptionKind.WITHDRAWN)
                )
        self._old_deck = None
        self._kept_back = {}
        self._view_held = None  # dealt again: live
        self._new_deck()
        assert self.deck is not None
        now = self.clock()
        for update in list(self._dealt.values()):
            # as it came: a caption that started a card after a pause
            # starts one again (553: a resize merged captions for good)
            first, last = self._dealt_at.get(update.caption_id, (now, now))
            for card in self.deck.show(update, first):
                view.apply(card)
            self.deck.said_at(last)
        self.glide.stop()
        view.scroll.follow()  # the card that was held is no more
        self.canvas.at_rest = {}
        # these cards are known: the next one's rise is measured, and glides
        self._known = {line.key for line in self.canvas.lines_in_view()}

    def _lay_out_again(self) -> None:
        """A new width (the window resized): the same cards, each laid out
        again at it - none dealt again, none withdrawn - and new words
        dealt at it (the user, 2026-11-21: "resizing screens creates bugs
        now, resetting the entire window, or going back to start of
        transcript"). Following, it stays live; scrolled back, the card
        read at the top stays where it is on the screen."""
        deck = self.deck
        assert deck is not None
        canvas, scroll = self.canvas, self.view.scroll
        place = None if scroll.following else self._reading_place()
        deck.set_width(float(canvas._width()))
        self._dealt_for = self._dealt_stamp()
        self._bare_heights.clear()
        self.glide.stop()
        self._lag = {}
        canvas.at_rest = {}
        if place is not None:
            key, top = place
            lines = canvas.lines_in_view()
            height, room, gap = canvas._height, canvas._view_height(), canvas._gap()
            if any(line.key == key for line in lines):
                scroll.anchor = Anchor(key, 0.0)
                scroll.scroll_by(top, lines, height, room, gap)
        self._known = {line.key for line in canvas.lines_in_view()}

    def _reading_place(self) -> tuple[int, float] | None:
        """Scrolled back: the first card the last paint drew whole, and
        where its top was in the scroll's view (0 its top)."""
        canvas = self.canvas
        top = PAD + self.held_top()
        for line, _, rect in canvas.placed:
            if rect.top() >= canvas.clear_top - 0.5:
                return line.key, rect.top() - top
        return None

    def held_top(self) -> float:
        """The strip at the top the cards leave free while scrolled back:
        the toolbar's, which shows whenever the mouse is on the window -
        it never hides the top card, and nothing moves as it comes and
        goes (572's reviews: it hid the top card, then gave it back)."""
        if self.deck is None or self.view.scroll.following:
            return 0.0
        return max(0.0, band_height() + 1.0 - PAD)

    def pill_room(self) -> float:
        """The room Back to live takes at the foot while the cards are
        scrolled back: the cards stand above it."""
        # Subtitle pages always leave this strip free. A hover count can
        # appear without moving or covering the words under the mouse.
        if not self.video_enabled and (self.deck is None or self.view.scroll.following):
            return 0.0
        return float(self.pill.sizeHint().height() + 8)

    def _sync_bar(self) -> None:
        """The scroll bar, in cards: where the first card shown is, of all."""
        bar = self.scroll_bar
        lines = self.view.lines
        page = self._cards_a_page()
        maximum = max(0, len(lines) - page) if self.deck is not None else 0
        anchor = self.view.scroll.anchor
        if anchor is None:
            value = maximum
        else:
            first = bisect.bisect_left(lines, anchor.key, key=lambda ln: ln.key)
            if anchor.offset < -0.5:
                first += 1  # the first whole card: the held one is cut
            value = min(first, max(0, maximum - 1))
        # none over a film: Video has no panel for it to stand on (556)
        show = maximum > 0 and not self.locked and self.look.opacity > 0.0
        if show != (not bar.isHidden()):
            bar.setVisible(show)
        if (bar.maximum(), bar.value(), bar.pageStep()) == (maximum, value, page):
            return
        self._bar_syncing = True
        bar.setRange(0, maximum)
        bar.setPageStep(page)
        bar.setValue(value)
        self._bar_syncing = False

    def _cards_a_page(self) -> int:
        """About how many cards the window holds: the bar's page. Not
        from what was last painted - the bar never waits for a paint."""
        return max(1, int(self.canvas._seen_height() / self._card_pitch()))

    def _card_pitch(self) -> float:
        """From one card's top to the next one's: by the newest card
        without a label - the room kept for a card made ahead is what the
        card then takes, or the stack would come back down."""
        tall = self._plain_tall or self.zone.line_height()
        return max(1.0, tall + self.canvas._gap())

    def _bar_moved(self, value: int) -> None:
        if self._bar_syncing:
            return
        lines = self.view.lines
        scroll = self.view.scroll
        was = scroll.anchor.key if scroll.anchor is not None else None

        def change() -> None:
            if value >= self.scroll_bar.maximum() or not lines:
                scroll.follow()
            else:
                scroll.anchor = Anchor(lines[value].key, 0.0)
                canvas = self.canvas
                room, gap = canvas._view_height(), canvas._gap()
                foot, used = value, canvas._height(lines[value])
                while foot + 1 < len(lines):
                    more = gap + canvas._height(lines[foot + 1])
                    if used + more > room + 0.5:
                        break
                    foot, used = foot + 1, used + more
                scroll.anchor = self._held_at(lines, foot)
                self._held_or_live()

        back = value < len(lines) and (was is None or lines[value].key < was)
        self._scrolled(change, back=back)

    def scroll_subtitles(self, notches: float) -> None:
        """Browse whole subtitles, one caption per notch, from the first
        actually on screen. The history anchor holds as new speech comes."""
        lines = self.canvas._lines()
        placed = self.canvas.placed
        if not notches or not lines:
            return
        self._view_held = None
        anchor = self.view.scroll.anchor
        if anchor is not None:
            first = anchor.key
        elif placed:
            first = placed[0][0].key
        elif notches > 0:
            first = lines[-1].key + 1
        else:
            return
        at = bisect.bisect_left(lines, first, key=lambda line: line.key)
        step = round(notches) or (1 if notches > 0 else -1)
        to = max(0, min(len(lines) - 1, at - step))
        if step < 0 and lines[to].key >= self.canvas.video.live_start:
            self.view.scroll.follow()
        elif to != at or (anchor is None and step > 0):
            self.view.scroll.anchor = Anchor(lines[to].key, 0.0)
        self._refresh()

    def scroll_cards(self, notches: float) -> None:
        """The wheel, with cards: a card a notch - back to older cards if
        positive - eased, and at rest on whole cards: the top of the view
        is a card's top, never a row cut through."""
        canvas = self.canvas
        lines = canvas.lines_in_view()
        if not lines or not notches:
            return
        step = round(notches) or (1 if notches > 0 else -1)
        scroll = self.view.scroll
        placed = scroll.placed(
            lines, canvas._height, canvas._view_height(), canvas._gap()
        )
        if not placed:
            return
        last = len(lines) - 1
        if scroll.anchor is None:
            if step < 0:
                return  # at the newest already
            # Back to live takes a strip of the foot: a card back would
            # show less than a card more. One further: a whole new card.
            foot = last - 1
        else:  # the last card that stands whole
            room = canvas._view_height()
            whole = [
                item.line.key
                for item in placed
                if item.top + canvas._height(item.line) <= room + 0.5
            ]
            key = whole[-1] if whole else placed[-1].line.key
            foot = next(n for n, line in enumerate(lines) if line.key == key)
        to = max(0, min(last, foot - step))
        if to == foot and scroll.anchor is not None:
            return

        def change() -> None:
            if to >= last - 1:  # and the same strip on the way back down
                scroll.follow()
                return
            scroll.anchor = Anchor(lines[to].key, 0.0)  # held: the pill takes room
            scroll.anchor = self._held_at(lines, to)
            self._held_or_live()

        self._scrolled(change, back=step > 0)

    def _held_at(self, lines: Sequence[Line], foot: int) -> Anchor:
        """The cards held with card `foot` whole at the foot of the view,
        as the newest is when following: what doesn't fit is cut at the
        top, where the card before isn't drawn - never a card cut at the
        foot, nor one fading there (553's third recording). At the oldest
        cards, from the top."""
        canvas = self.canvas
        gap, room = canvas._gap(), canvas._view_height()
        top, above = foot, room - canvas._height(lines[foot])
        while top > 0 and above - gap - canvas._height(lines[top - 1]) >= -0.5:
            top -= 1
            above -= gap + canvas._height(lines[top])
        if top == 0 or above < 1.0:
            return Anchor(lines[top].key, 0.0)
        before = lines[top - 1]
        return Anchor(before.key, above - gap - canvas._height(before))

    def _far_from_home(self) -> bool:
        """Scrolled back further than Back to live slides
        (`HOME_CARDS_MOST` cards)."""
        anchor = self.view.scroll.anchor
        lines = self.view.lines
        if anchor is None or not lines:
            return False
        at = bisect.bisect_left(lines, anchor.key, key=lambda ln: ln.key)
        return len(lines) - at > HOME_CARDS_MOST + self._cards_a_page()

    def veil(self, now: float) -> float:
        """The ink of the whole view while it comes home unseen: out over
        half of `VEIL_SEC`, in over the other half."""
        if self._veil_at is None:
            return 1.0
        share = (now - self._veil_at) / (VEIL_SEC / 2)
        if self._veil.isActive():
            return max(0.0, 1.0 - share)  # stay faded until the timer brings us home
        if share >= 2.0:
            self._veil_at = None
            return 1.0
        return min(1.0, abs(1.0 - share))

    def _come_home(self) -> None:
        """The fade-out timer fired: live again, at rest."""
        self._veil.stop()
        if self.deck is None or self.view.scroll.following:
            return
        self.view.scroll.follow()
        self.glide.stop()
        self._lag = {}
        self.canvas._covered.clear()
        self._refresh()
        self.canvas.at_rest = {}
        self._known = {line.key for line in self.canvas.lines_in_view()}
        self._veil_at = self.clock() - VEIL_SEC / 2
        self.canvas.update()
        self._wake()

    def _held_or_live(self) -> None:
        """After the learner scrolled: live again if the newest card's
        foot shows - only then. Scrolled back otherwise stays so until
        they go back (the pill, End, the wheel, the bar), whatever the
        cards below do (567's filmed runs: live again within 4-6 s)."""
        canvas, scroll = self.canvas, self.view.scroll
        scroll.sticky = False
        scroll.placed(
            canvas.lines_in_view(), canvas._height, canvas._view_height(), canvas._gap()
        )
        scroll.sticky = self.deck is not None

    def _scrolled(
        self, change: Callable[[], None], back: bool, home: bool = False
    ) -> None:
        """A scroll of the cards (`change` makes it): the stack glides to
        its new place from where it stood, by a card both views show - or,
        with none, the last of the way from the side it comes from, `back`
        from above. Never faster than `GLIDE_FASTEST`."""
        canvas = self.canvas
        before = canvas.rest_rows()
        change()
        self._refresh()
        if not self.sliding:
            return
        after = canvas.rest_rows()
        kept = before.keys() & after.keys()
        most = (HOME_CARDS_MOST if home else GLIDE_MOST) * self._card_pitch()
        if kept:
            moved = before[max(kept)] - after[max(kept)]
        elif home and before and after:
            # no card in both views: the way between them, by the cards
            # between - the stack is never thrown there (553: "310 px in
            # 9 ms through two flashes of unrelated cards")
            lines = canvas.lines_in_view()
            first, last = max(before)[0], max(after)[0]
            between = sum(
                canvas._height(line) + canvas._gap()
                for line in lines[-HOME_CARDS_MOST:]
                if first < line.key <= last
            )
            moved = between + before[max(before)] - after[max(after)]
        else:
            moved = -most if back else most
        self.glide.push(self.clock(), moved, most=most)
        self._lag = {}
        if home and before:
            last_seen = max(before)[0]
            self._lag = {key: self.glide.px for key, _ in after if key > last_seen}
        canvas.at_rest = after
        self._known = {line.key for line in canvas.lines_in_view()}
        canvas.update()
        self._wake()

    def _push(self, now: float, px: float, new: Collection[int] = ()) -> None:
        """The stack's place rose `px`: it glides there. The cards that
        came with the rise (`new`) stand in their place from the first
        frame - the stack moves up from under them."""
        was = self.glide.to(now)
        self._lag = {key: min(lag, was) for key, lag in self._lag.items() if was > 0.0}
        self.glide.push(now, px, most=GLIDE_MOST * self._card_pitch())
        for key in new:
            self._lag[key] = self.glide.px

    def card_offset(self, key: int, offset: float) -> float:
        """How far from its place card `key` is drawn while the stack is
        `offset` px from its own."""
        if offset <= 0.0 or not self._lag:
            return offset
        return max(0.0, offset - self._lag.get(key, 0.0))

    def _settle(self) -> None:
        """After a change of look (`Canvas.hold`): the stack glides from
        where its newest row stood to where it stands now."""
        before, self._held_rows = self._held_rows, None
        if before is None or self.deck is None or not self.sliding:
            return
        after = self.canvas.rest_rows()
        kept = before.keys() & after.keys()
        if not kept:
            return
        moved = before[max(kept)] - after[max(kept)]
        if abs(moved) > 0.5:
            most = GLIDE_MOST * self._card_pitch()
            self._lag = {}
            self.glide.push(self.clock(), moved, most=most)
            self.canvas.at_rest = after
            self._wake()

    def _place_bar(self) -> None:
        top = band_height() + 2 if self.band_shown else 4
        self.scroll_bar.setGeometry(
            self.width() - CARD_BAR_PX.value - 2,
            top,
            CARD_BAR_PX.value,
            self.height() - top - 4,
        )

    def reserve_translation(
        self, line: Line, laid: LaidLine, style: CaptionStyle
    ) -> LaidLine:
        """Reserve height until the translation fills the slot or the wait ends."""
        target = self.view.target
        if target is None or not self.look.show_original or self._untranslated(line):
            if target is None and self.deck is not None and not line.label:
                self._plain_tall = laid.height
            return laid
        room = self._translation_room()
        slots = self._translation_slots
        slot = slots.get(line.key)
        newest = self.view.lines[-1].key if self.view.lines else line.key
        if slot is not None and slot.filled_at is not None and slot.filled_at != newest:
            # A short translation may leave part of its estimate unused. The
            # next caption takes it back in the same scroll as its arrival.
            del slots[line.key]
            slot = None
        now = self.clock()
        translated = {
            row.clause for row in line.rows if row.kind is RowKind.TRANSLATION
        }
        originals = [
            row
            for row in laid.rows
            if row.row.kind is RowKind.ORIGINAL and row.row.text.strip()
        ]
        missing = [row for row in originals if row.row.clause not in translated]
        if missing:
            original = tuple(row.row.text for row in originals)
            if slot is None or slot.until is None:
                slot = slots[line.key] = _TranslationSlot(original, None)
                if len(slots) > 4 * CAPTION_WINDOW_LINES:
                    del slots[next(iter(slots))]
            if slot.until is None or slot.rows != original:
                slot.rows = original
                slot.until = now + TRANSLATION_WAIT_SEC.value
                self._schedule_translation_expiry(now)
            # The estimate must not push the original out of a short window.
            available = max(0.0, self.canvas._seen_height() - laid.height)
            size = self.view.text_size
            scale = (style.translation_size or size) * style.translation_factor / size
            ratio = TRANSLATION_WIDTH_RATIO.value * scale
            if laid.poured:
                rows = self._unfilled_translation_rows(laid, missing, ratio)
                slot.bare, slot.room = laid.height, min(room * rows, available)
            else:
                for row in missing:
                    wide = row.layout.maximumWidth() * ratio
                    space = min(available, room * max(1, math.ceil(wide / laid.width)))
                    slot.spaces[row.row.clause] = space
                    available -= space
        if slot is not None:
            share = self._translation_space_left(slot.until, now)
            if not missing:
                if slot.until is not None:
                    slot.spaces = {
                        clause: gap * share for clause, gap in slot.spaces.items()
                    }
                    slot.room *= share
                    slot.until = None
                    slot.filled_at = newest
                share = 1.0
            if laid.poured:
                height = max(laid.height, slot.bare + slot.room * share)
                if height > laid.height:
                    laid = replace(
                        laid, height=height, breaks=(*laid.breaks[:-1], height)
                    )
            elif slot.spaces and share > 0.0:
                laid = reserve_translation_space(
                    laid, {clause: gap * share for clause, gap in slot.spaces.items()}
                )
        if (
            self.deck is not None
            and not line.label
            and (translated or slot is not None)
        ):
            self._plain_tall = (
                max(laid.height, slot.bare + slot.room) if slot else laid.height
            )
        return laid

    def _unfilled_translation_rows(
        self, laid: LaidLine, missing: Sequence[LaidRow], ratio: float
    ) -> int:
        """A paired card can already have a translation when new words join it."""
        existing = [row for row in laid.rows if row.row.kind is RowKind.TRANSLATION]
        if not existing and self.deck is not None:
            return 1  # the deck already sizes a new card to fit the translation
        width = sum(row.layout.maximumWidth() for row in existing)
        width += TO_SPARE * ratio * sum(row.layout.maximumWidth() for row in missing)
        occupied = {
            round(row.top + row.layout.lineAt(n).y())
            for row in existing
            for n in range(row.layout.lineCount())
        }
        return max(0, math.ceil(width / laid.width) - len(occupied))

    def _translation_space_left(self, until: float | None, now: float) -> float:
        if until is None or now <= until:
            return 1.0
        if reduced_motion():
            return 0.0
        return 1.0 - ease_out((now - until) / slide_seconds(1.0))

    def _close_translation_gaps(self) -> None:
        self.canvas.update()
        self._zone_changed(new_text=False)
        self._schedule_translation_expiry(self.clock())

    def _schedule_translation_expiry(self, now: float) -> None:
        """Wake at the next deadline, then repaint each frame of the collapse."""
        if (
            self.video_enabled
            or self.view.target is None
            or not self.look.show_original
        ):
            return
        deadlines = [
            slot.until - now
            for slot in self._translation_slots.values()
            if slot.until is not None
        ]
        if not reduced_motion() and any(
            -slide_seconds(1.0) < when <= 0.0 for when in deadlines
        ):
            ms = FRAME_MS
        else:
            soon = min((when for when in deadlines if when > 0), default=None)
            if soon is None:
                return
            ms = max(1, math.ceil(soon * 1000))
        if (
            not self._translation_expiry.isActive()
            or ms < self._translation_expiry.remainingTime()
        ):
            self._translation_expiry.start(ms)

    def card_height(self, line: Line, laid: float) -> float:
        """Room for this card's current rows and one pending translation.
        A wrapped translation takes its measured height only while shown."""
        translated = any(row.kind is RowKind.TRANSLATION for row in line.rows)
        room = (
            self._translation_room()
            if self.view.target is not None and self.look.show_original
            else 0.0
        )
        if room and not translated:
            if line.key not in self._bare_heights:
                if len(self._bare_heights) > 4 * CAPTION_WINDOW_LINES:
                    self._bare_heights.clear()
                self._bare_heights[line.key] = (
                    None if self._untranslated(line) else laid
                )
            if self._bare_heights[line.key] is not None:
                self._bare_heights[line.key] = laid
        bare = self._bare_heights.get(line.key)
        tall = laid
        if room and bare is not None:
            if bare <= laid:
                # Keep the one row already reserved for this card. Any
                # additional wrapped rows follow the current translation.
                tall = max(laid, bare + room)
            else:
                # Even the whole card is shorter than its former source.
                del self._bare_heights[line.key]
        if not line.label and (
            translated or bare is not None or self.view.target is None
        ):
            self._plain_tall = tall
        return tall

    def _untranslated(self, line: Line) -> bool:
        """Card `line` will get no translation: all on it was said in the
        language this window translates into, and the server translates
        only the others (553's fourth recording: room kept 17.9 s for a
        translation that never came). No room is kept for one - but where
        this window's target has a second language, the server translates
        those into it: a second line comes, and its room is kept (577:
        #965 made English every target's second, and the stack stepped up
        65 px as each came)."""
        deck = self.deck
        if self._second() is not None:
            return False
        if deck is not None:
            return deck.spoken(line.caption_id) == {self.view.target}
        return set(line.heard) == {self.view.target}

    def _translation_room(self) -> float:
        """The room a translation's row takes under a card's words here:
        measured - a card laid out with one and without - so the room kept
        is never short of what the translation needs, its descenders too
        (553's recording: 12-17 px short, and the page nudged)."""
        view, canvas = self.view, self.canvas
        size = (
            view.text_size,
            canvas.engine.style,
            view.target,
            self._second(),
            canvas._width(),
        )
        if size != self._slot_for:  # another size or look: measured again
            self._bare_heights.clear()
            self._translation_slots.clear()
            self._slot_for, self._translation_row_height = size, self._probe_room()
        return self._translation_row_height

    def _probe_room(self) -> float:
        view, canvas = self.view, self.canvas
        target = view.target
        if target is None or not view.sources:
            return 0.0
        source = next(iter(view.sources))
        probe = CaptionLines(
            (source,),
            target,
            keep=2,
            second=self._second(),
            options=self._options(),
            cuts=True,
            text_size=view.text_size,
            sizes=CAPTION_TEXT_SIZES,
        )
        probe.set_models(True)  # measure the same paired layout the card uses
        said = Language("fr" if target == "en" else "en")
        tall: list[float] = []
        for name, lines in (("bare", {}), ("full", {target: "汉字 Ágyj"})):
            probe.apply(
                CaptionUpdate(
                    CaptionId(f"probe.{name}"),
                    source,
                    CaptionKind.FINISHED,
                    (Clause("Ágyj", lines),),
                    said,
                    (said,),
                )
            )
            # Negative synthetic keys avoid colliding with real lines in engine._kept
            line = replace(probe.lines[-1], key=-1 - len(tall))
            tall.append(canvas.laid_at(line, canvas._width()).height)
        return max(0.0, tall[1] - tall[0])

    def _is_new(self, update: CaptionUpdate) -> bool:
        """Whether `update` brings a caption the window doesn't show yet."""
        if update.kind is CaptionKind.WITHDRAWN:
            return False
        if self.deck is not None and any(
            self.deck.owns(key) for key in (update.caption_id, *update.replaces)
        ):
            return False
        shown = {line.caption_id for line in self.view.lines}
        return update.caption_id not in shown and not shown.intersection(
            update.replaces
        )

    def _let_paced(self) -> bool:
        """The updates waiting for the Lab's gap that may come now, shown in
        order; the next woken when it may (`views.pacing`) - the mouse
        holds the view, never them (583). True if what shows changed."""
        self._pace_timer.stop()
        gap, longest, now = self.look.lab.arrival_gap, self.longest_wait, self.clock()
        changed = False
        while (update := self.pacing.next(now, gap, longest, self._is_new)) is not None:
            changed = self._into_view(update) or changed
        if changed:
            self.apply_changed(new_caption=True)
        wait = self.pacing.wait_for(now, gap, longest)
        if wait is not None:
            self._pace_timer.start(max(1, math.ceil(wait * 1000)))
        return changed

    def _hold_on_words(self, pos: QPointF) -> None:
        """The mouse moved to `pos`: on a caption's words - or selecting
        some - new captions wait (`_hold`); anywhere else they come in at
        once (polyglotic-hq 554, DECISIONS #242's C). The panel around the
        text, the hover band and the edges never held them: a mouse
        crossing the window on its way somewhere held a tester's captions
        for up to 20 s under 4 s after its last move anywhere on it."""
        if self._drag is not None or (self.host is not None and self.host.dragging):
            on_words = False  # the window moves with the mouse: nothing to aim at
        else:
            on_words = self._selecting is not None or self._over_words(pos)
        if not on_words:
            if self._holding:
                self.let_go()
            return
        self._hold()

    def _over_words(self, pos: QPointF) -> bool:
        """Whether `pos` is on a caption's text - not on the hover band, an
        edge or a column's divider, nor the panel around the text."""
        if self.band.isVisible() and self.band.geometry().contains(pos.toPoint()):
            return False
        if self._divider(pos) is not None or self._edges(pos):
            return False
        return self.canvas.hit(pos) is not None

    def _hold(self) -> None:
        """The mouse moves over a caption's words: the view holds - nothing
        on it moves, new captions come in past it and Back to live counts
        them (583) - and a caption still sliding into place is there at
        once, whole: a slide stopped where it was left its last rows below
        the window's edge while the mouse stayed (polyglotic-hq 291)."""
        if self.locked:
            return
        self._holding = True
        self._hold_timer.stop()  # on the words again: not letting go
        if self.view.scroll.following and not self._view_holding():
            self._hold_view()
        if self.motion.moving(self.clock()):
            self.motion.stop()
            self.canvas.update()
        self.show_every_line()  # and no line comes in under the mouse

    def wake_frames(self) -> None:
        """Frames go on: the cards in depth are stepping."""
        self._wake()

    def _view_holding(self) -> bool:
        return self._view_held is not None or self._mouse_anchor is not None

    def view_held(self) -> int | None:
        """Newest caption visible during a mouse hold or Instant catch-up.
        Later captions continue into history until the view resumes."""
        if self._resume_timer.isActive():
            return self._resume_through
        return self._view_held if self.deck is not None or self.video_enabled else None

    def _hold_view(self) -> None:
        """The view stops where it stands for the mouse: with cards, at the
        newest card shown (`view_held`) - the drum stays as it is; without,
        the scroll holds where it stands, as scrolled back."""
        canvas, scroll = self.canvas, self.view.scroll
        lines = canvas.lines_in_view()
        if not lines:
            return
        if self.deck is not None or self.video_enabled:
            self._view_held = (
                canvas.placed[-1][0].key
                if self.video_enabled and canvas.placed
                else lines[-1].key
            )
            return
        placed = scroll.placed(
            lines, canvas._height, canvas._view_height(), canvas._gap()
        )
        if placed:
            self._mouse_anchor = Anchor(placed[0].line.key, placed[0].top)
            scroll.anchor = self._mouse_anchor
            scroll.sticky = True

    def let_go(self) -> None:
        """The mouse came off the words or left: the view goes live after
        `VIEW_GRACE_SEC`, unless it comes back to them first."""
        self._holding = False
        if self._view_holding():
            self._hold_timer.start(round(VIEW_GRACE_SEC.value * 1000))

    def _resume_hover(self) -> None:
        """After a long pause on Instant, show the first missed caption before
        following live. New speech is still received in the ordinary history."""
        missed = None
        lines = self.view.lines
        if (
            self.timing is CaptionMode.INSTANT
            and not self.video_enabled
            and self._mouse_anchor is not None
            and self.view.scroll.anchor == self._mouse_anchor
            and self.canvas.placed
        ):
            last = self.canvas.placed[-1][0].key
            index = bisect.bisect_right(lines, last, key=lambda line: line.key)
            if index + 1 < len(lines):
                missed = lines[index]
        before = self.canvas.rest_rows() if missed is not None else {}
        self.let_in()
        if missed is not None:
            # Captions went into history while the mouse held the view.
            # The first missed caption is only now arriving on screen.
            if self._known is not None:
                self._known = {key for key in self._known if key < missed.key}
            self._resume_through = missed.key
            seconds = 0.0
            for kind, pace, spaced in (
                (RowKind.ORIGINAL, SAID_PACE.value, SAID_PACE_SPACED.value),
                (RowKind.TRANSLATION, MEANT_PACE.value, MEANT_PACE_SPACED.value),
            ):
                words = " ".join(row.text for row in missed.rows if row.kind is kind)
                if words:
                    seconds += need(words, pace, spaced)
            self._resume_timer.start(math.ceil(1000 * seconds))
            self.canvas.at_rest = before
            self._show_resumed_lines()

    def _show_resumed_lines(self) -> None:
        self._refresh()
        self._note_arrivals()
        self._wake()

    def _release_view(self) -> None:
        """The view the mouse held goes live: one glide to where the cards
        that came meanwhile put it - unless the learner scrolled back."""
        held = self._view_held
        anchor, self._mouse_anchor = self._mouse_anchor, None
        if held is not None and self.video_enabled:
            self._view_held = None
            self._refresh()
            return
        if held is not None and self.deck is not None:
            if self.view.scroll.following:

                def live() -> None:
                    self._view_held = None

                # measured from the held view: one glide to the newest
                self._scrolled(live, back=False, home=True)
                return
            self._view_held = None
            self._refresh()
            self._wake()
            return
        self._view_held = None
        if anchor is not None:
            scroll = self.view.scroll
            if scroll.anchor == anchor:  # still where the mouse held it
                scroll.sticky = False
                self.go_live()

    def let_in(self) -> None:
        """The view the mouse held, live now (locked, hidden, another
        host; the grace after the mouse came off the words)."""
        self._resume_timer.stop()
        self._holding = False
        self._hold_timer.stop()
        if self._view_holding():
            self._release_view()
        self._wake()

    def apply_changed(self, new_caption: bool) -> None:
        """The view's captions changed (`CaptionWindows` applied an update)."""
        if new_caption:
            self._last_activity = time.monotonic()
            self.set_up_heard()
        revealed_line = self._pace_lines()
        self._zone_changed(new_caption)
        self._refresh()
        self._note_arrivals(revealed_line=revealed_line)
        self._note_corrections()
        self._wake()

    # -- a quiet correction (polyglotic-hq 494, decision 0228) --------------------

    def _note_corrections(self) -> None:
        """The lines whose words a quiet correction recolours, and since
        when: from when their caption's update came, once each."""
        now = self.clock()
        noted: dict[int, tuple[object, float]] = {}
        for line in self.view.lines:
            what = tuple(
                (row.text, row.corrected) for row in line.rows if row.corrected
            )
            if not what:
                continue
            before = self._corrections.get(line.key)
            noted[line.key] = (
                before if before is not None and before[0] == what else (what, now)
            )
        self._corrections = noted

    def correction_colour(self, key: int, now: float, row: QColor) -> QColor | None:
        """The colour line `key`'s corrected words are drawn in `now` - None
        once its moment is over (or it has none): `CORRECTION` held for the
        first half of `CORRECTION_SEC`, then eased into the `row`'s own."""
        found = self._corrections.get(key)
        if found is None:
            return None
        age = now - found[1]
        if not 0.0 <= age < CORRECTION_SEC:
            return None
        warm = QColor(readable_on(CORRECTION, self.look.background))
        share = min(1.0, max(0.0, 2.0 * (1.0 - age / CORRECTION_SEC)))
        return QColor.fromRgbF(
            row.redF() + (warm.redF() - row.redF()) * share,
            row.greenF() + (warm.greenF() - row.greenF()) * share,
            row.blueF() + (warm.blueF() - row.blueF()) * share,
            row.alphaF(),
        )

    def _correcting(self, now: float) -> bool:
        """Whether a quiet correction shows now."""
        return any(
            0.0 <= now - since < CORRECTION_SEC
            for _, since in self._corrections.values()
        )

    # -- a new caption's lines, one at a time (views.reveal; 309) ---------------------

    def _pace_lines(self) -> bool:
        """The captions new to the window start with no line shown, and
        the first that's due is (`views.reveal`) - with the Lab's Gap
        between new lines, following the newest, the mouse away.
        Return whether a paced line was revealed."""
        keys = {line.key for line in self.view.lines}
        seen, self._revealed = self._revealed, keys
        gap = self.look.lab.line_gap
        paced = (
            not self.video_enabled
            and gap > 0.0
            and self.view.scroll.following
            and not self.always_shown
        )
        if not paced or seen is None or self._holding:
            self.show_every_line()
            return False
        now = self.clock()
        for key in sorted(keys - seen):
            self.reveal.add(key, now)
        revealed = self.reveal.step(now, gap, self.longest_wait, self._lines_of)
        self._wait_for_line()
        return revealed

    def _lines_of(self, key: int) -> int | None:
        """How many lines of text caption `key` has, as laid out now."""
        for line in self.view.lines:
            if line.key == key:
                return len(self.canvas._laid(line).breaks)
        return None

    def _wait_for_line(self) -> None:
        wait = self.reveal.wait_for(
            self.clock(), self.look.lab.line_gap, self.longest_wait
        )
        if wait is None:
            self._reveal_timer.stop()
        else:
            self._reveal_timer.start(max(1, math.ceil(wait * 1000)))

    def _show_next_line(self) -> None:
        """The line that's due, shown: the text above rises for it as for a
        new caption (it slides, if the window does)."""
        gap = self.look.lab.line_gap
        if gap <= 0.0 or not self.view.scroll.following or self._holding:
            self.show_every_line()
            return
        if self.reveal.step(self.clock(), gap, self.longest_wait, self._lines_of):
            self._refresh()
            self._note_arrivals(revealed_line=True)
            self._wake()
        self._wait_for_line()

    def show_every_line(self) -> None:
        """Every line that waited, at once: the mouse came over the
        window, it was resized or scrolled back, or the Lab's gap is off."""
        self._reveal_timer.stop()
        if self.reveal.settle():
            self.motion.stop()
            self.canvas.at_rest = {}
            if self._known is not None:  # there now: not new at the next change
                self._known = {line.key for line in self.view.lines}
            self.canvas.update()

    @property
    def sliding(self) -> bool:
        """Whether arrivals slide here now: step and slide, with Windows'
        animation effects on, following the newest, and not the lab's
        photographs. Otherwise they step (`views.arrivals`)."""
        if self.deck is not None:  # the cards glide whatever the list's arrival
            return not reduced_motion() and not self.always_shown
        return (
            effective(self.look.arrival, reduced_motion()).slides
            and self.zones is None  # the live zone rolls by the line (526)
            and self.view.scroll.following
            and not self.always_shown
        )

    def age_of(self, key: int, now: float) -> float | None:
        """How long ago (`clock`) caption `key` arrived as text - None for
        one the window opened with, or not shown."""
        arrived = (self._arrived or {}).get(key)
        return None if arrived is None else now - arrived

    def _note_text(self) -> None:
        """When each caption in view arrived as text: a preview line when
        its finished caption came (284's New for)."""
        keys = [line.key for line in self.view.lines if not line.provisional]
        known, now = self._arrived, self.clock()
        if known is None:
            self._arrived = dict.fromkeys(keys)
            return
        self._arrived = {key: known.get(key, now) for key in keys}

    def _newness(self, now: float) -> tuple[bool, float | None]:
        """Whether a caption is fading back now (a frame each tick), and in
        how many seconds one next steps back or starts to - the Lab's New
        for; a repaint when what's new changed since the last."""
        lab = self.look.lab
        if lab.new_for <= 0.0 or self._arrived is None:
            return False, None
        state, fading, due = [], False, None
        for key, arrived in self._arrived.items():
            if arrived is None:
                continue
            age = now - arrived
            new = newness(age, lab)
            if new > 0.0:
                state.append((key, round(new, 3)))
            fading = fading or 0.0 < new < 1.0
            soon = changes_at(age, lab)
            if soon is not None:
                due = soon if due is None else min(due, soon)
        drawn = tuple(state)
        if drawn != self._newness_drawn:
            self._newness_drawn = drawn
            self.canvas.update()
        return fading, due

    def _note_arrivals(self, *, revealed_line: bool = False) -> None:
        """The new captions and paced lines, and how far the text in
        view rose for them since the last paint: sliding, it slides there
        instead of jumping, and the new lines enter from below, at the
        speech's pace - how long since the last caption, and whether speech
        is still under way. Stepping, they're simply there (F21)."""
        self._note_text()
        keys = {line.key for line in self.canvas.lines_in_view()}
        known, self._known = self._known, keys
        if known is None:
            return  # the captions it opens with are there
        new = keys - known
        now = self.clock()
        since = None if self._last_caption_at is None else now - self._last_caption_at
        if new:
            self._last_caption_at = now
        if not self.sliding:
            self.motion.stop()
            self.glide.stop()
            self.canvas.at_rest = {}  # what shows next isn't measured from this
            return
        if self.video_enabled:
            # Video starts its own entry when the live row is clear.
            self.motion.stop()
            return
        rest, before = self.canvas.rest_rows(), self.canvas.at_rest
        self.canvas.at_rest = rest
        if not new and not revealed_line:
            # Reflow at the live edge. Keep any arrival already in flight and
            # measure the next one from the edited layout.
            return
        # How far the oldest common row rose to make room for the new text.
        kept = rest.keys() & before.keys()
        risen = before[min(kept)] - rest[min(kept)] if kept else 0.0
        if self.deck is not None:
            if risen > 0.0:  # never from further than about a card below
                self._push(now, risen, new)
            return
        seconds = slide_seconds(pace_of(since, self.speaking))
        most = self.canvas.height()  # more at once can't be followed: at rest
        self.motion.start(now, max(0.0, risen), new, seconds, most_px=most)

    @property
    def arriving(self) -> bool:
        """A caption still sliding into place: the frame timer keeps going."""
        if not self.sliding:
            self.motion.stop()
            self.glide.stop()
        if self.deck is not None:
            now = self.clock()
            veiled = self._veil_at is not None
            moving = self.glide.moving(now)
            return veiled or moving or self.canvas.covering()
        return self.motion.moving(self.clock())

    @property
    def bar(self) -> BarInk:
        """Its chrome's colours, on its panel's (`bar_ink`)."""
        return bar_ink(self.look.background)

    def restyle(self) -> None:
        """Its chrome at the text size now - Windows' changed while it was
        open - and in its panel's colours; its captions keep the window's
        own size."""
        self.band.setStyleSheet(band_style(self.bar))
        self.tag.ink = self.bar
        self.notice.setStyleSheet(notice_style())
        self.pill.setStyleSheet(pill_style())
        if self.nudge is not None:
            self.nudge.restyle()
        self._draw_glyphs()
        self.tag.restyle()
        self._fit_band()
        self._place_overlays()  # its notice and Back to live, measured again
        self.canvas.update()

    def _engine(self, style: CaptionStyle) -> CaptionLayout:
        """A caption layout for `style`, its reading lines from the
        learner's dictionary (369)."""
        readings = (
            self._readings(style.reading_past, style.respelling_past)
            if self._readings
            else None
        )
        return CaptionLayout(style, lines_kept=self.view.keep, readings=readings)

    def reads(self, language: str | None) -> bool:
        """Whether a row in `language` can have a reading line here now:
        its dictionary is on this PC and read (369)."""
        found = reading_lines.reader(self.learner, language) if self.learner else None
        return found is not None and found.ready

    def dictionary_ready(self) -> None:
        """The dictionary's word split is read: rows laid out before it
        without their reading lines are laid out again with them (369) -
        and marks waiting on it drawn."""
        readings = self.canvas.engine.style.reading_lines and self._readings is not None
        if readings:
            self.canvas.engine = self._engine(self.canvas.engine.style)
        if self.view.refresh_link_classes() or readings:
            self._refresh()
        self.canvas.update()

    def refresh_link_classes(self) -> None:
        if self.view.refresh_link_classes():
            self._refresh()

    def set_look(self, look: CaptionLook) -> None:
        if look == self.look:
            return
        self.canvas.hold()
        recolour = look.background != self.look.background
        self.look = look
        style = self._style(look)
        if style != self.canvas.engine.style:  # laid out again: a font, link room
            self.canvas.engine = self._engine(style)
        self.canvas.ink = self._ink()
        self.marks.set_look(look.word_links, look.introductions, marks_panel(look))
        if recolour:  # its chrome in the panel's colours
            self.restyle()
        self._refresh_popovers()
        self._show_links()
        self._show_fill()
        self.show_every_line()
        self._configure_view()
        self._refresh()
        self._wake()
        if len(self.pacing):  # a gap changed or gone: those waiting, by it
            self._let_paced()

    def set_labels(self, labels: Mapping[SourceId, SourceLabel], you: str) -> None:
        """Each source's name and colour; `you`: what the mic is called."""
        own = labels.get(self.source)
        if own is not None and own != self.label:
            self.label = own
            self.setWindowTitle(_tr("{app} captions").format(app=own.name))
        mic = labels.get(self.mic) if self.mic else None
        self.labels = Labels(
            dict(labels), you=mic or SourceLabel(you, self.labels.you.color)
        )
        self._configure_view()
        self._sync_controls()  # the title, the tag, "Stop captioning ..."
        self._refresh()

    def set_timing(self, mode: CaptionMode) -> None:
        if self.timing is not mode:
            self._resume_timer.stop()
        self.timing = mode
        control = self.controls.get(mode.value)  # none for a retired mode
        if control is not None:
            control.setChecked(True)
        if not self._use_zones():
            self._configure_view()
        if self.path is ReadingPath.FOLLOW:  # Follow is the paced modes'
            self._path_changed()
        if hasattr(self, "timing_chip"):  # its name, once the bar is made
            self._fit_band()
        self._refresh_popovers()

    # -- Steady's two zones (views.zones; polyglotic-hq 526, decision 0251) -------

    def set_two_zones(self, on: bool) -> None:
        """Whether a paced mode shows the live lines below and the settled
        transcript above here (the learner's; on unless they turn it off)."""
        self.two_zones = on
        self._use_zones()

    def set_faint_ahead(self, on: bool) -> None:
        """Karaoke on or off (Steady's words ahead, the playout's)."""
        if on != self.faint_ahead:
            self.faint_ahead = on
            self.canvas.update()
            self.zone.update()

    def _style(self, look: CaptionLook | None = None) -> CaptionStyle:
        """The canvas's style for `look` (the window's): with two zones,
        the settled transcript's."""
        look = self.look if look is None else look
        if self.zones is not None:
            look = settled_look(look)
        elif self.cards_on and self.timing.paced:
            look = card_look(look)
        translation = (
            None
            if self.choices.translation_size == self.choices.text_size
            else self.choices.translation_size
        )
        style = self.path_style(caption_style(look, translation, self._mine_only()))
        if self.video_enabled:
            style = replace(
                style,
                fixed_script_size=True,
                smooth_track_fonts=True,
            )
        if self.video_enabled and look.lab.unfinished is Unfinished.AS_NOW:
            # Keep the typeface's advance widths as a draft settles. Its
            # ink still distinguishes the provisional words.
            return replace(style, italic_provisional=False)
        return style

    def _use_zones(self) -> bool:
        """Two zones on or off, as the mode and the learner's choice say.
        Coming on, the captions already here are the transcript."""
        cards = self.cards_on and self.timing.paced
        want = self.two_zones and self.timing.paced and not cards
        if want == (self.zones is not None) and cards == (self.deck is not None):
            return False
        self.canvas.hold()
        if self.deck is not None:  # put away: what was read stays as it stands
            self._show_kept()
            for card in self.deck.finish():
                self.view.apply(card)
            self._old_deck = self.deck
            self._dealt.clear()
        self.deck = None
        self.view.scroll.sticky = False
        self._dwell.stop()
        self.glide.stop()
        self.zones = Zones() if want else None
        if self.zones is not None:
            self.zones.settle(line.key for line in self.view.lines)
        else:
            self._zone_pause.stop()
        style = self._style()
        if style != self.canvas.engine.style:
            self.canvas.engine = self._engine(style)
        self._configure_view()
        self.show_every_line()
        self.zone.setVisible(want)
        self._place_zone()
        if cards:
            self._new_deck()
        self._refresh()
        return True

    def zone_room(self) -> float:
        """How much of the window's height the live zone takes, with the
        gap above it - none without two zones."""
        if self.zones is None or self.zone.height() <= 0:
            return 0.0  # nothing being read: the transcript has the window
        return float(self.zone.height() + ZONE_GAP)

    def _place_zone(self) -> None:
        """The live zone at the foot of the window: as many lines as
        `Zones.live_lines` says - fewer in a window too short for them and
        a line of transcript. Taller while a caption that began above
        those lines is still being read, so its first lines stay until all
        of it hands off (548's pictures, 2026-11-20: a long caption's
        first row was gone before the handoff); and no zone at all with
        nothing in it - after a pause the transcript has the whole window
        (the same day: the last caption was cut to its translation above
        an empty zone)."""
        if self.zones is None:
            return
        line = self.zone.line_height()
        most = max(1, int((self.height() - 2 * PAD - line) // line))
        lines = min(self.zones.live_lines(self.clock()), most)
        # each line with the gap under it but the newest, at the foot - as
        # `needed` stacks captions (559: the true pitch, 2 px a line more,
        # left the transcript above no room for a caption at 960 x 395)
        tall = math.ceil(line * lines - self.zone.gap_after()) + int(ZONE_TOP)
        room = max(0, self.height() - 2 * PAD)
        tall = min(tall, room)
        self.zone.lines_tall = float(tall)
        needed = self.zone.needed()
        if needed <= 0.0:
            tall = 0
        else:
            tall = min(max(tall, math.ceil(needed) + int(ZONE_TOP)), room)
        rect = QRect(0, self.height() - PAD - tall, self.width(), tall)
        if rect != self.zone.geometry():
            self.zone.setGeometry(rect)
            self.canvas.update()

    def _zone_changed(self, new_text: bool) -> None:
        """After the view changed: who spoke, the zone's size, and the
        captions that rolled out of it settle (the handoff by line)."""
        zones = self.zones
        if zones is None:
            return
        lines = self.view.lines
        zones.keep({line.key for line in lines})
        if new_text and lines:
            newest = lines[-1]
            zones.heard((newest.source, newest.by_you), self.clock())
            self._zone_pause.start()
        self._place_zone()
        if zones.settle(self.zone.rolled_out()):
            self._place_zone()  # as tall as what is still being read
            self.canvas.update()
        self.zone.update()

    def _zone_paused(self) -> None:
        """Nothing new for `PAUSE_SEC`: what the live zone holds settles -
        but a caption still being spoken."""
        zones = self.zones
        if zones is None:
            return
        if any(line.live for line in self.view.lines):
            self._zone_pause.start()
            return
        if zones.pause({line.key for line in self.view.lines}):
            self._place_zone()  # nothing being read: no zone
            self.canvas.update()
            self.zone.update()

    def placed(self) -> list[tuple[Line, LaidLine, QRectF]]:
        """Every caption drawn and where, in the window's coordinates: the
        canvas's and the live zone's."""
        if self.zones is None:
            return self.canvas.placed
        top = float(self.zone.y())
        return [
            *self.canvas.placed,
            *(
                (ln, laid, rect.translated(0.0, top))
                for ln, laid, rect in self.zone.placed
            ),
        ]

    def entry_changed(self, entry_id: EntryId, texts: tuple[str, ...]) -> None:
        """A Learning action changed one entry (`texts`: its forms): the
        captions holding it repaint - only those, and nothing is laid out."""
        forgotten = self.marks.forget(entry_id, texts)
        self.zone.update()
        for line, _, rect in self.placed():
            if line.key in forgotten:
                self.canvas.update(rect.toAlignedRect().adjusted(-4, -4, 4, 6))

    def load_changed(self, entries: frozenset[EntryId] | None) -> None:
        """Words of the learning load changed stage (None: any may have):
        the captions holding them repaint - nothing is laid out, nothing
        moves."""
        forgotten = self.marks.load_changed(entries)
        self.zone.update()
        if forgotten is None:
            self.canvas.update()
            return
        for line, _, rect in self.placed():
            if line.key in forgotten:
                self.canvas.update(rect.toAlignedRect().adjusted(-4, -4, 4, 6))

    def learning_changed(self, what: str) -> None:
        """Learning changed (a word saved, known, added to the deck): the
        marks showing are drawn again - nothing is laid out."""
        if self.marks.learning_changed(what):
            style = self.canvas.engine.style
            if style.follows_known:
                # a word known now or new again: its pinyin goes or comes
                self.canvas.engine = self._engine(style)
                self._refresh()
            self.canvas.update()

    def set_second_languages(self, seconds: Mapping[Language, Language]) -> None:
        self.second_languages = dict(seconds)
        self._configure_view()
        self._refresh()
        self._refresh_popovers()  # its "When they already speak ..." row

    def set_spoken_fallback(self, fallback: bool) -> None:
        """Whether its app is heard as Detect, not as its spoken language
        (`spoken_fallback`)."""
        if fallback != self.spoken_fallback:
            self.spoken_fallback = fallback
            self._refresh_popovers()

    def set_listening(self, listening: bool) -> None:
        if listening != self.listening:
            self.listening = listening
            # speech heard, or its mark gone: not quiet - a still mark
            # (reduced motion) doesn't keep the frame timer counting
            self._last_activity = time.monotonic()
            self.canvas.update()
            self._wake()

    def set_paused(self, paused: bool) -> None:
        self.notices.paused = paused
        self._wake()

    def set_minutes_used(self, used: bool) -> None:
        """Today's free minutes used: said on its notice line until there
        are more (after Paused; before the connection's state)."""
        self.notices.minutes_used = used
        self._wake()

    def set_failing(self, failing: bool) -> None:
        """Captions failing on the server: said on its notice line until a
        caption arrives again (after today's free minutes used)."""
        self.notices.failing = failing
        self._wake()

    def set_unstable(self, unstable: bool) -> None:
        """The connection keeps dropping: said on its notice line while it
        listens, until the connection has held again."""
        self.notices.unstable = unstable
        self._wake()

    def set_connection(self, notice: Notice | None, retry_in: float | None) -> None:
        self.notices.state = notice
        now = time.monotonic()
        self.notices.retry_at = now + retry_in if retry_in is not None else None
        self._wake()

    def set_hint(self, text: str | None) -> None:
        """A hint on its notice line while nothing else is said there
        (`Notices.hint`); None: gone."""
        if text == self.notices.hint:
            return
        self.notices.hint = text
        self._show_notice(time.monotonic())
        self._wake()

    def show_notice(self, text: str, seconds: float | None = None) -> None:
        """A brief notice (a server notice; a preset's name on snapping)."""
        now = time.monotonic()
        if seconds is None:
            self.notices.brief(text, now)
        else:
            self.notices.brief(text, now, seconds)
        self._show_notice(now)
        self._wake()

    # -- the learner's choices ---------------------------------------------------------

    def set_text_size(self, size: float) -> None:
        """Caption size (original text only): live; the window keeps its size
        and translation size stays untouched (655)."""
        with spans.span("caption_window.text_size"):
            self._set_text_sizes(size, self.choices.translation_size)

    def step_text(self, steps: int) -> None:
        self.set_text_size(stepped(self.view.text_size, steps, CAPTION_TEXT_SIZES))

    def set_translation_size(self, size: float) -> None:
        """Translation size (independent of caption size, TRANSLATION_SIZES):
        live, laid out again; the window keeps its size and caption size stays
        untouched (655)."""
        with spans.span("caption_window.translation_size"):
            self._set_text_sizes(self.choices.text_size, size)

    def _set_text_sizes(
        self, caption: float, translation: float, *, zoom_ratio: float | None = None
    ) -> None:
        """Lay out both rows and publish their saved choices together."""
        self.view.set_text_size(caption)
        caption = self.view.text_size
        translation = stepped_translation(translation, 0)
        if (caption, translation) == (
            self.choices.text_size,
            self.choices.translation_size,
        ):
            return
        self._wheel_zoom_ratio = zoom_ratio
        self.choices = replace(
            self.choices, text_size=caption, translation_size=translation
        )
        style = self._style()
        if style != self.canvas.engine.style:
            self.canvas.engine = self._engine(style)
        self._sync_translation_size()
        self._refresh()
        self.canvas.repaint()
        self._tip_text_size()
        if self.popover is not None and self.popover.isVisible():
            self.popover.refresh()
        self.changed.emit()

    def _step_text_sizes(self, step: int) -> None:
        """Scale both rows by the caption's A-/A+ step within both rows' limits."""
        caption = self.choices.text_size
        ratio = self._wheel_zoom_ratio or self.choices.translation_size / caption
        low, high = CAPTION_TEXT_SIZES  # both rows share these limits
        target = stepped(caption, step, CAPTION_TEXT_SIZES)
        smallest = max(low, low / ratio)
        largest = min(high, high / ratio)
        caption = min(largest, max(smallest, target))
        with spans.span("caption_window.text_size"):
            self._set_text_sizes(caption, caption * ratio, zoom_ratio=ratio)

    def match_translation_size(self) -> None:
        """Set the translation size equal to the caption size (655)."""
        self.set_translation_size(self.choices.text_size)

    def _mine_only(self) -> bool:
        """It captions the mic alone: all its lines are yours."""
        return bool(self.mic) and self.source == self.mic

    def step_translation(self, steps: int) -> None:
        self.set_translation_size(
            stepped_translation(self.choices.translation_size, steps)
        )

    def _sync_translation_size(self) -> None:
        """Keep caption and translation A-/A+ within bounds, and Match
        enabled only when the two sizes differ (655)."""
        cap_low, cap_high = CAPTION_TEXT_SIZES
        cap = self.choices.text_size
        self.controls["smaller"].setEnabled(cap > cap_low)
        self.controls["bigger"].setEnabled(cap < cap_high)
        low, high = TRANSLATION_SIZES
        size = self.choices.translation_size
        self.controls["translation_smaller"].setEnabled(size > low)
        self.controls["translation_bigger"].setEnabled(size < high)
        self.controls["translation_same"].setEnabled(size != cap)

    save_preset_language: Callable[[str, str], None] | None = None

    def choose_bar_language(self, field: str, code: str) -> None:
        """A choice from the language chip or its folded gear menu."""
        current = getattr(self.choices, field) or ""
        if code == current:
            return
        if self.save_preset_language is not None:
            self.save_preset_language(field, code)
        elif field == "spoken_language":
            self.set_spoken_language(code or None)
        else:
            self.set_language(code)

    def set_language(self, code: str) -> None:
        """This window's translation language; ORIGINAL_ONLY for none."""
        if code == self.choices.translate_into:
            return
        with spans.span("caption_window.language"):
            self.choices = replace(self.choices, translate_into=code)
            self._configure_view()
            if self.path is ReadingPath.FOLLOW:  # with a translation or none
                self._path_changed()
            self._refresh()
            if not self._batching_settings:
                self.canvas.repaint()
        self._sync_controls()
        self.changed.emit()
        self.language_changed.emit()

    def suggest_spoken(self, code: str) -> None:
        """Detect has heard its app speak `code` steadily: asks whether to
        always hear it as that (`spoken_nudge`) - not while it names a
        language already."""
        if self.choices.spoken_language is not None:
            return
        if self.nudge is None:
            self.nudge = SpokenNudge(self)
            self.nudge.answered.connect(self._nudge_answered)
            self.nudge.went.connect(self._nudge_went)
        self.nudge.ask(code)
        self.nudge.setVisible(not self.locked)
        self._place_overlays()
        self.canvas.update()  # the captions make room for it

    def _nudge_answered(self, yes: bool) -> None:
        nudge = self.nudge
        if nudge is None or nudge.code is None:
            return
        code, nudge.code = nudge.code, None
        nudge.hide()
        self.canvas.update()
        if yes:
            self.set_spoken_language(code)
        else:
            self.spoken_declined.emit(code)

    def _nudge_went(self) -> None:
        """Shown its while (`spoken_nudge.SHOWN_MS`) and not answered: it
        goes, and isn't asked again until the app starts again."""
        nudge = self.nudge
        if nudge is None or nudge.code is None:
            return
        code, nudge.code = nudge.code, None
        nudge.hide()
        self.canvas.update()
        self.spoken_unanswered.emit(code)

    def question_foot(self) -> float:
        """Where captions start below the spoken-language question while it
        shows (0 while it doesn't): it never covers a caption (350)."""
        nudge = self.nudge
        if nudge is None or nudge.code is None or not nudge.isVisible():
            return 0.0
        return float(nudge.geometry().bottom() + 1 + 4)

    @property
    def asking_spoken(self) -> str | None:
        """The language it's asking to always hear its app as, if any."""
        return self.nudge.code if self.nudge is not None else None

    def set_spoken_language(self, code: str | None) -> None:
        """The language its app's speech is in (one of SPOKEN_LANGUAGES);
        None: Detect."""
        if self.nudge is not None and self.nudge.code is not None:
            self.nudge.code = None  # named, or Detect chosen: not asked
            self.nudge.hide()
            self.canvas.update()
        if (code or None) == self.choices.spoken_language:
            return
        self.choices = replace(self.choices, spoken_language=code or None)
        self._sync_controls()
        self.changed.emit()
        self.language_changed.emit()

    def set_second(self, second: str) -> None:
        """Its lines already in its translation language: shown in `second`
        ("": left as they are) - asked of the app, which keeps it by
        language (`second_wanted`)."""
        target = self.choices.target
        if target is not None and second != (self._second() or ""):
            self.second_wanted.emit(str(target), second)

    def set_show_mic(self, on: bool) -> None:
        if on == self.choices.show_mic:
            return
        self.choices = replace(self.choices, show_mic=on)
        self.view.show_sources(self._sources())
        self._sync_controls()
        if self.host is not None:
            self.host.strips_changed()
        self.changed.emit()
        self.mic_changed.emit()

    def set_preset(self, preset: Preset) -> None:
        """At a preset's place; the size kept."""
        area = self._area()
        size = Size(self.width(), self.height())
        rect = placement.slot(preset, area, size)
        self.choices = replace(self.choices, preset=preset, geometry=rect)
        self._set_place(rect)
        self.changed.emit()

    def reset_position(self) -> None:
        """Its default slot and size, at Bottom centre."""
        area = self._primary()
        rect = placement.slot(
            Preset.BOTTOM_CENTRE, area, placement.default_size(area), self.index
        )
        self.choices = replace(self.choices, preset=Preset.BOTTOM_CENTRE, geometry=None)
        self._set_place(rect)
        self.introduce()  # shown where it now is (DECISIONS.md #56)
        self.changed.emit()

    def take_place(
        self,
        preset: Preset,
        geometry: Rect | None,
        text_size: float,
        translation_size: float | None = None,
    ) -> None:
        """At `geometry` - None: `preset`'s slot at the default size - and
        `text_size` (and `translation_size` if given), as its choices: Video's
        subtitles and back (polyglotic-hq 556, 655). At once, as a snap is: a
        window's place is one step. Says nothing changed - `CaptionWindows`
        keeps its own place apart while it's a subtitle."""
        self._wheel_zoom_ratio = None
        self.choices = replace(self.choices, preset=preset, geometry=geometry)
        self.view.set_text_size(text_size)
        self.choices = replace(self.choices, text_size=self.view.text_size)
        if translation_size is not None:
            trans = stepped_translation(translation_size, 0)
            if trans != self.choices.translation_size:
                self.choices = replace(self.choices, translation_size=trans)
                self.canvas.engine = self._engine(self._style())
        self._sync_translation_size()
        area = self._area() if self.isVisible() else self._primary()
        rect = geometry or placement.slot(
            preset, area, placement.default_size(area), self.index
        )
        self._set_place(rect)
        self._refresh()
        if not self._batching_settings:
            self.canvas.repaint()

    def subtitle_height(
        self,
        text_size: float,
        translation_size: float | None = None,
    ) -> int:
        """Room for the chosen number of subtitle lines and the hover band."""
        engine = self.canvas.engine
        if engine.style.translation_size != translation_size:
            engine = self._engine(
                replace(engine.style, translation_size=translation_size)
            )
        chrome = int(band_height())
        if self.choices.show_mic:
            chrome += self.canvas._own_subtitle_height()
        return math.ceil(
            chrome
            + VIDEO_MARGIN
            + subtitle_height(
                engine,
                text_size,
                self.video_languages(),
                self.video_sides(),
                self.preset_menu.video_lines_shown,
                any(line.label for line in self.view.lines),
            )
        )

    def video_sides(self) -> tuple[bool, bool]:
        show = self.preset_menu.show
        translated = self.choices.target is not None
        return show is not Show.TRANSLATION or not translated, (
            show is not Show.ORIGINAL and translated
        )

    def video_languages(self) -> tuple[Language | None, Language | None]:
        spoken = self.choices.spoken_language
        return Language(spoken) if spoken else None, self.choices.target

    def text_px(self) -> float:
        """Its captions' text in pixels at 100 % text size."""
        return float(self.canvas.engine.style.text_px)

    def area_now(self) -> Rect:
        """The work area it's on (its centre's screen)."""
        return self._area() if self.isVisible() else self._primary()

    def set_locked(self, locked: bool, at_length: bool = False) -> None:
        """Locked: clicks pass through; no band, no hover, no resizing.
        `at_length`: it says how to unlock at more length (the first lock on
        Linux, 570)."""
        if locked == self.locked:
            return
        self.locked = locked
        if self.isWindow():  # a column passes clicks through with its window
            set_click_through(self, locked)  # re-mapped, never live (550)
        if locked:
            if self.resize_hint is not None:
                self.resize_hint.hide()
            self.hovered = False
            self.let_in()
            self._stop_looking_for_pointer()
            self._let_go_of_word()
            self._show_band(False)
            self.go_live()
            if at_length:
                self.show_notice(first_locked_text(self.unlock_keys), FIRST_LOCKED_SEC)
            else:
                self.show_notice(locked_text(self.unlock_keys), LOCKED_SEC)
        self.unlock_spot.watch(locked and self.isVisible())
        self._show_set_up()  # not over a locked window: clicks pass through it
        if self.nudge is not None:  # clicks pass through a locked window
            self.nudge.setVisible(not locked and self.nudge.code is not None)
            self._place_overlays()
        self.canvas.update()
        self._wake()

    def set_unlock_keys(self, keys: str) -> None:
        """The hotkey that unlocks now ("" if it doesn't work here)."""
        if keys != self.unlock_keys:
            self.unlock_keys = keys
            self.controls["lock"].setToolTip(lock_tip(keys))
            self.canvas.update()

    def _lock_spot(self) -> QRect | None:
        """The lock in its corner, on the screen, while it shows one: where
        resting the mouse offers Unlock (`unlock_spot`) - None unlocked,
        hidden, or a joined window's column but the last."""
        if not self.locked or not self.isVisible():
            return None
        spot = self.canvas.lock_spot()
        if spot is None:
            return None
        return QRect(self.canvas.mapToGlobal(spot.topLeft()), spot.size())

    def go_live(self) -> None:
        self._resume_timer.stop()
        self._hold_timer.stop()
        if self.view_held() is not None and self.view.scroll.following:
            self._release_view()  # Back to live while the mouse held the view
            return
        self._view_held = None
        self._mouse_anchor = None
        if self.deck is not None:
            if self.sliding and self._far_from_home():
                # too far to slide: the whole view fades out, comes home
                # unseen, and fades in at rest - no cards flashing past
                if not self._veil.isActive():
                    self._veil_at = self.clock()
                    self._veil.start(int(VEIL_SEC * 500))
                    self._wake()
                return
            # the cards slide home: one slide, all the way
            self._scrolled(self.view.scroll.follow, back=False, home=True)
            return
        self.view.scroll.follow()
        self._refresh()

    def set_live_keys(self, keys: str) -> None:
        """Back to live's hotkey as the OS writes it ("" none), on its tip
        (polyglotic-hq 567)."""
        self.pill.setToolTip(live_tip(keys))

    # -- in a joined window -------------------------------------------------------------

    def set_host(self, host: "JoinedWindow | None") -> None:
        """A column of `host` - a child widget, with no window of its own -
        or a window of its own again, at its own place, in its own mode. Not
        shown: the caller shows it. Its captions, scroll-back and layouts
        are the same either way."""
        if host is self.host:
            return
        self.close_settings()
        self._let_go_of_word()
        if self.popover is not None:  # its rows differ: made again when next opened
            self.popover.deleteLater()
            self.popover = None
        if self.set_up is not None:  # still asked: over it again where it shows (554)
            self.set_up.hide()
        self._show_band(False)
        self.hovered = False
        self.let_in()
        self.host = host
        if host is not None:
            self.setParent(host)
        else:
            flags = WINDOW_FLAGS
            if self.locked:
                flags |= Qt.WindowType.WindowTransparentForInput
            self.setParent(None, flags)
            self.setWindowOpacity(self._alpha)
            self.setGeometry(to_qrect(self._start_place()))
        self.host_changed()
        self.introduce()  # joined, or back at its own place: shown there

    def host_changed(self) -> None:
        """Its joined window's columns or mode changed: its strip fitted
        again, and drawn; its notices where they now show."""
        self._fit_band()
        self._refresh()
        self._wake()

    def inner_sides(self) -> tuple[bool, bool]:
        """Whether another column of its joined window is beyond its left
        edge, and beyond its right."""
        host = self.host
        if host is None or self not in host.columns:
            return False, False
        index = host.columns.index(self)
        return index > 0, index < len(host.columns) - 1

    def show_band(self, shown: bool) -> None:
        """Its strip shown or gone: a joined window shows its columns' together."""
        self._show_band(shown)

    def set_hovered(self, hovered: bool) -> None:
        """The mouse over its joined window: the whole panel is drawn. New
        captions wait only while it's on a column's words (`_hold_on_words`)."""
        hovered = hovered and not self.locked
        if not hovered:
            self.let_go()
        if hovered != self.hovered:
            self.hovered = hovered
            self.canvas.update()
            self._wake()

    # -- the controls -------------------------------------------------------------------

    def _action(
        self,
        name: str,
        text: str,
        tip: str = "",
        slot: Callable[[], object] | None = None,
        glyph: Glyph | None = None,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setObjectName(f"caption_window.{name}")
        if glyph is not None:
            self.glyphs[name] = glyph  # the strip's button; the popover shows the text
        action.setToolTip(tip or text)
        action.setCheckable(checkable)
        if slot is not None:
            action.triggered.connect(slot)
        self.controls[name] = action
        return action

    def _choices(self, choices: tuple[tuple[str, str, str], ...]) -> list[QAction]:
        """Checkable actions, one of them checked at a time."""
        group = QActionGroup(self)
        found = []
        for name, text, tip in choices:
            action = self._action(name, text, tip, checkable=True)
            group.addAction(action)
            found.append(action)
        return found

    def _build_controls(self) -> None:
        """Every control of the window, once each, as a named action
        (`controls`): the hover strip draws those named in STRIP, the
        settings popover the rest (`settings_popover.ROWS`)."""
        self.controls: dict[str, QAction] = {}
        self.glyphs: dict[str, Glyph] = {}
        """The controls whose strip button is an icon, not words."""
        self._action(
            "links",
            _tr("Word links"),
            _tr("Word links on or off. Colours show word class."),
            glyph=Glyph.LINKS,
            checkable=True,
        ).triggered.connect(
            lambda on: self.links_wanted.emit(bool(on), self.readings())
        )
        self._action(
            "quiet",
            _tr("Quiet view"),
            quiet_tip(),
            glyph=Glyph.QUIET,
            checkable=True,
        ).triggered.connect(
            lambda on: self.quiet_wanted.emit(bool(on), self.readings())
        )
        for which, text in (
            (ChosenWords.CURRICULUM, _tr("Our curriculum")),
            (ChosenWords.EDGE, _tr("Words at your edge")),
            (ChosenWords.LOAD, _tr("Learning load")),
            (ChosenWords.SAVED, _tr("Saved words")),
        ):
            self._action(
                f"quiet_{which.value}", text, checkable=True
            ).triggered.connect(
                lambda on, which=which: self.quiet_word_wanted.emit(
                    which.value, bool(on)
                )
            )
        self._action(
            "fill",
            _tr("Fill the width"),
            _tr(
                "Fill the width on or off, in every window: captions run on, line "
                "by line, in lines as wide as the window - each line of what was "
                "said over its translation"
            ),
            glyph=Glyph.FILL,
            checkable=True,
        ).triggered.connect(lambda on: self.fill_wanted.emit(bool(on)))
        self._action(
            "aligned",
            _tr("Line up the parts"),
            _tr(
                "Line up the parts on or off, in every window: each part of what "
                "was said starts at the same place as its translation, so a word's "
                "translation is under it"
            ),
            glyph=Glyph.ALIGNED,
            checkable=True,
        ).triggered.connect(lambda on: self.aligned_wanted.emit(bool(on)))
        self._action(
            "said_colours",
            _tr("Colour linked words in what was said"),
            checkable=True,
        ).triggered.connect(lambda on: self.said_colours_wanted.emit(bool(on)))
        self._action(
            "translation_colours",
            _tr("Colour linked words in the translation"),
            checkable=True,
        ).triggered.connect(lambda on: self.translation_colours_wanted.emit(bool(on)))
        self._action(
            "smaller",
            "A-",
            hotkeys_here(_tr("Smaller text (Ctrl+wheel)")),
            lambda: self.step_text(-1),
        )
        self._action(
            "bigger",
            "A+",
            hotkeys_here(_tr("Bigger text (Ctrl+wheel)")),
            lambda: self.step_text(1),
        )
        self._action(
            "translation_smaller",
            "A-",
            _tr("Smaller translation"),
            lambda: self.step_translation(-1),
        )
        self._action(
            "translation_bigger",
            "A+",
            _tr("Bigger translation"),
            lambda: self.step_translation(1),
        )
        self._action(
            "translation_same",
            _tr("Match"),
            _tr("Set the translation size equal to the caption size"),
            self.match_translation_size,
        )
        self._sync_translation_size()
        self._action(
            "lock",
            _tr("Lock all windows"),
            lock_tip(self.unlock_keys),
            self.lock_wanted.emit,
            glyph=Glyph.LOCK,
        )
        self._action(
            "settings",
            _tr("Settings"),
            _tr("This window's settings: its translation, timing and more"),
            self.toggle_settings,
            glyph=Glyph.SETTINGS,
        )
        self._action("stop", "", slot=self.stop_wanted.emit, glyph=Glyph.CLOSE)
        self._action(
            "report",
            _tr("Report a problem"),
            _tr(
                "Report a problem - with what was shown and heard, which you check "
                "first"
            ),
            self.report_wanted.emit,
            glyph=Glyph.REPORT,
        )
        self._action(
            "start_like_this",
            _tr("Start new windows like this"),
            _tr(
                "New caption windows take this one's languages - what they "
                "speak too, not Detect"
            ),
            checkable=True,
        ).triggered.connect(lambda on: self.start_like_this_wanted.emit(bool(on)))
        self._action(
            "ask_set_up",
            _tr("Ask when a window opens"),
            _tr(
                "A caption window that opens asks what they speak and what to "
                "translate into, until you choose Use as my default there"
            ),
            checkable=True,
        ).triggered.connect(lambda on: self.ask_set_up_wanted.emit(bool(on)))
        self._action(
            "lyrics",
            _tr("Lyrics"),
            _tr(
                "Caption the singing in music players heard on Detect: their "
                "sound is sent even while no speech is heard, a few seconds at a "
                "time. Off: only what's heard as speech is sent"
            ),
            checkable=True,
        ).triggered.connect(lambda on: self.lyrics_wanted.emit(bool(on)))
        self._action(
            "show_mic",
            _tr("Show my speech here"),
            _tr("Your microphone is sent for your captions only while this is on"),
            checkable=True,
        ).triggered.connect(lambda on: self.set_show_mic(bool(on)))
        for action, timing in zip(
            self._choices(
                tuple((m.value, timing_name(m), timing_tip(m)) for m in OFFERED_MODES)
            ),
            OFFERED_MODES,
            strict=True,
        ):
            action.triggered.connect(
                lambda _=False, t=timing: self.timing_wanted.emit(t.value)
            )
        self._action(
            "all_settings",
            _tr("All caption settings…"),
            _tr(
                "Colours, font, word links, timing and the rest - for every "
                "window, in Settings"
            ),
            self.all_settings_wanted.emit,
        )
        self._action(
            "copy_all",
            _tr("Copy all captions"),
            _tr("Every caption this window holds, with its time and translation"),
            self.copy_all,
        )
        self._action(
            "transcript",
            _tr("Open transcript"),
            _tr("Everything said in this app, to read back, search and save"),
            self.transcript_wanted.emit,
        )
        self._action(
            "join",
            _tr("Join windows"),
            _tr("Every caption window side by side in one window"),
            self.join_wanted.emit,
        )

    def _build_band(self) -> None:
        band = self.band = QWidget(self)
        band.setObjectName("caption_window.band")
        band.setMouseTracking(True)  # the band's gaps pass the mouse to the window
        band.setStyleSheet(band_style(self.bar))
        row = QHBoxLayout(band)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(STRIP_GAP_PX)
        self.tag = SourceTag(band)
        self.tag.ink = self.bar
        self.tag.setMouseTracking(True)
        # the label takes what it needs, and is what shortens when it's narrow
        self.tag.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row.addWidget(self.tag)
        chip = self.chip = QToolButton(band)
        chip.setObjectName("caption_window.band.languages")
        chip.setProperty("chip", True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setMouseTracking(True)
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        chip.clicked.connect(self.toggle_languages)
        row.addWidget(chip)
        row.addStretch(1)
        # the preset chip ("Video ▾", polyglotic-hq 556): its dropdown
        chip = self.preset_chip = QToolButton(band)
        chip.setObjectName("caption_window.band.presets")
        chip.setProperty("chip", True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setMouseTracking(True)
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        chip.clicked.connect(self.toggle_presets)
        row.addWidget(chip)
        # the timings the preset offers (polyglotic-hq 593)
        chip = self.timing_chip = QToolButton(band)
        chip.setObjectName("caption_window.band.timing")
        chip.setProperty("chip", True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setMouseTracking(True)
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        chip.clicked.connect(self.toggle_timings)
        row.addWidget(chip)
        self._chips = (self.chip, self.preset_chip, self.timing_chip)
        self.strip_labels = StripLabels.FULL
        # A hidden button measures the same style as the chip it sizes,
        # without changing any visible button's contents or focus.
        self._chip_probe = QToolButton(band)
        self._chip_probe.setProperty("chip", True)
        self._chip_probe.hide()
        self._chip_widths: dict[str, int] = {}
        self.mic_button = MicButton(band)
        self.mic_button.clicked.connect(lambda on: self.set_show_mic(bool(on)))
        row.addWidget(self.mic_button)
        # a capped plan's allowance left (684): hidden on an unlimited plan
        self.usage_ring = UsageRing(band)
        row.addWidget(self.usage_ring)
        self.buttons: dict[str, QToolButton] = {}
        for name in STRIP:
            action = self.controls[name]
            button = QToolButton(band)
            button.setObjectName(f"caption_window.band.{name}")
            button.setDefaultAction(action)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMouseTracking(True)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.buttons[name] = button
            row.addWidget(button)
        # the window is never active, so Qt never shows their tooltips (395)
        self.tips = StripTips(self)
        self.tips.watch(self.tag, self.tag.tip_at)
        for name, button in self.buttons.items():
            if name == "links":
                self.tips.watch(
                    button,
                    lambda _: legend_html(self.look, self.controls["links"].toolTip()),
                )
            else:
                self.tips.watch(button)
        self.tips.watch(self.chip)
        self.tips.watch(self.preset_chip)
        self.tips.watch(self.timing_chip)
        self.tips.watch(self.mic_button)
        self.tips.watch(self.usage_ring)
        self._draw_glyphs()
        band.hide()
        self.set_timing(self.timing)
        self._sync_controls()

    def _draw_glyphs(self) -> None:
        """The strip's icon buttons' icons, at the text size now and in its
        panel's colours, each as wide as its glyph was (`glyphs.text_width`)."""
        side = style.px(GLYPH_PX)
        ink = self.bar
        for name, glyph in self.glyphs.items():
            self.controls[name].setIcon(
                icon(glyph, ink.text, side, disabled=ink.disabled)
            )
            if name in self.buttons:
                fit_glyph(self.buttons[name], side)
        for chip, glyph in zip(
            self._chips, (Glyph.LANGUAGES, Glyph.PRESET, Glyph.TIMING), strict=True
        ):
            chip.setIcon(icon(glyph, ink.text, side, disabled=ink.disabled))
            chip.setIconSize(QSize(side, side))
        probe = self._chip_probe
        probe.setIcon(self.timing_chip.icon())
        probe.setIconSize(self.timing_chip.iconSize())
        probe.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        probe.ensurePolished()
        self._icon_chip_width = probe.sizeHint().width()
        self._chip_widths.clear()
        self.mic_button.set_ink(ink, side)
        self.usage_ring.set_ink(
            ink.text,
            ink.disabled,
            readable_on(LOW_COLOUR, self.look.background, BAR_CONTRAST),
            side,
        )

    def _sync_controls(self) -> None:
        """The controls show the window's choices."""
        on = self.choices.show_mic
        self.controls["show_mic"].setChecked(on)
        self.mic_button.setChecked(on)
        tip = mic_button_tip(on)
        self.mic_button.setToolTip(tip)
        self.mic_button.setAccessibleName(_tr("Caption what I say"))
        self.mic_button.setAccessibleDescription(tip)
        if not on:
            self.mic_button.show_level(None)
        self._show_links()
        self._show_fill()
        stop = _tr("Stop captioning {app}").format(app=self.label.name)
        self.controls["stop"].setText(style.button_text(stop))
        self.controls["stop"].setToolTip(stop)
        self._name_buttons()
        self._fit_band()
        self._refresh_popovers()

    def _refresh_popovers(self) -> None:
        """Every popover of its that shows says its choices as they are now."""
        for each in (*self._strip_popovers(), self.set_up):
            if each is not None and each.isVisible():
                each.refresh()

    def _show_links(self) -> None:
        """The strip's word links button: on or off. With what was said
        hidden it can change nothing - a link joins a word of what was said
        to its translation - so it's off to clicks and says why, in Look's
        words (249's F9; polyglotic-hq 258)."""
        links = self.controls["links"]
        links.setChecked(self.look.word_links is not WordLinks.OFF)
        self.controls["quiet"].setChecked(self.look.quiet)
        links.setEnabled(self.look.show_original)
        links.setToolTip(
            _tr("Word links on or off. Colours show word class.")
            if self.look.show_original
            else _tr(
                "Word links need what was said: turn on “Show the original above "
                "the translation” in Settings"
            )
        )

    def _show_fill(self) -> None:
        """The strip's filled lines button: on while the Lab's New layout,
        Line by line and Captions run on all are - the same values, so a
        change in either place shows in both (372); and its parts lined up
        button, on while New layout and Parts lined up are."""
        self.controls["fill"].setChecked(self.look.lab.filled)
        self.controls["aligned"].setChecked(self.look.lab.lined_up)
        linked = self.look.word_links is not WordLinks.OFF  # else nothing to colour
        for name, on in (
            ("said_colours", self.look.said_in_link_colours),
            ("translation_colours", self.look.translation_in_link_colours),
        ):
            self.controls[name].setChecked(on)
            self.controls[name].setEnabled(linked)
        for which in ChosenWords:
            self.controls[f"quiet_{which.value}"].setChecked(
                which in self.look.quiet_words
            )

    def _name_buttons(self) -> None:
        """What a screen reader says for each of the strip's buttons: its
        action's words, never nothing for an icon."""
        for name, button in self.buttons.items():
            button.setAccessibleName(self.controls[name].text())

    def set_reporting(self, on: bool) -> None:
        """Show "Report a problem" on the strip: an alpha tester's (275)."""
        if on != self.reporting:
            self.reporting = on
            self._fit_band()
            if self.host is not None:
                self.host.strips_changed()

    def _fit_band(self) -> None:
        # a column: lock is the joined window's, at the right of the last
        self.buttons["lock"].setVisible(self.host is None)
        self.buttons["report"].setVisible(self.reporting)
        room = self.host.controls_width(self) if self.host is not None else 0
        width = max(0, self.width() - 2 * placement.CORNER_ZONE - room)
        target = self.choices.target
        languages = language_chip_label(self.choices.spoken_language, target)
        preset = preset_chip_label(self.preset_menu)
        timing = timing_chip_label(self.timing, self.preset_menu.chosen)
        names = (
            in_sentence(_tr("Languages: {languages}"), languages=languages),
            preset_chip_name(self.preset_menu),
            timing_chip_name(self.timing, self.preset_menu.chosen),
        )
        full = (languages + " ", preset, timing)
        full_widths = tuple(self._chip_width(label) for label in full)
        self.mic_button.setVisible(self.mic_offered())
        controls_width = self._strip_buttons_width()
        full_room = width - controls_width - sum(full_widths)
        self.tag.show_label(self.label, False, self.theme_words())
        tag_room = self.tag.short_width()
        was_icons = self.strip_labels is StripLabels.ICONS
        if full_room >= tag_room:
            self.strip_labels = StripLabels.FULL
            labels, widths = full, full_widths
        else:
            #: Caption bar at a narrow width: only the translation language's code.
            short_language = (
                _tr("→ {code}").format(code=target.upper())
                if target
                else _tr("Original only")
            )
            metrics = self._chip_probe.fontMetrics()
            short_preset = metrics.elidedText(
                preset, Qt.TextElideMode.ElideRight, style.px(SHORT_PRESET_PX)
            )
            labels = (short_language + " ", short_preset, timing)
            widths = tuple(self._chip_width(label) for label in labels)
            if width - controls_width - sum(widths) >= tag_room:
                self.strip_labels = StripLabels.SHORT
            else:
                self.strip_labels = StripLabels.ICONS
                widths = (self._icon_chip_width,) * len(self._chips)
        icons = self.strip_labels is StripLabels.ICONS
        if icons != was_icons:
            row = self.band.layout()
            assert isinstance(row, QHBoxLayout)
            row.removeWidget(self.chip)
            # Cross the stretch so the globe sits directly beside the other icons.
            row.insertWidget(
                row.indexOf(self.preset_chip) if icons else row.indexOf(self.tag) + 1,
                self.chip,
            )
        self.tag.show_dot(icons)
        self.tag.setMinimumWidth(self.tag.icon_width() if icons else tag_room)
        overflow_changed = False
        visible = dict.fromkeys(self._chips, True)
        if icons:
            room = width - controls_width - self.tag.icon_width() - sum(widths)
            for chip in (self.timing_chip, self.chip, self.preset_chip):
                if room >= 0:
                    break
                visible[chip] = False
                room += self._icon_chip_width + STRIP_GAP_PX
        popovers = (self.languages, self.presets, self.timings)
        for chip, label, name, wide, opened in zip(
            self._chips, labels, names, widths, popovers, strict=True
        ):
            if chip.accessibleName() != name:
                chip.setAccessibleName(name)
                chip.setToolTip(name)
            chip.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if icons
                else Qt.ToolButtonStyle.ToolButtonTextOnly
            )
            chip.setText(
                ""
                if icons
                else dropdown_label(label, opened is not None and opened.isVisible())
            )
            chip.setFixedWidth(wide)
            overflow_changed |= chip.isHidden() == visible[chip]
            chip.setVisible(visible[chip])
        # inside the corner zones, so every edge still resizes
        self.band.setGeometry(
            placement.CORNER_ZONE,
            placement.EDGE_ZONE - 1,
            width,
            band_height() - placement.EDGE_ZONE,
        )
        layout = self.band.layout()
        assert layout is not None
        layout.activate()
        for chip, popover in zip(self._chips, popovers, strict=True):
            if popover is not None and popover.isVisible():
                popover.follow_anchor(self._chip_anchor(chip))
        for popover in (self.popover, self.bar_controls):
            if popover is not None and popover.isVisible():
                popover.follow_anchor(self._chip_anchor(self.buttons["settings"]))
                if overflow_changed:
                    popover.refresh()
        if self.band_shown and self.host is None and self.notice.isVisible():
            self._place_overlays()

    def _strip_buttons_width(self) -> int:
        """Room for the fixed buttons and all three chip gaps."""
        return len(self._chips) * STRIP_GAP_PX + sum(
            laid_width(button) + STRIP_GAP_PX
            for button in (*self.buttons.values(), self.mic_button, self.usage_ring)
            if not button.isHidden()
        )

    def _chip_width(self, label: str) -> int:
        if label not in self._chip_widths:
            probe = self._chip_probe
            probe.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            widths = []
            for opened in (False, True):
                probe.setText(dropdown_label(label, opened))
                widths.append(probe.sizeHint().width())
            self._chip_widths[label] = max(widths)
        return self._chip_widths[label]

    def _chip_anchor(self, chip: QToolButton) -> QRect:
        if chip.isHidden():
            chip = self.buttons["settings"]
        return QRect(chip.mapToGlobal(QPoint()), chip.size())

    # -- the settings popover ----------------------------------------------------------

    @property
    def settings_open(self) -> bool:
        """Its settings popover or its languages' is open."""
        return any(
            each is not None and each.isVisible() for each in self._strip_popovers()
        )

    def _strip_popovers(self) -> tuple[SettingsPopover | None, ...]:
        return (
            self.popover,
            self.bar_controls,
            self.languages,
            self.presets,
            self.timings,
        )

    @property
    def keyboard_bar_open(self) -> bool:
        return any(
            each is not None and each.keyboard and each.isVisible()
            for each in self._strip_popovers()
        )

    def toggle_settings(self, *, keyboard: bool = False) -> None:
        """The settings popover, beside the settings button - or closed."""
        if self.popover is not None and self.popover.isVisible():
            self.close_settings()
            return
        self.close_settings()
        if self.locked or not self.isVisible():
            return
        with spans.span("caption_window.settings"):
            if self.popover is None:
                rows = COLUMN_ROWS if self.host is not None else ROWS
                self.popover = SettingsPopover(self, self.keys, rows)
            self.popover.open_beside(
                self._chip_anchor(self.buttons["settings"]), keyboard=keyboard
            )

    def open_bar_controls(self) -> None:
        """The bar's dropdowns and own-speech switch, reached through an explicit keyboard shortcut."""
        if self.locked or not self.isVisible():
            return
        self.close_settings()
        self._show_band(True)
        if self.bar_controls is None:
            self.bar_controls = SettingsPopover(self, self.keys, KEYBOARD_BAR_ROWS)
        self.bar_controls.open_beside(
            self._chip_anchor(self.buttons["settings"]), keyboard=True
        )
        if not self.hovered:
            self._band_out.start()

    def theme_words(self) -> str:
        """In the quiet view, what this window's source is talking about
        now: its few keyest words, said in its newest caption's language
        ("业主 · 小区 · 物业"; polyglotic-hq 491) - none until it has said
        enough, or with the quiet view off."""
        if not self.look.quiet or self.learner is None:
            return ""
        language = next(
            (
                row.language
                for line in reversed(self.view.lines)
                if not line.by_you
                for row in line.rows
                if row.kind is RowKind.ORIGINAL and row.language
            ),
            None,
        )
        learner = self.learner.of(language)
        said = learner.vocabulary.curriculum.theme_name(self.source)
        return " · ".join(s.form for s in said)

    def _on_label(self, event: QMouseEvent) -> bool:
        """A click on the strip's label (the app's name)."""
        if not self.band_shown:
            return False
        at = self.tag.mapFrom(self, event.position().toPoint())
        return self.tag.rect().contains(at)

    def pick_app(self) -> None:
        """Its settings, with the apps it can caption open (F12, 249): what
        a click on the strip's label opens - a window of one app's only."""
        if not self.app_choices():
            return
        if not self.settings_open:
            self.toggle_settings()
        popover = self.popover
        if popover is not None and popover.isVisible() and popover.apps.isHidden():
            popover._toggle_apps()

    def close_settings(self) -> None:
        for each in self._strip_popovers():
            if each is not None:
                each.close()

    def toggle_languages(self, *, keyboard: bool = False) -> None:
        """The bar's language chip: its three language choices and Start
        new windows like this, under the chip - or closed (465)."""
        if self.languages is not None and self.languages.isVisible():
            self.close_settings()
            self._fit_band()
            return
        self.close_settings()
        if self.locked or not self.isVisible():
            return
        if self.languages is None:
            self.languages = SettingsPopover(self, self.keys, LANGUAGE_ROWS)
            self.languages.setObjectName("caption_window.languages")
        self.languages.open_beside(self._chip_anchor(self.chip), keyboard=keyboard)
        self._fit_band()  # its arrow turned up

    def toggle_presets(self, *, keyboard: bool = False) -> None:
        """The bar's preset chip: the presets' dropdown under it, at its
        right - or closed (polyglotic-hq 556)."""
        if self.presets is not None and self.presets.isVisible():
            self.close_settings()
            self._fit_band()
            return
        self.close_settings()
        if self.locked or not self.isVisible():
            return
        with spans.span("caption_window.presets"):
            if self.presets is None:
                self.presets = PresetPopover(self)
            self.presets.open_beside(
                self._chip_anchor(self.preset_chip), keyboard=keyboard
            )
        self._fit_band()  # its arrow turned up

    def toggle_timings(self, *, keyboard: bool = False) -> None:
        """The bar's timing chip: the timings the preset offers under it, at
        its right - or closed (polyglotic-hq 593)."""
        if self.timings is not None and self.timings.isVisible():
            self.close_settings()
            self._fit_band()
            return
        self.close_settings()
        if self.locked or not self.isVisible():
            return
        if self.timings is None:
            self.timings = TimingPopover(self)
        self.timings.open_beside(self._chip_anchor(self.timing_chip), keyboard=keyboard)
        self._fit_band()  # its arrow turned up

    def set_respeaking(self, on: bool, key: str = "", hold_only: bool = False) -> None:
        """Keep whether re-speaking is available for this window."""
        if (on, key, hold_only) == (
            self.respeaking,
            self._respeak_key,
            self._respeak_hold_only,
        ):
            return
        self.respeaking = on
        self._respeak_key, self._respeak_hold_only = key, hold_only
        self._refresh_popovers()

    def mic_offered(self) -> bool:
        """Its bar offers the own-speech switch (every window but a mic-only one)."""
        return self.mic is not None and not self._mine_only()

    def set_usage(self, meter: UsageMeter | None) -> None:
        """A capped plan's allowance left, on the bar's ring beside the mic;
        None (an unlimited plan, or signed out) shows none (684)."""
        shown = not self.usage_ring.isHidden()
        self.usage_ring.show_meter(meter)
        if shown != (meter is not None):
            self._fit_band()  # the ring takes room the labels had, or gives it back

    def set_mic_level(self, level: float | None) -> None:
        """Live mic meter on the bar's own-speech switch while it is on."""
        self.mic_button.show_level(level if self.choices.show_mic else None)

    def languages_text(self, open_: bool = False) -> str:
        """Its languages on one line, as the bar's language chip says them -
        "Detect → English ▾" - for the gear menu's row (593)."""
        return chip_text(self.choices.spoken_language, self.choices.target, open_)

    def respeak_offered(self) -> bool:
        """Its app can be re-spoken for: re-speaking is on, and it doesn't
        caption the mic itself."""
        return (
            self.respeaking
            and self.source not in (MIC, DICTATION)
            and not self._mine_only()
        )

    def set_presets(self, menu: PresetMenu) -> None:
        """The presets as they are now (`main`'s, by way of
        `CaptionWindows`): the chip's name, and the dropdown if it's open."""
        if menu == self.preset_menu:
            return
        self.preset_menu = menu
        if self.video_enabled:
            self.canvas.update()
        self._fit_band()  # the timing chip's name can change too
        self._refresh_popovers()

    # -- the first window's set-up (465) ------------------------------------------------

    def band_bottom(self) -> int:
        """Where its captions start under the hover band (the set-up's top)."""
        return band_height()

    def ask_set_up(self) -> None:
        """Its three language choices asked in it (`caption_set_up`):
        shown now if it is, else when it shows."""
        if self.set_up is None:
            self.set_up = CaptionSetUp(self)
            self.set_up.done.connect(self.finish_set_up)
        self._show_set_up()

    def _show_set_up(self) -> None:
        """Over it while it shows, unlocked - a window of its own or a
        joined window's column alike: windows start joined, and a column
        once ended its set-up, so a second app opening during the first
        window's question took it away (polyglotic-hq 554)."""
        if self.set_up is None:
            return
        if self.isVisible() and not self.locked:  # a column locks with its window
            self.set_up.open_over()
        else:
            self.set_up.hide()

    def set_up_heard(self) -> None:
        """A caption came: captions start, the set-up goes - unless the
        learner is at it (the next caption after, then)."""
        if self.set_up is not None and not self.set_up.busy():
            self.finish_set_up()

    def finish_set_up(self) -> None:
        """The set-up goes, its answers this window's - and, with "Use as
        my default" chosen in it, how new windows start (478)."""
        set_up, self.set_up = self.set_up, None
        if set_up is None:
            return
        as_default = set_up.as_default.isChecked()
        set_up.close()
        set_up.deleteLater()
        self.set_up_done.emit(as_default)
        self._wake()

    def set_start_like_this(self, on: bool) -> None:
        """Whether new windows start like the last one, the spoken language
        too (the session's: `CaptionWindows`)."""
        self.controls["start_like_this"].setChecked(on)

    def set_lyrics(self, on: bool) -> None:
        """Whether music players are heard in songs mode (the learner's
        Lyrics setting, from `CaptionWindows`; decision 0287)."""
        self.controls["lyrics"].setChecked(on)

    @property
    def offers_lyrics(self) -> bool:
        """Whether its settings offer the Lyrics switch: its app is a known
        music player (`music_player`) and it hears Detect (DECISIONS.md
        #248: songs mode is kept to Detect)."""
        return self.music_player and self.choices.spoken is None

    def set_asks_set_up(self, on: bool) -> None:
        """Whether a window that opens asks its languages (the session's:
        `CaptionWindows`; 478)."""
        self.controls["ask_set_up"].setChecked(on)

    def area_at(self, rect: QRect) -> Rect:
        """The work area holding `rect` (global), or this window's."""
        return placement.area_for(to_rect(rect), self._areas()) or self._area()

    def _show_band(self, shown: bool) -> None:
        shown = shown and not self.locked
        if shown == self.band_shown:
            return
        self.band_shown = shown
        if shown:
            self._fit_band()  # the theme as it is now
        self.band.setVisible(shown)
        if shown:
            self.band.raise_()
            self._tip_text_size()
        else:
            self.close_settings()
        self._place_overlays()
        self.canvas.update()
        self._wake()

    def _band_left(self) -> None:
        if self.settings_open:  # the strip stays while its popover is open
            self._band_out.start()
            return
        if self.chip.isVisible():
            self._fit_band()  # its arrow down again
        self.hovered = False
        self._show_band(False)

    def _tip_text_size(self) -> None:
        few = self.canvas.rows_that_fit() <= FEW_ROWS
        self.controls["bigger"].setToolTip(
            _tr("Drag the top edge for more lines")
            if few
            else hotkeys_here(_tr("Bigger text (Ctrl+wheel)"))
        )

    def showEvent(self, event: QShowEvent) -> None:
        self._wake()  # faded when it was hidden: it looks for the mouse again
        self.unlock_spot.watch(self.locked)
        if self.set_up is not None:  # over it once it's on the screen
            QTimer.singleShot(0, self, self._show_set_up)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() is QEvent.Type.WindowStateChange and self.isMinimized():
            # Windows minimised it ("show desktop", another app): it has no
            # taskbar button to come back from, so it's back at once
            # (polyglotic-hq 272: "the caption window will minimize")
            log.info("caption window %d minimised by Windows: restored", self.index)
            QTimer.singleShot(0, self, restore_minimised(self))

    def hideEvent(self, event: QHideEvent) -> None:
        self.let_in()
        self._stop_looking_for_pointer()
        self.unlock_spot.watch(False)
        self.close_settings()  # hidden (Ctrl+Alt+H) or closed: so is its popover
        if self.set_up is not None:  # asked again when it shows
            self.set_up.hide()
        self._let_go_of_word()
        self.canvas.forget_panel()  # its memory: a window's size, four times over
        if self.card is not None:
            self.card.closed_with(self)  # and a card pinned from it

    # -- where it is --------------------------------------------------------------------

    def _primary(self) -> Rect:
        areas = self._areas()
        return areas[0] if areas else Rect(0, 0, 1920, 1040)

    def _area(self, rect: Rect | None = None) -> Rect:
        found = placement.area_for(rect or self._place(), self._areas())
        return found or self._primary()

    def _place(self) -> Rect:
        return to_rect(self.geometry())

    def _start_place(self) -> Rect:
        area = self._primary()
        choices = self.choices
        preset = (
            choices.preset
            if choices.preset is not Preset.CUSTOM
            else Preset.BOTTOM_CENTRE
        )
        default = placement.slot(preset, area, placement.default_size(area), self.index)
        return placement.at_start(
            choices.geometry, choices.preset, self._areas(), default
        )

    def _set_place(self, rect: Rect) -> None:
        if self.host is not None:  # a column: the joined window has the place
            return
        if rect != self._place():
            self.setGeometry(to_qrect(rect))

    def _minimum(self) -> Size:
        """Room for the captions and the strip's icons."""
        least = least_size(MIN_PANEL)
        height = (
            self.subtitle_height(self.choices.text_size, self.choices.translation_size)
            if self.video_enabled
            else least.height
        )
        return Size(max(least.width, self.strip_least()), height)

    def strip_least(self) -> int:
        """Room for the dot, all chip icons and fixed buttons, and the corners."""
        return (
            self.tag.icon_width()
            + self._strip_buttons_width()
            + len(self._chips) * self._icon_chip_width
            + 2 * placement.CORNER_ZONE
        )

    # -- keeping it in step -------------------------------------------------------------

    def _refresh(self) -> None:
        """After the view changed: Back to live, a repaint."""
        if self._batching_settings:
            return
        self._deal_again()
        lines = self.view.lines
        held = self.view_held()
        if held is not None and lines and self.view.scroll.following:
            # the mouse holds the view: what came since waits past it
            new = sum(1 for line in lines if line.key > held)
            self.pill.setText(_tr("Back to live · {n} new").format(n=new))
            self.pill.setVisible(new > 0)
        elif self.view.scroll.following or not lines:
            self._seen = lines[-1].key if lines else -1
            self.pill.hide()
        else:
            new = sum(1 for line in lines if line.key > self._seen)
            self.pill.setText(
                _tr("Back to live · {n} new").format(n=new)
                if new
                else _tr("Back to live")
            )
            self.pill.show()
        self._place_overlays()
        self._sync_bar()
        self.canvas.changed()
        self.canvas.update()

    def _place_overlays(self) -> None:
        self._place_bar()
        if self.pill.isVisible():
            self.pill.adjustSize()
            top = band_height() + 4 if self.band_shown else 6
            held = self.view_held() is not None and self.view.scroll.following
            self.pill.move(  # held for the mouse: at the top, over no new card
                (self.width() - self.pill.width()) // 2,
                top if held else self.height() - self.pill.height() - 6,
            )
            self.pill.raise_()
        if self.host is not None:
            self.host.place_notice()
        elif self.notice.isVisible():
            self.notice.adjustSize()
            at = self._notice_place()
            if at != self.notice.pos():
                self.notice.move(at)
            if self._notice_foot != self.notice_foot():  # not for its width
                self._notice_foot = self.notice_foot()
                self.canvas.update()  # the captions start below it
            self.notice.raise_()
        elif self._notice_foot:
            self._notice_foot = 0.0
            self.canvas.update()  # gone: its rows come back
        if self.nudge is not None and self.nudge.isVisible():
            self._place_nudge()

    def _notice_place(self) -> QPoint:
        """Keep the notice in the strip's gap at the same place on and off
        hover (109). If the gap cannot hold it, keep it centred and show it
        below the strip while the strip is visible (376, 403)."""
        notice = self.notice
        left = (self.width() - notice.width()) // 2
        band = self.band.geometry()
        top = max(2, band.center().y() - notice.height() // 2)
        if (layout := self.band.layout()) is not None:
            layout.activate()
            if not self.band.isVisible():
                # Qt defers the hidden band's resize until it shows.
                layout.setGeometry(self.band.rect())
        # The language chip crosses the stretch when the chips become icons.
        ends = [self.tag.x() + self.tag.width()]
        right: list[QWidget] = [b for b in self.buttons.values() if not b.isHidden()]
        if not self.chip.isHidden():
            if self.strip_labels is StripLabels.ICONS:
                right.append(self.chip)
            else:
                ends.append(self.chip.x() + self.chip.width())
        for chip in (
            self.preset_chip,
            self.timing_chip,
            self.mic_button,
            self.usage_ring,
        ):
            if not chip.isHidden():
                right.append(chip)
        first = min((b.x() for b in right), default=band.width())
        free_from = band.x() + max(ends) + NOTICE_GAP
        free_to = band.x() + first - NOTICE_GAP
        if free_from + notice.width() <= free_to:
            return QPoint(min(max(left, free_from), free_to - notice.width()), top)
        return QPoint(left, band_height() + 4 if self.band_shown else top)

    def notice_foot(self) -> float:
        """Where captions start below the notice line while it shows (0
        while it doesn't, and in a joined window, whose one line is the
        window's): like the spoken-language question, it never covers a
        caption - the oldest rows in view make room, as they do for the
        strip (403)."""
        if self.host is not None or not self.notice.isVisible():
            return 0.0
        return float(self.notice.geometry().bottom() + 1 + NOTICE_GAP / 2)

    def _place_nudge(self) -> None:
        """The question at the top, where the band, shown, doesn't reach -
        so the band coming and going never moves it - and under the notice
        line when that shows lower. The captions start below it
        (`question_foot`): it never covers one. Its geometry is touched only
        when it changes: a move repaints the captions."""
        nudge = self.nudge
        assert nudge is not None
        top = band_height() + 4
        if self.host is None and self.notice.isVisible():
            top = max(top, self.notice.geometry().bottom() + 4)
        width = min(nudge.maximumWidth(), max(self.width() - 16, 1))
        if nudge.width() != width or nudge.minimumWidth() != width:
            nudge.setFixedWidth(width)
        height = nudge.heightForWidth(width)
        if height <= 0:
            height = nudge.sizeHint().height()
        wanted = QRect((self.width() - width) // 2, top, width, height)
        if nudge.geometry() != wanted:
            nudge.setGeometry(wanted)
            self.canvas.update()  # the captions start below it (350)
        # never raised: made after the captions' canvas it's above them, and
        # it never overlaps the notice line - raising it after the notice's
        # raise swapped the two at every call, and each swap repainted the
        # captions under both (a hovered word's repaint grew to the window)

    def _notice_line(self) -> QLabel | None:
        """Where its notices show: its own line - or, in a joined window,
        the window's one line, which its first column speaks for (every
        window hears the same notices)."""
        host = self.host
        if host is None:
            return self.notice
        return host.notice if host.columns and host.columns[0] is self else None

    def _show_notice(self, now: float) -> None:
        notice, text = self.notices.showing(now)
        if notice is not None:
            text = notice_text(notice, self.notices.retry_in(now))
        line = self._notice_line()
        if line is not self.notice:
            self.notice.hide()
        if line is None:
            return
        if text is None:
            line.hide()
            self._place_overlays()  # its rows come back
            return
        if text != line.text():
            line.setText(text)
        # a notice with a step in it - a preset's Undo (587) - takes the click
        # on its link; every other lets the mouse through, as before
        linked = 'href="' in text
        line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not linked)
        if linked and not line.property("steps"):
            line.setProperty("steps", True)
            line.setCursor(Qt.CursorShape.PointingHandCursor)
            line.linkActivated.connect(self.preset_step)
        line.show()
        self._place_overlays()

    def _wake(self) -> None:
        if not self._tick_timer.isActive():
            self._wake_timer.stop()
            self._last_tick = time.monotonic()
            self._tick_timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - self._last_tick))
        self._last_tick = now
        moving = False
        if self.mark_showing:
            self._last_activity = now  # speech heard: not quiet
            if not reduced_motion():
                moving = True  # the bar sweeps; still, it needs no frames
                if self.canvas.mark_rect is not None:
                    self.canvas.update(self.canvas.mark_rect)
        arriving = self.arriving
        if arriving or self._slid:  # a new caption sliding in: a frame each tick -
            # and one more once it's at rest: the last frame painted may be a
            # slow paint's before the end, with the newest rows still below
            # the clip (the user's "translation cut off at the bottom", 272)
            moving = moving or arriving
            self.canvas.update()
        self._slid = arriving
        correcting = self._correcting(self.clock())  # a quiet correction (494)
        if correcting or self._corrected:  # and one frame more, drawn as usual
            self.canvas.update()
        self._corrected = correcting
        moving = moving or correcting
        fading, new_due = self._newness(self.clock())  # the Lab's New for
        moving = moving or fading
        self._show_notice(now)
        fade_after = self.look.fade_after
        line = self._notice_line()
        awake = (
            self.always_shown
            or (line is not None and line.isVisible())
            or self.band_shown
            or self.hovered
            or self.pointed
            or not self.view.scroll.following
            or self.mark_showing
            or self.notices.paused
            or self.set_up is not None
            or self.still_read()
        )
        quiet = now - self._last_activity
        intro = self._intro_until
        introducing = intro is not None and now < intro
        target = (
            1.0
            if shows(
                awake=awake,
                introducing=introducing,
                empty=not self.view.lines,
                quiet=quiet,
                fade_after=fade_after,
            )
            else 0.0
        )
        if self._alpha != target:
            step = dt / FADE_SEC
            if abs(target - self._alpha) <= max(step, 0.001):
                self._alpha = target
            else:
                self._alpha += step if target > self._alpha else -step
            if self.host is not None:
                self.host.follow_alpha()  # it fades when every column would
            else:
                self.setWindowOpacity(self._alpha)
            if self._alpha == 0.0 and fade_after is None:  # gone, fading off
                log.info(
                    "caption window %d faded out with fading off: %s",
                    self.index,
                    "nothing to read" if not self.view.lines else "unexpected",
                )
            moving = moving or self._alpha != target
        if intro is not None and not introducing and self._alpha == 0.0:
            self._intro_until = None  # its first seconds are over
            self.canvas.update()
        if moving:
            return
        self._tick_timer.stop()  # still: woken when the next thing is due
        faded = self._alpha < 1.0 and not self.locked and self.isVisible()
        if faded and not self._point_timer.isActive():  # it looks for the mouse
            self._pointed_looks = 0
            self._point_timer.start()
        due = []
        upcoming = self.notices.next_change(now)
        if upcoming is not None:
            due.append(upcoming)
        if fade_after and self._alpha > 0.0 and not awake:
            due.append(self._last_activity + fade_after)
        until = self.read_until() if fade_after and self._alpha > 0.0 else None
        if until is not None and until > self.clock():  # read: it may fade then
            due.append(now + until - self.clock() + 0.01)
        if intro is not None and introducing and not awake:
            due.append(intro)
        if new_due is not None:  # a caption steps back, or starts to
            due.append(now + new_due + 0.001)
        later = [at - now for at in due if at > now]
        if later:
            self._wake_timer.start(max(1, math.ceil(min(later) * 1000)))

    def _look_for_pointer(self) -> None:
        """Faded - or shown because the mouse rests on it - whether the
        mouse is on it now: Windows passes the mouse through a faded window,
        so it hears nothing of it. Resting `POINT_REST` looks brings it
        back; leaving lets it fade again."""
        if self.locked or not self.isVisible():
            self._stop_looking_for_pointer()
            return
        on = self.window().geometry().contains(self.pointer())
        self._pointed_looks = self._pointed_looks + 1 if on else 0
        pointed = self._pointed_looks >= POINT_REST
        if pointed != self.pointed:
            self.pointed = pointed
            self._wake()
        if not pointed and self._alpha >= 1.0:
            self._point_timer.stop()  # shown for something else: Qt hears the mouse

    def _stop_looking_for_pointer(self) -> None:
        self._point_timer.stop()
        self._pointed_looks = 0
        self.pointed = False

    # -- events -------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.show_every_line()  # poured again at the new width: all of it
        self.canvas.setGeometry(self.rect())
        if self.deck is not None:
            self._refresh()  # what fits a card changed with the width
        self._place_zone()
        self._fit_band()
        self._place_overlays()
        if self.set_up is not None:
            self.set_up.follow()

    def moveEvent(self, event: object) -> None:
        if self.set_up is not None:
            self.set_up.follow()

    def enterEvent(self, event: QEnterEvent) -> None:
        self.came_over()
        self._hover(event.position())
        if self.hovered or self.host is not None:
            self._hold_on_words(event.position())

    def came_over(self) -> None:
        """The mouse came over it: its band shows after BAND_IN_MS (new
        captions wait only on its words: `_hold_on_words`). Also from a
        mouse move while not hovered - Windows
        can lose the mouse's arrival: after locking and unlocking it, Qt
        heard no enter again until the app restarted (polyglotic-hq 272) -
        and while hovered it checks the mouse is still there
        (`_check_still_over`): the leave can be lost the same way."""
        if self.locked or self.host is not None:  # a column: the window's band
            return
        self.hovered = True
        self._band_out.stop()
        if not self.band_shown:
            self._band_in.start()
        self._still_over.start()
        self.canvas.update()
        self._wake()

    def _check_still_over(self) -> None:
        """While hovered: the mouse left without Qt saying so - as if it had."""
        if not self.hovered or self.locked or not self.isVisible():
            self._still_over.stop()
        elif not self.geometry().contains(self.pointer()):
            self._still_over.stop()
            self.leaveEvent(None)

    def leaveEvent(self, event: object) -> None:
        if self.resize_hint is not None:
            self.resize_hint.hide()
        self._still_over.stop()
        self.let_go()  # a column's too: only its own words held it (554, 583)
        self._band_in.stop()
        if self._drag is None and self.host is None:
            self._band_out.start()
        if self._selecting is None:
            self._unhover()

    def _edges(self, pos: QPointF) -> Edge:
        if self.host is not None:  # a column: the joined window's edges
            return self.host.edges_at(pos + QPointF(self.x(), self.y()))
        zone = GRIP if QApplication.platformName() == "cocoa" else placement.EDGE_ZONE
        return placement.edges_at(pos.x(), pos.y(), self.width(), self.height(), zone)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and not self.locked:
            if self._on_held(event.position()):  # copies what's selected (358)
                self.held.copy(event.globalPosition().toPoint())
                return
            self.held.clear()
            line = self._line_at(event.position())
            if line is not None:  # a right-click copies its caption (333)
                self.copy_line(line.key)
            return
        if event.button() != Qt.MouseButton.LeftButton or self.locked:
            return
        self.held.clear()  # a click elsewhere, or a drag of its own
        pos = event.position()
        divider = self._divider(pos)
        if divider is not None and self.host is not None:  # a column's width
            self.host.press_divider(divider, event.globalPosition())
            return
        edges = self._edges(pos)
        word = self._marked_at(pos) if not edges else None
        if word is not None:  # a click looks it up, a drag selects a phrase
            index = self.canvas.hit(pos)
            self._selecting = _Selecting(
                word, index[3] if index else word.start, QPointF(pos)
            )
            self._hold()  # pressed on its words: they stay put (554)
            self._unhover()
            return
        if self.host is not None:  # a column: the joined window moves or resizes
            self.host.press(edges, event.globalPosition())
            return
        self._drag = _Drag(edges, event.globalPosition(), self._place())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton and self._pressed():
            # a press whose release never came (macOS can lose it - GitHub's
            # Mac, polyglotic-hq 515): ended as its release would end it,
            # never resized or moved by a move with no button held (the
            # pointer watch's, while the app is in the background)
            self.mouseReleaseEvent(event)
            return
        if not self.hovered and self._drag is None:  # its arrival lost (272)
            if self.host is None:
                self.came_over()
            elif not self.host.dragging:
                self.host.came_over()
        if self.hovered or self.host is not None:
            self._hold_on_words(event.position())
        if self._selecting is not None:
            self._select_to(event.position())
            return
        if self.host is not None and self.host.dragging:
            self.host.drag_to(event.globalPosition())
            return
        drag = self._drag
        if drag is None:
            self._hover(event.position())
            if self.resize_hint is not None and not self.locked:
                self.resize_hint.follow(event.position(), self._edges(event.position()))
            return
        delta = event.globalPosition() - drag.origin
        dx, dy = round(delta.x()), round(delta.y())
        if not drag.moved and abs(dx) + abs(dy) < 3:
            return
        drag.moved = True
        with spans.span("caption_window.drag_step"):
            if drag.edges:
                self.resize_by(drag, dx, dy)
            else:
                self.move_by(drag, dx, dy)

    def _pressed(self) -> bool:
        """A press of its own under way: a drag (resizing or moving), a
        selection, or its joined window's drag."""
        return (
            self._drag is not None
            or self._selecting is not None
            or (self.host is not None and self.host.dragging)
        )

    def resize_by(self, drag: _Drag, dx: int, dy: int) -> None:
        """A resize step: the dragged edges moved, re-laid out in this frame."""
        area = self._area(drag.start)
        rect = placement.resized(
            drag.start, drag.edges, dx, dy, self.choices.preset, self._minimum(), area
        )
        self._set_place(rect)
        self.canvas.repaint()

    def move_by(self, drag: _Drag, dx: int, dy: int) -> None:
        """A move step: kept on the screen; near a preset, snapped to it."""
        raw = Rect(
            drag.start.x + dx, drag.start.y + dy, drag.start.width, drag.start.height
        )
        area = self._area(raw)
        rect, preset = placement.snapped(
            placement.moved(drag.start, dx, dy, area), area
        )
        if preset is not Preset.CUSTOM and preset is not drag.snapped:
            self.show_notice(preset_name(preset), seconds=1.0)
        drag.snapped = preset
        self._set_place(rect)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """A double-click on a word selects it whole - as in any text - and
        holds it to copy; its first click already looked it up
        (polyglotic-hq 395: a drag selects character by character, so the
        word at once is here). It never presses again: Qt's own handler
        did, and its release pinned the word twice - two lookups, the second
        turning a word assumed known new (polyglotic-hq 397, 400). Anywhere
        else: a press, as before."""
        word = None
        if event.button() == Qt.MouseButton.LeftButton and not self.locked:
            word = self._marked_at(event.position())
        if word is None:
            self.mousePressEvent(event)
            return
        shown = self.canvas.shown_row(word.key, word.row, (word.start, word.end))
        if shown is None:  # its row went as it arrived: nothing to select
            return
        row = shown[1].row
        self._selecting = None
        self.held.hold(
            Selection(
                Place(word.key, row.clause, word.start, row.kind),
                Place(word.key, row.clause, word.end, row.kind),
            )
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._selecting is not None:
            self._pin_selected(event.globalPosition().toPoint())
            return
        if self.host is not None:
            self.host.release()
            return
        drag, self._drag = self._drag, None
        if drag is None or not drag.moved:
            if drag is not None and not drag.edges and self._on_label(event):
                self.pick_app()  # the strip's label: which app (F12)
            return
        place = self._place()
        if drag.edges:
            self.choices = replace(self.choices, geometry=place)  # the preset kept
            say_resized(f"caption window {self.index}", drag, place, self._minimum())
        else:
            self.choices = replace(self.choices, preset=drag.snapped, geometry=place)
        self._refresh()
        self.changed.emit()

    def _divider(self, pos: QPointF) -> int | None:
        """A column: the joined window's divider at `pos`, if any (284)."""
        if self.host is None:
            return None
        return self.host.divider_at(pos + QPointF(self.x(), self.y()))

    def _hover(self, pos: QPointF) -> None:
        if self.locked:
            return
        if self._divider(pos) is not None:  # the divider beside: drag it
            self.setCursor(Qt.CursorShape.SplitHCursor)
            self._unhover()
            return
        edges = self._edges(pos)
        word = self._marked_at(pos) if not edges else None
        if word is None:
            self.setCursor(CURSORS.get(edges, Qt.CursorShape.SizeAllCursor))
            self._unhover()
            return
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if word != self.canvas.hovered:
            was = self.canvas.hovered
            self.canvas.hovered = word
            self._repaint_lines(was, word)
        card = self.card
        if card is None:
            return
        key = (word.key, word.row, word.start, word.end)
        if card.showing(key):  # the same word: nothing new to look up
            card.hover_kept()
            return
        if card.pinned:
            return
        found = self.word_at(word)
        if found is not None:
            card.hover(found)

    # -- copying (polyglotic-hq 333) ------------------------------------------------------

    def _line_at(self, pos: QPointF) -> Line | None:
        """The caption drawn at `pos` - not under the hover strip, which is
        drawn over the captions."""
        if self.band.isVisible() and self.band.geometry().contains(pos.toPoint()):
            return None
        for line, _, rect in self.placed():
            if rect.top() <= pos.y() < rect.bottom():
                return line
        return None

    def _finished_lines(self) -> list[Line]:
        """The finished captions it shows, oldest first - all it holds to
        scroll back through, not one still being heard."""
        return [line for line in self.canvas.lines_in_view() if not line.live]

    def copy_text(self, lines: Sequence[Line]) -> str:
        """`lines`' captions as the transcript's Copy writes them: each one's
        time, "You" on the learner's own, what was said and its translation
        (and the second language's, for a line already in the window's) -
        none for Original only; "" for no finished caption."""
        target, second = self.choices.target, self._second()
        languages = (
            []
            if target is None
            else [target]
            if second is None or second == target
            else [target, second]
        )
        names = {str(code): shown_name(str(code)) for code in languages}
        zone = datetime.now().astimezone().tzinfo  # the times this PC shows
        captions = self.view.captions_of(lines)
        seconds = {} if target is None or second is None else {target: second}
        return as_text(
            captions,
            languages,
            names,
            self.labels.you.name,
            zone,
            seconds=seconds,
            respoken=_tr("re-spoken"),
        )

    def copy_all(self) -> None:
        """The settings' Copy all captions."""
        self._copy(self._finished_lines())

    def copy_line(self, key: int) -> None:
        """A right-click on a caption: that one."""
        self._copy([line for line in self._finished_lines() if line.key == key])

    def _copy(self, lines: Sequence[Line]) -> None:
        """`lines` to the clipboard - nowhere else: caption text is never
        logged, sent or kept - and the notice line says so; or that there's
        nothing to copy yet (no caption finished)."""
        self.close_settings()
        text = self.copy_text(lines) if lines else ""
        # a column's notices are said on the joined window's one line
        host = self.host
        says = host.columns[0] if host is not None and host.columns else self
        if not text:
            says.show_notice(_tr("Nothing to copy yet"), COPIED_SEC)
            return
        QGuiApplication.clipboard().setText(text)
        says.show_notice(_trn("Copied %Ln caption(s)", len(lines)), COPIED_SEC)

    # -- the lookup ---------------------------------------------------------------------

    def _marked_at(self, pos: QPointF) -> Marked | None:
        """The word under `pos`, by the word split - None for none."""
        learner = self.learner
        hit = self.canvas.hit(pos)
        if learner is None or hit is None:
            return None
        line, row, _, index = hit
        text = line.rows[row.index].text
        if not 0 <= index < len(text):
            return None
        span = learner.word_at(text, index, row.row.language)
        if span is None or span[0] >= span[1]:
            return None
        return Marked(line.key, row.index, *span)

    def word_at(self, marked: Marked) -> WordAt | None:
        """What the lookup needs for `marked`: the text, its context (the
        caption's row and its translation) and where it is on the screen -
        None if its line isn't drawn any more."""
        shown = self.canvas.shown_row(
            marked.key, marked.row, (marked.start, marked.end)
        )
        if shown is None:
            return None
        line, row, origin = shown
        text = line.rows[row.index].text
        caption = self.view.caption(line.key)
        context = (
            lookup_context(text, clause_versions(caption, row.row.clause))
            if caption is not None and row.row.clause < len(caption.clauses)
            else LookupContext(text)
        )
        context = with_counterpart(
            context, caption, line.rows, row.index, (marked.start, marked.end)
        )
        rects = row.rectangles(marked.start, marked.end)
        if not rects:
            return None
        box = rects[0]
        for rect in rects[1:]:
            box = box.united(rect)
        word = self._on_screen(box.translated(origin))
        reading = self._on_screen(
            self.canvas.line_rect(row, origin, marked.start, marked.end)
        )
        return WordAt(
            text[marked.start : marked.end],
            context,
            (marked.start, marked.end),
            word,
            reading,
            self.area_at(QRect(word.x, word.y, word.width, word.height)),
            (marked.key, marked.row, marked.start, marked.end),
            row.row.language,
            self.view.fallbacks,
        )

    def _on_screen(self, rect: QRectF) -> Rect:
        top_left = self.canvas.mapToGlobal(rect.topLeft().toPoint())
        return Rect(
            top_left.x(), top_left.y(), round(rect.width()), round(rect.height())
        )

    def _repaint_lines(self, *changed: Marked | Line | None) -> None:
        """The lines a hover change touched, repainted - those alone, not
        the window: a mouse move across words with thick arrows painted
        the whole window each time, up to 487 ms on the user's PC
        (polyglotic-hq 272)."""
        if self.zones is not None:
            self.zone.update()
        for each in changed:
            if each is None:
                continue
            area = self.canvas.line_area(each.key)
            if area is None:  # not drawn where it was: all of it, to be sure
                self.canvas.update()
                return
            self.canvas.update(area)

    def _unhover(self) -> None:
        if self.canvas.hovered is not None:
            before = self.canvas.hovered
            self.canvas.hovered = None
            self._repaint_lines(before)
        if self.card is not None:
            self.card.unhover()

    def _let_go_of_word(self) -> None:
        """No word marked, nothing being selected (locked, hidden, closed)."""
        self._selecting = None
        self.canvas.selection = None
        self.held.clear()
        self._unhover()

    # -- selecting (polyglotic-hq 358; 340's design) ---------------------------------

    def use_say_it(self, reading: SelectionReading | None) -> None:
        """Say it on the selection's card reads through `reading`; the word
        it says lights here (polyglotic-hq 495)."""
        if self.say_it is not None:
            self.say_it.lit.disconnect(self._said_now)
        self.say_it = reading
        if reading is not None:
            reading.lit.connect(self._said_now)
        if self.sentence_card is not None:
            self.sentence_card.use_reading(reading)

    def _said_now(self, owner: object, words: dict[int, list[Words]]) -> None:
        if owner is self and words != self.canvas.said_now:
            self.canvas.said_now = words
            self.canvas.update()
            self.zone.update()

    def _held_changed(self) -> None:
        self.canvas.update()
        self.zone.update()
        if self.say_it is not None:  # a new selection, or none: no more reading
            self.say_it.stop_for(self)
        if self.held.selection is None and self.sentence_card is not None:
            self.sentence_card.withdraw()

    def _offer_sentence(self, at: QPoint, phrase: Marked | None = None) -> bool:
        """The selection just let go of, if more than a word: offered to
        save as a sentence (polyglotic-hq 459), by a card at `at` (the
        mouse, on the screen, where the drag let go: 522) - into the
        learning data of the language it was spoken in. `phrase`: a
        selection within one clause, which the card's "Look it up" opens
        the lookup card on (533). Whether it was."""
        chosen, learner = self.held.selection, self.learner
        if chosen is None or learner is None:
            return False
        pieces = held_pieces(self.view.lines, chosen)
        found = selected_sentence(pieces, self._speaker, self.view.caption)
        if found is None or not worth_saving(found):
            return False
        vocabulary = learner.of(found.language).vocabulary
        sentence = found

        def save(category_id: CategoryId) -> str:
            try:
                vocabulary.save_sentence(
                    sentence.parts,
                    sentence.original,
                    sentence.translation,
                    category_id,
                    sentence.translation_language,
                )
            except ValueError:
                return ""
            category = vocabulary.category(category_id)
            return category.name if category is not None else ""

        area = self._area()
        if self.sentence_card is None:
            self.sentence_card = SentenceCard(self)
            self.held.keeps.append(self.sentence_card)
        self.sentence_card.use_reading(self.say_it)
        self.sentence_card.offer(
            vocabulary.categories,
            save,
            at,
            QRect(area.x, area.y, area.width, area.height),
            sides_aloud(pieces),
            (lambda: self._look_up(phrase)) if phrase is not None else None,
        )
        return True

    def _look_up(self, phrase: Marked) -> None:
        """`phrase` looked up and pinned, as a click on a word is (533)."""
        found = self.word_at(phrase)
        if found is not None and self.card is not None:
            self.card.pin(found, self)

    def _speaker(self, line: Line) -> str:
        """Who said `line`, as its label names them: "You", or its app."""
        if line.by_you:
            return self.labels.you.name
        found = self.labels.sources.get(line.source)
        return found.name if found is not None else ""

    def _on_held(self, pos: QPointF) -> bool:
        """`pos` is on the words selected - not under the hover strip."""
        chosen = self.held.selection
        if chosen is None or pos.y() < self.canvas.clear_top:
            return False
        if self.band.isVisible() and self.band.geometry().contains(pos.toPoint()):
            return False
        rects = held_rects(self.placed(), chosen)
        return any(rect.contains(pos) for rect in rects)

    def _select_across(self, selecting: _Selecting, row: LaidRow, to: Place) -> None:
        """A drag from a word out of its clause and side, to `to`: a
        selection across lines, clauses and captions, from the character
        pressed on to the place the mouse is - character by character, not
        snapped to words (polyglotic-hq 395). No lookup."""
        selecting.across = True
        if self.canvas.selection is not None:
            self.canvas.selection = None  # no longer a phrase
        word = selecting.word
        start = Place(word.key, row.row.clause, selecting.anchor, row.row.kind)
        forward = (to.caption, to.clause, to.char) >= (
            word.key,
            start.clause,
            selecting.anchor,
        )
        anchor = start if forward else replace(start, char=selecting.anchor + 1)
        self.held.draw(Selection(anchor, to))
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def _select_to(self, pos: QPointF) -> None:
        """A drag from a word: within its clause and side, the characters
        from the one pressed on to the one under `pos`, each on its own
        (polyglotic-hq 395: "I want each character to be selectable one by
        one"); till the mouse has moved `startDragDistance`, still a click.
        Out of them: a selection (`_select_across`)."""
        selecting = self._selecting
        assert selecting is not None
        if not selecting.moved:
            if (pos - selecting.press).manhattanLength() < drag_distance():
                return
            selecting.moved = True
        word = selecting.word
        shown = self.canvas.shown_row(word.key, word.row, (word.start, word.end))
        if shown is None or self.learner is None:
            return
        line, row, origin = shown
        to = place_at(self.placed(), pos, self.canvas.clear_top)
        if to is not None and (to.caption, to.clause, to.side) != (
            word.key,
            row.row.clause,
            row.row.kind,
        ):
            self._select_across(selecting, row, to)
            return
        if selecting.across:  # back in its own clause: a phrase again
            selecting.across = False
            self.held.clear()
        text = line.rows[row.index].text
        fragment = (
            self.canvas.shown_row(word.key, word.row, (to.char, to.char + 1))
            if self.video_enabled and to is not None
            else None
        )
        if fragment is not None:
            _, row, origin = fragment
        current = self.canvas.char_at(row, origin, pos)
        low, high = sorted((selecting.anchor, current))
        selection = Marked(word.key, word.row, low, min(high + 1, len(text)))
        if selection != self.canvas.selection:
            self.canvas.selection = selection
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.canvas.update()
            self.zone.update()

    def _pin_selected(self, at: QPoint) -> None:
        """The phrase dragged across - trimmed of spaces and punctuation at
        its ends - or, after a plain click, the word: pinned. A phrase is
        held as a selection too, exactly as dragged (395): copied, it's
        what was highlighted. One worth saving as a sentence gets the
        sentence card at `at` (the mouse, on the screen) and no lookup -
        never both, overlapping (522); the card's "Look it up" opens the
        lookup in its place (533)."""
        selecting, self._selecting = self._selecting, None
        assert selecting is not None
        if selecting.across:  # a selection: held, no lookup
            self.held.hold()
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._offer_sentence(at)
            return
        selection, self.canvas.selection = self.canvas.selection, None
        marked = selecting.word
        if selection is not None:
            shown = self.canvas.shown_row(
                selection.key, selection.row, (selection.start, selection.end)
            )
            text = shown[0].rows[shown[1].index].text if shown else ""
            start = min(selection.start, len(text))
            end = min(selection.end, len(text))
            while start < end and not _wordlike(text[start]):
                start += 1
            while end > start and not _wordlike(text[end - 1]):
                end -= 1
            if start < end:  # else: only punctuation - the word pressed on
                marked = Marked(selection.key, selection.row, start, end)
            if shown is not None:  # a phrase is a selection too: copyable
                kind, clause = shown[1].row.kind, shown[1].row.clause
                self.held.hold(
                    Selection(
                        Place(selection.key, clause, selection.start, kind),
                        Place(selection.key, clause, selection.end, kind),
                    )
                )
                # more than a word: a sentence, which can be looked up (533)
                if self._offer_sentence(at, marked):
                    self.canvas.update()
                    return
            self.canvas.update()
        found = self.word_at(marked)
        if found is not None and self.card is not None:
            self.card.pin(found, self)

    def _wheel_zoom(self, event: QWheelEvent) -> bool:
        zoom_keys = Qt.KeyboardModifier.ControlModifier
        if on_a_mac():
            # Qt normally reports Command as ControlModifier and Control as MetaModifier.
            zoom_keys |= Qt.KeyboardModifier.MetaModifier
        if not event.modifiers() & zoom_keys:
            return False
        delta = event.angleDelta().y()
        if delta:
            self._step_text_sizes(1 if delta > 0 else -1)
        event.accept()
        return True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.scroll_bar and isinstance(event, QWheelEvent):
            return self._wheel_zoom(event)
        return super().eventFilter(watched, event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._wheel_zoom(event):
            return
        if not self.locked:
            notches = event.angleDelta().y() / 120
            with spans.span("caption_window.scroll_step"):
                if self.deck is not None:
                    self.scroll_cards(notches)
                elif self.video_enabled:
                    self.scroll_subtitles(notches)
                else:
                    self.canvas.scroll_by(notches * 48)
                    self._refresh()
        event.accept()
