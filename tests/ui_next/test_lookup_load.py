"""A word's own card and the learning load (polyglotic-hq 324): while the
mode is on, a pinned card says the word's stage and what it has been
heard; a word ready to check is answered there with one click; a word
that isn't in the load can be added. Off, the card is as it was. The
sample dictionary with made-up ranks, made-up lines. Offscreen."""

from PySide6.QtWidgets import QApplication
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample
from tests.ui_next.test_lookup_view import Learner

from polyglotic_desktop.core.learning.load import LoadRules, Stage
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_marks import STAGE_COLOURS
from polyglotic_desktop.ui_next.lookup_card import WIDTH, LookupCard
from polyglotic_desktop.ui_next.views.lookup import Lookup

RANKS = {"人": 800, "这个": 20, "电脑": 1200, "游戏": 1300, "研究": 1400, "足球": 1500}
CONTEXT = LookupContext("这个人研究电脑游戏足球")
HEARD: list[str] = []


def learner(mode: bool = True) -> Learner:
    """A learner of 1,000 words whose load is 电脑 and 游戏; 研究 and 足球
    are past it."""
    dictionary = ChineseDictionary(chinese_sample(frequency_ranks=RANKS))

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    vocabulary = Vocabulary(
        MemoryLearningStore(), facts, "hsk-2025", Clock(), placed=dictionary.words_past
    )
    vocabulary.set_known_words(1000)
    vocabulary.set_load_rules(LoadRules(size=2) if mode else None)
    return Learner(vocabulary, dictionary)


def hear(tools: Learner, text: str) -> None:
    HEARD.append(text)  # each a caption of its own
    tools.vocabulary.caption_finished(
        f"heard-{len(HEARD)}", tools.words_in(text), by_you=False
    )


def pinned(tools: Learner, word: str) -> Lookup:
    lookup = Lookup(tools)
    lookup.show(word, CONTEXT, pinned=True)
    return lookup


def test_a_pinned_card_says_the_words_stage_and_meetings() -> None:
    tools = learner()
    hear(tools, "电脑 " * 4)
    card = pinned(tools, "电脑").card()
    assert (card.load_stage, card.load_heard, card.load_step) == (Stage.ORANGE, 1, 3)
    assert not card.load_offer  # in it already
    hover = Lookup(tools)
    hover.show("电脑", CONTEXT, pinned=False)
    assert hover.card().load_stage is None  # a hover stays short


def test_a_word_outside_the_load_can_be_added_from_its_card() -> None:
    tools = learner()
    lookup = pinned(tools, "足球")
    assert lookup.card().load_stage is None and lookup.card().load_offer
    lookup.load_add()
    card = lookup.card()
    assert card.load_stage is Stage.RED and not card.load_offer
    assert tools.vocabulary.load.rules == LoadRules(size=3)  # it grew by the word
    # looked up twice, past half the line: no longer taken as known (397)
    pinned(tools, "人")
    person = pinned(tools, "人")
    assert person.card().load_offer
    person.known()
    assert not person.card().load_offer  # a word set known isn't offered


def test_a_word_ready_to_check_is_answered_on_its_card() -> None:
    tools = learner()
    hear(tools, "电脑 " * 12 + "游戏 " * 12)
    lookup = pinned(tools, "电脑")
    assert lookup.card().load_stage is Stage.READY
    lookup.load_check(False)  # not yet: back to yellow
    assert lookup.card().load_stage is Stage.YELLOW
    game = pinned(tools, "游戏")
    game.load_check(True)
    card = game.card()
    assert card.status is WordStatus.KNOWN and card.load_stage is None
    assert not card.load_offer  # known: not to be added again


def test_off_the_card_is_as_it_was() -> None:
    tools = learner(mode=False)
    card = pinned(tools, "电脑").card()
    assert card.load_stage is None and not card.load_offer


def drawn(shown: LookupCard) -> dict[str, str]:
    """The card's words and the colour each is drawn in."""
    painted = shown._lay_out(shown.model.card(), style.px(WIDTH))
    return {run.text: run.color.name() for run in painted.runs}


def test_the_card_draws_the_stage_and_the_check_and_does_them(
    qapp: QApplication,
) -> None:
    tools = learner()
    hear(tools, "电脑 " * 4)
    shown = LookupCard(tools)
    try:
        shown.model.show("电脑", CONTEXT, pinned=True)
        words = drawn(shown)
        assert words["Orange: heard 1 of 3"] == STAGE_COLOURS[Stage.ORANGE]
        assert "I know this" not in words and "Add to my load" not in words
        hear(tools, "电脑 " * 8)
        assert {"Ready to check", "I know this", "Not yet"} <= set(drawn(shown))
        shown.do("load_not_yet")
        assert "Yellow: heard 0 of 3" in drawn(shown)
        shown.model.show("足球", CONTEXT, pinned=True)
        assert "Add to my load" in drawn(shown)
        shown.do("load_add")
        words = drawn(shown)
        assert "Red: heard 0 of 3" in words and "Add to my load" not in words
    finally:
        shown.close()


def test_the_card_draws_nothing_of_the_load_while_the_mode_is_off(
    qapp: QApplication,
) -> None:
    shown = LookupCard(learner(mode=False))
    try:
        shown.model.show("电脑", CONTEXT, pinned=True)
        words = set(drawn(shown))
        assert not {w for w in words if "heard 0 of" in w or "load" in w.lower()}
    finally:
        shown.close()
