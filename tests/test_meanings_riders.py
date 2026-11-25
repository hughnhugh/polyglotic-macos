"""A dictionary's meanings in the learner's language (decision 0234): its
meanings files, one language each, published as riders (decision 0133) -
for a pack, or for a dictionary built into the app such as ECDICT
(decision 0197) - fetched only in the learner's language, and read through
a shelf every dictionary sees."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from tests import test_pack_riders
from tests.packs_server import StandIn
from tests.packs_storage import PRIVATE
from tests.test_pack_riders import (
    LIST,
    READER,
    Seen,
    built_in_of,
    deliveries,
    finish,
    offers_in,
)
from tools.package import publish_packs

from polyglotic_desktop.adapters.meanings_file import (
    ConvertedMeanings,
    MeaningsShelf,
    SqliteMeanings,
    meanings_beside,
    write_meanings,
)
from polyglotic_desktop.adapters.pack_downloads import PackDeliveries
from polyglotic_desktop.core.lexicon.packs import (
    Reader,
    Rider,
    read_built_in,
    read_fonts,
    riders_wanted,
)
from polyglotic_desktop.core.lexicon.traditional import TraditionalChinese

bucket = test_pack_riders.bucket  # the packs published, with their recordings
VERSION = "2026.11.18"
MEANINGS = Reader(
    frozenset({"1"}),
    frozenset({"spaced"}),
    "0.1.9",
    frozenset({("audio", "1"), ("meanings", "1")}),
)


def meanings_file(
    folder: Path,
    language: str,
    rows: dict[str, tuple[str, ...]],
    dictionary: str = "ecdict",
    version: str = "",
    machine: frozenset[str] = frozenset(),
    source_language: str = "en",
) -> Path:
    """`dictionary`'s meanings in `language`, as `tools.dictionaries.english_pairs`
    names its file (a published one has its `version` in its name)."""
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{dictionary}-{language}{'-' + version if version else ''}.meanings"
    write_meanings(
        folder / name,
        {
            "dictionary": dictionary,
            "language": source_language,
            "meanings_language": language,
            **({"version": version} if version else {}),
        },
        [(i, senses, i in machine) for i, senses in rows.items()],
    )
    return folder / name


# -- the file -----------------------------------------------------------------


def test_a_meanings_file_reads_back_and_hides_an_unapproved_machines_rows(
    tmp_path: Path,
) -> None:
    """People's meanings are shown; a row a machine made isn't, until the
    card can say so (DECISIONS #110) - the dictionary's own are."""
    path = meanings_file(
        tmp_path,
        "es",
        {"ecdict:bank": ("(noun) banco", "(noun) orilla"), "ecdict:go": ("(verb) ir",)},
        machine=frozenset({"ecdict:go"}),
    )
    file = SqliteMeanings(path)
    assert file.meanings("ecdict:bank") == ("(noun) banco", "(noun) orilla")
    assert file.meanings("ecdict:go") is None and file.meanings("ecdict:no") is None
    assert (file.info["entries"], file.info["machine_made"]) == ("2", "1")
    file.close()
    assert file.meanings("ecdict:bank") is None  # closed: the dictionary's own
    with pytest.raises(ValueError, match="line break"):
        write_meanings(tmp_path / "x.meanings", {}, [("ecdict:a", ("a\nb",), False)])


def test_only_approved_japanese_chinese_machine_meanings_are_exposed(
    tmp_path: Path,
) -> None:
    simplified = SqliteMeanings(
        meanings_file(
            tmp_path / "simplified",
            "zh",
            {"jmdict:1": ("吃",)},
            dictionary="jmdict",
            machine=frozenset({"jmdict:1"}),
            source_language="ja",
        )
    )
    unapproved = SqliteMeanings(
        meanings_file(
            tmp_path / "unapproved",
            "zh",
            {"wiktfr:1": ("吃",)},
            dictionary="wiktfr",
            machine=frozenset({"wiktfr:1"}),
        )
    )
    assert simplified.meanings("jmdict:1") == ("\x1emachine-made\x1f吃",)
    assert unapproved.meanings("wiktfr:1") is None


def test_a_missing_chinese_rider_can_be_read_in_the_other_script(
    tmp_path: Path,
) -> None:
    source = SqliteMeanings(
        meanings_file(
            tmp_path,
            "zh",
            {"jmdict:1": ("学习",)},
            dictionary="jmdict",
            machine=frozenset({"jmdict:1"}),
            source_language="ja",
        )
    )
    fallback = ConvertedMeanings(source, TraditionalChinese({"学习": "學習"}).convert)
    assert fallback.meanings("jmdict:1") == ("\x1emachine-made\x1f學習",)
    fallback.close()


def test_the_newest_file_in_the_learners_language_is_the_one_opened(
    tmp_path: Path,
) -> None:
    packs, installer = tmp_path / "packs", tmp_path / "installer"
    meanings_file(installer, "es", {"ecdict:a": ("viejo",)}, version="2026.11.1")
    meanings_file(packs, "es", {"ecdict:a": ("nuevo",)}, version="2026.11.18")
    meanings_file(packs, "fil", {"ecdict:a": ("bago",)}, version="2026.12.1")
    meanings_file(packs, "es", {"ecdict:a": ("otro",)}, "wiktfr", "2026.12.1")
    (packs / "ecdict-es-2026.12.9.meanings").write_bytes(b"not a meanings file")
    found = meanings_beside([packs, installer], "ecdict", "es")
    assert found is not None and found.meanings("ecdict:a") == ("nuevo",)
    found.close()
    assert meanings_beside([packs], "ecdict", "fi") is None  # not Filipino's
    assert meanings_beside([tmp_path / "none"], "ecdict", "es") is None


def test_the_shelf_hands_every_dictionary_the_file_on_it_now(tmp_path: Path) -> None:
    old = SqliteMeanings(meanings_file(tmp_path / "a", "es", {"ecdict:a": ("uno",)}))
    new = SqliteMeanings(meanings_file(tmp_path / "b", "es", {"ecdict:a": ("dos",)}))
    shelf = MeaningsShelf()
    view = shelf.view("ecdict")
    assert view.meanings("ecdict:a") is None
    assert shelf.put("ecdict", old) is None
    assert view.meanings("ecdict:a") == ("uno",)
    assert shelf.put("ecdict", new) is old  # for the caller to close, later
    assert view.meanings("ecdict:a") == ("dos",)
    assert shelf.view("cedict").meanings("ecdict:a") is None
    old.close()
    shelf.close()
    assert view.meanings("ecdict:a") is None


# -- the list ------------------------------------------------------------------


def published_meanings(
    monkeypatch: pytest.MonkeyPatch, out: Path, folder: Path, previous: Path
) -> int:
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    return publish_packs.main(
        [
            *("--built-in", "ecdict", "--meanings", str(folder)),
            *("--version", VERSION, "--out", str(out), "--previous", str(previous)),
        ]
    )


@pytest.fixture
def ecdict_bucket(
    bucket: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The packs published, then ECDICT's meanings in Spanish and Japanese."""
    folder = tmp_path / "meanings"
    meanings_file(folder, "es", {"ecdict:bank": ("(noun) banco",)})
    meanings_file(folder, "ja", {"ecdict:bank": ("(noun) 銀行",)})
    out = tmp_path / "bucket-ecdict"
    assert published_meanings(monkeypatch, out, folder, bucket / LIST) == 0
    shutil.copytree(
        bucket / "packs" / "files", out / "packs" / "files", dirs_exist_ok=True
    )
    return out


def test_english_meanings_go_up_as_ecdicts_own_riders_one_per_language(
    bucket: Path, ecdict_bucket: Path
) -> None:
    (entry,) = built_in_of(ecdict_bucket)
    assert (entry.dictionary, entry.language) == ("ecdict", "en")
    assert [(r.kind, r.meanings, r.file, r.min_app) for r in entry.riders] == [
        ("meanings", "es", f"ecdict-es-{VERSION}.meanings", "0.1.9"),
        ("meanings", "ja", f"ecdict-ja-{VERSION}.meanings", "0.1.9"),
    ]
    for rider in entry.riders:
        packed = ecdict_bucket / "packs" / "files" / rider.download
        assert packed.stat().st_size == rider.gz_size
    assert offers_in(ecdict_bucket) == offers_in(bucket)  # the packs as they were
    _, data = publish_packs.split_signed_list((bucket / LIST).read_bytes())
    for pack in json.loads(data)["packs"]:  # an audio rider says no language
        assert all("meanings" not in r for r in pack["riders"])


def test_a_meanings_rider_the_list_gets_wrong_is_left_out() -> None:
    good = {
        "kind": "meanings",
        "meanings": "es",
        "format": "1",
        "min_app": "0.1.9",
        "file": "ecdict-es-2026.11.18.meanings",
        "size": 10,
        "sha256": "a" * 64,
        "gz_size": 9,
        "gz_sha256": "b" * 64,
    }
    riders = [
        good,
        {k: v for k, v in good.items() if k != "meanings"},  # no language
        {**good, "meanings": "Spanish"},
        {**good, "meanings": "ja"},  # not its file's language
        {**good, "file": "ecdict-es-2026.11.18.audio"},
    ]
    whole = {
        "list": 1,
        "serial": 5,
        "packs": [],
        "built_in": [{"dictionary": "ecdict", "language": "en", "riders": riders}],
    }
    (entry,) = read_built_in(json.dumps(whole).encode())
    assert [(r.meanings, r.file) for r in entry.riders] == [("es", good["file"])]


def test_only_the_learners_language_is_wanted_and_only_by_an_app_that_reads_it(
    ecdict_bucket: Path,
) -> None:
    (entry,) = built_in_of(ecdict_bucket)

    def wanted(reader: Reader, language: str | None) -> list[str]:
        return [r.meanings for r in riders_wanted(entry, reader, language)]

    assert wanted(MEANINGS, "es") == ["es"]
    assert wanted(MEANINGS, "ja") == ["ja"]
    assert wanted(MEANINGS, "vi") == [] and wanted(MEANINGS, None) == []
    assert wanted(READER, "es") == []  # 0.1.8: recordings only
    older = Reader(MEANINGS.formats, MEANINGS.splits, "0.1.8", MEANINGS.riders)
    assert wanted(older, "es") == []  # reads them, but the list says from 0.1.9


def test_a_packs_meanings_in_its_own_language_are_never_fetched(
    bucket: Path,
) -> None:
    """A pack published with Chinese meanings needs no Chinese meanings file."""
    (offer,) = (o for o in offers_in(bucket) if o.meanings == "zh")
    rider = Rider(
        kind="meanings",
        format="1",
        min_app="0.1.9",
        file=f"wiktru-zh-{VERSION}.meanings",
        size=10,
        sha256="a" * 64,
        gz_size=9,
        gz_sha256="b" * 64,
        meanings="zh",
    )
    assert riders_wanted(replace(offer, riders=(rider,)), MEANINGS, "zh") == []
    english = replace(offer, meanings="en", riders=(rider,))
    assert riders_wanted(english, MEANINGS, "zh") == [rider]


# -- the download --------------------------------------------------------------


def learner(
    server: StandIn, folder: Path, seen: Seen, language: str | None
) -> PackDeliveries:
    got = deliveries(server, folder, seen, reader=MEANINGS)
    got.explained_in = language
    return got


def test_ecdicts_meanings_in_the_learners_language_come_quietly(
    ecdict_bucket: Path, tmp_path: Path
) -> None:
    with StandIn(ecdict_bucket) as server:
        seen = Seen()
        got = learner(server, tmp_path, seen, "es")
        got.want("en", "", built_in="ecdict")
        finish(got)
        assert seen.installed == []  # no pack
        assert [p.name for _, p in seen.riders] == [f"ecdict-es-{VERSION}.meanings"]
        found = meanings_beside([tmp_path / "packs"], "ecdict", "es")
        assert found is not None and found.meanings("ecdict:bank") == ("(noun) banco",)
        found.close()
        # an English interface takes none
        none = Seen()
        got = learner(server, tmp_path / "english", none, None)
        got.want("en", "", built_in="ecdict")
        finish(got)
        assert none.riders == []
        assert not list((tmp_path / "english").rglob("*.meanings"))


def test_caption_faces_and_ecdicts_meanings_go_on_one_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A publish with both kinds keeps both: the faces in `fonts` (decision
    0223), ECDICT's meanings in its `built_in` entry (decision 0234)."""
    from tests.test_font_packs import built_faces, publish

    faces = built_faces(tmp_path / "faces")
    with_faces = tmp_path / "with-faces"
    assert publish(monkeypatch, with_faces, faces) == 0
    folder = tmp_path / "meanings"
    meanings_file(folder, "es", {"ecdict:bank": ("(noun) banco",)})
    both = tmp_path / "both"
    assert published_meanings(monkeypatch, both, folder, with_faces / LIST) == 0
    _, data = publish_packs.split_signed_list((both / LIST).read_bytes())
    _, before = publish_packs.split_signed_list((with_faces / LIST).read_bytes())
    assert read_fonts(data) == read_fonts(before) and read_fonts(data)
    (entry,) = read_built_in(data)
    assert [r.file for r in entry.riders] == [f"ecdict-es-{VERSION}.meanings"]
