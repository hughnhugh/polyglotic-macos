"""Words, in the new main window - today's Vocabulary, renamed, everything
kept (polyglotic-hq project 109's structure, section 7; 049).

Top to bottom, in a column up to 960 px wide (`main_window.WORDS_COLUMN`):
- **Your level** - and Change, which asks `main` for the level picker;
- (under the title) the summary line: words met, coverage, listening;
- **What you've heard** (`heard_card`) - words met, coverage of the last
  7 days, listening time, and the bands (`word_bands`);
- **Words you keep hearing** - unfamiliar words, most heard first, each a
  click from the deck (or known): a few, then Show more in steps
  (polyglotic-hq 250);
- **Your words** - every word met, by status, searchable; a status
  corrected by hand. A few rows (`YOUR_WORDS_ROWS`), then Show all - the
  search finds the rest (polyglotic-hq 250);
- **Saved words** - the categories (rename, recolour, add, delete), the
  words in them (move, remove, "Heard in"; a few rows, `SAVED_WORDS_ROWS`,
  then Show all, polyglotic-hq 258), and **Export for Anki** (a
  CSV, or a deck file; only the words not exported yet, if ticked),
  written on a thread of its own with the buttons busy (polyglotic-hq
  273) - and under it what was written (how many words, and the file's
  full path), or why it couldn't be (`export_said`: the file open in
  another program, the folder read-only; polyglotic-hq project 145); and
  How to import into Anki, the site's help, in the browser (polyglotic-hq
  250).
- **Saved sentences** (polyglotic-hq 459, `saved_sentences`): what was
  selected in captions and saved, searched in either language, filtered
  by category or saved word; moved or removed.

Every full language learned is open at once, each its own section with
its own level, words, categories and Anki export (DECISIONS #110,
decision 0095). When the main language was changed this run to a full
dictionary not open yet, the page says whose words it shows until the
next start, when it opens (`show_in_use`; polyglotic-hq 299: a learner who
chose English saw Chinese words, unnamed, and "Words don't work for
English").

Clicking a word pins its lookup - the card every caption window shares
(`lookup_card`). The word lists are tables (`word_table`): their rows are
painted, and a row's text is looked up only when it shows, so a long list
costs no more to open than a short one (109's 10.5; the click and page
budgets). They refresh when Learning changes - while the page shows, at
once (words heard while listening: at most once a second), else when it
next shows. `main` hands over the learning tools and the card, and opens
today's level picker when asked.
"""

import contextlib
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QDir,
    QEvent,
    QLocale,
    QRect,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QPalette, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.exposures import ExposureCount
from polyglotic_desktop.core.learning.languages import Tier, tier_of
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import Category, CategoryId
from polyglotic_desktop.core.learning.vocabulary import (
    AnkiFormat,
    AnkiWords,
    words_and_sentences,
)
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.core.shared.papers import HELP_ANKI
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import to_rect, work_areas
from polyglotic_desktop.ui_next.colour_controls import pick_colour
from polyglotic_desktop.ui_next.controls import (
    Card,
    Combo,
    Flow,
    WrapCheckBox,
    focus_kept,
    label,
    page_button,
    swatch,
)
from polyglotic_desktop.ui_next.heard_card import HeardCard
from polyglotic_desktop.ui_next.home import Page
from polyglotic_desktop.ui_next.languages import in_sentence, learned_name
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.main_window import WORDS_COLUMN
from polyglotic_desktop.ui_next.save_folder import SaveFolder
from polyglotic_desktop.ui_next.saved_sentences import SavedSentences
from polyglotic_desktop.ui_next.views.lookup import WordAt
from polyglotic_desktop.ui_next.views.placement import area_for
from polyglotic_desktop.ui_next.views.words import (
    KEEP_HEARING_FIRST,
    KEEP_HEARING_STEP,
    MAX_ROWS,
    SAVED_WORDS_ROWS,
    YOUR_WORDS_ROWS,
    LanguageGroup,
    WordRows,
    WordsLearner,
    WordText,
    language_groups,
    level_line,
    word_text,
)
from polyglotic_desktop.ui_next.word_table import (
    Column,
    Item,
    SelectionBar,
    WordTable,
    status_name,
)

log = logging.getLogger(__name__)

KNOWN, DECK, NEW, IGNORE, MOVE, REMOVE = (
    "known", "deck", "new", "ignore", "move", "remove"
)  # fmt: skip
"""What can be done to several words picked at once (342): the keys of the
lists' `SelectionBar`s."""
PICKED_STATUSES = {
    KNOWN: WordStatus.KNOWN,
    DECK: WordStatus.LEARNING,
    NEW: WordStatus.NEW,
    IGNORE: WordStatus.IGNORED,
}

HEARD_EVERY_MS = 1000
"""While captions come in, Words shows the counts again at most this often."""


def _tr(text: str) -> str:
    return QApplication.translate("Words", text)


# the level schemes' names (core.lexicon.entries.SCHEMES), translated as
# the page shows them (polyglotic-hq 156)
SCHEME_NAMES = (
    QT_TRANSLATE_NOOP("Words", "HSK 3.0 (2025 exam syllabus)"),
    QT_TRANSLATE_NOOP("Words", "HSK 3.0 (2021 standard)"),
    QT_TRANSLATE_NOOP("Words", "The most common English words"),
)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Words", text, None, n)


def export_said(
    count: int | None, name: str, only_new: bool, sentences: int = 0
) -> str:
    """What Export for Anki says once it's done: how many words (`count`)
    and saved sentences went into `name`, or (`count` None) that the file
    couldn't be written."""
    if count is None:
        return _tr(
            "Couldn't write {name}. It may be open in another program, or the "
            "folder may be read-only - close it or pick another folder, and "
            "try again."
        ).format(name=name)
    if count == 0 and sentences:
        return _trn("%Ln saved sentence(s) written to {name}.", sentences).format(
            name=name
        )
    if count == 0:
        if only_new:
            return _tr("No new words since the last export - {name} is empty.").format(
                name=name
            )
        return _tr(
            "No words to export yet - {name} is empty. Save a word or add it to "
            "your deck first."
        ).format(name=name)
    said = _trn("%Ln word(s) written to {name}.", count).format(name=name)
    if sentences:
        #: after "12 words written to polyglotic-words.apkg."
        said += " " + _trn("And %Ln saved sentence(s).", sentences)
    return said


def heard_times(count: int) -> str:
    """How often a word was heard, in words: "heard once", "heard 12 times"
    (English's forms are in its translation file)."""
    return _trn("heard %Ln time(s)", count)


def heard_line(heard: ExposureCount) -> str:
    """A saved word's row, in words: how often it was heard, how often
    since it went in the deck, how often the learner said it - each only
    when it happened ("heard 12 times · 3 since it went in your deck · you
    said it once"; "not heard yet"). It said "heard 0 · by you 0 · in deck
    0" (polyglotic-hq 133)."""
    parts = [heard_times(heard.heard) if heard.heard else _tr("not heard yet")]
    if heard.heard_in_deck:
        parts.append(
            _tr("{n} since it went in your deck").format(n=heard.heard_in_deck)
        )
    if heard.heard_by_you:
        parts.append(_trn("you said it %Ln time(s)", heard.heard_by_you))
    return " · ".join(parts)


def words_count(count: int) -> str:
    """A category's words: "1 word", "3 words"."""
    return _trn("%Ln word(s)", count)


def words_level_text(words: int) -> str:
    """A level said in words (polyglotic-hq 323), for Words and Learning."""
    if words <= 0:
        return _tr("Just starting - no words known yet")
    return _tr("About {count} of the most common words").format(
        count=QLocale().toString(words)
    )


class Field(QLineEdit):
    """A text field whose hint (its placeholder) is in the theme's dim
    colour, which reads on a field: the window's stylesheet would give it
    a fainter one. Set again after every restyle (a theme change)."""

    def __init__(self, name: str, hint: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setPlaceholderText(hint)
        self.setAccessibleName(hint)

    def _hint_colour(self) -> None:
        palette = self.palette()
        palette.setColor(
            QPalette.ColorRole.PlaceholderText, QColor(style.current()["TEXT_DIM"])
        )
        self.setPalette(palette)

    def showEvent(self, event: QShowEvent) -> None:
        self._hint_colour()
        super().showEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._hint_colour()


class CategoryRow(QWidget):
    """A category: its colour (click to change), its name (edit to rename),
    how many words, and Delete (while there's another)."""

    def __init__(self, category: Category, count: int, deletable: bool) -> None:
        super().__init__()
        self.category = category
        row = Flow(self, spacing=10)  # Delete under the name where it's narrow
        self.colour = QToolButton()
        self.colour.setObjectName(f"category.color.{category.id}")
        self.colour.setIcon(swatch(category.color, 18))
        self.colour.setToolTip(_tr("Change colour"))
        self.colour.setAccessibleName(
            _tr("Colour for {name}").format(name=category.name)
        )
        self.colour.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.colour)
        self.name = QLineEdit(category.name)
        self.name.setObjectName(f"category.name.{category.id}")
        self.name.setAccessibleName(_tr("Category name"))
        self.name.setMinimumWidth(style.px(140))
        self.name.setMaximumWidth(style.px(260))
        row.add_widget(self.name, 1)
        row.addWidget(label(words_count(count), "Dim"))
        row.add_stretch(1)
        self.delete = QPushButton(_tr("Delete"))
        self.delete.setObjectName(f"category.delete.{category.id}")
        self.delete.setProperty("kind", "ghost")
        self.delete.setToolTip(_tr("Delete the category and the words saved in it"))
        self.delete.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.delete)
        self.delete.setHidden(not deletable)  # once it has a parent: never a window


class LanguageWords(QWidget):
    """One language's words: the level, what you've heard, words you keep
    hearing, your words, saved words and the export - a column of cards,
    in its section of the page (`WordsPage`)."""

    change_level_wanted = Signal()
    """Change: `main` opens the level picker (today's dialog)."""
    counted = Signal(int)
    """How many words met, at each refresh: the section's heading."""
    export_done = Signal()
    """An export's file is written - or couldn't be - and said."""
    _written = Signal(object)  # an `_Exported`, from the export's own thread

    def __init__(
        self,
        learner: WordsLearner,
        card: LookupCard | None,
        save_folder: SaveFolder | None = None,
    ) -> None:
        """`save_folder`: where the exports' save dialogs open (none:
        Documents, the last export's folder remembered while it's open)."""
        super().__init__()
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)  # as the page's own column (`home.Page`)
        self.learner = learner
        self.card = card
        self.save_folder = save_folder or SaveFolder()
        self.rows = WordRows(self._text)
        chinese = learner.is_chinese
        self._dirty = True
        self._categories_dirty = True
        self.count_dirty = True
        """Its words met not counted since Learning last changed, while it
        was closed: its heading is counted when the page shows (`count`)."""
        self._later = QTimer(self, singleShot=True)
        self._later.timeout.connect(self.refresh)

        level = Card(_tr("Your level"))
        line = QHBoxLayout()
        self.level = label("", wrap=True)
        self.level.setObjectName("words.level")
        line.addWidget(self.level, 1)
        self.change_level = _button(_tr("Change your level"), "words.change_level")
        self.change_level.clicked.connect(self.change_level_wanted)
        line.addWidget(self.change_level)
        level.add(line)
        self.content.addWidget(level)
        # opened as the app starts, while what it shows is still being read
        # (`WordsLearner.reading_ahead`): said, in place of the rest
        self.reading = label(_tr("Reading your words…"), "Dim", wrap=True)
        self.reading.setObjectName("words.reading")
        self.reading.hide()
        self.content.addWidget(self.reading)

        self.heard = HeardCard()
        self.content.addWidget(self.heard)
        # the summary line, under the page's title (155's mock 6) - or the
        # language's heading, with several
        self.summary = label("", "PageSubtitle", wrap=True)
        self.summary.setObjectName("words.summary")
        self.content.insertWidget(0, self.summary)

        hearing = Card(
            _tr("Words you keep hearing"),
            _tr(
                "Words new to you, most heard first - add the useful ones to your deck."
            ),
        )
        self.hearing = WordTable(
            "words.keep_hearing",
            (Column.WORD, Column.MEANING, Column.ADD, Column.KNOWN),
            self.rows,
            chinese,
        )
        self.hearing.setAccessibleName(_tr("Words you keep hearing"))
        self.hearing_bar = SelectionBar("words.keep_hearing_picked")
        self.hearing_bar.add(KNOWN, _tr("I know these"))
        self.hearing_bar.add(DECK, _tr("Add to deck"))
        hearing.add(self.hearing_bar)
        self.hearing_empty = label(
            _tr(
                "Nothing yet - words new to you show here once you've heard them "
                "a few times."
            ),
            "Dim",
            wrap=True,
        )
        hearing.add(self.hearing)
        # a few, then Show more in steps (`KEEP_HEARING_FIRST`, `_STEP`)
        self.hearing_rows = KEEP_HEARING_FIRST
        self.hearing_more = _button(_tr("Show more"), "words.keep_hearing_more")
        self.hearing_more.clicked.connect(self._more_hearing)
        self.hearing_fewer = _button(_tr("Show fewer"), "words.keep_hearing_fewer")
        self.hearing_fewer.clicked.connect(self._fewer_hearing)
        line = QHBoxLayout()
        line.setSpacing(8)
        for button in (self.hearing_more, self.hearing_fewer):
            button.setProperty("kind", "ghost")
            line.addWidget(button)
        line.addStretch(1)
        hearing.add(line)
        hearing.add(self.hearing_empty)
        self.content.addWidget(hearing)

        words = Card(
            _tr("Your words"), _tr("Every word you've met. Correct any status by hand.")
        )
        filters = Flow()
        self.status = Combo()
        self.status.setObjectName("words.filter")
        self.status.setAccessibleName(_tr("Show words with this status"))
        self.status.addItem(_tr("All statuses"), None)
        for status in WordStatus:
            self.status.addItem(status_name(status), status.value)
        self.status.currentIndexChanged.connect(lambda _: self._refresh_words())
        self.search = Field("words.search", _tr("Search - word, reading or meaning"))
        self.search.setAccessibleName(_tr("Search your words"))
        self.search.setClearButtonEnabled(True)
        clear = self.search.findChild(QToolButton)
        if clear is not None:  # the field's own x: named, and reached by Tab
            clear.setAccessibleName(_tr("Clear the search"))
            clear.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._searching = QTimer(self, singleShot=True, interval=150)
        self._searching.timeout.connect(self._refresh_words)
        self.search.textChanged.connect(lambda _: self._searching.start())
        filters.addWidget(self.status)
        filters.add_widget(self.search, 1)
        words.add(filters)
        self.words = WordTable(
            "words.your_words",
            (Column.WORD, Column.MEANING, Column.STATUS),
            self.rows,
            chinese,
        )
        self.words.setAccessibleName(_tr("Your words"))
        self.words_bar = SelectionBar("words.your_words_picked")
        self.words_bar.add(KNOWN, _tr("I know these"))
        self.words_bar.add(DECK, _tr("Add to deck"))
        self.words_bar.add(NEW, _tr("New again"), "ghost")
        self.words_bar.add(IGNORE, _tr("Ignore"), "ghost")
        words.add(self.words_bar)
        words.add(self.words)
        # a few rows, then Show all - or the search (`YOUR_WORDS_ROWS`)
        self.all_words = False
        self.words_all = _button("", "words.your_words_all")
        self.words_all.setProperty("kind", "ghost")
        self.words_all.clicked.connect(self._show_all_words)
        line = QHBoxLayout()
        line.addWidget(self.words_all)
        line.addStretch(1)
        words.add(line)
        self.words_note = label("", "Dim", wrap=True)
        words.add(self.words_note)
        self.content.addWidget(words)

        saved = Card(
            _tr("Saved words"),
            _tr(
                "Each category has its own colour, wherever its words are heard "
                "again. Yellow and white are best avoided: on the captions they "
                "mean a translation and what was said."
            ),
        )
        self.categories = QWidget()
        self.category_rows = _column(self.categories)
        saved.add(self.categories)
        add = Flow()
        self.new_category = Field("words.new_category", _tr("New category"))
        self.new_category.setMinimumWidth(style.px(140))
        self.new_category.setMaximumWidth(style.px(260))
        self.new_category.returnPressed.connect(self._add_category)
        add.add_widget(self.new_category, 1)
        self.add_category = _button(_tr("Add"), "words.add_category")
        self.add_category.clicked.connect(self._add_category)
        add.addWidget(self.add_category)
        add.add_stretch(1)
        saved.add(add)
        self.saved = WordTable(
            "words.saved",
            (Column.WORD, Column.MEANING, Column.CATEGORY, Column.REMOVE),
            self.rows,
            chinese,
        )
        self.saved.setAccessibleName(_tr("Saved words"))
        self.saved_bar = SelectionBar("words.saved_picked")
        self.saved_bar.add(MOVE, _tr("Move to…"))
        self.saved_bar.add(REMOVE, _tr("Remove"), "ghost")
        saved.add(self.saved_bar)
        saved.add(self.saved)
        # a few rows, then Show all (`SAVED_WORDS_ROWS`), as Your words
        self.all_saved = False
        self.saved_all = _button("", "words.saved_all")
        self.saved_all.setProperty("kind", "ghost")
        self.saved_all.clicked.connect(self._show_all_saved)
        line = QHBoxLayout()
        line.addWidget(self.saved_all)
        line.addStretch(1)
        saved.add(line)
        self.saved_empty = label(
            _tr("None yet - click a word in a caption and pick a category to save it."),
            "Dim",
            wrap=True,
        )
        saved.add(self.saved_empty)
        self.content.addWidget(saved)

        self.sentences = SavedSentences(lambda: self.learner.vocabulary)
        """Saved sentences, searched (polyglotic-hq 459)."""
        self._sentences_dirty = True
        self.content.addWidget(self.sentences)

        export = Card(
            _tr("Export for Anki"),
            _tr(
                "Saved words and words in your deck, with their sentences: a CSV "
                "file Anki can import, or a deck file - double-click it and Anki "
                "adds them with Polyglotic's card style, no set-up."
            ),
        )
        choice = Flow()  # the buttons under the choice where it's narrow (354)
        self.only_new = WrapCheckBox(_tr("Only words not exported yet"))
        self.only_new.setObjectName("words.export_only_new")
        choice.addWidget(self.only_new)
        choice.add_stretch(1)
        self.export_csv = _button(_tr("CSV file"), "words.export_csv")
        self.export_csv.clicked.connect(self._export_csv)
        choice.addWidget(self.export_csv)
        self.export_deck = _button(_tr("Anki deck file (.apkg)"), "words.export_deck")
        self.export_deck.setEnabled(learner.deck_writer is not None)
        self.export_deck.clicked.connect(self._export_deck)
        choice.addWidget(self.export_deck)
        export.add(choice)
        # how to import it, on the site's help (polyglotic-hq 250, F25)
        self.anki_help = page_button(
            _tr("How to import into Anki"), HELP_ANKI, "words.anki_help"
        )
        self.anki_help.setProperty("kind", "ghost")
        line = QHBoxLayout()
        line.addWidget(self.anki_help)
        line.addStretch(1)
        export.add(line)
        self.export_result = label("", "Dim", wrap=True)
        self.export_result.setObjectName("words.export_result")
        self.export_result.hide()
        export.add(self.export_result)
        self.exporting: threading.Thread | None = None
        """The export writing its file, on a thread of its own (273)."""
        self._written.connect(self._export_written)  # queued: from that thread
        self.content.addWidget(export)
        self._read_parts: tuple[QWidget, ...] = (
            self.heard, self.summary, hearing, words, saved, self.sentences, export
        )  # fmt: skip

        for table in (self.hearing, self.words, self.saved):
            table.acted.connect(self._acted)
        # several words picked at once (342): the bar above each list
        self.ask_remove: Callable[[int], bool] = self._ask_remove
        """Whether to remove `n` saved words picked together - asked first."""
        for table, bar in (
            (self.hearing, self.hearing_bar),
            (self.words, self.words_bar),
            (self.saved, self.saved_bar),
        ):
            table.picked_changed.connect(bar.show_count)
            bar.chosen.connect(lambda key, t=table, b=bar: self._for_picked(t, b, key))

    # -- refreshing --------------------------------------------------------------------

    def learning_changed(self, what: str = "") -> None:
        """Learning changed (`LearningTools.changed`): shown again while the
        page shows - at once (once for a run of changes), or for words heard
        while listening, at most once every `HEARD_EVERY_MS` - else when it
        next shows. Our curriculum's set isn't shown here (477)."""
        if what == "curriculum":
            return
        self._dirty = True
        self.count_dirty = True
        if what in ("", "saved_words"):
            self._categories_dirty = True
        if what in ("", "saved_words", "sentences"):
            self._sentences_dirty = True
        if not self.isVisible():
            return
        if what == "exposures":  # a finished caption's words
            if not self._later.isActive():
                self._later.start(HEARD_EVERY_MS)
        else:
            self._later.start(0)

    def showEvent(self, event: QShowEvent) -> None:
        if self._dirty:
            self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        with spans.span("words.refresh"):
            self._refresh_level()
            reading = self.learner.reading_ahead
            self.reading.setVisible(reading)
            for part in self._read_parts:
                part.setVisible(not reading)
            if reading:  # shown when it's back (`learning_changed`)
                return
            self._dirty = False
            self.heard.refresh(self.learner)
            self.count_dirty = False
            self.counted.emit(self.heard.words_met)
            self.summary.setText(self.heard.summary)
            self.summary.setHidden(not self.heard.summary)
            self._refresh_hearing()
            self._refresh_words()
            if self._categories_dirty:
                self._refresh_categories()
            self._refresh_saved()
            if self._sentences_dirty:  # read the first time it shows (459)
                self._sentences_dirty = False
                self.sentences.refresh()

    def count(self) -> None:
        """Its words met counted for its heading alone, while it's closed
        (polyglotic-hq 306: a second language's section said "0 words met"
        until opened) - as the heard card counts them, once what Words reads
        is read ahead (`main` starts that before the page is built); until
        then it waits (`count_dirty` stays)."""
        if self.learner.reading_ahead:
            return
        self.count_dirty = False
        self.counted.emit(len(self.learner.vocabulary.met_words()))

    def _text(self, entry_id: EntryId) -> WordText | None:
        vocabulary = self.learner.vocabulary
        return word_text(
            self.learner.describe(entry_id), vocabulary.saved_word(entry_id)
        )

    def _refresh_level(self) -> None:
        line = level_line(self.learner.vocabulary.line)
        if not line.picked:
            text = _tr("Not set yet - words count as known up to a middle level.")
        elif line.words is not None:
            text = words_level_text(line.words)
        elif not line.level:
            text = _tr("{scheme}: just starting").format(scheme=_tr(line.scheme))
        else:
            text = _tr("{scheme}: {level}").format(
                scheme=_tr(line.scheme), level=line.level
            )
        self.level.setText(text)

    def _refresh_hearing(self) -> None:
        shown = self.hearing_rows
        # one more than listed: whether there's more to show
        found = self.learner.vocabulary.keep_hearing(shown + 1)
        items = [
            Item(entry_id, heard_times(count.heard))
            for entry_id, count in found[:shown]
            if self.rows.text(entry_id) is not None
        ]
        self.hearing.set_items(items)
        self.hearing_empty.setVisible(not items)
        self.hearing_more.setVisible(len(found) > shown and shown < MAX_ROWS)
        self.hearing_fewer.setVisible(shown > KEEP_HEARING_FIRST and bool(items))

    def _more_hearing(self) -> None:
        self.hearing_rows = min(MAX_ROWS, self.hearing_rows + KEEP_HEARING_STEP)
        self._refresh_hearing()

    def _fewer_hearing(self) -> None:
        tall = self.hearing.height()
        self.hearing_rows = KEEP_HEARING_FIRST
        self._refresh_hearing()
        self._list_shrank(self.hearing, tall)

    def _refresh_words(self) -> None:
        wanted = self.status.currentData()
        vocabulary = self.learner.vocabulary
        met = vocabulary.met_entries(WordStatus(wanted) if wanted else None)
        query = self.search.text()
        found = self.rows.found(met, query)
        listed = MAX_ROWS if self.all_words else YOUR_WORDS_ROWS
        items = []
        for entry_id in found[:listed]:  # a row only for those listed
            row = vocabulary.vocabulary_row(entry_id)
            items.append(
                Item(
                    entry_id,
                    heard_line(row.exposures),
                    row.status.status,
                    row.status.is_learners_own,
                    sentence=row.saved.source_sentence if row.saved else "",
                )
            )
        self.words.set_items(items)
        self.words_all.setText(
            _tr("Show fewer")
            if self.all_words
            else _tr("Show all ({count})").format(count=len(found))
        )
        self.words_all.setVisible(len(found) > YOUR_WORDS_ROWS)
        if len(found) > listed > YOUR_WORDS_ROWS:
            note = _tr("{count} more - filter or search to find them.").format(
                count=len(found) - MAX_ROWS
            )
        elif not items:
            note = (
                _tr("No matches.")
                if query.strip() or wanted
                else _tr("None yet - words appear here as you hear them.")
            )
        else:
            note = ""
        self.words_note.setText(note)
        self.words_note.setVisible(bool(note))

    def _show_all_words(self) -> None:
        """Show all, or Show fewer: the list grows, or shrinks with the
        button staying where it was on the screen - not the page's end,
        where a list a few hundred rows shorter would leave the view."""
        tall = self.words.height()
        self.all_words = not self.all_words
        self._refresh_words()
        if not self.all_words:
            self._list_shrank(self.words, tall)

    def _list_shrank(self, table: WordTable, tall: int) -> None:
        """`table` was `tall` and is shorter now (Show fewer): the view
        moves up by what it lost, so the button right under it stays where
        it was on the screen. Known now; the page itself takes its new
        height a layout pass or two later."""
        page = self.parentWidget()
        while page is not None and not isinstance(page, QScrollArea):
            page = page.parentWidget()
        if page is not None:
            bar = page.verticalScrollBar()
            bar.setValue(bar.value() - (tall - table.height()))

    def _refresh_categories(self) -> None:
        self._categories_dirty = False
        # a category renamed or recoloured keeps the keyboard on its row made
        # again, and the page its place (polyglotic-hq 480)
        with focus_kept(self.categories):
            vocabulary = self.learner.vocabulary
            while self.category_rows.count():
                taken = self.category_rows.takeAt(0)
                widget = taken.widget() if taken is not None else None
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
            counts: dict[CategoryId, int] = {}
            for word in vocabulary.saved_words:
                counts[word.category_id] = counts.get(word.category_id, 0) + 1
            deletable = len(vocabulary.categories) > 1
            before: QWidget = self.words_all
            for category in vocabulary.categories:
                row = CategoryRow(category, counts.get(category.id, 0), deletable)
                row.colour.clicked.connect(
                    lambda _=False, c=category: self._recolour(c)
                )
                row.name.editingFinished.connect(
                    lambda c=category, field=row.name: self._rename(c, field.text())
                )
                row.delete.clicked.connect(
                    lambda _=False, c=category: vocabulary.remove_category(c.id)
                )
                self.category_rows.addWidget(row)
                # made after the page: Tab reaches the rows where they are,
                # between Your words and New category, not after the sidebar
                for control in (row.colour, row.name, row.delete):
                    QWidget.setTabOrder(before, control)
                    before = control

    def _refresh_saved(self) -> None:
        vocabulary = self.learner.vocabulary
        saved = vocabulary.saved_words
        listed = MAX_ROWS if self.all_saved else SAVED_WORDS_ROWS
        items = []
        for word in saved[:listed]:  # a row only for those listed
            sentence = word.source_sentence
            details = (
                _tr("Heard in: {sentence}").format(sentence=sentence)
                if sentence and sentence != word.headword
                else ""
            )
            items.append(
                Item(
                    word.entry_id,
                    details,
                    category=vocabulary.category(word.category_id),
                    sentence=sentence,
                )
            )
        self.saved.set_items(items)
        self.saved_empty.setVisible(not items)
        self.saved_all.setText(
            _tr("Show fewer")
            if self.all_saved
            else _tr("Show all ({count})").format(count=len(saved))
        )
        self.saved_all.setVisible(len(saved) > SAVED_WORDS_ROWS)

    def _show_all_saved(self) -> None:
        """Show all, or Show fewer, as Your words' (`_show_all_words`)."""
        tall = self.saved.height()
        self.all_saved = not self.all_saved
        self._refresh_saved()
        if not self.all_saved:
            self._list_shrank(self.saved, tall)

    # -- what the learner does -----------------------------------------------------------

    def _acted(self, column: str, entry: str, cell: QRect) -> None:
        entry_id = EntryId(entry)
        vocabulary = self.learner.vocabulary
        if column == Column.WORD:
            self.look_up(entry_id, cell)
        elif column == Column.ADD:
            vocabulary.set_status(entry_id, WordStatus.LEARNING)
        elif column == Column.KNOWN:
            vocabulary.set_status(entry_id, WordStatus.KNOWN)
        elif column == Column.STATUS:
            self.menu = self._status_menu(entry_id)
            self.menu.popup(cell.bottomLeft())
        elif column == Column.CATEGORY:
            self.menu = self._category_menu(entry_id)
            self.menu.popup(cell.bottomLeft())
        elif column == Column.REMOVE:
            vocabulary.unsave(entry_id)

    def _for_picked(self, table: WordTable, bar: SelectionBar, key: str) -> None:
        """An action for every word picked in `table` (342): a status for
        them all, moved to a category, or removed from the saved words -
        or "Clear", which lets them go."""
        entries = table.picked_entries()
        vocabulary = self.learner.vocabulary
        if key in PICKED_STATUSES and entries:
            vocabulary.set_statuses(entries, PICKED_STATUSES[key])
        elif key == MOVE and entries:
            button = bar.buttons[MOVE]
            self.menu = self._category_menu_for(entries)
            self.menu.popup(button.mapToGlobal(button.rect().bottomLeft()))
            return  # picked until a category is chosen
        elif key == REMOVE and entries:
            if not self.ask_remove(len(entries)):
                return
            for entry_id in entries:
                vocabulary.unsave(entry_id)
        table.let_go()

    def _ask_remove(self, count: int) -> bool:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            _tr("Remove saved words"),
            _trn(
                "Remove %Ln saved word(s)? The lines they were saved from go with them.",
                count,
            ),
            parent=self,
        )
        yes = box.addButton(_tr("Remove"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        answer = box.clickedButton() is yes
        box.deleteLater()
        return answer

    def _category_menu_for(self, entries: Sequence[EntryId]) -> QMenu:
        """Move to…: the categories; one chosen takes every word picked."""
        menu = QMenu(self)
        menu.setObjectName("words.picked_category_menu")
        for category in self.learner.vocabulary.categories:
            action = menu.addAction(swatch(category.color), category.name)
            action.setObjectName(f"words.picked_category.{category.id}")
            action.triggered.connect(
                lambda _=False, c=category.id: self._move_picked(entries, c)
            )
        return menu

    def _move_picked(self, entries: Sequence[EntryId], category_id: CategoryId) -> None:
        for entry_id in entries:
            self._move(entry_id, category_id)
        self.saved.let_go()

    def look_up(self, entry_id: EntryId, cell: QRect) -> None:
        """The word's lookup, pinned beside its cell (the caption windows'
        card), in this section's language: its own dictionary and learning
        data, with several open (306)."""
        text = self.rows.text(entry_id)
        if self.card is None or text is None:
            return
        saved = self.learner.vocabulary.saved_word(entry_id)
        sentence = saved.source_sentence if saved else ""
        rect = to_rect(cell)
        areas = work_areas()
        area = area_for(rect, areas) or (areas[0] if areas else rect)
        self.card.pin(
            WordAt(
                text.headword,
                LookupContext(sentence or text.headword),
                (0, len(text.headword)),
                rect,
                rect,
                area,
                (id(self) % 1_000_000, cell.x(), cell.y(), len(text.headword)),
                language_of(self.learner),
            )
        )

    def _status_menu(self, entry_id: EntryId) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("words.status_menu")
        current = self.learner.vocabulary.status_of_entry(entry_id).status
        for status in WordStatus:
            action = menu.addAction(status_name(status))
            action.setObjectName(f"words.status.{status.value}")
            action.setCheckable(True)
            action.setChecked(status is current)
            action.triggered.connect(
                lambda _=False, s=status: self.learner.vocabulary.set_status(
                    entry_id, s
                )
            )
        return menu

    def _category_menu(self, entry_id: EntryId) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("words.category_menu")
        vocabulary = self.learner.vocabulary
        word = vocabulary.saved_word(entry_id)
        for category in vocabulary.categories:
            action = menu.addAction(swatch(category.color), category.name)
            action.setObjectName(f"words.category.{category.id}")
            action.setCheckable(True)
            action.setChecked(word is not None and word.category_id == category.id)
            action.triggered.connect(
                lambda _=False, c=category.id: self._move(entry_id, c)
            )
        return menu

    def _move(self, entry_id: EntryId, category_id: CategoryId) -> None:
        vocabulary = self.learner.vocabulary
        word = vocabulary.saved_word(entry_id)
        if word is None or word.category_id == category_id:
            return
        vocabulary.save(
            word.entry_id, word.headword, word.traditional, word.reading, word.meaning,
            category_id, LookupContext(word.source_sentence, word.source_translation),
        )  # fmt: skip

    def _recolour(self, category: Category) -> None:
        colour = pick_colour(
            category.color, self, _tr("Colour for {name}").format(name=category.name)
        )
        if colour is not None:
            self.learner.vocabulary.change_category(category.id, color=colour)

    def _rename(self, category: Category, name: str) -> None:
        name = name.strip()
        if name and name != category.name:
            self.learner.vocabulary.change_category(category.id, name=name)

    def _add_category(self) -> None:
        name = self.new_category.text().strip()
        if name:
            self.new_category.clear()
            self.learner.vocabulary.add_category(name)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            _tr("Export words for Anki"),
            self.save_folder.start("polyglotic-words.csv"),
            _tr("CSV files (*.csv)"),
        )
        if path:
            self._export(write_csv, Path(path), AnkiFormat.CSV)

    def _export_deck(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            _tr("Export words as an Anki deck file"),
            self.save_folder.start("polyglotic-words.apkg"),
            _tr("Anki deck files (*.apkg)"),
        )
        if path:
            self._export(write_deck, Path(path), AnkiFormat.DECK)

    def _export(self, write: "Write", path: Path, file: AnkiFormat) -> None:
        """Writes the export on a thread of its own - the deck file took
        5.4 s and the CSV 1.6-1.8 s on the interface thread in the user's
        log (polyglotic-hq 273) - with the buttons busy meanwhile; then
        says what it wrote, and where (`_export_written`). The words are
        copied here, so the vocabulary can change while it writes. "Only
        words not exported yet" is per kind of `file` (polyglotic-hq 368)."""
        if self.exporting is not None:
            return
        only_new = self.only_new.isChecked()
        words = self.learner.vocabulary.anki_words(only_new, file)
        learner, written = self.learner, self._written

        def run() -> None:
            ids: tuple[EntryId, ...] | None
            try:
                ids = write(words, learner, path)
            except OSError as problem:
                # a file open in another program (Excel keeps a CSV it has
                # open locked) or a read-only folder: an answer, not an error
                log.warning("Anki export not written: %s", type(problem).__name__)
                ids = None
            with contextlib.suppress(RuntimeError):  # the page went meanwhile
                written.emit(_Exported(path, only_new, ids, file))

        self._show_exporting(path)
        self.exporting = threading.Thread(target=run, name="anki export")
        self.exporting.start()

    def _show_exporting(self, path: Path) -> None:
        for button in (self.export_csv, self.export_deck, self.only_new):
            button.setEnabled(False)
        self.export_result.setText(_tr("Writing {name}…").format(name=path.name))
        self.export_result.show()

    @Slot(object)
    def _export_written(self, done: "_Exported") -> None:
        """The export's file is written - the words in it marked exported,
        its folder remembered for the next - or it couldn't be: said either
        way, with where it went."""
        self.exporting = None
        if done.entry_ids is not None:
            self.learner.vocabulary.mark_exported(done.entry_ids, done.file)
            self.save_folder.saved(done.path)  # the next export opens there
        words, sentences = words_and_sentences(done.entry_ids or ())
        count = None if done.entry_ids is None else words
        where = QDir.toNativeSeparators(str(done.path))
        self.export_result.setText(export_said(count, where, done.only_new, sentences))
        self.export_result.show()
        self.export_csv.setEnabled(True)
        self.export_deck.setEnabled(self.learner.deck_writer is not None)
        self.only_new.setEnabled(True)
        self.export_done.emit()


@dataclass(frozen=True)
class _Exported:
    """An export, written: its file, whether only new words were asked for,
    the words in it - None if it couldn't be written - and its kind."""

    path: Path
    only_new: bool
    entry_ids: tuple[EntryId, ...] | None
    file: AnkiFormat


LANGUAGE_NAMES = {
    "zh": QT_TRANSLATE_NOOP("Words", "Chinese"),
    "en": QT_TRANSLATE_NOOP("Words", "English"),
}
"""The languages learned, as a section's heading names them."""
OPEN_KEY = "words_open"
"""Which language sections were left open or closed, in the settings file."""


def language_of(learner: WordsLearner) -> str:
    """The language `learner` learns (settings' codes: `zh`, `en`, or a
    pack language's - `ru`)."""
    return learner.language


def language_said(language: str) -> str:
    """A language learned, by name, as a section's heading and Words'
    lines say it: Chinese and English in Words' own words, a pack
    language's as Learning names it (`learned_name`)."""
    name = LANGUAGE_NAMES.get(language)
    return _tr(str(name)) if name else learned_name(language)


def heading(language: str, met: int | None) -> str:
    """A language section's heading: "Chinese · 360 words met" - or, not
    counted yet, "Chinese"."""
    said = language_said(language)
    if met is None:
        return said
    return in_sentence(_trn("{language} · %Ln word(s) met", met), language=said)


class OpenLanguages:
    """Which of Words' language sections the learner left open or closed -
    `{"zh": true, "en": false}` - kept in the settings file under its own
    key (`OPEN_KEY`), beside the others, as `SaveFolder` keeps its folder.
    Holds no words."""

    def __init__(self, store: SettingsStore | None = None) -> None:
        """`store`: the settings (none: this run only)."""
        self._store = store
        self._read: dict[str, object] = store.load() if store else {}
        """The settings file as last read: kept if a read finds nothing."""
        found = self._read.get(OPEN_KEY)
        self.opened: dict[str, bool] = (
            {k: v for k, v in found.items() if isinstance(v, bool)}
            if isinstance(found, dict)
            else {}
        )

    def set(self, language: str, open_: bool) -> None:
        """`language`'s section opened or closed: kept."""
        self.opened[language] = open_
        if self._store is None:
            return
        read = self._store.load()
        if read:
            self._read = read
        # nothing read - the file gone or unreadable for a moment - keeps the
        # settings as last read rather than losing them (`Settings.update`)
        self._read = {**self._read, OPEN_KEY: dict(self.opened)}
        self._store.save(self._read)


class LanguageSection(QWidget):
    """A language's section of Words: a heading - the language and how many
    words met - that opens and closes it, over its words. With one language
    there's no heading: it's simply open (`LanguageGroup.folds`)."""

    toggled = Signal(str, bool)
    """(the language, open): the learner opened or closed it."""

    def __init__(self, group: LanguageGroup, words: "LanguageWords") -> None:
        super().__init__()
        self.language = group.language
        self.words = words
        self._met: int | None = None
        """Words met, once counted; until then the heading names the
        language alone."""
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        self.heading = QPushButton()
        self.heading.setObjectName(f"words.language.{group.language}")
        self.heading.setProperty("kind", "section")
        self.heading.setCheckable(True)
        self.heading.setChecked(group.open)
        self.heading.setCursor(Qt.CursorShape.PointingHandCursor)
        self.heading.toggled.connect(self._toggled)
        column.addWidget(self.heading, 0, Qt.AlignmentFlag.AlignLeft)
        column.addWidget(words)
        self.heading.setVisible(group.folds)
        words.setVisible(group.open)
        words.counted.connect(self.count)
        self.count(None)

    def fold(self, folds: bool) -> None:
        """Whether it opens and closes under its heading: with one language
        it doesn't - simply open - with several it does (`LanguageGroup`)."""
        self.heading.setVisible(folds)

    def count(self, met: int | None) -> None:
        """The heading with `met` words met (None: not counted yet - the
        language alone), marked open or closed."""
        self._met = met
        said = heading(self.language, met)
        mark = "▾" if self.heading.isChecked() else "▸"
        self.heading.setText(f"{mark}  {said}")
        self.heading.setAccessibleName(said)

    def _toggled(self, open_: bool) -> None:
        self.words.setVisible(open_)  # shown: refreshed if out of date
        self.count(self._met)
        self.toggled.emit(self.language, open_)


class WordsPage(Page):
    """Words: a section per language learned (polyglotic-hq 250, the user's
    F23), each that language's words (`LanguageWords`). With one language
    it's simply open and the page looks as it did; with several, each opens
    and closes under a heading with its count, and stays as the learner
    left it (`OpenLanguages`). `main` hands over a learner per full language
    open (306), and one opened during the run (`add_learner`), the lookup
    card and where save dialogs open."""

    change_level_wanted = Signal(str)
    """A language's Change your level (its code): `main` opens the level
    picker."""

    def __init__(
        self,
        learners: WordsLearner | Sequence[WordsLearner],
        card: LookupCard | None,
        save_folder: SaveFolder | None = None,
        opened: OpenLanguages | None = None,
    ) -> None:
        """`opened`: which sections were left open (none: this run only)."""
        super().__init__(_tr("Words"), WORDS_COLUMN)
        self.in_use = label("", "Dim", wrap=True)
        self.in_use.setObjectName("words.in_use")
        self.in_use.hide()
        self.content.addWidget(self.in_use)
        each = list(learners) if isinstance(learners, Sequence) else [learners]
        self.opened = opened or OpenLanguages()
        self._card = card
        self._folder = save_folder or SaveFolder()
        groups = language_groups([language_of(e) for e in each], self.opened.opened)
        self.languages: list[LanguageWords] = []
        self.sections: list[LanguageSection] = []
        for learner, group in zip(each, groups, strict=True):
            self._add(learner, group)
        self.content.addStretch(1)

    def _add(self, learner: WordsLearner, group: LanguageGroup) -> None:
        words = LanguageWords(learner, self._card, self._folder)
        words.change_level_wanted.connect(
            lambda c=group.language: self.change_level_wanted.emit(c)
        )
        section = LanguageSection(group, words)
        section.toggled.connect(self.opened.set)
        # before the stretch, once there is one: in the order opened
        self.content.insertWidget(
            self.content.indexOf(self.sections[-1]) + 1
            if self.sections
            else self.content.count(),
            section,
        )
        self.languages.append(words)
        self.sections.append(section)

    def add_learner(self, learner: WordsLearner) -> None:
        """A full language opened during the run (Learning's "Learn it", a
        lookup's "Learn it too"; 306): its section, last, closed unless the
        learner left it open before; the first section then gets its
        heading, as with several from the start. The same language twice:
        nothing."""
        language = language_of(learner)
        if any(s.language == language for s in self.sections):
            return
        languages = [s.language for s in self.sections] + [language]
        groups = language_groups(languages, self.opened.opened)
        for section, group in zip(self.sections, groups, strict=False):
            section.fold(group.folds)
        self._add(learner, groups[-1])

    def show_in_use(self, running: Sequence[str], chosen: str | None) -> None:
        """Whose words these are, when the main language (`chosen`) is a full
        dictionary not open now (`running`: those open, main first): it opens
        from the next start, and until then the page shows the others'
        (polyglotic-hq 299). Hidden otherwise."""
        names = {code: _tr(str(name)) for code, name in LANGUAGE_NAMES.items()}
        shown = next((code for code in running if code in names), None)
        switching = chosen in names and shown is not None and chosen not in running
        self.in_use.setVisible(switching)
        if switching and shown is not None:
            self.in_use.setText(
                _tr(
                    "These are your {running} words. {chosen} is used from the "
                    "next time Polyglotic starts, and keeps its own words."
                ).format(running=names[shown], chosen=names[str(chosen)])
            )

    @property
    def first(self) -> "LanguageWords":
        """The first language's words - with one language, all of them."""
        return self.languages[0]

    def learning_changed(self, what: str = "") -> None:
        """Learning changed (`LearningTools.changed`): each language shows
        it again (`LanguageWords.learning_changed`); a closed one's heading
        is counted again at once while the page shows - not for every
        finished caption's words, which wait for the page's next showing."""
        for words in self.languages:
            words.learning_changed(what)
        if what != "exposures" and self.isVisible():
            self._count_closed()

    def showEvent(self, event: QShowEvent) -> None:
        self._count_closed()
        super().showEvent(event)

    def _count_closed(self) -> None:
        """Each closed section's heading counted, if Learning changed since
        (`LanguageWords.count`): with several languages, the ones folded
        away still say how many words they hold (306)."""
        for section in self.sections:
            words = section.words
            if not section.heading.isChecked() and words.count_dirty:
                words.count()

    def refresh(self) -> None:
        for words in self.languages:
            words.refresh()


def write_deck(
    words: AnkiWords, learner: WordsLearner, path: Path
) -> tuple[EntryId, ...]:
    """Writes `words` (`Vocabulary.anki_words`) to `path` as an Anki deck
    file (the same words and GUIDs as the CSV); returns the words in it.
    Safe off the interface thread: it reads only `words`, the dictionary
    and the deck writer."""
    if learner.deck_writer is None:
        raise RuntimeError("no deck file writer")
    pack = None if tier_of(learner.language) is Tier.FULL else learner.language
    # its own note type (0175); sentences in the language they were spoken in
    export = words.export(learner.describe, pack, learner.language)
    path.write_bytes(
        learner.deck_writer.build(export.notes, sentences=export.sentences)
    )
    return export.entry_ids


def write_csv(
    words: AnkiWords, learner: WordsLearner, path: Path
) -> tuple[EntryId, ...]:
    """Writes `words` to `path` as a CSV file for Anki, as UTF-8; returns
    the words in it. Safe off the interface thread, as `write_deck`."""
    export = words.export(learner.describe)
    path.write_text(export.text, encoding="utf-8", newline="")
    return export.entry_ids


Write = Callable[[AnkiWords, WordsLearner, Path], tuple[EntryId, ...]]
"""`write_deck` or `write_csv`."""


def export_deck(learner: WordsLearner, path: Path, only_new: bool = False) -> int:
    """Writes the saved words and the deck's to `path` as an Anki deck file
    - only the words not exported yet if `only_new` - and remembers they
    were exported once it's written. Returns how many words - and saved
    sentences (polyglotic-hq 459) - are in the file. All on this thread: Words writes on one of its own
    (`LanguageWords`)."""
    words = learner.vocabulary.anki_words(only_new, AnkiFormat.DECK)
    written = write_deck(words, learner, path)
    learner.vocabulary.mark_exported(written, AnkiFormat.DECK)
    return len(written)


def export_csv(learner: WordsLearner, path: Path, only_new: bool = False) -> int:
    """`export_deck`, as a CSV file."""
    words = learner.vocabulary.anki_words(only_new, AnkiFormat.CSV)
    written = write_csv(words, learner, path)
    learner.vocabulary.mark_exported(written, AnkiFormat.CSV)
    return len(written)


def _button(text: str, name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _column(widget: QWidget) -> QVBoxLayout:
    column = QVBoxLayout(widget)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    return column
