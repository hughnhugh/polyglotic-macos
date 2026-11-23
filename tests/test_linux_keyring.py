"""The device token's keyring on Linux, read once a run (polyglotic-hq 561,
decision 0269): a locked keyring shows its password box at most once, and
the app's later questions - many on its interface thread - are answered
from that read. The real locked keyring is `linux_desktop`, in a session
of its own (`.github/workflows/linux.yml`)."""

import os
import threading
import time
import uuid

import pytest

from polyglotic_desktop.platform.linux.secret_service import (
    KeyringRefused,
    NoKeyring,
    SecretService,
    SecretServiceStore,
)
from polyglotic_desktop.ports.credentials import DeviceCredentials

TOKEN = DeviceCredentials("install-561", "pgd_" + "y" * 43)


class CountedKeyring:
    """A keyring that counts its reads - each one, on a locked keyring, a
    password box and a wait of up to PROMPT_SEC on the asking thread."""

    def __init__(self, error: OSError | None = None) -> None:
        self.items: dict[str, tuple[str, bytes]] = {}
        self.error = error
        self.reads = 0

    def read(self, entry: str) -> tuple[str, bytes] | None:
        self.reads += 1
        if self.error:
            raise self.error
        return self.items.get(entry)

    def write(self, entry: str, account: str, secret: bytes) -> None:
        if self.error:
            raise self.error
        self.items[entry] = (account, secret)

    def delete(self, entry: str) -> None:
        if self.error:
            raise self.error
        self.items.pop(entry, None)


def test_the_keyring_is_read_once_a_run() -> None:
    """The app asks whether it's signed in many times, on its interface
    thread: the keyring answers once, and the rest come from that."""
    keyring = CountedKeyring()
    keyring.items["e"] = ("install-561", TOKEN.device_token.encode())
    store = SecretServiceStore("e", keyring, CountedKeyring())
    for _ in range(5):
        assert store.load() == DeviceCredentials("install-561", TOKEN.device_token)
        assert store.install_id() == "install-561"
    assert keyring.reads == 1


def test_a_box_dismissed_isnt_shown_again_that_run() -> None:
    """A locked keyring whose box was dismissed (or left unanswered) used to
    ask again at every question, each holding the interface up to 120 s."""
    keyring = CountedKeyring(KeyringRefused("dismissed"))
    store = SecretServiceStore("e", keyring, CountedKeyring())
    for _ in range(4):
        assert store.load() is None and store.install_id() is None
    assert keyring.reads == 1
    keyring.error = None  # signing in writes the token: the keyring asked again
    store.save(TOKEN)
    assert store.load() == TOKEN and keyring.reads == 1


def test_saves_and_sign_outs_are_what_later_questions_find() -> None:
    keyring = CountedKeyring()
    store = SecretServiceStore("e", keyring, CountedKeyring())
    store.save(TOKEN)
    store.forget()
    assert store.load() is None and store.install_id() == "install-561"
    assert keyring.items["e"] == ("install-561", b"")
    store.delete()
    assert store.load() is None and store.install_id() is None
    assert keyring.reads == 0  # saved first: the keyring never needed reading


def test_two_threads_asking_at_once_read_it_once() -> None:

    opened = threading.Event()

    class SlowKeyring(CountedKeyring):
        def read(self, entry: str) -> tuple[str, bytes] | None:
            opened.wait(5)  # its password box, up
            return super().read(entry)

    keyring = SlowKeyring()
    keyring.items["e"] = ("install-561", b"token")
    store = SecretServiceStore("e", keyring, CountedKeyring())
    answers: list[str | None] = []
    askers = [
        threading.Thread(target=lambda: answers.append(store.install_id()))
        for _ in range(2)
    ]
    for asker in askers:
        asker.start()
    opened.set()
    for asker in askers:
        asker.join(5)
    assert answers == ["install-561", "install-561"] and keyring.reads == 1


@pytest.mark.linux_desktop
@pytest.mark.skipif(
    os.environ.get("POLYGLOTIC_LOCKED_KEYRING") != "1",
    reason="a session of its own: it locks the session's keyring",
)
def test_a_locked_keyring_is_asked_once_and_bounded() -> None:
    """gnome-keyring, its login collection locked, and nobody to answer its
    box: the first question waits at most for the box, and comes back not
    signed in; the next ones don't ask again (561)."""

    entry = f"Polyglotic/test-561-{uuid.uuid4().hex[:8]}"
    nowhere = CountedKeyring(NoKeyring("unused"))
    SecretServiceStore(entry, SecretService(), nowhere).save(TOKEN)
    service = SecretService(prompt_seconds=5)
    connection = service._connect()
    try:
        (collection,) = service._service(connection, "ReadAlias", "s", ("default",))
        service._service(connection, "Lock", "ao", ([collection],))
    finally:
        connection.close()
    store = SecretServiceStore(entry, service, nowhere)
    started = time.monotonic()
    first = store.load()
    asked = time.monotonic()
    again = (store.load(), store.install_id(), store.load())
    done = time.monotonic()
    print(
        f"locked keyring: first answer in {asked - started:.2f} s, the next three in {done - asked:.4f} s"
    )
    assert first is None and again == (None, None, None)
    assert asked - started < 5 + 3  # the box's time, and no more
    assert done - asked < 0.05  # never asked again
