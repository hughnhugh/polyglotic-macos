"""Saved sentences for Anki (polyglotic-hq 459): a note like a word's -
the front what was said with its saved words marked, the back its word
links underlined on both sides - in the CSV and the deck file, each
exported once when only new ones are wanted."""

from datetime import UTC, datetime

from tests.learning.fakes import Clock, MemoryLearningStore
from tests.learning.test_vocabulary import lookup

from polyglotic_desktop.core.learning.anki import (
    LINK_COLOURS,
    sentence_csv_rows,
    sentence_guid,
    sentence_note,
)
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import SavedWord
from polyglotic_desktop.core.learning.sentences import (
    SavedSentence,
    SentenceLink,
    SentencePart,
)
from polyglotic_desktop.core.learning.vocabulary import (
    AnkiFormat,
    Vocabulary,
    sentence_key,
    words_and_sentences,
)
from polyglotic_desktop.core.shared import EntryId

AT = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)
PINK, TEAL = (f'<span style="border-bottom: 2px solid {c}">' for c in LINK_COLOURS[:2])

TWO_CAPTIONS = SavedSentence(
    "abc",
    "我今天去超市。买水果",
    "I went to the supermarket today. To buy <fruit>",
    (
        SentencePart(
            "我今天去超市。",
            "I went to the supermarket today.",
            (SentenceLink((4, 6), (14, 25)), SentenceLink((0, 1), (0, 1), key=False)),
            "Discord",
        ),
        SentencePart(
            "买水果", "To buy <fruit>", (SentenceLink((1, 3), (7, 14)),), "You"
        ),
    ),
    "saved",
    AT,
    "en",
)


def word(headword: str, traditional: str = "") -> SavedWord:
    return SavedWord(
        EntryId(f"x:{headword}"), headword, traditional, "", "", "saved", "", "", AT
    )


def test_the_front_marks_the_saved_words_and_the_back_underlines_links() -> None:
    note = sentence_note(TWO_CAPTIONS, [word("超市"), word("水果")], "Saved")
    assert note.front == "我今天去<b>超市</b>。买<b>水果</b>"
    # each key link its own colour, the same on both sides; minor ones not
    assert note.original == f"我今天去{PINK}超市</span>。买{TEAL}水果</span>"
    assert note.translation == (
        f"I went to the {PINK}supermarket</span> today. "
        f"To buy {TEAL}&lt;fruit&gt;</span>"
    )
    assert note.speakers == "Discord · You"


def test_an_english_saved_word_is_marked_as_a_whole_word_in_any_case() -> None:
    sentence = SavedSentence(
        "e", "Run, he runs to the run-down shop", "", (SentencePart("x"),), "s", AT
    )
    note = sentence_note(sentence, [word("run")], "")
    assert note.front == "<b>Run</b>, he runs to the <b>run</b>-down shop"


def test_a_csv_row_is_a_basic_card_with_its_own_guid_and_tags() -> None:
    (row,) = sentence_csv_rows([sentence_note(TWO_CAPTIONS, [], "Trip words")])
    front, back, tags, reading, meaning, original, translation, guid = row
    assert front == "我今天去超市。买水果"
    assert back.startswith(f"<div>我今天去{PINK}超市</span>")
    assert "Discord · You" in back
    assert tags == "polyglotic polyglotic::sentence polyglotic::Trip_words"
    assert (reading, meaning) == ("", "")
    assert guid == sentence_guid("abc") == "polyglotic:sentence:abc"
    assert original.startswith("我今天去") and translation.startswith("I went")


def test_a_cell_that_would_be_a_formula_is_written_as_text() -> None:
    sentence = SavedSentence("f", "- Who's there?", "", (SentencePart("x"),), "s", AT)
    (row,) = sentence_csv_rows([sentence_note(sentence, [], "")])
    assert row[0].startswith("&#45;")


def test_sentences_are_exported_with_the_words_and_once_when_only_new() -> None:
    clock = Clock()
    vocab = Vocabulary(MemoryLearningStore(), lookup, "hsk-2025", clock=clock)
    vocab.save(
        EntryId("x:超市"), "超市", "超市", "chāo shì", "supermarket", "saved",
        LookupContext("我今天去超市。"),
    )  # fmt: skip
    first = vocab.save_sentence(TWO_CAPTIONS.parts, "我今天去超市。", "", "saved")
    export = vocab.anki_words().export(language="zh")
    assert export.counts == (1, 1)
    assert export.entry_ids[-1] == sentence_key(first.id)
    (deck,) = export.sentences
    assert (deck.language, deck.front) == ("zh", "我今天去<b>超市</b>。")
    assert "polyglotic:sentence:" in export.text

    vocab.mark_exported(export.entry_ids, AnkiFormat.DECK)
    clock.advance(minutes=1)
    second = vocab.save_sentence(TWO_CAPTIONS.parts, "买水果", "", "saved")
    again = vocab.anki_words(only_new=True).export(language="zh")
    assert [s.sentence_id for s in again.sentences] == [second.id]
    assert again.counts == (0, 1)
    # the CSV has its own: both are new to it
    assert len(vocab.anki_words(True, AnkiFormat.CSV).export().sentences) == 2


def test_words_and_sentences_are_counted_from_any_iterable() -> None:
    keys = (EntryId("cedict:a"), sentence_key("s1"), EntryId("ecdict:b"))
    assert words_and_sentences(iter(keys)) == (2, 1)
