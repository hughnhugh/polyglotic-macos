"""Saved words found in a line: either script, inside longer words, never
across a word boundary (the proof of concept's test_vocab, on the real
word split), and English inflected forms by entry."""

from datetime import UTC, datetime

from tests.lexicon.sample import chinese_sample, english_sample

from polyglotic_desktop.core.learning.saved_words import SavedWord, SavedWordMatcher
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.shared import EntryId

AT = datetime(2026, 11, 4, tzinfo=UTC)


def saved(entry_id: str, headword: str, traditional: str = "") -> SavedWord:
    return SavedWord(
        EntryId(entry_id), headword, traditional, "", "", "saved", "", "", AT
    )


def test_saved_chinese_words_match_in_either_script_inside_words_not_across_them() -> (
    None
):
    zh = ChineseDictionary(chinese_sample())
    ids = {w: zh.lookup(w)[0].entry_id for w in ("电脑", "游戏", "个人")}
    matcher = SavedWordMatcher(
        [
            saved(ids["电脑"], "电脑", "電腦"),
            saved(ids["游戏"], "游戏", "遊戲"),
            saved(ids["个人"], "个人", "個人"),
        ]
    )

    def spans(line: str) -> list[tuple[int, int, str]]:
        found = matcher.spans(line, zh.words_in(line, "hsk-2025"))
        return [(s.start, s.end, s.entry_id) for s in found]

    assert spans("我的电脑") == [(2, 4, ids["电脑"])]
    assert spans("我的電腦") == [(2, 4, ids["电脑"])]
    assert spans("一起打游戏") == [(3, 5, ids["游戏"])]  # inside 打游戏
    assert spans("这个人") == []  # 这个/人 - 个人 would cut across 这个
    assert spans("English only") == []


def test_a_saved_english_word_matches_its_inflected_forms_but_not_inside_words() -> (
    None
):
    en = EnglishDictionary(english_sample())
    run = en.entry_for_word("run")
    assert run is not None
    matcher = SavedWordMatcher([saved(run.entry_id, "run")])
    line = "She ran, he runs, they keep running to brunch"
    found = matcher.spans(line, en.words_in(line, "en-frequency"))
    assert [line[s.start : s.end] for s in found] == ["ran", "runs", "running"]


def test_nothing_saved_finds_nothing() -> None:
    zh = ChineseDictionary(chinese_sample())
    assert (
        SavedWordMatcher([]).spans("我的电脑", zh.words_in("我的电脑", "hsk-2025"))
        == []
    )
