"""Thai's word split (polyglotic-hq 389, decision 0173): a caption written
without spaces cut into the pack's words - never inside a letter's
cluster, a word it hasn't got left whole, the commoner words first."""

from collections.abc import Mapping

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon import thai
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.thai import ThaiSplit, boundaries
from polyglotic_desktop.ports.dictionary import EntryRecord

WORDS: dict[str, int | None] = {
    "ฉัน": 3,
    "กิน": 40,
    "ข้าว": 200,
    "ไป": 10,
    "เรียน": 300,
    "ภาษา": 400,
    "ไทย": 150,
    "ภาษาไทย": 900,
    "ตา": 500,
    "กลม": 1500,
    "ตาก": 2000,
    "ลม": 800,
    "กา": 3000,
    "วัน": 60,
    "จันทร์": 1200,
    "จัน": 9000,
    "มา": 18,
    "ที่": 1,
    "ซี": 7000,
    "ดิน": 1100,
    "ที่ดิน": 2500,
}


def thai_file(words: Mapping[str, int | None]) -> FakeDictionaryFile:
    records = [
        EntryRecord(f"wiktth:{n}", word, "", "", ("a meaning",), rank)
        for n, (word, rank) in enumerate(words.items())
    ]
    return FakeDictionaryFile(records, {r.headword: [r.entry_id] for r in records})


def said(text: str, split: ThaiSplit) -> list[str]:
    return [text[w.start : w.end] for w in split.words(text)]


def test_a_line_without_spaces_is_cut_into_the_packs_words() -> None:
    split = ThaiSplit(thai_file(WORDS))
    assert said("ฉันกินข้าว", split) == ["ฉัน", "กิน", "ข้าว"]
    # a compound the pack has is one word; a space ends a phrase
    assert said("ฉันไปเรียนภาษาไทย วันจันทร์", split) == [
        "ฉัน",
        "ไป",
        "เรียน",
        "ภาษาไทย",
        "วัน",
        "จันทร์",
    ]
    assert said("ที่ดิน", split) == ["ที่ดิน"]  # land: not "at" + "soil"


def test_a_cut_never_falls_inside_a_cluster() -> None:
    """Not before a mark or a following vowel, not after a leading vowel,
    not before a consonant silenced by ์ - so กา is never found in กาะ."""
    assert boundaries("กาะ") == [0, 3]
    assert boundaries("เดือน") == [0, 3, 4, 5]
    assert boundaries("จันทร์") == [0, 2, 3, 6]
    split = ThaiSplit(thai_file(WORDS))
    assert said("กาะ", split) == ["กาะ"]
    assert said("จันทร์", split) == ["จันทร์"]


def test_a_word_the_pack_hasnt_got_stays_whole_between_its_words() -> None:
    split = ThaiSplit(thai_file(WORDS))
    # a name: one piece, not its letters
    assert said("ทักษิณไปเรียน", split) == ["ทักษิณ", "ไป", "เรียน"]
    words = split.words("ทักษิณไป")
    assert words[0].content  # a word all the same: the probe counts it a miss


def test_among_cuts_the_commoner_words_win() -> None:
    """ตากลม is ตา + กลม (eye, round) or ตาก + ลม (to expose to the wind):
    the ranks decide, as Chinese's and Vietnamese's splits' do."""
    assert said("ตากลม", ThaiSplit(thai_file(WORDS))) == ["ตา", "กลม"]
    rarer_eye = {**WORDS, "ตา": 20000, "กลม": 20000, "ตาก": 50, "ลม": 50}
    assert said("ตากลม", ThaiSplit(thai_file(rarer_eye))) == ["ตาก", "ลม"]


def test_every_word_of_the_pack_beats_leaving_its_cluster_over() -> None:
    """A word's cost is below a cluster left over at any rank a pack has
    (`LEFT_OVER`): a rare word the pack has is never left unfound."""
    assert thai.word_cost(65_535, 65_535) < thai.LEFT_OVER
    split = ThaiSplit(thai_file(WORDS))
    assert said("ซีมา", split) == ["ซี", "มา"]


def test_mai_yamok_is_a_word_of_its_own_and_no_content_word() -> None:
    split = ThaiSplit(thai_file(WORDS))
    words = split.words("ไปๆมาๆ")
    assert said("ไปๆมาๆ", split) == ["ไป", "ๆ", "มา", "ๆ"]
    assert [w.content for w in words] == [True, False, True, False]


def test_words_in_another_script_and_numbers() -> None:
    split = ThaiSplit(thai_file(WORDS))
    assert said("AIกินข้าว 5 จาน, ไทย-ฉัน", split) == [
        "AI",
        "กิน",
        "ข้าว",
        "จาน",
        "ไทย",
        "ฉัน",
    ]
    assert said("๒๕๖๙", split) == []  # Thai digits: no word


def test_lookups_and_the_words_a_learner_meets() -> None:
    file = thai_file(WORDS)
    dictionary = BasicDictionary(file, ThaiSplit(file), "th")
    line = "ฉันกินข้าว"
    assert dictionary.words(line) == [(0, 3), (3, 6), (6, 10)]
    assert dictionary.word_at(line, 4) == (3, 6)
    assert dictionary.lookup("ข้าว")[0].frequency_rank == 200
    assert [w.entry.frequency_rank for w in dictionary.words_in(line, "th")] == [
        3,
        40,
        200,
    ]


def test_a_word_spelt_as_the_speech_model_may_spell_it_is_found() -> None:
    """The speech model now and then writes ำ as ํ + า ("ประจํา"), and marks
    may come in another order: the split finds the word all the same, and
    the lookup finds it as the pack writes it (polyglotic-hq 389's
    captions)."""
    file = thai_file({**WORDS, "ประจำ": 700, "ปุ่ม": 3000})
    dictionary = BasicDictionary(file, ThaiSplit(file), "th")
    apart = "ประจําวัน"
    assert dictionary.words(apart) == [(0, 6), (6, 9)]
    assert dictionary.lookup(apart[:6])[0].headword == "ประจำ"
    swapped = "ปุ่ม"  # the tone mark before the vowel below
    assert dictionary.words(swapped) == [(0, 4)]
    assert dictionary.lookup(swapped)[0].headword == "ปุ่ม"
    # found as the pack's words, not left over (a left-over piece would join
    # whatever else is left over beside it)
    data = ThaiSplit(file)._read()
    assert thai.cut_run(apart, *data) == [(0, 6, True), (6, 9, True)]
    assert thai.cut_run(swapped, *data) == [(0, 4, True)]
    ranks = [w.entry.frequency_rank for w in dictionary.words_in(apart, "th")]
    assert ranks == [700, 60]  # ประจำ, วัน
