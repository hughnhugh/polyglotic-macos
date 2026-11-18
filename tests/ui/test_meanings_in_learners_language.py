"""An English word's meanings in the learner's own language (polyglotic-hq
510, decision 0234): a Spanish speaker learning English reads Spanish, not
Chinese. The card's meanings come, in order, from ECDICT's meanings file in
the interface's language where it has the word, else in English
(`ecdict-en.sqlite`, decision 0211), else - an older build without it, or a
Chinese interface - in Chinese. The file is a rider of ECDICT's own entry in
the pack list (decision 0197): fetched quietly for an English learner, and
read without a restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.packs_server import StandIn
from tests.packs_storage import PRIVATE, PUBLIC
from tests.test_meanings_riders import meanings_file
from tests.ui.test_check_install import sample_dictionaries
from tests.ui.test_english_in_english import IN_ENGLISH, with_english
from tests.ui.test_pack_delivery import until
from tools.package import publish_packs

from polyglotic_desktop import main
from polyglotic_desktop.adapters.meanings_file import MeaningsShelf
from polyglotic_desktop.core.lexicon.packs import FROM_SOURCE

SPANISH = ("(verb) correr", "(verb) funcionar")
VERSION = "2026.11.18"


def test_the_meanings_wanted_are_the_interfaces_language() -> None:
    wanted = [main.meanings_wanted(i) for i in ("es", "pt_BR", "fil", "ja", "ko")]
    assert wanted == ["es", "pt", "fil", "ja", "ko"]
    # the dictionaries' own: nothing to fetch
    assert [main.meanings_wanted(i) for i in ("en", "zh_CN", "zh_TW")] == [None] * 3


def delivery(
    folder: Path, installer: Path, shelf: MeaningsShelf, base: str, *learned: str
) -> main.PackDelivery:
    packs = main.PackDelivery(
        folder,
        {},
        "en",
        main.pack_reader(FROM_SOURCE),
        base,
        (PUBLIC,),
        built_in=main.BUILT_IN_RIDERS,
        built_in_folder=installer,
        learning=lambda: learned,
        explained=shelf,
        explained_in="es",
    )
    packs.start()
    return packs


def first_meanings(
    dictionaries: Path, data: Path, meanings: str, shelf: MeaningsShelf
) -> tuple[str, ...]:
    tools, store = main.learner_tools(
        dictionaries, True, data, meanings=meanings, explained=shelf
    )
    try:
        return tools.lookup("run")[0].meanings
    finally:
        store.close()


def test_spanish_first_then_english_then_chinese(
    qapp: QApplication, tmp_path: Path
) -> None:
    dictionaries = with_english(tmp_path)
    data, shelf = tmp_path / "data", MeaningsShelf()
    # no Spanish file yet: the English dictionary's English
    packs = delivery(tmp_path / "packs", dictionaries, shelf, "http://127.0.0.1:9/")
    assert first_meanings(dictionaries, data, "en", shelf) == (IN_ENGLISH,)
    packs.close()
    # one beside the app's dictionaries: Spanish, the same entry
    meanings_file(dictionaries, "es", {"ecdict:run": SPANISH}, version=VERSION)
    packs = delivery(tmp_path / "packs", dictionaries, shelf, "http://127.0.0.1:9/")
    assert first_meanings(dictionaries, data, "en", shelf) == SPANISH
    packs.close()
    # a word the file hasn't got keeps the English dictionary's (here: none
    # is in it, so the Chinese one's, as an older build has it)
    older = sample_dictionaries(tmp_path / "older")
    meanings_file(older, "es", {"ecdict:walk": ("caminar",)}, version=VERSION)
    packs = delivery(tmp_path / "packs-older", older, shelf, "http://127.0.0.1:9/")
    assert first_meanings(older, data, "en", shelf) == ("v. 跑",)
    packs.close()


@pytest.fixture
def ecdict_bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """ECDICT's meanings in Spanish, published as its riders."""
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    nothing = tmp_path / "nothing.signed"
    nothing.write_bytes(
        publish_packs.sign_list(
            publish_packs.list_bytes([], 1), publish_packs.private_key_from(PRIVATE)
        )
    )
    folder = tmp_path / "meanings"
    meanings_file(folder, "es", {"ecdict:run": SPANISH})
    out = tmp_path / "bucket"
    assert (
        publish_packs.main(
            [
                *("--built-in", "ecdict", "--meanings", str(folder)),
                *("--version", VERSION, "--out", str(out)),
                *("--previous", str(nothing)),
            ]
        )
        == 0
    )
    return out


def test_a_meanings_file_downloaded_reaches_english_lookups_at_once(
    qapp: QApplication, tmp_path: Path, ecdict_bucket: Path
) -> None:
    dictionaries = with_english(tmp_path)
    data, shelf = tmp_path / "data", MeaningsShelf()
    tools, store = main.learner_tools(
        dictionaries, True, data, meanings="en", explained=shelf
    )
    try:
        with StandIn(ecdict_bucket) as stand_in:
            packs = delivery(tmp_path / "none", dictionaries, shelf, stand_in.base)
            packs.check_updates()  # English isn't learned: nothing comes
            packs.close()
            assert not any(".meanings" in p for p, _, _ in stand_in.requests)
            assert tools.lookup("run")[0].meanings == (IN_ENGLISH,)

            folder = tmp_path / "packs"
            packs = delivery(folder, dictionaries, shelf, stand_in.base, "en")
            packs.check_updates()
            until(lambda: tools.lookup("run")[0].meanings == SPANISH)
            assert [p.name for p in folder.glob("ecdict-*")] == [
                f"ecdict-es-{VERSION}.meanings"
            ]
            assert packs.installed_lines() == []  # not a pack: nothing to remove
            packs.close()
    finally:
        store.close()
