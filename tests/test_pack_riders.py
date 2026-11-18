"""A pack's riders (decision 0133): its recorded words, named inside the
pack's entry in the signed list with their own `min_app` (decision 0192),
published beside it - with it, or later beside a pack already published -
and fetched quietly once the pack is in: never holding the pack up, and
never by an app that can't play them."""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.packs_server import StandIn
from tests.packs_storage import PRIVATE, PUBLIC, tiny_pack
from tools.package import publish_packs

from polyglotic_desktop.adapters.audio_file import audio_beside, write_audio
from polyglotic_desktop.adapters.pack_downloads import PackDeliveries, PackFolder
from polyglotic_desktop.adapters.pack_list import PackList, split_signed_list
from polyglotic_desktop.adapters.signed_feed import public_keys
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Step
from polyglotic_desktop.core.lexicon.packs import (
    FROM_SOURCE,
    BuiltIn,
    FontOffer,
    PackOffer,
    Reader,
    Rider,
    read_built_in,
    read_pack_list,
    riders_wanted,
)

VERSION = "2026.11.14"
BEFORE_RIDERS = Reader(frozenset({"1"}), frozenset({"spaced"}), "0.1.6")
READER = Reader(
    frozenset({"1"}), frozenset({"spaced"}), "0.1.7", frozenset({("audio", "1")})
)
LIST = "packs/v1/list.signed"
OGG_HEAD = b"OggS" + b"\0" * 40


def recorded(folder: Path, dictionary: str = "wiktru") -> Path:
    """One recorded word, as `tools.dictionaries.audio` names its file."""
    folder.mkdir(parents=True, exist_ok=True)
    write_audio(
        folder / f"{dictionary}.audio",
        {
            "dictionary": dictionary,
            "language": "ru",
            "voice_language": "ru-RU",
            "voice": "Kokoro-82M v1.0, rf_test (espeak-ng G2P)",
            "licence": "Apache-2.0; its voice's data CC BY 4.0 (its authors)",
        },
        OGG_HEAD,
        [("дом", b"OggS-the-word")],
    )
    return folder


def built_with_audio(folder: Path) -> Path:
    """A built pack (English and Chinese meanings, as Russian's is
    published) and its recorded words."""
    tiny_pack(folder)
    tiny_pack(folder, meanings="zh")
    return recorded(folder)


def published(
    monkeypatch: pytest.MonkeyPatch, out: Path, *extra: str, previous: Path
) -> int:
    """The real publishing command, a dry run, into `out` (a stand-in for
    the bucket), signed with the test key."""
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    return publish_packs.main(
        ["ru", "--out", str(out), "--previous", str(previous), *extra]
    )


@pytest.fixture
def bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "bucket"
    built = built_with_audio(tmp_path / "built")
    no_list = tmp_path / "no-list.signed"
    no_list.write_bytes(
        publish_packs.sign_list(
            publish_packs.list_bytes([], 1), publish_packs.private_key_from(PRIVATE)
        )
    )
    extra = ("--packs", str(built), "--audio", str(built), "--version", VERSION)
    assert published(monkeypatch, out, *extra, previous=no_list) == 0
    return out


@pytest.fixture
def server(bucket: Path) -> Iterator[StandIn]:
    with StandIn(bucket) as stand_in:
        yield stand_in


def offers_in(bucket: Path) -> tuple[PackOffer, ...]:
    _, data = split_signed_list((bucket / LIST).read_bytes())
    return read_pack_list(data)[0]


def listed(bucket: Path) -> PackOffer:
    (offer,) = (o for o in offers_in(bucket) if o.meanings == "en")
    return offer


@dataclass
class Seen:
    installed: list[Path] = field(default_factory=list)
    riders: list[tuple[Rider, Path]] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    done: threading.Event = field(default_factory=threading.Event)

    def on_progress(self, progress: PackProgress) -> None:
        self.steps.append(progress.step)

    def on_installed(self, offer: PackOffer, path: Path) -> None:
        self.installed.append(path)

    def on_rider(
        self, offer: PackOffer | BuiltIn | FontOffer, rider: Rider, path: Path
    ) -> None:
        self.riders.append((rider, path))


def deliveries(
    server: StandIn, tmp_path: Path, seen: Seen, reader: Reader = READER
) -> PackDeliveries:
    return PackDeliveries(
        PackList(server.base, public_keys([PUBLIC]), tmp_path / "list"),
        PackFolder(tmp_path / "packs"),
        reader,
        seen.on_progress,
        seen.on_installed,
        on_rider=seen.on_rider,
        retry=lambda _tries, _problem: None,
        stall_sec=0.5,
    )


def finish(got: PackDeliveries) -> None:
    """Everything asked of it done, and its thread over."""
    got.close()
    got.join(30)


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.suffix == ".audio")


# -- the list ------------------------------------------------------------------


def test_publishing_names_the_recordings_in_each_of_the_packs_entries(
    bucket: Path,
) -> None:
    offers = offers_in(bucket)
    assert sorted(o.meanings for o in offers) == ["en", "zh"]
    for offer in offers:  # the same file, whichever meanings a learner has
        assert [(r.kind, r.min_app, r.file) for r in offer.riders] == [
            ("audio", publish_packs.RIDER_MIN_APP, f"wiktru-{VERSION}.audio")
        ]
        assert offer.min_app == publish_packs.MIN_APP  # the pack's own stays
    (rider,) = listed(bucket).riders
    packed = bucket / "packs" / "files" / rider.download
    assert packed.stat().st_size == rider.gz_size and rider.format == "1"


def test_recordings_go_up_beside_a_pack_already_published(
    bucket: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-11-16's packs are out (min app 0.1.7): their recordings are
    added later, the packs as they are - nothing an app reads changes but
    the riders, which only an app that plays them takes."""
    built = tmp_path / "packs-only"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    before = tmp_path / "before"
    packs_only = (
        "--packs",
        str(built),
        "--version",
        "2026.11.16",
        "--min-app",
        "0.1.7",
    )
    assert published(monkeypatch, before, *packs_only, previous=bucket / LIST) == 0
    out_before = offers_in(before)
    assert not [o for o in out_before if o.version == "2026.11.16" and o.riders]

    later = tmp_path / "later"
    audio = recorded(tmp_path / "audio")
    extra = ("--audio", str(audio), "--riders-only", "--version", "2026.11.16")
    assert published(monkeypatch, later, *extra, previous=before / LIST) == 0
    files = sorted(p.name for p in (later / "packs" / "files").iterdir())
    assert files == ["wiktru-2026.11.16.audio.gz"]  # no pack goes up again
    after = {o.file: o for o in offers_in(later)}
    assert sorted(after) == sorted(o.file for o in out_before)
    for offer in out_before:
        now = after[offer.file]
        if offer.version != "2026.11.16":
            assert now == offer  # the older versions as they were
            continue
        assert now.sha256 == offer.sha256 and now.min_app == "0.1.7"
        assert [(r.file, r.min_app) for r in now.riders] == [
            ("wiktru-2026.11.16.audio", "0.1.7")
        ]
    _, data = split_signed_list((later / LIST).read_bytes())
    _, old = split_signed_list((before / LIST).read_bytes())
    assert json.loads(data)["serial"] == json.loads(old)["serial"] + 1


def test_riders_only_needs_the_pack_published_and_its_own_audio(
    bucket: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, listed_now = tmp_path / "out", bucket / LIST
    audio = recorded(tmp_path / "audio")
    not_out = ("--audio", str(audio), "--riders-only", "--version", "2026.12.1")
    assert published(monkeypatch, out, *not_out, previous=listed_now) == 1
    assert published(monkeypatch, out, "--riders-only", previous=listed_now) == 2
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    write_audio(wrong / "wiktru.audio", {"dictionary": "wiktfr"}, OGG_HEAD, [])
    with pytest.raises(SystemExit, match="wiktfr"):
        published(
            monkeypatch,
            out,
            *("--audio", str(wrong), "--riders-only", "--version", VERSION),
            previous=listed_now,
        )


def test_a_rider_the_list_gets_wrong_is_left_out_and_the_pack_stays(
    bucket: Path,
) -> None:
    _, data = split_signed_list((bucket / LIST).read_bytes())
    whole = json.loads(data)
    good = whole["packs"][0]["riders"][0]
    whole["packs"][0]["riders"] = [
        {**good, "meanings": "vi", "later": 1},  # a newer list's fields: ignored
        {**good, "kind": "pictures", "file": "wiktru-1.pictures"},  # a newer kind
        {**good, "file": "../wiktru-1.audio"},
        {**good, "file": "other-1.audio"},  # another dictionary's
        {**good, "min_app": "soon"},
        {k: v for k, v in good.items() if k != "min_app"},
        {**good, "size": 0},
        {**good, "sha256": "no"},
        "nonsense",
    ]
    offers, _ = read_pack_list(json.dumps(whole).encode())
    assert [r.file for r in offers[0].riders] == [good["file"]]
    whole["packs"][0]["riders"] = "nonsense"
    offers, _ = read_pack_list(json.dumps(whole).encode())
    assert offers[0].riders == ()
    del whole["packs"][0]["riders"]  # a list from before riders
    offers, _ = read_pack_list(json.dumps(whole).encode())
    assert offers[0].riders == ()


def test_only_an_app_that_plays_them_takes_the_recordings(bucket: Path) -> None:
    offer = listed(bucket)

    def kinds(reader: Reader) -> list[str]:
        return [r.kind for r in riders_wanted(offer, reader)]

    assert kinds(READER) == ["audio"]
    assert kinds(BEFORE_RIDERS) == []  # 0.1.6: no player
    older = Reader(READER.formats, READER.splits, "0.1.6", READER.riders)
    assert kinds(older) == []  # reads them, but the list says from 0.1.7
    source = Reader(READER.formats, READER.splits, FROM_SOURCE, READER.riders)
    assert kinds(source) == ["audio"]
    newer_format = Reader(
        READER.formats, READER.splits, "0.1.7", frozenset({("audio", "2")})
    )
    assert kinds(newer_format) == []


# -- the download --------------------------------------------------------------


def test_recordings_come_after_the_pack_and_open(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    finish(got)
    folder = tmp_path / "packs"
    assert [p.name for p in seen.installed] == [f"wiktru-en-{VERSION}.sqlite"]
    assert names(folder) == [f"wiktru-{VERSION}.audio"]
    assert [(r.kind, p.name) for r, p in seen.riders] == [
        ("audio", f"wiktru-{VERSION}.audio")
    ]
    assert not list(folder.glob("*.part")) and not list(folder.glob("*.unpacking"))
    audio = audio_beside([folder], "wiktru")
    assert audio is not None
    assert audio.clip("дом") == OGG_HEAD + b"OggS-the-word"
    assert audio.info["version"] == VERSION
    audio.close()
    # the pack's own steps end at "done": a rider's download says nothing
    assert seen.steps.count(Step.DONE) == 1 and seen.steps[-1] is Step.DONE


def test_an_app_from_before_riders_fetches_only_the_pack(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    got = deliveries(server, tmp_path, seen, reader=BEFORE_RIDERS)
    got.want("ru", "en")
    finish(got)
    assert len(seen.installed) == 1 and seen.riders == []
    assert names(tmp_path / "packs") == []
    fetched = [path for path, _, _ in server.requests]
    assert not any(".audio" in path for path in fetched)


def test_a_rider_that_fails_never_fails_the_pack_and_comes_next_time(
    server: StandIn, tmp_path: Path
) -> None:
    rider = f"packs/files/wiktru-{VERSION}.audio.gz"
    server.faults.status[rider] = 500
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    finish(got)
    assert len(seen.installed) == 1 and seen.riders == []
    assert names(tmp_path / "packs") == []

    del server.faults.status[rider]
    again = Seen()
    got = deliveries(server, tmp_path, again)
    got.want("ru", "en", update=True)  # the daily check
    finish(got)
    assert again.installed == []  # the pack was here already
    assert [r.kind for r, _ in again.riders] == ["audio"]
    assert names(tmp_path / "packs") == [f"wiktru-{VERSION}.audio"]


def test_a_rider_that_isnt_the_lists_file_is_refused(
    server: StandIn, tmp_path: Path
) -> None:
    rider = f"packs/files/wiktru-{VERSION}.audio.gz"
    server.faults.swap[rider] = (server.folder / rider).read_bytes()[:-9] + b"x" * 9
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    finish(got)
    assert len(seen.installed) == 1 and seen.riders == []
    assert names(tmp_path / "packs") == []
    assert not list((tmp_path / "packs").glob("*.unpacking"))


# -- the folder ----------------------------------------------------------------


def test_the_folder_names_a_dictionarys_riders_and_the_outdated(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "packs"
    folder.mkdir()
    for name in (
        "wiktru-2026.11.14.audio",
        "wiktru-2026.12.1.audio",
        "wiktfr-2026.11.14.audio",
        "wiktru-en-2026.12.1.sqlite",
    ):
        (folder / name).write_bytes(b"x")
    packs = PackFolder(folder)
    assert [p.name for p in packs.riders("wiktru")] == [
        "wiktru-2026.11.14.audio",
        "wiktru-2026.12.1.audio",
    ]
    assert [p.name for p in packs.outdated_riders()] == ["wiktru-2026.11.14.audio"]
    assert PackFolder(tmp_path / "none").riders("wiktru") == []
    assert PackFolder(tmp_path / "none").outdated_riders() == []


# -- a dictionary built into the app (decision 0197) -----------------------------

CEDICT_VERSION = "2026.11.17"


def recorded_chinese(folder: Path) -> Path:
    """CC-CEDICT's recorded words, as the tool names its file: the dictionary
    is built into the app, so no pack goes with them."""
    folder.mkdir(parents=True, exist_ok=True)
    write_audio(
        folder / "cedict.audio",
        {
            "dictionary": "cedict",
            "language": "zh",
            "voice_language": "zh-CN",
            "voice": "Chatterbox Multilingual zh-cmn, built-in voice",
            "licence": "Chatterbox: MIT (Resemble AI)",
            "watermark": "Resemble AI's Perth watermark",
        },
        OGG_HEAD,
        [("我们", b"OggS-women")],
    )
    return folder


def published_built_in(
    monkeypatch: pytest.MonkeyPatch, out: Path, audio: Path, previous: Path, *extra: str
) -> int:
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    return publish_packs.main(
        [
            *extra,
            "--built-in",
            "cedict",
            "--audio",
            str(audio),
            "--out",
            str(out),
            "--previous",
            str(previous),
        ]
    )


@pytest.fixture
def built_in_bucket(
    bucket: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The packs published, then CC-CEDICT's recordings beside them."""
    out = tmp_path / "bucket-cedict"
    audio = recorded_chinese(tmp_path / "zh-audio")
    extra = ("--version", CEDICT_VERSION)
    assert published_built_in(monkeypatch, out, audio, bucket / LIST, *extra) == 0
    shutil.copytree(
        bucket / "packs" / "files", out / "packs" / "files", dirs_exist_ok=True
    )
    return out


def built_in_of(bucket: Path) -> tuple[BuiltIn, ...]:
    _, data = split_signed_list((bucket / LIST).read_bytes())
    return read_built_in(data)


def test_a_built_in_dictionarys_recordings_have_an_entry_of_their_own(
    bucket: Path, built_in_bucket: Path
) -> None:
    """CC-CEDICT has no pack to ride on: its recordings get a `built_in`
    entry, and every pack's entry is as it was - an app from before reads
    the same list it did (decision 0197)."""
    (entry,) = built_in_of(built_in_bucket)
    assert (entry.dictionary, entry.language) == ("cedict", "zh")
    (rider,) = entry.riders
    assert (rider.kind, rider.file, rider.min_app) == (
        "audio",
        f"cedict-{CEDICT_VERSION}.audio",
        publish_packs.RIDER_MIN_APP,
    )
    packed = built_in_bucket / "packs" / "files" / rider.download
    assert packed.stat().st_size == rider.gz_size
    _, data = split_signed_list((built_in_bucket / LIST).read_bytes())
    assert read_pack_list(data) == (offers_in(bucket), 0)
    assert built_in_of(bucket) == ()


def test_a_later_publish_keeps_the_built_in_entry_and_a_new_one_replaces_it(
    built_in_bucket: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = built_with_audio(tmp_path / "built-again")
    again = tmp_path / "bucket-again"
    extra = ("--packs", str(built), "--version", "2026.12.1")
    assert published(monkeypatch, again, *extra, previous=built_in_bucket / LIST) == 0
    assert built_in_of(again) == built_in_of(built_in_bucket)  # kept
    newer = tmp_path / "bucket-newer"
    audio = recorded_chinese(tmp_path / "zh-audio-newer")
    later = ("--version", "2026.12.2")
    assert published_built_in(monkeypatch, newer, audio, again / LIST, *later) == 0
    (entry,) = built_in_of(newer)  # one entry for it, the newer file
    assert [r.file for r in entry.riders] == ["cedict-2026.12.2.audio"]
    # the same name with other bytes is refused, as a pack's is
    write_audio(
        audio / "cedict.audio",
        {"dictionary": "cedict", "language": "zh"},
        OGG_HEAD,
        [("你好", b"OggS-nihao")],
    )
    clash = tmp_path / "bucket-clash"
    assert published_built_in(monkeypatch, clash, audio, newer / LIST, *later) == 1


def test_the_publish_step_needs_packs_or_a_built_in_dictionary_with_its_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    out = str(tmp_path / "out")
    assert publish_packs.main(["--out", out]) == 2
    assert publish_packs.main(["--built-in", "cedict", "--out", out]) == 2


def test_a_built_in_entry_the_list_gets_wrong_is_left_out() -> None:
    good = {
        "kind": "audio",
        "format": "1",
        "min_app": "0.1.7",
        "file": "cedict-2026.11.17.audio",
        "size": 10,
        "sha256": "a" * 64,
        "gz_size": 9,
        "gz_sha256": "b" * 64,
    }
    entries = [
        {"dictionary": "cedict", "language": "zh", "riders": [good]},
        {"dictionary": "Ce/dict", "language": "zh", "riders": [good]},
        {"dictionary": "cedict", "riders": [good]},
        {"dictionary": "cedict", "language": "zh", "riders": [{**good, "kind": "x"}]},
        {"dictionary": "ecdict", "language": "en", "riders": [good]},  # not its file
        "cedict",
    ]
    whole = {"list": 1, "serial": 5, "packs": [], "built_in": entries}
    (entry,) = read_built_in(json.dumps(whole).encode())
    assert entry.dictionary == "cedict" and entry.riders[0].file == good["file"]
    assert read_built_in(b"[]") == () and read_built_in(b"not json") == ()
    assert read_built_in(json.dumps({**whole, "built_in": {}}).encode()) == ()


def test_a_built_in_dictionarys_recordings_come_quietly_to_an_app_that_plays_them(
    built_in_bucket: Path, tmp_path: Path
) -> None:
    with StandIn(built_in_bucket) as server:
        seen = Seen()
        got = deliveries(server, tmp_path, seen)
        got.want("zh", "", built_in="cedict")
        finish(got)
        assert seen.installed == [] and Step.DONE not in seen.steps
        assert [p.name for _, p in seen.riders] == [f"cedict-{CEDICT_VERSION}.audio"]
        audio = audio_beside([tmp_path / "packs"], "cedict")
        assert audio is not None and audio.clip("我们") == OGG_HEAD + b"OggS-women"
        audio.close()
        # an app from before them takes none; asked again, nothing comes twice
        before = Seen()
        older = deliveries(server, tmp_path / "older", before, reader=BEFORE_RIDERS)
        older.want("zh", "", built_in="cedict")
        finish(older)
        assert before.riders == [] and not list((tmp_path / "older").rglob("*.audio"))
        again = Seen()
        got = deliveries(server, tmp_path, again)
        got.want("zh", "", built_in="cedict")
        finish(got)
        assert again.riders == []


def test_on_a_metered_connection_a_built_in_dictionarys_recordings_wait(
    built_in_bucket: Path, tmp_path: Path
) -> None:
    with StandIn(built_in_bucket) as server:
        seen = Seen()
        got = PackDeliveries(
            PackList(server.base, public_keys([PUBLIC]), tmp_path / "list"),
            PackFolder(tmp_path / "packs"),
            READER,
            seen.on_progress,
            seen.on_installed,
            on_rider=seen.on_rider,
            metered=lambda: True,
            retry=lambda _tries, _problem: None,
        )
        got.want("zh", "", built_in="cedict")
        finish(got)
        assert seen.riders == []
        fetched = [path for path, _, _ in server.requests]
        assert not any(".audio" in path for path in fetched)
