"""The Mac's app run from macOS's temporary copy - App Translocation - and
the offer to move it to Applications (polyglotic-hq 433, decision 0205).

The logic on any OS, with folders in a temporary one; macOS's own
translocation (a quarantined stand-in app, translocated by Security as an
opening would) on GitHub's Mac: `macos_only`."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.main import moved_to_applications, os_adapters
from polyglotic_desktop.platform.macos import translocation
from polyglotic_desktop.platform.macos.translocation import (
    MacTranslocation,
    MoveFailed,
    app_bundle,
    move_to_applications,
    path_says,
)
from polyglotic_desktop.ui import move_to_applications as offer_box
from polyglotic_desktop.ui.settings import Settings

COPY = (
    "/private/var/folders/x5/abc123/T/AppTranslocation/"
    "0F9B2A51-7C1E-4E0B-9D3A-1B2C3D4E5F60/d/Polyglotic.app"
)


def _app(folder: Path, name: str = "Polyglotic.app", mark: str = "new") -> Path:
    app = folder / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Polyglotic").write_text(mark, encoding="utf-8")
    return app


def _mark(app: Path) -> str:
    return (app / "Contents" / "MacOS" / "Polyglotic").read_text(encoding="utf-8")


# --- seeing it ----------------------------------------------------------------


def test_the_bundle_is_found_from_its_executable() -> None:
    assert app_bundle(COPY + "/Contents/MacOS/Polyglotic") == Path(COPY)
    assert app_bundle("/Applications/Polyglotic.app/Contents/MacOS/Polyglotic") == Path(
        "/Applications/Polyglotic.app"
    )
    assert app_bundle("/usr/bin/python3") is None  # from source: no bundle
    assert app_bundle("/tmp/Contents/MacOS/python3") is None


@pytest.mark.parametrize(
    ("path", "says"),
    [
        (COPY, True),
        (COPY.removeprefix("/private"), True),  # /var links to /private/var
        ("/Applications/Polyglotic.app", False),
        ("/Users/learner/Downloads/Polyglotic.app", False),
        ("/Users/learner/Applications/Polyglotic.app", False),
        ("/private/var/folders/x5/abc123/T/Polyglotic.app", False),
    ],
)
def test_the_temporary_copys_path_says_so(path: str, says: bool) -> None:
    assert path_says(Path(path)) is says


def test_security_is_asked_when_the_path_doesnt_say() -> None:
    asked: list[Path] = []

    def security(bundle: Path) -> bool:
        asked.append(bundle)
        return True

    assert translocation.translocated(Path(COPY), security)
    assert asked == []  # the path said so: no call
    odd = Path("/Volumes/Elsewhere/Polyglotic.app")
    assert translocation.translocated(odd, security) and asked == [odd]


def test_security_failing_reads_as_not_translocated() -> None:
    def broken(_: Path) -> bool:
        raise OSError("no Security here")

    assert not translocation.translocated(Path("/Applications/Polyglotic.app"), broken)


def test_from_source_it_isnt_translocated() -> None:
    assert not MacTranslocation(executable=sys.executable).translocated()


# --- the move -----------------------------------------------------------------


def test_it_moves_into_applications_and_the_attribute_comes_off(tmp_path: Path) -> None:
    downloads, applications = tmp_path / "Downloads", tmp_path / "Applications"
    downloads.mkdir()
    applications.mkdir()
    app = _app(downloads)
    cleared: list[Path] = []
    moved = move_to_applications(
        app, [applications], tmp_path / ".Trash", cleared.append
    )
    assert moved == applications / "Polyglotic.app"
    assert _mark(moved) == "new" and not app.exists()
    assert cleared == [moved]


def test_the_users_own_applications_when_the_first_cant_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    system, own = tmp_path / "Applications", tmp_path / "home" / "Applications"
    system.mkdir()
    (tmp_path / "home").mkdir()
    real_access = os.access
    monkeypatch.setattr(
        translocation.os,
        "access",
        lambda path, mode: False if Path(path) == system else real_access(path, mode),
    )
    moved = move_to_applications(
        _app(downloads), [system, own], tmp_path / ".Trash", print
    )
    assert moved == own / "Polyglotic.app"  # ~/Applications made for it
    assert not (system / "Polyglotic.app").exists()


def test_a_polyglotic_already_there_goes_to_the_bin(tmp_path: Path) -> None:
    downloads, applications, trash = (
        tmp_path / "Downloads",
        tmp_path / "Apps",
        tmp_path / "Bin",
    )
    downloads.mkdir()
    applications.mkdir()
    _app(applications, mark="old")
    trash.mkdir()
    _app(trash, mark="older")  # a name taken in the Bin too
    moved = move_to_applications(_app(downloads), [applications], trash, print)
    assert _mark(moved) == "new"
    kept = sorted(p.name for p in trash.iterdir())
    assert len(kept) == 2 and "Polyglotic.app" in kept
    assert {_mark(trash / name) for name in kept} == {"old", "older"}


def test_already_in_applications_only_the_attribute_comes_off(tmp_path: Path) -> None:
    applications = tmp_path / "Applications"
    applications.mkdir()
    app = _app(applications)
    cleared: list[Path] = []
    assert (
        move_to_applications(app, [applications], tmp_path / "Bin", cleared.append)
        == app
    )
    assert cleared == [app] and _mark(app) == "new"


def test_nowhere_to_move_it_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    app = _app(downloads)
    monkeypatch.setattr(translocation.os, "access", lambda path, mode: False)
    with pytest.raises(MoveFailed, match="can't be written"):
        move_to_applications(
            app, [tmp_path / "A", tmp_path / "B"], tmp_path / "Bin", print
        )
    assert _mark(app) == "new"  # left where it was


def test_the_real_app_is_moved_not_the_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    real = _app(home / "Downloads")
    monkeypatch.setattr(translocation, "original", lambda bundle: real)
    monkeypatch.setattr(translocation, "unquarantine", lambda app: None)
    monkeypatch.setattr(
        translocation.os, "access", lambda path, mode: "home" in str(path)
    )
    place = MacTranslocation(
        executable=COPY + "/Contents/MacOS/Polyglotic",
        home=home,
        applications=tmp_path / "Applications",  # never the PC's own
    )
    assert place.translocated()
    assert place.move() == home / "Applications" / "Polyglotic.app"


def test_without_the_real_apps_place_it_doesnt_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(translocation, "original", lambda bundle: None)
    place = MacTranslocation(
        executable=COPY + "/Contents/MacOS/Polyglotic", home=tmp_path
    )
    with pytest.raises(MoveFailed, match="really is"):
        place.move()


def test_a_failed_moves_reason_names_no_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason goes in the log, which a problem report can carry: the
    home folder (it names the user) is said as ~."""
    home = tmp_path / "learner"
    (home / "Downloads").mkdir(parents=True)
    real = _app(home / "Downloads")
    monkeypatch.setattr(translocation, "original", lambda bundle: real)
    monkeypatch.setattr(translocation.os, "access", lambda path, mode: False)
    place = MacTranslocation(
        executable=COPY + "/Contents/MacOS/Polyglotic",
        home=home,
        applications=tmp_path / "Applications",  # never the PC's own
    )
    with pytest.raises(MoveFailed) as failed:
        place.move()
    assert "~" in str(failed.value) and str(home) not in str(failed.value)


@pytest.mark.skipif(sys.platform != "win32", reason="the refusal is Windows'")
def test_reopening_refuses_to_run_on_windows() -> None:
    with pytest.raises(OSError, match="macOS"):
        translocation.reopen_after(os.getpid(), Path("Polyglotic.app"))


# --- the offer, once ---------------------------------------------------------


class FakePlace:
    def __init__(self, translocated: bool = True, moves_to: Path | None = None) -> None:
        self._translocated = translocated
        self.moves_to = moves_to
        self.reopened: list[Path] = []

    def translocated(self) -> bool:
        return self._translocated

    def move(self) -> Path:
        if self.moves_to is None:
            raise MoveFailed("can't be written")
        return self.moves_to

    def reopen(self, app: Path) -> None:
        self.reopened.append(app)


MOVED = Path("/Applications/Polyglotic.app")


def test_moved_it_opens_again_from_applications() -> None:
    store = MemorySettingsStore()
    place = FakePlace(moves_to=MOVED)
    assert moved_to_applications(place, Settings(store), offer=lambda p: p.move())
    assert place.reopened == [MOVED]
    assert store.values["applications_offered"] is True


def test_not_now_goes_on_and_isnt_asked_again() -> None:
    store = MemorySettingsStore()
    asked: list[object] = []

    def not_now(place: object) -> None:
        asked.append(place)

    place = FakePlace(moves_to=MOVED)
    assert not moved_to_applications(place, Settings(store), offer=not_now)
    assert not moved_to_applications(place, Settings(store), offer=not_now)
    assert len(asked) == 1 and place.reopened == []


@pytest.mark.parametrize("place", [None, FakePlace(translocated=False)])
def test_nothing_asked_where_it_isnt_translocated(place: FakePlace | None) -> None:
    store = MemorySettingsStore()

    def never(_: object) -> None:
        raise AssertionError("asked")

    assert not moved_to_applications(place, Settings(store), offer=never)
    assert "applications_offered" not in store.values


def test_windows_has_nothing_to_move() -> None:
    assert os_adapters("darwin").translocation is MacTranslocation
    if sys.platform == "win32":
        assert os_adapters("win32").translocation is None


def test_the_box_moves_only_on_move() -> None:
    told: list[object] = []
    place = FakePlace(moves_to=MOVED)
    assert (
        offer_box.offer(place, asking=lambda parent: True, telling=told.append) == MOVED
    )
    assert (
        offer_box.offer(place, asking=lambda parent: False, telling=told.append) is None
    )
    assert told == []


def test_a_failed_move_says_how_to_do_it_by_hand() -> None:
    told: list[object] = []
    failing = FakePlace(moves_to=None)
    assert (
        offer_box.offer(failing, asking=lambda parent: True, telling=told.append)
        is None
    )
    assert told == [None]
    assert "drag it into Applications in Finder" in offer_box.by_hand()
    assert "can't update itself" in offer_box.question()


# --- macOS itself -------------------------------------------------------------


@pytest.mark.macos_only
def test_on_a_mac_security_answers_and_the_move_clears_the_quarantine(
    tmp_path: Path,
) -> None:
    """macOS itself: Security's calls answer through these signatures - an
    ordinary app isn't translocated, and its original place is itself - and a
    quarantined app in the runner's own Downloads is moved to an
    Applications folder of the test's with the attribute off, by the
    system's own xattr."""
    applications = tmp_path / "Applications"
    applications.mkdir()
    own = Path.home() / "Downloads" / f"polyglotic-433-{os.getpid()}"
    try:
        own.mkdir(parents=True)
        app = _stand_in(own, "0083", signed=False)
        assert translocation.security_says(app) is False
        assert not translocation.translocated(app)
        assert translocation.original(app) in (None, app, app.resolve())
        moved = move_to_applications(
            app, [applications], tmp_path / ".Trash", translocation.unquarantine
        )
        assert moved == applications / "Polyglotic.app" and not app.exists()
        held = subprocess.run(
            ["/usr/bin/xattr", "-r", "-p", translocation.QUARANTINE, str(moved)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert held.stdout.strip() == "", held.stdout
    finally:
        shutil.rmtree(own, ignore_errors=True)


@pytest.mark.macos_only
def test_macos_translocates_a_quarantined_app_and_it_moves_out(tmp_path: Path) -> None:
    """A stand-in app, quarantined as a browser's download is, translocated
    by Security as an opening does: seen as translocated (path and
    Security), its real place found, moved, the attribute off.

    On GitHub's Mac (2026-11-17, run 43907575317) Security won't make the
    copy for a test: "Operation not permitted" with Safari's flags (0083,
    0081), and the app's own path back with 0001. Then this skips, saying
    so - the copy itself is unproven on a runner (polyglotic-hq 433)."""
    applications = tmp_path / "Applications"
    applications.mkdir()
    own = Path.home() / "Downloads" / f"polyglotic-433-{os.getpid()}"
    tries: list[str] = []
    try:
        for flags in ("0083", "0081", "0001", "0181"):
            shutil.rmtree(own, ignore_errors=True)
            own.mkdir(parents=True)
            app = _stand_in(own, flags, signed=False)
            try:
                copy = translocation.translocate(app)
            except OSError as problem:
                tries.append(f"{flags}: {problem}")
                continue
            if copy.resolve() == app.resolve():
                tries.append(f"{flags}: not translocated (its own path back)")
                continue
            _check_translocated_and_moved(copy, app, applications, tmp_path)
            return
        pytest.skip("Security made no translocated copy here: " + "; ".join(tries))
    finally:
        shutil.rmtree(own, ignore_errors=True)


def _stand_in(folder: Path, flags: str, signed: bool) -> Path:
    """A stand-in app in `folder`, quarantined as a download, ad hoc signed
    if `signed`."""
    app = _app(folder, mark="#!/bin/sh\necho stand-in\n")
    (app / "Contents" / "MacOS" / "Polyglotic").chmod(0o755)
    (app / "Contents" / "Info.plist").write_text(_PLIST, encoding="utf-8")
    if signed:
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(app)],
            capture_output=True,
            check=False,
        )
    value = f"{flags};{int(time.time()):x};Safari;"
    subprocess.run(
        ["/usr/bin/xattr", "-w", "-r", translocation.QUARANTINE, value, str(app)],
        check=True,
    )
    return app


def _check_translocated_and_moved(
    copy: Path, app: Path, applications: Path, tmp_path: Path
) -> None:
    print(f"translocated to {copy}")
    assert copy != app
    assert path_says(copy) and translocation.security_says(copy)
    assert translocation.translocated(copy)
    assert translocation.original(copy) == app.resolve()
    assert not translocation.translocated(app.resolve())

    moved = move_to_applications(
        translocation.original(copy) or app,
        [applications],
        tmp_path / ".Trash",
        translocation.unquarantine,
    )
    assert moved == applications / "Polyglotic.app"
    held = subprocess.run(
        ["/usr/bin/xattr", "-r", "-p", translocation.QUARANTINE, str(moved)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert held.stdout.strip() == "", held.stdout
    assert not translocation.security_says(moved.resolve())


_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Polyglotic</string>
<key>CFBundleIdentifier</key><string>io.polyglotic.translocation-check</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
"""
