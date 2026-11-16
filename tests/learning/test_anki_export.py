"""Words for Anki (project 089): "Learn" keeps the line the word was in on
the PC, and the CSV carries it - checked against Anki's documented import
rules (docs.ankiweb.net, "Importing text files", read 2026-11-06) by a
small reader of the file written here from those rules, with no Anki
installed."""

import csv
import html
import io
from dataclasses import dataclass

from tests.learning.fakes import Clock, MemoryLearningStore

from polyglotic_desktop.core.learning.anki import (
    COLUMNS,
    AnkiNote,
    guid,
    marked_sentence,
)
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import (
    AnkiFormat,
    EntryText,
    Vocabulary,
)
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus

HANG = EntryId("cedict:行-háng")
XING = EntryId("cedict:行-xíng")
DURIAN = EntryId("cedict:榴莲")
TEXTS = {
    HANG: EntryText("行", "行", "háng", "row; profession"),
    XING: EntryText("行", "行", "xíng", "to walk; OK"),
    DURIAN: EntryText("榴莲", "榴槤", "liú lián", "durian"),
}


def known_facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return EntryFacts(entry_id, 1, 100, False) if entry_id in TEXTS else None


def describe(entry_id: EntryId) -> EntryText | None:
    return TEXTS.get(entry_id)


@dataclass
class Note:
    guid: str
    tags: list[str]
    fields: list[str]  # Front, Back, Reading, Meaning, Sentence, Translation


@dataclass
class AnkiFile:
    """What Anki reads from the file, by its documented rules."""

    headers: dict[str, str]
    columns: list[str]
    notes: list[Note]


def read_like_anki(text: str) -> AnkiFile:
    lines = text.split("\n")
    headers: dict[str, str] = {}
    at = 0
    while at < len(lines) and lines[at].startswith("#"):
        key, _, value = lines[at][1:].partition(":")
        headers[key] = value  # "#key:value"
        at += 1
    assert headers["separator"] == "Comma"
    assert headers["html"] == "true"
    rows = list(csv.reader(io.StringIO("\n".join(lines[at:])), delimiter=","))
    rows = [r for r in rows if r]
    # no line names the columns (polyglotic-hq 237): Anki maps them in order
    assert "columns" not in headers
    columns = list(COLUMNS)
    guid_column = int(headers["guid column"])  # 1-based
    tags_column = int(headers["tags column"])
    assert 1 <= guid_column <= len(columns) and 1 <= tags_column <= len(columns)
    assert guid_column != tags_column
    notes: list[Note] = []
    for row in rows:
        assert len(row) == len(columns), row  # every row has every column
        fields = [
            value
            for number, value in enumerate(row, start=1)
            if number not in (guid_column, tags_column)
        ]
        notes.append(Note(row[guid_column - 1], row[tags_column - 1].split(), fields))
    return AnkiFile(headers, columns, notes)


def import_into(collection: dict[str, list[str]], file: AnkiFile) -> None:
    """Anki's rule with a GUID column: a note with a GUID already in the
    collection is updated, any other is added."""
    for note in file.notes:
        collection[note.guid] = note.fields


class Setup:
    def __init__(self) -> None:
        self.store = MemoryLearningStore()
        self.clock = Clock()
        self.vocab = Vocabulary(self.store, known_facts, "hsk-2025", self.clock)


def test_learn_keeps_the_sentence_its_translation_and_the_time() -> None:
    s = Setup()
    s.vocab.learn(
        DURIAN, TEXTS[DURIAN], LookupContext("他爱吃榴莲。", "He loves durian.")
    )
    word = s.vocab.deck_word(DURIAN)
    assert word is not None
    assert (word.sentence, word.translation) == ("他爱吃榴莲。", "He loves durian.")
    assert word.learned_at == s.clock.now and word.reading == "liú lián"
    assert s.vocab.status_of_entry(DURIAN).status is WordStatus.LEARNING
    # on the PC, and back after a restart
    again = Vocabulary(s.store, known_facts, "hsk-2025", s.clock)
    assert again.deck_word(DURIAN) == word
    # it is not a saved word
    assert s.vocab.saved_word(DURIAN) is None and not s.vocab.saved_words


def test_learn_sends_only_the_status_to_the_server() -> None:
    s = Setup()
    events: list[object] = []
    s.vocab.subscribe(events.append)
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("他爱吃榴莲。", "secret"))
    assert "他爱吃榴莲" not in repr(events) and "secret" not in repr(events)


def test_learning_again_keeps_the_line_unless_there_is_a_new_one() -> None:
    s = Setup()
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("第一句榴莲", "first"))
    s.clock.advance(minutes=1)
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext(""))  # no line this time
    word = s.vocab.deck_word(DURIAN)
    assert word is not None and word.sentence == "第一句榴莲"
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("第二句榴莲", "second"))
    word = s.vocab.deck_word(DURIAN)
    assert word is not None and word.translation == "second"


def test_a_note_changes_only_when_its_word_does() -> None:
    """A deck note's time is when its word last changed in the app (its
    text or its line), so Anki keeps the learner's edits to the notes of
    words that haven't (project 162)."""
    s = Setup()
    durian, saved_at = TEXTS[DURIAN], s.clock.now
    s.vocab.save(
        DURIAN, durian.headword, durian.traditional, durian.reading,
        durian.meaning, "saved", LookupContext("榴莲好吃", "yum"),
    )  # fmt: skip

    def changed() -> object:
        return s.vocab.export_anki(describe).notes[0].changed

    assert changed() == saved_at
    s.clock.advance(minutes=1)
    s.vocab.learn(DURIAN, durian, LookupContext("他爱吃榴莲。", "He loves durian."))
    learned_at = s.clock.now
    assert changed() == learned_at  # the line it went into the deck with
    s.clock.advance(minutes=1)
    s.vocab.learn(DURIAN, durian, LookupContext("他爱吃榴莲。", "He loves durian."))
    s.vocab.learn(DURIAN, durian, LookupContext("榴莲"))  # from Words: no line
    s.vocab.save(
        DURIAN,
        durian.headword,
        durian.traditional,
        durian.reading,
        durian.meaning,
        "tricky",
        LookupContext(""),
    )  # fmt: skip  (moved to another category)
    assert changed() == learned_at  # the same word: unchanged
    s.clock.advance(minutes=1)
    s.vocab.learn(DURIAN, durian, LookupContext("他爱吃榴莲。", "He likes durian."))
    assert changed() == s.clock.now  # a new translation of the line
    s.clock.advance(minutes=1)
    newer = EntryText("榴莲", "榴槤", "liú lián", "durian (fruit)")
    s.vocab.learn(DURIAN, newer, LookupContext("他爱吃榴莲。", "He likes durian."))
    assert changed() == s.clock.now  # a new meaning in the dictionary


def test_a_deck_word_from_another_pc_changes_with_its_status() -> None:
    s = Setup()
    s.vocab.set_status(XING, WordStatus.LEARNING)
    note = s.vocab.export_anki(describe).notes[0]
    assert note.changed == s.vocab.status_of_entry(XING).at == s.clock.now


def test_the_word_on_its_own_is_no_line() -> None:
    """Words hands its lookup the headword as its context when the word has
    no line; "Learn" there keeps no line, so the card doesn't show the word
    twice - and a word in the deck keeps the line it has (projects 135, 152)."""
    s = Setup()
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("榴莲"))  # from Words
    note = read_like_anki(s.vocab.export_anki(describe).text).notes[0]
    assert note.fields[4:] == ["", ""]  # Sentence, Translation
    assert note.fields[1] == "<div>liú lián</div><div>durian</div>"  # Back
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("我去银行。", "the bank"))
    s.clock.advance(minutes=1)
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext(" 行 "))  # again, from Words
    word = s.vocab.deck_word(HANG)
    assert word is not None and word.sentence == "我去银行。"
    s.vocab.learn(XING, TEXTS[XING], LookupContext("榴槤"))  # another word: a line
    s.vocab.set_status(DURIAN, WordStatus.NEW)  # out of the deck
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("榴槤", "durian"))  # traditional
    lines = {w: s.vocab.deck_word(w) for w in (XING, DURIAN)}
    assert [w.sentence if w else None for w in lines.values()] == ["榴槤", ""]


def test_taking_a_word_out_of_the_deck_forgets_its_line() -> None:
    s = Setup()
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("榴莲", "durian"))
    s.vocab.set_status(DURIAN, WordStatus.NEW)
    assert s.vocab.deck_word(DURIAN) is None and not s.store.deck_words
    assert not s.vocab.export_anki(describe).entry_ids


def test_deleting_learning_data_deletes_the_lines_and_export_marks() -> None:
    s = Setup()
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext("榴莲", "durian"))
    export = s.vocab.export_anki(describe)
    s.vocab.mark_exported(export.entry_ids)
    s.vocab.delete_learning_data()
    assert s.vocab.deck_word(DURIAN) is None and not s.vocab.is_exported(DURIAN)
    assert not s.store.deck_words and not s.store.anki_exports


def test_the_file_has_deck_words_and_saved_words_with_marked_sentences() -> None:
    s = Setup()
    s.vocab.learn(
        DURIAN, TEXTS[DURIAN], LookupContext("他爱吃榴莲, <很> 臭。", "He loves it")
    )
    s.clock.advance(minutes=1)
    s.vocab.save(
        HANG, "行", "行", "háng", "row", "tricky", LookupContext("银行不行", "A bank")
    )
    file = read_like_anki(s.vocab.export_anki(describe).text)
    assert file.columns == [
        "Front", "Back", "Tags",
        "Reading", "Meaning", "Sentence", "Translation", "GUID",
    ]  # fmt: skip
    assert (file.headers["guid column"], file.headers["tags column"]) == ("8", "3")
    assert file.headers["notetype"] == "Basic" and file.headers["deck"]
    durian, hang = file.notes
    assert durian.guid == guid(DURIAN)
    assert durian.tags == ["polyglotic"]
    front, back, reading, meaning, sentence, translation = durian.fields
    assert front == "榴莲 (榴槤)" and reading == "liú lián" and meaning == "durian"
    # escaped, the word marked
    assert sentence == "他爱吃<b>榴莲</b>, &lt;很&gt; 臭。"
    assert translation == "He loves it"
    assert sentence in back and translation in back and "<hr>" in back
    assert hang.tags == ["polyglotic", "polyglotic::Tricky"]  # its category


def test_words_with_one_headword_do_not_clash_and_reimport_updates() -> None:
    s = Setup()
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("银行", "bank"))
    s.vocab.learn(XING, TEXTS[XING], LookupContext("行人", "pedestrian"))
    first = read_like_anki(s.vocab.export_anki(describe).text)
    assert len({n.guid for n in first.notes}) == 2
    assert [n.fields[0] for n in first.notes] == ["行", "行"]
    collection: dict[str, list[str]] = {}
    import_into(collection, first)
    assert len(collection) == 2
    # a new sentence, exported again: the same two notes, one changed
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("行业", "industry"))
    second = read_like_anki(s.vocab.export_anki(describe).text)
    import_into(collection, second)
    assert len(collection) == 2
    assert "<b>行</b>业" in collection[guid(HANG)][4]  # the Sentence field
    assert guid(HANG) != guid(XING)


def test_only_words_not_exported_yet() -> None:
    s = Setup()
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("银行", "bank"))
    everything = s.vocab.export_anki(describe)
    assert everything.entry_ids == (HANG,)
    s.vocab.mark_exported(everything.entry_ids)
    s.clock.advance(minutes=1)
    s.vocab.learn(XING, TEXTS[XING], LookupContext("行人", "pedestrian"))
    fresh = s.vocab.export_anki(describe, only_new=True)
    assert fresh.entry_ids == (XING,)
    assert read_like_anki(fresh.text).notes[0].guid == guid(XING)
    # the full export still has both, and the mark survives a restart
    assert set(s.vocab.export_anki(describe).entry_ids) == {HANG, XING}
    again = Vocabulary(s.store, known_facts, "hsk-2025", s.clock)
    assert again.is_exported(HANG) and not again.is_exported(XING)
    assert again.export_anki(describe, only_new=True).entry_ids == (XING,)


def test_each_kind_of_file_remembers_its_own_exports() -> None:
    """368 (QA 361's B5): an .apkg, then a CSV of only the words not
    exported yet, came out empty - the two shared one record. A learner
    keeping a deck file for Anki and a CSV for something else wants each
    to get every word once."""
    s = Setup()
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("银行", "bank"))
    deck = s.vocab.export_anki(describe, only_new=True, file=AnkiFormat.DECK)
    s.vocab.mark_exported(deck.entry_ids, AnkiFormat.DECK)
    assert (
        s.vocab.export_anki(describe, only_new=True, file=AnkiFormat.DECK).notes == ()
    )
    csv = s.vocab.export_anki(describe, only_new=True, file=AnkiFormat.CSV)
    assert csv.entry_ids == (HANG,)
    s.vocab.mark_exported(csv.entry_ids, AnkiFormat.CSV)
    assert s.vocab.export_anki(describe, only_new=True, file=AnkiFormat.CSV).notes == ()
    # each kept apart through a restart; exported in either is exported
    s.clock.advance(minutes=1)
    s.vocab.learn(XING, TEXTS[XING], LookupContext("行人", "pedestrian"))
    s.vocab.mark_exported([XING], AnkiFormat.DECK)
    again = Vocabulary(s.store, known_facts, "hsk-2025", s.clock)
    assert again.export_anki(describe, True, AnkiFormat.CSV).entry_ids == (XING,)
    assert again.export_anki(describe, True, AnkiFormat.DECK).entry_ids == ()
    assert again.is_exported(HANG) and again.is_exported(XING)


def test_a_deck_word_set_elsewhere_exports_without_a_sentence() -> None:
    s = Setup()
    s.vocab.set_status(XING, WordStatus.LEARNING)  # no lookup here
    export = s.vocab.export_anki(describe)
    note = read_like_anki(export.text).notes[0]
    assert note.fields[5] == ""
    assert "<hr>" not in note.fields[1]
    assert not s.vocab.export_anki(None).entry_ids  # nothing to say about it


def test_a_saved_word_in_the_deck_uses_the_line_it_was_saved_from() -> None:
    s = Setup()
    s.vocab.save(
        DURIAN,
        "榴莲",
        "榴槤",
        "liú lián",
        "durian",
        "saved",
        LookupContext("榴槤好吃", "yum"),
    )
    s.vocab.set_status(DURIAN, WordStatus.LEARNING)
    note = read_like_anki(s.vocab.export_anki(describe).text).notes[0]
    assert note.fields[4] == "<b>榴槤</b>好吃"  # traditional form found
    assert note.tags == ["polyglotic", "polyglotic::Saved"]


def test_marking_the_word_in_its_sentence() -> None:
    def note(headword: str, traditional: str, sentence: str) -> AnkiNote:
        return AnkiNote(
            "x", headword, traditional, "", "", sentence, "", "", Clock().now,
            Clock().now,
        )  # fmt: skip

    assert marked_sentence(note("run", "", "They Run fast & far")) == (
        "They <b>Run</b> fast &amp; far"
    )
    # whole words only
    assert marked_sentence(note("run", "", "a prune")) == "a prune"
    # not found: kept, escaped, nothing marked
    assert marked_sentence(note("run", "", "he ran <fast>")) == "he ran &lt;fast&gt;"
    assert (
        marked_sentence(note("电脑", "電腦", "我的電腦坏了")) == "我的<b>電腦</b>坏了"
    )
    assert marked_sentence(note("电脑", "電腦", "")) == ""


def test_marking_a_pack_languages_word_in_its_sentence() -> None:
    """Decision 0175: a word of any language written with spaces is marked
    as a whole word in any case; one written without spaces, anywhere."""

    def note(headword: str, sentence: str) -> AnkiNote:
        return AnkiNote(
            "x", headword, "", "", "", sentence, "", "", Clock().now, Clock().now
        )  # fmt: skip

    assert marked_sentence(note("дом", "Дом стоит у реки")) == (
        "<b>Дом</b> стоит у реки"
    )
    # whole words only: "дом" isn't marked inside "домой"
    assert marked_sentence(note("дом", "он идёт домой")) == "он идёт домой"
    # no spaces between Japanese words: kana, and a word with kanji
    assert marked_sentence(note("りんご", "私はりんごを食べる")) == (
        "私は<b>りんご</b>を食べる"
    )
    assert marked_sentence(note("食べる", "私はりんごを食べる")) == (
        "私はりんごを<b>食べる</b>"
    )


def test_a_sentence_with_line_breaks_and_quotes_round_trips() -> None:
    s = Setup()
    s.vocab.learn(
        DURIAN, TEXTS[DURIAN], LookupContext('他说：\n"榴莲"', 'He said,\n"durian"')
    )
    note = read_like_anki(s.vocab.export_anki(describe).text).notes[0]
    assert note.fields[4] == '他说：\n"<b>榴莲</b>"'
    assert note.fields[5] == 'He said,\n"durian"'


def test_a_merged_entry_takes_its_line_and_export_mark_along() -> None:
    old, new = EntryId("test:old"), EntryId("test:new")

    def before(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return EntryFacts(entry_id, 3, 5000, False)

    def after(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return EntryFacts(new if entry_id == old else entry_id, 3, 5000, False)

    store = MemoryLearningStore()
    clock = Clock()
    vocab = Vocabulary(store, before, "hsk-2025", clock)
    vocab.learn(
        old, EntryText("旧", "舊", "jiù", "old"), LookupContext("旧书", "old book")
    )
    vocab.mark_exported([old])
    clock.advance(minutes=1)
    updated = Vocabulary(store, after, "hsk-2025", clock)
    assert updated.follow_merged_entries([old]) == 1
    word = updated.deck_word(new)
    assert word is not None and word.sentence == "旧书" and word.entry_id == new
    assert updated.deck_word(old) is None
    assert updated.is_exported(new) and not updated.is_exported(old)
    assert set(store.deck_words) == {new} and {e for e, _ in store.anki_exports} == {
        new
    }


def test_no_cell_starts_like_a_spreadsheet_formula() -> None:
    """A line heard in a video can start with "-", "=", "+" or "@" (or
    their full-width forms, or a line break): in the file its first
    character is an HTML character reference, which Anki shows as the
    character and a spreadsheet takes as text (project 152)."""
    s = Setup()
    line = "-Who's there? =1+2"
    s.vocab.learn(DURIAN, TEXTS[DURIAN], LookupContext(line, "@all +榴莲"))
    s.clock.advance(minutes=1)
    sign = EntryText("+", "", "", "=plus")  # an English entry that is a sign
    # a line, not the word on its own (that keeps no line - #217)
    s.vocab.learn(EntryId("ecdict:+"), sign, LookupContext("\t+ 1", "\r-"))
    s.clock.advance(minutes=1)
    s.vocab.learn(HANG, TEXTS[HANG], LookupContext("－行不行？", "\n＠＝＋"))
    durian, plus, hang = read_like_anki(s.vocab.export_anki(describe).text).notes
    for value in durian.fields + plus.fields + hang.fields:
        assert value[:1] not in set("=+-@\t\r\n＝＋－＠"), value  # OWASP's list
    assert durian.fields[4] == "&#45;Who's there? =1+2"
    assert html.unescape(durian.fields[4]) == line
    assert durian.fields[5] == "&#64;all +榴莲"
    assert plus.fields[0] == "&#43;" and plus.fields[3] == "&#61;plus"
    assert plus.fields[4] == "&#9;<b>+</b> 1" and plus.fields[5] == "&#13;-"
    assert hang.fields[4] == "&#65293;<b>行</b>不行？"  # full-width minus
    assert html.unescape(hang.fields[5]) == "\n＠＝＋"


def test_a_saved_word_outlives_its_entry_in_a_new_dictionary() -> None:
    """A newer dictionary under the learner's words - an update's CC-CEDICT,
    or a language's full dictionary in place of its basic pack
    (polyglotic-hq 298, decision 0089) - that no longer has a saved word's
    entry: the word stays saved, with the text it was saved with, and still
    goes to Anki."""
    gone = EntryId("test:gone")

    def before(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return EntryFacts(entry_id, 3, 5000, False)

    def after(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return None if entry_id == gone else EntryFacts(entry_id, 3, 5000, False)

    store = MemoryLearningStore()
    clock = Clock()
    vocab = Vocabulary(store, before, "hsk-2025", clock)
    vocab.save(
        gone, "旧", "舊", "jiù", "old", "saved", LookupContext("旧书", "old book")
    )
    updated = Vocabulary(store, after, "hsk-2025", clock)
    assert updated.follow_merged_entries([]) == 0
    word = updated.saved_word(gone)
    assert word is not None and (word.headword, word.meaning) == ("旧", "old")

    def describe_nothing(entry_id: EntryId) -> EntryText | None:
        return None  # the new dictionary hasn't got it

    file = read_like_anki(updated.export_anki(describe_nothing).text)
    [note] = file.notes
    front, _, reading, meaning, sentence, translation = note.fields
    assert (front, reading, meaning) == ("旧 (舊)", "jiù", "old")
    assert (sentence, translation) == ("<b>旧</b>书", "old book")
    assert note.guid == guid(gone)
