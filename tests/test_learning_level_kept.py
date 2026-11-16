"""The level is kept beside the learning store as well as in it (decision
0048, polyglotic-hq 237; 223's QA, medium 3): a store set aside after
damage (206) took the level with it, and "What's your level?" opened at
the next start before Home said why. Now the new store takes the level
from its copy, so the learner isn't asked it again."""

import json
import logging
from pathlib import Path

import pytest
from tests.learning.test_vocabulary import lookup
from tests.test_learning_set_aside import DAMAGE

from polyglotic_desktop.adapters.sqlite_learning import (
    SqliteLearningStore,
    level_file,
    open_learning_store,
    read_level_file,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.ports.learning import StoredLevel

LEVEL = StoredLevel("hsk-2025", 3.5)


def with_a_level(path: Path, level: StoredLevel = LEVEL) -> None:
    store = SqliteLearningStore(path)
    store.save_level(level)
    store.close()


def files(folder: Path) -> list[str]:
    return sorted(each.name for each in folder.iterdir())


@pytest.mark.parametrize("damage", DAMAGE)
def test_a_store_set_aside_keeps_the_level(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "learning.sqlite"
    with_a_level(path)
    for each in tmp_path.glob("learning.sqlite*"):
        each.unlink()  # the store as each damage makes it; the copy stays
    make, _ = DAMAGE[damage]
    make(path)

    store = open_learning_store(path)

    assert store.set_aside is not None and store.created
    vocabulary = Vocabulary(store, lookup, "hsk-2025")
    assert vocabulary.line == KnownLine("hsk-2025", 3)  # not asked again
    store.close()
    again = SqliteLearningStore(path)  # and in the new store itself
    assert again.load().level == LEVEL
    again.close()


def test_each_change_of_level_is_kept_beside_the_store(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    store = SqliteLearningStore(path)
    vocabulary = Vocabulary(store, lookup, "hsk-2025")
    assert read_level_file(path) is None  # a first start: nothing to keep
    vocabulary.set_level(Level("hsk-2025", 2))
    assert read_level_file(path) == StoredLevel("hsk-2025", 2.5)
    vocabulary.set_level(Level("hsk-2025", 4))
    assert read_level_file(path) == StoredLevel("hsk-2025", 4.5)
    store.close()
    assert level_file(path).name == "learning-level.json"
    assert "learning-level.json.tmp" not in files(tmp_path)  # written whole
    english = tmp_path / "learning-en.sqlite"  # each language its own
    with_a_level(english, StoredLevel("en-frequency", 2.5))
    assert read_level_file(english) == StoredLevel("en-frequency", 2.5)
    assert read_level_file(path) == StoredLevel("hsk-2025", 4.5)


def test_a_store_from_before_writes_its_level_beside_it(tmp_path: Path) -> None:
    """An app before this one kept the level only in the store: its first
    start with this one writes the copy."""
    path = tmp_path / "learning.sqlite"
    with_a_level(path)
    level_file(path).unlink()
    store = SqliteLearningStore(path)
    store.close()
    assert read_level_file(path) == LEVEL


def test_the_store_wins_over_a_copy_that_differs(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    with_a_level(path)
    level_file(path).write_text(
        json.dumps({"scheme": "hsk-2025", "midpoint": 1.5}), "utf-8"
    )
    store = SqliteLearningStore(path)
    assert store.load().level == LEVEL
    store.close()
    assert read_level_file(path) == LEVEL


def test_a_copy_that_cant_be_read_is_left_out_and_the_level_asked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "learning.sqlite"
    level_file(path).write_text('{"scheme": "hsk-2025", "midp', "utf-8")
    with caplog.at_level(logging.INFO):
        store = SqliteLearningStore(path)
    assert Vocabulary(store, lookup, "hsk-2025").line is None  # asked, as before
    store.close()
    assert "the level's copy couldn't be read (JSONDecodeError)" in caplog.text
    assert "hsk-2025" not in caplog.text


def test_deleting_the_learning_data_keeps_the_level_and_its_copy(
    tmp_path: Path,
) -> None:
    """As before (Vocabulary.delete_learning_data): the level and the
    categories stay."""
    path = tmp_path / "learning.sqlite"
    store = SqliteLearningStore(path)
    store.save_level(LEVEL)
    store.delete_learning_data()
    assert store.load().level == LEVEL
    store.close()
    assert read_level_file(path) == LEVEL


def test_a_store_in_memory_keeps_no_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store = SqliteLearningStore(":memory:")
    store.save_level(LEVEL)
    assert store.load().level == LEVEL
    store.close()
    assert files(tmp_path) == []


def test_a_line_in_words_is_kept_in_the_same_two_values(tmp_path: Path) -> None:
    """polyglotic-hq 323: no new table or column - a version before it
    still opens the file, and reads a scheme it doesn't know."""
    path = tmp_path / "learning.sqlite"
    store = SqliteLearningStore(path)
    vocabulary = Vocabulary(store, lookup, "hsk-2025")
    vocabulary.set_known_words(3000)
    assert read_level_file(path) == StoredLevel("words", 3000.0)
    store.close()
    again = SqliteLearningStore(path)
    assert again.load().level == StoredLevel("words", 3000.0)
    assert Vocabulary(again, lookup, "hsk-2025").line == KnownLine.words(3000)
    again.close()
