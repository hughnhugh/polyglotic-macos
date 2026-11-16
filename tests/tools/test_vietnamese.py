"""Vietnamese's own rules for its pack (polyglotic-hq 325, decision 0121):
which of Wiktionary's words are a caption's, Wiktionary's words of several
syllables, and counting words in subtitles by the word split."""

import gzip
from pathlib import Path

from pytest import approx
from tests.tools.test_packs import VIETNAMESE
from tools.dictionaries import kaikki, vietnamese


def test_only_the_latin_script_is_a_captions() -> None:
    assert vietnamese.is_latin("học sinh") and vietnamese.is_latin("ki-lô-mét")
    assert not vietnamese.is_latin("學生") and not vietnamese.is_latin("123")


def test_a_word_of_several_syllables_is_an_entry_where_words_are_spaced() -> None:
    spaced = kaikki.read_language(kaikki.lines_of(VIETNAMESE, "vi"), spaced_words=True)
    assert "học sinh" in [e.word for e in spaced.entries]
    assert spaced.forms["bất kỳ"] == {"bất kì"}
    phrases = kaikki.read_language(kaikki.lines_of(VIETNAMESE, "vi"))
    assert "học sinh" not in [e.word for e in phrases.entries]


def test_words_are_counted_as_the_word_split_cuts_them(tmp_path: Path) -> None:
    """A comma or a number ends a run of syllables, and a syllable the
    dictionary hasn't got is a word of its own."""
    corpus = tmp_path / "vi.txt.gz"
    text = "Các học sinh học.\nHọc sinh, sinh viên 3 người.\n"
    corpus.write_bytes(gzip.compress(text.encode("utf-8")))
    counted = vietnamese.counted_words(corpus, {"học sinh", "sinh viên"})
    six = {"các": 1, "học sinh": 2, "học": 1, "sinh viên": 1, "người": 1}
    assert counted == approx({word: n / 6 for word, n in six.items()})
    assert counted.hyphenated
