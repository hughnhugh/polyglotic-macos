"""A stand-in for the update storage's packs (decision 0122), for tests:
tiny packs built here, published by the real command into a folder laid
out as the bucket is, with a test key."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
from nacl.signing import SigningKey
from tools.package import publish_packs

from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.ports.dictionary import EntryRecord

KEY = SigningKey(b"\x05" * 32)
PUBLIC = base64.b64encode(KEY.verify_key.encode()).decode()
PRIVATE = base64.b64encode(bytes(KEY)).decode()

WORDS = (
    ("wiktru:1", "дом", "до́м", "house"),
    ("wiktru:2", "говорить", "говори́ть", "to speak"),
)


def tiny_pack(
    folder: Path,
    language: str = "ru",
    dictionary: str = "wiktru",
    meanings: str = "en",
    padding: int = 0,
) -> Path:
    """A real pack file, two entries, as `tools.dictionaries.packs` names
    it (`<dictionary>.sqlite`, `-zh` for Chinese meanings); `padding` rows
    of filler make it bigger, for downloads worth cutting short."""
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{dictionary}{'-zh' if meanings == 'zh' else ''}.sqlite"
    records = [
        EntryRecord(
            entry_id=f"{dictionary}:{n}",
            headword=head,
            traditional="",
            reading=said,
            meanings=(meaning if meanings == "en" else "房子",),
            frequency_rank=n,
            levels=(),
        )
        for n, (_, head, said, meaning) in enumerate(WORDS, start=1)
    ]
    records += [
        EntryRecord(
            entry_id=f"{dictionary}:{n}",
            headword=f"слово{n}",
            traditional="",
            reading="",
            meanings=(
                hashlib.sha256(str(n).encode()).hexdigest() * 3,
            ),  # not squeezable
            frequency_rank=None,
            levels=(),
        )
        for n in range(100, 100 + padding)
    ]
    write_dictionary(
        folder / name,
        {
            "dictionary": dictionary,
            "language": language,
            "tier": "basic",
            "meanings_language": meanings,
            "licence": "CC BY-SA 4.0",
        },
        records,
        {r.headword: [r.entry_id] for r in records},
    )
    (folder / f"{dictionary}.CREDITS.md").write_text("# credits\n", encoding="utf-8")
    return folder / name


def publish(
    monkeypatch: pytest.MonkeyPatch,
    out: Path,
    built: Path,
    version: str = "2026.11.14",
    previous: Path | None = None,
    language: str = "ru",
) -> int:
    """The real publishing command, a dry run, into `out` - a stand-in for
    the bucket - signed with the test key."""
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    if previous is None:  # as if the storage had an empty list, serial 1
        previous = out.parent / "no-list.signed"
        previous.write_bytes(
            publish_packs.sign_list(publish_packs.list_bytes([], 1), KEY)
        )
    return publish_packs.main(
        [
            language,
            "--packs",
            str(built),
            "--out",
            str(out),
            "--version",
            version,
            "--previous",
            str(previous),
        ]
    )
