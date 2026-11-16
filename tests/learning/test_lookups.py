"""Lookup context: the line a word was looked up in, and its translation
(the proof of concept's `context_for`, by language code)."""

from polyglotic_desktop.core.learning.lookups import LookupContext, lookup_context


def test_a_chinese_line_pairs_with_english_first() -> None:
    versions = {
        "zh": "我今天去超市",
        "vi": "Hôm nay tôi đi siêu thị",
        "en": "I went shopping",
    }
    assert lookup_context("我今天去超市", versions) == LookupContext(
        "我今天去超市", "I went shopping"
    )
    no_english = {"zh": "我今天去超市", "vi": "Hôm nay tôi đi siêu thị"}
    assert lookup_context("我今天去超市", no_english).translation.startswith("Hôm")


def test_any_other_line_pairs_with_the_chinese() -> None:
    versions = {
        "en": "I went shopping",
        "fr": "Je suis allé",
        "zh-hant": "我今天去超市",
    }
    assert lookup_context("I went shopping", versions).translation == "我今天去超市"
    assert lookup_context("Je suis allé", {"en": "I went", "fr": "Je suis allé"}) == (
        LookupContext("Je suis allé", "I went")
    )


def test_a_cut_off_row_and_a_line_alone() -> None:
    assert lookup_context(
        "我今天 …", {"zh": "我今天", "en": "Today I"}
    ) == LookupContext("我今天", "Today I")
    assert lookup_context("电脑", {}) == LookupContext("电脑", "")
