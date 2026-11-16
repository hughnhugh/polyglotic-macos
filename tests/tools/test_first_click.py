"""A learner's first click on a common word opens its commonest meaning
(polyglotic-hq 402, 413): French's "est" had opened on "east", "L'" on the
pronoun "her", Portuguese's "A" on "wing" and "é" on an interjection,
Filipino's "May" on the month, and Italian's "dell'" on nothing."""

from __future__ import annotations

from pathlib import Path

from tools.dictionaries import kaikki, packs, treebanks


def sense(gloss: str) -> dict[str, object]:
    return {"glosses": [gloss]}


def form_of(gloss: str, *lemmas: str) -> dict[str, object]:
    return {
        "glosses": [gloss],
        "form_of": [{"word": lemma} for lemma in lemmas],
        "tags": ["form-of"],
    }


def obj(word: str, pos: str, *senses: dict[str, object]) -> dict[str, object]:
    return {"word": word, "pos": pos, "senses": list(senses)}


def table(words: kaikki.Language) -> tuple[dict[str, str], dict[str, str]]:
    """`lemma_table` with every entry kept, each word as common as another."""
    draft = packs.draft_of(words)
    draft.lemma_used = packs.lemma_used(words, USES)
    draft.came_through = dict(words.came_through)
    every = {e.key for e in draft.entries}
    return packs.lemma_table(
        draft, every, dict.fromkeys(every, 1.0), {"est": 9.0, "casa": 9.0}
    )


USES = {
    "est": {"AUX": 775, "VERB": 35, "NOUN": 16},
    "casa": {"NOUN": 300, "VERB": 4},
    "la": {"DET": 1991, "PRON": 18},
}
"""Counts as French's and Spanish's treebanks give them."""


def test_a_form_the_treebanks_use_as_its_lemma_opens_on_the_lemma() -> None:
    """French's "est" is a word of its own ("east") and être's "is": the
    treebanks use it as a verb 810 times, as a noun 16. It counts for être
    and opens on it. Spanish's "casa" (house; casar's "marries"), used as a
    noun, keeps its own first."""
    words = kaikki.read_language(
        [
            obj("est", "adj", sense("east")),
            obj("est", "noun", sense("east")),
            obj("est", "verb", form_of("third-person singular of être", "être")),
            obj("être", "verb", sense("to be")),
            obj("casa", "noun", sense("house")),
            obj("casa", "verb", form_of("inflection of casar", "casar")),
            obj("casar", "verb", sense("to marry")),
        ]
    )
    assert packs.lemma_used(words, USES) == {"est": frozenset({"être"})}
    assert packs.lemma_used(words, None) == {}
    lemmas, after = table(words)
    assert lemmas == {"est": "être"}
    assert after == {"casa": "casar"}


def test_a_form_of_a_word_that_counts_for_another_counts_for_that_one() -> None:
    """French's "l'" is la's and le's, as article and pronoun, and la (the
    pronoun "her", a form of le the article) is used as the article: "l'"
    counts for le, as la does. Portuguese's "la" is only a's (the pronoun),
    so it stays a's though a counts for o; French's "traces" is trace's
    plural and tracer's "you draw": trace counting for tracer doesn't make
    the plural noun the verb's."""
    lemmas = {"la": "le", "l'": "la", "a": "o", "pt-la": "a"}
    lemmas |= {"trace": "tracer", "traces": "trace"}
    came = {
        ("la", "le"): {"article", "pron"},
        ("l'", "la"): {"article", "pron"},
        ("l'", "le"): {"article", "pron"},
        ("a", "o"): {"article", "pron"},
        ("pt-la", "a"): {"pron"},
        ("trace", "tracer"): {"verb"},
        ("traces", "trace"): {"noun"},
        ("traces", "tracer"): {"verb"},
    }
    moved = {"la", "a"}  # by `lemma_used`; trace counts for tracer by its verb rule
    assert packs.chained_lemmas(lemmas, came, moved) == lemmas | {"l'": "le"}
    assert packs.chained_lemmas(lemmas, came, set()) == lemmas


def test_l_opens_on_the_article() -> None:
    """The whole way, from Wiktionary's lines: la's own entries are the
    pronoun and the note; le's table lists la; l' is le's and la's."""
    words = kaikki.read_language(
        [
            obj("le", "article", sense("the")),
            {
                **obj("le", "pron", sense("him")),
                "forms": [{"form": "la", "tags": ["feminine"]}],
            },
            {
                **obj("le", "article", sense("the")),
                "forms": [{"form": "la", "tags": ["feminine"]}],
            },
            obj("la", "pron", sense("her")),
            obj("la", "noun", sense("the note A")),
            obj("l'", "article", form_of("elided form of le, la", "le", "la")),
        ]
    )
    lemmas, _ = table(words)
    assert lemmas["la"] == "le"
    assert lemmas["l'"] == "le"


def test_an_elided_word_takes_its_frequency_without_the_apostrophe() -> None:
    """wordfreq drops the apostrophe: its "dell" is Italian's dell', which
    had no frequency and was cut. Only a word the app's split cuts off as
    elided: French's champ' (champagne) isn't champ (a field), nor German's
    genitive Paris' Paris again."""
    words = kaikki.read_language(
        [
            obj("dell'", "contraction", sense("of the")),
            obj("champ'", "noun", sense("champagne")),
            obj("champ", "noun", sense("field")),
            obj("z'", "infix", sense("a liaison")),
        ]
    )
    freq = {"dell": 0.002, "champ": 0.001, "z": 0.003}
    draft = packs.draft_of(words)
    draft.elisions = frozenset({"dell", "champ", "z"})
    assert packs.frequencies(draft, freq)["dell'|contraction|"] == 0.002
    draft.elisions = frozenset({"dell"})  # Italian's, as the app's split cuts them
    total = packs.frequencies(draft, freq)
    assert total["dell'|contraction|"] == 0.002
    assert total["champ'|noun|"] == 0.0
    assert total["champ|noun|"] == 0.001
    assert total["z'|infix|"] == 0.0


def test_an_elided_word_said_in_words_is_a_form_of_its_word() -> None:
    """French's n' is "Prevocalic form of ne.", with no form-of link: it is
    ne's form, not a word whose meaning is that sentence. A word without an
    apostrophe keeps such a gloss as its meaning."""
    words = kaikki.read_language(
        [
            obj("n'", "contraction", sense("Prevocalic form of ne.")),
            obj("t'", "pron", sense("elided form of te"), sense("elided form of tu")),
            obj(
                "s'",
                "pron",
                sense("Elision of se before a word beginning with a vowel."),
            ),
            obj("se", "pron", sense("oneself")),
            obj("ne", "particle", sense("not")),
            obj("te", "pron", sense("you")),
            obj("tu", "pron", sense("you")),
            obj("xy", "noun", sense("clitic form of yz")),
        ]
    )
    assert words.forms["n'"] == {"ne"}
    assert words.forms["t'"] == {"te", "tu"}
    assert words.forms["s'"] == {"se"}
    assert {e.word for e in words.entries} == {"se", "ne", "te", "tu", "xy"}


def said(pos: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Entry ID (here its headword) -> its headword and part of speech."""
    return {word: (word, part) for word, part in pos.items()}


RANK = {"may": 12, "Mayo": 2000, "a": 2, "á": 1805, "brasil": 5000, "Brasil": 300}
POS = {"may": "particle", "Mayo": "name", "a": "prep", "á": "noun"}
POS |= {"brasil": "adj", "Brasil": "name", "Zeit": "noun", "zeit": "prep"}
RANK |= {"Zeit": 50, "zeit": 9000}


def test_a_capitalised_word_opens_on_what_its_lower_case_opens_on() -> None:
    """The lookup tries a word as written before its lower case: Filipino's
    "May" (a sentence's first word: "there is") opened on Mayo, the month,
    and Portuguese's "A" on á, "wing". Where no treebank says (Filipino's
    are too few), the better ranked comes first, if it is a common word."""
    forms = {"may": ["may"], "Mayo": ["Mayo"], "a": ["a"], "á": ["á"], "A": ["á"]}
    forms |= {"éwé": ["éwé"], "eve": ["éwé"], "Ève": ["Ève"]}
    rank = RANK | {"éwé": 9000, "Ève": 1 << 30}  # unranked, as `assemble` gives it
    rank |= {"tourner": 300, "Tournai": 1 << 30}
    lemmas = {"May": "Mayo", "Eve": "Ève"}
    forms |= {"tourner": ["tourner"], "Tournai": ["Tournai"]}
    forms |= {"україна": ["україна"], "Україна": ["Україна"]}
    lemmas |= {"україні": "україна", "Україні": "Україна"}
    rank |= {"україна": 400, "Україна": 1 << 30}
    lemmas |= {"tournai": "tourner"}
    pos = POS | {"éwé": "noun", "Ève": "name", "tourner": "verb", "Tournai": "name"}
    pos |= {"україна": "noun", "Україна": "name"}
    assert packs.capitals_first(forms, lemmas, rank, said(pos), None) == {
        "May": ["may", "Mayo"],
        "A": ["a", "á"],
    }  # Eve stays Ève: éwé (the Ewe language) is no common word; Tournai
    # the city is its own headword, though tourner ("I turned") is common;
    # Україні is Україна's, whose lower case is the same word
    # where nouns are written with a capital, only the treebanks decide
    assert packs.capitals_first(forms, lemmas, rank, said(pos), None, True) == {}


def test_a_capitalised_word_the_treebanks_use_so_keeps_its_own() -> None:
    """Brazil stays Brasil (the treebanks use "brasil" as a name), German's
    Zeit stays "time", a noun; Portuguese's "A" gives way to the
    preposition. A word with nothing in lower case is left alone."""
    forms = {"brasil": ["brasil"], "Brasil": ["Brasil"], "Zeit": ["Zeit"]}
    forms |= {"zeit": ["zeit"], "a": ["a"], "A": ["á"], "Paris": ["Paris"]}
    uses = {
        "brasil": {"PROPN": 80, "ADJ": 1},
        "zeit": {"NOUN": 400, "ADP": 2},
        "a": {"ADP": 1057, "NOUN": 1},
    }
    rank = RANK | {"Paris": 100}
    pos = POS | {"Paris": "name"}
    assert packs.capitals_first(forms, {}, rank, said(pos), uses) == {"A": ["a", "á"]}


def test_a_used_form_opens_on_its_lemmas_entry_in_the_part_of_speech_it_is_used_as() -> (
    None
):
    """Italian's "tutti" (its own pronoun, "everybody") is used as tutto's
    determiner, "all"; tutto's row starts with the noun "whole". Its card
    opens on the determiner. Portuguese's "a" opens on o's article, and
    "la", looked up through a, keeps a's own entries."""
    draft = packs.Draft(
        [],
        {},
        came_through={("tutti", "tutto"): {"det", "pron"}, ("a", "o"): {"article"}},
        lemma_used={"tutti": frozenset({"tutto"}), "a": frozenset({"o"})},
    )
    forms = {"tutto": ["whole", "all", "everything"], "tutti": ["everybody"]}
    forms |= {"o": ["the"], "a": ["to"]}
    pos_of = {
        "whole": ("tutto", "noun"),
        "all": ("tutto", "det"),
        "everything": ("tutto", "pron"),
        "everybody": ("tutti", "pron"),
        "the": ("o", "article"),
        "to": ("a", "prep"),
    }
    lemmas = {"tutti": "tutto", "a": "o", "la": "a"}
    assert packs.opened_as_used(draft, forms, lemmas, pos_of) == {
        "tutti": ["all", "whole", "everything", "everybody"],
        "a": ["the", "to"],
        "la": ["to"],  # a's own, as before: not o's article
    }


def test_a_form_used_as_its_own_part_of_speech_keeps_its_own() -> None:
    """Italian's "il" is its own article and in lo's table as article and
    pronoun: the treebanks use it as the pronoun 3 times in 5,000."""
    words = kaikki.read_language(
        [
            obj("il", "article", sense("the")),
            {
                **obj("lo", "pron", sense("him")),
                "forms": [{"form": "il", "tags": ["masculine"]}],
            },
            {
                **obj("lo", "article", sense("the")),
                "forms": [{"form": "il", "tags": ["masculine"]}],
            },
        ]
    )
    assert packs.lemma_used(words, {"il": {"DET": 5000, "PRON": 3}}) == {}


def test_a_name_or_a_part_of_speech_the_lemma_lacks_moves_nothing() -> None:
    """Indonesian's "Indonesia" is in baja's (steel) noun table by a slip:
    the treebanks use it as a name 79 times, a noun twice. Italian's call
    "tutti" an adjective 8 times; tutto has no adjective entry."""
    words = kaikki.read_language(
        [
            obj("Indonesia", "name", sense("Indonesia")),
            obj("Indonesia", "adj", sense("Indonesian")),
            {
                **obj("baja", "noun", sense("steel")),
                "forms": [{"form": "Indonesia", "tags": ["plural"]}],
            },
            obj("tutti", "pron", sense("everybody")),
            obj("tutto", "noun", sense("whole")),
            {
                **obj("tutto", "adj", form_of("plural of tutto", "tutto")),
                "forms": [{"form": "tutti", "tags": ["plural"]}],
            },
        ]
    )
    uses = {"indonesia": {"PROPN": 79, "NOUN": 2}, "tutti": {"ADJ": 8, "NOUN": 1}}
    assert packs.lemma_used(words, uses) == {}


def test_a_forms_own_uses_are_counted_as_written(tmp_path: Path) -> None:
    """Turkish's treebanks give a verb's stem as its lemma: "dedi" (said) is
    "de"'s, so by lemma "de" (too, also) was a verb, and opened on demek, "to
    say". `lemma_used` counts each form as written."""
    bank = tmp_path / "tr.conllu"
    bank.write_text("1\tdedi\tde\tVERB\n2\tdedi\tde\tVERB\n3\tde\tde\tCCONJ\n")
    assert treebanks.uses([bank])["de"] == {"VERB": 2, "CCONJ": 1}
    assert treebanks.uses([bank], forms_only=True)["de"] == {"CCONJ": 1}
