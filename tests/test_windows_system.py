"""Windows' own answers to `ports/system.py` (`platform.windows.system`), and
`main.os_adapters` handing over the Windows adapters `main` imported
directly before decision 0038 - the same functions and classes, so nothing
changes on Windows."""

import sys
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.adapters.windows_credentials import (
    TARGET,
    WindowsCredentialStore,
)
from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.windows import (
    apps,
    capture,
    error_box,
    hotkeys,
    keys,
    on_top,
    process,
    sound,
    startup,
    system,
    taskbar,
)


def test_windows_names() -> None:
    assert system.os_name(26200) == "windows-11"
    assert system.os_name(19045) == "windows-10"
    assert system.os_name() in ("windows-10", "windows-11")
    assert system.os_version().count(".") == 2  # 10.0.26200


def test_the_users_data_is_outside_the_install_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    r"""The installer replaces or removes all of `%LOCALAPPDATA%\Polyglotic`
    (its app ID's folder) on install and uninstall, so the learner's data
    lives in roaming app data (decision 0014)."""
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    install_folder = local / "Polyglotic"

    folder = system.data_folder()

    assert folder == roaming / "Polyglotic"
    assert not folder.is_relative_to(install_folder)


def test_the_data_folder_without_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    assert system.data_folder() == Path.home() / "AppData" / "Roaming" / "Polyglotic"


def test_on_windows_main_gets_the_windows_adapters() -> None:
    found = os_adapters("win32")
    assert found.app_list is apps.WindowsAppList
    assert found.app_capture_support is capture.app_capture_support
    assert found.app_capture_trial is capture.Trial
    assert found.windows_build is system.windows_build
    assert found.app_capture is capture.AppCapture
    assert found.everything_else_capture is capture.EverythingElseCapture
    assert found.system_capture is capture.SystemCapture
    assert found.mic_capture is capture.MicCapture
    assert found.hotkeys is hotkeys.GlobalHotkeys
    assert found.sound_out is sound.PlayAloud  # the sample (176)
    assert found.start_at_sign_in is startup.RunAtSignIn  # start with Windows (176)
    assert found.keys is keys.held
    assert found.on_top is on_top.WindowsOnTop
    assert found.foreground_watch is on_top.ForegroundWatch
    assert found.light_taskbar is taskbar.light_taskbar
    assert found.taskbar_identity is taskbar.app_identity  # 245
    assert found.os_name is system.os_name
    assert found.os_version is system.os_version
    assert found.data_folder is system.data_folder
    assert found.show_error is error_box.show_error
    assert found.seconds_since_launch is process.seconds_since_launch


def test_the_device_token_store_is_the_apps_unless_one_is_named() -> None:
    """`--credentials NAME` (tests, the harness) keeps a token apart."""
    stores = os_adapters("win32").credentials
    app_own, named = stores(None), stores("Polyglotic/test")
    assert isinstance(app_own, WindowsCredentialStore)
    assert isinstance(named, WindowsCredentialStore)
    assert (app_own._target, named._target) == (TARGET, "Polyglotic/test")
