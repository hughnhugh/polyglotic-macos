"""The settings file: kept whole, read back, and a missing or broken file
gives the defaults rather than an error; written on the store's own thread,
never waited for from the interface (polyglotic-hq project 136)."""

import json
import logging
import stat
import threading
from pathlib import Path

import pytest
from tests.stopped_clock import AFTER_MIDNIGHT_IN_MELBOURNE, stopped_at

from polyglotic_desktop.adapters import json_settings
from polyglotic_desktop.adapters.json_settings import JsonSettingsStore


def test_settings_are_kept_and_read_back(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "Polyglotic" / "settings.json")
    store.save({"targets": ["en"], "text_scale": 1.2, "spoken": None})
    store.flush()
    assert JsonSettingsStore(store.path).load() == {
        "targets": ["en"],
        "text_scale": 1.2,
        "spoken": None,
    }
    store.save({"targets": ["zh"]})
    assert store.load() == {"targets": ["zh"]}
    store.close()
    assert not (tmp_path / "Polyglotic" / "settings.json.tmp").exists()


def test_no_file_or_a_broken_one_gives_no_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert JsonSettingsStore(path).load() == {}
    path.write_text("{not json", encoding="utf-8")
    assert JsonSettingsStore(path).load() == {}
    path.write_text("[1, 2]", encoding="utf-8")
    assert JsonSettingsStore(path).load() == {}


def test_a_broken_file_is_set_aside_and_said_so_not_written_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt settings file reset everything without a word and was then
    overwritten (polyglotic-hq 133, item 10). Now it's kept beside the
    settings, with the time, and `set_aside` names it for the interface."""
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    # the clock stopped: a "today" read after the name was made was the next
    # day when the PC's midnight fell between (polyglotic-hq 344)
    now = AFTER_MIDNIGHT_IN_MELBOURNE
    monkeypatch.setattr(json_settings, "datetime", stopped_at(now))
    store = JsonSettingsStore(path)
    assert store.load() == {}
    aside = store.set_aside
    assert aside is not None and aside.parent == tmp_path
    assert aside.name.startswith("settings.unreadable-") and aside.suffix == ".json"
    # named in this PC's time, with its offset - not UTC's, which Home's
    # banner showed as yesterday in Australia (polyglotic-hq 184, 203)
    here = now.astimezone()  # this PC's time and offset
    assert aside.stem == f"settings.unreadable-{here:%Y%m%dT%H%M%S%z}"
    assert aside.read_text(encoding="utf-8") == "{not json"
    assert not path.exists()
    store.save({"theme": "ink"})
    store.close()
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "ink"}
    assert aside.read_text(encoding="utf-8") == "{not json"  # still there
    assert JsonSettingsStore(tmp_path / "none.json").set_aside is None


def test_a_file_unreadable_for_a_moment_gives_what_was_last_read_or_saved(
    tmp_path: Path,
) -> None:
    """Several parts of the app write the file, each re-reading it first:
    a moment when it can't be read must not hand one of them an older
    copy of another's keys (project 128, 2026-11-07)."""
    path = tmp_path / "settings.json"
    store = JsonSettingsStore(path)
    store.save({"targets": ["zh"], "caption_windows": {"last": {"text_size": 1.2}}})
    store.flush()
    path.write_text("{not json", encoding="utf-8")  # half-written by something else
    assert store.load() == {
        "targets": ["zh"],
        "caption_windows": {"last": {"text_size": 1.2}},
    }
    path.unlink()  # gone for a moment
    assert store.load()["targets"] == ["zh"]
    path.write_text('{"targets": ["en"]}', encoding="utf-8")
    assert store.load() == {"targets": ["en"]}  # readable again: the file wins
    path.write_text("{not json", encoding="utf-8")
    assert store.load() == {"targets": ["en"]}
    assert JsonSettingsStore(path).load() == {}  # nothing known yet: the defaults


@pytest.mark.windows_only  # Windows' read-only files
def test_a_file_that_cant_be_written_keeps_the_settings_until_it_can(
    tmp_path: Path,
) -> None:
    """A read-only file (or one another program holds): saving isn't an
    error - every change was an uncaught one, and a crash report next time
    (polyglotic-hq 133). The settings are kept and read back as saved, so
    every writer builds on them, and the next save that works writes them."""
    path = tmp_path / "settings.json"
    store = JsonSettingsStore(path)
    store.save({"theme": "ink"})
    store.flush()
    path.chmod(stat.S_IREAD)
    try:
        store.save({"theme": "glaze", "caption_windows": {"last": {}}})
        store.flush()
        assert store.load() == {"theme": "glaze", "caption_windows": {"last": {}}}
        assert JsonSettingsStore(path).load() == {"theme": "ink"}  # the file as it was
        assert not (tmp_path / "settings.json.tmp").exists()
    finally:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
    store.save({**store.load(), "locked": True})
    store.close()
    assert JsonSettingsStore(path).load() == {
        "theme": "glaze",
        "caption_windows": {"last": {}},
        "locked": True,
    }


def test_a_value_that_isnt_json_fails_its_save_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug hands `save` a value JSON can't hold: that save fails, said
    by its type only, and the file stays as it was - but the next save
    still writes and `close` still ends (polyglotic-hq 142, Low 3: the
    error stuck every later save in memory and broke quit)."""
    path = tmp_path / "settings.json"
    store = JsonSettingsStore(path)
    store.save({"theme": "ink"})
    store.flush()
    with caplog.at_level(logging.WARNING):
        store.save({"theme": "glaze", "when": object()})
        store.flush()
    assert "settings not saved (TypeError)" in caplog.text
    assert JsonSettingsStore(path).load() == {"theme": "ink"}
    assert not (tmp_path / "settings.json.tmp").exists()
    store.save({"theme": "margin"})
    store.close()
    assert JsonSettingsStore(path).load() == {"theme": "margin"}


def test_saves_are_written_on_the_stores_own_thread_and_finished_at_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every click on a setting read and wrote the file on the interface
    thread (polyglotic-hq 133: 90-126 ms a time). The values are kept at
    once and written off it; `load` meanwhile answers the newest; `close`
    waits for the write, so nothing saved at quit is lost."""
    path = tmp_path / "settings.json"
    store = JsonSettingsStore(path)
    writers: list[int] = []
    real_write = store._write

    def write(values: dict[str, object]) -> None:
        writers.append(threading.get_ident())
        real_write(values)

    monkeypatch.setattr(store, "_write", write)
    store.save({"theme": "ink"})
    store.save({"theme": "glaze"})  # before the first write ran, or not
    assert store.load() == {"theme": "glaze"}  # the newest, whatever's on disk
    store.close()
    assert writers and all(w != threading.get_ident() for w in writers)
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "glaze"}
    store.save({"theme": "margin"})  # after close: written here and now
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "margin"}


def test_load_reads_the_file_only_when_another_program_changed_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "settings.json"
    store = JsonSettingsStore(path)
    store.save({"theme": "ink"})
    store.flush()
    reads: list[str] = []
    real_read = store._read

    def read(known: dict[str, object] | None) -> dict[str, object]:
        reads.append("read")
        return real_read(known)

    monkeypatch.setattr(store, "_read", read)
    assert store.load() == {"theme": "ink"} and reads == []  # unchanged: from memory
    path.write_text(json.dumps({"theme": "glaze", "n": 1}), encoding="utf-8")
    assert store.load() == {"theme": "glaze", "n": 1} and reads == ["read"]
    assert store.load() == {"theme": "glaze", "n": 1} and reads == ["read"]
    store.close()
