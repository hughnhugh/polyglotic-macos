"""Korean in Revised Romanization and Hindi in Latin letters, by rule
(polyglotic-hq 370 and 511): the sound changes RR writes at a syllable's
join, and Hindi's unsaid a's left out, in Wiktionary's letters. Words
from korean.go.kr's examples and Wiktionary."""

import pytest

from polyglotic_desktop.core.lexicon.hindi import HindiReader
from polyglotic_desktop.core.lexicon.hindi import romanized as hindi
from polyglotic_desktop.core.lexicon.korean import KoreanReader
from polyglotic_desktop.core.lexicon.korean import romanized as korean


@pytest.mark.parametrize(
    ("word", "said"),
    [
        ("한국어", "hangugeo"),  # liaison
        ("국물", "gungmul"),  # nasalization
        ("신라", "silla"),  # liquidization
        ("종로", "jongno"),  # ㄹ after ㅇ
        ("같이", "gachi"),  # palatalization
        ("좋다", "jota"),  # ㅎ aspiration
        ("놓고", "noko"),
        ("많다", "manta"),
        ("읽다", "ikda"),  # a double final, tensing not written
        ("서울", "seoul"),
    ],
)
def test_korean_is_written_as_said(word: str, said: str) -> None:
    assert korean(word) == said


def test_each_run_of_hangul_has_its_reading() -> None:
    text = "서울에 갔어요, OK?"
    found = [(text[r.start : r.end], r.text) for r in KoreanReader().readings(text)]
    assert found == [("서울에", "seoure"), ("갔어요", "gasseoyo")]


@pytest.mark.parametrize(
    ("word", "said"),
    [
        ("किताब", "kitāb"),  # the last a isn't said
        ("कमरा", "kamrā"),  # nor one between a vowel and a consonant with one
        ("हिंदी", "hindī"),  # ं as the next consonant's nasal
        ("रंग", "raṅg"),
        ("हैं", "ha͠i"),  # a nasal vowel at the end
        ("सामान्य", "sāmānya"),  # y keeps its a after a cluster
        ("धर्म", "dharm"),  # m doesn't
        ("भारतीय", "bhārtīya"),
        ("गाड़ी", "gāṛī"),  # the nukta
        ("ज़्यादा", "zyādā"),
    ],
)
def test_hindi_as_wiktionary_writes_it(word: str, said: str) -> None:
    assert hindi(word) == said


def test_a_precomposed_nukta_letter_reads_as_its_two() -> None:
    assert hindi("ज़रा") == hindi("ज़रा") == "zarā"


def test_each_hindi_word_has_its_reading() -> None:
    text = "मेरा कमरा, 2024"
    found = [(text[r.start : r.end], r.text) for r in HindiReader().readings(text)]
    assert found == [("मेरा", "merā"), ("कमरा", "kamrā")]


def test_what_the_rules_miss_a_noun_keeps_its_h() -> None:
    """RR writes a noun's h after ㄱ ㄷ ㅂ (북한 Bukhan, 축하 chukha): telling
    a noun needs a word list, which the rules haven't got (370: 5 of 1,542
    FLEURS words). Pinned, so a list added later shows here."""
    assert korean("북한") == "bukan"
    assert korean("축하") == "chuka"
