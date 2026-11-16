"""Deleting the learning data on this PC deletes every open language's
(DECISIONS #135, polyglotic-hq 306): Account's "Also delete it from this
PC" empties each language's own learning data file and deletes the copies
set aside from each (207, 213) - none of it readable afterwards - for a
language opened during the run too, and one whose file is open but empty.
One that can't be deleted is named, and the others are deleted all the
same. Nothing is sent again afterwards; Words and the caption windows'
marks empty at once in every language. Made-up words; the sample
dictionaries; offscreen."""

import sqlite3
import threading
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample, english_sample
from tests.test_learning_set_aside import DAMAGE
from tests.ui.fakes import tools_for
from tests.ui.test_check_install import sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.adapters.background_learning import BackgroundLearningStore
from polyglotic_desktop.adapters.sqlite_learning import set_aside_in
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import VocabularyChanged
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.shared import LearningEvent, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.words_page import OpenLanguages, WordsPage

ZH_SENTENCE = "周末一起去打游戏吧"
EN_SENTENCE = "They run every weekend"


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def learned(tools: LearningTools, word: str, sentence: str) -> None:
    """`word` saved with `sentence`, in the deck, and heard: something in
    every part of the language's learning data."""
    entry = tools.lookup(word)[0]
    category = tools.vocabulary.categories[0].id
    context = LookupContext(sentence)
    tools.vocabulary.save(
        entry.entry_id, entry.headword, entry.traditional, "", "", category, context
    )
    tools.vocabulary.set_status(entry.entry_id, WordStatus.LEARNING)
    tools.vocabulary.caption_finished(f"heard-{word}", tools.words_in(sentence), False)


class Opened:
    """`main`'s learning tools on the sample dictionaries: Chinese, and each
    other full language opened beside it as `main` opens them."""

    def __init__(self, tmp_path: Path, damaged: bool = False) -> None:
        self.folder = sample_dictionaries(tmp_path / "dictionaries")
        self.data = tmp_path / "data"
        self.data.mkdir()
        if damaged:  # each language's file set aside at the start (206)
            make, _ = DAMAGE["cut off"]
            make(main.learning_file(self.data, "zh"))
            make(main.learning_file(self.data, "en"))
        self.tools, store = main.learner_tools(self.folder, False, self.data)
        self.stores: list[BackgroundLearningStore] = [store]

    def open_beside(self, *codes: str) -> None:
        languages = LearningLanguages("zh", codes)
        for _, store in main.tools_beside(
            self.tools, self.folder, self.data, languages
        ):
            self.stores.append(store)

    def delete_here(self) -> None:
        """The server's "deleted", with "Also delete it from this PC" ticked
        - `main`'s listener, told on a session's thread."""
        exchanged = main.QtExchange(self.tools, data=self.data)
        exchanged.delete_here = True
        told = threading.Thread(target=exchanged.learning_deleted)
        told.start()
        told.join()
        settle()  # applied on the interface's thread
        for store in self.stores:
            store.flush()
        settle()  # what the stores told, on theirs
        exchanged.deleteLater()

    def close(self) -> None:
        for store in self.stores:
            store.close()


def on_disk(data: Path) -> bytes:
    """Every file in the data folder, together - as anyone could read them."""
    return b"".join(each.read_bytes() for each in data.rglob("*") if each.is_file())


def test_every_open_language_and_its_copies_set_aside_are_deleted(
    qapp: QApplication, tmp_path: Path
) -> None:
    opened = Opened(tmp_path, damaged=True)
    opened.open_beside("en")
    try:
        zh, en = opened.tools, opened.tools.of("en")
        assert en is not zh
        learned(zh, "电脑", ZH_SENTENCE)
        learned(en, "run", EN_SENTENCE)
        for store in opened.stores:
            store.flush()
        assert sum(s.set_aside_copies() for s in opened.stores) == 2  # the dialog's
        assert ZH_SENTENCE.encode() in on_disk(opened.data)
        assert EN_SENTENCE.encode() in on_disk(opened.data)

        opened.delete_here()

        for tools in (zh, en):
            assert tools.vocabulary.saved_words == []
            assert tools.vocabulary.met_entries() == []
            assert tools.learning_set_aside is None  # gone with it (213)
        assert set_aside_in(opened.data) == []
        held = on_disk(opened.data)  # none of it readable afterwards (207)
        assert ZH_SENTENCE.encode() not in held and EN_SENTENCE.encode() not in held
        assert b"ecdict:run" not in held
    finally:
        opened.close()


def test_a_language_not_open_is_deleted_too(
    qapp: QApplication, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Decision 0175, polyglotic-hq 391: a language learned before and
    stopped, or a pack language whose pack was removed, has its file on
    this PC still. "Also delete it from this PC" empties it too, keeping
    its level and categories; one from a newer app is left, and logged."""
    before = Opened(tmp_path)
    before.open_beside("en")
    try:
        en = before.tools.of("en")
        learned(en, "run", EN_SENTENCE)
        categories = [c.name for c in en.vocabulary.categories]
    finally:
        before.close()
    newer = main.learning_file(tmp_path / "data", "ru")  # from a newer app
    db = sqlite3.connect(newer)
    db.execute("PRAGMA user_version = 99")
    db.execute("CREATE TABLE kept (word TEXT)")
    db.execute("INSERT INTO kept VALUES ('слово')")
    db.commit()
    db.close()
    assert EN_SENTENCE.encode() in on_disk(tmp_path / "data")

    opened = Opened.__new__(Opened)  # the next run: Chinese only
    opened.data = tmp_path / "data"
    opened.folder = tmp_path / "dictionaries"
    opened.tools, store = main.learner_tools(opened.folder, False, opened.data)
    opened.stores = [store]
    try:
        opened.delete_here()
        held = on_disk(opened.data)
        assert EN_SENTENCE.encode() not in held and b"ecdict:run" not in held
        assert "слово".encode() in held  # never opened, never written over
        assert "learning-ru.sqlite couldn't be deleted" in caplog.text
    finally:
        opened.close()
    again = Opened.__new__(Opened)
    again.data, again.folder = opened.data, opened.folder
    again.tools, store = main.learner_tools(again.folder, False, again.data)
    again.stores = [store]
    again.open_beside("en")
    try:
        en = again.tools.of("en")
        assert en.vocabulary.saved_words == [] and en.vocabulary.met_entries() == []
        assert [c.name for c in en.vocabulary.categories] == categories
    finally:
        again.close()


def test_a_language_opened_during_the_run_is_deleted_too(
    qapp: QApplication, tmp_path: Path
) -> None:
    opened = Opened(tmp_path)
    try:
        learned(opened.tools, "电脑", ZH_SENTENCE)
        opened.open_beside("en")  # "Learn it" on Learning, after the start
        en = opened.tools.of("en")
        learned(en, "run", EN_SENTENCE)
        opened.delete_here()
        assert en.vocabulary.saved_words == [] and en.vocabulary.met_entries() == []
        assert EN_SENTENCE.encode() not in on_disk(opened.data)
    finally:
        opened.close()


def test_an_open_but_empty_language_is_deleted_without_a_fault(
    qapp: QApplication, tmp_path: Path
) -> None:
    opened = Opened(tmp_path)
    opened.open_beside("en")  # English's file new: nothing in it yet
    try:
        en = opened.tools.of("en")
        deleted: list[str] = []
        left: list[str] = []
        for tools in opened.tools.every:
            tools.learning_deleted.connect(lambda c=tools.language: deleted.append(c))
            tools.learning_not_deleted.connect(lambda c=tools.language: left.append(c))
        learned(opened.tools, "电脑", ZH_SENTENCE)
        assert en.vocabulary.saved_words == []
        opened.delete_here()
        assert sorted(deleted) == ["en", "zh"] and left == []
    finally:
        opened.close()


def test_one_that_cant_be_deleted_is_named_and_the_others_still_go(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """English's file busy (not damaged): its data stays in it, and it says
    so - Home's notice names English; Chinese's is deleted all the same."""
    opened = Opened(tmp_path)
    opened.open_beside("en")
    try:
        zh, en = opened.tools, opened.tools.of("en")
        learned(zh, "电脑", ZH_SENTENCE)
        learned(en, "run", EN_SENTENCE)
        english_store = opened.stores[1]

        def busy() -> None:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(english_store._store, "delete_learning_data", busy)
        left: list[str] = []
        for tools in (zh, en):
            tools.learning_not_deleted.connect(lambda c=tools.language: left.append(c))

        opened.delete_here()

        assert left == ["en"]
        held = on_disk(opened.data)
        assert ZH_SENTENCE.encode() not in held  # the others deleted all the same
        assert EN_SENTENCE.encode() in held  # said, not hidden
        notice = main.not_deleted_notice("en")
        assert "English" in notice and "Account" in notice
    finally:
        opened.close()


def test_the_hub_says_which_language_wasnt_deleted(qapp: QApplication) -> None:
    """Told on the store's thread; Home's notice, on the interface's."""
    from tests.ui.fakes import Built, MemorySettingsStore

    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    try:
        tools = built.desktop.tools
        assert tools is not None
        en = english()
        tools.learn_beside(en)
        built.hub.language_opened(en)
        said: list[str] = []
        built.desktop.home_notice.connect(said.append)
        told = threading.Thread(target=en.learning_not_deleted.emit)
        told.start()
        told.join()
        settle()
        assert said == [main.not_deleted_notice("en")]
    finally:
        built.close()


# -- nothing sent again; Words and the marks emptied at once -----------------------------


def chinese() -> LearningTools:
    return tools_for(ChineseDictionary(chinese_sample()), DEFAULT_CHINESE_SCHEME.id)


def english() -> LearningTools:
    return tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)


def deleted_here(tools: LearningTools) -> None:
    exchanged = main.QtExchange(tools)
    exchanged.delete_here = True
    exchanged.learning_deleted()
    settle()
    exchanged.deleteLater()


def test_nothing_is_sent_again_after_the_deletion(qapp: QApplication) -> None:
    """The deletion publishes no learning event - the server's copy went by
    its own request - and leaves nothing to resend: no status or saved
    word for a restored server, no day's exposures."""
    zh, en = chinese(), english()
    zh.learn_beside(en)
    learned(zh, "电脑", ZH_SENTENCE)
    learned(en, "run", EN_SENTENCE)
    sent: list[object] = []
    for tools in (zh, en):
        tools.vocabulary.subscribe(sent.append)
    deleted_here(zh)
    assert not [e for e in sent if isinstance(e, LearningEvent)]
    assert all(isinstance(e, VocabularyChanged) for e in sent)
    for tools in (zh, en):
        assert tools.vocabulary.learning_state() == []
        assert tools.vocabulary.take_finished_exposure_days(date(2100, 1, 1)) == {}


def test_words_and_the_marks_empty_at_once_in_every_language(
    qapp: QApplication,
) -> None:
    zh, en = chinese(), english()
    zh.learn_beside(en)
    learned(zh, "电脑", ZH_SENTENCE)
    learned(en, "run", EN_SENTENCE)
    page = WordsPage(list(zh.every), None, opened=OpenLanguages())
    zh.changed.connect(page.learning_changed)  # every language's, as `main` does
    page.resize(900, 700)
    page.show()
    page.sections[1].heading.click()  # English opened too
    settle()
    view = CaptionLines((APP,), Language("en"), keep=10)
    view.apply(finished("a", clause("我的电脑", "they run"), language=Language("zh")))
    line = view.lines[0]
    marks = CaptionMarks(zh)
    zh.changed.connect(marks.learning_changed)

    def saved_colours(row: int) -> list[tuple[int, int]]:
        return [
            (start, end)
            for start, end, format_ in marks(line, row)
            if isinstance(format_, QTextCharFormat)
            and format_.hasProperty(QTextCharFormat.Property.ForegroundBrush)
        ]

    assert saved_colours(0) and saved_colours(1)  # both lines, before
    assert all(words.heard.words_met > 0 for words in page.languages)

    deleted_here(zh)
    QApplication.processEvents()

    assert saved_colours(0) == [] and saved_colours(1) == []
    assert [words.heard.words_met for words in page.languages] == [0, 0]
    assert page.sections[1].heading.text().endswith("0 words met")
    page.close()
    page.deleteLater()
    settle()


def test_a_copy_set_aside_that_cant_be_deleted_says_so_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store emptied, but a copy set aside from it in use (207 keeps
    it): that language's data isn't all gone from this PC - told, as a
    store that couldn't be emptied is."""
    from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore

    path = tmp_path / "learning-en.sqlite"
    copy = tmp_path / "learning-en.sqlite.damaged-20261101T000000Z"
    copy.write_bytes(b"in use")
    store = BackgroundLearningStore(lambda: SqliteLearningStore(path))
    told: list[str] = []
    store.on_deleted = lambda: told.append("deleted")
    store.on_not_deleted = lambda: told.append("left")

    def in_use(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", in_use)
    store.delete_learning_data()
    store.flush()
    monkeypatch.undo()
    store.close()
    assert copy.exists() and told == ["deleted", "left"]
