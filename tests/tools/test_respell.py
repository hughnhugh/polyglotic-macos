"""The English respelling (polyglotic-hq 449, 471): the user's six
examples exactly, the long i, the pick among CMUdict's pronunciations and
the heteronyms. Offline: a few lines of CMUdict, as it writes them."""

from pathlib import Path

import pytest
from tools.dictionaries import respell
from tools.dictionaries.respell import Style, respelled

CMUDICT = """\
and AH0 N D
and(2) AE1 N D
anemone AE1 N IH0 M OW2 N
anemone(2) AH0 N EH1 M AH0 N IY0
chaos K EY1 AA0 S
colonel K ER1 N AH0 L
don't D OW1 N T
don't(2) D OW1 N
organized AO1 R G AH0 N AY2 Z D
receipt R IH0 S IY1 T
receipt(2) R IY0 S IY1 T
record R AH0 K AO1 R D
record(2) R EH1 K ER0 D
record(3) R IH0 K AO1 R D
subtle S AH1 T AH0 L
wednesday W EH1 N Z D IY0
wednesday(2) W EH1 N Z D EY2
"""

PICKS = """\
word\tpronunciation\talternates\twhy
anemone\tAH0 N EH1 M AH0 N IY0\t\tWiktionary's first American
wednesday\tW EH1 N Z D EY2\tW EH1 N Z D IY0\tWiktionary's first American
record\tR EH1 K ER0 D\tR IH0 K AO1 R D (verb)\theteronym: the noun is commoner
"""


def table() -> dict[str, respell.Respelling]:
    cmudict = respell.read_cmudict(CMUDICT)
    words = ["chaos", "receipt", "subtle", "colonel", "wednesday", "anemone", "record"]
    rows = respell.table(
        [*words, "and", "organised", "dont", "ii"], cmudict, respell.read_picks(PICKS)
    )
    return {r.word: r for r in rows}


def test_the_users_six_come_out_exactly() -> None:
    rows = table()
    assert [rows[w].respelling for w in ("chaos", "receipt", "subtle", "colonel")] == [
        "KAY-oss",
        "ri-SEET",
        "SUT-uhl",
        "KER-nuhl",
    ]
    # CMUdict lists these two first another way; the picks file chooses
    assert rows["wednesday"].respelling == "WENZ-day"
    assert rows["anemone"].respelling == "uh-NEM-uh-nee"


def test_a_heteronym_shows_the_commoner_sense_and_the_other_labelled() -> None:
    record = table()["record"]
    assert record.respelling == "REK-erd"
    assert record.alternates == ("ri-KORD (verb)",)
    assert table()["wednesday"].alternates == ("WENZ-dee",)


def test_without_a_pick_the_first_stressed_pronunciation_wins() -> None:
    # CMUdict lists the weak "uhnd" first
    assert table()["and"].respelling == "AND"


def test_a_british_spelling_or_a_missing_apostrophe_is_still_found() -> None:
    rows = table()
    assert rows["organised"].respelling == "OR-guh-nyzd"
    assert rows["dont"].respelling == "DOHNT"
    assert "ii" not in rows  # not in CMUdict at all: no respelling


@pytest.mark.parametrize(
    ("said", "y_e", "igh", "y"),
    [
        ("N AY1 T", "NYTE", "NIGHT", "NYT"),  # night
        ("T AY1 M", "TYME", "TIGHM", "TYM"),  # time
        ("M AY1", "MY", "MIGH", "MY"),  # my
        (
            "L AY1 B R EH2 R IY0",
            "LY-brair-ee",
            "LIGH-brair-ee",
            "LY-brair-ee",
        ),  # library
        ("AY1 S", "EYESS", "EYESS", "EYESS"),  # ice: no consonant before it
        ("AY1 L AH0 N D", "EYE-luhnd", "EYE-luhnd", "EYE-luhnd"),  # island
    ],
)
def test_the_long_i_in_each_style(said: str, y_e: str, igh: str, y: str) -> None:
    assert respelled(said, Style(long_i="y-e")) == y_e
    assert respelled(said, Style(long_i="igh")) == igh
    assert respelled(said, Style(long_i="y")) == y


def test_the_vowel_of_book_and_a_final_ee() -> None:
    assert respelled("P UH1 L") == "PUUL"  # pull, never "pool"
    assert respelled("P UH1 L", Style(book="oo")) == "POOL"
    assert respelled("HH AE1 P IY0") == "HAP-ee"
    assert respelled("HH AE1 P IY0", Style(happy="i")) == "HAP-i"


def test_a_closing_s_is_doubled_only_where_it_could_read_as_z() -> None:
    assert respelled("K EY1 AA0 S") == "KAY-oss"  # chaos: the word ends
    assert respelled("R EH1 S AH0 P IY0") == "RESS-uh-pee"  # recipe: a vowel follows
    assert respelled("K W EH1 S CH AH0 N") == "KWES-chuhn"  # question


def test_an_r_stays_with_a_stressed_vowel_before_it_only() -> None:
    assert respelled("S T AO1 R IY0") == "STOR-ee"  # story, not STAW-ree
    assert respelled("V EH1 R IY0") == "VAIR-ee"  # very
    # library, as CMUdict has it: an unstressed e keeps its r too
    assert respelled("L AY1 B R EH0 R IY2") == "LY-brair-ee"
    assert respelled("K AE1 R IY0") == "KAIR-ee"  # carry: as very, not KAR-ee (car)
    # an unstressed i lets the r start the stressed syllable (not deer-EK-ter)
    assert respelled("D IH0 R EH1 K T ER0") == "di-REK-ter"
    # s f doesn't start an English syllable here (not TRAN-sfer)
    assert respelled("T R AE1 N S F ER0") == "TRANS-fer"


def test_a_sound_cmudict_does_not_have_is_an_error() -> None:
    with pytest.raises(ValueError):
        respelled("K EY1 XX0 S")
    with pytest.raises(ValueError):
        respelled("K EY AA0 S")  # a vowel without its stress


def test_the_shipped_picks_all_respell() -> None:
    picks = respell.read_picks(respell.PICKS.read_text(encoding="utf-8"))
    assert len(picks) > 100
    for word, pick in picks.items():
        assert respelled(pick.pronunciation), word
        for said, _ in pick.alternates:
            assert respelled(said), word


def test_the_commonest_words_are_letters_with_one_inner_apostrophe() -> None:
    frequencies = {
        "the": 5.0,
        "don't": 1.0,
        "'s": 3.0,
        "2020": 2.0,
        "u.s": 1.5,
        "cat": 0.5,
    }
    assert respell.commonest(frequencies, 2) == ["the", "don't"]


def test_the_table_and_its_credits(tmp_path: Path) -> None:
    path = tmp_path / "respelling-en.tsv"
    respell.write(table().values(), path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "word\trespelling\talternates"
    assert "record\tREK-erd\tri-KORD (verb)" in lines
    text = respell.credits()
    assert "Carnegie Mellon University" in text and "CC BY-SA 4.0" in text
    assert "THIS SOFTWARE IS PROVIDED" in text
