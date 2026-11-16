"""Windows' audio devices as they are right now, from Core Audio
(IMMDeviceEnumerator): the defaults and every active output and mic, by id
and friendly name ("Headphones (HyperX Cloud III Wireless)").

From the proof of concept's `audio_devices.py`, by device id as well as
name: captures open devices by id, so a device plugged in later needs no
restart of anything (the proof of concept restarted PortAudio for that).
"""

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import POINTER, byref, c_uint, c_void_p, wintypes
from dataclasses import dataclass
from enum import IntEnum

from polyglotic_desktop.platform.windows.com import (
    CLSCTX_ALL,
    GUID,
    PROPERTYKEY,
    PROPVARIANT,
    VT_LPWSTR,
    ensure_com,
    method,
    ole32,
    release,
)
from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices

_CLSID_MMDeviceEnumerator = GUID.parse("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
_IID_IMMDeviceEnumerator = GUID.parse("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
_PKEY_Device_FriendlyName = PROPERTYKEY(
    GUID.parse("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14
)
_E_MULTIMEDIA = 1  # ERole: the default Windows' sound settings pick
_DEVICE_STATE_ACTIVE = 1
_STGM_READ = 0


class Flow(IntEnum):
    OUTPUT = 0  # eRender
    INPUT = 1  # eCapture


@dataclass(frozen=True, slots=True)
class AudioDevice:
    id: str
    name: str


@contextmanager
def _enumerator() -> Iterator[c_void_p]:
    ensure_com()
    enumerator = c_void_p()
    result = ole32.CoCreateInstance(
        byref(_CLSID_MMDeviceEnumerator),
        None,
        CLSCTX_ALL,
        byref(_IID_IMMDeviceEnumerator),
        byref(enumerator),
    )
    if result < 0:
        raise OSError(
            f"Couldn't reach Windows' audio devices: {result & 0xFFFFFFFF:#x}"
        )
    try:
        yield enumerator
    finally:
        release(enumerator)


def _describe(device: c_void_p) -> AudioDevice:
    raw_id = ctypes.c_wchar_p()
    method(device, 5, POINTER(ctypes.c_wchar_p))(byref(raw_id))  # GetId
    device_id = raw_id.value or ""
    ole32.CoTaskMemFree(raw_id)
    store = c_void_p()
    method(device, 4, wintypes.DWORD, POINTER(c_void_p))(_STGM_READ, byref(store))
    try:
        value = PROPVARIANT()
        method(store, 5, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(  # GetValue
            byref(_PKEY_Device_FriendlyName), byref(value)
        )
        try:
            ok = value.vt == VT_LPWSTR and value.value
            name = ctypes.wstring_at(value.value) if ok else ""
        finally:
            ole32.PropVariantClear(byref(value))
    finally:
        release(store)
    return AudioDevice(device_id, name)


def default_device(flow: Flow) -> AudioDevice | None:
    """Windows' default output or mic, or None if there is none."""
    with _enumerator() as enumerator:
        device = c_void_p()
        try:
            method(enumerator, 4, c_uint, c_uint, POINTER(c_void_p))(
                flow, _E_MULTIMEDIA, byref(device)
            )
        except OSError:
            return None  # nothing plugged in
        try:
            return _describe(device)
        finally:
            release(device)


def active_devices(flow: Flow) -> list[AudioDevice]:
    """Every output or mic that's plugged in and enabled, by name."""
    with _enumerator() as enumerator:
        collection = c_void_p()
        method(enumerator, 3, c_uint, wintypes.DWORD, POINTER(c_void_p))(
            flow, _DEVICE_STATE_ACTIVE, byref(collection)
        )
        try:
            count = c_uint()
            method(collection, 3, POINTER(c_uint))(byref(count))
            found = []
            for i in range(count.value):
                device = c_void_p()
                method(collection, 4, c_uint, POINTER(c_void_p))(i, byref(device))
                try:
                    found.append(_describe(device))
                finally:
                    release(device)
            return sorted(found, key=lambda d: d.name.lower())
        finally:
            release(collection)


def sound_devices() -> SoundDevices:
    """Every speaker and mic plugged in, by name, and Windows' defaults -
    for Home's and Settings' choice of them (polyglotic-hq 372). Nothing,
    if Windows can't say."""
    try:
        speaker, mic = default_device(Flow.OUTPUT), default_device(Flow.INPUT)
        return SoundDevices(
            tuple(SoundDevice(d.id, d.name) for d in active_devices(Flow.OUTPUT)),
            tuple(SoundDevice(d.id, d.name) for d in active_devices(Flow.INPUT)),
            speaker.id if speaker else None,
            mic.id if mic else None,
        )
    except OSError:
        return SoundDevices()


def activate(device_id: str, iid: GUID) -> c_void_p:
    """Interface `iid` (an IAudioClient, a session manager...) of the
    device `device_id`. The caller releases it."""
    with _enumerator() as enumerator:
        device = c_void_p()
        method(enumerator, 5, wintypes.LPCWSTR, POINTER(c_void_p))(
            device_id, byref(device)
        )
        try:
            out = c_void_p()
            method(
                device, 3, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p)
            )(byref(iid), CLSCTX_ALL, None, byref(out))
            return out
        finally:
            release(device)


_IID_IAudioMeterInformation = GUID.parse("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
PLAYING_PEAK = 0.001
"""An output whose meter peaks above this (about -60 dB) is playing sound."""


def outputs_playing() -> int | None:
    """How many outputs play sound now, by each one's own meter
    (IAudioMeterInformation: its peak lately, 0 to 1 - a number, never the
    audio); None if Windows can't say. For the caption log's line on each
    mic-bleed check: the check hears one output, Windows' default
    (decision 0004)."""
    try:
        count = 0
        for device in active_devices(Flow.OUTPUT):
            meter = activate(device.id, _IID_IAudioMeterInformation)
            try:
                peak = ctypes.c_float()
                method(meter, 3, POINTER(ctypes.c_float))(byref(peak))  # GetPeakValue
            finally:
                release(meter)
            count += peak.value > PLAYING_PEAK
        return count
    except OSError:
        return None
