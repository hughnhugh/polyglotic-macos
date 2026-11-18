"""Our curriculum's active set (polyglotic-hq 477, 473's option A), the
quiet view's chosen words and the store hooks (474), through `Vocabulary`
and a store in memory: the set fills past the known line with what the
learner's audio said first, then by the load's order; new words come in
only between sittings; a word met on 3 separate days retires; a word unmet
for a whole sitting gives up its place; the chosen words are kept as a
named set; every status change and line move is kept in order."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from tests.learning.fakes import Clock, MemoryLearningStore, facts, words_of

from polyglotic_desktop.core.learning.curriculum import (
    RETIRE_DAYS,
    Came,
    ChosenWords,
    chosen_from,
)
from polyglotic_desktop.core.learning.load import LoadRules
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import DEFAULT_CATEGORIES, CategoryId
from polyglotic_desktop.core.learning.vocabulary import (
    QUIET_SET,
    Changed,
    LineSource,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    WordStatus,
    WordStatusChanged,
)

ENTRIES = {f"w{n}": facts(f"w{n}", level=None, rank=n) for n in range(1, 81)}
ENTRIES["Bob"] = facts("Bob", level=None, rank=12, is_name=True)
BY_ID = {f.entry_id: f for f in ENTRIES.values()}
CURRICULUM = frozenset({ChosenWords.CURRICULUM})


def lookup(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return BY_ID.get(entry_id)


def placed(after: int, limit: int, scheme: str) -> Sequence[tuple[int, EntryFacts]]:
    found = sorted(
        (f.frequency_rank or 0, f.entry_id, f)
        for f in ENTRIES.values()
        if (f.frequency_rank or 0) > after
    )
    return [(rank, f) for rank, _, f in found[:limit]]


def eid(word: str) -> EntryId:
    return ENTRIES[word].entry_id


def melbourne(at: datetime) -> date:
    return (at + timedelta(hours=11)).date()


class Setup:
    def __init__(
        self,
        store: MemoryLearningStore | None = None,
        size: int = 5,
        chosen: frozenset[ChosenWords] = CURRICULUM,
        start: datetime = datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        heard_before: Sequence[str] = (),
    ) -> None:
        self.store = store or MemoryLearningStore()
        self.clock = Clock(start)
        self.vocab = Vocabulary(
            self.store, lookup, "en-frequency", self.clock, placed, melbourne
        )
        self.events: list[LearningEvent | VocabularyChanged] = []
        self.vocab.subscribe(self.events.append)
        if self.vocab.line is None:
            self.vocab.set_known_words(10)
        self.captions = 0
        for line in heard_before:
            self.hear(line)
        self.vocab.set_chosen(chosen, size)

    def hear(self, line: str, by_you: bool = False) -> None:
        self.captions += 1
        self.vocab.caption_finished(
            f"c{self.captions}", words_of(line, ENTRIES), by_you
        )

    def active(self) -> list[str]:
        return sorted(
            (w.entry_id.removeprefix("test:") for w in self.vocab.curriculum.members()),
            key=lambda name: int(name[1:]),
        )

    def later(self, **kwargs: float) -> None:
        self.clock.advance(**kwargs)


def test_the_set_fills_past_the_known_line_by_the_loads_order() -> None:
    setup = Setup()
    assert setup.active() == ["w11", "w12", "w13", "w14", "w15"]
    assert all(w.came is Came.ORDER for w in setup.vocab.curriculum.members())
    assert setup.vocab.chosen(ENTRIES["w11"]) and not setup.vocab.chosen(ENTRIES["w16"])


def test_the_start_turns_the_set_on_and_fills_it_once_the_window_is_up() -> None:
    """The app's start turns the set on without filling it (`fill=False`):
    filling looks through every word heard - 31 ms at 30,000 words met on
    the main PC, which the start's 400 ms had no room for (polyglotic-hq
    509). `fill_curriculum` fills it after the window, as a set turned on
    later fills at once; or the first sitting's first caption does."""
    setup = Setup(chosen=frozenset())
    setup.vocab.set_chosen(CURRICULUM, 5, fill=False)
    assert setup.vocab.curriculum.on and setup.active() == []
    told = len(setup.events)
    setup.vocab.fill_curriculum()
    assert setup.active() == ["w11", "w12", "w13", "w14", "w15"]
    assert VocabularyChanged(Changed.CURRICULUM) in setup.events[told:]
    setup.vocab.fill_curriculum()  # full: nothing more
    assert setup.active() == ["w11", "w12", "w13", "w14", "w15"]

    first = Setup(chosen=frozenset())
    first.vocab.set_chosen(CURRICULUM, 5, fill=False)
    first.hear("w40")
    assert first.active() == ["w11", "w12", "w13", "w14", "w15"]


def test_words_the_learners_audio_said_come_first_the_most_heard_first() -> None:
    # in 2 captions or more (polyglotic-hq 491): w50, said once, waits
    setup = Setup(heard_before=["w40 w30", "w30 w40", "w30", "w50", "Bob w5 Bob"])
    assert setup.active() == ["w11", "w12", "w13", "w30", "w40"]
    came = {w.entry_id: w.came for w in setup.vocab.curriculum.members()}
    assert came[eid("w30")] is Came.HEARD and came[eid("w11")] is Came.ORDER


def test_the_learners_own_mic_is_not_their_audio() -> None:
    setup = Setup(heard_before=["w40"])
    setup.hear("w11", by_you=True)
    assert setup.vocab.curriculum.word(eid("w11")).days_met == 0  # type: ignore[union-attr]


def test_a_word_retires_after_being_met_on_three_separate_days() -> None:
    setup = Setup()
    for _ in range(5):
        setup.hear("w11 w11")  # one day, however often
    assert setup.vocab.curriculum.word(eid("w11")).days_met == 1  # type: ignore[union-attr]
    for _ in range(RETIRE_DAYS - 1):
        setup.later(days=1)
        setup.hear("w11")
    assert "w11" not in setup.active()
    assert not setup.vocab.chosen(ENTRIES["w11"])
    for _ in range(3):  # and never comes back
        setup.later(days=1)
        setup.hear("w11 w12")
    assert "w11" not in setup.active()


def test_no_new_word_comes_in_the_middle_of_a_sitting() -> None:
    setup = Setup(size=3)  # w11 w12 w13
    setup.vocab.set_status(eid("w12"), WordStatus.KNOWN)  # leaves
    setup.hear("w11")  # a sitting begins: the set fills
    assert setup.active() == ["w11", "w13", "w14"]
    setup.vocab.set_status(eid("w13"), WordStatus.IGNORED)
    setup.later(minutes=20)
    setup.hear("w14")
    assert setup.active() == ["w11", "w14"]  # not mid-sitting
    setup.later(minutes=31)
    setup.hear("w11")  # the next sitting
    assert setup.active() == ["w11", "w14", "w15"]


def test_a_word_unmet_for_a_whole_sitting_gives_up_its_place() -> None:
    setup = Setup(size=3)  # w11 w12 w13
    setup.hear("w11 w12 w20")  # sitting 1: w13 unmet
    setup.later(hours=2)
    setup.hear("w20")  # sitting 2 begins: w13 goes, w20 (heard twice) comes
    assert setup.active() == ["w11", "w12", "w20"]
    setup.later(hours=2)
    setup.hear("w11")  # w20 had a sitting and was met in it: stays
    assert setup.active() == ["w11", "w12", "w20"]


def test_a_known_line_moved_past_its_words_empties_them() -> None:
    setup = Setup()
    setup.later(hours=1)  # between sittings
    setup.vocab.set_known_words(13)
    assert setup.active() == ["w14", "w15", "w16", "w17", "w18"]


def test_off_counts_nothing_and_chooses_nothing() -> None:
    setup = Setup(chosen=frozenset({ChosenWords.SAVED}))
    assert setup.active() == []
    assert not setup.vocab.curriculum.on
    setup.hear("w11")
    assert not setup.vocab.chosen(ENTRIES["w11"])


def test_the_chosen_words_are_the_union_of_whats_ticked() -> None:
    setup = Setup(size=2)
    setup.vocab.set_load_rules(LoadRules(size=3))  # w11 w12 w13
    setup.vocab.save(eid("w70"), *_saved_text())
    ids = {eid(f"w{n}") for n in (11, 12, 13, 70)}
    for chosen, blue in (
        (CURRICULUM, {"w11", "w12"}),
        (frozenset({ChosenWords.LOAD}), {"w11", "w12", "w13"}),
        (frozenset({ChosenWords.SAVED}), {"w70"}),
        (frozenset(ChosenWords) - {ChosenWords.EDGE}, {"w11", "w12", "w13", "w70"}),
    ):
        setup.vocab.set_chosen(chosen, 2)
        assert {e for e in ids if setup.vocab.chosen(BY_ID[e])} == {
            eid(w) for w in blue
        }


def test_the_chosen_words_are_kept_as_a_named_set_with_their_sources() -> None:
    setup = Setup(size=2)
    setup.vocab.save(eid("w11"), *_saved_text())
    setup.vocab.set_chosen(frozenset({ChosenWords.CURRICULUM, ChosenWords.SAVED}), 2)
    kept = {e: w.sources for (name, e), w in setup.store.set_words.items()}
    assert {name for name, _ in setup.store.set_words} == {QUIET_SET}
    assert kept == {
        eid("w11"): ("curriculum", "saved"),
        eid("w12"): ("curriculum",),
    }
    setup.vocab.set_chosen(frozenset({ChosenWords.SAVED}), 2)
    kept = {e: w.sources for (_, e), w in setup.store.set_words.items()}
    assert kept == {eid("w11"): ("saved",)}
    again = Vocabulary(setup.store, lookup, "en-frequency", setup.clock, placed)
    assert {w.entry_id for w in again.curriculum.members()} == {
        eid("w11"),
        eid("w12"),
    }  # the set comes back from the store


def test_every_status_change_is_kept_in_order_with_its_source() -> None:
    setup = Setup()
    setup.vocab.set_status(eid("w30"), WordStatus.LEARNING)
    setup.vocab.set_statuses([eid("w31"), eid("w5")], WordStatus.KNOWN)
    setup.vocab.apply_from_server(
        [WordStatusChanged(eid("w31"), WordStatus.NEW, setup.clock() + timedelta(1))],
        lambda _: None,
    )
    assert [
        (c.entry_id, c.before, c.after, c.source) for c in setup.store.status_history
    ] == [
        (eid("w30"), "new", "learning", "learner"),
        (eid("w31"), "new", "known", "learner"),
        (eid("w5"), "known", "known", "learner"),
        (eid("w31"), "known", "new", "server"),
    ]


def test_every_move_of_the_known_line_is_kept_with_how() -> None:
    setup = Setup()
    setup.vocab.set_known_words(40, LineSource.FIRST_KNOWN)
    setup.vocab.restore_line(None)
    assert [(c.midpoint, c.source) for c in setup.store.line_history] == [
        (10, "words"),
        (40, "first_known"),
        (None, "restored"),
    ]


def test_deleting_learning_data_deletes_the_set_the_histories_and_word_sets() -> None:
    setup = Setup(size=2)
    setup.vocab.set_status(eid("w30"), WordStatus.KNOWN)
    setup.vocab.delete_learning_data()
    store = setup.store
    assert not store.status_history and not store.line_history
    # chosen still: a new set, and its set of words, from nothing
    assert set(store.curriculum) == {eid("w11"), eid("w12")}
    assert setup.active() == ["w11", "w12"]
    assert {e for _, e in store.set_words} == {eid("w11"), eid("w12")}
    assert any(
        isinstance(e, VocabularyChanged) and e.what is Changed.CURRICULUM
        for e in setup.events
    )


def test_choices_kept_are_read_leniently() -> None:
    assert chosen_from(["load", "nonsense", 3, "saved"]) == {
        ChosenWords.LOAD,
        ChosenWords.SAVED,
    }
    assert chosen_from([]) == frozenset()


def _saved_text() -> tuple[str, str, str, str, CategoryId, LookupContext]:
    return ("w", "", "", "a word", DEFAULT_CATEGORIES[0].id, LookupContext(""))


def test_a_meeting_that_moves_no_word_tells_no_view() -> None:
    """The caption windows work their marks out again only when a word
    comes in or leaves - not at every meeting."""
    setup = Setup(start=datetime(2026, 11, 18, 12, 50, tzinfo=UTC))
    setup.hear("w11 w12 w13 w14 w15")  # a sitting begins: full already
    setup.events.clear()
    setup.later(minutes=20)  # midnight in Melbourne: the next day, same sitting
    setup.hear("w11 w12")
    assert setup.vocab.curriculum.word(eid("w11")).days_met == 2  # type: ignore[union-attr]
    assert not any(
        isinstance(e, VocabularyChanged) and e.what is Changed.CURRICULUM
        for e in setup.events
    )
