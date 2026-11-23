import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from tools.dictionaries.packs import Built, records_for
from tools.dictionaries.reviewed_classes import apply_reviews
from tools.dictionaries.sense_classes import jm, legacy_wikt

from polyglotic_desktop.adapters.sqlite_dictionary import (
    SqliteDictionary,
    write_dictionary,
)
from polyglotic_desktop.core.lexicon.chinese import entry_from_record
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_classes import WordClass

NOUN = WordClass.NOUN
VERB = WordClass.VERB
ADVERB = WordClass.ADVERB


def test_optional_sense_classes_follow_all_lookup_routes(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite"
    entry = EntryRecord(
        "dict:1",
        "guarantee",
        "",
        "",
        ("(verb) to promise", "(law) an assurance", "other", "pending"),
        sense_classes=((VERB,), (NOUN, VERB), (), None),
        sense_prefixes=(7, 0, 0, 0),
    )
    other = EntryRecord("dict:2", "guarantee", "", "", ("a promise",))
    write_dictionary(
        path,
        {},
        [entry, other],
        {"guarantee": [other.entry_id, entry.entry_id]},
        {"promise": [entry.entry_id]},
        merged={"dict:old": entry.entry_id},
    )
    file = SqliteDictionary(path)
    assert file.records("guarantee") == [other, entry]
    assert file.records_by_meaning("promise", 1) == [entry]
    assert file.record("dict:old") == entry
    assert [
        (sense.gloss, sense.classes) for sense in entry_from_record(entry).senses
    ] == [
        ("to promise", (VERB,)),
        ("(law) an assurance", (NOUN, VERB)),
        ("other", ()),
        ("pending", None),
    ]
    file.close()

    for extension in (None, "2", "1"):
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM info WHERE key = 'sense_classes_version'")
            if extension is not None:
                db.execute(
                    "INSERT INTO info VALUES ('sense_classes_version', ?)", (extension,)
                )
            if extension == "1":
                db.execute("DROP TABLE sense_classes")
        file = SqliteDictionary(path)
        assert file.records("guarantee") == [
            other,
            replace(entry, sense_classes=(), sense_prefixes=()),
        ]
        file.close()


def test_the_schema_refuses_classes_for_nonexistent_glosses(tmp_path: Path) -> None:
    entry = EntryRecord(
        "dict:1", "test", "", "", ("to test",), sense_classes=((VERB,), (NOUN,))
    )
    with pytest.raises(ValueError, match="classes must follow"):
        write_dictionary(tmp_path / "bad.sqlite", {}, [entry], {})


def test_native_variant_owns_its_class_order_and_fallback_keeps_its_source() -> None:
    entry = EntryRecord(
        "dict:1",
        "garantía",
        "",
        "",
        ("an assurance", "to promise"),
        sense_classes=((NOUN,), (VERB,)),
    )
    built = Built(
        [entry],
        {},
        {},
        {entry.entry_id: ("保证", "担保")},
        {},
        {},
        {entry.entry_id: ((VERB,), (NOUN,))},
    )
    assert records_for(built, "en") == [entry]
    assert records_for(built, "zh") == [
        replace(entry, meanings=("保证", "担保"), sense_classes=((VERB,), (NOUN,)))
    ]
    assert records_for(replace(built, zh={}), "zh") == [entry]
    assert records_for(replace(built, zh_classes={}), "zh")[0].sense_classes == ()
    assert legacy_wikt(("(noun) (law) an assurance", "(law) protection"), "noun") == (
        ((NOUN,), None),
        (7, 0),
    )
    assert jm(("vs", "n-adv")) == (NOUN, ADVERB)
    assert jm(("v5r", "vt")) == (VERB,)
    assert jm(("n", "exp")) is None


def test_a_pending_draft_needs_review_and_the_exact_frozen_sense(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cedict.sqlite"
    entry = EntryRecord(
        "cedict:1", "保证", "保證", "bao3 zheng4", ("to promise", "an assurance")
    )
    write_dictionary(path, {"language": "zh", "meanings_language": "en"}, [entry], {})
    review = {
        "language": "zh",
        "gloss_language": "en",
        "entry_id": entry.entry_id,
        "headword": entry.headword,
        "reading": entry.reading,
        "ordinal": 0,
        "gloss": entry.meanings[0],
        "source_ref": "CC-CEDICT",
        "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "gloss_sha256": hashlib.sha256(entry.meanings[0].encode()).hexdigest(),
        "classes": ["verb"],
        "human_reviewed": False,
    }
    draft = path.with_suffix(".json")
    moved = replace(entry, meanings=("an assurance", "to promise"))
    draft.write_text(json.dumps([review]), encoding="utf-8")
    assert apply_reviews([moved], tmp_path, "cedict", "zh", "en") == ([moved], {}, 0)

    review.update(human_reviewed=True, reviewer="Lexical reviewer")
    draft.write_text(json.dumps([review]), encoding="utf-8")
    records, provenance, count = apply_reviews([moved], tmp_path, "cedict", "zh", "en")
    assert records[0].sense_classes == (None, (VERB,))
    assert "sense_classes_review" in provenance and count == 1

    ambiguous = replace(moved, meanings=("to promise", "to promise"))
    records, _, count = apply_reviews([ambiguous], tmp_path, "cedict", "zh", "en")
    assert records == [ambiguous] and count == 0
