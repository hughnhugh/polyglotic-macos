"""The device token in Windows Credential Manager (`CredentialStore`).

One generic credential, `Polyglotic/device` by default, for the signed-in
Windows user on this PC: its user name is the install id, its secret the
device token. Windows encrypts it for that user (DPAPI); it's visible in
Control Panel > Credential Manager > Windows Credentials. Called through
ctypes (`advapi32`'s `CredWriteW`, `CredReadW`, `CredDeleteW`), as the
capture code calls Windows (decision 0006) - no extra dependency.

**Signing out keeps the credential with an empty secret** (polyglotic-hq
288, decision 0080): the install id stays, so the same invite code signs
this PC in again. Kept per Windows user, on this PC only (not roamed), and
untouched by the installer: updating, reinstalling and uninstalling keep
it. Deleting it in Credential Manager - or the Windows user, or a reset -
clears it; then the PC is a new install to the server.

The token never appears in an error or a log.
"""

import ctypes
from ctypes import wintypes

from polyglotic_desktop.ports.credentials import DeviceCredentials

TARGET = "Polyglotic/device"

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2  # this user, this PC; not roamed to others
_ERROR_NOT_FOUND = 1168


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_CredWrite = _advapi32.CredWriteW
_CredWrite.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
_CredWrite.restype = wintypes.BOOL
_CredRead = _advapi32.CredReadW
_CredRead.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.POINTER(_Credential)),
]
_CredRead.restype = wintypes.BOOL
_CredDelete = _advapi32.CredDeleteW
_CredDelete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_CredDelete.restype = wintypes.BOOL
_CredFree = _advapi32.CredFree
_CredFree.argtypes = [ctypes.c_void_p]
_CredFree.restype = None


def _failed(call: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(
        code, f"Credential Manager: {call} failed ({ctypes.FormatError(code)})"
    )


class WindowsCredentialStore:
    """`CredentialStore` in Windows Credential Manager, under `target`."""

    def __init__(self, target: str = TARGET) -> None:
        self._target = target

    def load(self) -> DeviceCredentials | None:
        found = self._read()
        if found is None:
            return None
        install_id, secret = found
        if not install_id or not secret:
            return None
        return DeviceCredentials(install_id, secret.decode("utf-8"))

    def install_id(self) -> str | None:
        found = self._read()
        if found is None:
            return None
        return found[0] or None

    def save(self, credentials: DeviceCredentials) -> None:
        self._write(credentials.install_id, credentials.device_token.encode("utf-8"))

    def forget(self) -> None:
        """The token goes; the credential stays with the install id and an
        empty secret (an app before 288 reads that as signed out)."""
        install_id = self.install_id()
        if install_id is None:  # nothing kept, or nothing worth keeping
            self.delete()
            return
        self._write(install_id, b"")

    def delete(self) -> None:
        """The whole credential, install id and all: for tests and trials
        under a target of their own, which leave nothing behind. The app
        never calls it."""
        deleted = _CredDelete(self._target, _CRED_TYPE_GENERIC, 0)
        if not deleted and ctypes.get_last_error() != _ERROR_NOT_FOUND:
            raise _failed("deleting the device token")

    def _read(self) -> tuple[str, bytes] | None:
        """The credential's user name (the install id) and secret (the token,
        or nothing once signed out); None if there's no credential."""
        found = ctypes.POINTER(_Credential)()
        if not _CredRead(self._target, _CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                return None
            raise _failed("reading the device token")
        try:
            credential = found.contents
            secret = ctypes.string_at(
                credential.CredentialBlob, credential.CredentialBlobSize
            )
            return credential.UserName or "", secret
        finally:
            _CredFree(found)

    def _write(self, install_id: str, secret: bytes) -> None:
        blob = (ctypes.c_ubyte * len(secret)).from_buffer_copy(secret)
        credential = _Credential(
            Type=_CRED_TYPE_GENERIC,
            TargetName=self._target,
            Comment="Polyglotic's device token for its server",
            CredentialBlobSize=len(secret),
            CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
            if secret
            else None,
            Persist=_CRED_PERSIST_LOCAL_MACHINE,
            UserName=install_id,
        )
        if not _CredWrite(ctypes.byref(credential), 0):
            raise _failed("saving the device token")
