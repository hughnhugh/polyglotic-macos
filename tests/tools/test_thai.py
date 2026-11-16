"""Thai's own rules for its pack (polyglotic-hq 389, decision 0173): which of
Wiktionary's lines are words, and counting words in sentences written
without spaces."""

from pathlib import Path

from tools.dictionaries import thai


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
