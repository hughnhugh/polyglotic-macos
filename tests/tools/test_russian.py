"""Russian's own rules for its pack (polyglotic-hq 298): stress marks off
the written forms and onto the reading, ё spelled е, a headword's listed
forms sorted into inflections and words of their own, participles
declined. End to end on a pack: `test_packs`."""

from typing import Any

from tools.dictionaries import russian


def test_stress_marks_come_off_but_yo_and_short_i_stay() -> None:
    assert russian.unstressed("ру́ку") == "руку"
    assert russian.unstressed("тво̀рог") == "творог"  # a secondary stress
    assert russian.unstressed("ещё") == "ещё"
    assert russian.unstressed("мой") == "мой"


def test_a_word_with_yo_is_also_found_spelled_with_ye() -> None:
    assert russian.spellings("ещё") == ("ещё", "еще")
    assert russian.spellings("Королёв") == ("Королёв", "Королев")
    assert russian.spellings("дом") == ("дом",)


def test_the_reading_is_the_headword_with_its_stress_marked() -> None:
    def obj(word: str, *canonical: str) -> dict[str, object]:
        forms = [{"form": c, "tags": ["canonical"]} for c in canonical]
        return {"word": word, "forms": forms}

    assert russian.stressed(obj("рука", "рука́")) == "рука́"
    assert russian.stressed(obj("творог", "тво́рог", "творо́г")) == "тво́рог, творо́г"
    assert russian.stressed(obj("дом", "дом")) == ""  # one syllable: no mark
    assert russian.stressed(obj("ещё", "ещё")) == ""  # ё is always stressed
    assert russian.stressed(obj("дом", "до́мик")) == ""  # not this word


def test_only_inflections_and_spellings_are_a_headwords_forms() -> None:
    assert russian.is_inflection(frozenset({"accusative", "singular"}))
    assert russian.is_inflection(frozenset({"alternative"}))
    for other in ("perfective", "diminutive", "adjective relational", "feminine"):
        assert not russian.is_inflection(frozenset(other.split()))


def test_a_table_with_an_optional_prefix_gives_both_spellings() -> None:
    cleaned = russian.cleaned(
        {
            "word": "новый",
            "pos": "adj",
            "forms": [{"form": "(по)но́вее", "tags": ["comparative"]}],
            "senses": [{"glosses": ["new"]}],
        }
    )
    forms: Any = cleaned["forms"]
    assert [f["form"] for f in forms] == ["новее", "поновее"]


def test_a_participle_declines_as_an_adjective() -> None:
    assert "рассматривающее" in russian.declined("рассматривающий")
    assert "находящегося" in russian.declined("находящийся")
    said = russian.declined("сказанный")
    assert {"сказанного", "сказан", "сказано", "сказаны"} <= set(said)
    assert "сказано" not in russian.declined("сказавший")
    assert russian.declined("говоря") == ()  # adverbial: doesn't decline


def test_a_heading_sense_and_a_letters_entry_give_no_meaning() -> None:
    cleaned = russian.cleaned(
        {
            "word": "в",
            "pos": "prep",
            "senses": [
                {"glosses": ["[with prepositional]"]},
                {"glosses": ["[with prepositional]", "in, at, on"]},
            ],
        }
    )
    senses: Any = cleaned["senses"]
    assert [s["glosses"] for s in senses] == [["[with prepositional]", "in, at, on"]]
    letter: dict[str, object] = {
        "word": "я",
        "pos": "character",
        "senses": [{"glosses": ["letter"]}],
    }
    assert russian.cleaned(letter)["senses"] == []
    name = {"word": "а", "pos": "noun", "senses": [{"glosses": ["The letter А"]}]}
    assert russian.is_letter(name)


def test_each_inflection_keeps_its_own_stress() -> None:
    obj = {
        "word": "рука",
        "forms": [
            {"form": "рука́", "tags": ["canonical"]},
            {"form": "ру́ки", "tags": ["nominative", "plural"]},
            {"form": "руки́", "tags": ["genitive", "singular"]},
            {"form": "ру́чка", "tags": ["diminutive"]},  # another word
            {"form": "рук", "tags": ["genitive", "plural"]},  # nothing to mark
        ],
    }
    assert list(russian.form_readings(obj)) == [
        ("рука", "рука́"),
        ("руки", "ру́ки"),
        ("руки", "руки́"),
    ]
