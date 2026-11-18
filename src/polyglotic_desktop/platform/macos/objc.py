"""Objective-C's runtime through ctypes (polyglotic-hq 428), as `cf.py` is
Core Foundation's: no extra dependency (decision 0006). The Mac's voices
(AVFoundation's `AVSpeechSynthesizer`) and starting at sign-in
(ServiceManagement's `SMAppService`) are Objective-C only.

- `send` sends a message with its argument and result types stated - on
  Apple silicon `objc_msgSend` must be called through the exact type of
  the method it reaches;
- `Block` is a block (`^(id buffer)`) a Python function stands behind,
  global so that the framework never copies it;
- `pool` is an autorelease pool, for work on a thread of the app's own;
- strings cross as Core Foundation's (`cf`): an `NSString` is a
  `CFString`.

The libraries load on first use, never at import, so this module imports
on any OS.
"""

import ctypes
import ctypes.util
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import cache
from typing import Any

from polyglotic_desktop.platform.macos import cf

_BLOCK_IS_GLOBAL = 1 << 28
_BLOCK_HAS_SIGNATURE = 1 << 30


class _Runtime:
    def __init__(self) -> None:
        self.objc = ctypes.CDLL(_found("objc"))
        self.system = ctypes.CDLL(_found("System"))
        p = ctypes.c_void_p
        for call, restype, argtypes in (
            (self.objc.objc_getClass, p, [ctypes.c_char_p]),
            (self.objc.sel_registerName, p, [ctypes.c_char_p]),
            (self.objc.objc_autoreleasePoolPush, p, []),
            (self.objc.objc_autoreleasePoolPop, None, [p]),
        ):
            call.restype = restype
            call.argtypes = argtypes
        found = ctypes.cast(self.objc.objc_msgSend, p).value
        if not found:
            raise OSError("macOS's objc_msgSend isn't here")
        self.msg_send: int = found
        self.global_block = ctypes.addressof(
            ctypes.c_void_p.in_dll(self.system, "_NSConcreteGlobalBlock")
        )


def _found(name: str) -> str:
    path = ctypes.util.find_library(name)
    if path is None:
        raise OSError(f"macOS's {name} library isn't here")
    return path


@cache
def runtime() -> _Runtime:
    return _Runtime()


def load(framework: str) -> None:
    """Loads a framework, so that its classes exist."""
    _load(framework)


@cache
def _load(framework: str) -> ctypes.CDLL:
    return ctypes.CDLL(_found(framework))


def cls(name: str) -> int:
    """A class by name; OSError if this macOS hasn't it."""
    found = runtime().objc.objc_getClass(name.encode())
    if not found:
        raise OSError(f"macOS has no {name}")
    return int(found)


@cache
def _selector(name: str) -> int:
    return int(runtime().objc.sel_registerName(name.encode()))


@cache
def _typed(restype: Any, argtypes: tuple[Any, ...]) -> Callable[..., Any]:
    prototype = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)
    return prototype(runtime().msg_send)


def send(
    receiver: int | None,
    selector: str,
    *args: object,
    restype: Any = ctypes.c_void_p,
    argtypes: Sequence[Any] = (),
) -> Any:
    """`[receiver selector:args...]`, typed as stated (an object by default:
    `c_void_p`, read as an int or None)."""
    if len(args) != len(argtypes):
        raise TypeError(f"{selector}: {len(args)} arguments, {len(argtypes)} types")
    return _typed(restype, tuple(argtypes))(receiver, _selector(selector), *args)


def text(ref: int | None) -> str | None:
    """An `NSString`'s text (None for nil)."""
    return cf.text(ref)


def string(value: str) -> int:
    """An `NSString` the caller owns: `cf.release` it."""
    return cf.create_string(value)


def items(array: int | None) -> list[int]:
    """An `NSArray`'s objects, in order (none for nil)."""
    if not array:
        return []
    count = send(array, "count", restype=ctypes.c_ulong)
    return [
        int(send(array, "objectAtIndex:", i, argtypes=[ctypes.c_ulong]) or 0)
        for i in range(count)
    ]


@contextmanager
def pool() -> Iterator[None]:
    """An autorelease pool for the block: what macOS hands back autoreleased
    on an app's own thread is freed when it ends."""
    lib = runtime().objc
    token = lib.objc_autoreleasePoolPush()
    try:
        yield
    finally:
        lib.objc_autoreleasePoolPop(token)


class _Descriptor(ctypes.Structure):
    _fields_ = (
        ("reserved", ctypes.c_ulong),
        ("size", ctypes.c_ulong),
        ("signature", ctypes.c_char_p),
    )


class _Literal(ctypes.Structure):
    _fields_ = (
        ("isa", ctypes.c_void_p),
        ("flags", ctypes.c_int32),
        ("reserved", ctypes.c_int32),
        ("invoke", ctypes.c_void_p),
        ("descriptor", ctypes.POINTER(_Descriptor)),
    )


_OBJECT_BLOCK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)


class Block:
    """A block taking one object and returning nothing (`void (^)(id)`),
    calling `call` with the object (an int, 0 for nil) on whatever thread
    the framework calls it. Global: the framework's copies are this one,
    so it must outlive every call - keep it while it can be called."""

    def __init__(self, call: Callable[[int], None]) -> None:
        self._invoke = _OBJECT_BLOCK(lambda _block, value: call(int(value or 0)))
        self._descriptor = _Descriptor(0, ctypes.sizeof(_Literal), b"v16@?0@8")
        self._literal = _Literal(
            runtime().global_block,
            _BLOCK_IS_GLOBAL | _BLOCK_HAS_SIGNATURE,
            0,
            ctypes.cast(self._invoke, ctypes.c_void_p).value,
            ctypes.pointer(self._descriptor),
        )

    @property
    def address(self) -> int:
        return ctypes.addressof(self._literal)


_FLAG_BLOCK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool)


class FlagBlock:
    """A block taking one yes or no and returning nothing (`void
    (^)(BOOL)`), calling `call` with it on whatever thread the framework
    calls it - AVFoundation's answer to a permission asked (polyglotic-hq
    478). Global, as `Block`: keep it while it can be called."""

    def __init__(self, call: Callable[[bool], None]) -> None:
        self._invoke = _FLAG_BLOCK(lambda _block, value: call(bool(value)))
        self._descriptor = _Descriptor(0, ctypes.sizeof(_Literal), b"v12@?0B8")
        self._literal = _Literal(
            runtime().global_block,
            _BLOCK_IS_GLOBAL | _BLOCK_HAS_SIGNATURE,
            0,
            ctypes.cast(self._invoke, ctypes.c_void_p).value,
            ctypes.pointer(self._descriptor),
        )

    @property
    def address(self) -> int:
        return ctypes.addressof(self._literal)
