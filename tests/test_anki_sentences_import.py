"""Saved sentences exported for Anki, imported into a real Anki collection
by Anki's own engine (polyglotic-hq 459; 152's way: the `anki` package, a
dev dependency only, a throwaway collection in the test's folder - no
learner's own Anki is opened).

Through the Words page's own export functions: the sentence note type,
its one card rendered never blank, the sub-deck of the language spoken,
the links underlined on the back, an export again updating rather than
doubling, and the CSV through Anki's importer as Basic cards."""

from anki.collection import Collection
from tests.test_anki_import import (
    BLANK,
    DURIAN,
    Files,
    Learner,
    anki,
    face,
    files,
    import_csv,
    import_deck,
    learner,
    logged,
    note_type,
    notes,
    text,
    type_of,
    write_csv,
)

from polyglotic_desktop.adapters.anki_package import SENTENCE_FIELDS
from polyglotic_desktop.core.learning.anki import LINK_COLOURS, sentence_guid
from polyglotic_desktop.core.learning.sentences import SentenceLink, SentencePart

__all__ = ["anki", "files", "learner"]  # the fixtures, used by name

PARTS = (
    SentencePart(
        "他爱吃榴莲。", "He loves durian.", (SentenceLink((3, 5), (9, 15)),), "Discord"
    ),
    SentencePart("你呢?", "And you?", (), "You"),
)


def save_sentence(learner: Learner) -> str:
    learner.clock.advance(minutes=1)
    saved = learner.vocabulary.save_sentence(
        PARTS, "他爱吃榴莲。你呢?", "He loves durian. And you?", "tricky", "en"
    )
    return sentence_guid(saved.id)


def test_a_saved_sentence_arrives_in_its_own_note_type_and_renders(
    anki: Collection, learner: Learner, files: Files
) -> None:
    learner.learn(DURIAN, "他爱吃榴莲。", "He loves durian.")
    learner.save(DURIAN, "他爱吃榴莲。")
    guid = save_sentence(learner)

    assert logged(import_deck(anki, learner, files)) == {"new": 2}

    model = note_type(anki, "Polyglotic Chinese sentence")
    assert anki.models.field_names(model) == list(SENTENCE_FIELDS)
    assert [t["name"] for t in model["tmpls"]] == ["Read"]
    sentence = notes(anki)[guid]
    assert type_of(sentence) == "Polyglotic Chinese sentence"
    assert set(sentence.tags) == {
        "polyglotic", "polyglotic::sentence", "polyglotic::Tricky",
    }  # fmt: skip
    (card,) = sentence.cards()
    assert anki.decks.name(card.did) == "Polyglotic::Chinese"

    front = face(card.question())
    assert BLANK not in front
    assert "<b>榴莲</b>" in front  # the saved word marked
    assert "He loves" not in front
    back = face(card.answer())
    assert f"border-bottom: 2px solid {LINK_COLOURS[0]}" in back
    assert text(back).count("他爱吃榴莲") == 1  # in place of the front, not under it
    assert "He loves durian. And you?" in text(back)
    assert "Discord · You" in text(back)


def test_exporting_again_updates_the_sentence_rather_than_doubling_it(
    anki: Collection, learner: Learner, files: Files
) -> None:
    guid = save_sentence(learner)
    import_deck(anki, learner, files)
    assert logged(import_deck(anki, learner, files)) == {"duplicate": 1}
    assert [g for g in notes(anki) if g.startswith("polyglotic:sentence:")] == [guid]


def test_the_csv_brings_a_sentence_as_a_basic_card(
    anki: Collection, learner: Learner, files: Files
) -> None:
    guid = save_sentence(learner)
    assert logged(import_csv(anki, write_csv(learner, files))) == {"new": 1}
    sentence = notes(anki)[guid]
    assert type_of(sentence) == "Basic"
    (card,) = sentence.cards()
    assert text(face(card.question())) == "他爱吃榴莲。你呢?"
    assert "He loves durian. And you?" in text(face(card.answer()))
