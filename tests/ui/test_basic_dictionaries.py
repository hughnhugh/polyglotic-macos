"""The basic dictionaries (decisions 0035, 0122): `main` opens the packs
it finds, and the learning tools look a row's words up in its language's
pack - the learner's dictionary otherwise."""

import threading
from collections.abc import Sequence
from pathlib import Path

from pytest import MonkeyPatch
from tests.lexicon.test_basic import SPANISH, FakeSplit
from tests.tools.test_packs import sources
from tests.ui.fakes import chinese_tools
from tools.dictionaries import packs

from polyglotic_desktop import main
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.packs import FROM_SOURCE
from polyglotic_desktop.ports.word_split import SplitWord
from polyglotic_desktop.ui.learning import LearningTools

OPENED: list[main.PackDelivery] = []


def opened(folder: Path, meanings: str) -> dict[str, BasicDictionary]:
    """The packs `main` opens for lookups at the start, from `folder`."""
    basic: dict[str, BasicDictionary] = {}
    reader = main.pack_reader(FROM_SOURCE)
    packs = main.PackDelivery(folder, basic, meanings, reader, "http://127.0.0.1:9/")
    packs.start()
    OPENED.append(packs)
    return basic


def close_opened() -> None:
    while OPENED:
        OPENED.pop().close()


def test_main_opens_each_basic_pack_by_its_language(
    tmp_path: Path, monkeypatch: MonkeyPatch, qapp: object
) -> None:
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    paths = sources(tmp_path / "upstream")
    out = tmp_path / "packs"
    out.mkdir()
    for pack in packs.PACKS.values():
        packs.build(pack, paths, out)
    english = opened(out, "en")
    assert sorted(english) == sorted(packs.PACKS)
    assert {"de", "pt", "it", "id", "ar", "hi", "pl"} <= set(english)  # 380
    # French cuts an elided word from the one after it (decision 0133)
    assert english["fr"].words("L'homme") == [(0, 2), (2, 7)]
    assert [e.headword for e in english["fr"].lookup("hommes")] == ["homme"]
    # "casa" is also casar's "he marries" since the Spanish forms (#255)
    assert [e.meanings[0] for e in english["es"].lookup("casa")] == [
        "(noun) house",
        "(verb) to marry",
    ]
    assert [e.headword for e in english["ja"].lookup("食べ")] == ["食べる"]
    # Russian's word split is simplemma's, as Spanish's (polyglotic-hq 298)
    assert [e.headword for e in english["ru"].lookup("Руку")] == ["рука"]
    # Vietnamese's by its pack's own words: "học sinh" is one (325)
    assert english["vi"].words("Học sinh đi") == [(0, 8), (9, 11)]
    # Thai's too, in a line without spaces (polyglotic-hq 389)
    assert english["th"].words("หมาจะกินดี") == [(0, 3), (3, 5), (5, 8), (8, 10)]
    chinese = opened(out, "zh")
    assert next(e.meanings[0] for e in chinese["es"].lookup("casa")) == "房子"
    # Vietnamese has English meanings only: English, not nothing
    assert chinese["vi"].lookup("học sinh")[0].meanings == ("(noun) pupil, student",)
    assert opened(tmp_path / "none", "en") == {}
    # a cut-off pack is left out, not a reason the app can't start
    close_opened()
    whole = (out / "wiktes.sqlite").read_bytes()
    (out / "wiktes.sqlite").write_bytes(whole[:4096])
    (out / "wiktes-zh.sqlite").unlink()
    assert sorted(opened(out, "en")) == sorted(set(packs.PACKS) - {"es"})
    close_opened()


def test_every_app_reads_vietnamese_packs_with_no_library_added() -> None:
    """Vietnamese's split is plain Python over the pack's own words
    (decision 0121), so an installed app - no simplemma, no Sudachi
    (decision 0123) - is offered Vietnamese's pack (polyglotic-hq 325)."""
    reader = main.pack_reader("0.1.5")
    assert {"spaced", "vietnamese"} <= reader.splits


def test_this_app_reads_thai_packs_with_no_library_added() -> None:
    """Thai's split is plain Python over the pack's own words, as
    Vietnamese's (decision 0173): every app from this one has it, and the
    list names it for Thai's pack (polyglotic-hq 389)."""
    from tools.package.publish_packs import SPLITS

    assert "thai" in main.pack_reader("0.1.5").splits
    assert SPLITS["th"] == "thai"


def test_this_app_reads_the_packs_whose_splits_keep_marks_and_clitics() -> None:
    """Hindi's pack needs the split that keeps a word's vowel signs, and
    Arabic's and Indonesian's the one that guesses their clitics off: an
    app with them says so, and the list names them (polyglotic-hq 380)."""
    from tools.package.publish_packs import SPLITS

    reader = main.pack_reader("0.1.6")
    assert {"marks", "clitics", "elided"} <= reader.splits
    assert [SPLITS[c] for c in ("hi", "ar", "id", "it")] == [
        "marks",
        "clitics",
        "clitics",
        "elided",
    ]


def test_this_app_reads_the_packs_whose_split_guesses_turkish_suffixes() -> None:
    """Turkish's pack needs its suffixes guessed off: an app from before
    would find a fifth of its words in no dictionary, so the pack names a
    split of its own (polyglotic-hq 388)."""
    from tools.package.publish_packs import SPLITS

    assert "turkish" in main.pack_reader("0.1.6").splits
    assert SPLITS["tr"] == "turkish"
    assert SPLITS["ms"] == "clitics"  # Malay's affixes are Indonesian's


def test_this_app_reads_the_packs_whose_splits_keep_joiners_and_guess_affixes() -> None:
    """Persian's pack needs the split that keeps a word whole at its
    zero-width non-joiner; Filipino's, Czech's and Greek's the one that
    guesses their affixes - each was under the floor without (polyglotic-hq
    387). Dutch, Swedish, Ukrainian, Romanian and Macedonian read as an
    app from 0.1.5 reads them."""
    from tools.package.publish_packs import SPLITS

    reader = main.pack_reader("0.1.6")
    assert {"joiners", "affixes"} <= reader.splits
    assert [SPLITS[c] for c in ("fa", "tl", "cs", "el")] == [
        "joiners",
        "affixes",
        "affixes",
        "affixes",
    ]
    assert not {"nl", "sv", "uk", "ro", "mk"} & set(SPLITS)


def test_the_switch_is_off_by_default_and_takes_a_meanings_language() -> None:
    assert main.arguments([]).basic_dictionaries is None
    assert main.arguments(["--basic-dictionaries"]).basic_dictionaries == "en"
    assert main.arguments(["--basic-dictionaries", "zh"]).basic_dictionaries == "zh"


def test_meanings_follow_the_interface_unless_the_switch_says() -> None:
    assert main.pack_meanings("zh_CN") == "zh" and main.pack_meanings("zh_TW") == "zh"
    assert main.pack_meanings("de") == "en" and main.pack_meanings("en") == "en"


def test_a_rows_language_picks_its_basic_dictionary() -> None:
    chinese = chinese_tools()
    tools = LearningTools(
        chinese.vocabulary,
        chinese.dictionary,
        basic={"es": BasicDictionary(SPANISH, FakeSplit(), "es")},
    )
    assert (
        tools.is_basic("es") and not tools.is_basic("zh") and not tools.is_basic(None)
    )
    assert [e.headword for e in tools.lookup("supe", "es")] == ["saber"]
    assert tools.lookup("supe") == []  # the Chinese learner's dictionary
    assert tools.word_at("no lo supe", 7, "es") == (6, 10)
    assert tools.lookup("电脑", "zh") == tools.lookup("电脑")  # no pack: as before


class SlowSplit:
    """A word split whose first use loads its data, noting the thread."""

    def __init__(self) -> None:
        self.loaded_on: str | None = None
        self.loaded = threading.Event()

    def words(self, text: str) -> Sequence[SplitWord]:
        if self.loaded_on is None:
            self.loaded_on = threading.current_thread().name
            self.loaded.set()
        return FakeSplit().words(text)


def test_a_basic_dictionarys_word_split_loads_off_the_interface_thread() -> None:
    chinese = chinese_tools()
    split = SlowSplit()
    tools = LearningTools(
        chinese.vocabulary,
        chinese.dictionary,
        basic={"es": BasicDictionary(SPANISH, split, "es")},
    )
    tools.prepare()
    assert split.loaded.wait(5)
    assert split.loaded_on == "basic dictionaries"


def test_an_installed_copys_packs_are_kept_with_its_data_not_the_app(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """An update replaces the install folder whole, and the Store's can't
    be written: packs there would be gone after the next update (decision
    0089, polyglotic-hq 298)."""
    install = tmp_path / "Local" / "Polyglotic" / "current"
    data = tmp_path / "Roaming" / "Polyglotic"
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "executable", str(install / "Polyglotic.exe"))
    folder = main.packs_folder(main.dictionaries_folder(), data)
    assert folder == data / "dictionaries"
    assert not folder.is_relative_to(install)
    monkeypatch.setattr(main.sys, "frozen", False)
    # from source: where tools.dictionaries.packs writes them
    built = Path("build/dictionaries")
    assert main.packs_folder(built, data) == built / "packs"
