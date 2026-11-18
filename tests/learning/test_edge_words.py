"""Words at your edge (polyglotic-hq 496, DECISIONS #215): the quiet view's
fourth choice lights any word in the learner's learning window as it is
said - at the size of window they chose - never a name, a number, everyday
talk or a filler - a couple a caption at most, the commonest first; ticked
by default for a new learner."""

from collections.abc import Sequence
from datetime import UTC, datetime

from tests.learning.fakes import Clock, MemoryLearningStore, facts

from polyglotic_desktop.core.learning.curriculum import (
    DEFAULT_CHOSEN,
    EDGE_PER_CAPTION,
    ChosenWords,
)
from polyglotic_desktop.core.learning.levels import UNLIMITED
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import DEFAULT_CATEGORIES
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus

ENTRIES: dict[str, EntryFacts] = {
    f"w{n}": facts(f"w{n}", level=None, rank=n) for n in range(1, 2001)
}
"""w1-w100 are known (the line is at 100)."""
ENTRIES["Bob"] = facts("Bob", level=None, rank=150, is_name=True)
ENTRIES["twenty"] = EntryFacts(
    EntryId("test:twenty"), None, 160, False, spells_a_number=True
)
ENTRIES["二十"] = EntryFacts(EntryId("test:二十"), None, 170, False, is_number=True)
ENTRIES["um"] = EntryFacts(EntryId("test:um"), None, 180, False, is_filler=True)
ENTRIES["okay"] = EntryFacts(EntryId("test:okay"), None, 900, False, spoken_rank=60)
"""Everyday talk: said far more than written."""
ENTRIES["thanks"] = EntryFacts(EntryId("test:thanks"), None, 200, False, spoken_rank=90)
"""Heard so often the learner knows it: its spoken rank inside their 100
(not everyday talk: written, it is the 200th)."""
BY_ID = {f.entry_id: f for f in ENTRIES.values()}


def lookup(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return BY_ID.get(entry_id)


def placed(after: int, limit: int, scheme: str) -> Sequence[tuple[int, EntryFacts]]:
    found = sorted(
        (f.frequency_rank or 0, f.entry_id, f)
        for f in ENTRIES.values()
        if (f.frequency_rank or 0) > after
    )
    return [(rank, f) for rank, _, f in found[:limit]]


def learner(
    chosen: frozenset[ChosenWords] = frozenset({ChosenWords.EDGE}),
) -> Vocabulary:
    vocab = Vocabulary(
        MemoryLearningStore(),
        lookup,
        "en-frequency",
        Clock(datetime(2026, 11, 18, 9, 0, tzinfo=UTC)),
        placed,
    )
    vocab.set_known_words(100)
    vocab.set_chosen(chosen, 50)
    return vocab


def blue(vocab: Vocabulary, *names: str) -> set[str]:
    return {name for name in names if vocab.chosen(ENTRIES[name])}


def test_a_word_in_the_window_is_blue_each_time_it_is_said() -> None:
    vocab = learner()  # the default window: the next 1,000 words past 100
    assert blue(vocab, "w50", "w101", "w600", "w1100", "w1101") == {
        "w101",
        "w600",
        "w1100",
    }  # w50 known by the line; w1101 past the window


def test_never_a_name_a_number_everyday_talk_or_a_filler() -> None:
    vocab = learner()
    assert blue(vocab, "Bob", "twenty", "二十", "um", "okay", "thanks") == set()


def test_what_the_learner_said_of_a_word_counts() -> None:
    vocab = learner()
    vocab.set_status(ENTRIES["w200"].entry_id, WordStatus.KNOWN)
    vocab.set_status(ENTRIES["w300"].entry_id, WordStatus.IGNORED)
    vocab.set_status(ENTRIES["w400"].entry_id, WordStatus.LEARNING)  # in the deck
    vocab.set_status(ENTRIES["w60"].entry_id, WordStatus.NEW)  # before the line
    assert blue(vocab, "w200", "w300", "w400", "w60") == {"w400", "w60"}


def test_the_window_is_the_size_the_learner_chose() -> None:
    vocab = learner()
    vocab.set_window_size(100)
    assert blue(vocab, "w150", "w200", "w201") == {"w150", "w200"}
    vocab.set_window_size(UNLIMITED)
    assert blue(vocab, "w1999") == {"w1999"}
    vocab.set_window_size(None)  # the default again
    assert blue(vocab, "w1100", "w1101") == {"w1100"}


def test_only_while_it_is_ticked() -> None:
    vocab = learner(frozenset({ChosenWords.SAVED}))
    assert blue(vocab, "w101") == set()


def test_a_new_learner_has_it_ticked_beside_our_curriculum() -> None:
    assert {ChosenWords.CURRICULUM, ChosenWords.EDGE} == DEFAULT_CHOSEN


def _save(vocab: Vocabulary, name: str) -> None:
    vocab.save(
        ENTRIES[name].entry_id,
        name,
        "",
        "",
        "a word",
        DEFAULT_CATEGORIES[0].id,
        LookupContext(""),
    )


def test_a_caption_lights_a_couple_of_edge_words_the_commonest_first() -> None:
    """The user's "a couple per sentence": edge words fill a caption up to
    `EDGE_PER_CAPTION` blue words; the other chosen words always light."""
    vocab = learner(frozenset({ChosenWords.EDGE, ChosenWords.SAVED}))
    words = [ENTRIES[n] for n in ("w900", "w50", "w300", "w101", "w600")]
    assert EDGE_PER_CAPTION == 2
    assert vocab.lit(words) == {2, 3}  # w300 and w101; w50 is known
    _save(vocab, "w600")
    assert vocab.lit(words) == {3, 4}  # saved w600, then w101
    for name in ("w900", "w300"):
        _save(vocab, name)
    assert vocab.lit(words) == {0, 2, 4}  # three saved: no room for an edge word


def test_a_word_capitalised_inside_its_sentence_is_part_of_a_name() -> None:
    """ "Agency" of the Central Intelligence Agency: in a language whose
    capitals inside a sentence mark only names; German's nouns light."""
    vocab = learner()
    english = EntryFacts(
        EntryId("test:agency"), None, 300, False, names_capitalised=True
    )
    german = EntryFacts(EntryId("test:Agentur"), None, 310, False)
    assert vocab.lit([english, english], capitalised={0}) == {1}
    assert vocab.lit([german], capitalised={0}) == {0}
