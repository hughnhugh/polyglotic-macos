"""A missing or damaged dictionary never stops the start (polyglotic-hq
199, 184's QA item 21: `cedict.sqlite` cut to 3 MB, or the dictionaries
folder empty, stopped the app with "Polyglotic couldn't start"). The
learning tools are built without it and say why; captions run, their words
neither marked nor counted while it's out; the learner's data is kept as
it was, and all there when it's back. Made-up text and the sample
dictionaries."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.test_guarded_dictionary import cut_off, damaged_inside
from tests.ui.test_check_install import checked, sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.recorded_captions import MIC, clause, finished


def test_the_learning_tools_are_built_without_a_dictionary(tmp_path: Path) -> None:
    empty = tmp_path / "dictionaries"
    empty.mkdir()
    for english in (False, True):
        tools, store = main.learner_tools(empty, english, tmp_path / "data")
        assert tools.dictionary_problem is DictionaryProblem.MISSING
        assert tools.lookup("电脑") == [] and tools.lookup("run") == []
        store.close()


def test_and_with_a_damaged_one(tmp_path: Path) -> None:
    folder = tmp_path / "dictionaries"
    folder.mkdir()
    cut_off(folder / "cedict.sqlite", 8192)
    tools, store = main.learner_tools(folder, False, tmp_path / "data")
    assert tools.dictionary_problem is DictionaryProblem.DAMAGED
    store.close()


def test_a_whole_dictionary_has_no_problem(tmp_path: Path) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    tools, store = main.learner_tools(folder, False, tmp_path / "data")
    assert tools.dictionary_problem is None
    assert tools.lookup("电脑")
    store.close()


def test_one_damaged_inside_goes_out_at_its_first_failing_query(
    qapp: QApplication, tmp_path: Path
) -> None:
    """It opens; the word split's read (or a lookup) meets the damage: the
    tools say so, once, by `dictionary_out`, and from then on as at a
    start without it."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    damaged_inside(folder / "cedict.sqlite")
    tools, store = main.learner_tools(folder, False, tmp_path / "data")
    assert tools.dictionary_problem is None
    told: list[bool] = []
    tools.dictionary_out.connect(lambda: told.append(True))

    assert isinstance(tools.dictionary, ChineseDictionary)
    tools.dictionary.prepare()  # its thread, in `main`
    assert tools.lookup("电脑") == []

    assert tools.dictionary_problem is DictionaryProblem.DAMAGED
    assert told == [True]
    assert tools.words_in("我的电脑又卡了，") == []
    store.close()


def test_captions_run_their_words_neither_marked_nor_counted(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Out, no word is found - none counted as heard (or first heard, or
    towards coverage), and none marked: nothing wrong is recorded."""
    empty = tmp_path / "dictionaries"
    empty.mkdir()
    tools, store = main.learner_tools(empty, False, tmp_path / "data")
    assert isinstance(tools.dictionary, ChineseDictionary)
    tools.dictionary.prepare()  # as `tools.prepare` does on its thread
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)

    feed.apply(finished("a", clause("我的电脑又卡了，"), clause("打游戏。")))

    assert feed.history.captions  # the caption is there
    assert tools.words_in("我的电脑又卡了，") == []
    assert tools.vocabulary.vocabulary_list() == []  # nothing heard
    lines = [("我的电脑又卡了，", tools.words_in("我的电脑又卡了，"))]
    marks = tools.vocabulary.highlights(lines)
    assert all(not (m.saved or m.unfamiliar or m.in_deck) for m in marks)
    store.close()


def test_the_learners_data_is_kept_while_its_out_and_all_there_when_back(
    tmp_path: Path,
) -> None:
    """A start without the dictionary moves, drops or changes nothing of
    the learner's (a merged entry is followed only when the dictionary
    can say so); the next start with it finds everything as it was."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    computer = tools.lookup("电脑")[0]
    tools.vocabulary.set_status(computer.entry_id, WordStatus.KNOWN)
    tools.vocabulary.caption_finished("a", tools.words_in("我的电脑又卡了"), False)
    before = tools.vocabulary.vocabulary_list()
    assert before
    store.close()

    empty = tmp_path / "empty"
    empty.mkdir()
    out, store = main.learner_tools(empty, False, data)
    assert out.dictionary_problem is DictionaryProblem.MISSING
    assert out.vocabulary.vocabulary_list() == before
    store.close()

    back, store = main.learner_tools(folder, False, data)
    assert back.dictionary_problem is None
    assert back.vocabulary.vocabulary_list() == before
    assert back.vocabulary.status(back.facts(computer)).status is WordStatus.KNOWN
    store.close()


@pytest.mark.windows_only  # a whole check: the windows need the OS's adapters
def test_check_install_names_whats_out_and_builds_the_rest(tmp_path: Path) -> None:
    """The release build's check fails on a dictionary that's out, naming
    it and why - after building everything else without it, as the app
    starts without it."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    cut_off(folder / "cedict.sqlite", 8192)

    code, found = checked(tmp_path, dictionaries=folder)

    assert code == 1 and found["ok"] is False
    assert found["dictionaries_out"] == {"cedict.sqlite": "damaged"}
    assert "cedict.sqlite" in found["error"]
    assert found["windows"] == [
        "caption_window",
        "joined_window",
        "transcript",
        "lookup_card",
    ]
