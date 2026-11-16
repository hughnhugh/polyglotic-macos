"""The app's own wiring gives the learning load its words (polyglotic-hq
324): `main.learner_tools` hands the vocabulary the dictionary's words in
frequency order, and the load's words are kept in the learning data file
and deleted with it."""

from pathlib import Path

from PySide6.QtWidgets import QApplication
from tests.tools.test_learner_start import ranked_dictionary

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.load import LoadRules, Stage


def test_the_load_fills_from_the_learners_dictionary_and_is_kept(
    qapp: QApplication, tmp_path: Path
) -> None:
    folder = tmp_path / "dictionaries"
    folder.mkdir()
    ranked_dictionary(folder / "cedict.sqlite", 300)
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    vocabulary = tools.vocabulary
    assert vocabulary.load.members() == []  # off until the Lab turns it on
    vocabulary.set_known_words(100)
    vocabulary.set_load_rules(LoadRules(size=50))
    ranks = sorted(w.place or 0 for w in vocabulary.load.members())
    assert ranks == list(range(101, 151))
    first = vocabulary.load.members()[0].entry_id
    word = chr(0x4E00 + 101)
    vocabulary.caption_finished("c1", tools.words_in(word * 3), by_you=False)
    assert vocabulary.load.stage(first) is Stage.ORANGE
    store.close()

    tools, store = main.learner_tools(folder, False, data)
    tools.vocabulary.set_load_rules(LoadRules(size=50))
    assert tools.vocabulary.load.stage(first) is Stage.ORANGE
    assert len(tools.vocabulary.load.members()) == 50
    tools.vocabulary.set_load_rules(None)
    tools.vocabulary.delete_learning_data()
    store.close()

    tools, store = main.learner_tools(folder, False, data)
    tools.vocabulary.set_load_rules(None)
    assert tools.vocabulary.load.word(first) is None
    store.close()


def test_the_loads_words_are_read_off_the_interface_thread(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Turning the load on, or making it larger, reads the dictionary's
    words in order (50-100 ms on the real packs): on a thread of its own,
    the rules set when it is back - and nothing the load then asks for is
    read on the interface thread."""
    import threading

    folder = tmp_path / "dictionaries"
    folder.mkdir()
    ranked_dictionary(folder / "cedict.sqlite", 1500)
    tools, store = main.learner_tools(folder, False, tmp_path / "data")
    try:
        ahead = tools._load_words
        assert ahead is not None
        reads: list[str] = []
        inner = ahead._read

        def read(after: int, limit: int, scheme: str) -> object:
            reads.append(threading.current_thread().name)
            return inner(after, limit, scheme)

        ahead._read = read  # type: ignore[assignment]
        vocabulary = tools.vocabulary
        vocabulary.set_known_words(100)
        tools.set_load_rules(LoadRules(size=50))
        assert vocabulary.load.rules is None  # being read: not on this thread
        tools.set_load_rules(LoadRules(size=60))  # asked again meanwhile
        tools.load_rules_settled()
        assert vocabulary.load.rules == LoadRules(size=60)  # the last asked for
        assert len(vocabulary.load.members()) == 60
        assert vocabulary.load.waiting(20)  # Learning's "next to enter"
        tools.add_next_to_load(50)
        assert reads and set(reads) == {"load"}  # never this thread
        tools.set_load_rules(None)  # off: at once
        assert vocabulary.load.rules is None
        tools.set_load_rules(LoadRules(size=50))  # on again: what it asks is held
        assert vocabulary.load.rules == LoadRules(size=50)
    finally:
        store.close()


def test_words_kept_once_read_are_answered_as_the_dictionary_would() -> None:
    from polyglotic_desktop.core.shared import EntryFacts, EntryId
    from polyglotic_desktop.ui.learning import PlacedAhead

    places = [1, 2, 2, 2, 3, 5, 5, 8, 9, 9, 12]
    words = [
        (place, EntryFacts(EntryId(f"w{n}"), None, place, False))
        for n, place in enumerate(places)
    ]
    asked: list[tuple[int, int]] = []

    def read(after: int, limit: int, scheme: str) -> list[tuple[int, EntryFacts]]:
        """Past `after`, `limit` words and the rest of the last one's place."""
        asked.append((after, limit))
        found = [w for w in words if w[0] > after]
        cut = found[limit - 1][0] if len(found) >= limit else 10**9
        return [w for w in found if w[0] <= cut]

    ahead = PlacedAhead(read)
    ahead.BATCH = 2
    assert [p for p, _ in ahead(0, 2, "s")] == [1, 2, 2, 2]  # a place is whole
    assert [p for p, _ in ahead(2, 1, "s")] == [3]
    assert [p for p, _ in ahead(1, 4, "s")] == [2, 2, 2, 3]  # from what is kept
    assert ahead.holds(1, 4, "s") and not ahead.holds(3, 9, "s")
    assert [p for p, _ in ahead(3, 20, "s")] == [5, 5, 8, 9, 9, 12]  # to the end
    count = len(asked)
    assert [p for p, _ in ahead(5, 3, "s")] == [8, 9, 9]
    assert ahead(12, 5, "s") == [] and len(asked) == count  # all read: no more asked
    # asked from before its run, or in another scheme: read again from there
    assert not ahead.holds(0, 1, "other")
    assert [p for p, _ in ahead(8, 2, "other")] == [9, 9]
    assert [p for p, _ in ahead(0, 1, "other")] == [1]
    # every word once, in order, however it is asked for
    again = PlacedAhead(read)
    again.BATCH = 3
    seen: list[int] = []
    while batch := again(seen[-1] if seen else 0, 2, "s"):
        seen += [p for p, _ in batch]
    assert seen == places
