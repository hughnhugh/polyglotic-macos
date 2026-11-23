"""Learning, a page of the main window (polyglotic-hq 262; 248's IA.md,
sections 3 and 3.6; the user's F19, F29 and F30): what you're learning,
what each language's dictionary can do, your level, and which words
captions point out - each said in words, not left to guess.

Top to bottom, in the pages' column:
- **a card per language being learned** (`views.learning.cards`): its
  dictionary's tier - full, basic or none yet - and what that gives; a
  full dictionary's level, with "Change your level" for each one open
  (and what a level does: words at or below it count as known, nothing
  is tested) - every full language learned is open at once, each keeping
  its own words, one added here opening as it's added (DECISIONS #110,
  decision 0095); "Make X your main language" for another full dictionary
  (Words' first section, Home's; from the next start); "Stop learning"
  for the others;
- **Learn another language** - every caption language, by name, each
  saying what it gets (none pinned on top: 293);
- **Word introductions** - Off · A few per caption · Every new word
  (`core.learning.highlights.WordIntroductions`), what each does, a
  caption drawn with the marks, and where the words go;
- **Words and Anki** - Words, and the site's help on importing;
- **Your learning data** - Account's "Delete learning data…", the same
  command.

The page only shows and asks: `main` hands over the cards and the choice,
and turns what's asked (`languages_wanted`, `introductions_chosen`,
`change_level_wanted`, `words_wanted`) into the settings and today's level
picker. Holds no words or caption text: its sample caption is the app's
own.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QLocale,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.first_known import MOST_KNOWN
from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import (
    LearningLanguages,
    Tier,
    learned_code,
    tier_of,
)
from polyglotic_desktop.core.learning.levels import (
    DEFAULT_WINDOW,
    LINKS_FROM,
    MAX_WINDOW,
    MIN_WINDOW,
    UNKNOWN_LEVEL_LINKS_FROM,
    UNLIMITED,
    LanguageChoices,
    LinkChoice,
    WindowSize,
)
from polyglotic_desktop.core.shared.papers import HELP_ANKI
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES
from polyglotic_desktop.ui_next.caption_marks import IN_DECK, UNFAMILIAR
from polyglotic_desktop.ui_next.controls import (
    Card,
    Combo,
    Flow,
    Segmented,
    focus_kept,
    label,
    page_button,
    right_row,
)
from polyglotic_desktop.ui_next.home import OneClick, Page
from polyglotic_desktop.ui_next.known_map_card import KnownMapCard
from polyglotic_desktop.ui_next.languages import (
    in_sentence,
    learned_name,
    target_languages,
)
from polyglotic_desktop.ui_next.load_card import LoadCard
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.pack_row import PackRow, size_text
from polyglotic_desktop.ui_next.views.learning import (
    WINDOW_CHOICES,
    Custom,
    InstalledPackLine,
    LanguageCard,
    PackKnown,
    PackLine,
    QuickMarksLine,
    offered,
    pack_known,
    typed_window,
    window_choice,
)
from polyglotic_desktop.ui_next.views.words import LevelLine


def _tr(text: str) -> str:
    return QApplication.translate("Learning", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Learning", text, None, n)


def learnable() -> list[str]:
    """Every language that can be learned, by name: each caption language's
    learned code, once (Simplified and Traditional Chinese are one) - none
    pinned on top (polyglotic-hq 293); each says what its dictionary gives."""
    codes = dict.fromkeys(learned_code(c) for c in target_languages(own=()))
    return sorted(codes, key=learned_name)


def tier_name(tier: Tier) -> str:
    return {
        Tier.FULL: _tr("Full dictionary"),
        Tier.BASIC: _tr("Basic dictionary"),
        Tier.NONE: _tr("No dictionary yet"),
    }[tier]


def what_it_gives(
    code: str,
    tier: Tier,
    pack_here: bool = False,
    known: PackKnown | None = None,
    on_card: bool = True,
) -> str:
    """What learning `code` gives, by its dictionary's tier - the line under
    its name on its card, or under "Learn another language" (`on_card`
    False) (polyglotic-hq 248, sections 3.1 and 3.3). A basic language's
    says only what the app knows of its pack (`known`; None: nothing):
    one offered is "once it's downloaded"; none to be had, no dictionary
    yet and what works without one; not known, no promise either way - the
    release may come before any list is published (329's QA, 330)."""
    if code == "zh":
        return _tr(
            "CC-CEDICT, with pinyin. Lookups, your level, word introductions, "
            "the words you hear and save, and an Anki deck."
        )
    if code == "en":
        return _tr(
            "ECDICT, with meanings in Chinese. Lookups, your level, word "
            "introductions, the words you hear and save, and an Anki deck."
        )
    name = learned_name(code)
    if tier is Tier.BASIC and pack_here:
        # learned with its pack here, it keeps learning data (decision 0175)
        return _tr(
            "From open data, meanings not checked by a person. Lookups, your "
            "level, word introductions, the words you hear and save, and an "
            "Anki deck."
        )
    if tier is Tier.BASIC and known is PackKnown.NONE_YET and on_card:
        # its tier says "No dictionary yet", its row "isn't ready" with Retry
        return _tr(
            "Captions and translation work without one, and a word you look up "
            "says what it is in that line's translation."
        )
    if tier is Tier.BASIC and known is PackKnown.NONE_YET:  # "Here: ..." works
        return in_sentence(
            _tr(
                "There's no {language} dictionary to download yet. Captions and "
                "translation work, and a word you look up says what it is in that "
                "line's translation."
            ),
            language=name,
        )
    if tier is Tier.BASIC and known is PackKnown.CHECKING and not on_card:
        # the list held is old and being checked: not a no from it (425)
        return _tr("Checking the list of dictionaries.")
    if tier is Tier.BASIC and known is not PackKnown.OFFERED and on_card:
        return in_sentence(
            pc_or_mac(
                _tr(
                    "A basic dictionary from open data (meanings not checked by a "
                    "person), if one is ready: lookups in {language} captions once it's "
                    "on this PC. Captions and translation work either way."
                ),
                _tr(
                    "A basic dictionary from open data (meanings not checked by a person), "
                    "if one is ready: lookups in {language} captions once it's on this "
                    "Mac. Captions and translation work either way."
                ),
            ),
            language=name,
        )
    if tier is Tier.BASIC and known is not PackKnown.OFFERED:
        return in_sentence(
            _tr(
                "A basic dictionary from open data (meanings not checked by a "
                "person), if one is ready: its card offers it once you add "
                "{language}. Captions and translation work either way."
            ),
            language=name,
        )
    if tier is Tier.BASIC:  # its pack's row says what it's doing
        return in_sentence(
            _tr(
                "A basic dictionary from open data, meanings not checked by a person: "
                "lookups in {language} captions once it's downloaded. Until then "
                "captions and translation work, without lookups."
            ),
            language=name,
        )
    return _tr(
        "Captions and translation work; there are no lookups or word "
        "introductions yet. We'll add a dictionary when one passes our check."
    )


def level_text(line: LevelLine) -> str:
    """A language's level, in Words' words (the same translations)."""
    tr = QApplication.translate
    if not line.picked:
        return tr("Words", "Not set yet - words count as known up to a middle level.")
    if line.words is not None and line.words <= 0:
        return tr("Words", "Just starting - no words known yet")
    if line.words is not None:
        return tr("Words", "About {count} of the most common words").format(
            count=QLocale().toString(line.words)
        )
    scheme = tr("Words", line.scheme)  # the schemes' names are Words'
    if not line.level:
        return tr("Words", "{scheme}: just starting").format(scheme=scheme)
    return tr("Words", "{scheme}: {level}").format(scheme=scheme, level=line.level)


INTRODUCTION_LINES = {
    WordIntroductions.OFF: QT_TRANSLATE_NOOP(
        "Learning",
        "No new words are pointed out. Words you've saved or put in your deck "
        "still show in their colours.",
    ),
    WordIntroductions.A_FEW: QT_TRANSLATE_NOOP(
        "Learning",
        "The commonest new words and the ones you keep hearing - at most about "
        "one word in twenty, and two a line.",
    ),
    WordIntroductions.EVERY: QT_TRANSLATE_NOOP(
        "Learning",
        "Every word that's new to you. Busy in fast speech; good for slow, "
        "careful listening.",
    ),
}


def introductions_line(choice: WordIntroductions) -> str:
    return _tr(str(INTRODUCTION_LINES[choice]))


SAMPLES: dict[bool, tuple[tuple[str, str], ...]] = {
    # (word, mark): "new" shows with a few or every; "more" with every
    True: (
        ("我今天去", ""),
        ("超市", "new"),
        ("买了", ""),
        ("榴莲", "more"),
        ("和", ""),
        ("酸奶", "deck"),
    ),
    False: (
        ("The ", ""),
        ("quarterly", "new"),
        (" figures look ", ""),
        ("promising", "deck"),
        (", the ", ""),
        ("analysts", "more"),
        (" said", ""),
    ),
}
"""The sample caption, Chinese (True) or English: each piece and its mark -
"new" shows with a few or every, "more" with every, "deck" always."""


class IntroductionSample(QWidget):
    """A caption as a caption window draws it, with the marks the choice
    gives: new words dotted in yellow, a word in the deck dashed in green
    (`caption_marks`' colours and shapes). The app's own sentence, in the
    language being learned."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("learning.sample")
        self.chinese = True
        self.choice = WordIntroductions.A_FEW
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(style.px(52))

    def show_choice(self, choice: WordIntroductions, chinese: bool) -> None:
        self.choice, self.chinese = choice, chinese
        self.update()

    def _font(self) -> QFont:
        font = QFont()
        families = CJK_FAMILIES["zh"] if self.chinese else LATIN_FAMILIES
        font.setFamilies(list(families))
        font.setPixelSize(style.px(20))
        return font

    def _marked(self, mark: str) -> str:
        if mark == "deck":
            return "deck"
        shown = {
            WordIntroductions.OFF: (),
            WordIntroductions.A_FEW: ("new",),
            WordIntroductions.EVERY: ("new", "more"),
        }[self.choice]
        return "new" if mark in shown else ""

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 12, 16, 235))  # a caption window's panel
        painter.drawRoundedRect(panel, 8, 8)
        font = self._font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        x = float(style.px(14))
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2
        for text, mark in SAMPLES[self.chinese]:
            width = metrics.horizontalAdvance(text)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                QRectF(x, 0, width + 2, self.height()),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            shown = self._marked(mark)
            if shown:
                pen = QPen(QColor(UNFAMILIAR if shown == "new" else IN_DECK))
                pen.setWidthF(max(1.5, style.px(2)))
                pen.setStyle(
                    Qt.PenStyle.DotLine if shown == "new" else Qt.PenStyle.DashLine
                )
                painter.setPen(pen)
                y = baseline + metrics.descent() + 1
                painter.drawLine(int(x), int(y), int(x + width), int(y))
            x += width
        painter.end()


def reset_question(language: str, back_to: LevelLine, changes: int) -> tuple[str, str]:
    """Reset's question for quick marks (polyglotic-hq 342): its title,
    and what it changes - how many words, and to what level."""
    return (
        in_sentence(_tr("Reset {language}'s known words?"), language=language),
        _trn(
            "About %Ln word(s) you marked known in bulk will count as new again, "
            "and your level goes back to: {level}. Words you marked yourself "
            "stay as you set them.",
            changes,
        ).format(level=_ended(level_text(back_to))),
    )


class LanguageCardView(Card):
    """One language's card (`views.learning.LanguageCard`)."""

    choices_chosen = Signal(object)
    """The learner chose its learning window's size or which of its words
    are linked: the language's `LanguageChoices` after it."""
    first_known_wanted = Signal(int)
    """"Mark known": the first so many words, known (342)."""
    undo_known_wanted = Signal()
    reset_known_wanted = Signal()
    """"Reset...": `main` asks first, saying how many words it changes."""

    def __init__(self, card: LanguageCard, running: str | None) -> None:
        name = learned_name(card.code)
        super().__init__(name)
        self.setObjectName("Card")
        self.code = card.code
        self.setAccessibleName(name)
        assert self.title is not None
        heading = QHBoxLayout()
        heading.setSpacing(10)
        self.column.removeWidget(self.title)
        heading.addWidget(self.title)
        # no pack in the list held: "No dictionary yet", as it is (330)
        tier = label(tier_name(Tier.NONE if card.no_pack_yet else card.tier), "Dim")
        heading.addWidget(tier)
        heading.addStretch(1)
        self.column.insertLayout(0, heading)
        said = what_it_gives(card.code, card.tier, card.pack_here, card.pack_known)
        self.gives = label(said, "Faint", wrap=True)  # "Faint": its style's name
        self.add(self.gives)
        self.recorded: QLabel | None = None
        if card.recorded_size:  # a full dictionary's recorded words (0197)
            self.recorded = label(
                _tr("Its commonest words are recorded ({size}).").format(
                    size=size_text(card.recorded_size)
                ),
                "Faint",
                wrap=True,
            )
            self.recorded.setObjectName(f"learning.{card.code}.recorded")
            self.recorded.setToolTip(card.recorded_credits)
            self.add(self.recorded)

        self.pack: PackRow | None = None
        # a basic language's pack (decision 0122) - with none to be had too:
        # "isn't ready yet", and Retry finds one published since (330)
        if card.pack is not None:
            self.pack = PackRow(card.code, self)
            self.pack.show_line(card.pack)
            self.add(self.pack)

        self.change_level: QPushButton | None = None
        if card.level is not None:
            line = QHBoxLayout()
            line.setSpacing(12)
            words = QVBoxLayout()
            words.setSpacing(2)
            words.addWidget(label(_tr("Your level"), "RowTitle"))
            level = label(level_text(card.level), wrap=True)
            level.setObjectName(f"learning.{card.code}.level")
            words.addWidget(level)
            line.addLayout(words, 1)
            if card.can_change_level:
                self.change_level = _button(
                    _tr("Change your level"), f"learning.{card.code}.change_level"
                )
                line.addWidget(self.change_level)
            self.add(line)
            if card.can_change_level:
                self.add(
                    label(
                        _tr(
                            "Words at or below your level count as known, and the "
                            "next ones are pointed out. Nothing is tested: a click "
                            "on any word corrects it."
                        ),
                        "Faint",
                        wrap=True,
                    )
                )
            elif card.tier is Tier.FULL:
                self.add(
                    label(
                        in_sentence(
                            _tr("You can change it while {language} is in use."),
                            language=learned_name(card.code),
                        ),
                        "Faint",
                        wrap=True,
                    )
                )

        self.first: QComboBox | None = None
        self.first_number: QSpinBox | None = None
        self.mark_known: QPushButton | None = None
        self.undo_known: QPushButton | None = None
        self.reset_known: QPushButton | None = None
        self.quick = card.quick
        if card.quick is not None and card.can_change_level:
            self._quick_marks(card.quick)

        self._choices = card.choices
        self.window_size: Segmented | None = None
        self.window_custom: QLineEdit | None = None
        self._window_note: QLabel | None = None
        self._custom_line: QWidget | None = None
        if card.window is not None:
            self._window_row(card.code, card.window)

        self.links = Segmented(
            [
                (LinkChoice.EVERY, _tr("Every word")),
                (LinkChoice.PAST_KNOWN, _tr("Past what you know")),
                (LinkChoice.OFF, _tr("Off")),
            ],
            card.choices.links,
        )
        self.links.setObjectName(f"learning.{card.code}.links")
        self.links.setAccessibleName(_tr("Word links"))
        self.links.changed.connect(
            lambda choice: self._choose(replace(self._choices, links=choice))
        )
        said = _tr(
            "Which words are joined to their translation while word links are on."
        )
        if card.key_words_only:
            said = in_sentence(
                _tr(
                    "No dictionary ranks {language} words yet, so only key words are "
                    "linked."
                ),
                language=name,
            )
        self._row(_tr("Word links"), said, self.links)
        self.links_from: QComboBox | None = None
        if card.offers_links_from:
            self.links_from = Combo()
            self.links_from.setObjectName(f"learning.{card.code}.links_from")
            self.links_from.setAccessibleName(_tr("Start links at"))
            if card.links_from_line:
                self.links_from.addItem(_tr("What you know"), None)
            for n in LINKS_FROM:
                self.links_from.addItem(QLocale().toString(n), n)
            at = self.links_from.findData(
                card.choices.links_from
                if card.links_from_line
                else card.choices.links_from or UNKNOWN_LEVEL_LINKS_FROM
            )
            self.links_from.setCurrentIndex(max(at, 0))
            self.links_from.activated.connect(self._links_from_chosen)
            line = QHBoxLayout()
            line.setSpacing(12)
            line.addWidget(label(_tr("Start links at"), "RowTitle"), 1)
            line.addWidget(self.links_from)
            self.add(line)

        self.switch: QPushButton | None = None
        self.stop: QPushButton | None = None
        buttons = Flow(right=True)  # onto two lines where it's narrow (354)
        if card.can_switch:
            self.switch = _button(
                in_sentence(_tr("Make {language} your main language"), language=name),
                f"learning.{card.code}.switch",
            )
            self.switch.setToolTip(_tr("From the next time Polyglotic starts"))
            buttons.addWidget(self.switch)
        if not card.main:
            self.stop = _button(
                in_sentence(_tr("Stop learning {language}"), language=name),
                f"learning.{card.code}.stop",
            )
            self.stop.setProperty("kind", "ghost")
            self.stop.setToolTip(_tr("Its words are kept - delete them on Account"))
            buttons.addWidget(self.stop)
        if self.switch is not None or self.stop is not None:
            self.add(buttons)

    def _quick_marks(self, quick: QuickMarksLine) -> None:
        """ "Mark the most common words known": the first 1,000 to 10,000,
        or a number typed - each moves the known line, so only those past
        it are offered; Undo right after, and Reset back to before the
        first (polyglotic-hq 342)."""
        code = self.code
        first = Combo()
        first.setObjectName(f"learning.{code}.first_known")
        first.setAccessibleName(_tr("How many of the most common words"))
        for n in quick.choices:
            first.addItem(_tr("The first {count}").format(count=_count(n)), n)
        first.addItem(_tr("Another number…"), 0)
        first.activated.connect(lambda _: self._first_chosen())
        number = QSpinBox()
        number.setObjectName(f"learning.{code}.first_number")
        number.setAccessibleName(_tr("How many of the most common words"))
        number.setRange(1, MOST_KNOWN)
        number.setSingleStep(500)
        number.setGroupSeparatorShown(True)
        number.setValue(min(MOST_KNOWN, max(1000, (quick.known or 0) + 1000)))
        number.valueChanged.connect(lambda _: self._first_chosen())
        mark = _button(_tr("Mark known"), f"learning.{code}.mark_known")
        mark.clicked.connect(self._mark_known)
        controls = QWidget()
        line = QHBoxLayout(controls)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        for widget in (first, number, mark):
            widget.setParent(controls)
            line.addWidget(widget)
        number.hide()  # until "Another number…"
        self.first, self.first_number, self.mark_known = first, number, mark
        self._row(
            _tr("Mark the most common words known"),
            _tr(
                "Every word up to the number you choose counts as known - your "
                "level moves there. Words you marked yourself stay as you set them."
            ),
            controls,
        )
        self._first_chosen()
        if quick.undo is not None:
            self.undo_known = _button(_tr("Undo"), f"learning.{code}.undo_known")
            self.undo_known.setToolTip(
                _tr("Back to: {level}").format(level=_ended(level_text(quick.undo)))
            )
            self.undo_known.clicked.connect(self.undo_known_wanted)
            said = _trn("About %Ln more word(s) count as known now.", quick.marked)
            self.add(self._said_with(said, self.undo_known))
        if quick.reset is not None:
            self.reset_known = _button(_tr("Reset…"), f"learning.{code}.reset_known")
            self.reset_known.setProperty("kind", "ghost")
            self.reset_known.clicked.connect(self.reset_known_wanted)
            said = _tr("Marked in bulk. Reset takes your level back to: {level}.")
            self.add(
                self._said_with(
                    said.format(level=_ended(level_text(quick.reset))), self.reset_known
                )
            )

    def _said_with(self, said: str, button: QPushButton) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(label(said, "Faint", wrap=True), 1)
        line.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        return line

    def first_known(self) -> int:
        """The number chosen to mark known: a quick choice, or the one typed."""
        if self.first is None or self.first_number is None:
            return 0
        chosen = self.first.currentData()
        if chosen == 0:
            return self.first_number.value()
        return chosen if isinstance(chosen, int) else 0

    def _first_chosen(self) -> None:
        if self.first is None or self.first_number is None or self.quick is None:
            return
        self.first_number.setVisible(self.first.currentData() == 0)
        if self.mark_known is not None:
            self.mark_known.setEnabled(self.quick.offered(self.first_known()))

    def _mark_known(self) -> None:
        n = self.first_known()
        if self.quick is not None and self.quick.offered(n):
            self.first_known_wanted.emit(n)

    def _window_row(self, code: str, size: WindowSize) -> None:
        """The learning window's choices (decision 0144): the sizes,
        Unlimited, and Custom - a number typed in the line below it."""
        self.window_size = Segmented(
            [(choice, _window_label(choice)) for choice in WINDOW_CHOICES],
            window_choice(size),
        )
        self.window_size.setObjectName(f"learning.{code}.window")
        self.window_size.setAccessibleName(_tr("Learning window"))
        self.window_size.changed.connect(self._window_chosen)
        self._window_note = label(self._window_said(size), "Faint", wrap=True)
        line = QHBoxLayout()
        line.setSpacing(12)
        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(label(_tr("Learning window"), "RowTitle"))
        words.addWidget(self._window_note)
        line.addLayout(words, 1)
        line.addWidget(self.window_size, 0, Qt.AlignmentFlag.AlignTop)
        self.add(line)

        self._custom_line = QWidget(self)
        custom = QHBoxLayout(self._custom_line)
        custom.setContentsMargins(0, 0, 0, 0)
        custom.setSpacing(8)
        custom.addStretch(1)
        custom.addWidget(label(_tr("Words in the window"), "Faint"))
        self.window_custom = QLineEdit()
        self.window_custom.setObjectName(f"learning.{code}.window_custom")
        self.window_custom.setAccessibleName(_tr("Words in the learning window"))
        bounds = _tr("{least} to {most}").format(
            least=QLocale().toString(MIN_WINDOW), most=QLocale().toString(MAX_WINDOW)
        )
        self.window_custom.setPlaceholderText(bounds)
        self.window_custom.setToolTip(bounds)
        self.window_custom.setFixedWidth(style.px(96))
        self.window_custom.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._show_custom(size)
        self.window_custom.editingFinished.connect(self._custom_typed)
        custom.addWidget(self.window_custom)
        self.add(self._custom_line)
        self._custom_line.setVisible(window_choice(size) is Custom.CUSTOM)

    @staticmethod
    def _window_said(size: WindowSize) -> str:
        if size is UNLIMITED:
            return _tr(
                "Every word past what you know can be pointed out, however rare. "
                "Hover or click any word to look it up."
            )
        return _tr(
            "The next words past what you know are the ones pointed out. "
            "Rarer words are left alone: hover or click one to look it up."
        )

    def _show_custom(self, size: WindowSize) -> None:
        assert self.window_custom is not None
        if size is not UNLIMITED:
            self.window_custom.setText(QLocale().toString(size))

    def _window_chosen(self, chosen: object) -> None:
        """A choice clicked: a size or Unlimited is chosen at once; Custom
        opens the line to type a number in, chosen when it's typed."""
        assert self._custom_line is not None and self.window_custom is not None
        custom = chosen is Custom.CUSTOM
        self._custom_line.setVisible(custom)
        if custom:
            self.window_custom.setFocus()
            self.window_custom.selectAll()
            return
        if chosen is UNLIMITED or isinstance(chosen, int):
            self._window_to(chosen)

    def _custom_typed(self) -> None:
        """The number typed for a custom window: kept within its bounds and
        shown as kept. Nothing that isn't a number changes the window."""
        assert self.window_custom is not None and self.window_size is not None
        if self.window_size.value() is not Custom.CUSTOM:
            return  # left for another choice: that one stands
        typed = typed_window(self.window_custom.text())
        if typed is None:
            now = self._choices.window_size
            self._show_custom(DEFAULT_WINDOW if now is None else now)
            return
        self.window_custom.setText(QLocale().toString(typed))
        self._window_to(typed)

    def _window_to(self, size: WindowSize) -> None:
        assert self._window_note is not None
        self._window_note.setText(self._window_said(size))
        self._choose(replace(self._choices, window_size=size))

    def _row(self, title: str, said: str, control: QWidget) -> None:
        """A titled row: what it is and what it does, its control beside -
        or under them, where there's no room beside (354)."""
        line = Flow(spacing=12)
        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(label(title, "RowTitle", wrap=True))
        words.addWidget(label(said, "Faint", wrap=True))
        line.add_layout(words, 1)
        line.addWidget(control)
        line.setAlignment(control, Qt.AlignmentFlag.AlignTop)
        self.add(line)

    def _links_from_chosen(self, index: int) -> None:
        assert self.links_from is not None
        at = self.links_from.itemData(index)
        self._choose(replace(self._choices, links_from=at))

    def _choose(self, choices: LanguageChoices) -> None:
        if choices != self._choices:
            self._choices = choices
            self.choices_chosen.emit(choices)


def _window_label(choice: WindowSize | Custom) -> str:
    """A learning window choice's words on its card."""
    if choice is UNLIMITED:
        return _tr("Unlimited")
    if choice is Custom.CUSTOM:
        return _tr("Custom")
    assert isinstance(choice, int)
    return QLocale().toString(choice)


class LearningPage(Page):
    """What you're learning and how (polyglotic-hq 262)."""

    change_level_wanted = Signal(str)
    """An open language's "Change your level" (its code): `main` opens the
    picker."""
    pack_wanted = Signal(str, str)
    """A language's pack: `download`, `cancel`, `retry`, `anyway`, `update`
    or `remove` (decision 0122)."""
    languages_wanted = Signal(object)
    """The languages being learned, changed (`LearningLanguages`)."""
    introductions_chosen = Signal(object)
    choices_chosen = Signal(str, object)
    """A language's learning window or word links were chosen: its code
    and its `LanguageChoices` (polyglotic-hq 323)."""
    """Word introductions chosen (`WordIntroductions`)."""
    words_wanted = Signal()
    """"Open Words"."""
    first_known_wanted = Signal(str, int)
    """A language's "Mark known": its code, and the first so many words
    (polyglotic-hq 342)."""
    undo_known_wanted = Signal(str)
    reset_known_wanted = Signal(str)
    shown = Signal()
    """The page came into view: what it shows only while in view (the
    learning load's card) is wanted now."""

    def __init__(self, delete_learning: QAction | None = None) -> None:
        """`delete_learning`: Account's "Delete learning data…" - the same
        command, on both pages."""
        super().__init__(_tr("Learning"))
        self.languages = LearningLanguages()
        self.running: str | None = None
        self._shown: tuple[object, ...] | None = None
        """What `show_learning` was last given: the same again changes nothing."""
        self.pack_line: Callable[[str], PackLine | None] = lambda _: None
        """A basic language's pack as `main` knows it, learned or not: what
        "Learn another language" may say of it (330; None: nothing known)."""
        intro = label(
            _tr(
                "For each language you learn, Polyglotic keeps your words: lookups "
                "use its dictionary, your level estimates which words you know, "
                "and captions point out new ones. Captions and translation work "
                "in every language, whatever you choose here."
            ),
            "PageSubtitle",
            wrap=True,
        )
        self.content.addWidget(intro)

        self.cards_column = QWidget()
        self.cards_column.setObjectName("learning.languages")
        self.cards_layout = QVBoxLayout(self.cards_column)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(16)
        self.content.addWidget(self.cards_column)
        self.cards: list[LanguageCardView] = []
        self.none_yet = Card(
            _tr("Languages you're learning"),
            _tr(
                "None yet. Pick one below for lookups, your level and word "
                "introductions."
            ),
        )
        self.none_yet.hide()
        self.cards_layout.addWidget(self.none_yet)

        self.load = LoadCard()
        """The learning load of the language in use, while the Lab's
        mode is on (polyglotic-hq 324); `main` fills it."""
        self.load.hide()
        self.content.addWidget(self.load)

        self.known_map = KnownMapCard()
        """The map of the language in use: every common word by how well
        it's known (polyglotic-hq 489); `main` fills it."""
        self.known_map.hide()
        self.content.addWidget(self.known_map)

        another = Card(_tr("Learn another language"))
        row = Flow()  # the button under the list where it's narrow (354)
        self.choices = Combo()
        self.choices.setObjectName("learning.another")
        self.choices.setAccessibleName(_tr("Learn another language"))
        # none chosen until the learner picks: the list is by name, and its
        # first language isn't a suggestion (293)
        self.choices.setPlaceholderText(_tr("Choose a language"))
        self.choices.currentIndexChanged.connect(self._chosen)
        row.add_widget(self.choices, 1)
        self.add = _button(_tr("Learn it"), "learning.add")
        # a double-click's second click is let go: after the first, the list
        # moves on to the next language, and the second added that one too
        # (269: Japanese after English)
        self._add_once = OneClick()
        self._add_once.watch(self.add)
        self.add.clicked.connect(lambda: self._add_once(self._add))
        row.addWidget(self.add)
        another.add(row)
        self.chosen_gives = label("", "Faint", wrap=True)
        another.add(self.chosen_gives)
        self.another = another
        self.content.addWidget(another)

        introductions = Card(
            _tr("Word introductions"),
            _tr(
                "Captions point out words that are probably new to you, so you "
                "notice them as you hear them. They're guessed from your level; "
                "a click on any word corrects it."
            ),
        )
        self.introductions = Segmented(
            [
                (WordIntroductions.OFF, _tr("Off")),
                (WordIntroductions.A_FEW, _tr("A few per caption")),
                (WordIntroductions.EVERY, _tr("Every new word")),
            ],
            WordIntroductions.A_FEW,
        )
        self.introductions.setObjectName("learning.introductions")
        self.introductions.setAccessibleName(_tr("Word introductions"))
        self.introductions.changed.connect(self._introductions_chosen)
        introductions.add(_left(self.introductions))
        self.introductions_said = label("", "Dim", wrap=True)
        introductions.add(self.introductions_said)
        self.sample = IntroductionSample()
        introductions.add(self.sample)
        introductions.add(
            label(
                _tr(
                    "Dotted yellow: a word new to you. Dashed green: a word in your "
                    "deck. A saved word takes its category's colour. Only finished "
                    "captions in a language you're learning are marked."
                ),
                "Faint",
                wrap=True,
            )
        )
        introductions.add(
            label(
                _tr(
                    "Where they go: hear a word a few times and it joins Words you "
                    "keep hearing, on Words. Add it to your deck there or from its "
                    "lookup, and it goes into your next Anki export."
                ),
                "Dim",
                wrap=True,
            )
        )
        self.content.addWidget(introductions)

        words = Card(
            _tr("Words and Anki"),
            _tr(
                "Your deck, your saved words and the words you keep hearing are on "
                "Words. Each language exports a deck of its own."
            ),
        )
        self.open_words = _button(_tr("Open Words"), "learning.open_words")
        self.open_words.clicked.connect(self.words_wanted)
        words.add(
            right_row(
                self.open_words,
                page_button(
                    _tr("How to import into Anki"), HELP_ANKI, "learning.anki_help"
                ),
            )
        )
        self.content.addWidget(words)

        # the packs on this PC (decision 0122): each one's version and size
        self.installed = Card(
            pc_or_mac(_tr("Dictionaries on this PC"), _tr("Dictionaries on this Mac")),
            _tr(
                "Downloaded for the languages you learn. Removing one frees its "
                "space; lookups in its language stop until it's downloaded again."
            ),
        )
        self.installed.setAccessibleName(
            pc_or_mac(_tr("Dictionaries on this PC"), _tr("Dictionaries on this Mac"))
        )
        self.installed_rows = QVBoxLayout()
        self.installed_rows.setSpacing(8)
        self.installed.add(self.installed_rows)
        self.no_packs = label(
            _tr("None yet: when you learn a language, its card offers its dictionary."),
            "Dim",
            wrap=True,
        )
        self.installed.add(self.no_packs)
        self._installed_shown: tuple[InstalledPackLine, ...] = ()
        self.content.addWidget(self.installed)

        data = Card(
            _tr("Your learning data"),
            pc_or_mac(
                _tr(
                    "The words you look up, save and mark are kept on this PC, and on "
                    "our server as dictionary words and times. You can delete them, "
                    "in every language you learn - the same as on Account."
                ),
                _tr(
                    "The words you look up, save and mark are kept on this Mac, and on "
                    "our server as dictionary words and times. You can delete them, in "
                    "every language you learn - the same as on Account."
                ),
            ),
        )
        if delete_learning is not None:
            data.add(right_row(_action_button(delete_learning, data)))
        self.content.addWidget(data)
        self.content.addStretch(1)
        self._show_choices()
        self._show_introductions(WordIntroductions.A_FEW)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.shown.emit()

    # -- what it shows -------------------------------------------------------------------

    def show_learning(
        self,
        languages: LearningLanguages,
        cards: Sequence[LanguageCard],
        introductions: WordIntroductions,
        running: str | None = None,
        chinese: bool = True,
    ) -> None:
        """The languages being learned (`cards`, from `views.learning`), the
        word introductions chosen, and the language in use now (`running`;
        the sample caption is in Chinese or English by `chinese`). Asked
        again with the same (any setting changed): nothing is rebuilt."""
        packs = {c.code: c.pack for c in cards if c.pack is not None}
        cards = [replace(c, pack=None) for c in cards]  # a pack's line changes in place
        shown = (languages, tuple(cards), introductions, running, chinese)
        if shown == self._shown:
            for code, line in packs.items():
                self.show_pack(code, line)
            self._show_choices()  # the list may have come: what each offers
            return
        self._shown = shown
        self.languages, self.running = languages, running
        # the keyboard on the same control, and the page where it was: not run
        # down to its middle as each old card hid in turn (480)
        with focus_kept(self.cards_column):
            for old in self.cards:
                old.hide()
                self.cards_layout.removeWidget(old)
                old.deleteLater()
            self.cards = []
            for n, card in enumerate(cards):
                view = LanguageCardView(
                    replace(card, pack=packs.get(card.code)), running
                )
                self.cards_layout.insertWidget(n, view)  # parented before it shows
                if view.pack is not None:
                    view.pack.wanted.connect(self.pack_wanted)
                if view.change_level is not None:
                    view.change_level.clicked.connect(
                        lambda _=False, c=card.code: self.change_level_wanted.emit(c)
                    )
                view.choices_chosen.connect(
                    lambda chosen, c=card.code: self.choices_chosen.emit(c, chosen)
                )
                view.first_known_wanted.connect(
                    lambda n, c=card.code: self.first_known_wanted.emit(c, n)
                )
                view.undo_known_wanted.connect(
                    lambda c=card.code: self.undo_known_wanted.emit(c)
                )
                view.reset_known_wanted.connect(
                    lambda c=card.code: self.reset_known_wanted.emit(c)
                )
                if view.switch is not None:
                    view.switch.clicked.connect(
                        lambda _=False, c=card.code: self._wanted(
                            self.languages.switched_to(c)
                        )
                    )
                if view.stop is not None:
                    view.stop.clicked.connect(
                        lambda _=False, c=card.code: self._wanted(
                            self.languages.stopped(c)
                        )
                    )
                self.cards.append(view)
        self.none_yet.setVisible(not cards)
        self._show_choices()
        self.introductions.set_value(introductions)
        self._show_introductions(introductions, chinese)

    def scroll_to_load(self) -> None:
        """The page scrolled to the learning load's card, at its top - Settings
        > Lab's "Open it on Learning" (polyglotic-hq 342). Once it's laid
        out: the card fills, and shows, as the page comes into view."""
        QTimer.singleShot(0, self._to_load)

    def _to_load(self) -> None:
        inner = self.widget()
        if inner is None or self.load.isHidden():
            return
        if (layout := inner.layout()) is not None:
            layout.activate()
        top = self.load.mapTo(inner, QPoint(0, 0)).y()
        self.verticalScrollBar().setValue(max(0, top - style.px(16)))

    def card(self, code: str) -> LanguageCardView | None:
        return next((c for c in self.cards if c.code == code), None)

    def show_pack(self, code: str, line: PackLine) -> None:
        """A language's pack as it is now - its card's row only, nothing
        rebuilt (a download says how far along a few times a second)."""
        card = self.card(code)
        if card is not None and card.pack is not None:
            card.pack.show_line(line)

    def show_installed(self, packs: Sequence[InstalledPackLine]) -> None:
        """The packs on this PC, each with its version, size and Remove."""
        if tuple(packs) == self._installed_shown:
            return
        self._installed_shown = tuple(packs)
        # a Remove's keyboard not handed on to Delete learning data (480)
        with focus_kept(self.installed):
            while self.installed_rows.count():
                item = self.installed_rows.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
            for pack in packs:
                row = QWidget(self.installed)
                line = QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(12)
                said = label(
                    in_sentence(
                        _tr("{language}: version {version}, {size}"),
                        language=learned_name(pack.code),
                        version=pack.version,
                        size=size_text(pack.size),
                    ),
                    wrap=True,
                )
                said.setParent(row)
                line.addWidget(said, 1)
                remove = _button(_tr("Remove"), f"learning.{pack.code}.pack_remove")
                remove.setParent(row)
                remove.setProperty("kind", "ghost")
                remove.clicked.connect(
                    lambda _=False, c=pack.code: self.pack_wanted.emit(c, "remove")
                )
                line.addWidget(remove)
                self.installed_rows.addWidget(row)
        self.no_packs.setVisible(not packs)

    def _known(self, code: str) -> PackKnown | None:
        """Whether a basic language's pack can be had, as `main` knows it."""
        if tier_of(code) is not Tier.BASIC:
            return None
        return pack_known(self.pack_line(code))

    def _show_choices(self) -> None:
        """Learn another language: those not learned, by name, each named
        with its tier - "No dictionary yet" for a basic one none of whose
        packs can be had (330). Built again only when that changes: an open
        list isn't closed under the learner."""
        items = []
        for code in offered(self.languages, learnable()):
            tier = tier_of(code)
            if self._known(code) is PackKnown.NONE_YET:
                tier = Tier.NONE
            items.append(
                (
                    in_sentence(
                        _tr("{language} - {tier}"),
                        language=learned_name(code),
                        tier=tier_name(tier),
                    ),
                    code,
                )
            )
        there = [
            (self.choices.itemText(n), self.choices.itemData(n))
            for n in range(self.choices.count())
        ]
        if items != there:
            blocked = self.choices.blockSignals(True)
            wanted = self.choices.currentData()
            self.choices.clear()
            for text, code in items:
                self.choices.addItem(text, code)
            self.choices.setCurrentIndex(self.choices.findData(wanted))  # -1: none
            self.choices.blockSignals(blocked)
        self.another.setVisible(self.choices.count() > 0)
        self._chosen()

    def _chosen(self, _index: int = 0) -> None:
        code = self.choices.currentData()
        self.chosen_gives.setText(
            what_it_gives(code, tier_of(code), known=self._known(code), on_card=False)
            if isinstance(code, str)
            else ""
        )
        self.add.setEnabled(isinstance(code, str))  # nothing to learn yet

    def _show_introductions(
        self, choice: WordIntroductions, chinese: bool | None = None
    ) -> None:
        self.introductions_said.setText(introductions_line(choice))
        self.sample.show_choice(
            choice, self.sample.chinese if chinese is None else chinese
        )

    # -- what it asks --------------------------------------------------------------------

    def _add(self) -> None:
        code = self.choices.currentData()
        if isinstance(code, str):
            self._wanted(self.languages.added(code))

    def _wanted(self, languages: LearningLanguages) -> None:
        if languages != self.languages:
            self.languages_wanted.emit(languages)

    def _introductions_chosen(self, choice: object) -> None:
        if isinstance(choice, WordIntroductions):
            self._show_introductions(choice)
            self.introductions_chosen.emit(choice)


def _ended(level: str) -> str:
    """A level's line inside a sentence of ours, which ends it itself:
    "Not set yet - ... level." loses its full stop (342)."""
    return level.rstrip(".。")


def _count(n: int) -> str:
    return QLocale().toString(n)


def _button(text: str, name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _action_button(action: QAction, within: QWidget) -> QPushButton:
    """A button showing `action` (Account's): its text, and whether it
    shows and works - as Account's own button follows it.

    A child of `within` from the first: shown with no parent it would open
    as a window of its own until its page took it - 120 ms of the start
    with real windows (polyglotic-hq 314)."""
    button = _button(action.text(), f"learning.{action.objectName()}")
    button.setParent(within)

    def follow() -> None:
        button.setText(action.text())
        button.setVisible(action.isVisible())
        button.setEnabled(action.isEnabled())

    button.clicked.connect(action.trigger)
    action.changed.connect(follow)
    follow()
    return button


def _left(widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch(1)
    return row
