"""The Anki deck file (project 099): built, then read back as Anki reads
it - the zip, the collection's SQLite - with no Anki installed. Checks the
note types, decks and GUIDs are fixed across exports, the CSV's words are
the deck's, both Chinese and English work, 行 háng and 行 xíng stay two
notes, and every text is escaped."""

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore

from polyglotic_desktop.adapters.anki_package import (
    FIELDS,
    NOTE_TYPES_CHANGED,
    GenankiDeckWriter,
)
from polyglotic_desktop.core.learning.anki import AnkiNote, deck_notes, guid
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import EntryText, Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ports.anki_deck import DeckSentence

HANG = EntryId("cedict:行-háng")
XING = EntryId("cedict:行-xíng")
DURIAN = EntryId("cedict:榴莲")
RUN = EntryId("ecdict:run")
TEXTS = {
    HANG: EntryText("行", "行", "háng", "row; profession"),
    XING: EntryText("行", "行", "xíng", "to walk; OK"),
    DURIAN: EntryText("榴莲", "榴槤", "liú lián", "durian <fruit> & more"),
    RUN: EntryText("run", "", "/rʌn/", "to move fast"),
}
WHEN = datetime(2026, 11, 6, tzinfo=UTC)


@dataclass
class Collection:
    """What Anki reads from an .apkg."""

    models: dict[str, dict[str, Any]]  # by note type name
    decks: dict[str, str]  # deck ID -> name
    notes: dict[str, dict[str, str]]  # guid -> field name -> value
    note_tags: dict[str, str]
    note_models: dict[str, str]  # guid -> note type name
    cards: dict[str, list[int]]  # guid -> template ordinals


def read_apkg(data: bytes) -> Collection:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert set(archive.namelist()) == {"collection.anki2", "media"}
        assert json.loads(archive.read("media")) == {}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "c.anki2"
            path.write_bytes(archive.read("collection.anki2"))
            db = sqlite3.connect(path)
            try:
                models_json, decks_json = db.execute(
                    "SELECT models, decks FROM col"
                ).fetchone()
                models = json.loads(models_json)
                decks = {k: v["name"] for k, v in json.loads(decks_json).items()}
                names = {k: v["name"] for k, v in models.items()}
                field_names = {
                    k: [f["name"] for f in v["flds"]] for k, v in models.items()
                }
                notes, tags, note_models, ids = {}, {}, {}, {}
                for nid, guid_, mid, tag, flds in db.execute(
                    "SELECT id, guid, mid, tags, flds FROM notes"
                ):
                    notes[guid_] = dict(
                        zip(field_names[str(mid)], flds.split("\x1f"), strict=True)
                    )
                    tags[guid_] = tag.strip()
                    note_models[guid_] = names[str(mid)]
                    ids[nid] = guid_
                cards: dict[str, list[int]] = {g: [] for g in notes}
                for nid, ord_ in db.execute("SELECT nid, ord FROM cards"):
                    cards[ids[nid]].append(ord_)
            finally:
                db.close()
    return Collection(
        {names[k]: models[k] for k in models},
        decks,
        notes,
        tags,
        note_models,
        {g: sorted(c) for g, c in cards.items()},
    )


def note(entry_id: EntryId, sentence: str = "", translation: str = "") -> AnkiNote:
    t = TEXTS[entry_id]
    return AnkiNote(
        entry_id, t.headword, t.traditional, t.reading, t.meaning,
        sentence, translation, "", WHEN, WHEN,
    )  # fmt: skip


def build(notes: list[AnkiNote], **options: bool) -> Collection:
    listen, recall = options.get("listen", False), options.get("recall", False)
    built = GenankiDeckWriter().build(deck_notes(notes), listen=listen, recall=recall)
    return read_apkg(built)


def test_chinese_and_english_notes_go_in_their_own_note_type_and_sub_deck() -> None:
    c = build(
        [note(DURIAN, "他爱吃榴莲。", "He loves durian."), note(RUN, "I run daily.")]
    )
    zh, en = c.notes[guid(DURIAN)], c.notes[guid(RUN)]
    assert list(zh) == list(FIELDS)
    assert list(FIELDS) == [
        "Word", "Reading", "Meaning", "Sentence", "Translation", "WordAudio",
        "SentenceAudio", "Source", "Traditional", "Notes", "Listen", "Recall", "EntryID",
    ]  # fmt: skip
    assert zh["Word"] == "榴莲" and zh["Traditional"] == "榴槤"
    assert zh["Sentence"] == "他爱吃<b>榴莲</b>。" and zh["EntryID"] == DURIAN
    assert zh["WordAudio"] == zh["SentenceAudio"] == ""
    assert en["Word"] == "run" and en["Traditional"] == ""
    assert en["Sentence"] == "I <b>run</b> daily."
    assert c.note_models[guid(DURIAN)] == "Polyglotic Chinese"
    assert c.note_models[guid(RUN)] == "Polyglotic English"
    assert {"Polyglotic::Chinese", "Polyglotic::English"} <= set(c.decks.values())
    assert c.note_tags[guid(DURIAN)] == "polyglotic"


def test_the_same_word_is_the_same_note_in_every_export() -> None:
    first = build([note(DURIAN, "a"), note(RUN)])
    second = build([note(RUN), note(DURIAN, "a changed 榴莲")])
    assert set(first.notes) == set(second.notes) == {guid(DURIAN), guid(RUN)}
    for name in ("Polyglotic Chinese", "Polyglotic English"):
        assert first.models[name]["id"] == second.models[name]["id"]
    assert sorted(first.decks) == sorted(second.decks)  # deck IDs too
    assert second.notes[guid(DURIAN)]["Sentence"] == "a changed <b>榴莲</b>"


def test_two_readings_of_one_headword_stay_two_notes() -> None:
    c = build([note(HANG, "银行"), note(XING, "不行")])
    assert guid(HANG) != guid(XING) and len(c.notes) == 2
    assert c.notes[guid(HANG)]["Reading"] == "háng"
    assert c.notes[guid(XING)]["Reading"] == "xíng"
    assert c.notes[guid(HANG)]["Word"] == c.notes[guid(XING)]["Word"] == "行"


def test_text_is_escaped() -> None:
    c = build([note(DURIAN, "<script>榴莲</script> & co", "<i>x</i>")])
    fields = c.notes[guid(DURIAN)]
    assert fields["Meaning"] == "durian &lt;fruit&gt; &amp; more"
    assert fields["Sentence"] == "&lt;script&gt;<b>榴莲</b>&lt;/script&gt; &amp; co"
    assert fields["Translation"] == "&lt;i&gt;x&lt;/i&gt;"
    assert "<script" not in "".join(fields.values())


def test_recognise_always_listen_and_recall_when_asked() -> None:
    assert build([note(DURIAN, "榴莲")]).cards[guid(DURIAN)] == [0]
    both = build([note(DURIAN, "榴莲")], listen=True, recall=True)
    assert both.cards[guid(DURIAN)] == [0, 1, 2]
    assert build([note(DURIAN)], listen=True).cards[guid(DURIAN)] == [0, 1]


def test_cards_use_tts_and_no_javascript() -> None:
    c = build([note(DURIAN), note(RUN)], listen=True)
    model = c.models["Polyglotic Chinese"]
    templates = " ".join(t["qfmt"] + t["afmt"] for t in model["tmpls"])
    css = str(model["css"])
    assert "{{tts zh_CN:Word}}" in templates and "{{tts zh_CN:Sentence}}" in templates
    assert "<script" not in templates + css
    assert ".nightMode" in css and "#ffa8cc" in css and "#5c2440" in css
    english = " ".join(t["qfmt"] for t in c.models["Polyglotic English"]["tmpls"])
    assert "{{tts en_US:Word}}" in english


def times(data: bytes) -> tuple[dict[str, int], dict[str, int]]:
    """Each note's time by GUID and each note type's by name, in seconds."""
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        tempfile.TemporaryDirectory() as folder,
    ):
        path = Path(folder) / "c.anki2"
        path.write_bytes(archive.read("collection.anki2"))
        db = sqlite3.connect(path)
        try:
            notes = dict(db.execute("SELECT guid, mod FROM notes").fetchall())
            (models,) = db.execute("SELECT models FROM col").fetchone()
        finally:
            db.close()
    return notes, {m["name"]: m["mod"] for m in json.loads(models).values()}


def test_each_note_carries_when_its_word_changed_not_when_it_was_written() -> None:
    """Anki updates a note or note type it has only from a newer one."""
    learned = datetime(2026, 11, 5, 8, 30, tzinfo=UTC)
    notes = [note(DURIAN), replace(note(RUN), changed=learned)]
    note_times, note_type_times = times(GenankiDeckWriter().build(deck_notes(notes)))
    assert note_times == {
        guid(DURIAN): int(WHEN.timestamp()),
        guid(RUN): int(learned.timestamp()),
    }
    changed = int(NOTE_TYPES_CHANGED.timestamp())
    assert note_type_times == {
        "Polyglotic Chinese": changed,
        "Polyglotic English": changed,
    }


NOTE_TYPES = (
    datetime(2026, 11, 7, 12, 5, tzinfo=UTC),
    "078e3b5dd4755c36",
)
"""`NOTE_TYPES_CHANGED` and the note types' fingerprint at that time."""


def test_changed_cards_carry_a_new_note_types_changed() -> None:
    """Anki takes our note types' cards and style into a deck already
    imported only from a newer note type: a change to them must come with
    a new `NOTE_TYPES_CHANGED` (the time of the change), or it never
    reaches anyone who has imported a deck. Change both lines above."""
    c = build([note(DURIAN), note(RUN)])
    shape = {
        name: (model["css"], [f["name"] for f in model["flds"]],
               [(t["name"], t["qfmt"], t["afmt"]) for t in model["tmpls"]])
        for name, model in sorted(c.models.items())
    }  # fmt: skip
    digest = hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:16]
    assert (NOTE_TYPES_CHANGED, digest) == NOTE_TYPES


def test_an_empty_export_is_still_a_valid_file() -> None:
    assert build([]).notes == {}


def test_nothing_is_left_in_the_temp_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a temp folder of the test's own: the PC's is shared with other
    test runs making the same folders (polyglotic-hq 197)."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    made: list[str] = []
    real = tempfile.TemporaryDirectory

    def recorded(*args: Any, **kwargs: Any) -> tempfile.TemporaryDirectory[str]:
        folder = real(*args, **kwargs)
        made.append(folder.name)
        return folder

    monkeypatch.setattr(tempfile, "TemporaryDirectory", recorded)
    GenankiDeckWriter().build(deck_notes([note(DURIAN)]))
    assert [Path(name).parent for name in made] == [tmp_path]  # it used this one
    assert list(tmp_path.iterdir()) == []


def _facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return EntryFacts(entry_id, 1, 100, False) if entry_id in TEXTS else None


def test_the_csv_and_the_deck_file_carry_the_same_words_and_guids() -> None:
    clock = Clock()
    vocab = Vocabulary(MemoryLearningStore(), _facts, "hsk-2025", clock)
    vocab.learn(HANG, TEXTS[HANG], LookupContext("银行", "bank"))
    clock.advance(minutes=1)
    vocab.learn(XING, TEXTS[XING], LookupContext("不行", "no good"))
    export = vocab.export_anki()
    assert [n.guid for n in export.notes] == [guid(HANG), guid(XING)]
    for n in export.notes:
        assert n.guid in export.text
    c = read_apkg(GenankiDeckWriter().build(export.notes))
    assert set(c.notes) == {guid(HANG), guid(XING)}
    vocab.mark_exported(export.entry_ids)
    assert vocab.export_anki(only_new=True).notes == ()


# -- a pack language's words (decision 0175; polyglotic-hq 391) --------------

HOUSE = EntryId("wiktru:дом")
EAT = EntryId("jmdict:食べる")
TEXTS[HOUSE] = EntryText("дом", "", "дом", "house; home")
TEXTS[EAT] = EntryText("食べる", "", "たべる", "to eat")


def pack_build(language: str, notes: list[AnkiNote]) -> Collection:
    return read_apkg(GenankiDeckWriter().build(deck_notes(notes, language)))


def test_a_pack_languages_words_go_in_its_own_note_type_and_sub_deck() -> None:
    c = pack_build("ru", [note(HOUSE, "Это мой Дом.", "This is my house.")])
    russian = c.notes[guid(HOUSE)]
    assert list(russian) == list(FIELDS)  # the same fields as Chinese's
    assert russian["Word"] == "дом" and russian["Traditional"] == ""
    assert russian["Reading"] == "дом" and russian["Meaning"] == "house; home"
    assert russian["Sentence"] == "Это мой <b>Дом</b>."  # any case
    assert russian["Translation"] == "This is my house."
    assert russian["EntryID"] == HOUSE
    assert c.note_models[guid(HOUSE)] == "Polyglotic Russian"
    assert "Polyglotic::Russian" in set(c.decks.values())
    model = c.models["Polyglotic Russian"]
    templates = " ".join(t["qfmt"] + t["afmt"] for t in model["tmpls"])
    assert "{{tts ru_RU:Word}}" in templates and "{{tts ru_RU:Sentence}}" in templates
    assert "YaHei" not in model["css"]  # the card's own font, not a Chinese one


def test_a_japanese_word_with_kanji_is_japanese_not_chinese() -> None:
    c = pack_build("ja", [note(EAT, "パンを食べる。")])
    assert c.note_models[guid(EAT)] == "Polyglotic Japanese"
    assert c.notes[guid(EAT)]["Sentence"] == "パンを<b>食べる</b>。"
    model = c.models["Polyglotic Japanese"]
    assert "Yu Gothic UI" in model["css"] and "YaHei" not in model["css"]
    assert "{{tts ja_JP:Word}}" in model["tmpls"][0]["qfmt"]


def ids(data: bytes) -> tuple[set[str], set[str]]:
    """The note type IDs and deck IDs in a deck file (Anki's own default
    deck, 1, left out)."""
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        tempfile.TemporaryDirectory() as folder,
    ):
        path = Path(folder) / "c.anki2"
        path.write_bytes(archive.read("collection.anki2"))
        db = sqlite3.connect(path)
        try:
            models, decks = db.execute("SELECT models, decks FROM col").fetchone()
        finally:
            db.close()
    return set(json.loads(models)), set(json.loads(decks)) - {"1"}


def test_each_languages_note_type_and_deck_keep_their_ids_for_good() -> None:
    """Anki knows a note type and a deck by number: a language's must be
    the same in every export, and no two languages' the same - worked out
    from the code, so a language added later needs no table."""
    writer = GenankiDeckWriter()
    russian = ids(writer.build(deck_notes([note(HOUSE)], "ru")))
    assert russian == ({"1791610507"}, {"1791640507"})  # r=18, u=21: 18*27+21
    assert ids(writer.build(deck_notes([note(HOUSE)], "ru"))) == russian
    seen: set[str] = set()
    codes = ["ja", "es", "ko", "fr", "de", "pt", "it", "ru", "vi", "nl", "id", "ar",
             "hi", "pl", "tr", "ms", "th", "yue", "xx", "aa", "zzz"]  # fmt: skip
    for code in codes:
        models, decks = ids(writer.build(deck_notes([note(HOUSE)], code)))
        assert len(models) == len(decks) == 1
        assert not (models | decks) & seen, code
        seen |= models | decks
    chinese = ids(writer.build(deck_notes([note(DURIAN), note(RUN)])))
    assert chinese == (
        {"1791606001", "1791606002"},
        {"1791606101", "1791606102"},
    )  # as they always were
    assert not (chinese[0] | chinese[1]) & seen


def test_a_language_with_no_name_here_yet_still_exports() -> None:
    c = pack_build("xx", [note(HOUSE)])
    assert c.note_models[guid(HOUSE)] == "Polyglotic xx"
    assert "Polyglotic::xx" in set(c.decks.values())


SENTENCE_TYPE = (datetime(2026, 11, 7, 12, 5, tzinfo=UTC), "c0b34a6b5fd2166c")
"""`NOTE_TYPES_CHANGED` and the sentence note type's fingerprint then
(polyglotic-hq 459): a change to its cards or style needs a new time too."""


def test_a_changed_sentence_card_carries_a_new_note_types_changed() -> None:
    sentence = DeckSentence(
        "polyglotic:sentence:a", "zh", "我", "我", "I", "", "a", ("polyglotic",), WHEN
    )
    c = read_apkg(GenankiDeckWriter().build([], sentences=[sentence]))
    model = c.models["Polyglotic Chinese sentence"]
    shape = (
        model["css"],
        [f["name"] for f in model["flds"]],
        [(t["name"], t["qfmt"], t["afmt"]) for t in model["tmpls"]],
    )
    digest = hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:16]
    assert (NOTE_TYPES_CHANGED, digest) == SENTENCE_TYPE
    assert c.note_models == {"polyglotic:sentence:a": "Polyglotic Chinese sentence"}
    assert c.decks[str(1_791_606_101)] == "Polyglotic::Chinese"
