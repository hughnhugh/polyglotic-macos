"""A problem report's facts on any OS (polyglotic-hq 515): main took the
audio devices from Windows' own module, which on a Mac fails while it
loads (AttributeError: ctypes has no WinDLL) - uncaught, so a tester's
Report a problem from a caption window's strip never opened on GitHub's
Mac. The devices now come from the OS's own adapter."""

import importlib.abc
import sys

import pytest

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.main import device_facts, report_facts
from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices

WINDOWS_DEVICES = "polyglotic_desktop.platform.windows.devices"


class LoadsAsOnAMac(importlib.abc.MetaPathFinder):
    """Windows' devices module failing as it does on a Mac."""

    def find_spec(self, name: str, path: object, target: object = None) -> None:
        if name == WINDOWS_DEVICES:
            raise AttributeError("module 'ctypes' has no attribute 'WinDLL'")


def test_the_facts_never_load_windows_own_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, WINDOWS_DEVICES, raising=False)
    monkeypatch.setattr(sys, "meta_path", [LoadsAsOnAMac(), *sys.meta_path])
    app = AppInfo.this_app("macOS", "26.0")
    mac = SoundDevices(
        (SoundDevice("AVIODevice 2", "MacBook Pro Speakers"),),
        (SoundDevice("AVIODevice", "MacBook Pro Microphone"),),
        "AVIODevice 2",
        "AVIODevice",
    )
    facts = report_facts(app, "macos-arm64-alpha", [], None, lambda: mac)
    assert facts["audio_devices"] == {
        "output": {
            "default": "MacBook Pro Speakers",
            "active": ["MacBook Pro Speakers"],
        },
        "input": {
            "default": "MacBook Pro Microphone",
            "active": ["MacBook Pro Microphone"],
        },
    }


def test_devices_that_cant_be_listed_never_stop_a_report() -> None:
    def fails() -> SoundDevices:
        raise AttributeError("no Core Audio")

    assert device_facts(fails) == {"unavailable": "AttributeError"}
    assert device_facts(None) == {"unavailable": "not asked"}
    assert device_facts(SoundDevices)["output"] == {"default": None, "active": []}
