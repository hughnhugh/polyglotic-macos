"""Spanish forms in the pack (polyglotic-hq project 174's hard forms, step 6
of 164): a verb form before the form's own entry when the verb explains
it ("era"), an imperative-only link weighed down ("sé"), pronominal verbs
and the forms with their reflexive pronoun attached ("levántate"), and
the forms that keep their own entry first ("casa", "neta").

The 55 cases 174 tried on simplemma run against the real pack where it's
built (POLYGLOTIC_PACKS, as `test_coverage`)."""

import os
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from tests.tools import test_packs
from tests.tools.test_packs import line, sense
from tools.dictionaries import packs
from tools.dictionaries.kaikki import Combined
from tools.dictionaries.spanish import is_reflexive

from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary


def tagged(gloss: str, lemma: str, *tags: str) -> dict[str, object]:
    return {
        "glosses": [gloss],
        "form_of": [{"word": lemma}],
        "tags": ["form-of", *tags],
    }


SPANISH = [
    line(
        "ser",
        "verb",
        sense("to be"),
        forms=[{"form": "sé", "tags": ["imperative", "second-person", "singular"]}],
    ),
    line("era", "verb", tagged("imperfect of ser", "ser", "imperfect")),
    line("era", "noun", sense("era, age")),
    line(
        "saber",
        "verb",
        sense("to know"),
        forms=[{"form": "sabe", "tags": ["third-person", "present"]}],
    ),
    line(
        "sé",
        "verb",
        tagged("first-person singular present indicative of saber", "saber", "present"),
        tagged("inflection of ser", "ser"),  # a heading: no mood of its own
        tagged("second-person singular imperative", "ser", "imperative"),
    ),
    line("sé", "intj", sense("yes")),
    line(
        "casar",
        "verb",
        sense("to marry"),
        forms=[{"form": "casa", "tags": ["third-person", "present"]}],
    ),
    line("casa", "noun", sense("house")),
    line("neto", "adj", sense("net")),
    line("neta", "noun", sense("truth")),
    line("neta", "adj", tagged("feminine singular of neto", "neto", "feminine")),
    line(
        "levantar",
        "verb",
        sense("to lift"),
        sense("to get up", tags=["reflexive"]),
    ),
    line(
        "levántate",
        "verb",
        tagged(
            "second-person singular imperative of levantar combined with te",
            "levantar",
            "imperative",
            "second-person",
            "singular",
        ),
    ),
    line(
        "levantarse",
        "verb",
        tagged("infinitive of levantar combined with se", "levantar"),
    ),
    line("decir", "verb", sense("to say")),
    line(
        "dímelo",
        "verb",
        tagged(
            "imperative of decir",
            "decir combined with indirect object me and direct object lo",
            "imperative",
            "second-person",
            "singular",
        ),
    ),
]
FREQ = {
    "es": {
        150: ["ser"],
        230: ["sabe"],
        240: ["sé"],
        250: ["era", "casa", "decir"],
        260: ["saber"],
        350: ["neto"],
        400: ["casar", "levantar", "neta"],
        450: ["levantarse", "levántate", "dímelo"],
    },
    "ja": {},
}


@pytest.fixture
def spanish(tmp_path: Path, monkeypatch: MonkeyPatch) -> BasicDictionary:
    monkeypatch.setattr(test_packs, "SPANISH", SPANISH)
    monkeypatch.setattr(test_packs, "FREQ", FREQ)
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    paths = test_packs.sources(tmp_path / "upstream")
    packs.build(packs.PACKS["es"], paths, tmp_path)
    file = SqliteDictionary(tmp_path / "wiktes.sqlite")
    return BasicDictionary(file, SpacedSplit("es"), "es")


def first(dictionary: BasicDictionary, word: str) -> tuple[str, str]:
    entry = dictionary.lookup(word)[0]
    return entry.headword, entry.meanings[0]


def test_a_verb_form_comes_before_its_own_entry_when_the_verb_explains_it(
    spanish: BasicDictionary,
) -> None:
    assert first(spanish, "era") == ("ser", "(verb) to be")
    assert [e.headword for e in spanish.lookup("era")] == ["ser", "era"]  # both


def test_an_imperative_only_link_counts_for_less(spanish: BasicDictionary) -> None:
    # ser is the commoner verb, but "sé" is ser's only as "be!"
    assert first(spanish, "sé") == ("saber", "(verb) to know")


def test_a_word_more_common_than_the_verb_explains_keeps_its_own_entry(
    spanish: BasicDictionary,
) -> None:
    assert first(spanish, "casa") == ("casa", "(noun) house")
    # a noun's or adjective's forms never go first: "neta" is truth
    assert first(spanish, "neta") == ("neta", "(noun) truth")
    # ... but the lemma is still shown, after
    assert [e.headword for e in spanish.lookup("casa")] == ["casa", "casar"]
    assert [e.headword for e in spanish.lookup("neta")] == ["neta", "neto"]


def test_a_pronominal_verb_has_its_own_entry_and_its_reflexive_forms(
    spanish: BasicDictionary,
) -> None:
    assert first(spanish, "levantarse") == ("levantarse", "(verb) to get up")
    assert first(spanish, "levántate") == ("levantarse", "(verb) to get up")
    assert first(spanish, "levantar") == ("levantar", "(verb) to lift")
    assert first(spanish, "dímelo") == ("decir", "(verb) to say")  # me isn't tú's


@pytest.mark.parametrize(
    ("pronouns", "tags", "reflexive"),
    [
        (("te",), {"imperative", "second-person", "singular"}, True),
        (("me", "lo"), {"imperative", "second-person", "singular"}, False),
        (("nos",), {"imperative", "first-person", "plural"}, True),
        (("se",), {"imperative", "third-person", "plural"}, True),
        (("se",), {"imperative", "second-person", "plural"}, True),  # ustedes
        (("os",), {"imperative", "second-person", "plural"}, True),
        (("se", "lo"), {"imperative", "second-person", "singular"}, False),
        (("se",), {"gerund"}, True),
        (("lo",), {"infinitive"}, False),
        ((), {"imperative"}, False),
    ],
)
def test_a_pronoun_is_reflexive_when_it_is_the_verbs_own_person(
    pronouns: tuple[str, ...], tags: set[str], reflexive: bool
) -> None:
    form = Combined("x", "y", pronouns, frozenset(tags))
    assert is_reflexive(form) is reflexive


# 174's 55 hard forms (lemma_probe_174.py), as the pack should answer them.
# Two differ from 174's list, on purpose: Wiktionary files comerse's
# senses under comer without a reflexive mark, so "cómetelo" is comer;
# and "riéndose" is reírse, the pronominal verb for "to laugh".
CASES_174 = [
    "fue:ser",
    "fui:ser",
    "era:ser",
    "iba:ir",
    "hizo:hacer",
    "hice:hacer",
    "pusiste:poner",
    "quiero:querer",
    "quise:querer",
    "sé:saber",
    "supe:saber",
    "tengo:tener",
    "tuvieron:tener",
    "estuvieron:estar",
    "dije:decir",
    "dijeron:decir",
    "vengo:venir",
    "voy:ir",
    "vamos:ir",
    "vámonos:irse",
    "dámelo:dar",
    "dímelo:decir",
    "haciéndolo:hacer",
    "dáselo:dar",
    "cómetelo:comer",
    "váyanse:irse",
    "levántate:levantarse",
    "acuérdate:acordarse",
    "hablábamos:hablar",
    "hablaremos:hablar",
    "hablaría:hablar",
    "hubiera:haber",
    "hayas:haber",
    "sea:ser",
    "seas:ser",
    "sido:ser",
    "oyes:oír",
    "oigo:oír",
    "huele:oler",
    "duermo:dormir",
    "durmió:dormir",
    "pidió:pedir",
    "sigue:seguir",
    "construyen:construir",
    "cayó:caer",
    "leyó:leer",
    "creí:creer",
    "riéndose:reírse",
    "güey:güey",
    "neta:neta",
    "chido:chido",
    "tío:tío",
    "coño:coño",
    "pibe:pibe",
    "boludo:boludo",
]
PACKS_BUILT = os.environ.get("POLYGLOTIC_PACKS")


@pytest.mark.skipif(not PACKS_BUILT, reason="the packs aren't built (POLYGLOTIC_PACKS)")
def test_174s_hard_forms_find_the_word_a_learner_needs() -> None:
    file = SqliteDictionary(Path(str(PACKS_BUILT)) / "wiktes.sqlite")
    spanish = BasicDictionary(file, SpacedSplit("es"), "es")
    wrong = []
    for case in CASES_174:
        form, want = case.split(":")
        found = spanish.lookup(form)
        if not found or found[0].headword != want:
            wrong.append(f"{form} -> {[e.headword for e in found[:2]]}, want {want}")
    assert not wrong, wrong
