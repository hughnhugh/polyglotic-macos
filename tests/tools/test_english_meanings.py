"""An English word's meanings in English (polyglotic-hq 447, decision
0211): our own for the words WordNet lacks, WordNet's parts of speech in
the order English uses them, short definitions, examples that use the word."""

from tools.dictionaries import english_meanings as em
from tools.dictionaries.ecdict import EcdictRow
from tools.dictionaries.oewn import Sense


def row(word: str, exchange: dict[str, str] | None = None) -> EcdictRow:
    return EcdictRow(word, "", ("中文",), (), bnc=1, frq=1, exchange=exchange or {})


BACK = [
    Sense("noun", "the posterior part of a human body", ("my back hurts",)),
    Sense("noun", "the side that goes last", ()),
    Sense("adverb", "in or to a former location", ("she went back home",)),
    Sense("adverb", "at or to the rear", ()),
    Sense("verb", "be behind; approve of", ()),
]


def test_the_commonest_use_comes_first_and_a_common_second_is_shown() -> None:
    """WordNet lists "back"'s noun first; English uses it as an adverb
    most, and as a noun often enough (25 %) that the card's three show it.
    The verb, rarer, comes last."""
    found = em.from_wordnet("back", BACK, {"ADV": 60, "NOUN": 25, "VERB": 15})
    assert found[:4] == (
        '(adv) in or to a former location: "she went back home"',
        "(adv) at or to the rear",
        "(noun) the posterior part of a human body",
        "(noun) the side that goes last",
    )
    assert found[-1] == "(verb) be behind; approve of" and len(found) == len(BACK)


def test_without_counts_wordnets_order_stays() -> None:
    found = em.from_wordnet("back", BACK, None)
    assert found[0] == '(noun) the posterior part of a human body: "my back hurts"'


def test_an_example_must_use_the_word() -> None:
    """WordNet gives a meaning group's examples: "big"'s first was "a
    large city", which teaches "large"."""
    assert em.example_for("big", ["a large city", "set out for the big city"]) == (
        "set out for the big city"
    )
    assert em.example_for("run", ["he was running late"]) == "he was running late"
    assert em.example_for("run", ["x" * 80 + " run"]) == ""  # too long for the card
    assert em.example_for("big", ["a large city"]) == ""


def test_a_definition_is_cut_where_its_first_part_stands_alone() -> None:
    assert em.short("have the quality of being; (copula, used with ...)") == (
        "have the quality of being"
    )
    assert em.short("flee; take to one's heels") == "flee; take to one's heels"


def test_our_own_replace_wordnets_and_only_the_first_has_its_example() -> None:
    """WordNet's first "can" is a tin; ours is the verb."""
    core = {"can": [("verb", "to be able to", "I can swim."), ("noun", "a tin", "x")]}
    senses = {"can": [Sense("verb", "preserve in a can", ())]}
    assert em.meanings_of(row("can"), senses, core, {}, {}) == (
        '(verb) to be able to: "I can swim."',
        "(noun) a tin",
    )
    # matched exactly: "Can" (a name, a capital) isn't "can"
    assert em.meanings_of(row("Can"), senses, core, {}, {})[0].startswith(
        "(verb) preserve"
    )


def test_a_form_without_meanings_of_its_own_says_what_it_is_a_form_of() -> None:
    """ECDICT's "was" has no inflections of its own: "be" lists it."""
    be = row("be", {"p": "was,were", "d": "been", "3": "is"})
    left = row("left", {"0": "leave", "1": "pd"})
    forms = em.inflections([be, left])
    assert em.meanings_of(row("was"), {}, {}, {}, forms) == ("(verb) past tense of be",)
    assert em.meanings_of(left, {}, {}, {}, forms) == (
        "(verb) past tense and past participle of leave",
    )
    assert em.meanings_of(row("zzz"), {}, {}, {}, forms) == ()


def test_our_own_file_reads_and_names_known_parts_of_speech() -> None:
    core = em.read_core()
    parts = {"noun", "verb", "adj", "adv", "prep", "conj", "pron", "det"}
    parts |= {"article", "particle", "intj"}
    assert {pos for senses in core.values() for pos, _, _ in senses} <= parts
    assert all(definition for senses in core.values() for _, definition, _ in senses)
    # the words WordNet has nothing for, or the wrong first sense ("North":
    # the US region; the card for a caption's "north", polyglotic-hq 462)
    for word in ("the", "of", "you", "I", "he", "can", "like", "do", "North"):
        assert word in core, word


def test_the_check_counts_the_words_a_card_explains() -> None:
    """`english_check`: a word counts when its card's first entry has a
    meaning - "ran" through run's; "zzz" isn't in the dictionary."""
    from tests.lexicon.sample import english_sample
    from tools.dictionaries import english_check

    from polyglotic_desktop.core.lexicon.english import EnglishDictionary

    d = EnglishDictionary(english_sample())
    found = english_check.in_lines(d, ["They ran to zzz, 42."])
    assert (found.found, found.counted, dict(found.misses)) == (3, 4, {"zzz": 1})
    listed = english_check.top(d, {"to": 0.5, "zzz": 0.2, "42": 0.3}, 2)
    assert listed == [(1, "to", "prep. 到"), (2, "zzz", "")]
