"""The card's "Here:" line (polyglotic-hq 328): a looked-up word's
counterpart in its caption line's translation, on every kind of card,
hovered or pinned - and nothing new kept. The view in plain Python; the
caption window and transcript offscreen; made-up text only."""

from dataclasses import replace

from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample
from tests.lexicon.test_basic import SPANISH, FakeSplit
from tests.ui_next.test_lookup_view import COMPUTER, CONTEXT, Learner, learner

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

HERE = replace(CONTEXT, counterpart="computer", counterpart_language="en")


def test_hovered_and_pinned_the_card_says_the_counterpart() -> None:
    lookup = Lookup(learner())
    lookup.show("电脑", HERE, pinned=False, at=COMPUTER)
    hover = lookup.card()
    assert (hover.shows, hover.counterpart) == (Shows.ENTRY, "computer")
    assert hover.counterpart_language == "en"
    lookup.show("电脑", HERE, pinned=True, at=COMPUTER)
    assert lookup.card().counterpart == "computer"


def test_none_says_nothing() -> None:
    lookup = Lookup(learner())
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    assert lookup.card().counterpart == ""


def test_a_part_looked_into_has_none_and_back_returns_it() -> None:
    """The line's link is the word's, not its characters'."""
    lookup = Lookup(learner())
    lookup.show("电脑", HERE, pinned=True, at=COMPUTER)
    lookup.part(0)
    assert lookup.card().counterpart == ""
    assert lookup.back()
    assert lookup.card().counterpart == "computer"


def test_every_kind_of_card_says_it() -> None:
    """Not in the dictionary, no dictionary for the row (the card's main
    content there), the learner's dictionary out, a basic dictionary's."""
    lookup = Lookup(learner())
    lookup.show("画面", replace(HERE, counterpart="graphics"), pinned=True)
    assert (lookup.card().shows, lookup.card().counterpart) == (
        Shows.NOT_FOUND,
        "graphics",
    )
    bank = LookupContext("은행에 가요", "I'm going to the bank", "bank", "en")
    lookup.show("은행", bank, pinned=True, language="ko")
    card = lookup.card()
    assert (card.shows, card.counterpart) == (Shows.NO_DICTIONARY, "bank")
    lookup.show("은행", bank, pinned=False, language="ko")
    assert lookup.card().counterpart == "bank"
    out = learner()
    out.dictionary_problem = DictionaryProblem.DAMAGED
    broken = Lookup(out)
    broken.show("电脑", HERE, pinned=True, at=COMPUTER)
    card = broken.card()
    assert (card.shows, card.counterpart) == (Shows.DICTIONARY_OUT, "computer")
    tools = learner()
    tools.basic["es"] = BasicDictionary(SPANISH, FakeSplit(), "es")
    basic = Lookup(tools)
    basic.show("casa", LookupContext("Mi casa.", "", "house", "en"), True, None, "es")
    card = basic.card()
    assert (card.basic, card.counterpart) == (True, "house")


def _learner(store: MemoryLearningStore) -> Learner:
    dictionary = ChineseDictionary(chinese_sample())

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    return Learner(Vocabulary(store, facts, "hsk-2025", Clock()), dictionary)


def _everything(context: LookupContext) -> tuple[str, str, str]:
    """Hover, pin, Add to deck, Known, Save to, moved, Remove and
    saved again, on `context`: the learning events published, what the
    store keeps and what an Anki export is made from - as text."""
    store = MemoryLearningStore()
    tools = _learner(store)
    events: list[object] = []
    tools.vocabulary.subscribe(events.append)
    lookup = Lookup(tools)
    lookup.show("电脑", context, pinned=False, at=COMPUTER)
    lookup.show("电脑", context, pinned=True, at=COMPUTER)
    lookup.add_to_deck()
    lookup.known()
    lookup.known()
    lookup.add_to_deck()
    lookup.save_to("saved")
    lookup.save_to("tricky")  # moved
    lookup.remove()
    lookup.save_to("saved")
    lookup.show("游戏", context, pinned=True, at=(4, 6))
    lookup.save_to("saved")
    return repr(events), repr(store.load()), repr(tools.vocabulary.anki_words())


def test_nothing_new_is_kept_or_sent() -> None:
    """The counterpart is the card's only: the learning events (what goes
    to the server), the saved word (its line and translation) and Anki's
    words are exactly what they were without it."""
    without = _everything(CONTEXT)
    with_it = _everything(
        replace(CONTEXT, counterpart="laptop!", counterpart_language="q-test")
    )
    assert with_it == without
    for kept in with_it:
        assert "laptop!" not in kept and "q-test" not in kept
    assert "My computer froze again," in with_it[1]  # the line's translation is
