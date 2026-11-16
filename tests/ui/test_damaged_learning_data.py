"""A learning data file that can't be read never stops the start
(polyglotic-hq 206; 199 found it: a folder where `learning.sqlite` should
be stopped the app with "Polyglotic couldn't start"). It's set aside and
kept, a new one is started, and `--check-install` names it; a newer app's
file still stops the start (tests/ui/test_main_crashes.py). Made-up text
and the sample dictionaries."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.test_background_learning import damage
from tests.test_learning_set_aside import DAMAGE, SENTENCE, contents
from tests.ui.test_check_install import checked, sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.adapters.sqlite_learning import (
    SqliteLearningStore,
    set_aside_in,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.shared import Level, WordStatus
from polyglotic_desktop.ports.learning import (
    LearningDataProblem,
    LearningSnapshot,
    StoredStatus,
)


@pytest.mark.parametrize("english", [False, True])
@pytest.mark.parametrize("damage", ["a folder", "cut off", "not SQLite"])
def test_the_learning_tools_start_with_a_new_store(
    tmp_path: Path, damage: str, english: bool
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    data.mkdir()
    name = "learning-en.sqlite" if english else "learning.sqlite"
    make, _ = DAMAGE[damage]
    make(data / name)
    before = list(contents(data / name).values())

    tools, store = main.learner_tools(folder, english, data)

    word = tools.lookup("run" if english else "电脑")[0]
    tools.vocabulary.set_status(word.entry_id, WordStatus.KNOWN)
    assert tools.vocabulary.categories  # the first ones, as a new learner's
    store.close()
    (aside,) = set_aside_in(data)  # with its WAL files, if SQLite made them
    assert list(contents(data / aside).values()) == before  # kept as it was
    again, store = main.learner_tools(folder, english, data)
    assert again.vocabulary.status(again.facts(word)).status is WordStatus.KNOWN
    store.close()


@pytest.mark.windows_only  # a whole check: the windows need the OS's adapters
def test_check_install_names_the_files_set_aside(tmp_path: Path) -> None:
    """Listed, never opened; the check passes - the app starts."""
    data = tmp_path / "data"
    data.mkdir()
    for name in (
        "learning.sqlite.damaged-20261108T063000Z",
        "learning.sqlite.damaged-20261108T063000Z-wal",
        "learning-en.sqlite.damaged-20261101T000000Z",
    ):
        (data / name).write_bytes(b"set aside")

    code, found = checked(tmp_path, data=data)

    assert code == 0 and found["ok"] is True, found
    assert found["learning_set_aside"] == [
        "learning-en.sqlite.damaged-20261101T000000Z",
        "learning.sqlite.damaged-20261108T063000Z",
    ]


def test_a_new_store_is_new_and_a_whole_one_isnt(tmp_path: Path) -> None:
    """What `main` tells the exchange, so it syncs from the start, and Home
    and Help, so they say so."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    assert tools.learning_data_new  # a first start
    assert tools.learning_set_aside is None
    store.close()
    tools, store = main.learner_tools(folder, False, data)
    assert not tools.learning_data_new
    store.close()
    DAMAGE["not SQLite"][0](data / "learning.sqlite")
    tools, store = main.learner_tools(folder, False, data)
    assert tools.learning_data_new  # set aside
    aside = tools.learning_set_aside  # for Home and Help to say so
    assert aside is not None and aside.problem is LearningDataProblem.DAMAGED
    assert aside.path.name == set_aside_in(data)[0]
    store.close()
    tools, store = main.learner_tools(folder, False, data)
    assert tools.learning_set_aside is None  # once
    store.close()


def test_what_the_server_keeps_comes_back_and_the_rest_stays_aside(
    tmp_path: Path,
) -> None:
    """The learner's words, back from their account into a new store as
    the sync from the start brings them (`apply_from_server`, as
    `QtExchange` applies them): every status they set, every saved word, the
    words in the deck. What only this PC had - a saved word's sentence and
    category, the line a word went into the deck with, the level, exposure
    counts, what was exported to Anki - is in the file set aside. The level
    comes back from its copy beside the store (decision 0048, polyglotic-hq
    237: it was asked again before Home said why)."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    vocabulary = tools.vocabulary
    vocabulary.set_level(Level("hsk-2025", 3))
    computer = tools.lookup("电脑")[0]
    me = tools.lookup("人")[0]
    food = vocabulary.add_category("Mine")
    text = main.entry_text(tools, computer.entry_id)
    assert text is not None
    vocabulary.save(
        computer.entry_id, text.headword, text.traditional, text.reading,
        text.meaning, food.id, LookupContext(SENTENCE, "My computer froze again"),
    )  # fmt: skip
    vocabulary.set_status(computer.entry_id, WordStatus.KNOWN)
    me_text = main.entry_text(tools, me.entry_id)
    assert me_text is not None
    vocabulary.learn(me.entry_id, me_text, LookupContext(SENTENCE))
    vocabulary.caption_finished("a", tools.words_in(SENTENCE), False)
    vocabulary.mark_exported([computer.entry_id])
    on_the_server = vocabulary.learning_state()  # what this PC has sent
    store.close()
    DAMAGE["overwritten in places"][0](data / "learning.sqlite")

    tools, store = main.learner_tools(folder, False, data)
    vocabulary = tools.vocabulary
    changed = vocabulary.apply_from_server(
        on_the_server, lambda entry_id: main.entry_text(tools, entry_id)
    )

    assert changed == 3
    # back: the statuses, the saved word, the deck
    assert vocabulary.status_of_entry(computer.entry_id).status is WordStatus.KNOWN
    assert vocabulary.status_of_entry(me.entry_id).status is WordStatus.LEARNING
    (saved,) = vocabulary.saved_words
    assert (saved.entry_id, saved.headword) == (computer.entry_id, "电脑")
    # not back: only this PC had them
    assert saved.source_sentence == "" and saved.category_id != food.id
    assert vocabulary.category(food.id) is None
    assert vocabulary.deck_word(me.entry_id) is None  # its line
    assert vocabulary.line == KnownLine.picked(Level("hsk-2025", 3))  # kept
    assert vocabulary.exposures(computer.entry_id).heard == 0
    assert not vocabulary.is_exported(computer.entry_id)
    store.close()


def test_damage_found_by_the_first_read_is_set_aside_as_at_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Damage SQLite's own check missed, found by the snapshot's read: set
    aside, and a new store started - not an empty session."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    store.close()
    load = SqliteLearningStore.load
    reads: list[SqliteLearningStore] = []

    def damaged_once(self: SqliteLearningStore) -> LearningSnapshot:
        reads.append(self)
        if len(reads) == 1:
            raise damage()
        return load(self)

    monkeypatch.setattr(SqliteLearningStore, "load", damaged_once)

    tools, store = main.learner_tools(folder, False, data)

    assert not store.out  # the new one
    assert tools.learning_data_new  # syncs back from the start
    aside = tools.learning_set_aside
    assert aside is not None and aside.path.exists()
    tools.vocabulary.set_status(tools.lookup("电脑")[0].entry_id, WordStatus.KNOWN)
    store.close()
    assert (data / "learning.sqlite").exists()


def test_damage_found_later_tells_the_tools_once(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A save failing on a damaged file, from the store's thread to the
    learner's tools: nothing more is saved, and where the file went."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    seen: list[object] = []
    tools.learning_damaged.connect(seen.append)

    def damaged(self: SqliteLearningStore, status: StoredStatus) -> None:
        raise damage()

    monkeypatch.setattr(SqliteLearningStore, "save_status", damaged)
    computer = tools.lookup("电脑")[0]
    tools.vocabulary.set_status(computer.entry_id, WordStatus.KNOWN)
    tools.vocabulary.set_status(computer.entry_id, WordStatus.LEARNING)
    store.flush()
    qapp.processEvents()  # emitted on the store's thread: queued

    assert len(seen) == 1
    assert tools.learning_unsaved
    aside = tools.learning_set_aside
    assert aside is not None and aside.path.exists()
    assert not (data / "learning.sqlite").exists()
    # the session goes on, from what Learning holds
    status = tools.vocabulary.status_of_entry(computer.entry_id).status
    assert status is WordStatus.LEARNING
    store.close()


@pytest.mark.parametrize("damage", ["cut off", "a folder"])
def test_deleting_the_learning_data_forgets_the_file_set_aside_once_its_gone(
    qapp: QApplication, tmp_path: Path, damage: str
) -> None:
    """Polyglotic-hq 213 (207): "Delete learning data... also from this
    PC" deleted the file set aside at the start, but the tools still named
    it - so Home's banner and Help's check did - for the rest of that run.
    A folder set aside is kept (what's in it may not be the app's), so it's
    still named."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    data.mkdir()
    make, _ = DAMAGE[damage]
    make(data / "learning.sqlite")
    tools, store = main.learner_tools(folder, False, data)
    aside = tools.learning_set_aside
    assert aside is not None and aside.path.exists()

    tools.vocabulary.delete_learning_data()
    store.flush()
    qapp.processEvents()  # told on the store's thread: queued

    if damage == "a folder":
        assert aside.path.is_dir() and tools.learning_set_aside == aside
    else:
        assert not aside.path.exists() and tools.learning_set_aside is None
    store.close()
