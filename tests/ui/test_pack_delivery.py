"""Dictionary packs in the running app (decision 0122): a download asked on
Learning reaches the lookups without a restart, a newer version swaps in
while its language is open, Home says once when the learner is elsewhere,
removing closes and deletes it, and packs outlive an update of the app."""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.packs_server import StandIn
from tests.packs_storage import PRIVATE, PUBLIC, publish, tiny_pack
from tools.package import publish_packs

from polyglotic_desktop import main
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.pack_download import Problem
from polyglotic_desktop.core.lexicon.packs import FROM_SOURCE
from polyglotic_desktop.ui_next.pack_row import megabytes


def until(done: Callable[[], bool], seconds: float = 20.0) -> None:
    end = time.monotonic() + seconds
    while not done():
        assert time.monotonic() < end, "never happened"
        QTest.qWait(20)


@pytest.fixture
def server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
) -> Iterator[StandIn]:
    # the deliveries' own account, shown with a failure: GitHub's Windows
    # machine once waited 20 s for a 1 kB pack and said nothing of why - a
    # failed try waits 5 s, then 15, for the next (polyglotic-hq 578)
    caplog.set_level(logging.INFO, logger="polyglotic_desktop")
    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built) == 0
    with StandIn(out) as stand_in:
        yield stand_in


def delivery(
    server: StandIn, folder: Path, basic: dict[str, BasicDictionary]
) -> main.PackDelivery:
    packs = main.PackDelivery(
        folder,
        basic,
        "en",
        main.pack_reader(FROM_SOURCE),
        server.base,
        (PUBLIC,),
    )
    packs.start()
    return packs


def test_a_download_asked_on_learning_reaches_the_lookups_at_once(
    server: StandIn, tmp_path: Path
) -> None:
    basic: dict[str, BasicDictionary] = {}
    packs = delivery(server, tmp_path / "packs", basic)
    notices: list[str] = []
    packs.notice.connect(notices.append)
    lines: list[str] = []
    packs.line_changed.connect(lines.append)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    assert [e.headword for e in basic["ru"].lookup("дом")] == ["дом"]
    line = packs.line("ru")
    assert line.installed_version == "2026.11.14" and line.progress is None
    assert lines and set(lines) == {"ru"}
    assert notices == [
        "The Russian dictionary is ready: look up words in Russian captions."
    ]
    assert [p.code for p in packs.installed_lines()] == ["ru"]
    packs.close()


def test_no_notice_while_the_learner_is_on_learning(
    server: StandIn, tmp_path: Path
) -> None:
    basic: dict[str, BasicDictionary] = {}
    packs = delivery(server, tmp_path / "packs", basic)
    packs.on_learning = lambda: True
    notices: list[str] = []
    packs.notice.connect(notices.append)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    assert notices == []
    packs.close()


def test_a_failure_is_said_on_home_once(server: StandIn, tmp_path: Path) -> None:
    server.faults.status["packs/files/wiktru-en-2026.11.14.sqlite.gz"] = 404
    packs = delivery(server, tmp_path / "packs", {})
    assert packs.deliveries is not None
    notices: list[str] = []
    packs.notice.connect(notices.append)
    packs.asked("ko", "download")  # no Korean pack: stops at once
    until(lambda: bool(notices))
    progress = packs.line("ko").progress
    assert progress is not None and progress.problem is Problem.NOT_OFFERED
    assert notices == ["The Korean dictionary couldn't be downloaded: see Learning."]
    packs.close()


def test_a_language_the_list_has_no_pack_for_is_said_to_have_none(
    server: StandIn, tmp_path: Path
) -> None:
    """329's QA (K11): from the list the app holds, the one a download is
    offered from - none held yet, it can't be told (330)."""
    packs = delivery(server, tmp_path / "packs", {})
    assert not packs.line("ko").not_offered  # no list held yet
    packs.wanted_list(["ko"])
    until(lambda: packs.offers is not None)
    assert packs.line("ko").not_offered  # the stand-in has Russian's only
    russian = packs.line("ru")
    assert not russian.not_offered and russian.size > 0
    packs.close()


def test_a_list_that_cant_be_read_is_said_not_checked_for_good(
    tmp_path: Path, qapp: QApplication
) -> None:
    packs = main.PackDelivery(
        tmp_path / "packs",
        {},
        "en",
        main.pack_reader(FROM_SOURCE),
        "http://127.0.0.1:9/",  # nothing answers
        (PUBLIC,),
    )
    packs.start()
    assert packs.line("ru").size == 0 and not packs.line("ru").unlisted
    packs.wanted_list(["ru"])
    until(lambda: packs.line("ru").unlisted)
    assert not packs.line("ru").not_offered  # couldn't be read: no claim (330)
    packs.close()


def test_none_published_is_no_dictionary_yet_and_retry_finds_one_published_since(
    server: StandIn, tmp_path: Path
) -> None:
    """The release may come before any list is published (330's addendum):
    the storage's 404 for the list says none can be had - for every basic
    language, not "checking" and not a promise - and Retry finds one
    published since."""
    server.faults.status["packs/v1/list.signed"] = 404
    basic: dict[str, BasicDictionary] = {}
    packs = delivery(server, tmp_path / "packs", basic)
    packs.wanted_list(["ru"])
    until(lambda: packs.list_problem is Problem.NOT_OFFERED)
    for code in ("ru", "vi"):
        line = packs.line(code)
        assert line.not_offered and not line.unlisted and line.size == 0
    server.faults.status.pop("packs/v1/list.signed")  # published since
    packs.asked("ru", "retry")
    until(lambda: "ru" in basic)
    packs.close()


def test_a_newer_version_swaps_in_while_its_language_is_open(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    basic: dict[str, BasicDictionary] = {}
    folder = tmp_path / "packs"
    packs = delivery(server, folder, basic)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    first = basic["ru"]
    before = [e.entry_id for e in first.lookup("дом")]
    old_file = folder / "wiktru-en-2026.11.14.sqlite"
    # a newer version published (the same words, more of them)
    built = tmp_path / "built2"
    tiny_pack(built, padding=10)
    tiny_pack(built, meanings="zh", padding=10)
    newer = tmp_path / "bucket2"
    previous = server.folder / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, newer, built, "2026.12.1", previous) == 0
    server.folder = newer
    packs.check_updates()  # quiet: not metered here
    until(lambda: basic["ru"] is not first)
    assert [e.headword for e in basic["ru"].lookup("дом")] == ["дом"]  # answers now
    # the same entry ID in the new version: statuses and saved words, kept by
    # ID, carry over (decision 0089; tests/tools/test_packs.py and
    # tests/learning/test_anki_export.py prove it for real builds)
    assert [e.entry_id for e in basic["ru"].lookup("дом")] == before
    assert packs.line("ru").installed_version == "2026.12.1"
    until(lambda: not old_file.exists(), seconds=10)  # closed, then deleted
    assert (folder / "wiktru-en-2026.12.1.sqlite").is_file()
    packs.close()


def test_removing_closes_and_deletes_it(server: StandIn, tmp_path: Path) -> None:
    basic: dict[str, BasicDictionary] = {}
    folder = tmp_path / "packs"
    packs = delivery(server, folder, basic)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    changed: list[bool] = []
    packs.changed.connect(lambda: changed.append(True))
    packs.asked("ru", "remove")
    assert "ru" not in basic and not packs.installed_lines() and changed
    assert not (folder / "wiktru-en-2026.11.14.sqlite").exists()
    packs.close()


def test_packs_outlive_an_update_of_the_app(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Velopack replaces the whole install folder at an update; an installed
    copy keeps packs with the learner's data (decision 0089), so the next
    start opens what the last one downloaded."""
    monkeypatch.setattr(main, "installed", lambda: True)
    data = tmp_path / "Roaming" / "Polyglotic"
    install = tmp_path / "Local" / "Polyglotic" / "current"
    (install / "dictionaries").mkdir(parents=True)
    folder = main.packs_folder(install / "dictionaries", data)
    assert data in folder.parents
    basic: dict[str, BasicDictionary] = {}
    packs = delivery(server, folder, basic)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    packs.close()
    for path in sorted(install.rglob("*"), reverse=True):  # the update
        path.rmdir() if path.is_dir() else path.unlink()
    install.rmdir()
    (install / "dictionaries").mkdir(parents=True)
    again: dict[str, BasicDictionary] = {}
    started = delivery(server, main.packs_folder(install / "dictionaries", data), again)
    assert sorted(again) == ["ru"]
    started.close()


def test_the_installers_packs_are_read_first_and_never_removed(
    server: StandIn, tmp_path: Path
) -> None:
    """A build made with `--packs ru` (decision 0124): Russian opens from the
    app's own folder, offline too; no download is offered or made; Learning
    lists only what was downloaded (the installer's can't be removed)."""
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info

    installer = tmp_path / "app" / "dictionaries" / "packs"
    pack = tiny_pack(installer)
    add_info(pack, {"pack_version": "2026.11.14"})
    basic: dict[str, BasicDictionary] = {}
    packs = main.PackDelivery(
        tmp_path / "data",
        basic,
        "en",
        main.pack_reader(FROM_SOURCE),
        "http://127.0.0.1:9/",  # offline
        (PUBLIC,),
        also=(installer,),
    )
    packs.start()
    assert [e.headword for e in basic["ru"].lookup("дом")] == ["дом"]
    assert packs.line("ru").installed_version == "2026.11.14"
    assert packs.installed_lines() == []
    packs.asked("ru", "remove")
    assert pack.is_file() and "ru" in basic  # the installer's own stays
    packs.close()


def test_check_install_opens_the_installers_packs(tmp_path: Path) -> None:
    """A `--packs ru` build's own check: each pack it carries opened and a
    word looked up (decision 0124)."""
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info

    folder = tmp_path / "packs"
    pack = tiny_pack(folder)
    add_info(pack, {"pack_version": "0.1.5"})
    assert main.try_the_installers_packs(folder) == {"ru/en": "0.1.5: руку -> ?"}
    assert main.try_the_installers_packs(tmp_path / "none") == {}


def test_learning_asks_for_the_list_once_in_a_while(
    server: StandIn, tmp_path: Path
) -> None:
    """Learning is shown again at every setting it follows; the list is
    asked for once, then not again for ten minutes (a download still asks)."""
    packs = delivery(server, tmp_path / "packs", {})
    packs.wanted_list(["ru"])
    until(lambda: packs.offers is not None)
    for _ in range(3):
        packs.wanted_list(["ru"])
    QTest.qWait(300)
    listed = [p for p, _, _ in server.requests if p == "packs/v1/list.signed"]
    assert len(listed) == 1
    packs.close()


def test_a_downloaded_packs_recordings_reach_the_speaker_and_go_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    """The pack's recorded words come down after it and are said without a
    restart; Learning says they're there, with who said them; removing the
    pack deletes them with it (decisions 0133, 0192)."""
    from tests.test_pack_riders import OGG_HEAD, built_with_audio, published

    from polyglotic_desktop.platform.recorded_voices import Recordings

    out = tmp_path / "bucket"
    built = built_with_audio(tmp_path / "built")
    assert publish(monkeypatch, out, built) == 0  # the packs alone, first
    recordings = Recordings()
    basic: dict[str, BasicDictionary] = {}
    folder = tmp_path / "packs"
    with StandIn(out) as stand_in:
        packs = main.PackDelivery(
            folder,
            basic,
            "en",
            main.pack_reader(FROM_SOURCE),
            stand_in.base,
            (PUBLIC,),
            recordings=recordings,
        )
        packs.start()
        packs.asked("ru", "download")
        until(lambda: "ru" in basic)
        assert recordings.voices() == ()  # this list has no riders
        assert "recorded" not in main_line_text(packs)
        packs.close()
    # then its recordings, beside the pack already published
    with_audio = tmp_path / "bucket-audio"
    extra = ("--audio", str(built), "--riders-only", "--version", "2026.11.14")
    assert published(monkeypatch, with_audio, *extra, previous=out / LIST) == 0
    shutil.copytree(
        out / "packs" / "files", with_audio / "packs" / "files", dirs_exist_ok=True
    )
    with StandIn(with_audio) as stand_in:
        packs = main.PackDelivery(
            folder,
            basic,
            "en",
            main.pack_reader(FROM_SOURCE),
            stand_in.base,
            (PUBLIC,),
            recordings=recordings,
        )
        packs.start()  # the pack is here: the daily check brings its riders
        assert "ru" in packs.here and recordings.voices() == ()
        packs.check_updates()
        until(lambda: bool(recordings.voices()))
        (voice,) = recordings.voices()
        assert voice.language == "ru-RU"
        assert recordings.clip(voice, "дом") == OGG_HEAD + b"OggS-the-word"
        assert not recordings.has(voice, "говорить")
        line = packs.line("ru")
        assert line.recorded_size > 0 and "rf_test" in line.credits
        assert "CC BY 4.0" in line.credits
        assert "recorded" in main_line_text(packs)
        (here,) = packs.installed_lines()  # removing it frees both
        assert here.size == line.installed_size + line.recorded_size
        assert len(list(folder.glob("wiktru-*"))) == 2  # the pack, the audio
        # read again (as when a newer file arrives): the one it replaces is
        # closed, though only its connection is held here - a timer's bound
        # method dropped with its object never ran (441's lesson, 443)
        db = packs._recorded["ru"]._db
        assert db is not None
        packs.record("ru")
        QTest.qWait(main.PACK_OLD_CLOSED_AFTER_MS + 900)
        with pytest.raises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")
        assert recordings.clip(voice, "дом") == OGG_HEAD + b"OggS-the-word"
        packs.asked("ru", "remove")
        assert "ru" not in basic and recordings.voices() == ()
        assert not list(folder.glob("wiktru-*"))
        packs.close()


@pytest.mark.parametrize(
    ("version", "recorded"), [(FROM_SOURCE, True), ("0.1.7", True), ("0.1.6", False)]
)
def test_the_offer_names_the_recordings_size_before_the_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    version: str,
    recorded: bool,
) -> None:
    """DECISIONS #192 (B; polyglotic-hq 423): the recordings come by
    themselves after the dictionary, so Learning's offer says both sizes -
    only where the list has recordings this app takes (0.1.7 on: 0192)."""
    from tests.test_pack_riders import built_with_audio, published

    built = built_with_audio(tmp_path / "built")
    out = tmp_path / "bucket"
    no_list = tmp_path / "no-list.signed"
    no_list.write_bytes(
        publish_packs.sign_list(
            publish_packs.list_bytes([], 1), publish_packs.private_key_from(PRIVATE)
        )
    )
    extra = ("--packs", str(built), "--audio", str(built), "--version", "2026.11.14")
    assert published(monkeypatch, out, *extra, previous=no_list) == 0
    with StandIn(out) as stand_in:
        packs = main.PackDelivery(
            tmp_path / "packs",
            {},
            "en",
            main.pack_reader(version),
            stand_in.base,
            (PUBLIC,),
        )
        packs.start()
        packs.wanted_list(["ru"])
        until(lambda: packs.offers is not None)
        line = packs.line("ru")
        (rider,) = next(o for o in packs.offers or () if o.meanings == "en").riders
        assert line.size > 0
        assert line.recorded_offered == (rider.gz_size if recorded else 0)
        said = main_line_text(packs)
        if recorded:
            assert said == (
                f"Its dictionary: {megabytes(line.size)} MB to download, then "
                f"{megabytes(rider.gz_size)} MB of recorded words."
            )
        else:
            assert said == f"Its dictionary: {megabytes(line.size)} MB to download."
        packs.close()


LIST = "packs/v1/list.signed"


def main_line_text(packs: main.PackDelivery) -> str:
    from polyglotic_desktop.ui_next.pack_row import shown

    return shown("ru", packs.line("ru"))[0]


def _german_published_since(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newer list on the stand-in, with a German pack the kept one hasn't."""
    built = tmp_path / "built-de"
    tiny_pack(built, language="de", dictionary="wiktde")
    newer = tmp_path / "bucket-de"
    previous = server.folder / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, newer, built, "2026.11.16", previous, "de") == 0
    server.folder = newer


def _kept_list(server: StandIn, folder: Path) -> None:
    """An earlier run's list (Russian's only), kept in `folder`."""
    earlier = delivery(server, folder, {})
    earlier.wanted_list(["ru"])
    until(lambda: earlier.offers is not None)
    earlier.close()
    assert earlier.deliveries is not None
    earlier.deliveries.join(5)


def test_an_old_list_is_checked_again_as_learning_opens(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """425 (preview 2): started with the list an earlier run kept, Learning
    said "No dictionary yet" for a language published since, for two
    minutes, until the update check read the list. Opening Learning checks
    the old list at once, says it's checking meanwhile, and then offers the
    new language; opened again with the list just read, it isn't asked for."""
    from polyglotic_desktop.ui_next.views.learning import PackKnown, pack_known

    folder = tmp_path / "packs"
    _kept_list(server, folder)
    _german_published_since(server, tmp_path, monkeypatch)
    packs = delivery(server, folder, {})
    assert packs.offers is not None  # the kept list: no German in it
    assert packs.line("de").not_offered  # what it says until Learning opens
    changes: list[None] = []
    packs.changed.connect(lambda: changes.append(None))
    packs.learning_opened()
    german = packs.line("de")
    assert german.checking and not german.not_offered and not german.unlisted
    assert pack_known(german) is PackKnown.CHECKING
    assert changes  # Learning says it's checking
    until(lambda: packs.line("de").size > 0)  # the new language is offered
    german = packs.line("de")
    assert not german.checking and pack_known(german) is PackKnown.OFFERED
    asked = len([p for p, _, _ in server.requests if p == "packs/v1/list.signed"])
    packs.learning_opened()  # read just now: not again
    QTest.qWait(300)
    listed = [p for p, _, _ in server.requests if p == "packs/v1/list.signed"]
    assert len(listed) == asked
    packs.close()


def test_an_old_list_that_cant_be_checked_says_what_it_did(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """425: a check of the old list that fails says what it said before -
    the kept list's answer - not "checking" for good."""
    folder = tmp_path / "packs"
    _kept_list(server, folder)
    server.faults.status["packs/v1/list.signed"] = 500
    packs = delivery(server, folder, {})
    packs.learning_opened()
    assert packs.line("de").checking
    until(lambda: not packs.list_checking)
    german = packs.line("de")
    assert german.not_offered and not german.checking
    assert packs.list_problem is Problem.SERVER
    assert packs.line("ru").size > 0  # the kept list's offer stands
    packs.close()


def test_a_list_read_over_an_hour_ago_is_checked_again(
    server: StandIn, tmp_path: Path
) -> None:
    """425: read in this run, but over an hour ago - checked again as
    Learning opens; read within the hour, not."""
    packs = delivery(server, tmp_path / "packs", {})
    packs.learning_opened()  # none kept: read now
    until(lambda: packs.offers is not None and not packs.list_checking)
    asked = len([p for p, _, _ in server.requests if p == "packs/v1/list.signed"])
    packs.learning_opened()
    assert not packs.list_checking  # within the hour
    assert packs._list_read is not None
    packs._list_read -= main.LIST_OLD_AFTER_SEC + 1  # an hour on
    packs._list_asked -= main.LIST_OLD_AFTER_SEC + 1
    packs.learning_opened()
    assert packs.list_checking
    until(lambda: not packs.list_checking)
    listed = [p for p, _, _ in server.requests if p == "packs/v1/list.signed"]
    assert len(listed) == asked + 1
    packs.close()


def test_learning_coming_into_view_asks_for_the_old_list_to_be_checked(
    tmp_path: Path, qapp: QApplication
) -> None:
    """425: the main window's Learning page, opened, is what checks the list
    (`PackDelivery.learning_opened`)."""
    from tests.ui.fakes import Built

    built = Built()
    try:
        packs = main.PackDelivery(
            tmp_path / "packs", {}, "en", main.pack_reader(FROM_SOURCE)
        )
        opened: list[None] = []
        packs.learning_opened = lambda: opened.append(None)  # type: ignore[method-assign]
        built.hub.use_packs(packs)
        built.hub.window.show()
        built.hub.window.go_to("home")
        qapp.processEvents()
        assert opened == []
        built.hub.window.go_to("learning")
        qapp.processEvents()
        assert opened == [None]
    finally:
        built.close()


def test_a_built_in_dictionarys_recordings_come_for_its_learner_and_are_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    """CC-CEDICT is built into the app: its recorded words come as riders of
    their own (decision 0197) - only while Chinese is learned, at the daily
    check - and are said from the next click, without a restart; Chinese's
    card says they're there, their size and who said them. One the
    installer brought is used as it is."""
    from tests.test_pack_riders import (
        CEDICT_VERSION,
        OGG_HEAD,
        built_with_audio,
        published_built_in,
        recorded_chinese,
    )

    from polyglotic_desktop.platform.recorded_voices import Recordings

    packs_only = tmp_path / "bucket"
    built = built_with_audio(tmp_path / "built")
    assert publish(monkeypatch, packs_only, built) == 0
    out = tmp_path / "bucket-cedict"
    audio = recorded_chinese(tmp_path / "zh-audio")
    extra = ("--version", CEDICT_VERSION)
    assert published_built_in(monkeypatch, out, audio, packs_only / LIST, *extra) == 0
    learned: list[str] = ["es"]
    recordings = Recordings()
    folder = tmp_path / "packs"
    installer = tmp_path / "dictionaries"
    installer.mkdir()
    with StandIn(out) as stand_in:

        def chinese_delivery() -> main.PackDelivery:
            packs = main.PackDelivery(
                folder,
                {},
                "en",
                main.pack_reader(FROM_SOURCE),
                stand_in.base,
                (PUBLIC,),
                recordings=recordings,
                built_in=main.BUILT_IN_RIDERS,
                built_in_folder=installer,
                learning=lambda: tuple(learned),
            )
            packs.start()
            return packs

        packs = chinese_delivery()
        packs.check_updates()  # Chinese isn't learned: nothing comes
        QTest.qWait(300)
        packs.close()
        assert not any(".audio" in p for p, _, _ in stand_in.requests)
        assert recordings.voices() == () and packs.recorded_line("zh") == (0, "")

        learned.append("zh")
        packs = chinese_delivery()
        packs.check_updates()
        until(lambda: bool(recordings.voices()))
        (voice,) = recordings.voices()
        assert voice.language == "zh-CN"
        assert recordings.clip(voice, "我们") == OGG_HEAD + b"OggS-women"
        size, credits = packs.recorded_line("zh")
        assert size > 0 and "Chatterbox" in credits and "MIT" in credits
        assert [p.name for p in folder.glob("cedict-*")] == [
            f"cedict-{CEDICT_VERSION}.audio"
        ]
        assert packs.installed_lines() == []  # not a pack: nothing to remove
        packs.close()

    # the installer's own, with nothing downloaded and no list
    for path in folder.glob("cedict-*"):
        path.unlink()
    recorded_chinese(installer)
    others = Recordings()
    packs = main.PackDelivery(
        folder,
        {},
        "en",
        main.pack_reader(FROM_SOURCE),
        "http://127.0.0.1:9/",
        (PUBLIC,),
        recordings=others,
        built_in=main.BUILT_IN_RIDERS,
        built_in_folder=installer,
    )
    packs.start()
    (voice,) = others.voices()
    assert others.has(voice, "我们") and packs.recorded_line("zh")[0] > 0


def turns(done: Callable[[], bool], seconds: float = 20.0) -> bool:
    """The event loop's turns, with the interpreter let go between them -
    `QTest.qWait` keeps it, and a thread running Python (a pack's split
    reading its data) waits - until `done` or `seconds` have passed."""
    end = time.monotonic() + seconds
    while not done() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    return done()


def test_a_pack_is_ready_once_its_word_split_has_read_its_data(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its learner opens only then (polyglotic-hq 436): a pack opens for
    lookups at once, and is `ready` - `readied` said once - when its word
    split's first read, on a thread of its own, is done; removed, it isn't."""
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info

    folder = tmp_path / "packs"
    add_info(tiny_pack(folder, "es", "wiktes"), {"pack_version": "2026.11.14"})
    read = threading.Event()
    words = BasicDictionary.words

    def held(self: BasicDictionary, text: str) -> object:
        read.wait(10)  # the split's first read, held until the test says
        return words(self, text)

    monkeypatch.setattr(BasicDictionary, "words", held)
    basic: dict[str, BasicDictionary] = {}
    packs = main.PackDelivery(
        folder,
        basic,
        "en",
        main.pack_reader(FROM_SOURCE),
        "http://127.0.0.1:9/",  # offline
        (PUBLIC,),
    )
    readied: list[bool] = []
    packs.readied.connect(lambda: readied.append(True))
    packs.start()
    assert "es" in basic  # looked up at once
    turns(lambda: False, 0.3)  # its read begun, and held
    assert packs.ready == set() and readied == []  # its split still reading

    read.set()
    assert turns(lambda: bool(readied)), "its split's read never said so"
    assert packs.ready == {"es"} and readied == [True]
    packs.asked("es", "remove")
    assert packs.ready == set()


def test_the_replaced_file_is_closed_and_deleted_when_nothing_else_holds_it(
    server: StandIn, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 441: the swap closes the file it replaces even when
    nothing else holds it. PySide drops a timer's bound method once its
    object has no other holder, so `singleShot(ms, old.close)` never ran:
    the old file's connections stayed open (a connection is freed only by
    a later garbage collection) and Windows couldn't delete it. Unlike the
    test above, nothing here holds the old dictionary - only its
    connections, to see that they were closed (on Linux an open file can
    be deleted, so the deletion alone proves nothing there)."""
    basic: dict[str, BasicDictionary] = {}
    folder = tmp_path / "packs"
    packs = delivery(server, folder, basic)
    packs.asked("ru", "download")
    until(lambda: "ru" in basic)
    basic["ru"].lookup("дом")  # a connection of this thread's too
    connections = list(packs._files["ru"]._opened)
    assert connections
    old_file = folder / "wiktru-en-2026.11.14.sqlite"
    built = tmp_path / "built2"
    tiny_pack(built, padding=10)
    tiny_pack(built, meanings="zh", padding=10)
    newer = tmp_path / "bucket2"
    previous = server.folder / "packs" / "v1" / "list.signed"
    assert publish(monkeypatch, newer, built, "2026.12.1", previous) == 0
    server.folder = newer
    packs.check_updates()
    until(lambda: packs.line("ru").installed_version == "2026.12.1")
    QTest.qWait(main.PACK_OLD_CLOSED_AFTER_MS + 900)
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):  # closed
            connection.execute("SELECT 1")
    assert not old_file.exists()
    packs.close()
