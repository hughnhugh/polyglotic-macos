"""Words in the new main window - today's Vocabulary, renamed, everything
kept (project 109's structure, section 7; build step 6): the rows' text
from the dictionary or what was saved, looked up only when shown; the
level; words you keep hearing into the deck; a status corrected; saved
words moved and removed; categories; the Anki export; the lookup pinned
from a word. Made-up learning, kept in memory; offscreen."""

import gc
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QMenu, QWidget
from tests.budget_judge import Sampled, timed, within
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for
from tests.ui_next.made_up import export_written

from polyglotic_desktop.core.learning.exposures import ExposureCount
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import SavedWord
from polyglotic_desktop.core.learning.vocabulary import AnkiFormat
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryId, Level, WordStatus
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import words_page
from polyglotic_desktop.ui_next.lookup_card import LookupCard, heard_in, more_readings
from polyglotic_desktop.ui_next.views.words import (
    KEEP_HEARING_FIRST,
    KEEP_HEARING_STEP,
    MAX_ROWS,
    SAVED_WORDS_ROWS,
    YOUR_WORDS_ROWS,
    WordRows,
    WordText,
    level_line,
    word_text,
)
from polyglotic_desktop.ui_next.word_table import ROW, Column
from polyglotic_desktop.ui_next.words_page import (
    HEARD_EVERY_MS,
    WordsPage,
    export_csv,
    export_said,
    heard_line,
    heard_times,
    words_count,
)


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    """Every window a test makes is deleted after it. A page kept alive to
    the end of the run (its signals' lambdas hold it) is destroyed after the
    application, and the process can end with an error once every test has
    passed (CI, 2026-11-07)."""
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


# -- the views: plain Python ------------------------------------------------------------


def test_a_rows_text_is_the_dictionarys_or_what_was_saved() -> None:
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    computer = tools.describe(entry(tools, "电脑"))
    assert word_text(computer, None) == WordText("电脑", "電腦", "diàn nǎo", "computer")
    kept = SavedWord(
        EntryId("gone"), "旧", "舊", "jiù", "old", "saved", "", "", datetime.now(UTC)
    )
    assert word_text(None, kept) == WordText("旧", "舊", "jiù", "old")
    assert word_text(None, None) is None


def test_a_search_finds_the_word_its_reading_or_its_meaning() -> None:
    text = WordText("电脑", "電腦", "diàn nǎo", "computer")
    for query in ("电", "電腦", "diàn", "comp", ""):
        assert text.matches(query)
    assert not text.matches("brain")


@pytest.mark.parametrize(
    "query",
    ["电", "電腦", "diàn", "diàn nǎo", "comp", "computer", "brain", "ǎo", "o\nc",
     "腦\ndiàn", "αΣ", "ας", "ασ", "φια", "i̇s", "dom; öl"],
)  # fmt: skip
def test_a_search_finds_what_matches_finds(query: str) -> None:
    """A search looks once in each word's `search_text` (polyglotic-hq 220)
    and finds just what `matches` finds - a query that would span two of a
    word's texts too."""
    words = [
        WordText("电脑", "電腦", "diàn nǎo", "computer"),
        WordText("ΣΟΦΙΑ", "", "ΣΟΦΊΑΣ", "WISDOM; ÖL"),
        WordText("İstanbul", "", "", "a city"),
    ] + [WordText(f"字{n}", "", f"zì {n}", f"word {n}; 电") for n in range(50)]
    texts = {EntryId(f"e{n}"): w for n, w in enumerate(words)}
    ids = list(texts)
    want = [e for e in ids if texts[e].matches(query.strip().lower())]
    rows = WordRows(texts.get)
    assert rows.found(ids, query) == want
    assert rows.found(ids, query) == want  # again, from what the first kept


def test_a_rows_text_is_looked_up_only_when_asked_for_and_once() -> None:
    asked: list[str] = []

    def text(entry_id: EntryId) -> WordText | None:
        asked.append(entry_id)
        return WordText(entry_id, "", "", f"meaning of {entry_id}")

    rows = WordRows(text)
    ids = [EntryId(f"e{n}") for n in range(1000)]
    assert rows.found(ids, "  ") == ids
    assert asked == []  # no search: nothing looked up until a row shows
    rows.text(ids[0])
    rows.text(ids[0])
    assert asked == ["e0"]
    assert rows.found(ids, "OF E999") == [EntryId("e999")]


def test_the_level_in_words() -> None:
    assert not level_line(None).picked
    starting = level_line(KnownLine("hsk-2025", 0))
    assert starting.picked and starting.level == "" and "HSK" in starting.scheme
    assert level_line(KnownLine("hsk-2025", 3)).level
    unknown = level_line(KnownLine("from-a-newer-version", 2))
    assert (unknown.scheme, unknown.level) == ("from-a-newer-version", "2")


# -- the page ------------------------------------------------------------------------


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture
def tools() -> LearningTools:
    zh = ChineseDictionary(chinese_sample())
    tools = tools_for(zh, "hsk-2025")
    tools.vocabulary.set_level(Level("hsk-2025", 6))
    for n in range(3):
        tools.vocabulary.caption_finished(f"c{n}", tools.words_in("我的电脑"), False)
    return tools


@pytest.fixture
def page(qapp: QApplication, tools: LearningTools) -> WordsPage:
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    page.resize(900, 700)
    page.show()
    settle()
    return page


def entry(tools: LearningTools, word: str) -> EntryId:
    return tools.lookup(word)[0].entry_id


def act(page: WordsPage, table_name: str, column: Column, entry_id: EntryId) -> None:
    table = {
        "hearing": page.first.hearing,
        "words": page.first.words,
        "saved": page.first.saved,
    }[table_name]
    row = [i.entry_id for i in table.words.items].index(entry_id)
    table.act(table.words.index(row, table.words.columns.index(column)))
    settle()


def test_the_level_and_change(page: WordsPage) -> None:
    assert "HSK" in page.first.level.text()
    asked: list[bool] = []
    page.change_level_wanted.connect(lambda: asked.append(True))
    page.first.change_level.click()
    assert asked == [True]


def test_words_you_keep_hearing_go_into_the_deck_in_one_click(
    page: WordsPage, tools: LearningTools
) -> None:
    computer = entry(tools, "电脑")
    assert [i.entry_id for i in page.first.hearing.words.items] == [computer]
    act(page, "hearing", Column.ADD, computer)
    assert tools.vocabulary.status_of_entry(computer).status is WordStatus.LEARNING
    assert page.first.hearing.words.items == []  # in the deck: no longer new
    assert page.first.hearing_empty.isVisible()


def test_words_you_keep_hearing_lists_a_few_then_more_in_steps(
    qapp: QApplication,
) -> None:
    """A few, then Show more adds a step at a time, and Show fewer goes
    back (polyglotic-hq 250, the user's F26); a word added to the deck
    makes room for the next."""
    from tools.ui_lab.pages import full_tools

    tools = full_tools()
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    page.resize(900, 700)
    page.show()
    settle()
    every = tools.vocabulary.keep_hearing(MAX_ROWS)
    assert len(every) > KEEP_HEARING_FIRST + KEEP_HEARING_STEP  # room for 2 steps
    shown = lambda: [i.entry_id for i in page.first.hearing.words.items]
    assert shown() == [e for e, _ in every[:KEEP_HEARING_FIRST]]
    assert (
        page.first.hearing_more.isVisible() and not page.first.hearing_fewer.isVisible()
    )
    page.first.hearing_more.click()
    settle()
    assert len(shown()) == KEEP_HEARING_FIRST + KEEP_HEARING_STEP
    assert page.first.hearing_fewer.isVisible()
    act(page, "hearing", Column.ADD, shown()[0])  # into the deck: the next moves up
    assert len(shown()) == KEEP_HEARING_FIRST + KEEP_HEARING_STEP
    while page.first.hearing_more.isVisible():
        page.first.hearing_more.click()
        settle()
    assert len(shown()) == len(every) - 1  # all of them, the one in the deck gone
    height = inner(page).height()
    page.first.hearing_fewer.click()
    laid_out(page, height)
    assert len(shown()) == KEEP_HEARING_FIRST
    assert (
        page.first.hearing_more.isVisible() and not page.first.hearing_fewer.isVisible()
    )
    page.close()


def test_a_status_is_corrected_from_its_menu(
    page: WordsPage, tools: LearningTools
) -> None:
    computer = entry(tools, "电脑")
    act(page, "words", Column.STATUS, computer)
    menu = page.findChild(QMenu, "words.status_menu")
    assert menu is not None
    known = next(a for a in menu.actions() if a.objectName() == "words.status.known")
    known.trigger()
    settle()
    assert tools.vocabulary.status_of_entry(computer).status is WordStatus.KNOWN
    item = page.first.words.item(computer)
    assert item is not None and item.status is WordStatus.KNOWN and item.own
    menu.close()


def test_the_list_filters_by_status_and_search(
    page: WordsPage, tools: LearningTools
) -> None:
    shown = {i.entry_id for i in page.first.words.words.items}
    assert entry(tools, "电脑") in shown
    page.first.search.setText("computer")
    page.first._searching.timeout.emit()
    assert [i.entry_id for i in page.first.words.words.items] == [entry(tools, "电脑")]
    page.first.search.setText("no such word")
    page.first._searching.timeout.emit()
    assert (
        page.first.words.words.items == []
        and page.first.words_note.text() == "No matches."
    )
    assert not page.first.words.isVisible()


def test_your_words_lists_a_few_then_show_all_then_show_fewer(
    qapp: QApplication,
) -> None:
    """Every word met, listed, ran the page's length: a few rows, then Show
    all (how many) - or the search (polyglotic-hq 250, the user's F24)."""
    from tools.ui_lab.pages import full_tools

    tools = full_tools()  # 360 words met
    page = WordsPage(tools, None)
    page.show()
    settle()
    assert len(page.first.words.words.items) == YOUR_WORDS_ROWS
    assert page.first.words.height() == YOUR_WORDS_ROWS * ROW
    assert (
        page.first.words_all.isVisible()
        and page.first.words_all.text() == "Show all (360)"
    )
    assert not page.first.words_note.isVisible()  # no "N more" under a short list
    page.first.words_all.click()
    settle()
    assert len(page.first.words.words.items) == MAX_ROWS
    assert page.first.words_note.text().startswith("60 more")
    assert (
        page.first.words.height() == MAX_ROWS * ROW
    )  # the page scrolls, not the table
    assert page.first.words_all.text() == "Show fewer"
    page.learning_changed()  # a refresh keeps what was asked
    settle()
    assert len(page.first.words.words.items) == MAX_ROWS
    page.first.words_all.click()
    settle()
    assert len(page.first.words.words.items) == YOUR_WORDS_ROWS
    assert not page.first.words_note.isVisible()
    page.close()


def test_show_fewer_from_far_down_keeps_the_button_where_it_was(
    qapp: QApplication,
) -> None:
    """Show fewer at the end of 300 rows: the button stays where it was on
    the screen - not the page's end, a few thousand pixels further on."""
    from PySide6.QtCore import QPoint
    from tools.ui_lab.pages import full_tools

    page = WordsPage(full_tools(), None)
    page.resize(900, 700)
    page.show()
    settle()
    height = inner(page).height()
    page.first.words_all.click()
    laid_out(page, height)
    page.ensureWidgetVisible(page.first.words_all)
    settle()
    at = page.first.words_all.mapTo(page, QPoint()).y()
    assert 0 <= at < page.height()
    height = inner(page).height()
    page.first.words_all.click()
    laid_out(page, height)
    assert page.first.words_all.text().startswith("Show all")
    assert page.first.words_all.mapTo(page, QPoint()).y() == at
    page.close()


def inner(page: WordsPage) -> QWidget:
    """The page's scrolled column."""
    widget = page.widget()
    assert widget is not None
    return widget


def laid_out(page: WordsPage, height: int) -> None:
    """Until the page is no longer `height` tall: it takes its new height a
    few passes after its lists do."""
    import time

    deadline = time.monotonic() + 2
    while inner(page).height() == height and time.monotonic() < deadline:
        settle()
        time.sleep(0.01)
    settle()


def test_a_search_lists_its_first_few_and_says_how_many_it_found(
    qapp: QApplication,
) -> None:
    from tools.ui_lab.pages import full_tools

    page = WordsPage(full_tools(), None)
    page.show()
    settle()
    page.first.search.setText("sky")
    page.first._searching.timeout.emit()
    found = page.first.rows.found(
        page.first.learner.vocabulary.met_entries(None), "sky"
    )
    assert len(found) > YOUR_WORDS_ROWS
    assert len(page.first.words.words.items) == YOUR_WORDS_ROWS
    assert page.first.words_all.text() == f"Show all ({len(found)})"
    page.first.search.setText("天山")
    page.first._searching.timeout.emit()
    assert len(page.first.words.words.items) == 1
    assert not page.first.words_all.isVisible()  # all of it is listed
    page.close()


def test_saved_words_move_between_categories_and_are_removed(
    page: WordsPage, tools: LearningTools
) -> None:
    computer = tools.lookup("电脑")[0]
    vocabulary = tools.vocabulary
    vocabulary.save(
        computer.entry_id, computer.headword, computer.traditional, computer.reading,
        "computer", "saved", LookupContext("我的电脑"),
    )  # fmt: skip
    settle()
    item = page.first.saved.item(computer.entry_id)
    assert item is not None and item.category is not None
    assert item.category.id == "saved" and item.sentence == "我的电脑"
    act(page, "saved", Column.CATEGORY, computer.entry_id)
    menu = page.findChild(QMenu, "words.category_menu")
    assert menu is not None
    tricky = next(
        a for a in menu.actions() if a.objectName() == "words.category.tricky"
    )
    tricky.trigger()
    settle()
    moved = vocabulary.saved_word(computer.entry_id)
    assert moved is not None and moved.category_id == "tricky"
    assert moved.source_sentence == "我的电脑"  # kept
    menu.close()
    act(page, "saved", Column.REMOVE, computer.entry_id)
    assert vocabulary.saved_word(computer.entry_id) is None
    assert page.first.saved_empty.isVisible()


def test_saved_words_lists_a_few_then_show_all_then_show_fewer(
    qapp: QApplication,
) -> None:
    """Every saved word, listed, ran the page's length, as Your words had: a
    few rows, then Show all (how many) (polyglotic-hq 258; the user's F24,
    250)."""
    from tools.ui_lab.pages import full_tools

    page = WordsPage(full_tools(), None)
    page.show()
    settle()
    first = page.first
    saved = len(first.learner.vocabulary.saved_words)
    assert saved > SAVED_WORDS_ROWS
    assert len(first.saved.words.items) == SAVED_WORDS_ROWS
    assert first.saved.height() == SAVED_WORDS_ROWS * ROW
    assert first.saved_all.isVisible()
    assert first.saved_all.text() == f"Show all ({saved})"
    first.saved_all.click()
    settle()
    assert len(first.saved.words.items) == saved
    assert first.saved.height() == saved * ROW  # the page scrolls, not the table
    assert first.saved_all.text() == "Show fewer"
    page.learning_changed()  # a refresh keeps what was asked
    settle()
    assert len(first.saved.words.items) == saved
    first.saved_all.click()
    settle()
    assert len(first.saved.words.items) == SAVED_WORDS_ROWS
    assert first.saved_all.text() == f"Show all ({saved})"
    page.close()


def test_a_few_saved_words_need_no_show_all(
    page: WordsPage, tools: LearningTools
) -> None:
    computer = tools.lookup("电脑")[0]
    tools.vocabulary.save(
        computer.entry_id, computer.headword, computer.traditional, computer.reading,
        "computer", "saved", LookupContext("我的电脑"),
    )  # fmt: skip
    settle()
    assert len(page.first.saved.words.items) == 1
    assert not page.first.saved_all.isVisible()


def test_categories_are_added_renamed_and_deleted(
    page: WordsPage, tools: LearningTools
) -> None:
    vocabulary = tools.vocabulary
    page.first.new_category.setText("  Food ")
    page.first.add_category.click()
    settle()
    food = next(c for c in vocabulary.categories if c.name == "Food")
    row = next(
        r
        for r in page.first.categories.children()
        if getattr(r, "category", None) == food
    )
    row.name.setText("Cooking")  # type: ignore[attr-defined]
    row.name.editingFinished.emit()  # type: ignore[attr-defined]
    settle()
    assert vocabulary.category(food.id).name == "Cooking"  # type: ignore[union-attr]
    row = next(
        r
        for r in page.first.categories.children()
        if getattr(getattr(r, "category", None), "id", None) == food.id
    )
    row.delete.click()  # type: ignore[attr-defined]
    settle()
    assert vocabulary.category(food.id) is None


def test_category_rows_are_reached_between_your_words_and_new_category(
    page: WordsPage,
) -> None:
    """The rows are rebuilt after the page; Tab still reaches them where
    they are, not after everything else (131)."""
    from tests.ui_next.made_up import tab_stops

    stops = tab_stops(page)
    rows = [s for s in stops if s.objectName().startswith("category.")]
    assert len(rows) >= 3
    assert stops.index(page.first.words) < stops.index(rows[0])
    assert stops.index(rows[-1]) < stops.index(page.first.new_category)


def test_learning_changed_while_hidden_shows_when_the_page_next_shows(
    page: WordsPage, tools: LearningTools
) -> None:
    page.hide()
    computer = entry(tools, "电脑")
    tools.vocabulary.set_status(computer, WordStatus.KNOWN)
    settle()
    assert page.first.hearing.words.items  # not refreshed while hidden
    page.show()
    settle()
    assert page.first.hearing.words.items == []


def test_the_csv_export_writes_the_words_and_remembers(
    page: WordsPage, tools: LearningTools, tmp_path: Path
) -> None:
    computer = entry(tools, "电脑")
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    path = tmp_path / "words.csv"
    assert export_csv(tools, path) == 1
    assert "电脑" in path.read_text(encoding="utf-8")
    assert export_csv(tools, tmp_path / "again.csv", only_new=True) == 0
    assert not page.first.export_deck.isEnabled()  # no deck writer handed over


def chosen_file(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """The save dialog answers `path`, as if the learner picked it."""
    monkeypatch.setattr(
        words_page.QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(path), "")
    )


written = export_written  # its file written on its own thread, and said (273)


def test_an_export_says_how_many_words_went_and_where(
    page: WordsPage,
    tools: LearningTools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools.vocabulary.set_status(entry(tools, "电脑"), WordStatus.LEARNING)
    assert not page.first.export_result.isVisible()
    chosen_file(monkeypatch, tmp_path / "words.csv")
    page.first.export_csv.click()
    written(page)
    assert page.first.export_result.isVisible()
    where = str(tmp_path / "words.csv")  # the full path: where it went (273)
    assert page.first.export_result.text() == f"1 word written to {where}."
    page.first.only_new.setChecked(True)
    chosen_file(monkeypatch, tmp_path / "again.csv")
    page.first.export_csv.click()
    written(page)
    assert "No new words since the last export" in page.first.export_result.text()


def test_an_export_writes_off_the_interface_thread_with_the_buttons_busy(
    page: WordsPage,
    tools: LearningTools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deck file took 5.4 s and the CSV 1.6-1.8 s on the interface
    thread in the user's log (polyglotic-hq 273): the click now returns at
    once, the buttons busy and the page saying it's writing, and the file is
    written on a thread of its own."""
    tools.vocabulary.set_status(entry(tools, "电脑"), WordStatus.LEARNING)
    release, threads = threading.Event(), []
    write_csv = words_page.write_csv

    def slow_write(*args: object) -> tuple[EntryId, ...]:
        threads.append(threading.current_thread())
        assert release.wait(10)  # held until the test has looked
        return write_csv(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(words_page, "write_csv", slow_write)
    chosen_file(monkeypatch, tmp_path / "words.csv")
    page.first.export_csv.click()  # returns while the file is written
    assert threads and threads[0] is not threading.main_thread()
    busy = (page.first.export_csv, page.first.export_deck, page.first.only_new)
    assert not any(b.isEnabled() for b in busy)
    assert page.first.export_result.text() == "Writing words.csv…"
    page.first.export_csv.click()  # a second click meanwhile: nothing more
    release.set()
    written(page)
    assert len(threads) == 1
    assert page.first.export_csv.isEnabled() and page.first.only_new.isEnabled()
    assert not page.first.export_deck.isEnabled()  # no deck writer, as before
    assert page.first.export_result.text().startswith("1 word written to")
    assert tools.vocabulary.is_exported(entry(tools, "电脑"))  # marked once written


def test_a_csv_of_only_new_words_after_a_deck_file_has_them(
    page: WordsPage,
    tools: LearningTools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """368 (QA 361's B5): after an .apkg, Export CSV with "Only words not
    exported yet" said nothing new - the two kinds shared one record."""
    computer = entry(tools, "电脑")
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    tools.vocabulary.mark_exported([computer], AnkiFormat.DECK)  # an .apkg had it
    page.first.only_new.setChecked(True)
    chosen_file(monkeypatch, tmp_path / "words.csv")
    page.first.export_csv.click()
    written(page)
    assert page.first.export_result.text().startswith("1 word written to")
    assert "电脑" in (tmp_path / "words.csv").read_text(encoding="utf-8-sig")
    chosen_file(monkeypatch, tmp_path / "again.csv")
    page.first.export_csv.click()  # the CSV's own record now has it
    written(page)
    assert page.first.export_result.text().startswith("No new words")


def test_an_export_click_within_the_click_budget(
    page: WordsPage,
    tools: LearningTools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """However long the file takes to write - here 200 ms a file - the
    click shows its change within the click budget (`budgets.CLICK`)."""
    tools.vocabulary.set_status(entry(tools, "电脑"), WordStatus.LEARNING)

    def slow_write(*args: object) -> tuple[EntryId, ...]:
        time.sleep(0.2)
        return (entry(tools, "电脑"),)

    monkeypatch.setattr(words_page, "write_csv", slow_write)
    chosen_file(monkeypatch, tmp_path / "words.csv")

    def take() -> Sampled:
        """Five clicks, each after the last one's file is written (that
        wait not timed); the garbage collector held off, as `sampled`."""
        runs = []
        gc.disable()
        try:
            for _ in range(5):
                written(page)
                runs.append(timed(qapp, page.first.export_csv.click))
        finally:
            gc.enable()
        return Sampled(tuple(runs))

    within(budgets.CLICK, take)
    written(page)


def test_an_export_that_cant_be_written_says_so_not_an_error(
    page: WordsPage,
    tools: LearningTools,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CSV open in Excel is locked, and a folder can be read-only: the
    page says so (145 found the error went uncaught - the crash report's
    offer at the next start)."""
    tools.vocabulary.set_status(entry(tools, "电脑"), WordStatus.LEARNING)
    path = tmp_path / "words.csv"
    path.write_text("open elsewhere", encoding="utf-8")
    path.chmod(0o444)  # read-only, as a file another program holds
    chosen_file(monkeypatch, path)
    try:
        page.first._export_csv()  # raised PermissionError before
        written(page)
    finally:
        path.chmod(0o666)
    assert page.first.export_result.isVisible()
    assert page.first.export_result.text().startswith(f"Couldn't write {path}.")
    assert (
        export_csv(tools, tmp_path / "later.csv", only_new=True) == 1
    )  # not marked exported


def test_export_for_anki_links_to_how_to_import_it(
    page: WordsPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """How to import into Anki opens the site's help on it, in the browser
    (polyglotic-hq 250, the user's F25)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    from polyglotic_desktop.core.shared.papers import HELP_ANKI

    opened: list[str] = []

    def open_url(url: QUrl) -> bool:
        opened.append(url.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)
    assert page.first.anki_help.isVisible()
    assert page.first.anki_help.text() == "How to import into Anki"
    page.first.anki_help.click()
    assert opened == [HELP_ANKI]
    assert HELP_ANKI.endswith("/help/your-words-and-anki/")


def test_what_an_export_says(qapp: QApplication) -> None:
    assert export_said(12, "polyglotic-words.apkg", False) == (
        "12 words written to polyglotic-words.apkg."
    )
    assert export_said(1, "w.csv", False) == "1 word written to w.csv."
    assert export_said(0, "w.csv", False).startswith("No words to export yet")
    assert export_said(0, "w.csv", True).startswith(
        "No new words since the last export"
    )
    assert "open in another program" in export_said(None, "w.csv", False)
    # saved sentences go with the words (polyglotic-hq 459)
    assert export_said(12, "w.apkg", False, 3) == (
        "12 words written to w.apkg. And 3 saved sentences."
    )
    assert export_said(0, "w.apkg", True, 1) == "1 saved sentence written to w.apkg."


def test_a_word_pins_the_caption_windows_lookup(
    qapp: QApplication, tools: LearningTools
) -> None:
    card = LookupCard(tools)
    page = WordsPage(tools, card)
    page.show()
    settle()
    computer = entry(tools, "电脑")
    act(page, "words", Column.MEANING, computer)  # the meaning is the word's too
    assert card.pinned and card.model.word == "电脑"
    card.close_card()
    card.close()
    page.close()


class WindowsShown(QObject):
    """Every widget shown as a window of its own while it watches."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            self.shown.append(type(watched).__name__)
        return False


def test_no_part_of_the_page_shows_as_a_window_of_its_own(
    qapp: QApplication, tools: LearningTools
) -> None:
    """A widget made visible before it has a parent flashes up as a window
    of its own on a real screen (and costs a native window): a category's
    Delete did, at every refresh of the categories."""
    watching = WindowsShown()
    qapp.installEventFilter(watching)
    try:
        page = WordsPage(tools, None)
        page.show()
        settle()
        tools.vocabulary.add_category("Food")  # the categories built again
        settle()
    finally:
        qapp.removeEventFilter(watching)
    assert watching.shown == ["WordsPage"]
    page.close()


def test_words_heard_while_listening_refresh_at_most_once_a_second(
    page: WordsPage, tools: LearningTools
) -> None:
    for n in range(5):  # captions finishing while the page shows
        tools.vocabulary.caption_finished(f"d{n}", tools.words_in("电脑"), False)
    assert (
        page.first._later.isActive() and page.first._later.interval() == HEARD_EVERY_MS
    )
    page.learning_changed("statuses")  # the learner's own change: at once
    assert page.first._later.interval() == 0


def test_counts_read_as_words(qapp: QApplication) -> None:
    """No "time(s)" or "word(s)" (the user, 2026-11-07)."""
    assert heard_times(1) == "heard once"
    assert heard_times(12) == "heard 12 times"
    assert words_count(1) == "1 word" and words_count(0) == "0 words"


def test_a_saved_words_row_says_its_counts_in_words(qapp: QApplication) -> None:
    """polyglotic-hq 133: a row said "heard 0 · by you 0 · in deck 0", and
    the card "Heard in 1 caption(s)". Each count is said only when it
    happened, in words (137)."""
    assert heard_line(ExposureCount()) == "not heard yet"
    assert heard_line(ExposureCount(1)) == "heard once"
    assert heard_line(ExposureCount(12, 1, 3)) == (
        "heard 12 times · 3 since it went in your deck · you said it once"
    )
    assert heard_line(ExposureCount(0, 2)) == "not heard yet · you said it 2 times"
    assert heard_in(1) == "Heard in 1 caption" and heard_in(4) == "Heard in 4 captions"
    assert more_readings(1) == "+1 more reading"
    assert more_readings(2) == "+2 more readings"
