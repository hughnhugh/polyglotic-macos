"""The speakers and mics Home's Sound lists (polyglotic-hq 372): Windows'
devices as the port's values, and nothing when Windows can't say. No
real device is listed or opened: Core Audio's answers are stand-ins."""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform.windows import devices
from polyglotic_desktop.platform.windows.devices import AudioDevice, Flow
from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices

OUT = [AudioDevice("{o1}", "Speakers"), AudioDevice("{o2}", "Headphones")]
IN = [AudioDevice("{i1}", "Microphone Array")]


def test_the_devices_and_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        devices, "active_devices", lambda flow: OUT if flow is Flow.OUTPUT else IN
    )
    monkeypatch.setattr(
        devices,
        "default_device",
        lambda flow: OUT[0] if flow is Flow.OUTPUT else None,
    )
    assert devices.sound_devices() == SoundDevices(
        (SoundDevice("{o1}", "Speakers"), SoundDevice("{o2}", "Headphones")),
        (SoundDevice("{i1}", "Microphone Array"),),
        "{o1}",
        None,
    )


def test_nothing_when_windows_cant_say(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(flow: Flow) -> list[AudioDevice]:
        raise OSError("no audio service")

    monkeypatch.setattr(devices, "active_devices", refused)
    monkeypatch.setattr(devices, "default_device", lambda flow: None)
    assert devices.sound_devices() == SoundDevices()
