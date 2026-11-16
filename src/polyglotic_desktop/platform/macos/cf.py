"""macOS's Core Foundation and Security frameworks through ctypes, as the
Windows adapters call Windows (decision 0006): no extra dependency.

Only what the Mac's adapters use: strings, data and dictionaries to and
from Python, a value's release, and the frameworks' named constants. The
libraries load on first use, never at import, so this module - and the
adapters' logic, tested with fakes - imports on any OS.

Every `create_*` returns a reference the caller owns: `release` it (the
`owned` context does). A reference this module reads (`text`, `data`)
stays the caller's.
"""

import ctypes
import ctypes.util
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import cache

UTF8 = 0x08000100
"""kCFStringEncodingUTF8."""


class Libraries:
    """Core Foundation and Security, loaded with their calls' types."""

    def __init__(self) -> None:
        self.cf = ctypes.CDLL(_found("CoreFoundation"))
        self.security = ctypes.CDLL(_found("Security"))
        p, index, i32 = ctypes.c_void_p, ctypes.c_long, ctypes.c_int32
        cf, sec = self.cf, self.security
        _typed(cf.CFStringCreateWithCString, p, [p, ctypes.c_char_p, ctypes.c_uint32])
        _typed(cf.CFStringGetLength, index, [p])
        _typed(cf.CFStringGetMaximumSizeForEncoding, index, [index, ctypes.c_uint32])
        _typed(
            cf.CFStringGetCString,
            ctypes.c_bool,
            [p, ctypes.c_char_p, index, ctypes.c_uint32],
        )
        _typed(cf.CFStringGetTypeID, ctypes.c_ulong, [])
        _typed(cf.CFDataCreate, p, [p, ctypes.c_char_p, index])
        _typed(cf.CFDataGetLength, index, [p])
        _typed(cf.CFDataGetBytePtr, p, [p])
        _typed(cf.CFDataGetTypeID, ctypes.c_ulong, [])
        _typed(cf.CFGetTypeID, ctypes.c_ulong, [p])
        _typed(cf.CFDictionaryCreate, p, [p, p, p, index, p, p])
        _typed(cf.CFDictionaryGetValue, p, [p, p])
        _typed(cf.CFRelease, None, [p])
        _typed(cf.CFPreferencesCopyAppValue, p, [p, p])
        _typed(
            cf.CFUserNotificationDisplayAlert,
            i32,
            [ctypes.c_double, ctypes.c_ulong, p, p, p, p, p, p, p, p, p],
        )
        _typed(sec.SecItemCopyMatching, i32, [p, ctypes.POINTER(p)])
        _typed(sec.SecItemAdd, i32, [p, p])
        _typed(sec.SecItemUpdate, i32, [p, p])
        _typed(sec.SecItemDelete, i32, [p])
        _typed(sec.SecCopyErrorMessageString, p, [i32, p])

    def constant(self, name: str, library: str = "security") -> int:
        """A framework's named constant (`kSecClass`, `kCFBooleanTrue`): the
        reference its symbol holds."""
        found = ctypes.c_void_p.in_dll(getattr(self, library), name).value
        if found is None:
            raise OSError(f"macOS: {name} isn't set")
        return found

    def address(self, name: str, library: str = "cf") -> int:
        """Where a framework's named structure is (the dictionaries' call
        backs, which are passed by address)."""
        return ctypes.addressof(ctypes.c_void_p.in_dll(getattr(self, library), name))


def _found(name: str) -> str:
    path = ctypes.util.find_library(name)
    if path is None:
        raise OSError(f"macOS's {name} framework isn't here")
    return path


def _typed(call: object, restype: object, argtypes: list[object]) -> None:
    call.restype = restype  # type: ignore[attr-defined]
    call.argtypes = argtypes  # type: ignore[attr-defined]


@cache
def libraries() -> Libraries:
    """The frameworks, loaded once, on first use."""
    return Libraries()


def release(ref: int | None) -> None:
    if ref:
        libraries().cf.CFRelease(ref)


@contextmanager
def owned(*refs: int | None) -> Iterator[None]:
    """Releases these references when the block ends, however it ends."""
    try:
        yield
    finally:
        for ref in refs:
            release(ref)


def create_string(text: str) -> int:
    ref = libraries().cf.CFStringCreateWithCString(None, text.encode("utf-8"), UTF8)
    if not ref:
        raise OSError("macOS: a string couldn't be made")
    return int(ref)


def create_data(data: bytes) -> int:
    ref = libraries().cf.CFDataCreate(None, data, len(data))
    if not ref:
        raise OSError("macOS: data couldn't be made")
    return int(ref)


def create_dictionary(entries: Mapping[int, int]) -> int:
    """A dictionary of Core Foundation references, each retained by it."""
    libs = libraries()
    count = len(entries)
    keys = (ctypes.c_void_p * count)(*entries.keys())
    values = (ctypes.c_void_p * count)(*entries.values())
    ref = libs.cf.CFDictionaryCreate(
        None,
        keys,
        values,
        count,
        libs.address("kCFTypeDictionaryKeyCallBacks"),
        libs.address("kCFTypeDictionaryValueCallBacks"),
    )
    if not ref:
        raise OSError("macOS: a dictionary couldn't be made")
    return int(ref)


def text(ref: int | None) -> str | None:
    """A string's text; None for no reference, or one that isn't a string."""
    cf = libraries().cf
    if not ref or cf.CFGetTypeID(ref) != cf.CFStringGetTypeID():
        return None
    size = cf.CFStringGetMaximumSizeForEncoding(cf.CFStringGetLength(ref), UTF8) + 1
    buffer = ctypes.create_string_buffer(size)
    if not cf.CFStringGetCString(ref, buffer, size, UTF8):
        return None
    return buffer.value.decode("utf-8")


def data(ref: int | None) -> bytes | None:
    """Data's bytes; None for no reference, or one that isn't data."""
    cf = libraries().cf
    if not ref or cf.CFGetTypeID(ref) != cf.CFDataGetTypeID():
        return None
    length = cf.CFDataGetLength(ref)
    if length == 0:
        return b""
    return ctypes.string_at(cf.CFDataGetBytePtr(ref), length)


def value(dictionary: int, key: int) -> int | None:
    """The value a dictionary has for `key` (the dictionary's own, not
    retained), or None."""
    found = libraries().cf.CFDictionaryGetValue(dictionary, key)
    return int(found) if found else None
