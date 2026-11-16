"""The device token in Windows Credential Manager (adapters.windows_credentials).

Uses the real Credential Manager of whoever runs the tests, under a target
name of its own that is deleted afterwards; never the app's own entry.

Signing out forgets the token and keeps the install id (polyglotic-hq 288,
decision 0080): the same invite code signs this PC in again only with the
install id it was used with.
"""

import sys
import uuid
from collections.abc import Iterator

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.adapters.windows_credentials import WindowsCredentialStore
from polyglotic_desktop.ports.credentials import DeviceCredentials

TOKEN = "pgd_TEST0TOKEN0" + "x" * 29


@pytest.fixture
def store() -> Iterator[WindowsCredentialStore]:
    test_store = WindowsCredentialStore(f"Polyglotic-test/{uuid.uuid4()}")
    yield test_store
    test_store.delete()  # forget() keeps the install id: nothing may stay


def test_nothing_saved_yet(store: WindowsCredentialStore) -> None:
    assert store.load() is None


def test_saved_credentials_come_back(store: WindowsCredentialStore) -> None:
    install_id = str(uuid.uuid4())
    store.save(DeviceCredentials(install_id, TOKEN))
    assert store.load() == DeviceCredentials(install_id, TOKEN)
    store.save(DeviceCredentials(install_id, TOKEN + "2"))  # replaced in place
    loaded = store.load()
    assert loaded is not None and loaded.device_token == TOKEN + "2"


def test_forgetting_the_token_keeps_the_install_id(
    store: WindowsCredentialStore,
) -> None:
    """Before 288, signing out deleted the install id with the token, so the
    next code came from a "new PC" - and a code that signs its install in
    again (server decision 0057) couldn't."""
    install_id = str(uuid.uuid4())
    assert store.install_id() is None
    store.save(DeviceCredentials(install_id, TOKEN))
    assert store.install_id() == install_id
    store.forget()
    assert store.load() is None  # signed out
    assert store.install_id() == install_id  # but the same install
    store.forget()  # nothing more to forget: no error
    assert store.install_id() == install_id
    store.save(DeviceCredentials(install_id, TOKEN + "2"))  # signed in again
    assert store.load() == DeviceCredentials(install_id, TOKEN + "2")


def test_forgetting_with_nothing_saved_and_deleting(
    store: WindowsCredentialStore,
) -> None:
    store.forget()  # nothing saved: nothing made
    assert store.install_id() is None and store.load() is None
    store.save(DeviceCredentials(str(uuid.uuid4()), TOKEN))
    store.delete()
    assert store.install_id() is None and store.load() is None
    store.delete()  # nothing to delete: no error


def test_the_token_stays_out_of_repr() -> None:
    assert TOKEN not in repr(DeviceCredentials("id", TOKEN))
