"""The learning load (polyglotic-hq 324), through `Vocabulary` and a store
in memory: it fills past the known line, words move a stage for every few
meetings as the counting says, a full colour holds a word, the check
graduates or sends back, a graduated word is replaced, and the size and
the hand feed it."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from tests.learning.fakes import Clock, MemoryLearningStore, facts, words_of

from polyglotic_desktop.core.learning.load import (
    NOT_YET,
    Counting,
    LoadRules,
    Stage,
    Standing,
)
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    Level,
    WordStatus,
    WordStatusChanged,
)

# A made-up dictionary of 60 words, w1 the commonest, and a name.
ENTRIES = {f"w{n}": facts(f"w{n}", level=None, rank=n) for n in range(1, 61)}
ENTRIES["Bob"] = facts("Bob", level=None, rank=12, is_name=True)
BY_ID = {f.entry_id: f for f in ENTRIES.values()}


TEN = LoadRules(size=10)


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
    """The day in Melbourne in November (UTC+11)."""
    return (at + timedelta(hours=11)).date()


class Setup:
    def __init__(
        self,
        store: MemoryLearningStore | None = None,
        known: int = 10,
        rules: LoadRules | None = TEN,
        start: datetime = datetime(2026, 11, 4, 9, 0, tzinfo=UTC),
    ) -> None:
        self.store = store or MemoryLearningStore()
        self.clock = Clock(start)
        self.vocab = Vocabulary(
            self.store, lookup, "en-frequency", self.clock, placed, melbourne
        )
        self.events: list[LearningEvent | VocabularyChanged] = []
        self.vocab.subscribe(self.events.append)
        if self.vocab.line is None:
            self.vocab.set_known_words(known)
        self.vocab.set_load_rules(rules)
        self.captions = 0

    def hear(self, line: str, by_you: bool = False, caption_id: str = "") -> str:
        self.captions += 1
        caption_id = caption_id or f"c{self.captions}"
        self.vocab.caption_finished(caption_id, words_of(line, ENTRIES), by_you)
        return caption_id

    def stage(self, word: str) -> Stage | None:
        return self.vocab.load.stage(eid(word))

    def meetings(self, word: str) -> int:
        kept = self.vocab.load.word(eid(word))
        assert kept is not None
        return kept.meetings

    def in_load(self) -> list[str]:
        return sorted(
            (w.entry_id.removeprefix("test:") for w in self.vocab.load.members()),
            key=lambda name: int(name[1:]),
        )

    def load_changes(self) -> int:
        found = sum(
            1
            for e in self.events
            if isinstance(e, VocabularyChanged) and e.what is Changed.LOAD
        )
        self.events.clear()
        return found


def names(first: int, last: int) -> list[str]:
    return [f"w{n}" for n in range(first, last + 1)]


# -- the load ------------------------------------------------------------------


def test_the_load_is_the_next_words_past_the_known_line_in_red() -> None:
    s = Setup()
    # the name at rank 12 is passed over
    assert s.in_load() == names(11, 20)
    assert {s.stage(w) for w in s.in_load()} == {Stage.RED}
    assert s.stage("w5") is None  # known
    assert s.stage("w30") is None  # past the load
    assert s.vocab.load.stage(eid("Bob")) is None


def test_off_there_is_no_load_and_nothing_is_counted() -> None:
    s = Setup(rules=None)
    assert s.in_load() == []
    s.hear("w11 w11 w11")
    assert s.store.load_words == {}
    assert s.stage("w11") is None
    assert s.load_changes() == 0


def test_turned_off_the_load_is_kept_and_back_as_it_was() -> None:
    s = Setup()
    s.hear("w11 w11 w11")
    s.vocab.set_load_rules(None)
    assert s.stage("w11") is None
    s.hear("w11 w11 w11")  # not counted while off
    s.vocab.set_load_rules(LoadRules(size=10))
    assert s.stage("w11") is Stage.ORANGE
    assert s.meetings("w11") == 0


def test_words_set_known_or_ignored_by_hand_are_not_in_it() -> None:
    store = MemoryLearningStore()
    first = Setup(store, rules=None)
    first.vocab.set_status(eid("w11"), WordStatus.KNOWN)
    first.vocab.set_status(eid("w12"), WordStatus.IGNORED)
    first.vocab.set_status(eid("w13"), WordStatus.LEARNING)  # in the deck: in
    first.vocab.set_load_rules(LoadRules(size=10))
    assert first.in_load() == names(13, 22)


def test_a_dictionary_without_ranks_has_no_load() -> None:
    store = MemoryLearningStore()
    vocab = Vocabulary(store, lookup, "en-frequency", Clock())
    vocab.set_load_rules(LoadRules(size=10))
    assert vocab.load.members() == []
    assert vocab.load.waiting(5) == []


def test_the_load_survives_a_restart() -> None:
    store = MemoryLearningStore()
    first = Setup(store)
    first.hear("w11 w11 w11 w12")
    again = Setup(store)
    assert again.in_load() == names(11, 20)
    assert again.stage("w11") is Stage.ORANGE
    assert again.meetings("w12") == 1


# -- meetings and stages ---------------------------------------------------------


def test_every_three_meetings_move_a_word_a_stage_to_ready_to_check() -> None:
    s = Setup()
    seen = []
    for _ in range(12):
        s.hear("w11")
        seen.append(s.stage("w11"))
    assert seen == [
        *[Stage.RED] * 2,
        *[Stage.ORANGE] * 3,
        *[Stage.YELLOW] * 3,
        *[Stage.GREEN] * 3,
        Stage.READY,
    ]
    s.hear("w11")  # ready: meetings no longer count
    assert s.meetings("w11") == 0


def test_every_time_heard_counts_each_time_in_a_caption() -> None:
    s = Setup()
    s.hear("w11 w11 w11 w11 w12")
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.ORANGE, 1)
    assert (s.stage("w12"), s.meetings("w12")) == (Stage.RED, 1)


def test_a_word_heard_many_times_in_a_caption_moves_more_than_one_stage() -> None:
    s = Setup()
    s.hear(" ".join(["w11"] * 7))
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.YELLOW, 1)


def test_once_a_caption_counts_a_caption_once() -> None:
    s = Setup(rules=LoadRules(size=10, counting=Counting.CAPTION))
    s.hear("w11 w11 w11 w11")
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.RED, 1)
    s.hear("w11")
    s.hear("w11 w11")
    assert s.stage("w11") is Stage.ORANGE


def test_once_a_session_counts_again_after_half_an_hour_of_quiet() -> None:
    s = Setup(rules=LoadRules(size=10, counting=Counting.SESSION))
    s.hear("w11 w11")
    s.clock.advance(minutes=5)
    s.hear("w11")
    assert s.meetings("w11") == 1
    s.clock.advance(minutes=29)
    s.hear("w12")  # captions kept coming: the same session
    s.clock.advance(minutes=29)
    s.hear("w11")
    assert s.meetings("w11") == 1
    s.clock.advance(minutes=31)
    s.hear("w11")
    assert s.meetings("w11") == 2


def test_once_a_day_is_the_learners_day_not_utcs() -> None:
    # 12:30 UTC is 23:30 in Melbourne; 13:30 UTC is 00:30 the next day there
    start = datetime(2026, 11, 4, 12, 30, tzinfo=UTC)
    s = Setup(rules=LoadRules(size=10, counting=Counting.DAY), start=start)
    s.hear("w11")
    s.clock.advance(minutes=20)
    s.hear("w11 w11")
    assert s.meetings("w11") == 1
    s.clock.advance(minutes=40)  # 13:30 UTC: the same UTC day, Melbourne's next
    s.hear("w11")
    assert s.meetings("w11") == 2
    s.clock.advance(hours=11)  # 00:30 UTC: UTC's next day, Melbourne's same
    s.hear("w11")
    assert s.meetings("w11") == 2


def test_once_a_day_holds_across_a_restart() -> None:
    store = MemoryLearningStore()
    rules = LoadRules(size=10, counting=Counting.DAY)
    first = Setup(store, rules=rules)
    first.hear("w11")
    again = Setup(store, rules=rules)
    again.clock.advance(hours=1)
    again.hear("w11")
    assert again.meetings("w11") == 1
    again.clock.advance(days=1)
    again.hear("w11")
    assert again.meetings("w11") == 2


def test_the_users_own_speech_and_names_are_not_meetings() -> None:
    s = Setup()
    s.events.clear()
    s.hear("w11 w11 w11 Bob", by_you=True)
    assert s.meetings("w11") == 0
    assert s.load_changes() == 0


def test_a_joined_caption_counts_only_the_difference_and_a_withdrawal_takes_back() -> (
    None
):
    s = Setup()
    caption = s.hear("w11 w12")
    s.hear("w11 w12 w12 w13", caption_id=caption)  # a join: the same caption
    assert [s.meetings(w) for w in ("w11", "w12", "w13")] == [1, 2, 1]
    s.vocab.caption_withdrawn(caption)
    assert [s.meetings(w) for w in ("w11", "w12", "w13")] == [0, 0, 0]


def test_a_withdrawal_never_moves_a_word_back_a_stage() -> None:
    s = Setup()
    s.hear("w11 w11")
    caption = s.hear("w11")
    assert s.stage("w11") is Stage.ORANGE
    s.vocab.caption_withdrawn(caption)
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.ORANGE, 0)


def test_what_was_heard_before_a_word_entered_does_not_count() -> None:
    s = Setup(rules=None)
    for _ in range(5):
        s.hear("w11")
    assert s.vocab.exposures(eid("w11")).heard == 5
    s.vocab.set_load_rules(LoadRules(size=10))
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.RED, 0)


def test_a_change_of_step_moves_the_words_that_now_have_their_meetings() -> None:
    s = Setup(rules=LoadRules(size=10, step=5))
    s.hear("w11 w11 w11")
    assert s.stage("w11") is Stage.RED
    s.vocab.set_load_rules(LoadRules(size=10, step=3))
    assert s.stage("w11") is Stage.ORANGE


# -- at most so many in a colour -----------------------------------------------


def test_a_full_colour_holds_a_word_until_one_moves_on() -> None:
    s = Setup(rules=LoadRules(size=10, stage_limit=1))
    s.hear("w11 w11 w11")
    s.hear("w12 w12 w12 w12")
    s.hear("w13 w13 w13")
    assert s.stage("w11") is Stage.ORANGE
    # orange is full: w12 and w13 have had their meetings and wait in red
    assert (s.stage("w12"), s.meetings("w12")) == (Stage.RED, 4)
    assert s.stage("w13") is Stage.RED
    kept = s.vocab.load.word(eid("w12"))
    assert kept is not None and kept.needs(3) == 0
    s.hear("w11 w11 w11")  # w11 moves to yellow: the most-met word follows
    assert s.stage("w11") is Stage.YELLOW
    assert (s.stage("w12"), s.meetings("w12")) == (Stage.ORANGE, 1)
    assert s.stage("w13") is Stage.RED


def test_red_and_ready_to_check_have_no_limit() -> None:
    s = Setup(rules=LoadRules(size=10, step=1, stage_limit=1))
    assert len([w for w in s.in_load() if s.stage(w) is Stage.RED]) == 10
    for _ in range(4):
        s.hear("w11")
    for _ in range(8):
        s.hear("w12")
    assert s.stage("w11") is Stage.READY
    assert s.stage("w12") is Stage.READY


# -- the check, and rolling ---------------------------------------------------------


def ready(s: Setup, word: str) -> None:
    for _ in range(12):
        s.hear(word)
    assert s.stage(word) is Stage.READY


def test_i_know_this_graduates_the_word_and_the_next_takes_its_place() -> None:
    s = Setup()
    ready(s, "w11")
    s.events.clear()
    s.vocab.check_word(eid("w11"), knows=True)
    assert s.in_load() == names(12, 21)
    assert s.stage("w21") is Stage.RED
    record = s.vocab.status_of_entry(eid("w11"))
    assert record.status is WordStatus.KNOWN and record.is_learners_own
    # it syncs as any status the learner set: an entry ID and a time
    sent = [e for e in s.events if not isinstance(e, VocabularyChanged)]
    assert sent == [WordStatusChanged(eid("w11"), WordStatus.KNOWN, s.clock.now)]
    kept = s.vocab.load.word(eid("w11"))
    assert kept is not None and kept.standing is Standing.GRADUATED
    assert [w.entry_id for w in s.vocab.load.graduated()] == [eid("w11")]
    progress = s.vocab.load.progress(s.clock.now)
    assert (progress.words, progress.graduated_week, progress.graduated) == (10, 1, 1)


def test_not_yet_sends_the_word_back_to_yellow() -> None:
    s = Setup()
    ready(s, "w11")
    s.vocab.check_word(eid("w11"), knows=False)
    assert (s.stage("w11"), s.meetings("w11")) == (NOT_YET, 0)
    assert s.in_load() == names(11, 20)
    assert s.vocab.status_of_entry(eid("w11")).status is WordStatus.NEW


def test_only_a_word_ready_to_check_can_be_checked() -> None:
    s = Setup()
    s.hear("w11")
    s.vocab.check_word(eid("w11"), knows=True)
    assert s.stage("w11") is Stage.RED
    assert s.vocab.status_of_entry(eid("w11")).status is WordStatus.NEW


def test_graduated_this_week_counts_seven_days() -> None:
    s = Setup()
    ready(s, "w11")
    s.vocab.check_word(eid("w11"), knows=True)
    s.clock.advance(days=6)
    assert s.vocab.load.progress(s.clock.now).graduated_week == 1
    s.clock.advance(days=2)
    progress = s.vocab.load.progress(s.clock.now)
    assert (progress.graduated_week, progress.graduated) == (0, 1)


def test_a_word_set_known_anywhere_graduates_and_ignored_leaves() -> None:
    s = Setup()
    s.hear("w11")
    s.vocab.set_status(eid("w11"), WordStatus.KNOWN)
    s.vocab.set_status(eid("w12"), WordStatus.IGNORED)
    assert s.in_load() == names(13, 22)
    kept = s.vocab.load.word(eid("w11"))
    assert kept is not None and kept.standing is Standing.GRADUATED
    assert s.vocab.load.word(eid("w12")) is None
    assert eid("w12") not in s.store.load_words


def test_a_status_set_on_another_pc_graduates_the_word_here() -> None:
    s = Setup()
    s.events.clear()
    at = s.clock.now + timedelta(minutes=1)
    s.vocab.apply_from_server(
        [WordStatusChanged(eid("w11"), WordStatus.KNOWN, at)], lambda _: None
    )
    assert s.in_load() == names(12, 21)
    assert s.load_changes() == 1


def test_a_graduated_word_set_new_again_comes_back_in_red() -> None:
    s = Setup()
    ready(s, "w11")
    s.vocab.check_word(eid("w11"), knows=True)
    s.vocab.set_status(eid("w11"), WordStatus.NEW)
    # the load is full: it waits, the next to come in
    assert [f.entry_id for _, f in s.vocab.load.waiting(1)] == [eid("w11")]
    s.vocab.set_aside_from_load(eid("w21"))
    assert s.stage("w11") is Stage.RED


# -- by hand, and the size ------------------------------------------------------------


def test_the_next_words_wait_in_frequency_order() -> None:
    s = Setup()
    waiting = s.vocab.load.waiting(3)
    assert [(rank, f.entry_id) for rank, f in waiting] == [
        (21, eid("w21")),
        (22, eid("w22")),
        (23, eid("w23")),
    ]


def test_adding_the_next_words_raises_the_size_by_them() -> None:
    s = Setup()
    s.vocab.add_next_to_load(5)
    assert s.in_load() == names(11, 25)
    assert s.vocab.load.rules == LoadRules(size=15)


def test_one_word_added_by_hand_raises_the_size_by_one() -> None:
    s = Setup()
    assert s.vocab.add_to_load(eid("w40"))
    assert s.in_load() == [*names(11, 20), "w40"]
    assert s.vocab.load.rules == LoadRules(size=11)
    assert not s.vocab.add_to_load(eid("w40"))  # in it already
    assert not s.vocab.add_to_load(eid("w3"))  # known
    assert not s.vocab.add_to_load(eid("Bob"))  # a name
    assert s.vocab.load.rules == LoadRules(size=11)


def test_not_now_takes_a_word_out_until_it_is_added_by_hand() -> None:
    s = Setup()
    s.hear("w11 w11")
    s.vocab.set_aside_from_load(eid("w11"))
    assert s.in_load() == names(12, 21)
    s.vocab.add_next_to_load(3)
    assert "w11" not in s.in_load()
    assert s.vocab.add_to_load(eid("w11"))
    assert (s.stage("w11"), s.meetings("w11")) == (Stage.RED, 0)


def test_a_raised_size_brings_the_next_words_in_at_once() -> None:
    s = Setup()
    s.vocab.set_load_rules(LoadRules(size=14))
    assert s.in_load() == names(11, 24)


def test_a_lowered_size_sends_the_far_reds_to_wait_with_their_meetings() -> None:
    s = Setup()
    s.hear("w11 w11 w11")  # orange
    s.hear("w20 w20")  # red, 2 meetings
    s.hear("w19")  # red, 1 meeting
    s.vocab.add_to_load(eid("w40"))  # by hand: the last to leave
    s.vocab.set_load_rules(LoadRules(size=5))
    # the reds never met leave first, the rarest first
    assert s.in_load() == ["w11", "w12", "w19", "w20", "w40"]
    s.vocab.set_load_rules(LoadRules(size=3))
    # then the red with the fewest meetings
    assert s.in_load() == ["w11", "w20", "w40"]
    kept = s.vocab.load.word(eid("w19"))
    assert kept is not None
    assert (kept.standing, kept.meetings) == (Standing.WAITING, 1)
    assert s.vocab.load.word(eid("w18")) is None  # never met: nothing to keep
    s.vocab.set_load_rules(LoadRules(size=11))
    assert s.in_load() == [*names(11, 20), "w40"]
    assert s.meetings("w19") == 1  # back with its meeting


# -- the known line moves -----------------------------------------------------------


def test_a_raised_line_takes_the_words_it_covers_out_and_fills_past_it() -> None:
    s = Setup()
    s.hear("w11 w11 w11")
    s.vocab.set_known_words(15)
    assert s.in_load() == names(16, 25)
    kept = s.vocab.load.word(eid("w11"))
    assert kept is not None and kept.standing is Standing.WAITING
    s.vocab.set_known_words(10)  # back: w11 returns as it was
    assert s.in_load() == names(11, 20)
    assert s.stage("w11") is Stage.ORANGE


def test_a_lowered_line_brings_commoner_words_in_place_of_those_never_met() -> None:
    s = Setup(known=20)
    s.hear("w30")
    s.vocab.set_known_words(10)
    assert s.in_load() == [*names(11, 19), "w30"]


def test_a_line_kept_as_a_level_fills_past_the_words_it_knows() -> None:
    store = MemoryLearningStore()
    vocab = Vocabulary(store, lookup, "en-frequency", Clock(), placed)
    # every made-up word is beyond the scheme's levels: none known, the
    # load starts at the commonest
    vocab.set_level(Level("hsk-2025", 2))
    vocab.set_load_rules(LoadRules(size=3))
    assert sorted(w.place or 0 for w in vocab.load.members()) == [1, 2, 3]


# -- deleted, merged ----------------------------------------------------------------


def test_deleting_the_learning_data_deletes_the_load_and_starts_a_new_one() -> None:
    s = Setup()
    ready(s, "w11")
    s.vocab.check_word(eid("w11"), knows=True)
    s.hear("w12 w12 w12")
    s.vocab.delete_learning_data()
    assert s.in_load() == names(11, 20)
    assert {s.stage(w) for w in s.in_load()} == {Stage.RED}
    assert s.vocab.load.graduated() == []
    assert sorted(s.store.load_words) == sorted(eid(w) for w in names(11, 20))
    s.vocab.set_load_rules(None)
    s.vocab.delete_learning_data()
    assert s.store.load_words == {}


def test_views_hear_of_the_load_only_when_it_changes() -> None:
    s = Setup()
    s.events.clear()
    s.hear("w5 w30")  # known, and past the load
    assert s.load_changes() == 0
    s.hear("w11")
    assert s.load_changes() == 1
    s.vocab.set_load_rules(LoadRules(size=10))  # the same rules
    assert s.load_changes() == 0


def test_a_load_change_names_the_words_whose_stage_changed() -> None:
    """Captions repaint only those: a meeting that moves no word names
    none; the load turned on or off may have changed every word's."""
    s = Setup()

    def touched() -> list[frozenset[EntryId] | None]:
        found = [
            e.entries
            for e in s.events
            if isinstance(e, VocabularyChanged) and e.what is Changed.LOAD
        ]
        s.events.clear()
        return found

    assert touched() == [None]  # turned on
    s.hear("w11 w12")
    assert touched() == [frozenset()]
    s.hear("w11 w11")
    assert touched() == [frozenset({eid("w11")})]
    ready(s, "w12")
    s.events.clear()
    s.vocab.check_word(eid("w12"), knows=True)  # w12 out, w21 in
    assert touched() == [frozenset({eid("w12"), eid("w21")})]
    s.vocab.set_load_rules(None)
    assert touched() == [None]
