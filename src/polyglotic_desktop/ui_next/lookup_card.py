"""W3, the lookup card: one painted card, shared by every caption window
(polyglotic-hq project 109's structure, section 6; project 113).

It draws `views.lookup`'s card - the content and wording of today's
lookup (`ui.lookup`) in 109's shape:
- **One painted card:** its text is laid out and painted, its buttons are
  rectangles it hit-tests - no widget tree, nothing rebuilt per open (108:
  today's built a widget tree on every open).
- **Hover:** shown `HOVER_MS` after the mouse rests on a word - the
  headword, reading, status and first sense, no actions. It lets the
  mouse through to the window under it, so it never takes the hover from
  the words; it goes `HIDE_MS` after the mouse leaves the word.
- **Pinned** by a click on a word, or a drag across a phrase: the
  actions (Add to deck, Known, Save to - with New category - Remove, and
  Copy: the word, its reading and meaning to the clipboard, "✓ Copied"
  until the next click, Ctrl+C while one of the app's windows has the
  keyboard - polyglotic-hq 333),
  the parts with Back, "Heard in N captions" and the context line. It
  stays until Esc, a click elsewhere, or `LEAVE_MS` after the mouse
  leaves it.
- **It never takes the focus** (a full-screen game can minimise when it
  loses it), like the settings popover: a tool window with
  `Qt.WindowDoesNotAcceptFocus`, shown without activating, never raised.
  So Esc, Backspace (Back) and clicks elsewhere reach it through an event
  filter on this app, and - while it's pinned, and only then - a look
  every `POLL_MS` at whether Esc, Backspace or a mouse button is held
  anywhere (`keys`: Windows' key state, read, not taken).
- **The learner's dictionary out** (missing or damaged on the PC;
  polyglotic-hq 199): the word, what's wrong and how to fix it
  (`dictionary_out`, the words Home and Help use too) - never "not in the
  dictionary", which it can't know.
- **"Learning Japanese too?"** on a pinned word in a language not being
  learned that has a dictionary - asked once: Learn Japanese too adds it
  to Learning's list, Not now isn't asked again (DECISIONS.md #65,
  polyglotic-hq 262; `views.lookup.LanguagesOffer`, `main`'s).
- **Placed** by `views.lookup.place`: above the word, centred on it;
  below the row near the top of the screen; never over the row being
  read; on the work area.
- **Say it** (polyglotic-hq 286): pinned, a speaker beside Close says the
  word aloud in one of the PC's voices (`WordSpeech`, `main`'s) - at its
  own pace, every click (518); a click while it speaks stops it, and so
  does the card closing. Played in a basic voice (a Mac's compact one),
  the card says how to add a better one, with "Don't show again" for the
  language and Dismiss (518). R does the same while one of the app's
  windows has the keyboard (not in a text field) - never over a game,
  where R is the game's. With no voice for the word's language the
  speaker is crossed out, and a click says how Windows adds one, with a
  button to its speech settings. Screen readers get the word as the
  card's name and the button's state as its description.
- **Its text can be copied** (polyglotic-hq 343): pinned, a drag across
  the word, its readings, senses, parts, the "Here:" line and the context
  selects it (`copying.TextSelection`) - a click on a part, without a
  drag, still looks it up. A right-click on the selection copies it, with
  "Copied" by the mouse and never the keyboard (`copying.copy_quietly`);
  Ctrl+C copies it while one of the app's windows has the keyboard - or
  the whole card, as Copy does, with nothing selected. A drag that leaves
  the card doesn't close it.
- **"Here: ngân hàng"** (polyglotic-hq 328): what the word is in the
  translation shown with its caption line, from the line's word links -
  first under the word, hovered or pinned; larger on a word whose row has
  no dictionary, where it's what the card has to say. None, no line.

A Learning action runs through `act`, which the caption windows hand it:
they repaint only the captions holding the entry it changed. Its colours
are the dark palette's (the caption windows stay neutral); the main
window's theme comes with 109's step 4. Holds words and caption text (the
context): never log them.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from PySide6.QtCore import (
    QEvent,
    QLocale,
    QObject,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QEnterEvent,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QToolTip,
    QWidget,
)

from polyglotic_desktop.core.learning.languages import Tier, tier_of
from polyglotic_desktop.core.learning.load import Stage
from polyglotic_desktop.core.lexicon.chinese import has_han
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry, DictionarySense
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui_next import glyphs, style
from polyglotic_desktop.ui_next.above_all import ABOVE_ALL, set_click_through
from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES
from polyglotic_desktop.ui_next.caption_marks import STAGE_COLOURS
from polyglotic_desktop.ui_next.copying import Painted, TextSelection, copy_quietly
from polyglotic_desktop.ui_next.languages import an_before, in_sentence, learned_name
from polyglotic_desktop.ui_next.load_card import add_text, check_texts, stage_text
from polyglotic_desktop.ui_next.os_words import hotkeys_here, on_linux, pc_or_mac
from polyglotic_desktop.ui_next.settings_popover import KeyState
from polyglotic_desktop.ui_next.views.lookup import (
    Card,
    Learner,
    Lookup,
    PartsTitle,
    Shows,
    WordAt,
    copy_text,
    place,
)
from polyglotic_desktop.ui_next.views.placement import Size
from polyglotic_desktop.ui_next.views.speech import Say, notice_language, word_language
from polyglotic_desktop.ui_next.word_classes import class_name
from polyglotic_desktop.ui_next.word_speech import WordSpeech

HOVER_MS = 100
"""The mouse rests on a word this long before its lookup shows."""
FOLLOW_MS = 40
"""A hover card showing follows the mouse to the next word this long after
the mouse comes to it - not in the mouse move itself: a sweep across a
line looks up the word it stops on, not each word on the way, each a
dictionary read on the interface thread (up to 297 ms on the user's PC,
polyglotic-hq 272)."""
HIDE_MS = 150
"""A hover card goes this long after the mouse leaves its word."""
LEAVE_MS = 10_000
"""A pinned card closes this long after the mouse leaves it (and its word)."""
POLL_MS = 40
"""How often a pinned card looks at Esc, Backspace and the mouse buttons."""
WIDTH = 360
"""A pinned card's width at 100 % text size: it grows with the text
(`style.px`), as do its fonts."""
HOVER_WIDTHS = (160, 320)
"""A hover card is as wide as its words, between these (at 100 %)."""
PAD = 14
GAP = 6
SMALLEST_HEADWORD = 0.7
"""A headword a little too long for its line shrinks, to this share of
its size at most, to fit it (`fitted`); one longer still wraps at its own
size, two lines of it as easy to read as one: either way it never runs
under Say it and Close (polyglotic-hq 522's picture of a long selection's
card, 533)."""
SURFACE, LINE, TEXT, DIM, FAINT = "#191d24", "#2a303b", "#e9ecf2", "#a0a8b6", "#848c9c"
"""FAINT is the faintest text still 4.5:1 on SURFACE (5.0:1; the UI lab)."""
ACCENT, ACCENT_TEXT = "#7c9cff", "#0d1220"
SELECTED = 0.35
"""Selected text's background: the accent, this opaque under the text."""
STATUS_COLORS = {
    WordStatus.NEW: "#ffd27a",
    WordStatus.LEARNING: "#7ee0a8",
    WordStatus.KNOWN: DIM,
    WordStatus.IGNORED: FAINT,
}
"""A status chip's colour: new and in the deck as the captions mark them."""
CHENGYU = "#ffb86b"
ROW = "part:"
"""A part row's hit: a click looks the part up, a drag selects its words."""
SAY_KEY = Qt.Key.Key_R
"""Says the word, or stops it: Anki's key for hearing a card's audio again."""
SAY_GLYPHS = {
    Say.READY: (glyphs.Glyph.SPEAKER, DIM),
    Say.SPEAKING: (glyphs.Glyph.SPEAKING, ACCENT),
    Say.NO_VOICE: (glyphs.Glyph.NO_VOICE, FAINT),
}
_TYPING = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
"""Widgets an R typed into is text, not "say it"."""


def _has_selection(widget: QWidget | None) -> bool:
    """`widget` has words selected of its own - a label in the main window,
    or anything with a selection that says so as a label does
    (`hasSelectedText`): Ctrl+C there copies those (343)."""
    selected = getattr(widget, "hasSelectedText", None)
    return callable(selected) and bool(selected())


Action = Callable[[], DictionaryEntry | None]
"""A Learning action: it returns the entry it changed, or None."""
Act = Callable[[Action], None]
"""Runs a Learning action (the caption windows: and repaint its captions)."""


def _tr(text: str) -> str:
    return QApplication.translate("LookupCard", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("LookupCard", text, None, n)


def _sense_parts(sense: DictionarySense) -> tuple[str, str, str]:
    if not sense.classes:
        return sense.gloss, "", ""
    labels = " / ".join(class_name(cls) for cls in sense.classes)
    before, _, after = _tr("{classes} · {gloss}").partition("{classes}")
    return before.format(gloss=sense.gloss), labels, after.format(gloss=sense.gloss)


def _sense_text(sense: DictionarySense) -> str:
    return "".join(_sense_parts(sense))


def no_voice_steps(language: str, system_voice: bool = True) -> str:
    """No voice for `language` on this PC, and how Windows adds one - or a
    Mac's steps: the card's "say it", and the selection's Say it
    (polyglotic-hq 495). On Linux, why (591): speech-dispatcher, the
    system's voice, missing or not starting (`system_voice` False: none of
    the PC's own voices answer), or without the language."""
    name = learned_name("zh" if language == "zh-hant" else language)
    if on_linux():
        if not system_voice:
            return in_sentence(
                _tr(
                    "No {language} voice yet: Polyglotic speaks with the "
                    "system's speech-dispatcher, which isn't installed or didn't "
                    "start. Install speech-dispatcher and "
                    "speech-dispatcher-espeak-ng from your software manager."
                ),
                language=name,
            )
        return in_sentence(
            _tr(
                "No {language} voice yet: the system's speech-dispatcher has "
                "none. speech-dispatcher-espeak-ng, from your software manager, "
                "adds voices for over 100 languages."
            ),
            language=name,
        )
    return in_sentence(
        pc_or_mac(
            _tr(
                "No {language} voice on this PC yet. Windows adds one for free: "
                "Settings > Time & language > Speech > Add voices, then "
                "{language}."
            ),
            _tr(
                "No {language} voice on this Mac yet. macOS adds one for free: "
                "System Settings > Accessibility > Spoken Content > System "
                "voice > Manage Voices, then {language}."
            ),
        ),
        language=name,
    )


def better_voice_steps(language: str) -> str:
    """A word or selection was said in a basic voice: how to add a better
    one of its language (polyglotic-hq 518; Apple's steps, 428). Only a
    Mac's voices are basic (`ports.speaker.Quality`): Windows' natural
    voices are Narrator's own. On Linux every voice is speech-dispatcher's
    basic one, and none better is open to the app yet (591; DECISIONS #243
    item 3): the notice says so, and that recorded words sound natural."""
    name = learned_name(notice_language(language))
    if on_linux():
        return in_sentence(
            _tr(
                "That was the system's basic {language} voice, from "
                "speech-dispatcher. Polyglotic can't use a more natural one on "
                "Linux yet; words with a recording play in a natural voice."
            ),
            language=name,
        )
    if an_before(name):  # "an English voice" (551)
        #: "an" before a language name said with a vowel first ("an English voice"). Translate as the text with "then a {language} voice"
        said = _tr(
            "That was macOS's basic {language} voice. A more natural one is "
            "free: System Settings > Accessibility > Spoken Content > System "
            "voice > Manage Voices, then an {language} voice marked Enhanced "
            "or Premium."
        )
    else:
        said = _tr(
            "That was macOS's basic {language} voice. A more natural one is "
            "free: System Settings > Accessibility > Spoken Content > System "
            "voice > Manage Voices, then a {language} voice marked Enhanced or "
            "Premium."
        )
    return in_sentence(said, language=name)


def never_again_text(language: str) -> str:
    """The better-voice notice's checkbox (518)."""
    name = learned_name(notice_language(language))
    return in_sentence(_tr("Don't show again for {language}"), language=name)


def dismiss_text() -> str:
    """The better-voice notice's button (518)."""
    return _tr("Dismiss")


def heard_in(count: int) -> str:
    """How many captions the word was heard in: "Heard in 1 caption", "Heard
    in 3 captions" - each language's plural forms, English's too, from the
    translation files (polyglotic-hq 133, 156)."""
    return _trn("Heard in %Ln caption(s)", count)


def more_readings(count: int) -> str:
    """ "+1 more reading", "+2 more readings" (as `heard_in`)."""
    return _trn("+%Ln more reading(s)", count)


def here(words: str) -> tuple[str, tuple[int, int]]:
    """The card's line for a word's counterpart in its caption line's
    translation - "Here: ngân hàng" (polyglotic-hq 328) - and where `words`
    are in it (the rest is the label, drawn faint)."""
    #: what the word looked up is in the translation of its caption line, e.g. "Here: ngân hàng": what it means here
    label = _tr("Here: {words}")
    before, _, after = label.partition("{words}")
    return f"{before}{words}{after}", (len(before), len(before) + len(words))


def answered_by(language: str) -> str:
    """The card's line naming the dictionary that answered, when it isn't
    the row's language's (polyglotic-hq 337)."""
    #: the card's word was found in another language's dictionary than its caption line's, e.g. "From the English dictionary"
    said = _tr("From the {language} dictionary")
    return in_sentence(said, language=learned_name(language))


def _here_font(card: Card) -> QFont:
    """The counterpart's line: in its own language's fonts - a Chinese or
    Japanese face first for those - with the interface's behind, for the
    label (a Chinese interface's in its own Chinese face, 198). Larger
    where it's the card's main content (no dictionary for the row)."""
    own = CJK_FAMILIES.get(card.counterpart_language, ())
    families = (*own, *LATIN_FAMILIES, *style.UI_FAMILIES)
    return _font(16 if card.shows is Shows.NO_DICTIONARY else 14, families)


def dictionary_out(problem: DictionaryProblem, chinese: bool) -> tuple[str, str]:
    """What's wrong with the learner's dictionary, and how to fix it: the
    card's words, which Home and Help use too (polyglotic-hq 199). The
    dictionaries are in the installed app's own folder, which an install
    replaces whole; the learner's words and settings are in another
    (`main.data_folder`), so reinstalling repairs it and keeps them."""
    if problem is DictionaryProblem.MISSING:
        what = (
            _tr("The Chinese dictionary is missing")
            if chinese
            else _tr("The English dictionary is missing")
        )
    elif problem is DictionaryProblem.UNREADABLE:
        what = (
            _tr("The Chinese dictionary can't be opened")
            if chinese
            else _tr("The English dictionary can't be opened")
        )
    else:
        what = (
            _tr("The Chinese dictionary is damaged")
            if chinese
            else _tr("The English dictionary is damaged")
        )
    fix = _tr(
        "Reinstall Polyglotic to repair it (ask us for the installer). "
        "Your words and settings are kept."
    )
    return what, fix


def _run(action: Action) -> None:
    action()


def _status_name(status: WordStatus) -> str:
    """Today's words for a status."""
    return {
        WordStatus.NEW: _tr("new"),
        WordStatus.LEARNING: _tr("in your deck"),
        WordStatus.KNOWN: _tr("known"),
        WordStatus.IGNORED: _tr("ignored"),
    }[status]


def _font(
    px: float, families: Sequence[str] = LATIN_FAMILIES, bold: bool = False
) -> QFont:
    font = QFont()
    font.setFamilies(list(families))
    font.setPixelSize(style.px(px))  # at Windows' text size
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def fitted(text: str, font: QFont, room: float) -> tuple[QFont, bool]:
    """`font`, a pixel at a time smaller - down to `SMALLEST_HEADWORD` of
    its size - till `text` fits `room` on one line; and whether it does."""
    fitting = QFont(font)
    size = fitting.pixelSize()
    least = max(1, round(size * SMALLEST_HEADWORD))
    while QFontMetricsF(fitting).horizontalAdvance(text) > room:
        if size <= least:
            return fitting, False
        size -= 1
        fitting.setPixelSize(size)
    return fitting, True


def _ui(px: float, bold: bool = False) -> QFont:
    """The card's own words - its buttons, chips and notes - in the
    interface's fonts (`style.UI_FAMILIES`), with the Chinese face of the
    interface's language: Microsoft YaHei UI for zh_CN, JhengHei UI for
    zh_TW. In the card's Latin fonts their Chinese came from whatever face
    Windows found: MS UI Gothic, a Japanese one, in an English locale
    (polyglotic-hq 176, 198)."""
    return _font(px, style.UI_FAMILIES, bold)


def _meanings(card: Card) -> Sequence[str]:
    """The fonts for a card's meanings, its parts' meanings and Back's word:
    Chinese first, in the word's script, and Latin behind, as the context
    line has them. An English word's meanings are Chinese (ECDICT); a
    Chinese word's hold Chinese ("CL:台[tai2]"). Not Latin first with Chinese
    behind: Qt keeps the fonts behind a family as they were first asked for
    at a size, so a Simplified card's and a Traditional card's would be
    whichever came first (198). A Japanese word's meanings are English."""
    if card.language == "ja":
        return LATIN_FAMILIES
    return (*CJK_FAMILIES["zh-hant" if card.traditional else "zh"], *LATIN_FAMILIES)


def _families(card: Card) -> Sequence[str]:
    """The fonts for a card's own text: Japanese's for a Japanese word."""
    if card.language == "ja":
        return (*CJK_FAMILIES["ja"], *LATIN_FAMILIES)
    return LATIN_FAMILIES


def _alpha(color: str, alpha: float) -> QColor:
    found = QColor(color)
    found.setAlphaF(alpha)
    return found


@dataclass
class _Run:
    """One line of text, drawn at its baseline."""

    text: str
    font: QFont
    color: QColor
    at: QPointF


@dataclass
class _Block:
    """Text laid out to wrap, drawn from its top left."""

    layout: QTextLayout
    color: QColor
    at: QPointF
    formats: list[QTextLayout.FormatRange] = field(default_factory=list)


@dataclass
class _Box:
    """A chip, a button or a row's background; `hit`: what a click on it does."""

    rect: QRectF
    fill: QColor | None = None
    border: QColor | None = None
    radius: float = 6.0
    hit: str | None = None


@dataclass
class _Piece:
    """Something in a row: words in a font, in a box or not."""

    text: str
    font: QFont
    color: str
    box: tuple[QColor | None, QColor | None] | None = None
    hit: str | None = None


class _Painted:
    """The card laid out top to bottom, ready to paint: boxes, then text."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.y = float(PAD)
        self.boxes: list[_Box] = []
        self.runs: list[_Run] = []
        self.blocks: list[_Block] = []
        self.glyphs: list[tuple[glyphs.Glyph, QRectF, QColor]] = []
        self.texts: list[Painted] = []
        """The text that can be selected, in reading order (343)."""
        self.lines = 0

    def new_line(self) -> int:
        """A number for the next line of text: pieces on one line are copied
        with a space between them, lines with a new line."""
        self.lines += 1
        return self.lines

    def selectable(
        self, text: str, font: QFont, x: float, baseline: float, line: int
    ) -> None:
        """`text`, drawn as a run at `baseline`, can be selected."""
        if not text:
            return
        layout = _one_line(text, font)
        top = baseline - layout.lineAt(0).ascent()
        self.texts.append(Painted(text, layout, QPointF(x, top), line))

    @property
    def right(self) -> float:
        return self.width - PAD

    def row(self, pieces: Sequence[_Piece], gap: float = 8.0, right: float = 0) -> None:
        """Pieces left to right on a shared baseline, wrapping when full,
        short of the right edge by `right` (the buttons beside the first
        lines). Words too long for a line of their own - a long phrase's
        headword or reading - are wrapped on lines of their own (533)."""
        line: list[tuple[_Piece, float, QFontMetricsF]] = []
        x = float(PAD)
        for piece in pieces:
            metrics = QFontMetricsF(piece.font)
            width = metrics.horizontalAdvance(piece.text) + (16 if piece.box else 0)
            if (
                piece.box is None
                and piece.hit is None
                and width > self.right - right - PAD
            ):
                if line:
                    self._place(line)
                    line, x = [], float(PAD)
                self.text(piece.text, piece.font, piece.color, right=right)
                continue
            if line and x + width > self.right - right:
                self._place(line)
                line, x = [], float(PAD)
            line.append((piece, x, metrics))
            x += width + gap
        if line:
            self._place(line)

    def _place(self, line: list[tuple[_Piece, float, QFontMetricsF]]) -> None:
        ascent = max(m.ascent() + (4 if p.box else 0) for p, _, m in line)
        descent = max(m.descent() + (4 if p.box else 0) for p, _, m in line)
        baseline = self.y + ascent
        number = self.new_line()
        for piece, x, metrics in line:
            text_x = x + (8 if piece.box else 0)
            if piece.box is None and piece.hit is None:  # not a chip or a button
                self.selectable(piece.text, piece.font, text_x, baseline, number)
            if piece.box is not None:
                fill, border = piece.box
                width = metrics.horizontalAdvance(piece.text) + 16
                top = baseline - metrics.ascent() - 4
                rect = QRectF(x, top, width, metrics.height() + 8)
                self.boxes.append(
                    _Box(rect, fill, border, rect.height() / 2, piece.hit)
                )
            self.runs.append(
                _Run(
                    piece.text,
                    piece.font,
                    QColor(piece.color),
                    QPointF(text_x, baseline),
                )
            )
        self.y = baseline + descent + 2

    def text(
        self,
        text: str,
        font: QFont,
        color: str,
        x: float = PAD,
        formats: Sequence[tuple[int, int, QTextCharFormat]] = (),
        right: float = 0,
        fonts: Sequence[QTextLayout.FormatRange] = (),
    ) -> float:
        """`text` wrapped from `x` to the right edge, short of it by `right`
        (it can be selected); its height."""
        layout, height = _laid(text, font, self.right - right - x, fonts)
        self.texts.append(Painted(text, layout, QPointF(x, self.y), self.new_line()))
        ranges = []
        for start, end, format_ in formats:
            selection = QTextLayout.FormatRange()
            selection.start, selection.length = start, end - start
            selection.format = format_
            ranges.append(selection)
        self.blocks.append(_Block(layout, QColor(color), QPointF(x, self.y), ranges))
        self.y += height + 2
        return height

    def space(self, pixels: float) -> None:
        self.y += pixels

    def height(self) -> int:
        return round(self.y + PAD - 2)


def _one_line(text: str, font: QFont) -> QTextLayout:
    """`text` laid out on one line, as `QPainter.drawText` draws it: where a
    run's characters are, to select them."""
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.NoWrap)
    layout.setTextOption(option)
    layout.beginLayout()
    line = layout.createLine()
    line.setPosition(QPointF(0, 0))
    layout.endLayout()
    return layout


def _laid(
    text: str,
    font: QFont,
    width: float,
    fonts: Sequence[QTextLayout.FormatRange] = (),
) -> tuple[QTextLayout, float]:
    layout = QTextLayout(text, font)
    if fonts:
        layout.setFormats(fonts)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(10.0, width))
        line.setPosition(QPointF(0, height))
        height += line.height()
    layout.endLayout()
    return layout, height


class LookupCard(QWidget):
    """The lookup card every caption window shares. `opened`: a word was
    looked up - hovered until the card showed, or pinned."""

    opened = Signal()

    def __init__(
        self,
        learner: Learner,
        keys: KeyState | None = None,
        act: Act | None = None,
    ) -> None:
        """`keys`: whether Esc, Backspace or a mouse button is held anywhere
        (from `platform`, by way of `main`); `act`: runs a Learning action -
        the caption windows hand theirs, to repaint its captions."""
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput  # until pinned
            | ABOVE_ALL,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # on a Mac a tool window hides while the app isn't active - and the
        # app is never active while the learner is in another (polyglotic-hq 429)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setObjectName("lookup_card")
        self.model = Lookup(learner)
        self.keys = keys
        self.act: Act = act or _run
        self.request: WordAt | None = None
        self.origin: QWidget | None = None
        """The window a pinned card came from: it closes with it."""
        self.above = True
        self._pending: WordAt | None = None
        self._saving = False  # the categories open under Save to
        self._copied = False  # Copy says "Copied" until the next action or word
        self._painted = _Painted(style.px(WIDTH))
        self.selection = TextSelection()
        """The card's text selected by a drag (343)."""
        self._press: tuple[QPointF, str | None] | None = None
        """Where the left button went down on the card - and the part row
        there, looked up on release unless the mouse drags - till it's up."""
        self._dragging = False
        self._hits: list[tuple[QRectF, str]] = []
        self._hot: str | None = None
        self._hover = QTimer(self, singleShot=True, interval=HOVER_MS)
        self._hover.timeout.connect(self._show_pending)
        self._follow = QTimer(self, singleShot=True, interval=FOLLOW_MS)
        self._follow.timeout.connect(self._show_pending)
        self._hide = QTimer(self, singleShot=True, interval=HIDE_MS)
        self._hide.timeout.connect(self._hide_hover)
        self._leave = QTimer(self, singleShot=True, interval=LEAVE_MS)
        self._leave.timeout.connect(self.close_card)
        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self._look_at_keys)
        self.speech: WordSpeech | None = None
        """Says the word aloud (`use_speech`); None: no speaker button."""
        self._voice_help = False  # no voice: how Windows adds one, shown
        self._never_again = False  # the better-voice notice's box, ticked (518)
        self.create()  # its native window now: the first lookup shows at once

    def use_speech(self, speech: WordSpeech) -> None:
        """The pinned card's speaker says its word (`main`'s; polyglotic-hq
        286)."""
        self.speech = speech
        speech.changed.connect(self._speech_changed)

    def _speech_changed(self) -> None:
        if self.isVisible():
            self._render()

    @property
    def pinned(self) -> bool:
        return self.model.pinned and self.isVisible()

    # -- what the caption windows ask --------------------------------------------------

    def hover(self, word: WordAt) -> None:
        """The mouse is on `word`: its lookup once it has rested there -
        FOLLOW_MS after it came if a hover card is showing already (it
        follows the mouse). Not while a card is pinned."""
        if self.pinned:
            return
        self._hide.stop()
        if (
            self.isVisible()
            and self.request is not None
            and word.key == self.request.key
        ):
            return
        resting = self._pending is not None and self._pending.key == word.key
        self._pending = word
        if self.isVisible():
            self._follow.start()  # from the latest word the mouse came to
        elif not (resting and self._hover.isActive()):
            self._hover.start()  # from when the mouse came to this word

    def unhover(self) -> None:
        """The mouse left the word."""
        self._hover.stop()
        self._follow.stop()
        self._pending = None
        if self.isVisible() and not self.pinned and not self._hide.isActive():
            self._hide.start()

    def pin(self, word: WordAt, origin: QWidget | None = None) -> None:
        """`word` looked up and kept up, with the actions. `origin`: the
        caption window or transcript it came from - the card closes when
        that does (`closed_with`)."""
        self._hover.stop()
        self._follow.stop()
        self._hide.stop()
        self._pending = None
        self._open(word, pinned=True)
        self.origin = origin

    def closed_with(self, window: QWidget) -> None:
        """`window` closed or hid: a card pinned from it goes too - however
        it closed (its x, Alt+F4, the title bar's close, the picker), not
        only by a click the card sees (polyglotic-hq 133)."""
        if self.origin is window and self.isVisible():
            self.close_card()

    def hover_kept(self) -> None:
        """The mouse is still on the word shown: a hover card stays; a
        pinned one hasn't been "left"."""
        if self.pinned:
            self._leave.start()
        else:
            self._hide.stop()

    def refresh(self) -> None:
        """Learning changed elsewhere (the Words page, another device)."""
        if self.isVisible():
            self._render()

    def showing(self, key: tuple[int, int, int, int]) -> bool:
        """It shows, or is about to show, the word at `key` already."""
        if self.isVisible():
            return self.request is not None and self.request.key == key
        return self._pending is not None and self._pending.key == key

    def close_card(self) -> None:
        self._hover.stop()
        self._follow.stop()
        self._hide.stop()
        self._watch(False)
        self.model.close()
        self.request = None
        self.origin = None
        self._pending = None
        self._saving = False
        self._voice_help = False
        self._never_again = False
        self._end_press()
        self.selection.clear()
        if self.speech is not None:
            self.speech.forget()  # a word being said stops with its card
        self.hide()

    # -- showing -----------------------------------------------------------------------

    def _show_pending(self) -> None:
        self._follow.stop()
        if self._pending is not None and not self.pinned:
            self._open(self._pending, pinned=False)
        self._pending = None

    def _hide_hover(self) -> None:
        if not self.pinned:
            self.close_card()

    def _open(self, word: WordAt, pinned: bool) -> None:
        with spans.span("lookup_card.pin" if pinned else "lookup_card.hover"):
            self.request = word
            self._saving = False
            self._copied = False
            self._hot = None
            self._voice_help = False
            self._never_again = False
            self.selection.clear()
            if self.speech is not None:
                self.speech.forget()  # another word: the last one stops

            def shown() -> DictionaryEntry | None:
                # a pin is evidence the word isn't known: it may change
                self.model.show(
                    word.word,
                    word.context,
                    pinned,
                    word.at,
                    word.language,
                    word.fallbacks,
                )
                return self.model.entry() if pinned else None

            self.act(shown)
            # re-mapped, never live (550): shown below once it's drawn
            set_click_through(self, not pinned, show=False)
            self._render()
            self.show()  # on top already, and never raise_()d: that activates
            self._watch(pinned)
            self.opened.emit()

    def _watch(self, on: bool) -> None:
        """While pinned: Esc, Backspace and clicks elsewhere, here and anywhere."""
        app = QApplication.instance()
        if on:
            if app is not None:
                app.installEventFilter(self)
            if self.keys is not None:
                for name in ("escape", "backspace", "mouse"):
                    self.keys(name)  # forget presses from before it was pinned
                self._poll.start()
            self._leave.start()
        else:
            if app is not None:
                app.removeEventFilter(self)
            self._poll.stop()
            self._leave.stop()

    def _render(self) -> None:
        """Lays the card out, sizes it and places it by its word."""
        word = self.request
        if word is None:
            return
        card = self.model.card()
        painted = self._lay_out(card, self._width(card))
        self._painted = painted
        self.selection.use(painted.texts)  # kept while its text is the same
        self._hits = [(box.rect, box.hit) for box in painted.boxes if box.hit]
        # a screen reader: the word, and what its speaker does now
        self.setAccessibleName(card.word)
        description = self._say_tip(card)
        senses = [sense for reading in card.readings for sense in reading.definitions]
        if any(sense.classes for sense in senses):
            description = "\n".join(
                line for line in (*map(_sense_text, senses), description) if line
            )
        self.setAccessibleDescription(description)
        rect, self.above = place(
            word.rect, word.row, Size(painted.width, painted.height()), word.area
        )
        self.setGeometry(QRect(rect.x, rect.y, rect.width, rect.height))
        self.update()

    # -- the card's content ------------------------------------------------------------

    def _width(self, card: Card) -> int:
        if card.pinned:
            return style.px(WIDTH)
        low, high = (style.px(w) for w in HOVER_WIDTHS)
        if card.shows in (Shows.DICTIONARY_OUT, Shows.NO_DICTIONARY):  # sentences: wide
            return high
        headline = QFontMetricsF(self._headword_font(card)).horizontalAdvance(card.word)
        sense = (
            _sense_text(card.readings[0].definitions[0])
            if card.readings and card.readings[0].definitions
            else ""
        )
        reading = card.readings[0].reading if card.readings else card.guess
        counterpart = here(card.counterpart)[0] if card.counterpart else ""
        wanted = max(
            headline
            + QFontMetricsF(_font(15)).horizontalAdvance(reading)
            + style.px(110),
            QFontMetricsF(_font(13, _meanings(card))).horizontalAdvance(sense),
            QFontMetricsF(_here_font(card)).horizontalAdvance(counterpart),
        )
        return round(min(high, max(low, wanted + 2 * PAD)))

    @staticmethod
    def _headword_font(card: Card) -> QFont:
        px = 26 if card.pinned else 20
        if card.language == "ja":  # kanji and kana in a Japanese font
            return _font(px, (*CJK_FAMILIES["ja"], *LATIN_FAMILIES), bold=False)
        if has_han(card.word):
            script = "zh-hant" if card.traditional else "zh"
            return _font(px, (*CJK_FAMILIES[script], *LATIN_FAMILIES), bold=False)
        return _font(px - 2, bold=True)

    def _saying(self, card: Card) -> tuple[str, Say] | None:
        """The word's language and what its speaker shows; None: no speaker
        (a hover card, no speech wired, nothing to say)."""
        if not card.pinned or self.speech is None:
            return None
        language = word_language(card)
        if language is None:
            return None
        return language, self.speech.state(card.word, language, card.simplified)

    def _lay_out(self, card: Card, width: int) -> _Painted:
        painted = _Painted(width)
        saying = self._saying(card)
        # Close, and Say it: each a button at the text size, and a gap
        room = (style.px(22) + 4) * (2 if saying else 1)
        if card.pinned:
            self._top(painted, card, saying, room)
        self._headline(painted, card, room)
        if saying is not None and saying[1] is Say.NO_VOICE and self._voice_help:
            system = self.speech is None or self.speech.system_voice()
            self._no_voice(painted, saying[0], system)
        speech = self.speech
        if (
            saying is not None
            and speech is not None
            and speech.notice == speech.key(card.word, saying[0])
        ):
            self._better_voice(painted, saying[0])
        if card.shows is Shows.ENTRY and card.pinned:
            self._chips(painted, card)
        if card.counterpart:
            painted.space(3)
            painted.text(class_name(card.word_class), _ui(12), FAINT)
            self._counterpart(painted, card)
        if card.answered_by:
            self._answered_by(painted, card)
        if card.shows is Shows.ENTRY:
            self._readings(painted, card)
            if card.actions:
                self._actions(painted, card)
        elif card.shows is Shows.NOT_FOUND:
            self._not_found(painted, card)
        elif card.shows is Shows.DICTIONARY_OUT:
            self._dictionary_out(painted, card)
        elif card.shows is Shows.NO_DICTIONARY:
            painted.space(3)
            name = learned_name(card.language or "")
            painted.text(
                in_sentence(
                    _tr(
                        "The {language} dictionary is used once you learn {language}. "
                        "Captions and translation still work."
                    ),
                    language=name,
                )
                if tier_of(card.language or "") is Tier.FULL  # not learned (306)
                else in_sentence(
                    _tr(
                        "No dictionary for {language} yet. Captions and translation "
                        "still work."
                    ),
                    language=name,
                ),
                _ui(13),
                DIM,
            )
        elif not card.parts:
            painted.text(_tr("No Chinese for it in the dictionary"), _ui(13), DIM)
        if card.parts and (card.pinned or card.shows is Shows.CHINESE_FOR):
            self._parts(painted, card)
        if card.context is not None:
            self._context(painted, card)
        if card.offer or card.added:
            self._offer(painted, card)
        return painted

    def _offer(self, painted: _Painted, card: Card) -> None:
        """ "Learning Japanese?" - Learn Japanese too · Not now - asked once
        about a language with a dictionary that isn't being learned
        (DECISIONS.md #65, polyglotic-hq 262); or, just added, where it is."""
        painted.space(10)
        if not card.offer:
            name = learned_name(card.added)
            painted.text(
                in_sentence(
                    _tr(
                        "{language} is on your Learning page now, with its dictionary "
                        "to download there ({size} MB)."
                    ),
                    language=name,
                    size=QLocale().toString(card.added_pack / 1_000_000, "f", 1),
                )
                if card.added_pack
                else in_sentence(
                    _tr("{language} is on your Learning page now."), language=name
                ),
                _ui(12),
                DIM,
            )
            return
        name = learned_name(card.offer)
        painted.text(
            in_sentence(_tr("Learning {language} too?"), language=name),
            _ui(12),
            DIM,
        )
        painted.space(2)
        painted.row(
            [
                _Piece(
                    in_sentence(_tr("Learn {language} too"), language=name),
                    _ui(12, bold=True),
                    ACCENT,
                    (None, _alpha(ACCENT, 0.8)),
                    "learn_too",
                ),
                _Piece(_tr("Not now"), _ui(12), DIM, (None, QColor(LINE)), "not_now"),
            ],
            gap=6,
        )

    def _top(
        self, painted: _Painted, card: Card, saying: tuple[str, Say] | None, room: int
    ) -> None:
        """Back (to the word before the part shown), Say it and Close."""
        size = style.px(22)
        close = QRectF(painted.width - PAD - size, 8, size, size)
        painted.boxes.append(_Box(close, radius=6, hit="close"))
        glyph = QPointF(close.left() + style.px(6), close.top() + style.px(16))
        painted.runs.append(_Run("✕", _font(13), QColor(DIM), glyph))
        if saying is not None:
            say = QRectF(close.left() - size - 4, 8, size, size)
            painted.boxes.append(_Box(say, radius=6, hit="say"))
            shape, color = SAY_GLYPHS[saying[1]]
            inset = size * 0.18
            icon = say.adjusted(inset, inset, -inset, -inset)
            painted.glyphs.append((shape, icon, QColor(color)))
        if card.back_to:
            painted.row(
                [
                    _Piece(
                        f"←  {card.back_to}",
                        _font(13, _meanings(card)),
                        TEXT,
                        (None, None),
                        "back",
                    ),
                    _Piece(_tr("Backspace"), _ui(12), FAINT),
                ],
                gap=2,
                right=room,
            )

    def _no_voice(self, painted: _Painted, language: str, system: bool) -> None:
        """No voice for the word's language on this PC: how Windows adds
        one (Microsoft's steps, polyglotic-hq 286), and a button to it - on
        a Mac, how macOS adds one (Apple's steps, 428). On Linux the steps
        alone, and why (591): there is no settings page to open."""
        painted.space(4)
        painted.text(no_voice_steps(language, system), _ui(12), DIM)
        if on_linux():
            return
        painted.space(2)
        painted.row(
            [
                _Piece(
                    _tr("Open speech settings"),
                    _ui(12, bold=True),
                    ACCENT,
                    (None, _alpha(ACCENT, 0.8)),
                    "add_voice",
                )
            ]
        )

    def _better_voice(self, painted: _Painted, language: str) -> None:
        """The word was said in a basic voice: how to add a better one, a
        "Don't show again" box and Dismiss (518)."""
        painted.space(4)
        painted.text(better_voice_steps(language), _ui(12), DIM)
        painted.space(2)
        tick = "☑" if self._never_again else "☐"
        painted.row(
            [
                _Piece(
                    f"{tick} {never_again_text(language)}",
                    _ui(12),
                    TEXT,
                    (None, _alpha(DIM, 0.6)),
                    "voice_never",
                ),
                _Piece(
                    dismiss_text(),
                    _ui(12, bold=True),
                    ACCENT,
                    (None, _alpha(ACCENT, 0.8)),
                    "voice_dismiss",
                ),
            ]
        )

    def _headline(self, painted: _Painted, card: Card, room: int = 26) -> None:
        """The word and its reading; a word too long for the line beside the
        buttons (a pinned card's Say it and Close) shrinks, then wraps."""
        right = room if card.pinned else 0
        font = self._headword_font(card)
        smaller, fits = fitted(card.word, font, painted.right - right - PAD)
        # a little too long: smaller, on its line; far too long: `row` wraps it
        pieces = [_Piece(card.word, smaller if fits else font, TEXT)]
        reading = card.readings[0].reading if card.readings else card.guess
        if reading and (self.model.is_chinese or not card.pinned):
            pieces.append(_Piece(reading, _font(15, _families(card)), ACCENT))
        if card.other:
            families = (*CJK_FAMILIES["zh"], *LATIN_FAMILIES)
            pieces.append(_Piece(card.other, _font(15, families), FAINT))
        if card.base:
            pieces.append(_Piece(f"→ {card.base}", _font(14, _families(card)), FAINT))
        if not card.pinned and card.status is not None:
            pieces.append(
                self._chip(_status_name(card.status), STATUS_COLORS[card.status])
            )
        if not card.pinned and card.basic:
            pieces.append(self._basic_chip())
        painted.row(pieces, gap=10, right=right)

    def _basic_chip(self) -> _Piece:
        """From a basic dictionary: open data, meanings no person has
        checked (decision 0035)."""
        return self._chip(_tr("basic dictionary"), DIM)

    def _chip(self, text: str, color: str) -> _Piece:
        return _Piece(
            text,
            _ui(12, bold=True),
            color,
            (_alpha(color, 0.14), _alpha(color, 0.45)),
        )

    def _chips(self, painted: _Painted, card: Card) -> None:
        pieces = []
        if card.status is not None:
            pieces.append(
                self._chip(_status_name(card.status), STATUS_COLORS[card.status])
            )
        if card.saved_in is not None:
            pieces.append(self._chip(card.saved_in.name, card.saved_in.color))
        if card.chengyu:
            pieces.append(self._chip(_tr("chengyu"), CHENGYU))
        if card.basic:
            pieces.append(self._basic_chip())
        if card.heard:
            pieces.append(_Piece(heard_in(card.heard), _ui(12), FAINT))
        if card.load_stage is not None:  # the learning load's stage (324)
            stage = card.load_stage
            colour = TEXT if stage is Stage.READY else STAGE_COLOURS[stage]
            said = stage_text(stage, card.load_heard, card.load_step)
            pieces.append(self._chip(said, colour))
        if pieces:
            painted.space(2)
            painted.row(pieces, gap=6)

    def _counterpart(self, painted: _Painted, card: Card) -> None:
        """ "Here: ngân hàng" - what the word is in its line's translation
        (polyglotic-hq 328): the label faint, the words in the card's text
        colour. Larger where the row's language has no dictionary: the
        card's main content there."""
        text, (start, end) = here(card.counterpart)
        faint = QTextCharFormat()
        faint.setForeground(QColor(FAINT))
        formats = [(a, b, faint) for a, b in ((0, start), (end, len(text))) if a < b]
        main = card.shows is Shows.NO_DICTIONARY
        painted.space(4 if main else 3)
        painted.text(text, _here_font(card), TEXT, formats=formats)

    def _answered_by(self, painted: _Painted, card: Card) -> None:
        """Which dictionary answered, when it isn't the row's language's -
        a fallback found the word (polyglotic-hq 337): faint, one line."""
        painted.space(3)
        painted.text(answered_by(card.answered_by), _ui(12), FAINT)

    def _readings(self, painted: _Painted, card: Card) -> None:
        meanings = _font(13, _meanings(card))
        for index, reading in enumerate(card.readings):
            painted.space(3)
            if not card.pinned:
                self._definitions(painted, reading.definitions[:1], meanings, False)
                continue
            # a reading of its own (a phonetic, a second pinyin): nothing if
            # there's none - not a lone blue "-" (polyglotic-hq 192, 198)
            if (index or not self.model.is_chinese) and reading.reading:
                painted.text(reading.reading, _font(14, _families(card)), ACCENT)
            self._definitions(painted, reading.definitions, meanings, True)
            if reading.measure_words:
                painted.text(
                    _tr("Measure word: {words}").format(
                        words=", ".join(reading.measure_words)
                    ),
                    _ui(12),
                    FAINT,
                )
        if card.more_readings:
            painted.text(more_readings(card.more_readings), _ui(12), FAINT)

    @staticmethod
    def _definitions(
        painted: _Painted,
        senses: Sequence[DictionarySense],
        font: QFont,
        numbered: bool,
    ) -> None:
        text = ""
        labels = []
        for index, sense in enumerate(senses, 1):
            if numbered:
                text += ("   " if index > 1 else "") + f"{index}. "
            before, classes, after = _sense_parts(sense)
            text += before
            if classes:
                label = QTextLayout.FormatRange()
                label.start = len(text.encode("utf-16-le")) // 2  # Qt's offsets
                label.length = len(classes.encode("utf-16-le")) // 2
                label.format.setFont(_ui(13))
                labels.append(label)
            text += classes + after
        painted.text(text or "-", font, TEXT, fonts=labels)

    def _not_found(self, painted: _Painted, card: Card) -> None:
        painted.space(3)
        if not self.model.is_chinese and not card.meaning:
            painted.text(_tr("Not in the dictionary"), _ui(13), DIM)
            return
        text = (
            _tr("Not in the dictionary as a whole - {meaning}").format(
                meaning=card.meaning
            )
            if card.meaning
            else _tr("Not in the dictionary as a whole")
        )
        painted.text(text, _ui(13), DIM)

    def _dictionary_out(self, painted: _Painted, card: Card) -> None:
        assert card.problem is not None
        what, fix = dictionary_out(card.problem, self.model.is_chinese)
        painted.space(3)
        painted.text(what, _ui(13, bold=True), TEXT)
        painted.text(fix, _ui(12), DIM)

    def _actions(self, painted: _Painted, card: Card) -> None:
        """Add to deck (first, the primary), Known, Save to, Remove."""
        painted.space(8)
        deck = STATUS_COLORS[WordStatus.LEARNING]
        add = (
            _Piece(
                f"✓ {_tr('Add to deck')}",
                _ui(12, bold=True),
                deck,
                (_alpha(deck, 0.18), _alpha(deck, 0.8)),
                "deck",
            )
            if card.in_deck
            else _Piece(
                _tr("Add to deck"),
                _ui(12, bold=True),
                ACCENT_TEXT,
                (QColor(ACCENT), QColor(ACCENT)),
                "deck",
            )
        )
        known = _Piece(
            f"✓ {_tr('Known')}" if card.known else _tr("Known"),
            _ui(12),
            TEXT,
            (_alpha(DIM, 0.2) if card.known else None, QColor(LINE)),
            "known",
        )
        saved = card.saved_in
        save = _Piece(
            f"{_tr('Save to')} {'▴' if self._saving else '▾'}",
            _ui(12),
            saved.color if saved else TEXT,
            (None, QColor(saved.color) if saved else QColor(LINE)),
            "save",
        )
        pieces = [add, known, save]
        if saved is not None:
            pieces.append(_Piece(_tr("Remove"), _ui(12), DIM, (None, None), "remove"))
        pieces.append(  # the word, its reading and meaning (333)
            _Piece(
                f"✓ {_tr('Copied')}" if self._copied else _tr("Copy"),
                _ui(12),
                TEXT,
                (None, QColor(LINE)),
                "copy",
            )
        )
        painted.row(pieces, gap=6)
        if card.load_stage is Stage.READY:  # the load's one-click check (324)
            know, not_yet = check_texts()
            painted.space(2)
            painted.row(
                [
                    _Piece(know, _ui(12), TEXT, (None, QColor(LINE)), "load_know"),
                    _Piece(
                        not_yet, _ui(12), TEXT, (None, QColor(LINE)), "load_not_yet"
                    ),
                ],
                gap=6,
            )
        elif card.load_offer:
            painted.space(2)
            painted.row(
                [_Piece(add_text(), _ui(12), TEXT, (None, QColor(LINE)), "load_add")],
                gap=6,
            )
        if self._saving:
            painted.space(2)
            chips = []
            for category in card.categories:
                current = saved is not None and saved.id == category.id
                chips.append(
                    _Piece(
                        f"✓ {category.name}" if current else category.name,
                        _ui(12, bold=current),
                        category.color,
                        (
                            _alpha(category.color, 0.22 if current else 0.08),
                            _alpha(category.color, 0.9 if current else 0.35),
                        ),
                        f"save:{category.id}",
                    )
                )
            chips.append(
                _Piece(
                    f"+ {_tr('New category')}",
                    _ui(12),
                    DIM,
                    (None, QColor(LINE)),
                    "new_category",
                )
            )
            painted.row(chips, gap=6)

    def _parts(self, painted: _Painted, card: Card) -> None:
        title = {
            PartsTitle.INSIDE: _tr("Inside this word"),
            PartsTitle.WORDS_AND_CHARACTERS: _tr("Words and characters"),
            PartsTitle.CHINESE_FOR: _tr("Chinese for it"),
        }[card.parts_title or PartsTitle.INSIDE]
        painted.space(8)
        painted.row([_Piece(title.upper(), _ui(12, bold=True), FAINT)])
        hanzi = (  # a basic pack's parts in its script's fonts (390)
            _font(17, _families(card))
            if card.basic
            else _font(17, (*CJK_FAMILIES["zh"], *LATIN_FAMILIES))
        )
        small = _font(13)  # pinyin
        meanings = _font(13, _meanings(card))
        for index, part in enumerate(card.parts):
            top = painted.y
            words = QFontMetricsF(hanzi)
            baseline = top + 4 + words.ascent()
            x = PAD + 8.0
            number = painted.new_line()
            painted.runs.append(
                _Run(part.word, hanzi, QColor(TEXT), QPointF(x, baseline))
            )
            painted.selectable(part.word, hanzi, x, baseline, number)
            x += words.horizontalAdvance(part.word) + 10
            meaning = part.meaning or _tr("not in the dictionary")
            meaning_font = meanings if part.meaning else _ui(13)
            rest = QFontMetricsF(small)
            if part.reading:
                painted.runs.append(
                    _Run(part.reading, small, QColor(ACCENT), QPointF(x, baseline))
                )
                painted.selectable(part.reading, small, x, baseline, number)
                x += rest.horizontalAdvance(part.reading) + 8
            room = painted.right - 8 - x
            shown = QFontMetricsF(meaning_font).elidedText(
                meaning, Qt.TextElideMode.ElideRight, room
            )
            painted.runs.append(
                _Run(shown, meaning_font, QColor(DIM), QPointF(x, baseline))
            )
            painted.selectable(shown, meaning_font, x, baseline, number)
            height = words.height() + 8
            rect = QRectF(PAD, top, painted.right - PAD, height)
            if card.pinned:
                painted.boxes.append(_Box(rect, radius=8, hit=f"part:{index}"))
            painted.y = top + height + 1

    def _context(self, painted: _Painted, card: Card) -> None:
        """The caption's row the word was in, and its translation."""
        context = card.context
        assert context is not None
        painted.space(10)
        top = painted.y
        formats = []
        if card.found_at is not None:
            bold = QTextCharFormat()
            bold.setFontWeight(QFont.Weight.Bold)
            bold.setForeground(QColor(ACCENT))
            formats.append((*card.found_at, bold))
        families = (*CJK_FAMILIES["zh"], *LATIN_FAMILIES)
        painted.text(context.sentence, _font(13, families), TEXT, PAD + 10, formats)
        if context.translation:
            painted.text(context.translation, _font(12, families), DIM, PAD + 10)
        painted.boxes.append(
            _Box(QRectF(PAD, top, 2, painted.y - top - 2), QColor(LINE), radius=1)
        )

    # -- painting and the mouse ---------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        with spans.span("lookup_card.paint"):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setPen(QColor(LINE))
            painter.setBrush(QColor(SURFACE))  # opaque: no caption shows through
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10
            )
            for box in self._painted.boxes:
                fill = box.fill
                if box.hit is not None and box.hit == self._hot:
                    fill = (
                        QColor(255, 255, 255, 46) if fill is None else fill.lighter(125)
                    )
                if fill is None and box.border is None:
                    continue
                painter.setPen(
                    box.border if box.border is not None else Qt.PenStyle.NoPen
                )
                painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    box.rect.adjusted(0.5, 0.5, -0.5, -0.5), box.radius, box.radius
                )
            for shape, square, color in self._painted.glyphs:
                glyphs.paint(painter, shape, square, color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_alpha(ACCENT, SELECTED))
            for rect in self.selection.highlights():
                painter.drawRect(rect)
            for run in self._painted.runs:
                painter.setFont(run.font)
                painter.setPen(run.color)
                painter.drawText(run.at, run.text)
            for block in self._painted.blocks:
                painter.setPen(block.color)
                block.layout.draw(painter, block.at, block.formats)
            painter.end()

    def _hit_at(self, pos: QPointF) -> str | None:
        return next((hit for rect, hit in self._hits if rect.contains(pos)), None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._press is not None:  # the left button is down: a drag selects
            start, _ = self._press
            far = (pos - start).manhattanLength() >= QApplication.startDragDistance()
            self._dragging = self._dragging or far
            if self._dragging:
                self.selection.extend(pos)
                self.update()
            return
        hit = self._hit_at(pos)
        if hit and not hit.startswith(ROW):
            shape = Qt.CursorShape.PointingHandCursor
        elif self.selection.on_text(pos):  # a part row's too: a drag selects
            shape = Qt.CursorShape.IBeamCursor
        elif hit:
            shape = Qt.CursorShape.PointingHandCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        if self.cursor().shape() != shape:
            self.setCursor(shape)
        if hit != self._hot:
            self._hot = hit
            tip = self.tip(hit) if hit else ""
            if tip:
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()
            self.update()

    def _say_tip(self, card: Card) -> str:
        """What the speaker does now, in words: its tooltip, and the card's
        description for a screen reader. "" without one."""
        saying = self._saying(card)
        if saying is None or self.speech is None:
            return ""
        language, state = saying
        if state is Say.NO_VOICE:
            name = learned_name("zh" if language == "zh-hant" else language)
            return in_sentence(
                pc_or_mac(
                    _tr("No {language} voice on this PC"),
                    _tr("No {language} voice on this Mac"),
                ),
                language=name,
            )
        if state is Say.SPEAKING:
            return _tr("Stop (R)")
        return _tr("Say it (R)")

    def tip(self, what: str) -> str:
        """A button's or row's tooltip: today's words."""
        if what == "say":
            return self._say_tip(self.model.card())
        if what.startswith("part:"):
            parts = self.model.card().parts
            index = int(what.removeprefix("part:"))
            if index < len(parts):
                return _tr("Look up {word}").format(word=parts[index].word)
            return ""
        if what.startswith("save:"):
            category = next(
                (c for c in self.model.card().categories if c.id == what[5:]), None
            )
            return (
                _tr("Save to {category}").format(category=category.name)
                if category
                else ""
            )
        return {
            "deck": _tr("Put it in the words you're learning"),
            "known": _tr("I know this word - don't highlight it"),
            "remove": _tr("Remove from your saved words"),
            "learn_too": _tr("Add it to the languages on your Learning page"),
            "not_now": _tr("Don't ask about this language again"),
            "back": _tr("Back (Backspace)"),
            "close": _tr("Close (Esc)"),
            "add_voice": pc_or_mac(
                _tr("Opens Windows' Settings, where voices are added"),
                _tr("Opens System Settings, where voices are added"),
            ),
            "copy": hotkeys_here(
                _tr("Copy the word, its reading and meaning (Ctrl+C)")
            ),
        }.get(what, "")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """A button acts at once. Elsewhere the left button starts a
        selection (on a part row, a click without a drag looks the part up,
        on release); the right one copies the selection - no menu, never
        the keyboard."""
        event.accept()
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            if not self.selection.empty:
                at = event.globalPosition().toPoint()
                copy_quietly(self.selection.text(), at, self)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit_at(pos)
        if hit is not None and not hit.startswith(ROW):
            self.do(hit)
            return
        self._press, self._dragging = (pos, hit), False
        self.selection.start(pos)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        event.accept()
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        _, hit = self._press
        dragged = self._dragging
        self._end_press()
        if dragged and self.keys is not None:
            self.keys("mouse")  # the drag's press, perhaps let go off the card
        if not dragged and hit is not None:
            self.do(hit)  # a part row, clicked

    def _end_press(self) -> None:
        self._press, self._dragging = None, False

    def enterEvent(self, event: QEnterEvent) -> None:
        self._leave.stop()

    def leaveEvent(self, event: QEvent) -> None:
        if self._hot is not None:
            self._hot = None
            self.update()
        if self.pinned:
            self._leave.start()

    def do(self, what: str) -> None:
        """What a click on the card does: `what` is a button's or row's name."""
        model = self.model
        with spans.span("lookup_card.action"):
            if what == "close":
                self.close_card()
                return
            self._copied = what == "copy"
            if what == "copy":  # to the clipboard, nowhere else (333)
                QGuiApplication.clipboard().setText(copy_text(model.card()))
            elif what == "say":
                self._say()
            elif what == "add_voice":
                if self.speech is not None:
                    self.speech.add_voice()
            elif what == "voice_never":
                self._never_again = not self._never_again
            elif what == "voice_dismiss":
                if self.speech is not None:
                    self.speech.dismiss(self._never_again)
                self._never_again = False
            elif what == "back":
                model.back()
            elif what == "save":
                self._saving = not self._saving
            elif what.startswith("part:"):
                index = int(what.removeprefix("part:"))

                def part() -> DictionaryEntry | None:
                    model.part(index)
                    return model.entry()

                self.act(part)
            elif what.startswith("save:"):
                category = what.removeprefix("save:")
                self.act(lambda: model.save_to(category))
                self._saving = False
            elif what in ("learn_too", "not_now"):
                (model.learn_too if what == "learn_too" else model.not_now)()
            elif what == "new_category":
                self.act(lambda: model.new_category(_tr("New category")))
                self._saving = False
            elif what in ("load_know", "load_not_yet"):
                self.act(lambda: model.load_check(what == "load_know"))
            elif what == "load_add":
                self.act(model.load_add)
            else:
                self.act(
                    {
                        "deck": model.add_to_deck,
                        "known": model.known,
                        "remove": model.remove,
                    }[what]
                )
            self._render()

    def _say(self) -> None:
        """The speaker: says the word, or stops it; with no voice, shows
        (or hides) how Windows adds one."""
        card = self.model.card()
        saying = self._saying(card)
        if saying is None or self.speech is None:
            return
        language, state = saying
        if state is Say.NO_VOICE:
            self._voice_help = not self._voice_help
        else:
            self.speech.toggle(card.word, language, card.simplified)

    @staticmethod
    def _say_key(watched: QObject, event: QKeyEvent) -> bool:
        """R pressed, for this card: once (the key goes to the window, then
        the widget with the keyboard), not held, not typed into a text
        field."""
        if event.key() != SAY_KEY or event.isAutoRepeat():
            return False
        if event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, _TYPING):
            return False
        return watched is (focus or QApplication.activeWindow())

    def _copy_key(self, watched: QObject, event: QKeyEvent) -> bool:
        """Ctrl+C pressed, for this card's Copy (333): as R is (`_say_key`) -
        while one of the app's windows has the keyboard, not in a text
        field, and only while the card shows Copy."""
        if not event.matches(QKeySequence.StandardKey.Copy) or event.isAutoRepeat():
            return False
        selected = not self.selection.empty
        if not (selected or self.model.card().actions):
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, _TYPING):
            return False
        if not selected and _has_selection(focus):
            return False  # words selected where the keyboard is: theirs (343)
        return watched is (focus or QApplication.activeWindow())

    def _copy(self) -> None:
        """Ctrl+C: what's selected on the card, else the whole card (Copy)."""
        if self.selection.empty:
            self.do("copy")
        else:
            copy_quietly(self.selection.text(), QCursor.pos(), self)

    # -- closing without the focus ---------------------------------------------------------

    def _back(self) -> None:
        if self.model.back():
            self._render()

    def _look_at_keys(self) -> None:
        keys = self.keys
        if keys is None or not self.pinned:
            return
        if keys("escape"):
            self.close_card()
            return
        if keys("backspace"):
            self._back()
        if keys("mouse") and self._press is None:  # not a drag from the card
            at = QCursor.pos()
            # a click on this app's own windows is the event filter's
            if (
                not self.frameGeometry().contains(at)
                and QApplication.widgetAt(at) is None
            ):
                self.close_card()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            key = getattr(event, "key", lambda: None)()
            if key == Qt.Key.Key_Escape:
                self.close_card()
            elif key == Qt.Key.Key_Backspace:
                self._back()
            elif (
                self.speech is not None
                and isinstance(event, QKeyEvent)
                and self._say_key(watched, event)
            ):
                self.do("say")
                return True  # the card's: not a list's search for "r"
            elif isinstance(event, QKeyEvent) and self._copy_key(watched, event):
                self._copy()
                return True  # the card's: not a list's own copy
        elif (
            kind == QEvent.Type.MouseButtonPress
            and isinstance(watched, QWidget)
            and watched is not self
        ):
            position = getattr(event, "globalPosition", None)
            at = position().toPoint() if position is not None else QCursor.pos()
            if not self.frameGeometry().contains(at):
                self.close_card()
        return False
