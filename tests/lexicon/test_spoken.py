"""Everyday talk (polyglotic-hq 491, decision 0227): Mandarin's and
English's entries carry each word's rank in speech (OpenSubtitles 2018's
counts, where the pack ranks it rarer) and whether it is a filler; a pack
language's entries carry neither, though it borrows English's rules."""

from polyglotic_desktop.core.lexicon import spoken
from polyglotic_desktop.core.lexicon.basic import entry_from_record as basic_entry
from polyglotic_desktop.core.lexicon.chinese import (
    entry_from_record as chinese_entry,
)
from polyglotic_desktop.core.lexicon.chinese import facts_from_record
from polyglotic_desktop.core.lexicon.english import (
    entry_from_record as english_entry,
)
from polyglotic_desktop.ports.dictionary import EntryRecord


def record(headword: str, reading: str = "", rank: int = 5000) -> EntryRecord:
    return EntryRecord(f"x:{headword}", headword, "", reading, ("a meaning",), rank)


def test_speech_places_everyday_words_the_written_ranks_place_too_rare() -> None:
    thanks = spoken.MANDARIN.rank("谢谢")  # 6,361st in the pack's written ranks
    assert thanks is not None and thanks < 200
    um = spoken.ENGLISH.rank("um")
    assert um is not None and um < 1000
    assert spoken.MANDARIN.rank("业主") is None  # a conversation's own word


def test_fillers() -> None:
    assert spoken.MANDARIN.is_filler("嗯") and spoken.MANDARIN.is_filler("呃")
    assert spoken.ENGLISH.is_filler("um") and spoken.ENGLISH.is_filler("uh-huh")
    assert not spoken.MANDARIN.is_filler("业主")
    assert not spoken.ENGLISH.is_filler("rubber")


def test_mandarin_entries_and_facts_carry_them() -> None:
    thanks = record("谢谢", "xie4 xie5", 6361)
    entry = chinese_entry(thanks)
    assert entry.spoken_rank == spoken.MANDARIN.rank("谢谢")
    facts = entry.facts("hsk-2025")
    assert facts.spoken_rank == entry.spoken_rank and not facts.is_filler
    assert facts_from_record(thanks, "hsk-2025") == facts
    assert chinese_entry(record("嗯", "ng4", 3570)).facts("hsk-2025").is_filler


def test_english_entries_carry_them() -> None:
    entry = english_entry(record("um"))
    assert entry.is_filler and entry.spoken_rank == spoken.ENGLISH.rank("um")
    assert entry.facts("en-frequency").is_filler


def test_english_capitals_inside_a_sentence_mark_names_a_packs_do_not() -> None:
    assert english_entry(record("julia")).facts("en-frequency").names_capitalised
    assert not basic_entry(record("haus")).facts("de-frequency").names_capitalised


def test_english_numbers_spelled_out_are_marked() -> None:
    assert english_entry(record("fourteen")).facts("en-frequency").spells_a_number
    assert not english_entry(record("rubber")).facts("en-frequency").spells_a_number


def test_a_pack_languages_entries_carry_neither() -> None:
    entry = basic_entry(record("okay"))  # a word some pack might have
    assert entry.spoken_rank is None and not entry.is_filler
    assert not basic_entry(record("nine")).spells_a_number
