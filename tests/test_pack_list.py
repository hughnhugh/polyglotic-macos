"""The packs' list is trusted only as we signed it, with the update feed's
keys and a prefix of its own, in one file with its signature, never older
than the one kept, and only from `https://` (decision 0122)."""

import base64
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from polyglotic_desktop.adapters.pack_list import (
    PackList,
    PackListNotTrusted,
    signed_list_file,
    signed_list_message,
    storage_address,
)
from polyglotic_desktop.adapters.signed_feed import signed_message
from polyglotic_desktop.core.lexicon.packs import PackOffer

KEY = SigningKey(b"\x07" * 32)
OTHER = SigningKey(b"\x08" * 32)
BASE = "https://updates.example/"
ADDRESS = BASE + "packs/v1/list.signed"
OFFER = PackOffer(
    language="ru",
    meanings="en",
    dictionary="wiktru",
    version="2026.11.14",
    format="1",
    split="spaced",
    min_app="0.1.5",
    file="wiktru-en-2026.11.14.sqlite",
    size=10,
    sha256="b" * 64,
    gz_size=8,
    gz_sha256="d" * 64,
    licence="CC BY-SA 4.0",
    credits="Wiktionary's contributors",
)


def listed(serial: int = 5, offer: PackOffer = OFFER) -> bytes:
    return json.dumps({"list": 1, "serial": serial, "packs": [asdict(offer)]}).encode()


LIST = listed()


def sig(message: bytes, key: SigningKey = KEY) -> bytes:
    return base64.b64encode(key.sign(message).signature)


def signed(data: bytes, key: SigningKey = KEY) -> bytes:
    return signed_list_file(sig(signed_list_message(data), key), data)


class Storage:
    """What the storage serves at the list's address, changed at will."""

    def __init__(self, whole: bytes | None) -> None:
        self.whole = whole

    def get(self, url: str) -> bytes:
        assert url == ADDRESS, url
        if self.whole is None:
            raise OSError("not found")
        return self.whole


def pack_list(tmp_path: Path, served: Storage) -> PackList:
    return PackList(BASE, [KEY.verify_key], tmp_path / "kept", get=served.get)


def test_a_signed_list_is_read_and_kept(tmp_path: Path) -> None:
    packs = pack_list(tmp_path, Storage(signed(LIST)))
    assert packs.fetch() == (OFFER,)
    assert packs.kept() == (OFFER,)
    assert packs.file_address(OFFER) == BASE + "packs/files/" + OFFER.file + ".gz"


@pytest.mark.parametrize(
    "whole",
    [
        signed_list_file(sig(signed_list_message(LIST), OTHER), LIST),  # another key
        signed_list_file(sig(signed_list_message(LIST + b" ")), LIST),  # another list's
        signed_list_file(sig(signed_message("win-x64-alpha", LIST)), LIST),  # a feed's
        signed_list_file(b"not base64!", LIST),
        signed_list_file(base64.b64encode(b"short"), LIST),
        LIST,  # no signature line at all
        signed(LIST).replace(b'"size": 10', b'"size": 11'),  # changed after signing
    ],
)
def test_a_tampered_list_is_refused_and_the_kept_one_stays(
    tmp_path: Path, whole: bytes
) -> None:
    served = Storage(signed(LIST))
    packs = pack_list(tmp_path, served)
    packs.fetch()
    served.whole = whole
    with pytest.raises(PackListNotTrusted):
        packs.fetch()
    assert packs.kept() == (OFFER,)


def test_an_older_list_served_again_is_refused(tmp_path: Path) -> None:
    """A list with a lower serial than the one kept - genuinely signed, but
    old - can't hide a newer pack."""
    newer = OFFER.__class__(**{**asdict(OFFER), "version": "2026.12.1"})
    served = Storage(signed(listed(6, newer)))
    packs = pack_list(tmp_path, served)
    assert packs.fetch() == (newer,)
    served.whole = signed(listed(5))
    with pytest.raises(PackListNotTrusted, match="older"):
        packs.fetch()
    assert packs.kept() == (newer,)
    served.whole = signed(listed(6, newer))  # the same list again: fine
    assert packs.fetch() == (newer,)


def test_a_newer_list_replaces_the_kept_one(tmp_path: Path) -> None:
    served = Storage(signed(listed(5)))
    packs = pack_list(tmp_path, served)
    packs.fetch()
    served.whole = signed(listed(9))
    packs.fetch()
    assert sorted(p.name for p in (tmp_path / "kept").iterdir()) == ["list.signed"]


def test_a_changed_kept_list_isnt_used(tmp_path: Path) -> None:
    packs = pack_list(tmp_path, Storage(signed(LIST)))
    packs.fetch()
    kept = tmp_path / "kept" / "list.signed"
    kept.write_bytes(kept.read_bytes().replace(b'"size": 10', b'"size": 12'))
    assert packs.kept() is None


def test_nothing_kept_is_none(tmp_path: Path) -> None:
    assert pack_list(tmp_path, Storage(None)).kept() is None


def test_a_list_too_big_is_refused(tmp_path: Path) -> None:
    big = LIST + b" " * 4_000_000
    with pytest.raises(PackListNotTrusted, match="too big"):
        pack_list(tmp_path, Storage(signed(big))).fetch()


def test_a_signed_list_of_another_format_is_refused(tmp_path: Path) -> None:
    other = json.dumps({"list": 2, "serial": 1, "packs": []}).encode()
    with pytest.raises(PackListNotTrusted, match="another format"):
        pack_list(tmp_path, Storage(signed(other))).fetch()


def test_a_signed_list_without_a_serial_is_refused(tmp_path: Path) -> None:
    unnumbered = json.dumps({"list": 1, "packs": [asdict(OFFER)]}).encode()
    with pytest.raises(PackListNotTrusted, match="serial"):
        pack_list(tmp_path, Storage(signed(unnumbered))).fetch()


def test_a_list_cant_be_fetched_raises_its_oserror(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        pack_list(tmp_path, Storage(None)).fetch()


def test_no_keys_is_a_mistake() -> None:
    with pytest.raises(ValueError):
        PackList(BASE, [], Path("."))


@pytest.mark.parametrize(
    "base",
    [
        "http://updates.polyglotic.io/",  # not https
        "ftp://updates.polyglotic.io/",
        "file:///C:/packs/",
        "https:///nohost",
        "http://192.168.1.5:8000/",  # http only on this PC's loopback
    ],
)
def test_packs_come_over_https_or_from_a_loopback_stand_in_only(base: str) -> None:
    with pytest.raises(ValueError):
        storage_address(base)


def test_https_and_a_loopback_stand_in_are_taken() -> None:
    assert storage_address("https://updates.polyglotic.io") == (
        "https://updates.polyglotic.io/"
    )
    assert storage_address("http://127.0.0.1:8123/") == "http://127.0.0.1:8123/"
