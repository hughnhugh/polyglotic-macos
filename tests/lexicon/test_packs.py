"""The packs' list as the app reads it: which pack it gets, which it can't
read, and when the one on this PC is older (decision 0122)."""

import json
from dataclasses import asdict, replace

import pytest

from polyglotic_desktop.core.lexicon.packs import (
    FROM_SOURCE,
    InstalledPack,
    PackListError,
    PackOffer,
    Reader,
    Rider,
    best_offer,
    list_serial,
    needs_newer_app,
    newer,
    read_pack_list,
    riders_wanted,
    update_for,
    version_key,
)

RUSSIAN = PackOffer(
    language="ru",
    meanings="en",
    dictionary="wiktru",
    version="2026.11.14",
    format="1",
    split="spaced",
    min_app="0.1.5",
    file="wiktru-en-2026.11.14.sqlite",
    size=62_400_000,
    sha256="a" * 64,
    gz_size=13_300_000,
    gz_sha256="c" * 64,
    licence="CC BY-SA 4.0",
    credits="Wiktionary's contributors (via kaikki.org), wordfreq",
    credits_text="# Russian dictionary pack - credits\n",
)
READER = Reader(frozenset({"1"}), frozenset({"spaced"}), "0.1.5")


def listed(*offers: PackOffer, **whole: object) -> bytes:
    return json.dumps(
        {"list": 1, "serial": 3, "packs": [asdict(o) for o in offers], **whole}
    ).encode()


def test_a_list_reads_back_as_its_offers() -> None:
    zh = replace(RUSSIAN, meanings="zh", file="wiktru-zh-2026.11.14.sqlite")
    assert read_pack_list(listed(RUSSIAN, zh)) == ((RUSSIAN, zh), 0)


@pytest.mark.parametrize(
    "change",
    [
        {"file": "../dictionaries/x.sqlite"},
        {"file": "packs/x.sqlite"},
        {"file": "nul.sqlite"},
        {"file": "COM1.sqlite"},
        {"file": "lpt9"},
        {"file": "wiktru-en-2026.11.14.sqlite."},
        {"file": "wiktru-en-2026.11.14.exe"},
        {"file": "wiktru-en-2026.11.14.sqlite.lnk"},
        {"file": "other-en-2026.11.14.sqlite"},
        {"dictionary": "con", "file": "con-en-1.sqlite"},
        {"dictionary": "Wikt.ru"},
        {"sha256": "A" * 64},
        {"sha256": "a" * 63},
        {"gz_sha256": ""},
        {"gz_size": -1},
        {"size": 0},
        {"size": True},
        {"size": "62400000"},
        {"version": "latest"},
        {"min_app": "0.1"[:0]},
        {"language": "Russian"},
        {"meanings": None},
    ],
)
def test_a_malformed_entry_is_left_out_and_counted(change: dict[str, object]) -> None:
    bad = {**asdict(RUSSIAN), **change}
    data = json.dumps(
        {"list": 1, "serial": 3, "packs": [bad, asdict(RUSSIAN)]}
    ).encode()
    assert read_pack_list(data) == ((RUSSIAN,), 1)


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        b"[]",
        b'{"list": 1}',
        listed(RUSSIAN, list=2),
        b"\xff\xfe",
        listed(RUSSIAN, serial=0),
        listed(RUSSIAN, serial="4"),
        json.dumps({"list": 1, "packs": []}).encode(),  # no serial
    ],
)
def test_what_isnt_a_list_of_this_format_is_refused_whole(data: bytes) -> None:
    with pytest.raises(PackListError):
        read_pack_list(data)


def test_versions_compare_as_numbers() -> None:
    assert version_key("2026.11.14") == (2026, 11, 14)
    assert newer("2026.11.14.2", "2026.11.14")
    assert newer("2026.12.1", "2026.11.30")
    assert not newer("2026.11.14", "2026.11.14")
    assert not newer("soon", "2026.11.14")


def test_the_newest_pack_this_app_reads_is_the_one_offered() -> None:
    older = replace(RUSSIAN, version="2026.11.1", file="old.sqlite")
    assert best_offer((older, RUSSIAN), "ru", "en", READER) == RUSSIAN


def test_an_old_app_is_never_offered_a_pack_it_cant_read() -> None:
    """A new format and a pack needing a newer app stay listed beside the
    old one: the old app takes the old one, and never the others."""
    new_format = replace(RUSSIAN, version="2027.1.1", format="2", file="f2.sqlite")
    needs_newer = replace(RUSSIAN, version="2027.2.1", min_app="0.2.0", file="n.sqlite")
    offers = (RUSSIAN, new_format, needs_newer)
    assert best_offer(offers, "ru", "en", READER) == RUSSIAN
    newer_app = Reader(frozenset({"1", "2"}), frozenset({"spaced"}), "0.2.0")
    assert best_offer(offers, "ru", "en", newer_app) == needs_newer


def test_a_pack_whose_word_split_this_app_hasnt_got_isnt_offered() -> None:
    japanese = replace(RUSSIAN, language="ja", split="japanese", file="jm.sqlite")
    assert best_offer((japanese,), "ja", "en", READER) is None
    assert not needs_newer_app((japanese,), "ja", "en", READER)


def test_only_unreadable_packs_says_a_newer_app_reads_them() -> None:
    new_format = replace(RUSSIAN, format="2")
    assert not needs_newer_app((new_format,), "ru", "en", READER)
    assert not needs_newer_app((RUSSIAN,), "ru", "en", READER)
    assert not needs_newer_app((), "ru", "en", READER)  # simply not there yet


def test_from_source_any_app_version_reads_it() -> None:
    needs_newer = replace(RUSSIAN, min_app="9.0.0")
    source = Reader(frozenset({"1"}), frozenset({"spaced"}), FROM_SOURCE)
    assert best_offer((needs_newer,), "ru", "en", source) == needs_newer
    assert best_offer((needs_newer,), "ru", "en", READER) is None


def test_meanings_fall_back_to_english() -> None:
    assert best_offer((RUSSIAN,), "ru", "zh", READER) == RUSSIAN
    zh = replace(RUSSIAN, meanings="zh", file="zh.sqlite")
    assert best_offer((RUSSIAN, zh), "ru", "zh", READER) == zh


def installed(version: str, meanings: str = "en") -> InstalledPack:
    return InstalledPack("ru", meanings, "wiktru", version, "x.sqlite", 1)


def test_an_older_pack_on_this_pc_has_an_update() -> None:
    assert update_for(installed("2026.11.1"), (RUSSIAN,), READER) == RUSSIAN
    assert update_for(installed("2026.11.14"), (RUSSIAN,), READER) is None
    assert update_for(installed("2026.12.1"), (RUSSIAN,), READER) is None


def test_an_app_too_old_for_the_next_format_keeps_its_pack() -> None:
    new_format = replace(RUSSIAN, version="2027.1.1", format="2")
    assert update_for(installed("2026.11.14"), (RUSSIAN, new_format), READER) is None


def test_an_update_keeps_the_meanings_language_it_has() -> None:
    """Chinese meanings installed, and the list has only English ones newer:
    not an update (English would replace Chinese)."""
    assert update_for(installed("2026.1.1", "zh"), (RUSSIAN,), READER) is None


def test_a_pack_downloads_gzipped() -> None:
    assert RUSSIAN.download == "wiktru-en-2026.11.14.sqlite.gz"


def test_a_lists_serial_is_read() -> None:
    assert list_serial(listed(RUSSIAN)) == 3


def test_japanese_chinese_pack_offers_drafts_to_both_chinese_locales() -> None:
    old = replace(
        RUSSIAN,
        language="ja",
        dictionary="jmdict",
        meanings="zh",
        file="jmdict-zh-2026.11.14.sqlite",
        split="japanese",
    )
    version = "2026.11.25"
    successor = replace(
        old,
        version=version,
        min_app="0.1.12",
        file=f"jmdict-zh-{version}.sqlite",
        riders=tuple(
            Rider(
                "meanings",
                "1",
                "0.1.12",
                f"jmdict-{locale}-{version}.meanings",
                10,
                "a" * 64,
                9,
                "b" * 64,
                locale,
            )
            for locale in ("zh", "zh_TW")
        ),
    )
    offers, skipped = read_pack_list(listed(old, successor))
    assert skipped == 0 and offers == (old, successor)
    reader = replace(
        READER,
        app_version="0.1.12",
        splits=frozenset({"japanese"}),
        riders=frozenset({("meanings", "1")}),
    )
    assert best_offer(offers, "ja", "zh", reader) == successor
    assert best_offer(offers, "ja", "zh", replace(reader, app_version="0.1.11")) == old
    for locale, rider in zip(("zh", "zh_TW"), successor.riders, strict=True):
        assert riders_wanted(successor, reader, locale) == [rider]
    assert riders_wanted(successor, replace(reader, app_version="0.1.11"), "zh") == []
    assert riders_wanted(successor, reader, "es") == []
    same_language = replace(
        RUSSIAN,
        meanings="zh",
        riders=(replace(successor.riders[0], file=f"wiktru-zh-{version}.meanings"),),
    )
    assert riders_wanted(same_language, reader, "zh") == []
