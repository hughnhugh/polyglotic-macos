"""Calling Windows' COM audio interfaces through ctypes.

Just enough COM for Core Audio: GUIDs, calling a method by its slot in an
object's vtable, releasing objects, and a multithreaded COM apartment per
thread. From the proof of concept's `audio_devices.py`.
"""

import ctypes
import threading
from collections.abc import Callable
from ctypes import POINTER, byref, c_uint, c_void_p, wintypes
from typing import Any

ole32 = ctypes.WinDLL("ole32")
ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long  # checked by hand: S_FALSE is fine
ole32.CoCreateInstance.argtypes = [
    c_void_p,
    c_void_p,
    wintypes.DWORD,
    c_void_p,
    c_void_p,
]
ole32.CoCreateInstance.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [c_void_p]
ole32.PropVariantClear.argtypes = [c_void_p]
ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, c_void_p]

COINIT_MULTITHREADED = 0
RPC_E_CHANGED_MODE = -2147417850  # COM already set up single-threaded: usable as it is
CLSCTX_ALL = 23
E_NOINTERFACE = -2147467262
VT_LPWSTR = 31
VT_BLOB = 65


class GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        guid = cls()
        ole32.CLSIDFromString(text, byref(guid))
        return guid

    def same(self, other: "GUID") -> bool:
        return bytes(self) == bytes(other)


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    """A PROPVARIANT on 64-bit Windows: the type, then a 16-byte union -
    read as a pointer (a string) or as a BLOB's size and data."""

    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("value", c_void_p),
        ("value2", c_void_p),
    ]


_apartment = threading.local()


def ensure_com() -> None:
    """Joins this thread to the multithreaded COM apartment, once."""
    if getattr(_apartment, "ready", False):
        return
    result = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    if result < 0 and result != RPC_E_CHANGED_MODE:
        raise OSError(f"CoInitializeEx failed: {result & 0xFFFFFFFF:#x}")
    _apartment.ready = True


def method(obj: c_void_p, index: int, *argtypes: Any) -> Callable[..., Any]:
    """COM method `index` of `obj` (its vtable's slot), callable with the
    rest of its arguments; raises OSError on a failed HRESULT."""
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    function = prototype(vtable[index])
    return lambda *args: function(obj, *args)


def release(obj: c_void_p | None) -> None:
    if obj:
        vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        ctypes.WINFUNCTYPE(c_uint, c_void_p)(vtable[2])(obj)


def query_interface(obj: c_void_p, iid: GUID) -> c_void_p:
    out = c_void_p()
    method(obj, 0, POINTER(GUID), POINTER(c_void_p))(byref(iid), byref(out))
    return out
