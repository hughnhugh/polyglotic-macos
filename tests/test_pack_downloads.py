"""A dictionary pack's download on a stand-in for the storage (decision
0122): each step said, each way it stands still said, cut downloads
carried on, a wrong file or list refused, and the log's lines for a
failure content-free."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.packs_server import StandIn
from tests.packs_storage import KEY, PUBLIC, publish, tiny_pack
from tools.package import publish_packs

from polyglotic_desktop.adapters.pack_downloads import PackDeliveries, PackFolder
from polyglotic_desktop.adapters.pack_list import (
    PackList,
    signed_list_file,
    split_signed_list,
)
from polyglotic_desktop.adapters.signed_feed import public_keys
from polyglotic_desktop.core.lexicon.pack_download import (
    PackProgress,
    Problem,
    Step,
    retry_after,
)
from polyglotic_desktop.core.lexicon.packs import PackOffer, Reader, Rider

READER = Reader(frozenset({"1"}), frozenset({"spaced"}), "0.1.5")
FILE = "packs/files/wiktru-en-2026.11.14.sqlite.gz"
LIST = "packs/v1/list.signed"


def served_list(server: StandIn) -> tuple[bytes, bytes]:
    """The stand-in's list as published: (signature, list)."""
    return split_signed_list((server.folder / LIST).read_bytes())


def resigned(data: bytes) -> bytes:
    """`data` signed as the publisher signs a list, with the test key."""
    return publish_packs.sign_list(data, KEY)


@dataclass
class Seen:
    """What the deliveries said, from their thread."""

    progress: list[PackProgress] = field(default_factory=list)
    installed: list[tuple[PackOffer, Path]] = field(default_factory=list)
    finished: threading.Event = field(default_factory=threading.Event)

    def on_progress(self, progress: PackProgress) -> None:
        self.progress.append(progress)
        if progress.step is Step.CANCELLED or progress.stopped:
            self.finished.set()

    def on_installed(self, offer: PackOffer, path: Path) -> None:
        self.installed.append((offer, path))
        self.finished.set()

    def wait(self) -> None:
        assert self.finished.wait(20), "the download never finished or stopped"
        self.finished.clear()

    @property
    def steps(self) -> list[Step]:
        return list(dict.fromkeys(p.step for p in self.progress))

    @property
    def last(self) -> PackProgress:
        return self.progress[-1]


@pytest.fixture
def bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    built = tmp_path / "built"
    tiny_pack(built, padding=20000)  # about 1.2 MB gzipped: worth cutting short
    tiny_pack(built, meanings="zh")
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built) == 0
    return out


@pytest.fixture
def server(bucket: Path) -> Iterator[StandIn]:
    with StandIn(bucket) as stand_in:
        yield stand_in


def deliveries(
    server: StandIn,
    tmp_path: Path,
    seen: Seen,
    **options: object,
) -> PackDeliveries:
    packs = PackList(server.base, public_keys([PUBLIC]), tmp_path / "list")
    options.setdefault(
        "retry", lambda tries, problem: 0.05 if retry_after(tries, problem) else None
    )
    options.setdefault("stall_sec", 0.5)
    reader = options.pop("reader", READER)
    return PackDeliveries(
        packs,
        PackFolder(tmp_path / "packs"),
        reader,  # type: ignore[arg-type]
        seen.on_progress,
        seen.on_installed,
        **options,  # type: ignore[arg-type]
    )


@pytest.fixture
def japanese_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[StandIn, Rider, bytes]]:
    """A Japanese pack and its required dictionary beside it in fake storage."""
    built = tmp_path / "japanese-built"
    tiny_pack(built, language="ja", dictionary="jmdict")
    tiny_pack(built, language="ja", dictionary="jmdict", meanings="zh")
    bucket = tmp_path / "japanese-bucket"
    assert publish(monkeypatch, bucket, built, language="ja") == 0
    dictionary = b"stand-in Sudachi system dictionary"
    packed = gzip.compress(dictionary, mtime=0)
    rider = Rider(
        kind="japanese-dictionary",
        format="test",
        min_app="0.1.5",
        file="test.system.dic",
        size=len(dictionary),
        sha256=hashlib.sha256(dictionary).hexdigest(),
        gz_size=len(packed),
        gz_sha256=hashlib.sha256(packed).hexdigest(),
    )
    object_name = "packs/v1/test.system.dic.gz"
    (bucket / object_name).parent.mkdir(parents=True, exist_ok=True)
    (bucket / object_name).write_bytes(packed)
    monkeypatch.setattr("polyglotic_desktop.adapters.japanese_dictionary.RIDER", rider)
    monkeypatch.setattr(
        "polyglotic_desktop.adapters.japanese_dictionary.OBJECT_NAME", object_name
    )
    with StandIn(bucket) as stand_in:
        yield stand_in, rider, packed


def test_japanese_pack_and_dictionary_download_as_one_delivery(
    japanese_server: tuple[StandIn, Rider, bytes], tmp_path: Path
) -> None:
    server, rider, _packed = japanese_server
    seen = Seen()
    got = deliveries(
        server,
        tmp_path,
        seen,
        reader=Reader(frozenset({"1"}), frozenset({"japanese"}), "0.1.12"),
    )
    got.want("ja", "en")
    seen.wait()
    assert seen.installed[0][0].split == "japanese"
    assert (tmp_path / "packs" / rider.file).read_bytes() == (
        b"stand-in Sudachi system dictionary"
    )
    requested = [path for path, _range, code in server.requests if code == 200]
    assert requested.index(
        "packs/files/jmdict-en-2026.11.14.sqlite.gz"
    ) < requested.index("packs/v1/test.system.dic.gz")
    assert seen.steps == [
        Step.LIST,
        Step.DOWNLOADING,
        Step.CHECKING,
        Step.OPENING,
        Step.DONE,
    ]
    got.close()


def test_wrong_japanese_dictionary_hash_is_refused_and_deleted(
    japanese_server: tuple[StandIn, Rider, bytes], tmp_path: Path
) -> None:
    server, rider, packed = japanese_server
    server.faults.swap["packs/v1/test.system.dic.gz"] = (
        bytes([packed[0] ^ 1]) + packed[1:]
    )
    seen = Seen()
    got = deliveries(
        server,
        tmp_path,
        seen,
        reader=Reader(frozenset({"1"}), frozenset({"japanese"}), "0.1.12"),
    )
    got.want("ja", "en")
    seen.wait()
    assert seen.last.problem is Problem.FILE_REFUSED
    assert not (tmp_path / "packs" / rider.file).exists()
    assert not list((tmp_path / "packs").glob("*system.dic*"))
    got.close()


def test_a_pack_downloads_checks_opens_and_is_installed(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    seen.wait()
    offer, path = seen.installed[0]
    assert path == tmp_path / "packs" / "wiktru-en-2026.11.14.sqlite"
    assert path.stat().st_size == offer.size
    assert (tmp_path / "packs" / "wiktru.CREDITS.md").read_text(
        encoding="utf-8"
    ) == "# credits\n"
    assert not list((tmp_path / "packs").glob("*.part"))
    assert seen.steps == [  # nothing ahead of it: no "waiting" (330)
        Step.LIST,
        Step.DOWNLOADING,
        Step.CHECKING,
        Step.OPENING,
        Step.DONE,
    ]
    installed = PackFolder(tmp_path / "packs").installed()
    assert installed[("ru", "en")][0].version == "2026.11.14"
    got.close()


@dataclass
class Holding(Seen):
    """Seen, holding the deliveries' thread at the first language's
    download until `go` is set: one download under way."""

    first: str = "ru"
    held: threading.Event = field(default_factory=threading.Event)
    go: threading.Event = field(default_factory=threading.Event)

    def on_progress(self, progress: PackProgress) -> None:
        super().on_progress(progress)
        if progress.language == self.first and progress.step is Step.DOWNLOADING:
            self.held.set()
            self.go.wait(10)


def test_waiting_is_said_only_behind_another_download(
    server: StandIn, tmp_path: Path
) -> None:
    """329's QA (D3): "Waiting for another dictionary to finish." showed
    after Download with nothing else downloading. Alone, a download says
    it checks the list; behind another, that it waits (330)."""
    seen = Holding()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    assert seen.held.wait(10), "the first download never started"
    got.want("ko", "en")  # Korean asked for while Russian's comes down
    try:
        first = {p.language: p.step for p in reversed(seen.progress)}
        assert first == {"ru": Step.LIST, "ko": Step.WAITING}
    finally:
        seen.go.set()
    deadline = time.monotonic() + 20  # Russian's in; then Korean, which has no pack
    while not (seen.last.language == "ko" and seen.last.stopped):
        assert time.monotonic() < deadline, "Korean was never tried"
        time.sleep(0.02)
    assert seen.installed and seen.last.problem is Problem.NOT_OFFERED
    got.close()


def test_chinese_meanings_come_from_their_own_file(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "zh")
    seen.wait()
    assert seen.installed[0][0].file == "wiktru-zh-2026.11.14.sqlite"


def test_a_cut_download_is_carried_on_from_where_it_stopped(
    server: StandIn, tmp_path: Path
) -> None:
    server.faults.cut_after = [400_000, 400_000]
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    assert seen.installed
    asked = [(r, code) for path, r, code in server.requests if path == FILE]
    assert asked == [("", 200), ("bytes=400000-", 206), ("bytes=800000-", 206)]
    offline = [p for p in seen.progress if p.problem is Problem.OFFLINE]
    assert offline and offline[0].retry_in is not None and offline[0].tries == 1
    assert offline[0].done == 400_000  # where it stood, said


def test_a_wrong_file_is_refused_and_deleted(server: StandIn, tmp_path: Path) -> None:
    size = (server.folder / FILE).stat().st_size
    server.faults.swap[FILE] = b"\0" * size  # the right size, other bytes
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.FILE_REFUSED and seen.last.stopped
    assert not seen.installed
    assert not list((tmp_path / "packs").glob("*"))


def test_a_tampered_list_is_refused_before_anything_downloads(
    server: StandIn, tmp_path: Path
) -> None:
    signature, data = served_list(server)
    whole = json.loads(data)
    whole["packs"][0]["sha256"] = "0" * 64
    server.faults.swap[LIST] = signed_list_file(signature, json.dumps(whole).encode())
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.LIST_REFUSED and seen.last.stopped
    assert not any(path == FILE for path, _, _ in server.requests)


def test_a_stalled_download_says_so_and_is_tried_again(
    server: StandIn, tmp_path: Path
) -> None:
    server.faults.stall_after = 128 * 1024
    server.faults.stall_for = 2.0
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    stalled = [p for p in seen.progress if p.problem is Problem.STALLED]
    assert stalled and stalled[0].retry_in is not None
    assert seen.installed  # the next try, from where it stopped


def test_tries_stop_after_the_last_and_retry_starts_again(
    server: StandIn, tmp_path: Path
) -> None:
    server.faults.status[FILE] = 503
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.SERVER and seen.last.status == 503
    assert seen.last.tries == 6 and seen.last.stopped
    del server.faults.status[FILE]
    got.want("ru", "en")  # Retry
    seen.wait()
    assert seen.installed


def test_not_enough_room_says_how_much_it_needs(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    deliveries(server, tmp_path, seen, free_space=lambda _: 1000).want("ru", "en")
    seen.wait()
    listed = json.loads(served_list(server)[1])
    entry = next(p for p in listed["packs"] if p["meanings"] == "en")
    assert seen.last.problem is Problem.NO_ROOM and seen.last.stopped
    assert seen.last.needed == entry["gz_size"] + entry["size"]  # both, a while


def test_a_metered_connection_pauses_until_the_learner_says_go_on(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    got = deliveries(server, tmp_path, seen, metered=lambda: True)
    got.want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.METERED and seen.last.stopped
    assert not any(path == FILE for path, _, _ in server.requests)
    got.want("ru", "en", metered_ok=True)  # Download anyway
    seen.wait()
    assert seen.installed


def test_a_pack_only_a_newer_app_reads_is_never_downloaded(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    old_app = Reader(frozenset({"1"}), frozenset({"spaced"}), "0.1.4")
    deliveries(server, tmp_path, seen).reader = old_app
    got = deliveries(server, tmp_path, seen)
    got.reader = old_app
    got.want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.NEEDS_NEWER_APP and seen.last.stopped
    assert not any(path == FILE for path, _, _ in server.requests)


def test_a_language_with_no_pack_says_so(server: StandIn, tmp_path: Path) -> None:
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ko", "en")
    seen.wait()
    assert seen.last.problem is Problem.NOT_OFFERED


def test_offline_is_tried_again_then_stops(tmp_path: Path) -> None:
    seen = Seen()
    packs = PackList("http://127.0.0.1:9/", public_keys([PUBLIC]), tmp_path / "list")
    got = PackDeliveries(
        packs,
        PackFolder(tmp_path / "packs"),
        READER,
        seen.on_progress,
        seen.on_installed,
        retry=lambda tries, problem: 0.01 if retry_after(tries, problem) else None,
    )
    got.want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.OFFLINE and seen.last.tries == 6


def test_cancel_stops_it_and_deletes_what_came(server: StandIn, tmp_path: Path) -> None:
    server.faults.slow = 0.2
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    while not any(p.step is Step.DOWNLOADING and p.done for p in seen.progress):
        threading.Event().wait(0.02)
    got.cancel("ru")
    seen.wait()
    assert seen.last.step is Step.CANCELLED
    assert not seen.installed
    assert not list((tmp_path / "packs").glob("*.part"))


def test_a_slow_download_says_how_far_along_and_no_time_left_too_soon(
    server: StandIn, tmp_path: Path
) -> None:
    server.faults.slow = 0.1
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    downloading = [p for p in seen.progress if p.step is Step.DOWNLOADING]
    done = [p.done for p in downloading]
    assert len(done) >= 3 and done == sorted(done)
    assert all(p.seconds_left is None for p in downloading)  # under 5 s in: not said


def test_the_log_says_what_happened_without_addresses_or_paths(
    server: StandIn, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "polyglotic_desktop.adapters")
    server.faults.cut_after = [200_000]
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    said = caplog.text
    assert "packs list checked: 2 packs" in said
    assert "dictionary pack ru: try 1 of 6 failed: offline; next try in" in said
    assert "downloading from byte 200000 of" in said
    assert "dictionary pack ru/en 2026.11.14: installed" in said
    assert "127.0.0.1" not in said and str(tmp_path) not in said


def test_already_on_this_pc_isnt_downloaded_again(
    server: StandIn, tmp_path: Path
) -> None:
    seen = Seen()
    got = deliveries(server, tmp_path, seen)
    got.want("ru", "en")
    seen.wait()
    server.requests.clear()
    got.want("ru", "en")
    seen.wait()
    assert len(seen.installed) == 2
    assert not any(path == FILE for path, _, _ in server.requests)


def test_the_folder_keeps_the_newest_and_names_the_rest(tmp_path: Path) -> None:
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info

    folder = tmp_path / "packs"
    old = tiny_pack(folder)
    add_info(old, {"pack_version": "2026.11.1"})
    new = folder / "wiktru-en-2026.11.14.sqlite"
    new.write_bytes(old.read_bytes())
    add_info(new, {"pack_version": "2026.11.14"})
    packs = PackFolder(folder)
    assert packs.installed()[("ru", "en")][1] == new
    assert packs.outdated() == [old]
    assert packs.remove(packs.outdated()) > 0
    assert not old.exists()


def test_a_download_that_unpacks_wrong_is_refused(
    server: StandIn, tmp_path: Path
) -> None:
    """Right size and SHA-256 for the download, but what it unpacks to isn't
    the list's file: refused, both deleted (only a list we signed could
    say so - this is the second check holding on its own)."""
    import gzip
    import hashlib

    whole = json.loads(served_list(server)[1])
    other = gzip.compress(b"not a dictionary" * 1000)
    entry = next(p for p in whole["packs"] if p["meanings"] == "en")
    entry["gz_size"], entry["gz_sha256"] = len(other), hashlib.sha256(other).hexdigest()
    server.faults.swap[FILE] = other
    server.faults.swap[LIST] = resigned(json.dumps(whole).encode())
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.FILE_REFUSED and seen.last.stopped
    assert not list((tmp_path / "packs").glob("*"))


def test_a_gzip_bomb_stops_at_the_lists_size(tmp_path: Path) -> None:
    import gzip

    from polyglotic_desktop.adapters.pack_downloads import _unpack

    bomb = tmp_path / "bomb.gz"
    bomb.write_bytes(gzip.compress(b"\0" * 50_000_000))
    out = tmp_path / "out"
    _unpack(bomb, out, 1_000_000, lambda _: None)
    assert out.stat().st_size == 1_000_001  # cut one past: refused by its size


def test_retry_while_waiting_tries_at_once(server: StandIn, tmp_path: Path) -> None:
    """A stalled or cut download offers Retry while it counts down: asked,
    the next try starts now, not after the wait."""
    server.faults.cut_after = [100_000]
    seen = Seen()
    got = deliveries(
        server,
        tmp_path,
        seen,
        retry=lambda tries, problem: 60.0 if retry_after(tries, problem) else None,
    )
    got.want("ru", "en")
    while not any(p.problem is Problem.OFFLINE for p in seen.progress):
        threading.Event().wait(0.02)
    got.want("ru", "en")  # Retry, mid-countdown
    seen.wait()
    assert seen.installed  # well before the 60 s wait


@pytest.mark.parametrize(
    "fault",
    ["tampered", "mismatched", "older", 404, 500, "not even a list"],
)
def test_a_refresh_that_fails_never_ends_the_downloads(
    server: StandIn, tmp_path: Path, fault: object
) -> None:
    """A refresh - Learning asking for the list - that meets a tampered list,
    a signature of another list, an older list than the one kept, a 404, a
    500 or rubbish hands over the list kept and leaves the thread working:
    the next download still runs (checker's 1, 2026-11-14) - with why it
    wasn't read: a 404 as none published (330's addendum)."""
    seen = Seen()
    listed: list[tuple[object, Problem | None]] = []
    got = deliveries(
        server, tmp_path, seen, on_listed=lambda o, p: listed.append((o, p))
    )
    got.refresh()  # the good list first: kept, serial 2
    until_true(lambda: len(listed) == 1)
    signature, data = served_list(server)
    if fault == "tampered":
        server.faults.swap[LIST] = signed_list_file(signature, data + b" ")
    elif fault == "mismatched":  # a new signature beside the old list
        other = data.replace(b'"serial": 2', b'"serial": 3')
        server.faults.swap[LIST] = signed_list_file(
            split_signed_list(resigned(other))[0], data
        )
    elif fault == "older":
        server.faults.swap[LIST] = resigned(
            data.replace(b'"serial": 2', b'"serial": 1')
        )
    elif isinstance(fault, int):
        server.faults.status[LIST] = fault
    else:
        server.faults.swap[LIST] = b"not even a list"
    got.refresh()
    until_true(lambda: len(listed) == 2)
    assert listed[0][1] is None  # read
    assert listed[1][0] == listed[0][0]  # the list kept, handed over again
    why = {404: Problem.NOT_OFFERED, 500: Problem.SERVER}.get(fault)  # type: ignore[call-overload]
    assert listed[1][1] is not None and (why is None or listed[1][1] is why)
    server.faults.swap.pop(LIST, None)
    server.faults.status.pop(LIST, None)
    got.want("ru", "en")
    seen.wait()
    assert seen.installed  # the thread lived on


def test_no_list_published_yet_is_said_calmly(server: StandIn, tmp_path: Path) -> None:
    """A 404 for the list - before the first upload, or an old app after a
    new list format - is "not ready yet", with Retry; not a server error
    tried six times (checker's 7)."""
    server.faults.status[LIST] = 404
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    seen.wait()
    assert seen.last.problem is Problem.NOT_OFFERED and seen.last.stopped
    assert seen.last.tries == 1


def test_a_newer_pack_on_this_pc_is_never_replaced_by_an_older(
    server: StandIn, tmp_path: Path
) -> None:
    """Whatever a list says - an old one served to a PC that never read the
    newer - a pack on this PC is never replaced by an older version
    (checker's 2)."""
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info

    folder = tmp_path / "packs"
    newer = tiny_pack(folder)
    add_info(newer, {"pack_version": "2027.1.1"})
    seen = Seen()
    deliveries(server, tmp_path, seen).want("ru", "en")
    until_true(lambda: any(p.step is Step.DONE for p in seen.progress))
    assert not seen.installed
    assert not any(path == FILE for path, _, _ in server.requests)
    assert newer.is_file()


def test_an_unexpected_failure_is_logged_by_its_class_never_its_message() -> None:
    from polyglotic_desktop.adapters.pack_downloads import failure_of

    error = OSError(13, "Access is denied", "C:\\Users\\someone\\AppData\\x")
    assert failure_of(error) == "PermissionError (errno 13)"
    assert failure_of(ValueError("C:\\Users\\someone")) == "ValueError"


def until_true(done: Callable[[], bool], seconds: float = 20.0) -> None:
    end = time.monotonic() + seconds
    while not done():
        assert time.monotonic() < end, "never happened"
        time.sleep(0.02)
