"""What the app exports for Anki, imported into a real Anki collection
(polyglotic-hq project 152).

Anki's own engine - the `anki` package on PyPI, the code inside Anki's
desktop app (AGPL-3.0; a dev dependency only, never in the installed app) -
opens a throwaway collection in the test's temp folder, and the deck file
and the CSV go in as Anki's File > Import puts them, with the options its
import screen starts with. Nothing here opens a learner's own Anki: no
profile folder is read or written.

The words go through the app's own path: `Vocabulary.learn` / `save`, then
`export_deck` and `export_csv`, the functions the Words page writes its
files with. What this proves on every change to the export:
- the note types, their fields and cards, the decks and tags, as Anki reads
  them; each card's faces as Anki renders them, never blank;
- Chinese and English text, escaped, arriving as it was written;
- no media, and nothing for Anki's Check Database or Empty Cards to find;
- importing an updated export updates the notes rather than doubling them,
  from the deck file and from the CSV;
- exporting an unchanged word again leaves the learner's own edits to its
  note alone, and a change to our cards reaches a deck already imported;
- the learner's own notes, note types, decks and study progress untouched;
- the CSV through Anki's importer, as the file maps itself (Basic) and
  mapped into a note type of the learner's own.
A known gap is marked `xfail(strict=True)` with the reason: it passes the
day it's fixed, and the marker must then go.

Anki's Python side keeps note types it has read in a cache that an import
doesn't clear, so `note_type` reads them afresh: reading the cache made a
changed style look as if it hadn't arrived (project 152).
"""

import csv
import html
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from anki.collection import (  # first: anki's own modules import each other
    CardId,
    Collection,
    ImportAnkiPackageRequest,
    ImportCsvRequest,
    RustBackend,
)
from anki.import_export_pb2 import CsvMetadata, CsvMetadataRequest, ImportResponse
from anki.models import NotetypeDict, NotetypeId
from anki.notes import Note
from tests.learning.fakes import Clock, MemoryLearningStore

from polyglotic_desktop.adapters import anki_package
from polyglotic_desktop.adapters.anki_package import FIELDS, GenankiDeckWriter
from polyglotic_desktop.core.learning.anki import COLUMNS, guid
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import EntryText, Vocabulary
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ui_next.words_page import export_csv, export_deck

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
NOTE_TYPES = {"Polyglotic Chinese": 1_791_606_001, "Polyglotic English": 1_791_606_002}
BLANK = "The front of this card is blank"  # Anki's text for a card with nothing to ask


@dataclass
class Learner:
    """What the Words page's export functions need (`WordsLearner`)."""

    vocabulary: Vocabulary
    clock: Clock
    deck_writer: GenankiDeckWriter = field(default_factory=GenankiDeckWriter)
    is_chinese: bool = True
    reading_ahead: bool = False
    language: str = "zh"

    def entry(self, entry_id: EntryId) -> DictionaryEntry | None:
        return None

    def describe(self, entry_id: EntryId) -> EntryText | None:
        return TEXTS.get(entry_id)

    def band_sizes(self) -> tuple[list[int], dict[int, int]]:
        return [0, 0, 0, 0], {}

    def learn(self, entry_id: EntryId, sentence: str, translation: str = "") -> None:
        self.clock.advance(minutes=1)
        self.vocabulary.learn(
            entry_id, TEXTS[entry_id], LookupContext(sentence, translation)
        )

    def save(self, entry_id: EntryId, sentence: str) -> None:
        """Saved into "Tricky", not put in the deck."""
        self.clock.advance(minutes=1)
        t = TEXTS[entry_id]
        self.vocabulary.save(
            entry_id, t.headword, t.traditional, t.reading, t.meaning, "tricky",
            LookupContext(sentence),
        )  # fmt: skip


def _facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return EntryFacts(entry_id, 1, 100, False) if entry_id in TEXTS else None


@pytest.fixture
def learner() -> Learner:
    """The app's clock, an hour ago and a minute on for each word learned:
    Anki stamps the learner's own edits with the real time, after the
    words were learned, as in the app."""
    clock = Clock(datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1))
    vocabulary = Vocabulary(MemoryLearningStore(), _facts, "hsk-2025", clock)
    return Learner(vocabulary, clock)


@pytest.fixture
def anki(tmp_path: Path) -> Iterator[Collection]:
    """A new, empty collection of our own, as a new Anki profile has."""
    collection = Collection(str(tmp_path / "collection.anki2"))
    yield collection
    collection.close()


# -- importing, as Anki's File > Import does ---------------------------------------


class Files:
    """The exports, each to a new file in the test's folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.count = 0

    def path(self, suffix: str) -> Path:
        self.count += 1
        return self.folder / f"export-{self.count}{suffix}"


@pytest.fixture
def files(tmp_path: Path) -> Files:
    return Files(tmp_path)


def import_deck(
    anki: Collection, learner: Learner, files: Files, **cards: bool
) -> ImportResponse.Log:
    """The learner's words written as the Words page writes the deck file
    (`listen` / `recall` switch on those cards), then imported with the
    options Anki's import screen starts with."""
    path = files.path(".apkg")
    if cards:
        export = learner.vocabulary.export_anki(learner.describe)
        listen, recall = cards.get("listen", False), cards.get("recall", False)
        built = learner.deck_writer.build(export.notes, listen=listen, recall=recall)
        path.write_bytes(built)
    else:
        export_deck(learner, path)
    options = anki._backend.get_import_anki_package_presets()
    request = ImportAnkiPackageRequest(package_path=str(path), options=options)
    return anki.import_anki_package(request).log


def write_csv(learner: Learner, files: Files) -> Path:
    path = files.path(".csv")
    export_csv(learner, path)
    return path


def csv_mapping(anki: Collection, path: Path, note_type_id: int = 0) -> CsvMetadata:
    """What Anki's import screen proposes for the file: its own header's
    mapping, or, for a note type the learner picks, Anki's mapping onto it."""
    request = CsvMetadataRequest(path=str(path))
    if note_type_id:
        request.notetype_id = note_type_id
    return anki._backend.get_csv_metadata(request)


def import_csv(
    anki: Collection, path: Path, mapping: CsvMetadata | None = None
) -> ImportResponse.Log:
    metadata = mapping or csv_mapping(anki, path)
    return anki.import_csv(ImportCsvRequest(path=str(path), metadata=metadata)).log


# -- reading it back ---------------------------------------------------------------


def notes(anki: Collection) -> dict[str, Note]:
    """Every note in the collection, by GUID."""
    found = (anki.get_note(n) for n in anki.find_notes(""))
    return {n.guid: n for n in found}


def note_type(anki: Collection, name: str) -> NotetypeDict:
    """The note type as the collection holds it now (not Python's cache)."""
    anki.models._clear_cache()
    found = anki.models.by_name(name)
    assert found is not None, name
    return found


def type_of(note: Note) -> str:
    """The name of a note's note type."""
    found = note.note_type()
    assert found is not None
    return str(found["name"])


def text(field_html: str) -> str:
    """A field as the learner reads it on a card: tags gone, entities read."""
    return html.unescape(re.sub(r"<[^>]+>", "", field_html))


def face(card_html: str) -> str:
    """A rendered card side without its style sheet."""
    return re.sub(r"<style>.*?</style>", "", card_html, flags=re.DOTALL)


def card_state(anki: Collection, card_id: CardId) -> tuple[Any, ...]:
    """Everything about a card's place and study progress."""
    c = anki.get_card(card_id)
    return (c.did, c.odid, c.type, c.queue, c.due, c.ivl, c.factor, c.reps, c.lapses,
            c.left, c.flags, c.memory_state)  # fmt: skip


def the_learners_own(anki: Collection) -> dict[str, Any]:
    """Some of the learner's own work, as they'd have it before our first
    import: their own note type and deck, a Basic note whose front is one of
    our words, and a card they've studied."""
    mine = anki.models.new("Chinese (mine)")
    for name in ("Hanzi", "Pinyin", "Meaning", "Sentence", "SentenceMeaning"):
        anki.models.add_field(mine, anki.models.new_field(name))
    template = anki.models.new_template("Read")
    template["qfmt"], template["afmt"] = "{{Hanzi}}", "{{FrontSide}}<hr>{{Meaning}}"
    anki.models.add_template(mine, template)
    anki.models.add(mine)
    deck = anki.decks.id("Chinese::Mining")
    assert deck is not None
    hanzi = anki.new_note(note_type(anki, "Chinese (mine)"))
    hanzi["Hanzi"], hanzi["Pinyin"], hanzi["Meaning"] = "行", "xíng", "OK (mine)"
    hanzi.tags = ["mine"]
    anki.add_note(hanzi, deck)
    basic = anki.new_note(note_type(anki, "Basic"))
    basic["Front"], basic["Back"] = "run", "my own card"
    anki.add_note(basic, deck)
    anki.sched.set_due_date([hanzi.cards()[0].id], "12!")
    return {"note types": anki.models.all_names_and_ids(), **snapshot(anki)}


def snapshot(anki: Collection) -> dict[str, Any]:
    """The learner's notes (not ours) and their cards, and every deck."""
    theirs = {
        g: (n.mid, n.mod, n.fields, n.tags, [card_state(anki, c.id) for c in n.cards()])
        for g, n in notes(anki).items()
        if not g.startswith("polyglotic:")
    }
    return {
        "notes": theirs,
        "decks": {d.id: d.name for d in anki.decks.all_names_and_ids()},
    }


def logged(log: ImportResponse.Log) -> dict[str, int]:
    """How many notes the import put under each heading of its log."""
    names = ("new", "updated", "duplicate", "conflicting", "first_field_match",
             "missing_notetype", "missing_deck", "empty_first_field")  # fmt: skip
    return {name: len(getattr(log, name)) for name in names if getattr(log, name)}


# -- the deck file -----------------------------------------------------------------


def test_the_deck_file_brings_our_note_types_decks_fields_and_tags(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。", "He loves durian.")
    learner.learn(HANG, "我去银行。", "I'm going to the bank.")
    learner.learn(XING, "不行!")
    learner.save(RUN, "I run daily.")

    assert logged(import_deck(anki, learner, files)) == {"new": 4}

    for name, note_type_id in NOTE_TYPES.items():
        model = note_type(anki, name)
        assert model["id"] == note_type_id
        assert anki.models.field_names(model) == list(FIELDS)
        assert [t["name"] for t in model["tmpls"]] == ["Recognise", "Listen", "Recall"]
        assert model["sortf"] == 0  # the browser sorts by Word
    found = notes(anki)
    assert set(found) == {guid(DURIAN), guid(HANG), guid(XING), guid(RUN)}
    durian, run = found[guid(DURIAN)], found[guid(RUN)]
    assert type_of(durian) == "Polyglotic Chinese"
    assert type_of(run) == "Polyglotic English"
    assert dict(durian.items()) == {
        "Word": "榴莲", "Reading": "liú lián", "Meaning": "durian &lt;fruit&gt; &amp; more",
        "Sentence": "他爱吃<b>榴莲</b>。", "Translation": "He loves durian.",
        "WordAudio": "", "SentenceAudio": "", "Source": "", "Traditional": "榴槤",
        "Notes": "", "Listen": "", "Recall": "", "EntryID": DURIAN,
    }  # fmt: skip
    assert (run["Word"], run["Reading"], run["Traditional"]) == ("run", "/rʌn/", "")
    assert run["Sentence"] == "I <b>run</b> daily."
    assert durian.tags == ["polyglotic"]
    assert run.tags == ["polyglotic", "polyglotic::Tricky"]  # under ours
    assert set(anki.find_notes("tag:polyglotic")) == set(anki.find_notes(""))
    assert not anki.find_notes("tag:Tricky")  # not the learner's own "Tricky"
    # 行 háng and 行 xíng: one headword, two words, two notes
    assert found[guid(HANG)]["Reading"] == "háng"
    assert found[guid(XING)]["Reading"] == "xíng"
    decks = {g: {anki.decks.name(c.did) for c in n.cards()} for g, n in found.items()}
    assert decks[guid(DURIAN)] == decks[guid(HANG)] == {"Polyglotic::Chinese"}
    assert decks[guid(RUN)] == {"Polyglotic::English"}


def test_one_recognise_card_a_word_and_listen_and_recall_when_asked(
    anki: Collection, learner: Learner, files: Files, tmp_path: Path
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。", "He loves durian.")
    learner.learn(RUN, "")  # a word put in the deck with no line

    import_deck(anki, learner, files)
    durian, run = notes(anki)[guid(DURIAN)], notes(anki)[guid(RUN)]
    assert [c.template()["name"] for c in durian.cards()] == ["Recognise"]
    front = face(durian.cards()[0].question())
    assert '<div class="word">榴莲</div>' in front
    assert '<div class="sentence">他爱吃<b>榴莲</b>。</div>' in front
    assert "[anki:play:q:0]" in front  # the word, read by Anki's own voice
    back = face(durian.cards()[0].answer())
    for shown in ("liú lián", "durian &lt;fruit&gt; &amp; more", "He loves durian."):
        assert shown in back
    # the back adds to the front, it doesn't show the word and line again
    assert back.count('<div class="word">') == 1 and back.count("他爱吃") == 1
    run_front = face(run.cards()[0].question())
    assert '<div class="word">run</div>' in run_front and "sentence" not in run_front

    # Into a new collection: the words haven't changed, so a deck that has
    # them keeps its notes as they are, flags too (A2 will date the choice).
    other = Collection(str(tmp_path / "other.anki2"))
    try:
        learner.learn(RUN, "I run daily.", "我每天跑步。")
        import_deck(other, learner, files, listen=True, recall=True)
        run_recall = face(notes(other)[guid(RUN)].cards()[2].question())
        assert "/rʌn/" not in run_recall and "run" not in run_recall  # IPA, line
        durian = notes(other)[guid(DURIAN)]
        cards = {c.template()["name"]: c for c in durian.cards()}
        assert list(cards) == ["Recognise", "Listen", "Recall"]
        listen = face(cards["Listen"].question())
        assert "[anki:play:q:0]" in listen and "榴莲" not in listen  # heard, not read
        recall = face(cards["Recall"].question())
        assert "durian" in recall and "He loves durian." in recall  # meaning, line
        assert "榴莲" not in recall and "liú" not in recall  # not the word or reading
        recall_back = face(cards["Recall"].answer())
        assert "榴莲" in recall_back and "liú lián" in recall_back
        assert recall_back.count("durian &lt;fruit&gt;") == 1
        for card in cards.values():
            assert BLANK not in card.question()
        assert not other.get_empty_cards().notes  # Tools > Empty Cards finds nothing
    finally:
        other.close()


def test_text_arrives_in_anki_as_it_was_written(
    anki: Collection, learner: Learner, files: Files
) -> None:
    sentence = '<script>alert("榴莲")</script> & 榴莲 "quoted", 1 < 2'
    learner.learn(DURIAN, sentence, "<i>not italic</i> & =1+2")

    import_deck(anki, learner, files)
    durian = notes(anki)[guid(DURIAN)]
    assert text(durian["Sentence"]) == sentence
    assert text(durian["Translation"]) == "<i>not italic</i> & =1+2"
    assert text(durian["Meaning"]) == "durian <fruit> & more"
    back = face(durian.cards()[0].answer())
    assert "<script" not in back and "<i>" not in back
    assert "<b>榴莲</b>" in back  # the one tag we mean: the word, marked


def test_no_media_and_nothing_for_check_database_to_find(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。")
    learner.learn(RUN, "I run daily.")
    import_deck(anki, learner, files)
    import_csv(anki, write_csv(learner, files))

    assert list(Path(anki.media.dir()).iterdir()) == []
    media = anki.media.check()
    assert not media.missing and not media.unused
    problems, ok = anki.fix_integrity()  # Tools > Check Database
    assert ok, problems


def test_an_updated_deck_file_updates_the_notes_rather_than_doubling_them(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。")
    learner.learn(RUN, "I run daily.")
    import_deck(anki, learner, files)
    cards = anki.card_count()

    learner.learn(DURIAN, "榴莲很臭。", "Durian stinks.")  # heard again, a new line
    learner.learn(HANG, "我去银行。")  # and a new word
    log = import_deck(anki, learner, files)

    assert logged(log) == {"new": 1, "updated": 1, "duplicate": 1}  # run: unchanged
    assert anki.note_count() == 3 and anki.card_count() == cards + 1
    durian = notes(anki)[guid(DURIAN)]
    assert durian["Sentence"] == "<b>榴莲</b>很臭。"
    assert durian["Translation"] == "Durian stinks."
    assert [m["name"] for m in anki.models.all()].count("Polyglotic Chinese") == 1


def test_the_learners_own_notes_decks_and_note_types_are_untouched(
    anki: Collection, learner: Learner, files: Files
) -> None:
    before = the_learners_own(anki)
    learner.learn(XING, "不行!")
    learner.learn(RUN, "I run daily.")

    import_deck(anki, learner, files)
    learner.learn(XING, "行不行?")
    import_deck(anki, learner, files)
    import_csv(anki, write_csv(learner, files))

    after = snapshot(anki)
    assert after["notes"] == before["notes"]
    assert before["decks"].items() <= after["decks"].items()
    mine = {n.name: n.id for n in before["note types"]}
    now = {n.name: n.id for n in anki.models.all_names_and_ids()}
    assert {k: now[k] for k in mine} == mine
    assert set(now) - set(mine) == set(NOTE_TYPES)


def test_study_progress_and_where_the_learner_put_a_card_are_kept(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。")
    import_deck(anki, learner, files)
    card = notes(anki)[guid(DURIAN)].cards()[0]
    new = card_state(anki, card.id)
    assert (card.type, card.queue, card.reps) == (0, 0, 0)  # new: we bring no progress

    anki.sched.set_due_date([card.id], "7!")  # studied
    mining = anki.decks.id("Chinese::Mining")
    assert mining is not None
    anki.set_deck([card.id], mining)  # and moved to a deck of their own
    studied = card_state(anki, card.id)
    assert studied != new

    learner.learn(DURIAN, "榴莲很臭。")
    log = import_deck(anki, learner, files)
    assert logged(log) == {"updated": 1}
    assert card_state(anki, card.id) == studied


def test_a_learners_own_edit_to_our_note_survives_the_word_exported_again(
    anki: Collection, learner: Learner, files: Files
) -> None:
    """Each note's time is when its word last changed in the app, and Anki
    updates only from a newer note: an unchanged word leaves the learner's
    Notes and tags alone - Anki's own "leech" and "marked" too - and a
    changed one updates, the whole note (the polyglotic-hq 162 choice)."""
    learner.learn(DURIAN, "他爱吃榴莲。")
    learner.learn(RUN, "I run daily.")
    import_deck(anki, learner, files)
    durian = notes(anki)[guid(DURIAN)]
    durian["Notes"] = "smells like onions"
    durian.tags += ["favourite", "leech", "marked"]
    anki.update_note(durian)
    durian = notes(anki)[guid(DURIAN)]
    edited = (durian.fields, durian.tags)

    learner.clock.now = datetime.now(UTC)  # later, in the app:
    learner.learn(DURIAN, "他爱吃榴莲。")  # learned again from the same line
    log = import_deck(anki, learner, files)  # the same words, unchanged in the app
    assert logged(log) == {"duplicate": 2}
    durian = notes(anki)[guid(DURIAN)]
    assert (durian.fields, durian.tags) == edited

    learner.learn(DURIAN, "榴莲很臭。", "Durian stinks.")  # changed: a new line
    log = import_deck(anki, learner, files)
    assert logged(log) == {"updated": 1, "duplicate": 1}
    durian = notes(anki)[guid(DURIAN)]
    assert durian["Sentence"] == "<b>榴莲</b>很臭。"
    assert (durian["Notes"], durian.tags) == ("", ["polyglotic"])  # replaced


def test_a_change_to_our_cards_reaches_a_deck_already_imported(
    anki: Collection, learner: Learner, files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A note type's cards and style arrive when the file's note type is
    newer (`NOTE_TYPES_CHANGED`) and its fields and card types still match.
    Until then, a learner's own change to them stays."""
    earlier = datetime.now(UTC) - timedelta(hours=1)  # the cards in this app
    monkeypatch.setattr(anki_package, "NOTE_TYPES_CHANGED", earlier)
    learner.learn(DURIAN, "他爱吃榴莲。")
    import_deck(anki, learner, files)
    mine = note_type(anki, "Polyglotic Chinese")
    mine["css"] += "\n.word { font-size: 3em; } /* mine */"
    anki.models.update_dict(mine)

    learner.learn(DURIAN, "榴莲很臭。")  # the word changes; the cards don't
    import_deck(anki, learner, files)
    assert note_type(anki, "Polyglotic Chinese")["css"].endswith("/* mine */")

    later = datetime.now(UTC) + timedelta(hours=1)  # the next app's cards
    monkeypatch.setattr(anki_package, "NOTE_TYPES_CHANGED", later)
    monkeypatch.setattr(anki_package, "CSS", anki_package.CSS + "/* new */")
    import_deck(anki, learner, files)
    model = note_type(anki, "Polyglotic Chinese")
    assert model["css"].endswith("/* new */") and model["mod"] == int(later.timestamp())
    assert [m["name"] for m in anki.models.all()].count("Polyglotic Chinese") == 1
    durian = notes(anki)[guid(DURIAN)]
    assert "/* new */" in durian.cards()[0].answer()


def test_a_new_field_would_split_our_note_type(
    anki: Collection, learner: Learner, files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why the fields and card types never change: Anki matches a note type
    by them, and on a mismatch makes a second one and leaves every word it
    has on the first ("conflicting") - nothing would update again."""
    learner.learn(DURIAN, "他爱吃榴莲。")
    import_deck(anki, learner, files)

    monkeypatch.setattr(anki_package, "FIELDS", (*FIELDS, "Example"))
    learner.learn(DURIAN, "榴莲很臭。")
    log = import_deck(anki, learner, files)
    assert logged(log) == {"conflicting": 1}
    names = [m["name"] for m in anki.models.all()]
    assert len([n for n in names if n.startswith("Polyglotic Chinese")]) == 2


# -- the CSV -----------------------------------------------------------------------


def test_the_csv_maps_itself_onto_basic_with_its_guids_tags_and_deck(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。", "He loves durian.")
    learner.learn(HANG, "我去银行。")
    learner.learn(XING, "不行!")
    path = write_csv(learner, files)

    mapping = csv_mapping(anki, path)
    assert mapping.delimiter == CsvMetadata.Delimiter.COMMA and mapping.is_html
    assert mapping.deck_name == "Polyglotic"  # made on import if it isn't there
    basic = anki.models.get(NotetypeId(mapping.global_notetype.id))
    assert basic is not None and basic["name"] == "Basic"
    assert list(mapping.global_notetype.field_columns) == [1, 2]  # Front, Back
    assert (mapping.guid_column, mapping.tags_column) == (8, 3)
    # no names (polyglotic-hq 237): Anki's import screen shows each column's
    # number and the first word's value - "1: 榴莲 (榴槤)" - and Help lists them
    assert list(mapping.column_labels) == [""] * 8
    assert mapping.preview[0].vals[0] == "榴莲 (榴槤)"

    assert logged(import_csv(anki, path)) == {"new": 3}
    durian = notes(anki)[guid(DURIAN)]
    assert durian["Front"] == "榴莲 (榴槤)"
    assert durian["Back"] == (
        "<div>liú lián</div><div>durian &lt;fruit&gt; &amp; more</div><hr>"
        "<div>他爱吃<b>榴莲</b>。</div><div>He loves durian.</div>"
    )
    assert durian.tags == ["polyglotic"]
    assert {anki.decks.name(c.did) for c in durian.cards()} == {"Polyglotic"}
    assert notes(anki)[guid(HANG)]["Front"] == notes(anki)[guid(XING)]["Front"] == "行"


def test_an_updated_csv_updates_the_notes_rather_than_doubling_them(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。")
    learner.learn(RUN, "I run daily.")
    import_csv(anki, write_csv(learner, files))
    assert logged(import_csv(anki, write_csv(learner, files))) == {"duplicate": 2}

    learner.learn(DURIAN, "榴莲很臭。")
    log = import_csv(anki, write_csv(learner, files))
    assert logged(log) == {"updated": 1, "duplicate": 1}
    assert anki.note_count() == 2
    assert "<b>榴莲</b>很臭。" in notes(anki)[guid(DURIAN)]["Back"]


def test_the_csv_into_a_note_type_of_the_learners_own(
    anki: Collection, learner: Learner, files: Files
) -> None:
    """The learner picks their own note type in Anki's import screen. The
    file names no columns (polyglotic-hq 237), so Anki proposes them in
    order, the tags and the GUID left out - the word in the first field -
    and the learner maps the rest, by the numbers Help lists. Captions
    starting with a spreadsheet's formula characters arrive as they were
    said."""
    the_learners_own(anki)
    line = "-Run! =now +fast @home"
    learner.learn(RUN, line, "+跑 =现在")
    path = write_csv(learner, files)
    mine = note_type(anki, "Chinese (mine)")

    mapping = csv_mapping(anki, path, mine["id"])
    proposed = list(mapping.global_notetype.field_columns)
    assert proposed == [1, 2, 4, 5, 6]  # in order: Hanzi gets the word
    mapping.global_notetype.field_columns[:] = [1, 4, 5, 6, 7]  # the learner's choice
    assert logged(import_csv(anki, path, mapping)) == {"new": 1}

    run = notes(anki)[guid(RUN)]
    assert type_of(run) == "Chinese (mine)"
    assert (run["Hanzi"], run["Pinyin"], run["Meaning"]) == (
        "run",
        "/rʌn/",
        "to move fast",
    )
    assert text(run["Sentence"]) == line
    assert text(run["SentenceMeaning"]) == "+跑 =现在"
    assert run.tags == ["polyglotic"]


def test_the_csv_and_the_deck_file_never_double_a_word(
    anki: Collection, learner: Learner, files: Files
) -> None:
    """The CSV's notes are Basic and the deck file's are ours: Anki finds a
    word's note by its GUID whichever file brought it, and, its note type
    being different, leaves it alone ("conflicting") - no second note, and
    no update either. A word stays the kind of note it first came as."""
    learner.learn(DURIAN, "他爱吃榴莲。")
    import_deck(anki, learner, files)
    learner.learn(RUN, "I run daily.")
    assert logged(import_csv(anki, write_csv(learner, files))) == {
        "new": 1,
        "conflicting": 1,
    }
    learner.learn(HANG, "我去银行。")
    assert logged(import_deck(anki, learner, files)) == {
        "new": 1,
        "duplicate": 1,  # 榴莲, unchanged since the last deck file
        "conflicting": 1,
    }
    assert anki.note_count() == 3
    assert type_of(notes(anki)[guid(DURIAN)]) == "Polyglotic Chinese"
    assert type_of(notes(anki)[guid(RUN)]) == "Basic"


def old_layout(path: Path) -> Path:
    """The same file as the app wrote it before 2026-11-08: the GUID in
    column 1, the tags in column 4, and the columns named in a `#columns:`
    line (polyglotic-hq 237 dropped it)."""
    head: list[str] = []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        (head if line.startswith("#") else rows).append(line)
    assert head[2] == "#guid column:8\n" and head[5] == "#tags column:3\n"
    head[2], head[5] = "#guid column:1\n", "#tags column:4\n"
    old = path.with_name("old-" + path.name)
    table = list(csv.reader(io.StringIO("".join(rows))))
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([r[-1], *r[:-1]] for r in table)
    head.append("#columns:" + ",".join(["GUID", *COLUMNS[:-1]]) + "\n")
    old.write_text("".join(head) + "\n" + out.getvalue(), encoding="utf-8")
    return old


def test_a_csv_written_before_the_guid_moved_still_finds_its_notes(
    anki: Collection, learner: Learner, files: Files
) -> None:
    """Each file says where its GUID is, so notes from an old file (GUID
    first) and a new one (GUID last) are the same notes, either way round."""
    learner.learn(DURIAN, "他爱吃榴莲。")
    learner.learn(RUN, "I run daily.")
    old = old_layout(write_csv(learner, files))
    assert csv_mapping(anki, old).guid_column == 1
    assert logged(import_csv(anki, old)) == {"new": 2}
    assert notes(anki)[guid(DURIAN)]["Front"] == "榴莲 (榴槤)"

    learner.learn(DURIAN, "榴莲很臭。")
    assert logged(import_csv(anki, write_csv(learner, files))) == {
        "updated": 1,
        "duplicate": 1,
    }
    learner.learn(RUN, "Run!")
    assert logged(import_csv(anki, old_layout(write_csv(learner, files)))) == {
        "updated": 1,
        "duplicate": 1,
    }
    assert anki.note_count() == 2


@pytest.fixture
def chinese_anki(tmp_path: Path) -> Iterator[Collection]:
    """A new collection made by an Anki set to Chinese: Basic is 问答题, its
    fields 正面 and 背面."""
    collection = Collection(str(tmp_path / "zh.anki2"), RustBackend(["zh_CN"]))
    yield collection
    collection.close()


def test_in_a_chinese_language_anki_the_csv_puts_the_word_on_the_front(
    chinese_anki: Collection, learner: Learner, files: Files
) -> None:
    """问答题's fields take the columns in order (no names to match since
    polyglotic-hq 237): the word on the front, since the GUID moved to the
    end (162). The GUID still finds the note again, and updates it."""
    assert chinese_anki.models.by_name("Basic") is None
    learner.learn(RUN, "I run daily.")
    assert logged(import_csv(chinese_anki, write_csv(learner, files))) == {"new": 1}
    run = notes(chinese_anki)[guid(RUN)]
    assert run.fields[0] == "run"
    assert "polyglotic:" not in "".join(run.fields)
    learner.learn(RUN, "Run!")  # a new line, on the back
    log = import_csv(chinese_anki, write_csv(learner, files))
    assert logged(log) == {"updated": 1} and chinese_anki.note_count() == 1
    assert "<b>Run</b>!" in notes(chinese_anki)[guid(RUN)].fields[1]


def test_in_a_chinese_language_anki_the_csv_fills_the_back(
    chinese_anki: Collection, learner: Learner, files: Files
) -> None:
    """polyglotic-hq 237 (223's QA, medium 4): with the file's `#columns:`
    line, no name matched 背面 and every card's back was empty."""
    learner.learn(RUN, "I run daily.")
    import_csv(chinese_anki, write_csv(learner, files))
    assert "I <b>run</b> daily." in notes(chinese_anki)[guid(RUN)].fields[1]
