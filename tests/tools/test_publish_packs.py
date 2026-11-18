"""The packs' publishing command: a dry run lays out the bucket and signs
the list; an old app is never offered a pack it can't read (decision
0122)."""

import gzip
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from tests.packs_storage import PUBLIC, publish, tiny_pack
from tools.package import publish_packs

from polyglotic_desktop.adapters.pack_list import PackList, split_signed_list
from polyglotic_desktop.adapters.signed_feed import public_keys
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.packs import (
    Reader,
    best_offer,
    list_serial,
    read_pack_list,
)


def served(out: Path) -> PackList:
    """The list as an app would read it from `out`, a stand-in bucket."""
    return PackList(
        "https://stand-in/",
        public_keys([PUBLIC]),
        out / "kept",
        get=lambda url: (out / url.removeprefix("https://stand-in/")).read_bytes(),
    )


def test_a_dry_run_lays_out_the_bucket_and_signs_the_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built) == 0
    offers = served(out).fetch()
    assert {(o.language, o.meanings, o.download) for o in offers} == {
        ("ru", "en", "wiktru-en-2026.11.14.sqlite.gz"),
        ("ru", "zh", "wiktru-zh-2026.11.14.sqlite.gz"),
    }
    assert sorted(p.name for p in (out / "packs" / "files").iterdir()) == [
        "wiktru-en-2026.11.14.sqlite.gz",
        "wiktru-zh-2026.11.14.sqlite.gz",
    ]  # only the downloads go up
    for offer in offers:
        packed = out / "packs" / "files" / offer.download
        assert offer.gz_size == packed.stat().st_size
        assert offer.gz_sha256 == publish_packs.sha256_of(packed)
        unpacked = tmp_path / offer.file
        unpacked.write_bytes(gzip.decompress(packed.read_bytes()))
        assert offer.size == unpacked.stat().st_size
        assert offer.sha256 == publish_packs.sha256_of(unpacked)
        assert offer.credits_text == "# credits" + chr(10)
        file = SqliteDictionary(unpacked)
        assert file.info["pack_version"] == "2026.11.14"
        file.close()
    said = capsys.readouterr().out
    # files first, the list last; nothing uploaded
    assert said.index("packs/files/wiktru-en") < said.index("packs/v1/list.signed  <-")
    assert "list.json" not in said  # one file: the list and its signature
    assert "The list: serial 2," in said  # one more than the one published
    assert ".sqlite.gz  <-" in said
    assert "Dry run: nothing uploaded" in said


def test_vietnamese_goes_up_in_english_only_for_apps_with_its_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vietnamese's pack is written in English only (polyglotic-hq 325),
    and splits by its own words: an app without that split - one from
    before it, which would cut "học sinh" in two - is never offered it."""
    built = tmp_path / "built"
    tiny_pack(built, language="vi", dictionary="wiktvi")
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built, language="vi") == 0
    (offer,) = served(out).fetch()
    assert (offer.language, offer.meanings, offer.download) == (
        "vi",
        "en",
        "wiktvi-en-2026.11.14.sqlite.gz",
    )
    assert offer.split == "vietnamese"
    assert "OpenSubtitles" in offer.credits and "CC BY-SA 4.0" in offer.credits
    with_split = Reader(
        frozenset({offer.format}), frozenset({"spaced", "vietnamese"}), "0.1.5"
    )
    before_it = replace(with_split, splits=frozenset({"spaced"}))
    assert best_offer([offer], "vi", "en", with_split) == offer
    assert best_offer([offer], "vi", "zh", with_split) == offer  # English, not none
    assert best_offer([offer], "vi", "en", before_it) is None


def test_thai_goes_up_in_english_only_for_apps_with_its_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thai's pack is cut by its own words (decision 0173): an app from
    before that split would take a phrase written without spaces for one
    word, so it is never offered the pack (polyglotic-hq 389)."""
    built = tmp_path / "built"
    tiny_pack(built, language="th", dictionary="wiktth")
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built, language="th") == 0
    (offer,) = served(out).fetch()
    assert (offer.language, offer.meanings, offer.split) == ("th", "en", "thai")
    assert "Common Voice" in offer.credits and "CC0" in offer.credits
    with_split = Reader(
        frozenset({offer.format}), frozenset({"spaced", "thai"}), "0.1.7"
    )
    before_it = replace(with_split, splits=frozenset({"spaced", "vietnamese"}))
    assert best_offer([offer], "th", "en", with_split) == offer
    assert best_offer([offer], "th", "en", before_it) is None


def test_without_the_key_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    monkeypatch.delenv(publish_packs.KEY_VARIABLE, raising=False)
    out = tmp_path / "bucket"
    code = publish_packs.main(
        ["ru", "--packs", str(built), "--out", str(out), "--previous", "x"]
    )
    assert code == 1
    assert not out.exists()


def test_a_version_published_with_other_bytes_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    first = tmp_path / "first"
    assert publish(monkeypatch, first, built) == 0
    tiny_pack(built, padding=3)  # rebuilt, different, same version
    again = tmp_path / "again"
    previous = first / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, again, built, previous=previous) == 1


def offers_of(out: Path) -> list[str]:
    data = split_signed_list((out / "packs" / "v1" / "list.signed").read_bytes())[1]
    return sorted(
        f"{o.meanings} {o.version} {o.format}" for o in read_pack_list(data)[0]
    )


def test_a_new_version_replaces_the_old_one_an_old_app_reads_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    first = tmp_path / "first"
    assert publish(monkeypatch, first, built) == 0
    second = tmp_path / "second"
    previous = first / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, second, built, "2026.12.1", previous) == 0
    assert offers_of(second) == ["en 2026.12.1 1", "zh 2026.12.1 1"]


def test_an_old_format_stays_listed_for_the_apps_that_read_only_it() -> None:
    """A pack in a new format: the last version in the old one stays, so an
    old app keeps getting (and updating to) the newest it reads, and is
    never offered the new one."""
    old = publish_packs.PackOffer(
        language="ru",
        meanings="en",
        dictionary="wiktru",
        version="2026.11.14",
        format="1",
        split="spaced",
        min_app="0.1.5",
        file="wiktru-en-2026.11.14.sqlite",
        size=1,
        sha256="a" * 64,
        gz_size=1,
        gz_sha256="b" * 64,
        licence="CC BY-SA 4.0",
        credits="",
    )
    older = replace(old, version="2026.11.1", file="wiktru-en-2026.11.1.sqlite")
    new = replace(old, version="2027.1.1", format="2", file="wiktru-en-2027.1.1.sqlite")
    listed = publish_packs.merged([new], [older, old])
    assert listed == [new, old]
    old_app = Reader(frozenset({"1"}), frozenset({"spaced"}), "0.1.5")
    new_app = Reader(frozenset({"1", "2"}), frozenset({"spaced"}), "0.2.0")
    assert best_offer(listed, "ru", "en", old_app) == old
    assert best_offer(listed, "ru", "en", new_app) == new


def test_a_newer_min_app_keeps_the_last_pack_older_apps_read() -> None:
    old = publish_packs.PackOffer(
        "ru", "en", "wiktru", "2026.11.14", "1", "spaced", "0.1.5",
        "a.sqlite", 1, "a" * 64, 1, "b" * 64, "", "",
    )  # fmt: skip
    new = replace(old, version="2027.1.1", min_app="0.3.0", file="b.sqlite")
    assert publish_packs.merged([new], [old]) == [new, old]


def test_another_languages_packs_stay_as_they_were() -> None:
    spanish = publish_packs.PackOffer(
        "es", "en", "wiktes", "2026.11.1", "1", "spaced", "0.1.5",
        "es.sqlite", 1, "a" * 64, 1, "b" * 64, "", "",
    )  # fmt: skip
    russian = replace(spanish, language="ru", dictionary="wiktru", file="ru.sqlite")
    assert publish_packs.merged([russian], [spanish]) == [russian, spanish]


def test_the_list_is_stable_json() -> None:
    data = publish_packs.list_bytes([], 4)
    assert json.loads(data) == {"list": 1, "serial": 4, "packs": []}
    assert data.endswith(b"\n")


def test_only_a_missing_live_list_starts_a_new_one() -> None:
    """A list the storage can't serve just now isn't "no list": publishing
    over it would drop the packs old apps read."""
    import urllib.error

    def failing(code: int) -> Callable[[str], bytes]:
        def get(url: str) -> bytes:
            raise urllib.error.HTTPError(url, code, "x", None, None)  # type: ignore[arg-type]

        return get

    assert publish_packs.previous_list(None, failing(404)) == ((), 0, (), ())
    with pytest.raises(SystemExit):
        publish_packs.previous_list(None, failing(503))


def test_each_publish_numbers_the_list_one_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    first, second = tmp_path / "first", tmp_path / "second"
    assert publish(monkeypatch, first, built) == 0
    previous = first / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, second, built, "2026.12.1", previous) == 0
    serials = [
        list_serial(split_signed_list((o / "packs/v1/list.signed").read_bytes())[1])
        for o in (first, second)
    ]
    assert serials == [2, 3]


def test_wrangler_never_sees_the_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, "secret")
    monkeypatch.setenv("PATH_FOR_TEST", "kept")
    given = publish_packs.wrangler_environment()
    assert publish_packs.KEY_VARIABLE not in given
    assert given["PATH_FOR_TEST"] == "kept" and given["MSYS_NO_PATHCONV"] == "1"


def test_an_out_folder_not_its_own_is_never_emptied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    elsewhere = tmp_path / "someones-folder"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("mine")
    assert publish(monkeypatch, elsewhere, built) == 1
    assert (elsewhere / "keep.txt").read_text() == "mine"
    ours = tmp_path / "ours"
    assert publish(monkeypatch, ours, built) == 0
    assert publish(monkeypatch, ours, built) == 0  # an earlier run's: emptied, again
