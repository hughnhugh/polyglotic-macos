"""The Mac's adapters (polyglotic-hq 409; decision 0038): `os_adapters`
gives macOS a whole record without loading anything of Windows', and each
piece's logic holds on any OS - what touches macOS itself is `macos_only`
(run by the macOS job, polyglotic-hq 410), and the file lock runs wherever
there is `flock` (macOS and Linux)."""

import ast
import dataclasses
import subprocess
import sys
import uuid
from pathlib import Path

import pydantic
import pytest

from polyglotic_desktop import main
from polyglotic_desktop.connection.app import (
    AppInfo,
    Release,
    first_channel,
    this_release,
)
from polyglotic_desktop.connection.protocol import Hello, HelloAuth
from polyglotic_desktop.main import (
    NoOsAdapters,
    OsAdapters,
    os_adapters,
    this_copys_release,
)
from polyglotic_desktop.platform.macos import (
    apps,
    capture,
    categories,
    keychain,
    mic_permission,
    system,
)
from polyglotic_desktop.platform.macos.one_copy import FileLock
from polyglotic_desktop.ports.credentials import DeviceCredentials

WINDOWS_ONLY = (
    "polyglotic_desktop.platform.windows",
    "polyglotic_desktop.adapters.windows_credentials",
)
NOT_ON_A_MAC_YET: tuple[str, ...] = ()
"""The record's pieces macOS has none of yet: None, so the app leaves
them out. Since 428 none: the word card's voice and Home's offer to start
at sign-in are the Mac's own."""


def test_macos_gets_a_whole_record() -> None:
    mac = os_adapters("darwin")
    assert isinstance(mac, OsAdapters)
    for field in dataclasses.fields(OsAdapters):
        piece = getattr(mac, field.name)
        if field.name in NOT_ON_A_MAC_YET:
            assert piece is None, field.name
        elif field.name == "common_apps":
            assert piece == categories.COMMON_APPS
        elif field.name == "typing_permission":  # a Mac's Accessibility (438)
            assert piece is not None and callable(piece.allowed)
        elif field.name == "mic_permission":  # the Mac's microphone (478)
            assert isinstance(piece, mic_permission.Permission)
        elif field.name in ("qt_platform", "system_mode"):  # Qt's own (550, 571)
            assert piece is None
        elif field.name in (
            "dictation",  # offered on a Mac (574: not on Linux yet)
            "list_voices_at_start",  # pre-listed after start (646)
        ):
            assert piece is True
        elif field.name in ("unlock_spot", "clipboard_typing"):
            assert piece is False
        else:
            assert callable(piece), field.name
            assert "windows" not in getattr(piece, "__module__", ""), field.name


def test_macos_record_loads_nothing_of_windows() -> None:
    script = (
        "import sys\n"
        "from polyglotic_desktop.main import os_adapters\n"
        "os_adapters('darwin')\n"
        f"print('\\n'.join(m for m in sys.modules if m.startswith({WINDOWS_ONLY!r})))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert loaded.stdout.split() == []


def test_another_os_still_has_none() -> None:
    """Linux has its own since polyglotic-hq 550 (tests/test_linux_adapters.py)."""
    with pytest.raises(NoOsAdapters, match="freebsd"):
        os_adapters("freebsd14")


@pytest.mark.windows_only
def test_windows_record_is_as_it_was() -> None:
    windows = os_adapters("win32")
    assert windows.speaker is not None and windows.start_at_sign_in is not None
    assert windows.data_folder().name == "Polyglotic"
    assert "platform.windows" in windows.copy_lock.__module__
    assert windows.typing_permission is None  # Windows asks none (438)
    assert windows.mic_permission is None  # nor for the mic (478)


# --- system -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "name"),
    [("26.1", "macos-26"), ("14.2.1", "macos-14"), ("15", "macos-15")],
)
def test_os_name_is_the_major_version(version: str, name: str) -> None:
    assert system.os_name(version) == name


@pytest.mark.parametrize("version", ["", "x.1", "0.5"])
def test_os_name_refuses_a_version_it_cant_read(version: str) -> None:
    with pytest.raises(OSError):
        system.os_name(version)


def test_data_folder_is_application_support(tmp_path: Path) -> None:
    """Decision 0185."""
    assert system.data_folder(tmp_path) == (
        tmp_path / "Library" / "Application Support" / "Polyglotic"
    )


@pytest.mark.parametrize(("style", "light"), [("Dark", False), (None, True)])
def test_menu_bar_is_light_unless_dark_mode(style: str | None, light: bool) -> None:
    assert system.light_menu_bar(style) is light


def test_launch_clock_counts_up() -> None:
    assert system.seconds_since_launch() >= 0


# --- the protocol's os and channel -----------------------------------------


def hello(os: str, channel: str = "macos-arm64-alpha") -> Hello:
    return Hello.model_validate(
        {
            "app_version": "0.1.0",
            "install_id": str(uuid.uuid4()),
            "channel": channel,
            "os": os,
            "auth": HelloAuth(device_token="t"),
        }
    )


def test_a_mac_says_hello_as_the_server_accepts() -> None:
    """The server's `os` pattern and `macos-arm64-*` channels (server
    `api/protocol/v1.py`, read 2026-11-16)."""
    sent = hello(system.os_name("26.1"))
    assert (sent.os, sent.channel) == ("macos-26", "macos-arm64-alpha")
    assert hello("windows-11", "win-x64-alpha").os == "windows-11"


@pytest.mark.parametrize("os", ["macos", "macos-0", "macos-26.1", "windows-12"])
def test_an_os_the_server_wouldnt_take_isnt_sent(os: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        hello(os)


def test_a_mac_from_source_is_on_the_macs_first_channel(tmp_path: Path) -> None:
    assert first_channel("macos-26") == "macos-arm64-alpha"
    assert first_channel("windows-11") == "win-x64-alpha"
    missing = tmp_path / "release.json"
    assert this_release(missing, first_channel("macos-26")).channel == (
        "macos-arm64-alpha"
    )
    assert AppInfo("0.0.0", "macos-26").platform == "macos"


def test_settings_updates_names_the_macs_channel_from_source() -> None:
    """Settings > Updates, the log and the install check read `main`'s
    release: from source on a Mac it's the Mac's first channel, not
    "0.0.0 (win-x64-alpha)" (polyglotic-hq 451) - and every read in `main`
    goes through the one that knows the OS."""
    assert this_copys_release("darwin") == Release("0.0.0", "macos-arm64-alpha")
    assert this_copys_release("win32") == Release("0.0.0", "win-x64-alpha")
    tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    reads = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "this_release"
        and not any(k.arg == "first" for k in node.keywords)
    ]
    assert reads == [], "main.py: read the release with this_copys_release()"


# --- the Keychain -----------------------------------------------------------


class FakeKeychain:
    def __init__(self) -> None:
        self.items: dict[str, tuple[str, bytes]] = {}

    def read(self, service: str) -> tuple[str, bytes] | None:
        return self.items.get(service)

    def write(self, service: str, account: str, secret: bytes) -> None:
        kept = self.items.get(service)
        if kept is not None and not secret:  # as macOS' login keychain does
            secret = kept[1]  # (polyglotic-hq 420): an empty one isn't a change
        self.items[service] = (account, secret)

    def delete(self, service: str) -> None:
        self.items.pop(service, None)


def test_keychain_store_keeps_the_token_with_its_install_id() -> None:
    fake = FakeKeychain()
    store = keychain.KeychainStore(keychain=fake)
    assert store.load() is None and store.install_id() is None
    store.save(DeviceCredentials("id-1", "token-1"))
    assert store.load() == DeviceCredentials("id-1", "token-1")
    assert fake.items == {"Polyglotic/device": ("id-1", b"token-1")}


def test_signing_out_keeps_the_install_id() -> None:
    """Decision 0080, as on Windows."""
    fake = FakeKeychain()
    store = keychain.KeychainStore("Polyglotic/test", fake)
    store.save(DeviceCredentials("id-1", "token-1"))
    store.forget()
    assert store.load() is None
    assert store.install_id() == "id-1"
    assert fake.items == {"Polyglotic/test": ("id-1", b"")}  # the token's gone
    store.delete()
    assert store.install_id() is None and fake.items == {}


def test_forgetting_with_nothing_kept_leaves_nothing() -> None:
    fake = FakeKeychain()
    keychain.KeychainStore(keychain=fake).forget()
    assert fake.items == {}


@pytest.mark.macos_only
def test_the_real_keychain_keeps_and_forgets_a_token() -> None:
    """Under a service of the test's own, deleted after."""
    store = keychain.KeychainStore(f"Polyglotic/test-{uuid.uuid4()}")
    try:
        assert store.load() is None
        store.save(DeviceCredentials("id-1", "token-1"))
        assert store.load() == DeviceCredentials("id-1", "token-1")
        store.save(DeviceCredentials("id-1", "token-2"))
        assert store.load() == DeviceCredentials("id-1", "token-2")
        store.forget()
        assert store.load() is None and store.install_id() == "id-1"
    finally:
        store.delete()
    assert store.install_id() is None


@pytest.mark.macos_only
def test_macos_names_itself() -> None:
    assert system.os_name().startswith("macos-")
    assert system.os_version().split(".")[0].isdigit()
    assert system.light_menu_bar() in (True, False)
    assert 0 < system.seconds_since_launch() < 3600


# --- one copy ---------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="flock: macOS's and Linux's")
def test_a_second_copy_finds_the_lock_held(tmp_path: Path) -> None:
    first, second = FileLock("copy", tmp_path), FileLock("copy", tmp_path)
    assert first.take() and first.take()  # taking it again keeps it
    assert not second.take()
    assert FileLock("another", tmp_path).take()
    first.release()
    assert second.take()  # the copy before has ended
    second.release()


# --- what isn't on a Mac yet ------------------------------------------------


def test_the_mac_captures_with_its_own_taps_and_mic() -> None:
    """411's capture, in place of 409's stand-in (tests/test_macos_capture.py
    tests it; a Mac proves it, polyglotic-hq 410's job)."""
    mac = os_adapters("darwin")
    assert mac.app_list is apps.MacAppList
    assert mac.app_capture is capture.AppCapture
    assert mac.everything_else_capture is capture.EverythingElseCapture
    assert mac.system_capture is capture.SystemCapture
    assert mac.mic_capture is capture.MicCapture
    assert mac.windows_build() == ""
