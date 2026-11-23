"""The coverage probe (polyglotic-hq project 157's rule for the basic
tier): how it counts, and - where the packs are built - that Spanish and
Japanese pass the basic floor.

The packs need about 350 MB of sources, so the second test runs only where
they're built: `.github/workflows/dictionary-packs.yml` builds them and
sets POLYGLOTIC_PACKS; elsewhere it's skipped."""

import os
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from tests.lexicon.sample import FakeDictionaryFile
from tests.lexicon.test_basic import SPANISH, FakeSplit
from tests.lexicon.test_compounds import german
from tests.tools.test_packs import sources
from tools.dictionaries import coverage, packs
from tools.dictionaries.packs import PACKS

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_split import SplitWord


def test_the_probe_counts_content_words_with_letters() -> None:
    split = FakeSplit({"de": SplitWord(0, 0, content=False)})
    spanish = BasicDictionary(SPANISH, split, "es")
    result = coverage.measure(
        spanish, split, ["vengo de casa 1990", "Darwin y Wallace", "casa"]
    )
    # "de" isn't a content word, "1990" has no letter
    assert (result.found, result.counted) == (4, 6)
    assert result.misses == {"y": 1, "Wallace": 1}
    assert f"{result.share:.3f}" == "0.667"
    assert "66.7 % of 6 content words" in str(result)


def test_a_word_the_card_shows_by_its_parts_counts_as_found() -> None:
    """polyglotic-hq DECISIONS #227: a word the pack hasn't got whole, but
    whose card shows it by its parts with every part found, is found - as
    Thai's, Vietnamese's and Cantonese's word splits already count it."""
    d = german()
    line = "Internetmaterialien Arbeitsplatz T-Rex Kovelun Haus"
    result = coverage.measure(d, FakeSplit(), [line])
    # Internet + materialien and Arbeits + platz are shown by their parts;
    # T-Rex's "Rex" isn't in the pack, and Kovelun has no parts
    assert (result.found, result.counted, result.by_parts) == (3, 5, 2)
    assert result.misses == {"T-Rex": 1, "Kovelun": 1}
    assert "(2 by their parts)" in str(result)


def test_a_pack_records_its_coverage_and_says_if_it_passes(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    paths = sources(tmp_path / "upstream")
    stats = packs.build(PACKS["ja"], paths, tmp_path)
    # a four-word fixture finds little of the real sentences
    assert stats["passes the basic floor"] is False
    for name in ("jmdict.sqlite", "jmdict-zh.sqlite"):
        share = float(SqliteDictionary(tmp_path / name).info["coverage"])
        assert 0 < share < coverage.FLOORS["basic"]


def test_every_pack_has_its_sentences() -> None:
    for language in PACKS:
        lines = coverage.sentences(language)
        assert len(lines) == 100 and all(line.strip() for line in lines)


PACKS_BUILT = os.environ.get("POLYGLOTIC_PACKS")


@pytest.mark.skipif(not PACKS_BUILT, reason="the packs aren't built (POLYGLOTIC_PACKS)")
@pytest.mark.parametrize("language", sorted(PACKS))
def test_each_pack_passes_the_basic_tiers_floor(language: str) -> None:
    pack = PACKS[language]
    result = coverage.probe(Path(str(PACKS_BUILT)) / f"{pack.name}.sqlite", language)
    print(f"{pack.name}: {result}")
    assert result.share >= coverage.FLOORS["basic"], str(result)


def test_running_words_weigh_each_word_by_its_frequency() -> None:
    split = FakeSplit()
    spanish = BasicDictionary(SPANISH, split, "es")
    frequencies = {"casa": 0.5, "wallace": 0.2, "1990": 0.2, "дом": 0.1}
    result = coverage.running_words(spanish, frequencies, "es")
    # numbers and words in another script aren't counted
    assert (result.words, f"{result.share:.3f}") == (2, f"{0.5 / 0.7:.3f}")
    assert result.misses == {"wallace": 0.2}
    assert "71.4 % of running words found" in str(result)


RUNNING_WORDS_TARGETS = {"ru": 0.95}
"""The share of running words a pack must find (polyglotic-hq 298: a full
Russian dictionary finds 95 %)."""


@pytest.mark.skipif(not PACKS_BUILT, reason="the packs aren't built (POLYGLOTIC_PACKS)")
@pytest.mark.parametrize("language", sorted(RUNNING_WORDS_TARGETS))
def test_russian_finds_its_target_share_of_running_words(language: str) -> None:
    pack = PACKS[language]
    info = SqliteDictionary(Path(str(PACKS_BUILT)) / f"{pack.name}.sqlite").info
    print(f"{pack.name}: {info['running_words']} of running words")
    assert float(info["running_words"]) >= RUNNING_WORDS_TARGETS[language]


def test_the_commonest_words_are_each_found_or_said_why_not(
    monkeypatch: MonkeyPatch,
) -> None:
    """A pack's build checks wordfreq's 200 commonest words in its script
    (polyglotic-hq 390): Polish's "i" had had no entry."""
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    freq = {"casa": 1e-2, "the": 5e-3, "supe": 1e-3, "1990": 9e-4, "xyz": 1e-4}
    monkeypatch.setitem(coverage.EXEMPT, "es", {"the": "English"})
    result = coverage.top_words(spanish, freq, "es", top=4)
    # "1990" isn't in the script; the top 4 are casa, the, supe, xyz
    assert result.missing == [(4, "xyz")] and result.exempt == [(2, "the")]
    assert str(result) == "missing xyz (4); exempt the (2)"


def test_thais_build_checks_its_commonest_words_by_common_voice(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """wordfreq has no Thai list, so the check had skipped Thai; its pack
    is ranked by Common Voice's sentences, and their commonest words are
    checked instead, commonest first (polyglotic-hq 394, 396)."""
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    out = tmp_path / "out"
    out.mkdir()
    stats = packs.build(PACKS["th"], sources(tmp_path / "upstream"), out)
    assert stats["finds its commonest words"] is True
    assert str(stats["top words"]).startswith("missing none")
    top = coverage.probe_top_words_of(
        out / "wiktth.sqlite", "th", {"กิน": 1e-1, "ฟฟฟ": 5e-1, "หมา": 1e-2}
    )
    assert top.missing == [(1, "ฟฟฟ")]


def test_an_elided_word_is_looked_up_as_captions_write_it() -> None:
    """wordfreq cuts "l'homme" into "l" and "homme"; the split gives "l'",
    looked up as le or la (polyglotic-hq 390). French's "l" and "j" had
    passed only as the letters' entries, which 387 dropped."""
    french = FakeDictionaryFile(
        [EntryRecord("wiktfr:le", "le", "", "", ("(article) the",), 3)],
        {"le": ["wiktfr:le"]},
    )
    assert coverage.finds(BasicDictionary(french, FakeSplit(), "fr"), "l")
    assert not coverage.finds(BasicDictionary(french, FakeSplit(), "es"), "l")


def test_the_commonest_running_words_open_as_the_treebanks_use_them() -> None:
    """The top-words check asks only whether a word is found: Hindi's लिए,
    the 12th commonest running word, was - on लेना, "to take", though the
    treebanks use it as a postposition (के लिए, "for"). The build lists
    such words (polyglotic-hq 448, 461): here "vengo" opens on venir, a
    verb, but is used as an adposition; "casa" (a noun, used so) and "supe" (too
    few uses) pass."""
    hindi_like = FakeDictionaryFile(
        [
            EntryRecord("wiktes:venir", "venir", "", "", ("(verb) to come",), 270),
            EntryRecord("wiktes:casa", "casa", "", "", ("(noun) house",), 300),
            EntryRecord("wiktes:saber", "saber", "", "", ("(verb) to know",), 160),
        ],
        {"venir": ["wiktes:venir"], "casa": ["wiktes:casa"], "saber": ["wiktes:saber"]},
        lemmas={"vengo": "venir", "supe": "saber"},
    )
    dictionary = BasicDictionary(hindi_like, FakeSplit(), "es")
    freq = {"vengo": 1e-2, "casa": 5e-3, "supe": 1e-3}
    uses = {
        "vengo": {"ADP": 30, "VERB": 2},
        "casa": {"NOUN": 40, "PROPN": 1},
        "supe": {"ADP": 3},
    }
    result = coverage.opened_as_used(dictionary, freq, "es", uses)
    assert result.mismatched == [(1, "vengo", "venir (verb)", "ADP")]
    assert str(result) == "vengo (1): venir (verb), used as ADP"
