"""A word's language by its script, where its row's says otherwise
(polyglotic-hq 337, decision 0129). Made-up words."""

import pytest

from polyglotic_desktop.core.lexicon.scripts import is_latin, word_script, written_in


@pytest.mark.parametrize(
    ("word", "row", "expected"),
    [
        # Chinese characters outside a Chinese, Japanese or Cantonese row
        ("北京", "en", "zh"),
        ("北京", None, "zh"),
        ("北京", "ru", "zh"),
        ("北京", "vi", "zh"),
        # ... and inside one: the row's own
        ("北京", "zh", None),
        ("北京", "zh-hant", None),
        ("北京", "ZH-Hant", None),
        ("東京", "ja", None),
        ("北京", "yue", None),
        # Latin letters in a row not written in them, or not known
        ("iPhone", "zh", "en"),
        ("OK", "zh-hant", "en"),
        ("OK", "ja", "en"),
        ("OK", "ko", "en"),
        ("OK", "ru", "en"),
        ("OK", "yue", "en"),
        ("weekend", None, "en"),
        # ... and in one that is: the row's own
        ("weekend", "en", None),
        ("phở", "vi", None),
        ("mañana", "es", None),
        # every other script told apart, outside a row written in it
        ("руку", "en", "ru"),
        ("руку", "zh", "ru"),
        ("руку", None, "ru"),
        ("руку", "ru", None),
        ("руку", "uk", None),
        ("ひらがな", "en", "ja"),
        ("食べる", "zh", "ja"),  # kana with kanji: Japanese
        ("カタカナ", "ja", None),
        ("東京", "ko", "zh"),
        ("은행에", "en", "ko"),
        ("은행에", "zh", "ko"),
        ("은행에", "ko", None),
        ("สวัสดี", "en", "th"),
        ("สวัสดี", "th", None),
        ("مرحبا", "en", "ar"),
        ("مرحبا", "fa", None),
        ("γεια", "en", "el"),
        ("नमस्ते", "en", "hi"),
        ("שלום", "en", "he"),
        # neither: the row's own
        ("123", "zh", None),
        ("", "zh", None),
    ],
)
def test_a_words_script_names_its_language_where_its_row_isnt_written_in_it(
    word: str, row: str | None, expected: str | None
) -> None:
    assert written_in(word, row) == expected


def test_a_words_script_is_its_letters_kana_first() -> None:
    assert word_script("食べる") == "kana"
    assert word_script("ラーメン") == "kana"  # with ー
    assert word_script("北京") == "han"
    assert word_script("OK") == "latin"
    assert word_script("2024!") is None


def test_latin_is_letters_of_the_latin_script_only() -> None:
    assert is_latin("Let's")
    assert is_latin("café")
    assert not is_latin("OKです")
    assert not is_latin("123")
    assert not is_latin("")
