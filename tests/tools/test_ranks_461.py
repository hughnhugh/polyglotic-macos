"""Ranks that a word took from another word's spelling, found by 448's and
461's audits of the published packs (polyglotic-hq 448, 461): a lower-case
list can't tell German's "herzen" (to hug) from Herzen (hearts), nor
Spanish's mercedar's form "mercedes" from the name."""

from __future__ import annotations

from tools.dictionaries import kaikki, packs


def sense(gloss: str, *tags: str) -> dict[str, object]:
    return {"glosses": [gloss], "tags": list(tags)}


def obj(word: str, pos: str, *senses: dict[str, object], **more: object) -> dict:
    return {"word": word, "pos": pos, "senses": list(senses), **more}


def row(form: str, *tags: str) -> dict[str, object]:
    return {"form": form, "tags": list(tags)}


def test_a_word_that_looks_like_a_nouns_form_keeps_its_own_share() -> None:
    """German's "herzen" is met as Herzen, Herz's plural, far more than as
    the verb: the verb's forms are rare, so it keeps at most ten times
    theirs, and then theirs. "leben", whose forms are common, keeps its own; Herz keeps
    Herzen's, as before."""
    words = kaikki.read_language(
        [
            obj("Herz", "noun", sense("heart"), forms=[row("Herzen", "plural")]),
            obj("herzen", "verb", sense("to hug"), forms=[row("herzt", "present")]),
            obj("Leben", "noun", sense("life"), forms=[row("Lebens", "genitive")]),
            obj("leben", "verb", sense("to live"), forms=[row("lebt", "present")]),
        ]
    )
    draft = packs.draft_of(words)
    draft.capitalised = packs.capitalised_nouns(words)
    freq = {
        "herz": 0.0002,
        "herzen": 0.0001,
        "herzt": 0.000001,
        "leben": 0.0005,
        "lebens": 0.0001,
        "lebt": 0.0001,
    }
    total = packs.frequencies(draft, freq)
    assert abs(total["herzen|verb|"] - 0.000001 * (1 / packs.DECLINED + 1)) < 1e-12
    assert total["Herz|noun|"] > 0.0002
    assert total["leben|verb|"] >= 0.0005


def test_a_name_or_a_nouns_headword_says_nothing_of_a_words_use() -> None:
    """French's "soleil" (sun) has a name too, Soleil, and German's
    "bisschen" a noun, Bisschen: their rare plurals had cut both out of the
    top 1,000. Only a noun's inflected form counts as a look-alike."""
    words = kaikki.read_language(
        [
            obj("Soleil", "name", sense("the Sun")),
            obj("soleil", "noun", sense("sun"), forms=[row("soleils", "plural")]),
        ]
    )
    freq = {"soleil": 0.0002, "soleils": 0.000001}
    total = packs.frequencies(packs.draft_of(words), freq)
    assert total["soleil|noun|"] >= 0.0002


def test_a_verbs_form_spelled_as_a_noun_shares_with_the_noun() -> None:
    """herzen's imperative "herz" is Herz in lower case, and its table
    lists its auxiliary "haben": herzen had taken Herz's frequency through
    "herz", and stayed 536th. It now shares "herz" with Herz, in proportion
    to each one's own; "haben" is a word of its own, no measure of herzen."""
    words = kaikki.read_language(
        [
            obj("Herz", "noun", sense("heart"), forms=[row("Herzen", "plural")]),
            obj(
                "herzen",
                "verb",
                sense("to hug"),
                forms=[
                    row("herzt", "present"),
                    row("herz", "imperative"),
                    row("haben", "auxiliary"),
                ],
            ),
            obj("haben", "verb", sense("to have")),
        ]
    )
    draft = packs.draft_of(words)
    draft.capitalised = packs.capitalised_nouns(words)
    draft.split_shared_forms = True
    freq = {"herz": 0.0002, "herzen": 0.0001, "herzt": 0.000001, "haben": 0.003}
    total = packs.frequencies(draft, freq)
    assert total["herzen|verb|"] < 0.00003  # had been 0.0003
    assert total["Herz|noun|"] > 0.0002


def test_a_noun_whose_lower_case_is_only_a_verbs_form_keeps_its_share() -> None:
    """German's "wasser" is wassern's imperative and Wasser in lower case:
    Wasser had no frequency, was cut from the pack, and "Wasser" opened on
    wassern, "to land on water". It now takes at most ten times its own
    forms' (Wassers); a noun with none (Habe: "habe" is haben's) keeps none."""
    words = kaikki.read_language(
        [
            obj("Wasser", "noun", sense("water"), forms=[row("Wassers", "genitive")]),
            obj(
                "wassern",
                "verb",
                sense("to land on water"),
                forms=[row("wasser", "imperative")],
            ),
            obj("Habe", "noun", sense("belongings")),
            obj("haben", "verb", sense("to have"), forms=[row("habe", "first-person")]),
        ]
    )
    draft = packs.draft_of(words)
    draft.capitalised = packs.capitalised_nouns(words)
    freq = {"wasser": 0.0002, "wassers": 0.000005, "wassern": 0.000001, "habe": 0.003}
    total = packs.frequencies(draft, freq)
    assert abs(total["Wasser|noun|"] - (0.00005 + 0.000005)) < 1e-12  # and Wassers
    assert abs(total["wassern|verb|"] - (0.000001 + 0.0002 - 0.00005)) < 1e-12
    assert total["Habe|noun|"] == 0.0
