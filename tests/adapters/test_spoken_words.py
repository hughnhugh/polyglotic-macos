"""Dictionary-backed word counting for speaking pace."""

from pathlib import Path

import sudachidict_small
from tests.lexicon.sample import FakeDictionaryFile, chinese_sample

from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.adapters.spoken_words import (
    PaceDictionary,
    count_chinese_words,
    spoken_word_counter,
)
from polyglotic_desktop.core.lexicon.basic import BasicDictionary, absent
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary

SUDACHI_DIC = Path(sudachidict_small.__file__).parent / "resources" / "system.dic"


def test_chinese_counter_counts_dictionary_words_and_non_han_words() -> None:
    dictionary = ChineseDictionary(chinese_sample())
    assert count_chinese_words(dictionary, "研究生命起源。") == 3
    assert count_chinese_words(dictionary, "这个人打游戏，画蛇添足！") == 4
    assert count_chinese_words(dictionary, "我用 iPhone 15 打游戏。") == 5
    assert count_chinese_words(dictionary, "電腦、足球和北京。") == 4


def test_spoken_word_counter_uses_installed_dictionary_splits_and_falls_back() -> None:
    japanese_pack = BasicDictionary(
        FakeDictionaryFile((), {}), JapaneseSplit(SUDACHI_DIC), "ja"
    )
    chinese = ChineseDictionary(chinese_sample())
    fallback_calls: list[tuple[str, str | None]] = []

    def fallback(text: str, language: str | None) -> int:
        fallback_calls.append((text, language))
        return 99

    dictionaries: dict[str, PaceDictionary] = {"ja": japanese_pack, "zh": chinese}
    counter = spoken_word_counter(dictionaries.get, fallback=fallback)

    assert counter("私は昨日、寿司を食べました。", "ja") == 8
    assert counter("这个人打游戏，画蛇添足！", "zh") == 4
    assert counter("這個人打遊戲，畫蛇添足！", "zh-Hant") == 4
    assert fallback_calls == []

    assert counter("Hello world", "en") == 99
    assert fallback_calls == [("Hello world", "en")]


def test_japanese_without_sudachi_or_absent_pack_falls_back_to_system_breaks() -> None:
    spaced_ja = BasicDictionary(
        FakeDictionaryFile((), {}), SpacedSplit("ja", simplemma=False), "ja"
    )
    calls: list[tuple[str, str | None]] = []

    def fallback(text: str, language: str | None) -> int:
        calls.append((text, language))
        return 6

    for pack in (spaced_ja, absent("ja")):

        def lookup(_code: str, chosen: BasicDictionary = pack) -> BasicDictionary:
            return chosen

        counter = spoken_word_counter(lookup, fallback=fallback)
        assert counter("小鳥が青い空を飛ぶ。", "ja") == 6
    assert len(calls) == 2


def test_main_pace_word_counter_routes_installed_tools() -> None:
    from tests.ui.fakes import chinese_tools

    from polyglotic_desktop.main import pace_word_counter

    tools = chinese_tools()
    tools.basic["ja"] = BasicDictionary(
        FakeDictionaryFile((), {}), JapaneseSplit(SUDACHI_DIC), "ja"
    )
    counter = pace_word_counter(tools)
    assert counter("私は昨日、寿司を食べました。", "ja") == 8
    assert counter("这个人打游戏，画蛇添足！", "zh") == 4
    assert counter("Five birds fly over water.", "en") == 5
