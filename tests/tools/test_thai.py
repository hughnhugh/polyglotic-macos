"""Thai's own rules for its pack (polyglotic-hq 389, decision 0173): which of
Wiktionary's lines are words, and counting words in sentences written
without spaces."""

from pathlib import Path

import pytest
from tools.dictionaries import thai
from tools.dictionaries.kaikki import WiktEntry


def test_the_second_count_cuts_as_the_apps_split_will(tmp_path: Path) -> None:
    """The first count has no ranks, and a tie goes to the longer first
    word: "ตากลม" read ตาก + ลม (to expose to the wind). The second count
    cuts with the first's ranks, as the app's split does: ตา + กลม (round
    eyes), the commoner words - so ตาก isn't counted for it."""
    corpus = tmp_path / "th.txt"
    lines = ["ตา", "กลม"] * 5 + ["ตากลม"]
    corpus.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counted = thai.counted_words(corpus, ["ตา", "กลม", "ตาก", "ลม"])
    assert "ตาก" not in counted and "ลม" not in counted
    assert counted["ตา"] == counted["กลม"] == 0.5


def test_a_lines_forms_that_are_other_words_are_dropped() -> None:
    line: dict[str, object] = {
        "word": "หมา",
        "pos": "noun",
        "forms": [
            {"form": "mǎa", "tags": ["romanization"]},
            {"form": "ตัว", "tags": ["classifier"]},
            {"form": "หมาๆ", "tags": ["alternative"]},
        ],
    }
    letter: dict[str, object] = {"word": "ก", "pos": "character"}
    english: dict[str, object] = {"word": "dog", "pos": "noun"}
    (kept,) = thai.words([line, letter, english])
    forms = kept["forms"]
    assert isinstance(forms, list)
    assert [f["form"] for f in forms] == ["mǎa", "หมาๆ"]
    assert thai.caption_word("ณ") and not thai.caption_word("จ")


def test_a_word_is_counted_as_the_pack_writes_it(tmp_path: Path) -> None:
    """ำ written as ํ + า counts for the word as the pack writes it."""
    corpus = tmp_path / "th.txt"
    corpus.write_text("ประจําวัน\nประจำ\n", encoding="utf-8")
    counted = thai.counted_words(corpus, ["ประจำ", "วัน"])
    assert counted == {"ประจำ": 2 / 3, "วัน": 1 / 3}


def _entry(word: str, pos: str, *meanings: str, n: int = 1) -> WiktEntry:
    return WiktEntry(f"{word}|{pos}|{n}", word, pos, meanings)


def test_a_common_word_opens_on_its_everyday_meaning() -> None:
    """Wiktionary lists โลก's Pali sense, "land; country", before "world",
    and ยัง's verb before its adverb "still" (polyglotic-hq 448, 461): the
    table read by hand moves the meaning first, and its entry first among
    the word's, in the places the word's entries had - keys untouched."""
    entries = [
        _entry("ยัง", "verb", "to be, have", "to exist"),
        _entry("ดี", "adj", "good"),
        _entry("ยัง", "adv", "still; yet", "also; too", n=3),
        _entry(
            "โลก", "noun", "land; country", "mankind; humanity", "world", "the Earth"
        ),
    ]
    table = {w: thai.FIRST_SENSES[w] for w in ("ยัง", "โลก")}
    out = thai.first_senses(entries, table)
    assert [e.key for e in out] == ["ยัง|adv|3", "ดี|adj|1", "ยัง|verb|1", "โลก|noun|1"]
    assert out[0].meanings == ("still; yet", "also; too")
    assert out[3].meanings == (
        "world",
        "the Earth",
        "land; country",
        "mankind; humanity",
    )


def test_a_meaning_wiktionary_no_longer_has_stops_the_build() -> None:
    entries = [_entry("โลก", "noun", "land; country", "planet")]
    with pytest.raises(ValueError, match="โลก"):
        thai.first_senses(entries, {"โลก": ("world",)})
