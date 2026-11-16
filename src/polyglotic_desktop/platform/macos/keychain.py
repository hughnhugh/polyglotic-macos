"""The device token in the macOS Keychain (`CredentialStore`): Windows'
Credential Manager's counterpart (`adapters/windows_credentials.py`).

One generic password, service `Polyglotic/device` by default, in the
user's login keychain: its account is the install id, its password the
device token. macOS encrypts it for that user; it's visible in Keychain
Access under "Polyglotic/device". Called through Security.framework's
`SecItem` calls by ctypes (`cf.py`) - **never the `security` command**,
which would put the token in the process list for any process to read
(polyglotic-hq 408).

As on Windows, **signing out keeps the item with an empty password**
(polyglotic-hq 288, decision 0080): the install id stays, so the same
invite code signs this Mac in again. Deleting the item in Keychain
Access, or the macOS user, clears it; then the Mac is a new install to
the server.

The Keychain's own access list trusts the app that made the item. A
build signed differently - each ad-hoc-signed build, until the app has a
stable signature - may make macOS ask the learner to allow it the first
time it reads the item (polyglotic-hq 409's report: to check on a Mac).

The token never appears in an error or a log.
"""

import ctypes
from typing import Protocol

from polyglotic_desktop.platform.macos import cf
from polyglotic_desktop.ports.credentials import DeviceCredentials

SERVICE = "Polyglotic/device"

_NOT_FOUND = -25300  # errSecItemNotFound


class Keychain(Protocol):
    """A generic password per service: the Keychain itself
    (`SecurityKeychain`), or a test's fake."""

    def read(self, service: str) -> tuple[str, bytes] | None:
        """The item's account and password; None if there's no item."""
        ...

    def write(self, service: str, account: str, secret: bytes) -> None:
        """Makes the item, or changes the one there. A change to no bytes
        may leave the old password: macOS' login keychain does (`forget`)."""
        ...

    def delete(self, service: str) -> None:
        """Removes the item, if there is one."""
        ...


class KeychainStore:
    """`CredentialStore` in the Keychain, under `service`."""

    def __init__(
        self, service: str = SERVICE, keychain: Keychain | None = None
    ) -> None:
        self._service = service
        self._keychain = keychain if keychain is not None else SecurityKeychain()

    def load(self) -> DeviceCredentials | None:
        found = self._keychain.read(self._service)
        if found is None:
            return None
        install_id, secret = found
        if not install_id or not secret:
            return None
        return DeviceCredentials(install_id, secret.decode("utf-8"))

    def install_id(self) -> str | None:
        found = self._keychain.read(self._service)
        if found is None:
            return None
        return found[0] or None

    def save(self, credentials: DeviceCredentials) -> None:
        self._keychain.write(
            self._service,
            credentials.install_id,
            credentials.device_token.encode("utf-8"),
        )

    def forget(self) -> None:
        """The token goes; the item stays with the install id and an empty
        password. Made again, not changed: macOS' login keychain takes an
        update to an empty password as no change to it, and the token
        stayed (polyglotic-hq 419's run 2 on GitHub's Mac, 420)."""
        install_id = self.install_id()
        self.delete()
        if install_id is not None:  # else nothing kept, or nothing worth keeping
            self._keychain.write(self._service, install_id, b"")

    def delete(self) -> None:
        """The whole item, install id and all: for tests and trials under a
        service of their own, which leave nothing behind. The app never
        calls it."""
        self._keychain.delete(self._service)


class SecurityKeychain:
    """`Keychain` through Security.framework's `SecItem` calls."""

    def read(self, service: str) -> tuple[str, bytes] | None:
        libs = cf.libraries()
        true = libs.constant("kCFBooleanTrue", "cf")
        query = self._query(
            service,
            {
                libs.constant("kSecMatchLimit"): libs.constant("kSecMatchLimitOne"),
                libs.constant("kSecReturnAttributes"): true,
                libs.constant("kSecReturnData"): true,
            },
        )
        found = ctypes.c_void_p()
        with cf.owned(query):
            status = libs.security.SecItemCopyMatching(query, ctypes.byref(found))
        if status == _NOT_FOUND:
            return None
        if status != 0:
            raise _failed("reading the device token", status)
        with cf.owned(found.value):
            item = int(found.value or 0)
            account = cf.text(cf.value(item, libs.constant("kSecAttrAccount")))
            secret = cf.data(cf.value(item, libs.constant("kSecValueData")))
        return account or "", secret or b""

    def write(self, service: str, account: str, secret: bytes) -> None:
        libs = cf.libraries()
        account_ref, secret_ref = cf.create_string(account), cf.create_data(secret)
        with cf.owned(account_ref, secret_ref):
            changes = cf.create_dictionary(
                {
                    libs.constant("kSecAttrAccount"): account_ref,
                    libs.constant("kSecValueData"): secret_ref,
                }
            )
            query = self._query(service)
            with cf.owned(changes, query):
                status = libs.security.SecItemUpdate(query, changes)
            if status == _NOT_FOUND:
                label = cf.create_string("Polyglotic's device token for its server")
                with cf.owned(label):
                    item = self._query(
                        service,
                        {
                            libs.constant("kSecAttrAccount"): account_ref,
                            libs.constant("kSecValueData"): secret_ref,
                            libs.constant("kSecAttrDescription"): label,
                        },
                    )
                    with cf.owned(item):
                        status = libs.security.SecItemAdd(item, None)
        if status != 0:
            raise _failed("saving the device token", status)

    def delete(self, service: str) -> None:
        query = self._query(service)
        with cf.owned(query):
            status = cf.libraries().security.SecItemDelete(query)
        if status not in (0, _NOT_FOUND):
            raise _failed("deleting the device token", status)

    @staticmethod
    def _query(service: str, more: dict[int, int] | None = None) -> int:
        """A dictionary naming the generic password for `service`, with
        `more` in it (the caller owns the result)."""
        libs = cf.libraries()
        name = cf.create_string(service)
        with cf.owned(name):
            return cf.create_dictionary(
                {
                    libs.constant("kSecClass"): libs.constant(
                        "kSecClassGenericPassword"
                    ),
                    libs.constant("kSecAttrService"): name,
                    **(more or {}),
                }
            )


def _failed(call: str, status: int) -> OSError:
    """The Keychain's own words for `status` - never the token."""
    message = cf.libraries().security.SecCopyErrorMessageString(status, None)
    with cf.owned(message):
        why = cf.text(message) or "unknown"
    return OSError(status, f"Keychain: {call} failed ({why}, {status})")
