"""English's words with meanings in learners' languages (polyglotic-hq 510,
decision 0234): `tools.dictionaries.english_pairs` reads Wiktionary's
translation tables and a language's own Wiktionary, and writes ECDICT's
meanings file in that language - each entry's lines in the order that
makes its first click right."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tools.dictionaries import english_pairs
from tools.dictionaries.english_pairs import (
    Found,
    Headword,
    Sense,
    agreeing,
    coverage,
    lines_for,
    ordered,
    read_edition,
    read_tables,
)

from polyglotic_desktop.adapters.meanings_file import SqliteMeanings

BANK = Headword("ecdict:bank", "bank", 900, ("noun", "verb"), False)


def jsonl(path: Path, entries: list[dict[str, object]]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def tr(code: str, word: str, sense: str, tags: list[str] | None = None) -> dict:
    return {"lang_code": code, "word": word, "sense": sense, "tags": tags or []}


def test_the_tables_give_a_line_per_sense_in_the_learners_language(
    tmp_path: Path,
) -> None:
    path = jsonl(
        tmp_path / "en.jsonl.gz",
        [
            {  # the river's edge first, as the page has it
                "pos": "noun",
                "senses": [{"glosses": ["An edge of a river."]}],
                "translations": [
                    tr("es", "orilla", "edge of river"),
                    tr("es", "ribera", "edge of river"),
                    tr("vi", "bờ", "edge of river"),
                ],
                "word": "bank",
                "lang_code": "en",
            },
            {
                "pos": "noun",
                "senses": [
                    {
                        "glosses": ["An institution where one can borrow money."],
                        "translations": [
                            tr("es", "banco", "institution"),
                            tr("es", "banca", "institution"),
                            tr("es", "banco", "institution"),  # once
                            tr("es", "cambista", "institution", ["obsolete"]),
                            tr("de", "Bank", "institution"),
                            tr("fr", "banque", "institution"),
                        ],
                    }
                ],
                "word": "bank",
                "lang_code": "en",
            },
            {"pos": "noun", "translations": [tr("es", "x", "y")], "word": "zzz"},
        ],
    )
    found = read_tables(path, {"bank"}, ["es", "vi"])
    assert [s.text for s in found["es"].senses["bank"]] == [
        "orilla, ribera",
        "banco, banca",
    ]
    assert [s.text for s in found["vi"].senses["bank"]] == ["bờ"]
    assert "zzz" not in found["es"].senses
    # the institution first: more languages have words for it
    assert lines_for(BANK, found["es"], None, "tables") == (
        "(noun) banco, banca",
        "(noun) orilla, ribera",
    )


def test_an_edition_gives_its_definitions_leaving_out_forms(tmp_path: Path) -> None:
    path = jsonl(
        tmp_path / "vi.jsonl.gz",
        [
            {
                "word": "bank",
                "pos": "noun",
                "lang_code": "en",
                "senses": [
                    {"glosses": ["Đê, gờ, ụ (đất, đá)."]},
                    {"glosses": ["Ngân hàng."]},
                    {"glosses": ["banks"], "tags": ["form-of"]},
                ],
            },
            {"word": "bank", "pos": "noun", "lang_code": "vi", "senses": []},
            {
                "word": "ran",
                "pos": "verb",
                "lang_code": "en",
                "senses": [
                    {"glosses": ["Quá khứ của run."], "form_of": [{"word": "run"}]}
                ],
            },
        ],
    )
    found = read_edition(path, {"bank", "ran"})
    assert [s.text for s in found.senses["bank"]] == [
        "Đê, gờ, ụ (đất, đá)",
        "Ngân hàng",
    ]
    assert "ran" not in found.senses
    tables = Found()
    tables.senses["bank"] = [Sense("noun", "institution", "ngân hàng")]
    # the edition read first, its line the tables agree with first
    assert lines_for(BANK, tables, found, "edition")[0] == "(noun) Ngân hàng"


def test_parts_of_speech_follow_englishs_own_order() -> None:
    run = Headword("ecdict:run", "run", 202, ("verb", "noun"), False)
    senses = [
        Sense("noun", "act of running", "carrera", 40),
        Sense("verb", "to flow", "fluir", 30),
        Sense("verb", "to move quickly on foot", "correr", 90),
        Sense("intj", "", "¡corre!"),
    ]
    assert [s.text for s in ordered(senses, run)] == [
        "correr",
        "fluir",
        "carrera",
        "¡corre!",
    ]
    # an edition's (no weights): the page's order stays
    plain = [Sense("verb", "", "a"), Sense("verb", "", "b")]
    assert [s.text for s in ordered(plain, run)] == ["a", "b"]
    assert agreeing(plain, None) == plain


def test_coverage_counts_the_card_englishs_commonest_words_open_on() -> None:
    words = [
        Headword("ecdict:the", "the", 1, ("article",), False),
        Headword("ecdict:ran", "ran", 2, ("verb",), True, "ecdict:run"),  # run's card
        Headword("ecdict:go", "go", 3, ("verb",), False),
        Headword("ecdict:went", "went", 3, ("verb",), False),  # rank's second
        Headword("ecdict:s", "S", 4, ("noun",), False),  # a lone letter
        Headword("ecdict:zebu", "zebu", None, ("noun",), False),
    ]
    assert coverage(words, {"ecdict:the": ("el",)}) == 1 / 3
    found = {"ecdict:the": ("el",), "ecdict:go": ("ir",), "ecdict:run": ("correr",)}
    assert coverage(words, found) == 1.0


def test_a_built_file_is_ecdicts_meanings_in_the_language(tmp_path: Path) -> None:
    tables = {"es": Found()}
    tables["es"].senses["bank"] = [Sense("noun", "institution", "banco")]
    edition = Found()
    edition.senses["bank"] = [Sense("noun", "", "Banco")]
    form = Headword("ecdict:banks", "banks", 5000, ("noun",), True, "ecdict:bank")
    stats = english_pairs.build([BANK, form], tables, {"es": edition}, ["es"], tmp_path)
    assert stats["es"]["read first"] == "tables"  # as many: the tables
    file = SqliteMeanings(tmp_path / "ecdict-es.meanings")
    try:
        assert file.meanings("ecdict:bank") == ("(noun) banco",)
        assert file.meanings("ecdict:banks") is None
        assert (file.info["dictionary"], file.info["meanings_language"]) == (
            "ecdict",
            "es",
        )
        assert file.info["licence"] == "CC BY-SA 4.0"
        assert "Spanish edition" in file.info["sources"]
    finally:
        file.close()


def test_a_senses_commonest_words_first_and_rare_ones_left_out() -> None:
    frequency = {"correr": 1e-4, "cosa": 1e-3, "banco": 1e-4, "banca": 1e-5}
    assert english_pairs.commonest_first(["correr", "apeonar"], frequency) == ["correr"]
    assert english_pairs.commonest_first(["banca", "banco"], frequency) == [
        "banco",
        "banca",
    ]
    said = ["tener la cuenta en", "zzz"]  # a phrase stays; none known: as is
    assert english_pairs.commonest_first(said, frequency) == said
    assert english_pairs.commonest_first(["b", "a"], {}) == ["b", "a"]


def test_a_determiner_sorts_with_englishs_adjectives() -> None:
    """WordNet files "any" as an adjective: Wiktionary's determiner is it."""
    any_ = Headword("ecdict:any", "any", 96, ("adj", "adv"), False)
    senses = [Sense("adv", "", "algo"), Sense("det", "", "cualquier")]
    assert [s.text for s in ordered(senses, any_)] == ["cualquier", "algo"]


def test_a_word_with_alternatives_counts_as_its_first() -> None:
    frequency = {"necesitar": 1e-4, "ocupar": 1e-5}
    said = ["ocupar", "necesitar/precisar (de)", "hacer(le) falta"]
    assert english_pairs.commonest_first(said, frequency)[:2] == [
        "necesitar/precisar (de)",
        "ocupar",
    ]


def test_ecdicts_chinese_order_says_which_sense_is_commonest() -> None:
    """More languages name a beak than an invoice; ECDICT's Chinese puts the
    invoice first, then the banknote, then the beak - and so does the card."""
    bill = Headword(
        "ecdict:bill",
        "bill",
        655,
        ("noun",),
        False,
        chinese=(("noun", "帐单"), ("noun", "钞票"), ("noun", "鸟嘴")),
    )
    senses = [
        Sense("noun", "beak", "pico", 120, ("鳥嘴", "鸟嘴")),
        Sense("noun", "banknote", "billete", 60, ("鈔票", "钞票", "纸币")),
        Sense("noun", "invoice", "factura, cuenta", 80, ("帐单", "账单")),
        Sense("noun", "draft law", "proyecto de ley", 90, ()),
    ]
    assert [s.text for s in ordered(senses, bill)] == [
        "factura, cuenta",
        "billete",
        "pico",
        "proyecto de ley",
    ]


def test_stress_marks_and_jawi_dont_hide_a_word(tmp_path: Path) -> None:
    frequency = {"этот": 1e-3, "сей": 1e-6}
    assert english_pairs.commonest_first(["сей", "э́тот"], frequency) == [
        "э́тот",
        "сей",
    ]
    path = jsonl(
        tmp_path / "en.jsonl.gz",
        [
            {
                "pos": "noun",
                "translations": [
                    tr("ms", "rang undang-undang", "law"),
                    tr("ms", "رڠ", "law"),
                ],
                "word": "bill",
                "lang_code": "en",
            }
        ],
    )
    found = read_tables(path, {"bill"}, ["ms"])
    assert [s.text for s in found["ms"].senses["bill"]] == ["rang undang-undang"]


def test_two_senses_ecdict_says_alike_keep_the_pages_order() -> None:
    hide = Headword(
        "ecdict:hide",
        "hide",
        900,
        ("verb",),
        False,
        chinese=(
            ("noun", "躲藏处"),
            ("verb", "藏"),
            ("verb", "隐藏"),
            ("verb", "躲藏"),
        ),
    )
    senses = [
        Sense("verb", "put out of sight", "ocultar", 50, ("藏",)),
        Sense("verb", "put oneself out of sight", "esconderse", 70, ("躲藏", "隐藏")),
    ]
    assert [s.text for s in ordered(senses, hide)] == ["ocultar", "esconderse"]
