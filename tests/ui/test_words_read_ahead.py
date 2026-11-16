"""What Words reads from the dictionary for every word met - each one's
facts and the bands' sizes - is read at the start, on the dictionary's
thread, and handed back (`LearningTools.prepare`): Words' first show
reads none of it (polyglotic-hq project 212: 50 ms and more at 10,000
words met, on the interface thread). Then each one's text, which Words'
search reads: its first search reads nothing either (polyglotic-hq 220:
150 ms at 10,000 words met on CC-CEDICT)."""

import threading
import time
from collections.abc import Callable, Mapping, Sequence

import pytest
from PySide6.QtWidgets import QApplication
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import FakeDictionaryFile, chinese_sample, english_sample

from polyglotic_desktop.core.learning.bands import FREQUENCY_BANDS
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.learning import StoredExposures
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.words_page import WordsPage


class Recording(FakeDictionaryFile):
    """A dictionary file noting each read Words makes, and on which thread."""

    def __init__(self, file: FakeDictionaryFile) -> None:
        super().__init__(list(file.by_id.values()), file.forms, file.meaning_words)
        self.reads: list[tuple[str, str]] = []
        self.out: set[str] = set()
        """Entry IDs not found, as while the file is out."""

    def _read(self, what: str) -> None:
        self.reads.append((what, threading.current_thread().name))

    def record(self, entry_id: str) -> EntryRecord | None:
        self._read("record")
        return None if entry_id in self.out else super().record(entry_id)

    def words_ranked(self, last: int) -> Sequence[int]:
        self._read("words_ranked")
        return super().words_ranked(last)

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        self._read("words_at_levels")
        return super().words_at_levels(scheme)


def started(
    english: bool, kind: type[Recording] | None = None
) -> tuple[LearningTools, Recording]:
    """A learner's tools as at the app's start: every word in the sample
    heard twice, nothing read about them yet."""
    file = (kind or Recording)(english_sample() if english else chinese_sample())
    dictionary = EnglishDictionary(file) if english else ChineseDictionary(file)
    store = MemoryLearningStore()
    for entry_id in file.by_id:
        store.exposures[entry_id] = StoredExposures(entry_id, 2, 0, 0)
    scheme = "en-frequency" if english else "hsk-2025"

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    vocabulary = Vocabulary(store, facts, scheme, Clock())
    file.reads.clear()
    return LearningTools(vocabulary, dictionary), file


@pytest.mark.parametrize("english", [False, True])
def test_words_reads_are_read_ahead_on_the_dictionarys_thread(
    qapp: QApplication, english: bool
) -> None:
    tools, file = started(english)
    read_ahead(qapp, tools)
    assert file.reads and {thread for _, thread in file.reads} == {"dictionary"}
    # each word's facts, then its text (polyglotic-hq 220)
    assert sum(what == "record" for what, _ in file.reads) == 2 * len(file.by_id)
    file.reads.clear()
    vocabulary = tools.vocabulary
    met = vocabulary.met_words()
    vocabulary.vocabulary_list()
    vocabulary.keep_hearing()
    sizes = tools.band_sizes()
    assert file.reads == []  # Words' first show: nothing left to read
    assert met
    dictionary = tools.dictionary
    assert sizes == (
        dictionary.words_in_ranks(FREQUENCY_BANDS),
        dictionary.words_at_levels(vocabulary.scheme),
    )


def test_words_opened_before_the_read_ahead_reads_what_it_needs() -> None:
    """Before `prepare`'s hand-back (Words opened at once), Words reads
    what it needs itself, on the interface thread - as before 212."""
    tools, file = started(english=False)
    assert not tools.read_ahead
    tools.vocabulary.met_words()
    tools.band_sizes()
    assert {thread for _, thread in file.reads} == {"MainThread"}


def read_ahead(qapp: QApplication, tools: LearningTools) -> None:
    tools.prepare()
    deadline = time.monotonic() + 5
    while not tools.texts_read_ahead and time.monotonic() < deadline:
        qapp.processEvents()  # the reads, then the queued hand-backs
        time.sleep(0.005)
    assert tools.read_ahead and tools.texts_read_ahead


@pytest.mark.parametrize("english", [False, True])
def test_words_first_search_reads_nothing_after_the_read_ahead(
    qapp: QApplication, english: bool
) -> None:
    tools, file = started(english)
    read_ahead(qapp, tools)
    assert {thread for _, thread in file.reads} == {"dictionary"}
    file.reads.clear()
    page = WordsPage(tools, None)
    try:
        page.refresh()
        page.first.search.setText("a")  # in some word of either sample
        page.first._searching.timeout.emit()
        assert page.first.words.words.items  # found some
        assert file.reads == []  # every word's text was read ahead
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_a_word_the_read_ahead_didnt_find_is_read_when_wanted(
    qapp: QApplication,
) -> None:
    """The dictionary may have been out when it read: asked again."""
    tools, file = started(english=False)
    some = next(iter(file.by_id))
    file.out.add(some)
    read_ahead(qapp, tools)
    file.out.clear()
    file.reads.clear()
    text = tools.describe(EntryId(some))
    assert text is not None and text.headword == file.by_id[some].headword
    assert file.reads == [("record", "MainThread")]


def opened_at_once(qapp: QApplication, tools: LearningTools) -> WordsPage:
    """Words opened as the app starts: just after `prepare`, before its
    hand-back - wired as `main` wires it."""
    page = WordsPage(tools, None)
    tools.read_ahead_done.connect(page.learning_changed)
    tools.prepare()
    page.resize(900, 700)
    page.show()  # offscreen
    return page


def until(qapp: QApplication, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not done() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)


def test_words_opened_during_the_read_ahead_says_so_then_shows_the_words(
    qapp: QApplication,
) -> None:
    """Opened while the read ahead reads, Words read every word's facts
    itself, alongside it: 425 ms at 10,000 words met on CC-CEDICT
    (polyglotic-hq 212's finding 7). Now it says it's reading, reads
    nothing, and shows the words once the read ahead is back (220)."""
    tools, file = started(english=False)
    page = opened_at_once(qapp, tools)
    try:
        assert tools.reading_ahead
        assert page.first.reading.isVisible() and not page.first.words.isVisible()
        assert [read for read in file.reads if read[1] == "MainThread"] == []
        until(qapp, lambda: not page.first.reading.isVisible())
        assert tools.read_ahead and not tools.reading_ahead
        assert page.first.words.isVisible() and page.first.words.words.items
    finally:
        page.deleteLater()
        qapp.processEvents()


class Failing(Recording):
    """A bug in the read ahead: it fails on the dictionary's thread."""

    def words_ranked(self, last: int) -> Sequence[int]:
        if threading.current_thread().name == "dictionary":
            raise RuntimeError("the read ahead failed")
        return super().words_ranked(last)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_words_isnt_left_waiting_when_the_read_ahead_fails(qapp: QApplication) -> None:
    """It then reads what it needs itself, as before 212."""
    tools, _ = started(english=False, kind=Failing)
    page = opened_at_once(qapp, tools)
    try:
        assert page.first.reading.isVisible()
        until(qapp, lambda: not page.first.reading.isVisible())
        assert not tools.read_ahead and not tools.reading_ahead
        assert page.first.words.isVisible() and page.first.words.words.items
    finally:
        page.deleteLater()
        qapp.processEvents()
