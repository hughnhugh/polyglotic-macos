"""The conversation's words in our curriculum's set (polyglotic-hq 491,
decision 0227), through `Vocabulary` and a store in memory: they enter
mid-sitting only at a source's update, stretch words first, up to the
blue words a caption should show; never from the learner's own mic; they
take the place of a word never met, never a met one; look-alikes wait; a
word no longer said rests and comes back with its days met; the fixed
heard-first fill never takes fillers, words heard once or past the
learning window; why each came is kept; a conversation's word retires
when the learner knows it, not on its third day met (496)."""

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tests.learning.fakes import Clock, MemoryLearningStore, facts, words_of

from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.core.learning.curriculum import (
    MOST_NEW,
    RETIRE_DAYS,
    TARGET_RATE,
    Came,
    ChosenWords,
    Curriculum,
    CurriculumStore,
    Standing,
)
from polyglotic_desktop.core.learning.theme import EVERY, STRETCH_IN, WINDOW
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ports.learning import LearningStore

ENTRIES: dict[str, EntryFacts] = {
    f"w{n}": facts(f"w{n}", level=None, rank=n) for n in range(1, 81)
}
"""w1-w10 are known (the line is at 10); w11 on come by the load's order."""
for name, rank in [("remote", 600), ("remove", 610), ("battery", 2413)]:
    ENTRIES[name] = facts(name, level=None, rank=rank)
TOPIC = ["apple", "grape", "lemon", "mango", "olive", "peach", "melon", "cherry"]
"""Words in the learning window, no two of them look-alikes."""
for n, name in enumerate(TOPIC, 1):
    ENTRIES[name] = facts(name, level=None, rank=500 + n)
ENTRIES["rubber"] = facts("rubber", level=None, rank=4735)  # past the window
ENTRIES["um"] = EntryFacts(EntryId("test:um"), None, 5615, False, is_filler=True)
ENTRIES["Bob"] = facts("Bob", level=None, rank=300, is_name=True)
BY_ID = {f.entry_id: f for f in ENTRIES.values()}
START = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
TALK = "w1 w2 w3 w4"
"""What every caption says besides: words the learner knows."""


def lookup(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return BY_ID.get(entry_id)


def placed(after: int, limit: int, scheme: str) -> Sequence[tuple[int, EntryFacts]]:
    found = sorted(
        (f.frequency_rank or 0, f.entry_id, f)
        for f in ENTRIES.values()
        if (f.frequency_rank or 0) > after and f.entry_id.startswith("test:w")
    )
    return [(rank, f) for rank, _, f in found[:limit]]


def melbourne(at: datetime) -> date:
    return (at + timedelta(hours=11)).date()


class Setup:
    def __init__(
        self,
        size: int = 5,
        store: LearningStore | None = None,
        heard_before: Sequence[str] = (),
    ) -> None:
        self.store = store or MemoryLearningStore()
        self.clock = Clock(START)
        self.vocab = Vocabulary(
            self.store, lookup, "en-frequency", self.clock, placed, melbourne
        )
        if self.vocab.line is None:
            self.vocab.set_known_words(10)
        self.captions = 0
        for line in heard_before:
            self.hear(line)
        self.vocab.set_chosen(frozenset({ChosenWords.CURRICULUM}), size)

    def hear(self, line: str, source: str = "video", by_you: bool = False) -> None:
        self.captions += 1
        text = f"{line} {TALK}".strip()
        self.vocab.caption_finished(
            f"c{self.captions}",
            words_of(text, ENTRIES),
            by_you,
            source,
            [t for t in text.split(" ") if t in ENTRIES],
        )

    def talk(self, lines: Sequence[str], every: float = 15, **kw: str | bool) -> None:
        """Captions `every` seconds apart, the clock moved on before each."""
        for line in lines:
            self.clock.advance(seconds=every)
            self.hear(line, **kw)  # type: ignore[arg-type]

    def active(self) -> set[str]:
        return {
            w.entry_id.removeprefix("test:") for w in self.vocab.curriculum.members()
        }

    def came(self, name: str) -> Came | None:
        word = self.vocab.curriculum.word(ENTRIES[name].entry_id)
        return word.came if word else None


def until_update(setup: Setup, line: str = "") -> None:
    """Captions every 15 s up to a source's update (its first: `EVERY`
    after its talk began)."""
    setup.talk([line] * round(EVERY.total_seconds() / 15))


def test_conversation_words_come_in_at_an_update_and_not_before() -> None:
    setup = Setup()  # w11-w15, by the load's order, none met
    setup.hear("apple")
    setup.talk(["apple", "apple"])  # in 3 captions, 30 s in
    assert "apple" not in setup.active()
    until_update(setup)
    assert "apple" in setup.active() and setup.came("apple") is Came.THEME
    # it took the place of the newest word never met: w15
    assert setup.active() == {"w11", "w12", "w13", "w14", "apple"}


def test_the_learners_own_mic_never_counts() -> None:
    setup = Setup()
    setup.hear("apple grape", by_you=True)
    setup.talk(["apple grape"] * 10, by_you=True)
    assert setup.active() == {"w11", "w12", "w13", "w14", "w15"}
    assert setup.vocab.curriculum.themes.window("video") is None


def test_a_stretch_word_comes_first() -> None:
    setup = Setup()
    setup.hear("")
    setup.talk(["rubber apple"] * (STRETCH_IN - 1) + ["rubber"])
    until_update(setup)
    assert setup.came("rubber") is Came.STRETCH
    assert setup.came("apple") is Came.THEME


def test_a_met_word_never_gives_up_its_place() -> None:
    setup = Setup(size=2)  # w11 w12
    setup.hear("w11 w12 apple")
    setup.talk(["w11 w12 apple"])
    until_update(setup, "w11 w12")
    assert setup.active() == {"w11", "w12"}  # both met: apple waits


def test_words_enter_up_to_the_blue_words_a_caption_should_show() -> None:
    setup = Setup(size=20)
    # each topic word in 6 of the window's captions: a rate of 6/n each
    lines = [f"{TOPIC[n % 8]} {TOPIC[(n + 4) % 8]}" for n in range(24)]
    setup.hear("")
    setup.talk(lines, every=EVERY.total_seconds() / len(lines))
    window = setup.vocab.curriculum.themes.window("video")
    assert window is not None
    rate = 6 / window.captions
    entered = [name for name in TOPIC if setup.came(name) is Came.THEME]
    expected = min(MOST_NEW, math.ceil(TARGET_RATE / rate - 1e-9))
    assert expected < len(TOPIC)  # the target binds, not the words said
    assert len(entered) == expected


def test_a_look_alike_of_a_lit_word_waits() -> None:
    setup = Setup(size=20)
    setup.hear("")
    setup.talk(["remote remove"] * 3)
    until_update(setup)
    lit = {"remote", "remove"} & setup.active()
    assert len(lit) == 1


def test_a_word_no_longer_said_rests_and_comes_back_with_its_days() -> None:
    setup = Setup()
    setup.hear("")
    setup.talk(["apple"] * 3)
    until_update(setup, "apple")
    word = setup.vocab.curriculum.word(ENTRIES["apple"].entry_id)
    assert word is not None and word.active and word.days_met == 1
    # the talk moves on: apple isn't said for the window's length
    setup.talk([""] * round((WINDOW + EVERY).total_seconds() / 15))
    word = setup.vocab.curriculum.word(ENTRIES["apple"].entry_id)
    assert word is not None and word.standing is Standing.RESTING
    assert word.days_met == 1 and "apple" not in setup.active()
    setup.clock.advance(days=1)  # another day
    setup.talk(["apple"] * 3)
    until_update(setup, "apple")
    word = setup.vocab.curriculum.word(ENTRIES["apple"].entry_id)
    assert word is not None and word.active and word.days_met == 2


def test_the_fixed_heard_first_never_takes_fillers_once_heard_or_past_the_window() -> (
    None
):
    setup = Setup(
        heard_before=[
            "um w40",
            "um w40 w60",
            "um rubber",
            "rubber",
            "rubber Bob",
            "Bob",
        ]
    )
    assert setup.came("w40") is Came.HEARD  # in 2 captions, in the window
    assert setup.came("um") is None  # a filler
    assert setup.came("rubber") is None  # past the window
    assert setup.came("Bob") is None  # a name
    assert setup.came("w60") is None  # heard once


def test_why_a_word_came_and_resting_come_back_from_the_store(tmp_path: Path) -> None:
    store = SqliteLearningStore(tmp_path / "learning.sqlite")
    setup = Setup(store=store)
    setup.hear("")
    setup.talk(["rubber apple"] * STRETCH_IN + ["grape", "grape"])
    until_update(setup, "grape")
    setup.talk(["grape"] * round((WINDOW + EVERY).total_seconds() / 15))
    before = {w.entry_id: w for w in setup.vocab.curriculum.retired()}
    words = {
        n: setup.vocab.curriculum.word(ENTRIES[n].entry_id) for n in ("rubber", "grape")
    }
    assert words["rubber"] is not None and words["rubber"].standing is Standing.RESTING
    assert words["grape"] is not None and words["grape"].came is Came.THEME
    store.close()
    again = Setup(store=SqliteLearningStore(tmp_path / "learning.sqlite"))
    for name, word in words.items():
        assert word is not None
        back = again.vocab.curriculum.word(ENTRIES[name].entry_id)
        assert back is not None
        assert (back.came, back.standing, back.days_met) == (
            word.came,
            word.standing,
            word.days_met,
        )
    assert before == {w.entry_id: w for w in again.vocab.curriculum.retired()}


def test_the_theme_is_named_by_what_is_said_now() -> None:
    setup = Setup()
    setup.hear("")
    setup.talk(["rubber battery um"] * 3 + ["rubber remote"] * 2)
    named = [s.form for s in setup.vocab.curriculum.theme_name("video")]
    assert named[:2] == ["rubber", "battery"]
    assert "um" not in named
    assert setup.vocab.curriculum.theme_name("call") == []


def test_a_withdrawn_caption_leaves_the_window() -> None:
    setup = Setup()
    setup.hear("apple")
    setup.hear("apple")
    window = setup.vocab.curriculum.themes.window("video")
    assert window is not None
    said = window.word(ENTRIES["apple"].entry_id)
    assert said is not None and said.captions == 2
    setup.vocab.caption_withdrawn(f"c{setup.captions}")
    said = window.word(ENTRIES["apple"].entry_id)
    assert said is not None and said.captions == 1


# -- a conversation's word retires when known (polyglotic-hq 496) ------------------


def test_a_conversation_word_keeps_lighting_day_after_day_until_known() -> None:
    """A series' core word (业主 in residents' meetings) stays in the set
    episode after episode: not retired on its third day met (DECISIONS
    #215: the rule halved the blue words across 491's series)."""
    setup = Setup()
    setup.hear("")
    setup.talk(["apple"] * 3)
    until_update(setup, "apple")
    assert setup.came("apple") is Came.THEME
    for _ in range(RETIRE_DAYS + 1):  # an episode a day
        setup.clock.advance(days=1)
        setup.talk(["apple w11"] * 3)
    word = setup.vocab.curriculum.word(ENTRIES["apple"].entry_id)
    assert word is not None and word.active
    assert word.days_met == RETIRE_DAYS + 2
    # a word that came by the load's order still retires on its third day
    order = setup.vocab.curriculum.word(ENTRIES["w11"].entry_id)
    assert order is not None and order.came is Came.ORDER
    assert order.standing is Standing.RETIRED and order.days_met == RETIRE_DAYS


def test_a_conversation_word_retires_when_its_chance_says_known() -> None:
    known: set[EntryId] = set()
    saved: list[object] = []
    curriculum = Curriculum(
        (),
        CurriculumStore(saved.extend, lambda _: None),
        BY_ID.get,
        lambda f: not f.is_name and (f.frequency_rank or 0) > 10,
        lambda: (),
        lambda after, limit: placed(after, limit, ""),
        lambda: 10,
        melbourne,
        known=lambda f: f.entry_id in known,
    )
    clock = Clock(START)
    curriculum.set_size(5, clock())
    apple = ENTRIES["apple"]

    def say(n: int, line: str) -> None:
        clock.advance(seconds=15)
        found = words_of(line, ENTRIES)
        curriculum.caption_finished(found, clock(), f"c{n}", "video", line.split())

    for n in range(12):  # an update comes
        say(n, "apple")
    word = curriculum.word(apple.entry_id)
    assert word is not None and word.came is Came.THEME and word.active
    known.add(apple.entry_id)  # green now: 489's chance 0.85 or more
    clock.advance(days=1)  # met again on another day
    say(12, "apple")
    word = curriculum.word(apple.entry_id)
    assert word is not None and word.standing is Standing.RETIRED
