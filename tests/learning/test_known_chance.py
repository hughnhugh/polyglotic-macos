"""How well the learner knows each word, 0 to 1 (polyglotic-hq 489,
decision 0226): where a word starts (what the learner said, the line as a
curve), what moves it and how far, the bands the user named - red,
between, green - and that it is cheap enough for every caption word.
Made-up words; the days are the learner's own."""

import math
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from tests.learning.fakes import facts

from polyglotic_desktop.core.learning import known_chance as kc
from polyglotic_desktop.core.learning.knowledge import Knowledge
from polyglotic_desktop.core.learning.known_chance import (
    Band,
    Chance,
    Evidence,
    KnownChances,
    Moved,
    Start,
    band,
    curve,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.lookups import LookupCount
from polyglotic_desktop.core.learning.statuses import StatusRecord, StatusSource
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
TODAY = NOW.date()
YESTERDAY = TODAY - timedelta(days=1)


def word(rank: int | None, name: str = "", is_name: bool = False) -> EntryFacts:
    return facts(name or f"w{rank}", level=None, rank=rank, is_name=is_name)


class Learner:
    """A learner's `KnownChances` over statuses, a line and evidence a test
    sets."""

    def __init__(self, line: int | None = 1000) -> None:
        self.own: dict[EntryId, StatusRecord] = {}
        self.line = None if line is None else KnownLine.words(line)
        self.evidence: dict[EntryId, Evidence] = {}
        self.now = NOW
        self.chances = KnownChances(
            Knowledge(self.own.get, lambda: self.line, KnownLine.words(1000)),
            lambda e: self.evidence.get(e, kc.NO_EVIDENCE),
            lambda: self.now,
            lambda at: at.date(),
        )

    def says(
        self,
        facts_: EntryFacts,
        status: WordStatus,
        source: StatusSource = StatusSource.LEARNER,
    ) -> None:
        self.own[facts_.entry_id] = StatusRecord(status, source, NOW)

    def did(self, facts_: EntryFacts, **evidence: object) -> None:
        was = self.evidence.get(facts_.entry_id, kc.NO_EVIDENCE)
        self.evidence[facts_.entry_id] = replace(was, **evidence)  # type: ignore[arg-type]

    def of(self, facts_: EntryFacts) -> Chance:
        found = self.chances.of(facts_)
        assert found is not None
        return found


def logit(p: float) -> float:
    return math.log(p / (1 - p))


# -- the curve -------------------------------------------------------------------


def test_the_line_is_where_half_the_words_are_known() -> None:
    assert curve(1000, 1000) == pytest.approx(0.5)
    assert Learner(1000).of(word(1000)).chance == pytest.approx(0.5)


def test_the_chance_falls_smoothly_with_the_place_not_in_a_step() -> None:
    chances = [curve(at, 1000) for at in (125, 250, 500, 999, 1001, 2000, 4000)]
    assert chances == sorted(chances, reverse=True)
    assert len(set(chances)) == len(chances)
    # either side of the line, nothing jumps: the step was 1 -> 0
    assert curve(999, 1000) - curve(1001, 1000) < 0.01
    # 019's spread: half the line 0.82, twice it 0.18, four times 0.05
    assert curve(500, 1000) == pytest.approx(0.82, abs=0.01)
    assert curve(2000, 1000) == pytest.approx(0.18, abs=0.01)
    assert curve(4000, 1000) == pytest.approx(0.05, abs=0.01)


def test_the_curve_agrees_with_knowledge_either_side_of_the_line() -> None:
    learner = Learner(1000)
    for rank in (1, 10, 400, 999, 1000, 1001, 1500, 3000, 50000):
        known = learner.chances.knowledge.of(word(rank)).known
        chance = learner.of(word(rank)).chance
        assert (chance >= 0.5) == known, rank


def test_the_bands_for_a_learner_of_1000_words() -> None:
    # green up to about the 440th word, red past about the 2,260th
    assert curve(440, 1000) >= kc.MASTERED_FROM > curve(446, 1000)
    assert curve(2250, 1000) >= kc.UNKNOWN_BELOW > curve(2270, 1000)
    assert band(curve(100, 1000)) is Band.MASTERED
    assert band(curve(1000, 1000)) is Band.PARTIAL
    assert band(curve(5000, 1000)) is Band.UNKNOWN


def test_just_starting_knows_nothing_yet() -> None:
    assert Learner(0).of(word(1)).band is Band.UNKNOWN


def test_a_native_line_colours_every_common_word_green() -> None:
    native = Learner(90_000)
    assert all(native.of(word(rank)).band is Band.MASTERED for rank in (1, 5000, 30000))


def test_the_starting_line_is_said_to_be_assumed() -> None:
    assert Learner(None).of(word(10)).start is Start.STARTING_LINE
    assert Learner(1000).of(word(10)).start is Start.LINE


# -- where a word starts -------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "source", "start", "chance"),
    [
        (WordStatus.KNOWN, StatusSource.LEARNER, Start.SAID_KNOWN, 0.98),
        (WordStatus.KNOWN, StatusSource.IMPORTED, Start.IMPORTED_KNOWN, 0.95),
        (WordStatus.LEARNING, StatusSource.LEARNER, Start.LEARNING, 0.27),
        (WordStatus.NEW, StatusSource.LEARNER, Start.SAID_NEW, 0.05),
        (WordStatus.NEW, StatusSource.ESTIMATED, Start.LOOKED_UP, 0.27),
    ],
)
def test_what_the_learner_said_wins_over_the_line(
    status: WordStatus, source: StatusSource, start: Start, chance: float
) -> None:
    learner = Learner(1000)
    for rank in (5, 50000):  # common or rare, the same
        learner.says(word(rank), status, source)
        found = learner.of(word(rank))
        assert (found.start, round(found.chance, 2)) == (start, chance)


def test_names_and_ignored_words_are_not_coloured() -> None:
    learner = Learner(1000)
    learner.says(word(30), WordStatus.IGNORED)
    assert learner.chances.of(word(30)) is None
    assert learner.chances.of(word(40, "Zhang", is_name=True)) is None


def test_a_word_nothing_places_is_rarer_than_the_map() -> None:
    """Red for a learner of 1,000 words, between for a near-native one,
    green for a native - not red for everyone (输掉 was, on real captions)."""
    found = Learner(1000).of(word(None))
    assert (found.start, found.band) == (Start.NOT_PLACED, Band.UNKNOWN)
    assert Learner(20000).of(word(None)).band is Band.PARTIAL
    assert Learner(90000).of(word(None)).band is Band.MASTERED
    assert Learner(20000).of(word(None)).chance == pytest.approx(
        curve(kc.UNPLACED, 20000)
    )


def test_a_number_in_numerals_is_known() -> None:
    twenty = EntryFacts(EntryId("test:二十"), None, None, False, None, is_number=True)
    assert Learner(500).of(twenty).band is Band.MASTERED


# -- what moves it -----------------------------------------------------------------


def test_each_day_heard_raises_it_half_a_step_up_to_five() -> None:
    learner = Learner(1000)
    rare = word(2000)  # 0.18: no floor or cap in the way
    before = logit(learner.of(rare).chance)
    for days in (1, 3, 5, 9):
        learner.did(rare, days_heard=days, last_heard=YESTERDAY)
        after = logit(learner.of(rare).chance)
        assert after - before == pytest.approx(0.5 * min(days, 5))
    assert learner.of(rare).moved == ((Moved.HEARD, 2.5),)


def test_todays_hearing_counts_from_tomorrow() -> None:
    """Every word of a caption was just heard: counted at once, none could
    ever be red, and a colour would change as it was read."""
    learner = Learner(1000)
    rare = word(20000)
    learner.did(rare, days_heard=1, last_heard=TODAY)
    assert learner.of(rare).band is Band.UNKNOWN
    assert learner.of(rare).moved == ()
    learner.did(rare, days_heard=3, last_heard=TODAY)  # two days before today
    assert learner.of(rare).days_heard == 2
    learner.now = NOW + timedelta(days=1)  # the next day: today's counts too
    assert learner.of(rare).days_heard == 3


def test_hearing_isnt_knowing_it_never_makes_a_word_green() -> None:
    learner = Learner(1000)
    near = word(1100)  # just past the line: 0.45
    learner.did(near, days_heard=30, last_heard=YESTERDAY, saved=True)
    assert learner.of(near).chance == pytest.approx(kc.EXPOSURE_CAP)
    assert learner.of(near).band is Band.PARTIAL


def test_hearing_never_lowers_a_word_that_started_higher() -> None:
    learner = Learner(1000)
    common = word(20)
    was = learner.of(common).chance
    learner.did(common, days_heard=3, last_heard=YESTERDAY)
    assert learner.of(common).chance == pytest.approx(was)


def test_a_rare_word_once_heard_is_no_longer_red_and_rises_with_days() -> None:
    learner = Learner(1000)
    rare = word(20000)
    assert learner.of(rare).band is Band.UNKNOWN
    learner.did(rare, days_heard=1, last_heard=YESTERDAY)
    assert learner.of(rare).chance == pytest.approx(kc.MET)
    assert learner.of(rare).band is Band.PARTIAL
    learner.did(rare, days_heard=5)
    assert learner.of(rare).chance == pytest.approx(0.38, abs=0.01)  # -3 + 2.5


def test_a_fresh_lookup_lowers_it_and_an_old_one_kept_raises_it() -> None:
    learner = Learner(1000)
    middle = word(1500)
    start = logit(learner.of(middle).chance)
    looked = LookupCount(pinned=1, last=NOW - timedelta(hours=2))
    learner.did(middle, lookups=looked, last_heard=TODAY, days_heard=0)
    assert logit(learner.of(middle).chance) - start == pytest.approx(-1.5)
    assert learner.of(middle).moved == ((Moved.FRESH_LOOKUP, -1.5),)
    assert learner.of(middle).band is Band.UNKNOWN  # they didn't know it just now
    # four days on, heard again since without another lookup: kept
    learner.now = NOW + timedelta(days=4)
    learner.did(middle, last_heard=TODAY + timedelta(days=3))
    assert logit(learner.of(middle).chance) - start == pytest.approx(1.0)
    assert learner.of(middle).moved == ((Moved.NOT_AGAIN, 1.0),)
    # not heard since: the old lookup says nothing
    learner.did(middle, last_heard=TODAY)
    assert learner.of(middle).moved == ()


def test_one_hover_isnt_a_lookup() -> None:
    learner = Learner(1000)
    learner.did(word(800), lookups=LookupCount(hovered=3, last=NOW))
    assert learner.of(word(800)).moved == ()


def test_a_word_said_known_and_looked_up_twice_since_drops_from_green() -> None:
    learner = Learner(1000)
    rare = word(9000)
    learner.says(rare, WordStatus.KNOWN)
    assert learner.of(rare).band is Band.MASTERED
    looked = LookupCount(pinned=2, last=NOW, pinned_since_known=2)
    learner.did(rare, lookups=looked)
    found = learner.of(rare)
    assert found.band is Band.PARTIAL
    assert found.moved == ((Moved.FRESH_LOOKUP, -1.5), (Moved.SINCE_KNOWN, -1.5))


def test_saving_raises_it_a_little() -> None:
    learner = Learner(1000)
    rare = word(2000)
    before = logit(learner.of(rare).chance)
    learner.did(rare, saved=True)
    assert logit(learner.of(rare).chance) - before == pytest.approx(0.5)


def test_dont_know_then_heard_on_days_is_between() -> None:
    learner = Learner(1000)
    common = word(100)
    learner.says(common, WordStatus.NEW)
    assert learner.of(common).band is Band.UNKNOWN
    learner.did(common, days_heard=5, last_heard=YESTERDAY)
    assert learner.of(common).band is Band.PARTIAL


def test_nothing_is_ever_certain() -> None:
    learner = Learner(1000)
    rare, common = word(80000), word(1)
    learner.says(rare, WordStatus.NEW)
    learner.says(common, WordStatus.KNOWN)
    looked = LookupCount(pinned=5, last=NOW, pinned_since_known=5)
    learner.did(rare, lookups=looked)
    learner.did(common, days_heard=50, last_heard=YESTERDAY, saved=True)
    assert kc.LOWEST <= learner.of(rare).chance < kc.MET / 3
    assert 0.97 < learner.of(common).chance <= kc.HIGHEST


# -- cheap enough for every caption word ----------------------------------------------


def test_a_captions_words_take_a_few_microseconds_each() -> None:
    learner = Learner(1000)
    words = [word(rank) for rank in range(1, 2001)]
    for each in words[::3]:
        learner.did(each, days_heard=2, last_heard=date(2026, 11, 17))
    for each in words[::7]:
        learner.says(each, WordStatus.KNOWN)
    best = math.inf
    for _ in range(5):
        began = time.perf_counter()
        learner.chances.each(words)
        best = min(best, time.perf_counter() - began)
    per_word = best / len(words) * 1e6
    # about 3 us a word on the user's PC (489); 40 is a slow CI runner's room
    assert per_word < 40, f"{per_word:.1f} us a word"


# -- the learner's own vocabulary ---------------------------------------------------


def test_the_vocabulary_counts_separate_days_heard_and_colours_by_them() -> None:
    """A word heard twice on one of the learner's days is one day; the next
    day is another; what the PC played only, never the mic - and the
    vocabulary's chances read them, and lookups and saves."""
    from tests.learning.fakes import Clock, MemoryLearningStore, words_of

    from polyglotic_desktop.core.learning.lookups import LookupContext
    from polyglotic_desktop.core.learning.vocabulary import Vocabulary

    rare = facts("榴莲", level=None, rank=30000)
    entries = {"榴莲": rare}
    clock = Clock(datetime(2026, 11, 18, 1, 0, tzinfo=UTC))
    vocab = Vocabulary(
        MemoryLearningStore(),
        lambda entry_id, scheme: rare if entry_id == rare.entry_id else None,
        "hsk-2025",
        clock,
        day_of=lambda at: (at + timedelta(hours=11)).date(),  # Melbourne's
    )
    vocab.set_known_words(1000)
    chance = vocab.chances.of(rare)
    assert chance is not None and chance.band is Band.UNKNOWN

    def hear(caption: str, by_you: bool = False) -> None:
        vocab.caption_finished(caption, words_of("榴莲", entries), by_you)

    hear("a")
    hear("b")
    hear("c", by_you=True)
    assert vocab.exposures(rare.entry_id).days_heard == 1
    clock.advance(hours=12)  # 13:00 UTC: Melbourne's next day, UTC's same
    hear("d")
    count = vocab.exposures(rare.entry_id)
    assert (count.days_heard, count.last_heard) == (2, date(2026, 11, 19))
    chance = vocab.chances.of(rare)
    assert chance is not None  # the first day counts; today's from tomorrow
    assert chance.band is Band.PARTIAL and chance.days_heard == 1
    vocab.save(
        rare.entry_id,
        "榴莲",
        "榴蓮",
        "liu2 lian2",
        "durian",
        "saved",
        LookupContext(""),
    )
    vocab.looked_up(rare, pinned=True)
    chance = vocab.chances.of(rare)
    assert chance is not None
    assert [m for m, _ in chance.moved] == [
        Moved.HEARD,
        Moved.SAVED,
        Moved.FRESH_LOOKUP,
    ]


def test_a_compound_is_placed_no_rarer_than_twice_its_rarest_part() -> None:
    """输掉 is the 83,039th word in CC-CEDICT's list, but 输 is the 2,836th
    and 掉 the 987th: a learner of 3,000 words who knows them understands
    it. A word of rare parts stays rare; a part nothing places leaves the
    word as it was."""
    shudiao = facts("输掉", level=None, rank=83039)
    shu, diao = facts("输", level=None, rank=2836), facts("掉", level=None, rank=987)
    rare = facts("龃龉", level=None, rank=None)
    ju, yu = facts("龃", level=None, rank=40000), facts("龉", level=None, rank=52000)
    odd = facts("三柱门", level=None, rank=None)
    san, zhu, men = (
        facts(c, level=None, rank=r)
        for c, r in (("三", 130), ("柱", 4286), ("门", 139))
    )
    unplaced_part = facts("某某", level=None, rank=None)
    parts = {
        shudiao.entry_id: (shu, diao),
        rare.entry_id: (ju, yu),
        odd.entry_id: (san, zhu, men),
        unplaced_part.entry_id: (shu, facts("某", level=None, rank=None)),
    }
    learner = Learner(3000)
    before = learner.of(shudiao)
    assert before.band is Band.UNKNOWN  # by its own place alone: red
    learner.chances.parts = lambda word: parts.get(word.entry_id, ())
    found = learner.of(shudiao)
    assert found.place == 2 * 2836
    assert found.band is not Band.UNKNOWN and found.start is Start.LINE
    assert learner.of(rare).band is Band.UNKNOWN  # rare parts: still red
    assert learner.of(odd).place == 2 * 4286  # 三柱门 by 柱
    assert learner.of(odd).band is Band.UNKNOWN  # rare-ish at 3,000
    assert Learner(20000).of(odd).start is Start.NOT_PLACED  # no parts: past the map
    assert learner.of(unplaced_part).start is Start.NOT_PLACED
    assert learner.of(word(500)).place == 500  # a word with no parts: as it was


def test_the_app_gives_a_chinese_word_its_characters() -> None:
    """`main.characters_of` over the sample dictionary: 电脑 is 电 and 脑,
    each a word of its own; one character has no parts; read once."""
    from tests.lexicon.sample import chinese_sample

    from polyglotic_desktop import main
    from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary

    ranks = {"电脑": 83000, "电": 608, "脑": 2791}
    dictionary = ChineseDictionary(chinese_sample(frequency_ranks=ranks))
    dictionary.prepare()
    parts = main.characters_of(lambda: dictionary, lambda: "hsk-2025")
    computer = dictionary.words_in("电脑", "hsk-2025")[0].entry
    found = parts(computer)
    assert [p.frequency_rank for p in found] == [608, 2791]
    assert parts(computer) is found  # kept
    assert parts(dictionary.words_in("电", "hsk-2025")[0].entry) == ()
