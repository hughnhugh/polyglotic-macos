"""Linux's adapters (polyglotic-hq 546, 547, 550; decision 0038):
`os_adapters` gives Linux a whole record without loading anything of
Windows' or the Mac's, and each piece's logic holds on any OS - what needs
Linux itself (a sound server, a session bus) is `linux_desktop`, run by
`.github/workflows/linux.yml` on GitHub's Ubuntu runner."""

import dataclasses
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pydantic
import pytest

from polyglotic_desktop.connection.app import AppInfo, first_channel, this_release
from polyglotic_desktop.connection.protocol import Hello, HelloAuth
from polyglotic_desktop.main import OsAdapters, os_adapters, this_copys_release
from polyglotic_desktop.platform.linux import apps, capture, not_yet, on_top, system
from polyglotic_desktop.platform.linux.one_copy import FileLock
from polyglotic_desktop.platform.linux.secret_service import (
    FileKeyring,
    KeyringRefused,
    NoKeyring,
    SecretService,
    SecretServiceStore,
    state_folder,
)
from polyglotic_desktop.ports.capture import AppCaptureSupport
from polyglotic_desktop.ports.credentials import DeviceCredentials

OTHER_OSES = (
    "polyglotic_desktop.platform.windows",
    "polyglotic_desktop.platform.macos",
    "polyglotic_desktop.adapters.windows_credentials",
)
NOT_ON_LINUX_YET = (
    "typing_permission",
    "mic_permission",
)
"""The record's pieces Linux has none of: None, so the app leaves them out
(Linux asks no permission to type or to hear the mic). Starting at sign-in
is an XDG autostart entry (571); the word card's voice is slice 5's (591)."""


def test_linux_gets_a_whole_record() -> None:
    linux = os_adapters("linux")
    assert isinstance(linux, OsAdapters)
    for field in dataclasses.fields(OsAdapters):
        piece = getattr(linux, field.name)
        if field.name in NOT_ON_LINUX_YET:
            assert piece is None, field.name
        elif field.name == "activate_from_tray":
            # Cocoa alone needs explicit native activation from its status item.
            assert piece is None
        elif field.name == "translocation":
            assert not piece, field.name
        elif field.name == "common_apps":  # listed before they play (561)
            assert piece, field.name
        elif field.name == "platform_kind":
            assert piece in {"linux", "crostini"}
        elif field.name == "qt_platform":  # X11, through XWayland (0258)
            assert piece == "xcb"
        elif (
            field.name == "dictation" or field.name == "list_voices_at_start"
        ):  # none until 546's slice 8 (574)
            assert piece is False
        elif field.name in {"unlock_spot", "clipboard_typing"}:
            assert isinstance(piece, bool)
        else:
            assert callable(piece), field.name
            module = getattr(piece, "__module__", "") or ""
            assert "windows" not in module and "macos" not in module, field.name


def test_linux_record_loads_nothing_of_the_other_oses() -> None:
    script = (
        "import sys\n"
        "from polyglotic_desktop.main import os_adapters\n"
        "os_adapters('linux')\n"
        f"print('\\n'.join(m for m in sys.modules if m.startswith({OTHER_OSES!r})))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert loaded.stdout.split() == []


def test_what_isnt_there_yet_says_so_through_its_port() -> None:
    """No dictation yet (slice 8)."""
    linux = os_adapters("linux")
    assert not linux.dictation
    assert linux.hold_key("right_ctrl", print, print, print).start() is False
    assert linux.type_text("hello") is False
    assert linux.keys("escape") is False
    assert linux.foreground_watch(lambda: None).start() is False
    assert not_yet.same_name("Polyglotic") == "Polyglotic"


def test_the_voice_and_the_sample_are_linuxs_own() -> None:
    """Slice 5 (591): a word said in a pack's recording, else
    speech-dispatcher's voice, played through the sound server; Home's
    sample played aloud there too. Nothing is asked of speech-dispatcher
    until the voices are."""
    from polyglotic_desktop.platform.linux import sound
    from polyglotic_desktop.platform.linux.voices import DispatcherVoices
    from polyglotic_desktop.platform.recorded_voices import RecordedVoices, Recordings

    linux = os_adapters("linux")
    assert isinstance(linux.sound_out(), sound.PlayAloud)
    assert linux.speaker is not None
    speaker = linux.speaker(Recordings())
    try:
        said = speaker._source
        assert isinstance(said, RecordedVoices)
        assert isinstance(said._os, DispatcherVoices)
        assert speaker._new_output is sound.PulseOutput
        assert not speaker.listed  # never during the start
    finally:
        speaker.close()


def test_linux_starts_speech_dispatcher_only_on_demand_not_at_start() -> None:
    """646: listing voices at app start spawns speech-dispatcher and its
    never-paused dummy stream; Linux leaves `list_voices_at_start` False while
    Windows and macOS keep pre-listing after start."""
    from polyglotic_desktop import main

    default = next(
        field.default
        for field in dataclasses.fields(OsAdapters)
        if field.name == "list_voices_at_start"
    )
    assert default is True
    assert os_adapters("linux").list_voices_at_start is False
    assert os_adapters("darwin").list_voices_at_start is True
    if sys.platform == "win32":
        assert os_adapters("win32").list_voices_at_start is True
    source = Path(main.__file__).read_text(encoding="utf-8")
    assert "if speaker is not None and system.list_voices_at_start:" in source


def test_one_app_at_a_time_is_linuxs_own() -> None:
    """Slice 2 (561): one app and everything else captured from the apps'
    own streams, the apps listed from the sound server's, the known apps
    by their Linux executables."""
    linux = os_adapters("linux")
    assert linux.app_capture_support is capture.app_capture_support
    assert capture.app_capture_support(lambda: None) is AppCaptureSupport.YES
    assert linux.app_list is apps.LinuxAppList
    one = linux.app_capture(1, "firefox", None)
    rest = linux.everything_else_capture(1, None)
    assert isinstance(one, capture.AppCapture)
    assert isinstance(rest, capture.EverythingElseCapture)
    assert {"firefox", "chrome", "Discord"} <= {a.name for a in linux.common_apps}


# --- the protocol's os and channel -------------------------------------------


@pytest.mark.parametrize(
    ("release", "name"),
    [
        ("6.8.0-49-generic", "linux-6"),
        ("5.15.0", "linux-5"),
        ("6.17.7-300.fc45.x86_64", "linux-6"),
    ],
)
def test_os_name_is_the_kernels_major_version(release: str, name: str) -> None:
    assert system.os_name(release) == name


@pytest.mark.parametrize("release", ["", "generic", "0.1", "1000.1"])
def test_os_name_refuses_a_kernel_it_cant_read(release: str) -> None:
    with pytest.raises(OSError, match="kernel"):
        system.os_name(release)


def hello(os_: str, channel: str = "linux-x64-alpha") -> Hello:
    return Hello.model_validate(
        {
            "app_version": "0.1.0",
            "install_id": str(uuid.uuid4()),
            "channel": channel,
            "os": os_,
            "auth": HelloAuth(device_token="t"),
        }
    )


def test_linux_says_hello_as_the_server_accepts() -> None:
    """The server's `os` pattern and `linux-x64-*` channels (server
    `api/protocol/v1.py`, read 2026-11-20; its smoke test says `linux-6`)."""
    sent = hello(system.os_name("6.8.0-49-generic"))
    assert (sent.os, sent.channel) == ("linux-6", "linux-x64-alpha")
    for channel in ("linux-x64-beta", "linux-x64-stable"):
        assert hello("linux-6", channel).channel == channel


@pytest.mark.parametrize("os_", ["linux", "linux-0", "linux-6.8", "ubuntu-24"])
def test_a_linux_os_the_server_wouldnt_take_isnt_sent(os_: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        hello(os_)


def test_linux_from_source_is_on_linuxs_first_channel(tmp_path: Path) -> None:
    assert first_channel("linux-6") == "linux-x64-alpha"
    missing = tmp_path / "release.json"
    assert this_release(missing, first_channel("linux-6")).channel == "linux-x64-alpha"
    assert AppInfo("0.0.0", "linux-6").platform == "linux"
    assert this_copys_release("linux").channel == "linux-x64-alpha"


# --- system ----------------------------------------------------------------------


def test_folders_follow_xdg(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert system.data_folder({}, home) == home / ".local/share/Polyglotic"
    assert system.cache_folder({}, home) == home / ".cache/Polyglotic"
    given = {
        "XDG_DATA_HOME": str(tmp_path / "d"),
        "XDG_CACHE_HOME": str(tmp_path / "c"),
    }
    assert system.data_folder(given, home) == tmp_path / "d" / "Polyglotic"
    assert system.cache_folder(given, home) == tmp_path / "c" / "Polyglotic"
    # a relative path is ignored, as the XDG specification says
    relative = {"XDG_DATA_HOME": "relative/data"}
    assert system.data_folder(relative, home) == home / ".local/share/Polyglotic"


def test_the_lock_lives_in_the_runtime_folder(tmp_path: Path) -> None:
    runtime = {"XDG_RUNTIME_DIR": str(tmp_path / "run")}
    assert system.runtime_folder(runtime, tmp_path) == tmp_path / "run" / "Polyglotic"
    without = system.runtime_folder({}, tmp_path)
    assert without == tmp_path / ".local/share/Polyglotic/locks"


def test_os_version_names_the_distribution_desktop_and_session(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n# a comment\nNAME="Ubuntu"\n')
    fields = system.os_release(release)
    env = {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"}
    assert system.os_version(fields, env) == "ubuntu 24.04 ubuntu wayland"
    assert system.os_version({}, {}) == "linux"


def test_launch_clock_reads_proc() -> None:
    stat_line = "1234 (python3 (x)) S " + " ".join(["0"] * 18) + " 500 0 0"
    assert system.seconds_since_launch(stat_line, "12.5 3.0", 100) == pytest.approx(7.5)
    assert system.seconds_since_launch("garbled", "x", 100) >= 0


def test_a_program_of_the_desktops_gets_the_systems_libraries() -> None:
    """PyInstaller's loader points LD_LIBRARY_PATH at the app's own folder
    and keeps the one before in LD_LIBRARY_PATH_ORIG: zenity or kdialog
    must get the system's (550)."""
    env = system.outside_environment(
        {"LD_LIBRARY_PATH": "/tmp/_MEI/app", "LD_LIBRARY_PATH_ORIG": "/usr/lib/x"}
    )
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/x" and "LD_LIBRARY_PATH_ORIG" not in env


def test_the_packed_app_leaves_its_library_path_to_itself() -> None:
    """A link opened in the packed app started the browser through
    `xdg-open` with LD_LIBRARY_PATH naming the app's own folder, so the
    browser loaded the app's copies of libraries (550's finding): the start
    puts the outside path back for every program started after it (561)."""
    env = {
        "LD_LIBRARY_PATH": "/tmp/.mount_Poly/usr/bin/_internal:/opt/x",
        "LD_LIBRARY_PATH_ORIG": "/opt/x",
        "HOME": "/home/learner",
    }
    system.leave_packed_environment(env)
    assert env == {"LD_LIBRARY_PATH": "/opt/x", "HOME": "/home/learner"}
    env = {"LD_LIBRARY_PATH": "/tmp/.mount_Poly/usr/bin/_internal"}  # none before
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(system.sys, "frozen", True, raising=False)
        system.leave_packed_environment(env)
    assert env == {}
    env = {"LD_LIBRARY_PATH": "/opt/qt-libs"}  # from source: the developer's own
    system.leave_packed_environment(env)
    assert env == {"LD_LIBRARY_PATH": "/opt/qt-libs"}


def test_a_program_the_app_starts_gets_none_of_the_loaders_variables() -> None:
    """PyInstaller's loader tells a process it starts of itself who its
    parent is (`_PYI_*`): Velopack's updater, started by the app, starts the
    new AppImage after an update, which then took itself for this one's
    child (561's proposal, 574). Neither a desktop's program nor anything
    started after the start gets them; the app's other variables stay."""
    loader = {
        "_PYI_APPLICATION_HOME_DIR": "/tmp/.mount_Poly/usr/bin/_internal",
        "_PYI_ARCHIVE_FILE": "/tmp/.mount_Poly/usr/bin/Polyglotic",
        "_PYI_PARENT_PROCESS_LEVEL": "1",
    }
    env = system.outside_environment({**loader, "HOME": "/home/learner"})
    assert env == {"HOME": "/home/learner"}
    env = {**loader, "HOME": "/home/learner", "PYI_NOT_THE_LOADERS": "kept"}
    assert system.loader_variables(env) == sorted(loader)
    system.leave_packed_environment(env)
    assert env == {"HOME": "/home/learner", "PYI_NOT_THE_LOADERS": "kept"}
    assert system.loader_variables(env) == []


def test_the_start_leaves_the_packed_environment_on_linux_only() -> None:
    from polyglotic_desktop.main import leave_packed_environment

    for os_ in ("win32", "darwin"):
        env = {"LD_LIBRARY_PATH": "/app", "LD_LIBRARY_PATH_ORIG": "/x"}
        leave_packed_environment(os_, env)
        assert env == {"LD_LIBRARY_PATH": "/app", "LD_LIBRARY_PATH_ORIG": "/x"}
    env = {"LD_LIBRARY_PATH": "/app", "LD_LIBRARY_PATH_ORIG": "/x"}
    leave_packed_environment("linux", env)
    assert env == {"LD_LIBRARY_PATH": "/x"}


def test_the_install_check_says_whose_libraries_a_program_gets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from polyglotic_desktop.main import programs_library_path

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    inside = {"LD_LIBRARY_PATH": f"{tmp_path}{os.pathsep}/opt/x"}
    assert programs_library_path(inside) == "the app's"
    assert programs_library_path({"LD_LIBRARY_PATH": "/opt/x"}) == "the system's"
    assert programs_library_path({}) == "the system's"


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX program as the child")
def test_a_program_started_after_the_start_gets_the_outside_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What Qt's `xdg-open` inherits is the process's own environment: a
    child started after the start sees the outside library path."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/nowhere/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/nowhere/outside")
    system.leave_packed_environment()
    seen = subprocess.run(
        ["/usr/bin/env"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert "LD_LIBRARY_PATH=/nowhere/outside" in seen
    assert not any(line.startswith("LD_LIBRARY_PATH_ORIG=") for line in seen)


def test_the_error_box_is_the_desktops_own(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(
        system.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "kdialog" else None,
    )
    monkeypatch.setattr(system.subprocess, "run", lambda args, **_k: ran.append(args))
    system.show_error("Polyglotic", "It couldn't start.")
    assert ran == [
        ["/usr/bin/kdialog", "--title", "Polyglotic", "--error", "It couldn't start."]
    ]
    assert "It couldn't start." in capsys.readouterr().err


# --- one copy ---------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="flock: Linux's and macOS's")
def test_a_second_copy_finds_the_lock_held(tmp_path: Path) -> None:
    first, second = FileLock("copy", tmp_path), FileLock("copy", tmp_path)
    assert first.take()
    assert not second.take()
    first.release()
    assert second.take()
    second.release()


# --- credentials ------------------------------------------------------------------


class FakeKeyring:
    def __init__(self, error: OSError | None = None) -> None:
        self.items: dict[str, tuple[str, bytes]] = {}
        self.error = error

    def read(self, entry: str) -> tuple[str, bytes] | None:
        if self.error:
            raise self.error
        return self.items.get(entry)

    def write(self, entry: str, account: str, secret: bytes) -> None:
        if self.error:
            raise self.error
        self.items[entry] = (account, secret)

    def delete(self, entry: str) -> None:
        if self.error:
            raise self.error
        self.items.pop(entry, None)


TOKEN = DeviceCredentials("install-550", "pgd_" + "x" * 43)


def test_the_keyring_keeps_the_token_with_its_install_id() -> None:
    keyring = FakeKeyring()
    store = SecretServiceStore(
        "Polyglotic/device", keyring, FakeKeyring(NoKeyring("unused"))
    )
    assert store.load() is None and store.install_id() is None
    store.save(TOKEN)
    assert store.load() == TOKEN
    assert keyring.items["Polyglotic/device"] == (
        "install-550",
        TOKEN.device_token.encode(),
    )


def test_signing_out_keeps_the_install_id() -> None:
    store = SecretServiceStore("e", FakeKeyring(), FakeKeyring())
    store.save(TOKEN)
    store.forget()
    assert store.load() is None
    assert store.install_id() == "install-550"


def test_no_keyring_keeps_it_in_a_file_only_the_user_can_read(tmp_path: Path) -> None:
    files = FileKeyring(tmp_path / "state")
    store = SecretServiceStore(
        "Polyglotic/device@127.0.0.1:8217", FakeKeyring(NoKeyring("no bus")), files
    )
    store.save(TOKEN)
    assert store.load() == TOKEN
    kept = next((tmp_path / "state").glob("*.json"))
    assert json.loads(kept.read_text())["account"] == "install-550"
    if sys.platform != "win32":
        assert stat.S_IMODE(kept.stat().st_mode) == 0o600
        assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == 0o700
    store.delete()
    assert store.load() is None


def test_a_keyring_that_wont_open_is_not_signed_in_not_a_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Locked, and its password box dismissed: not signed in yet, and the log
    says why - once (546 section 1.6)."""
    store = SecretServiceStore(
        "e", FakeKeyring(KeyringRefused("dismissed")), FakeKeyring()
    )
    assert store.load() is None and store.load() is None
    assert store.install_id() is None
    said = [r.message for r in caplog.records if "credentials" in r.message]
    assert len(said) == 1 and "wouldn't open" in said[0]
    assert TOKEN.device_token not in caplog.text


def test_no_session_bus_is_no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nonexistent/550-bus")
    with pytest.raises(NoKeyring):
        SecretService().read("e")


def test_the_state_folder_follows_xdg(tmp_path: Path) -> None:
    assert state_folder({}, tmp_path) == tmp_path / ".local/state/Polyglotic"
    given = {"XDG_STATE_HOME": str(tmp_path / "s")}
    assert state_folder(given, tmp_path) == tmp_path / "s" / "Polyglotic"


@pytest.mark.linux_desktop
def test_the_real_keyring_keeps_and_forgets_a_token() -> None:
    """The Secret Service on the session bus (gnome-keyring on the runner),
    through its plain session - under an entry of the test's own, deleted."""
    entry = f"Polyglotic/test-550-{uuid.uuid4().hex[:8]}"
    store = SecretServiceStore(entry, SecretService(), FakeKeyring(NoKeyring("unused")))
    try:
        store.save(TOKEN)
        assert store.load() == TOKEN
        store.forget()
        assert store.load() is None and store.install_id() == "install-550"
        # a store of its own reads the keyring afresh (561: once a run)
        fresh = SecretServiceStore(entry, SecretService(), FakeKeyring())
        assert fresh.install_id() == "install-550" and fresh.load() is None
    finally:
        store.delete()
    fresh = SecretServiceStore(entry, SecretService(), FakeKeyring(NoKeyring("x")))
    assert fresh.install_id() is None


# --- the caption windows' order ---------------------------------------------------


def test_the_windows_given_go_up_first_then_the_popovers_above_them() -> None:
    """A caption window shown again comes up over the popover it opened
    (they're override-redirect: no window manager orders them), so the
    popover goes back above it (550, as the Mac's `lifted`)."""
    shown = {11: False, 12: True, 13: True, 14: False}  # 12 a popover, 13 a menu
    assert on_top.raising_order([14, 11], shown) == [14, 11, 12, 13]
    assert on_top.raising_order([99], shown) == [12, 13]  # 99 isn't showing


def test_the_caption_windows_are_always_put_in_order() -> None:
    assert on_top.LinuxOnTop().game_in_front() is True


def test_nothing_needs_the_os_to_import() -> None:
    """Every module imports on any OS: libpulse and D-Bus load on first use."""
    assert os.path.basename(capture.__file__) == "capture.py"


# --- X11, whatever the session would pick ------------------------------------------


def test_linux_runs_on_x11_whatever_the_session_picks() -> None:
    """On a Wayland desktop Qt would pick its Wayland platform, where a
    window can't stay on top or place itself - and the packed app carries
    none (550): the app asks for X11 (XWayland) before Qt starts."""
    from polyglotic_desktop.main import use_qt_platform

    assert os_adapters("linux").qt_platform == "xcb"
    for asked in (
        {},
        {"QT_QPA_PLATFORM": "wayland"},
        {"QT_QPA_PLATFORM": "wayland;xcb"},
    ):
        env = dict(asked)
        use_qt_platform("xcb", env)
        assert env["QT_QPA_PLATFORM"] == "xcb"
    for kept in ("offscreen", "minimal"):  # the tests' and the install check's
        env = {"QT_QPA_PLATFORM": kept}
        use_qt_platform("xcb", env)
        assert env["QT_QPA_PLATFORM"] == kept
    env = {}
    use_qt_platform(None, env)  # Windows, a Mac: Qt's own choice
    assert env == {}


def test_a_locked_windows_corner_takes_the_mouse_only_on_a_wayland_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The X server can't say where the mouse is over a Wayland app's window
    (547); in an Xorg session it can, anywhere (570)."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert os_adapters("linux").unlock_spot
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert not os_adapters("linux").unlock_spot


def test_crostini_uses_guest_markers_only(tmp_path: Path) -> None:
    assert system.platform_kind(tmp_path) == "linux"
    apt = tmp_path / "etc/apt/sources.list.d/cros.list"
    apt.parent.mkdir(parents=True)
    apt.touch()
    assert system.platform_kind(tmp_path) == "linux"
    (tmp_path / "opt/google/cros-containers").mkdir(parents=True)
    assert system.platform_kind(tmp_path) == "crostini"
    apt.unlink()
    milestone = tmp_path / "dev/.cros_milestone"
    milestone.parent.mkdir()
    milestone.touch()
    assert system.platform_kind(tmp_path) == "crostini"
