"""Words' Saved sentences (polyglotic-hq 459; the user, 2026-11-14:
"filtering for a given save word or plain text search, matching on both
original / translation texts ... search from how they learnt it").

A card in each language's section of Words, after Saved words:
- **the search** - "Search saved sentences": a sentence with
  most of the query's words (each Chinese character a word) in what was
  said or its translation, best first (`Vocabulary.find_sentences`);
- **the filters** - a category (shared with saved words), and a saved
  word: only the sentences it's in;
- **the sentences**, newest first with no search: each what was said, its
  translation, and a line with its category, who said it and when; Move
  to… (a category) and Remove. `SHOWN` at first, then Show more.

Read when the card is first shown, not at the start (`Vocabulary`'s
sentences are read when first wanted). Holds caption text: never log it.
"""

from collections.abc import Callable, Sequence
from datetime import datetime

from PySide6.QtCore import QDate, QLocale, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.saved_words import CategoryId
from polyglotic_desktop.core.learning.sentences import SavedSentence, SentenceId
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Card, Combo, Flow, label

SHOWN = 20
"""Sentences listed at first, and how many more Show more adds."""
SEARCH_AFTER_MS = 150
"""The search runs this long after the last key (as Your words')."""


def _tr(text: str) -> str:
    return QApplication.translate("SavedSentences", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("SavedSentences", text, None, n)


def found_said(found: int, total: int, searching: bool) -> str:
    """The line under the filters: how many sentences, or how many match."""
    if searching:
        return _trn("{found} of %Ln saved sentence(s)", total).format(found=found)
    return _trn("%Ln saved sentence(s)", total)


class SentenceRow(QWidget):
    """One sentence: what was said, its translation, and its category, who
    said it and when - with Move to… and Remove."""

    def __init__(
        self,
        sentence: SavedSentence,
        category: str,
        colour: str,
        when: str,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("words.sentence")
        self.sentence_id = sentence.id
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 4, 0, 4)
        column.setSpacing(2)
        line = QHBoxLayout()
        line.setSpacing(8)
        self.original = label(sentence.original, wrap=True)
        self.original.setObjectName("words.sentence_original")
        line.addWidget(self.original, 1)
        self.move_to = QPushButton(_tr("Move to…"))
        self.move_to.setObjectName("words.sentence_move")
        self.move_to.setProperty("kind", "ghost")
        self.remove = QPushButton(_tr("Remove"))
        self.remove.setObjectName("words.sentence_remove")
        self.remove.setProperty("kind", "ghost")
        for button in (self.move_to, self.remove):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            line.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(line)
        if sentence.translation:
            self.translation = label(sentence.translation, "Dim", wrap=True)
            self.translation.setObjectName("words.sentence_translation")
            column.addWidget(self.translation)
        about = " · ".join(p for p in (category, *sentence.speakers, when) if p)
        self.about = label(about, "Faint", wrap=True)
        self.about.setObjectName("words.sentence_about")
        self.about.setStyleSheet(f"QLabel {{ border-left: 3px solid {colour}; padding-left: 6px; }}")  # fmt: skip
        column.addWidget(self.about)


class _Filter(Combo):
    """A filter's box, as wide as its widest choice draws. Qt sizes a box
    to its contents by each choice's ink (`QFontMetrics.boundingRect`) but
    draws it by its advance, wider in Korean's Malgun Gothic: "모든 저장한
    단어" ran 2 px past the box's text room (polyglotic-hq 472)."""

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        metrics = self.fontMetrics()
        texts = [self.itemText(i) for i in range(self.count())]
        if not texts:
            return hint
        drawn = max(metrics.horizontalAdvance(t) for t in texts)
        ink = max(metrics.boundingRect(t).width() for t in texts)
        return QSize(hint.width() + max(0, drawn - ink), hint.height())


class SavedSentences(Card):
    """The Saved sentences card of one language's Words. `vocabulary` gives
    that language's vocabulary."""

    def __init__(self, vocabulary: Callable[[], Vocabulary]) -> None:
        super().__init__(
            _tr("Saved sentences"),
            _tr(
                "Text you selected and saved from captions, with its translation. "
                "Search either language."
            ),
        )
        self.setObjectName("words.sentences")
        self.vocabulary = vocabulary
        self.shown = SHOWN
        filters = Flow()
        self.search = QLineEdit()
        self.search.setObjectName("words.sentence_search")
        self.search.setPlaceholderText(_tr("Search saved sentences"))
        self.search.setAccessibleName(_tr("Search saved sentences"))
        self.search.setClearButtonEnabled(True)
        clear = self.search.findChild(QToolButton)
        if clear is not None:
            clear.setAccessibleName(_tr("Clear search"))
            clear.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._searching = QTimer(self, singleShot=True, interval=SEARCH_AFTER_MS)
        self._searching.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _: self._searching.start())
        self.category = _Filter()
        self.category.setSizeAdjustPolicy(Combo.SizeAdjustPolicy.AdjustToContents)
        self.category.setObjectName("words.sentence_category")
        self.category.setAccessibleName(_tr("Filter by category"))
        self.category.currentIndexChanged.connect(lambda _: self.refresh())
        self.word = _Filter()
        self.word.setSizeAdjustPolicy(Combo.SizeAdjustPolicy.AdjustToContents)
        self.word.setObjectName("words.sentence_word")
        self.word.setAccessibleName(_tr("Filter by saved word"))
        self.word.currentIndexChanged.connect(lambda _: self.refresh())
        filters.add_widget(self.search, 1)
        filters.addWidget(self.category)
        filters.addWidget(self.word)
        self.add(filters)
        self.said = label("", "Dim", wrap=True)
        self.said.setObjectName("words.sentences_said")
        self.add(self.said)
        self.rows = QWidget()
        self.rows.setObjectName("words.sentence_rows")
        self.list = QVBoxLayout(self.rows)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.list.setSpacing(6)
        self.add(self.rows)
        self.more = QPushButton(_tr("Show more"))
        self.more.setObjectName("words.sentences_more")
        self.more.setProperty("kind", "ghost")
        self.more.clicked.connect(self._show_more)
        line = QHBoxLayout()
        line.addWidget(self.more)
        line.addStretch(1)
        self.add(line)
        self.empty = label(
            _tr(
                "No saved sentences yet. Select several words in the caption "
                "window, then choose a category."
            ),
            "Dim",
            wrap=True,
        )
        self.empty.setObjectName("words.sentences_empty")
        self.add(self.empty)
        self.menu: QMenu | None = None

    # -- the filters -------------------------------------------------------------

    def _fill_filters(self, vocabulary: Vocabulary) -> None:
        """The categories and saved words to filter by, the choices kept."""
        for combo, first, choices in (
            (
                self.category,
                _tr("All categories"),
                [(c.name, c.id) for c in vocabulary.categories],
            ),
            (
                self.word,
                _tr("All saved words"),
                sorted((w.headword, w.entry_id) for w in vocabulary.saved_words),
            ),
        ):
            chosen = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, None)
            for text, value in choices:
                combo.addItem(text, value)
            at = combo.findData(chosen) if chosen is not None else 0
            combo.setCurrentIndex(max(at, 0))
            combo.blockSignals(False)

    # -- the list ----------------------------------------------------------------

    def refresh(self) -> None:
        """The sentences the search and filters find, `shown` of them."""
        with spans.span("words.sentences"):
            vocabulary = self.vocabulary()
            self._fill_filters(vocabulary)
            query = self.search.text()
            category: CategoryId | None = self.category.currentData()
            word: EntryId | None = self.word.currentData()
            found = vocabulary.find_sentences(query, category, word)
            total = len(vocabulary.sentences)
            searching = bool(query.strip()) or category is not None or word is not None
            self._list([f.sentence for f in found[: self.shown]], vocabulary)
            self.said.setText(found_said(len(found), total, searching))
            self.said.setVisible(total > 0)
            self.more.setVisible(len(found) > self.shown)
            self.empty.setVisible(total == 0)
            for each in (self.search, self.category, self.word):
                each.setVisible(total > 0)

    def _list(self, sentences: Sequence[SavedSentence], vocabulary: Vocabulary) -> None:
        while self.list.count():
            item = self.list.takeAt(0)
            gone = item.widget() if item is not None else None
            if gone is not None:  # gone from sight now, deleted soon after
                gone.hide()
                gone.deleteLater()
        locale = QLocale()
        for sentence in sentences:
            category = vocabulary.category(sentence.category_id)
            row = SentenceRow(
                sentence,
                category.name if category else "",
                category.color if category else style.current()["BORDER"],
                _when(locale, sentence.saved_at),
                self.rows,
            )
            row.move_to.clicked.connect(
                lambda _=False, r=row: self._move_menu(r.sentence_id, r)
            )
            row.remove.clicked.connect(
                lambda _=False, s=sentence.id: vocabulary.unsave_sentence(s)
            )
            self.list.addWidget(row)
            row.show()

    def _show_more(self) -> None:
        self.shown += SHOWN
        self.refresh()

    def _move_menu(self, sentence_id: SentenceId, row: SentenceRow) -> None:
        vocabulary = self.vocabulary()
        menu = QMenu(self)
        for category in vocabulary.categories:

            def move(_: bool = False, chosen: CategoryId = category.id) -> None:
                vocabulary.move_sentence(sentence_id, chosen)

            menu.addAction(category.name, move)
        self.menu = menu
        menu.popup(row.move_to.mapToGlobal(row.move_to.rect().bottomLeft()))


def _when(locale: QLocale, at: datetime) -> str:
    """When it was saved, as the PC writes a short date."""
    local = at.astimezone()
    day = QDate(local.year, local.month, local.day)
    return locale.toString(day, QLocale.FormatType.ShortFormat)
