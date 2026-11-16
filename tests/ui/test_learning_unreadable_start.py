"""A garbled row in the learning data never stops the start (polyglotic-hq
207): `main` builds the learner's tools without it, and `--check-install`
counts it. Too many stop the start, as a newer app's file does, with
nothing set aside or written. Made-up rows and the sample dictionaries."""

from pathlib import Path

import pytest
from tests.test_learning_unreadable_rows import GARBLED, put, rows_in
from tests.ui.test_check_install import checked, sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.adapters.sqlite_learning import (
    LearningStoreUnreadableError,
    set_aside_in,
)
from polyglotic_desktop.core.shared import WordStatus


def started_with_a_word_known(folder: Path, data: Path, english: bool) -> str:
    """The learner's store as the app writes it, with one word known."""
    tools, store = main.learner_tools(folder, english, data)
    word = tools.lookup("run" if english else "电脑")[0]
    tools.vocabulary.set_status(word.entry_id, WordStatus.KNOWN)
    store.close()
    return "run" if english else "电脑"


@pytest.mark.parametrize("english", [False, True])
@pytest.mark.parametrize(
    "garble", ["a status's bad time", "a status this app doesn't know"]
)
def test_a_garbled_row_never_stops_the_start(
    tmp_path: Path, garble: str, english: bool
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    text = started_with_a_word_known(folder, data, english)
    path = data / ("learning-en.sqlite" if english else "learning.sqlite")
    put(path, *GARBLED[garble])

    tools, store = main.learner_tools(folder, english, data)

    word = tools.lookup(text)[0]
    assert tools.vocabulary.status(tools.facts(word)).status is WordStatus.KNOWN
    assert not tools.learning_data_new and tools.learning_set_aside is None
    store.close()
    assert rows_in(path, "statuses") == 2  # the garbled one kept
    assert set_aside_in(data) == []


def test_too_many_stop_the_start_with_nothing_set_aside_or_written(
    tmp_path: Path,
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    started_with_a_word_known(folder, data, False)
    path = data / "learning.sqlite"
    for n in range(3):
        put(
            path,
            "INSERT INTO statuses VALUES (?, ?, ?, ?)",
            (f"cedict:bad{n}", "mastered", "learner", "2026-11-08T06:30:00+00:00"),
        )
    before = path.read_bytes()

    with pytest.raises(LearningStoreUnreadableError):
        main.learner_tools(folder, False, data)

    assert set_aside_in(data) == []
    assert path.read_bytes() == before


@pytest.mark.windows_only  # a whole check: the windows need the OS's adapters
def test_check_install_counts_unreadable_rows_and_fails_on_a_refused_store(
    tmp_path: Path,
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    started_with_a_word_known(folder, data, False)
    started_with_a_word_known(folder, data, True)
    put(data / "learning.sqlite", *GARBLED["a status's bad time"])
    for n in range(3):  # all 3 of 4: refused
        put(
            data / "learning-en.sqlite",
            "INSERT INTO statuses VALUES (?, ?, ?, ?)",
            (f"ecdict:bad{n}", "mastered", "learner", "2026-11-08T06:30:00+00:00"),
        )

    code, found = checked(tmp_path, dictionaries=folder, data=data)

    assert code == 1 and found["ok"] is False, found
    assert found["learning_unreadable"] == {
        "learning-en.sqlite": 3,
        "learning.sqlite": 1,
    }
    assert found["learning_refused"] == {"learning-en.sqlite": "statuses"}
    assert found["error"] == "learning data refused: learning-en.sqlite"
    assert "mastered" not in str(found) and "bad" not in str(found)
