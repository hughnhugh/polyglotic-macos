"""Frequency lists for a pack's ranks (polyglotic-hq 325, decision 0120):
a list of counts, averaging lists, and the hyphen and affix rules."""

import gzip
import zipfile
from pathlib import Path

import pytest
from pytest import approx
from tests.tools.wordfreq_data import msgpack
from tools.dictionaries import frequency, packs, wordfreq_ranks


def test_a_list_of_counts_becomes_shares_in_lower_case(tmp_path: Path) -> None:
    path = tmp_path / "ru_50k.txt"
    path.write_text("я 6\nЯ 2\nчто-то 2\nnot-a-count x\n", encoding="utf-8")
    found = frequency.counted(path)
    assert found == approx({"я": 0.8, "что-то": 0.2})
    assert found.hyphenated and found.floor == approx(0.2)


def test_lists_are_averaged_over_the_lists_that_could_have_a_word() -> None:
    wordfreq = frequency.Frequencies({"я": 0.6, "что": 0.4}, hyphenated=False)
    subtitles = frequency.Frequencies({"я": 0.8, "что-то": 0.2}, hyphenated=True)
    both = frequency.mean([wordfreq, subtitles])
    assert both["я"] == approx(0.7)
    assert both["что"] == approx(0.2)  # the subtitles never met it
    # wordfreq splits at hyphens, so it says nothing about "что-то"
    assert both["что-то"] == approx(0.2)
    assert both.hyphenated
    assert frequency.mean([wordfreq]) is wordfreq


def test_an_affix_is_never_a_word() -> None:
    """ "в-" had been given "в"'s frequency: wordfreq has no hyphens
    (polyglotic-hq 325: Russian's commonest entry was a prefix)."""
    freq = frequency.Frequencies({"в": 0.03, "ить": 0.001}, hyphenated=False)
    assert packs.frequency_of("в-", freq) == 0.0
    assert packs.frequency_of("-ить", freq) == 0.0
    assert packs.frequency_of("в", freq) == 0.03


def test_a_hyphenated_word_from_its_parts_only_where_the_list_splits_them() -> None:
    parts = {"премьер": 0.0002, "министр": 0.0002, "у": 0.01, "т": 0.001}
    wordfreq = frequency.Frequencies(parts, hyphenated=False)
    # a phrase of its parts, ten times rarer (packs.JOINED; polyglotic-hq
    # 380: Portuguese's tem-tem had been its 69th word)
    assert packs.frequency_of("премьер-министр", wordfreq) == approx(0.00001)
    assert packs.frequency_of("у-т", wordfreq) > 0  # wordfreq can't tell
    assert packs.frequency_of("у-у", wordfreq) < wordfreq["у"] / 10
    subtitles = frequency.Frequencies(
        {**parts, "премьер-министр": 0.00005}, hyphenated=True
    )
    assert packs.frequency_of("премьер-министр", subtitles) == 0.00005
    # never met whole: rarer than the list's rarest word, not as common
    # as its parts make it seem
    assert subtitles.floor == 0.00005
    assert packs.frequency_of("у-т", subtitles) == 0.00005
    assert packs.frequency_of("абу-даби", subtitles) == 0.0  # parts unknown


def _wheel(path: Path, lists: dict[str, list[list[str]]]) -> Path:
    """A wordfreq wheel holding `lists`: file stem ("small_id") -> buckets."""
    with zipfile.ZipFile(path, "w") as wheel:
        for stem, buckets in lists.items():
            data = msgpack([{"format": "cB", "version": 1}, *buckets])
            wheel.writestr(f"wordfreq/data/{stem}.msgpack.gz", gzip.compress(data))
    return path


def test_a_language_with_only_a_small_list_is_read_from_it(tmp_path: Path) -> None:
    """Eleven caption languages have only a small wordfreq list: Indonesian,
    Korean, Turkish... (polyglotic-hq 374). It had been a KeyError."""
    wheel = _wheel(tmp_path / "w.whl", {"small_id": [["yang"], ["dan", "di"]]})
    assert wordfreq_ranks.frequencies(wheel, "id") == approx(
        {"yang": 1.0, "dan": 10 ** (-1 / 100), "di": 10 ** (-1 / 100)}
    )


def test_a_large_list_is_read_before_a_small_one(tmp_path: Path) -> None:
    wheel = _wheel(
        tmp_path / "w.whl", {"large_es": [["de"]], "small_es": [["que"], ["de"]]}
    )
    assert wordfreq_ranks.frequencies(wheel, "es") == {"de": 1.0}


def test_filipino_is_read_under_wordfreqs_own_code(tmp_path: Path) -> None:
    """The app and kaikki call Filipino "tl"; wordfreq's list is "fil"
    (polyglotic-hq 387). It had been a KeyError."""
    wheel = _wheel(tmp_path / "w.whl", {"small_fil": [["ang"], ["ng"]]})
    assert wordfreq_ranks.frequencies(wheel, "tl") == approx(
        {"ang": 1.0, "ng": 10 ** (-1 / 100)}
    )


def test_a_language_wordfreq_hasnt_got_says_so(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "w.whl", {"small_id": [["yang"]]})
    with pytest.raises(KeyError, match="'th'"):
        wordfreq_ranks.frequencies(wheel, "th")


def test_sentences_are_counted_by_the_words_a_split_finds(tmp_path: Path) -> None:
    """Common Voice's Persian sentences give ranks beside wordfreq's
    (polyglotic-hq 374, 387): each word as the app's split finds it - a
    word with a zero-width non-joiner whole - in lower case."""
    from polyglotic_desktop.core.lexicon.english import words

    path = tmp_path / "fa.txt"
    path.write_text("داستان\u200cها و کتاب\nو Kitab kitab\n", encoding="utf-8")
    counted = frequency.sentences_counted(path, words)
    assert counted == approx(
        {"داستان\u200cها": 1 / 6, "و": 2 / 6, "کتاب": 1 / 6, "kitab": 2 / 6}
    )
    assert counted.hyphenated
