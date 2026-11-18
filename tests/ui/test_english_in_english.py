"""An English word's meanings are in English unless the app is in Chinese
(the user, 2026-11-17: "implement english dictionary in english? only
display the chinese if the app main language is set to chinese";
polyglotic-hq 447, decision 0211). The English learner's dictionary is
`ecdict-en.sqlite` - ECDICT's entries and IDs with English meanings - for
every interface but Chinese, which keeps `ecdict.sqlite`'s Chinese."""

from pathlib import Path

from tests.ui.test_check_install import sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.ports.dictionary import EntryRecord

IN_ENGLISH = "(verb) move fast on foot"


def with_english(tmp_path: Path) -> Path:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    run = EntryRecord("ecdict:run", "run", "", "rʌn", (IN_ENGLISH,), 202)
    write_dictionary(
        folder / main.ENGLISH_IN_ENGLISH,
        {"dictionary": "ecdict", "meanings": "en"},
        [run],
        {"run": ["ecdict:run"]},
    )
    return folder


def meaning(folder: Path, data: Path, meanings: str) -> tuple[str, str]:
    tools, store = main.learner_tools(folder, True, data, meanings=meanings)
    try:
        found = tools.lookup("run")[0]
        return found.entry_id, found.meanings[0]
    finally:
        store.close()


def test_an_english_word_is_explained_in_english_unless_the_app_is_in_chinese(
    tmp_path: Path,
) -> None:
    folder = with_english(tmp_path)
    data = tmp_path / "data"
    assert meaning(folder, data, "en") == ("ecdict:run", IN_ENGLISH)
    # the same entry: what the learner saved is the same word either way
    assert meaning(folder, data, "zh") == ("ecdict:run", "v. 跑")


def test_the_meanings_language_is_the_interfaces() -> None:
    """Every interface but Chinese (Simplified or Traditional) reads English."""
    assert [main.pack_meanings(i) for i in ("en", "vi", "es", "ja")] == ["en"] * 4
    assert [main.pack_meanings(i) for i in ("zh_CN", "zh_TW")] == ["zh", "zh"]


def test_without_the_english_file_the_chinese_meanings_stay(tmp_path: Path) -> None:
    """An older build's dictionaries: the learner still has a dictionary."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    assert meaning(folder, tmp_path / "data", "en") == ("ecdict:run", "v. 跑")


def test_a_chinese_learners_dictionary_is_cc_cedict_whatever_the_interface(
    tmp_path: Path,
) -> None:
    folder = with_english(tmp_path)
    for meanings in ("en", "zh"):
        path = main.learner_dictionary_file(folder, False, meanings)
        assert path == folder / "cedict.sqlite"
    assert main.learner_dictionary_file(folder, True, "en") == folder / (
        main.ENGLISH_IN_ENGLISH
    )


def test_english_beside_chinese_is_in_the_interfaces_language(tmp_path: Path) -> None:
    """A Chinese learner who also learns English opens English's dictionary
    beside (`tools_beside`) in the interface's meanings language too."""
    from polyglotic_desktop.core.learning.languages import LearningLanguages

    folder = with_english(tmp_path)
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data, meanings="en")
    beside = main.tools_beside(
        tools, folder, data, LearningLanguages("zh", ("en",)), meanings="en"
    )
    try:
        (english, _), *_ = beside
        assert english.lookup("run")[0].meanings[0] == IN_ENGLISH
    finally:
        for _, other in beside:
            other.close()
        store.close()
