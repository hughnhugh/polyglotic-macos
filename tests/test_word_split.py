"""The word splits behind the `WordSplit` port (polyglotic-hq project 164):
Sudachi for Japanese, letters and simplemma for Spanish."""

import pytest

from polyglotic_desktop.adapters import spaced_split
from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.ports.word_split import SplitWord, WordSplit


def texts(split: WordSplit, line: str) -> list[str]:
    return [line[w.start : w.end] for w in split.words(line)]


def test_japanese_is_split_into_words_with_their_dictionary_forms() -> None:
    line = "私は昨日、寿司を食べました。"
    split = JapaneseSplit()
    assert texts(split, line) == [
        "私",
        "は",
        "昨日",
        "寿司",
        "を",
        "食べ",
        "まし",
        "た",
    ]
    words = {line[w.start : w.end]: w for w in split.words(line)}
    assert words["食べ"].lemmas == ("食べる",)
    assert words["まし"].lemmas == ("ます",)
    assert words["寿司"] == SplitWord(
        5, 7, kana="スシ"
    )  # its own dictionary form, content
    assert words["食べ"].kana == "タベ"  # read in its line, for furigana (511)
    assert not words["は"].content and not words["まし"].content  # particle, auxiliary
    assert words["食べ"].content and words["昨日"].content


def test_japanese_normalised_forms_come_first_they_tell_namesakes_apart() -> None:
    line = "猫がいた。することがある。"
    words = {line[w.start : w.end]: w for w in JapaneseSplit().words(line)}
    assert words["い"].lemmas == ("居る", "いる")  # "to be", not 要る "to need"
    assert words["する"].lemmas == ("為る",)
    assert words["ある"].lemmas == ("有る",)


def test_japanese_spaces_and_punctuation_are_not_words() -> None:
    assert texts(JapaneseSplit(), "「はい」、 そう。") == ["はい", "そう"]
    assert JapaneseSplit().words("") == []


def test_spanish_words_with_simplemmas_lemma() -> None:
    line = "¿Hablábamos de eso? Sí, y del agua."
    split = SpacedSplit("es")
    assert texts(split, line) == ["Hablábamos", "de", "eso", "Sí", "y", "del", "agua"]
    words = split.words(line)
    assert words[0].guesses == ("hablar",) and words[0].lemmas == ()
    assert words[1].guesses == ()  # "de" is its own lemma
    assert all(w.content for w in words)


def test_a_spanish_word_beside_chinese_characters_is_a_word_of_its_own() -> None:
    assert texts(SpacedSplit("es"), "用español说") == ["español"]


def test_without_simplemma_words_are_split_with_no_guesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed app leaves simplemma out (decision 0123): each word is
    still found, and looked up through the pack's own table."""
    import builtins

    real = builtins.__import__

    def without(name: str, *args: object, **kwargs: object) -> object:
        if name == "simplemma":
            raise ImportError(name)
        return real(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", without)
    found = SpacedSplit("ru").words("Он говорил долго")
    assert [(w.start, w.end, w.guesses) for w in found] == [
        (0, 2, ()),
        (3, 10, ()),
        (11, 16, ()),
    ]


def test_french_elided_words_are_cut_from_the_word_they_are_written_onto() -> None:
    """ "l'homme" is two words; "aujourd'hui" and Spanish's or English's
    apostrophes aren't cut (polyglotic-hq 341)."""
    split = SpacedSplit("fr")
    assert texts(split, "L’homme qu'il voit, aujourd'hui, c'est") == [
        "L’",
        "homme",
        "qu'",
        "il",
        "voit",
        "aujourd'hui",
        "c'",
        "est",
    ]
    assert texts(SpacedSplit("es"), "l'homme") == ["l'homme"]


def test_italian_elided_words_are_cut_as_frenchs_are() -> None:
    """polyglotic-hq 380: "dell'anno", "c'è" are two words each."""
    assert texts(SpacedSplit("it"), "Dell'anno c'è l'uomo, quest'anno") == [
        "Dell'",
        "anno",
        "c'",
        "è",
        "l'",
        "uomo",
        "quest'",
        "anno",
    ]


def guesses(language: str, word: str) -> tuple[str, ...]:
    return SpacedSplit(language).words(word)[0].guesses


def test_a_word_is_guessed_without_the_small_words_written_onto_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arabic's "and", "the", "with" and its pronouns, Indonesian's -nya and
    affixes, Hindi's endings are guessed off, likeliest first; Arabic's
    vowel marks first of all (polyglotic-hq 380). Without simplemma, as
    installed."""
    monkeypatch.setattr(spaced_split, "_lemmatizer", lambda: None)
    assert guesses("ar", "والكتاب")[:2] == ("كتاب", "الكتاب")  # longest first
    assert guesses("ar", "مدرسته")[:2] == ("مدرست", "مدرسة")
    assert guesses("ar", "كِتَابٌ") == ("كتاب",) + guesses("ar", "كتاب")
    assert guesses("id", "rumahnya") == ("rumah",)
    assert guesses("id", "nya") == ()  # nothing left
    assert guesses("id", "tumbuh-tumbuhan") == ("tumbuh",)
    assert guesses("es", "casas") == ()
    assert guesses("id", "ditempati")[:2] == ("tempati", "tempat")
    assert guesses("id", "menulis")[0] == "tulis"  # the nasal took its t
    assert guesses("id", "membaca") == ("baca",)
    assert guesses("hi", "उनके") == ("उनका",)
    assert guesses("hi", "लोगों")[0] == "लोग"
    assert SpacedSplit("it").words("dell'anno")[0].guesses[:2] == ("dello", "della")


def test_turkish_suffixes_are_guessed_off_and_a_name_is_cut_only_as_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turkish's suffixes are guessed off (`core.lexicon.turkish`), without
    simplemma as installed. A capitalised word inside a sentence is a name:
    Atlantik had been guessed as atlamak (to jump), Lee as le; the first
    word of a sentence is cut as any word (polyglotic-hq 388)."""
    monkeypatch.setattr(spaced_split, "_lemmatizer", lambda: None)
    assert "vermek" in guesses("tr", "verilen")
    words = SpacedSplit("tr").words("Bugün Atlantik. İnsanlar Okyanusu'nda.")
    assert words[1].guesses == ()  # Atlantik, inside its sentence
    assert words[2].guesses[0] == "insanlar" and "insan" in words[2].guesses
    assert "Okyanus" in words[3].guesses
    assert "atlamak" in SpacedSplit("tr").words("Atlantik")[0].guesses


def test_a_word_starts_a_sentence_after_a_full_stop_or_a_quote() -> None:
    text = 'Bir. "İki" üç? (Dört) beş'
    starts = [spaced_split.starts_sentence(text, text.index(w)) for w in text.split()]
    assert starts == [True, True, False, True, False]


def test_the_second_batchs_affixes_are_guessed_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filipino's linker, prefixes, infixes and doubled syllables; Czech's
    ne- and nej-; Greek's present endings; Persian's prefix and endings with
    or without the zero-width non-joiner, and its Arabic letters
    (polyglotic-hq 387). Without simplemma, as installed. Each language had
    been below the probe's floor without them (Filipino 77.1 %)."""
    monkeypatch.setattr(spaced_split, "_lemmatizer", lambda: None)
    assert guesses("tl", "isang")[0] == "isa"
    assert "noon" in guesses("tl", "noong")
    assert guesses("tl", "pang")[0] == "pa"  # two letters left by the linker
    assert guesses("tl", "tinatawag")[-1] == "tawag"
    assert "lakbay" in guesses("tl", "paglalakbay")
    assert "kilos" in guesses("tl", "kumikilos")
    assert guesses("tl", "pag-ukit")[0] == "ukit"
    assert guesses("tl", "iba't")[0] == "iba"
    assert guesses("cs", "neměl") == ("měl",)
    assert guesses("cs", "není") == ()  # ní ("her") is no guess
    assert guesses("cs", "nejsou")[0] == "jsou"
    assert guesses("el", "διαθέτουν") == ("διαθέτω",)
    assert guesses("el", "κρατούν") == ("κρατώ",)
    zwnj = "\u200c"
    assert guesses("fa", f"داستان{zwnj}های") == ("داستان",)
    assert guesses("fa", f"می{zwnj}کنم") == ("کنم",)
    assert guesses("fa", "میکنم")[:2] == (f"می{zwnj}کنم", "کنم")
    assert guesses("fa", "کشورهای")[0] == "کشور"
    assert guesses("fa", "كتاب") == ("کتاب",) + guesses("fa", "کتاب")
    assert guesses("fa", "تقریباً")[0] == "تقریبا"
    assert guesses("nl", "huizen") == ()  # a language without guesses
