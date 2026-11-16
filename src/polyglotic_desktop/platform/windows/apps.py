"""The apps with sound on Windows, for the app picker (the `AppList` port).

Windows keeps an audio session per app on each output device
(IAudioSessionManager2, Windows 7+). Each is reported once, by its top
process: a browser plays sound from a child process, so the child is
traced up to the first process of the same executable, and capturing that
process's tree catches all of its sound, even if the child is replaced.
"""

import ctypes
import functools
import os
from ctypes import POINTER, byref, c_int, c_void_p, wintypes

from polyglotic_desktop.platform.windows.categories import category_of, known_name
from polyglotic_desktop.platform.windows.com import (
    GUID,
    method,
    query_interface,
    release,
)
from polyglotic_desktop.platform.windows.devices import Flow, activate, active_devices
from polyglotic_desktop.ports.capture import PlayingApp

_IID_IAudioSessionManager2 = GUID.parse("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
_IID_IAudioSessionControl2 = GUID.parse("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
_IID_IAudioMeterInformation = GUID.parse("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
_SESSION_ACTIVE = 1
_TH32CS_SNAPPROCESS = 2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_INVALID_HANDLE = ctypes.c_void_p(-1).value

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    POINTER(wintypes.DWORD),
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

_version = ctypes.WinDLL("version", use_last_error=True)
_version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
_version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, POINTER(wintypes.DWORD)]
_version.GetFileVersionInfoW.restype = wintypes.BOOL
_version.GetFileVersionInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    c_void_p,
]
_version.VerQueryValueW.restype = wintypes.BOOL
_version.VerQueryValueW.argtypes = [
    c_void_p,
    wintypes.LPCWSTR,
    POINTER(c_void_p),
    POINTER(wintypes.UINT),
]
_ENGLISH_UNICODE = "040904b0"
"""U.S. English, Unicode: the version resource's usual table, tried when
it lists none."""


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, POINTER(_PROCESSENTRY32W)]


def _processes() -> dict[int, tuple[int, str]]:
    """Every process now: id -> (parent id, executable name)."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, _INVALID_HANDLE):
        raise OSError(f"Couldn't list processes: {ctypes.get_last_error()}")
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        found = {}
        ok = _kernel32.Process32FirstW(snapshot, byref(entry))
        while ok:
            found[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = _kernel32.Process32NextW(snapshot, byref(entry))
        return found
    finally:
        _kernel32.CloseHandle(snapshot)


def _path(process_id: int) -> str | None:
    handle = _kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
    )
    if not handle:
        return None  # gone, or not ours to look at
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, byref(size))
        return buffer.value if ok else None
    finally:
        _kernel32.CloseHandle(handle)


@functools.lru_cache(maxsize=256)
def own_name(path: str | None) -> str | None:
    """What the executable at `path` calls itself, from its version
    resource - its description ("VLC media player"), else its product name
    - as Task Manager shows it; None if it says neither, or can't be read.
    Read once per path (the picker looks every few seconds)."""
    if not path:
        return None
    size = _version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not _version.GetFileVersionInfoW(path, 0, size, data):
        return None
    tables = []
    found, length = c_void_p(), wintypes.UINT()
    if (
        _version.VerQueryValueW(
            data, r"\VarFileInfo\Translation", byref(found), byref(length)
        )
        and found.value
    ):
        pairs = ctypes.cast(found, POINTER(wintypes.WORD))
        for i in range(0, length.value // 2 - 1, 2):
            tables.append(f"{pairs[i]:04x}{pairs[i + 1]:04x}")
    tables.append(_ENGLISH_UNICODE)
    for field in ("FileDescription", "ProductName"):
        for table in tables:
            query = rf"\StringFileInfo\{table}\{field}"
            if (
                _version.VerQueryValueW(data, query, byref(found), byref(length))
                and found.value
                and length.value
            ):
                text = ctypes.wstring_at(found.value, length.value)
                text = text.replace("\x00", "").strip()
                if text:
                    return text
    return None


def top_process(process_id: int, processes: dict[int, tuple[int, str]]) -> int:
    """The first process up the tree from `process_id` that runs the same
    executable (a browser's main process, for its audio child)."""
    if process_id not in processes:
        return process_id
    exe = processes[process_id][1].lower()
    for _ in range(16):  # process ids are reused: never loop forever
        parent = processes[process_id][0]
        if parent == process_id or parent not in processes:
            break
        if processes[parent][1].lower() != exe:
            break
        process_id = parent
    return process_id


def _sessions(device_id: str) -> list[tuple[int, bool]]:
    """(process id, active?) of each app's audio session on one output."""
    manager = activate(device_id, _IID_IAudioSessionManager2)
    try:
        sessions = c_void_p()
        method(manager, 5, POINTER(c_void_p))(byref(sessions))  # GetSessionEnumerator
        try:
            count = c_int()
            method(sessions, 3, POINTER(c_int))(byref(count))
            found = []
            for i in range(count.value):
                control = c_void_p()
                method(sessions, 4, c_int, POINTER(c_void_p))(i, byref(control))
                try:
                    state = c_int()
                    method(control, 3, POINTER(c_int))(byref(state))
                    control2 = query_interface(control, _IID_IAudioSessionControl2)
                    try:
                        if method(control2, 15)() == 0:  # IsSystemSoundsSession: S_OK
                            continue
                        pid = wintypes.DWORD()
                        method(control2, 14, POINTER(wintypes.DWORD))(byref(pid))
                        if pid.value:
                            found.append((pid.value, state.value == _SESSION_ACTIVE))
                    finally:
                        release(control2)
                finally:
                    release(control)
            return found
        finally:
            release(sessions)
    finally:
        release(manager)


def in_tree(process_id: int, root: int, processes: dict[int, tuple[int, str]]) -> bool:
    """Whether `process_id` is `root` or one of its children's children -
    the tree process loopback captures."""
    for _ in range(16):  # process ids are reused: never loop forever
        if process_id == root:
            return True
        if process_id not in processes:
            return False
        parent = processes[process_id][0]
        if parent == process_id:
            return False
        process_id = parent
    return False


def _peaks(device_id: str) -> list[tuple[int, float]]:
    """(process id, peak) of each app's audio session on one output: the
    session's meter (IAudioMeterInformation, Windows 7+), 0 to 1 - how loud
    it played lately, a number, never the audio itself."""
    manager = activate(device_id, _IID_IAudioSessionManager2)
    try:
        sessions = c_void_p()
        method(manager, 5, POINTER(c_void_p))(byref(sessions))  # GetSessionEnumerator
        try:
            count = c_int()
            method(sessions, 3, POINTER(c_int))(byref(count))
            found = []
            for i in range(count.value):
                control = c_void_p()
                method(sessions, 4, c_int, POINTER(c_void_p))(i, byref(control))
                try:
                    control2 = query_interface(control, _IID_IAudioSessionControl2)
                    try:
                        pid = wintypes.DWORD()
                        method(control2, 14, POINTER(wintypes.DWORD))(byref(pid))
                    finally:
                        release(control2)
                    meter = query_interface(control, _IID_IAudioMeterInformation)
                    try:
                        peak = ctypes.c_float()
                        method(meter, 3, POINTER(ctypes.c_float))(byref(peak))
                    finally:
                        release(meter)
                    if pid.value:
                        found.append((pid.value, peak.value))
                finally:
                    release(control)
            return found
        finally:
            release(sessions)
    finally:
        release(manager)


def app_peak(process_id: int) -> float:
    """How loud the app at `process_id` (with its child processes) plays
    now, by Windows' own meters of its audio sessions: the loudest, 0 to 1;
    0 if it has none, or they can't be read. For telling an app that plays
    from one that's quiet when its capture gets nothing (decision 0076)."""
    try:
        processes = _processes()
        return max(
            (
                peak
                for device in active_devices(Flow.OUTPUT)
                for pid, peak in _peaks(device.id)
                if in_tree(pid, process_id, processes)
            ),
            default=0.0,
        )
    except OSError:
        return 0.0


APP_EXE = "polyglotic.exe"
"""Every packed copy's executable (`tools/package`): the installed app, a
preview or a rehearsal alike."""


def is_polyglotic(
    process_id: int, processes: dict[int, tuple[int, str]], this: int
) -> bool:
    """Whether the app at `process_id` (a top process) is Polyglotic: this
    copy (`this`, its own process - from source, Python), or any other copy
    of it, by its executable. Its own sounds - the sample, a word's - are
    never an app to caption (polyglotic-hq 368)."""
    if process_id == top_process(this, processes):
        return True
    return processes[process_id][1].lower() == APP_EXE


class WindowsAppList:
    """The `AppList` port on Windows."""

    def playing_apps(self) -> list[PlayingApp]:
        processes = _processes()
        this = os.getpid()
        playing: dict[int, bool] = {}
        for device in active_devices(Flow.OUTPUT):
            for pid, active in _sessions(device.id):
                top = top_process(pid, processes)
                playing[top] = playing.get(top, False) or active
        apps = []
        for pid, active in playing.items():
            if pid not in processes:
                continue  # exited since
            if is_polyglotic(pid, processes, this):
                continue  # its own sounds: never an app to caption (368)
            exe = processes[pid][1]
            path = _path(pid)
            category = category_of(exe, path)
            apps.append(
                PlayingApp(pid, exe, active, category, known_name(exe), own_name(path))
            )
        return sorted(apps, key=lambda a: (not a.playing, a.name.lower()))
