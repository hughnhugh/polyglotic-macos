"""The device token in the desktop's keyring (`CredentialStore`) - Windows'
Credential Manager and the Mac's Keychain for Linux (polyglotic-hq 546
section 1.6, 550): the freedesktop Secret Service, which GNOME's keyring
and KDE's (ksecretd, or KWallet's own) both serve on the session bus.

- **The client is jeepney** (pure Python, MIT): a D-Bus message per call,
  on a connection of the call's own - so any thread may ask. Not
  `secretstorage`, which would bring `cryptography` into the app (it uses
  PyNaCl), and not QtDBus, which wants Qt's event loop.
- **The plain session:** the token crosses the session bus - the user's
  own, which no other user can reach - unencrypted, as libsecret's own
  plain mode does; the keyring encrypts it at rest. 550's runs check that
  each keyring accepts it.
- **One item per entry** (`Polyglotic/device`, or a developer's own
  server's): its attributes name the app and the entry, its `account`
  attribute is the install id, its secret the device token. As on Windows
  and the Mac, **signing out keeps the item with an empty secret**
  (polyglotic-hq 288, decision 0080): the install id stays.
- **A locked keyring** asks the learner for its password in the
  desktop's own box (its Prompt), waited for up to PROMPT_SEC - once a
  run: the keyring is read once and the app's later questions answered
  from that (`SecretServiceStore`, 561). Dismissed, or not answered, the
  app isn't signed in (`load` is None) - never a crash; saving says why.
- **No keyring at all** (no session bus, or nothing serving the Secret
  Service: a bare window manager, a session started without one): the
  token is kept in a file only the user can read, in
  `$XDG_STATE_HOME/Polyglotic` (`~/.local/state`), and the log says so.

The token never appears in an error or a log.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Protocol

from polyglotic_desktop.ports.credentials import DeviceCredentials

log = logging.getLogger(__name__)

SERVICE = "Polyglotic/device"
APP_ID = "io.polyglotic.Polyglotic"
SCHEMA = f"{APP_ID}.Device"
"""libsecret's `xdg:schema` attribute: how a keyring's own window groups
the item."""
LABEL = "Polyglotic's device token for its server"
BUS_NAME = "org.freedesktop.secrets"
SERVICE_PATH = "/org/freedesktop/secrets"
CALL_SEC = 10.0
PROMPT_SEC = 120.0
"""How long the learner has to answer the keyring's password box."""
NO_SERVICE = (
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
    "org.freedesktop.DBus.Error.Spawn.ServiceNotFound",
    "org.freedesktop.DBus.Error.Spawn.ChildExited",
)
"""What the bus answers when nothing serves the Secret Service."""


class NoKeyring(OSError):
    """There's no keyring to keep the token in: no session bus, or nothing
    serving the Secret Service on it."""


class KeyringRefused(OSError):
    """The keyring is there but wouldn't open: locked, and its password box
    dismissed or left unanswered - or it answered with an error."""


class Keyring(Protocol):
    """An item per entry: the Secret Service itself (`SecretService`), or a
    test's fake."""

    def read(self, entry: str) -> tuple[str, bytes] | None:
        """The item's account (the install id) and secret; None if there's
        no item. `NoKeyring`, `KeyringRefused`."""
        ...

    def write(self, entry: str, account: str, secret: bytes) -> None:
        """Makes the item, or replaces the one there."""
        ...

    def delete(self, entry: str) -> None:
        """Removes the item, if there is one."""
        ...


def state_folder(
    environ: dict[str, str] | None = None, home: Path | None = None
) -> Path:
    """`$XDG_STATE_HOME/Polyglotic`, by default `~/.local/state/Polyglotic`."""
    env = os.environ if environ is None else environ
    given = env.get("XDG_STATE_HOME", "")
    base = Path(given) if given and Path(given).is_absolute() else None
    return (base or (home or Path.home()) / ".local" / "state") / "Polyglotic"


class FileKeyring:
    """`Keyring` as one JSON file per user, only the user can read or write
    (0600, in a 0700 folder): for a session with no keyring at all."""

    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or state_folder()

    def _path(self, entry: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in entry)
        return self.folder / f"{safe}.json"

    def read(self, entry: str) -> tuple[str, bytes] | None:
        try:
            data = json.loads(self._path(entry).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise KeyringRefused("the token's file can't be read") from None
        account, secret = data.get("account"), data.get("secret")
        if not isinstance(account, str) or not isinstance(secret, str):
            return None
        return account, secret.encode("utf-8")

    def write(self, entry: str, account: str, secret: bytes) -> None:
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(entry)
        part = path.with_suffix(".part")
        text = json.dumps({"account": account, "secret": secret.decode("utf-8")})
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(part, path)

    def delete(self, entry: str) -> None:
        self._path(entry).unlink(missing_ok=True)


class SecretService:
    """`Keyring` on the Secret Service, through jeepney (imported when first
    used: Linux only)."""

    def __init__(self, prompt_seconds: float = PROMPT_SEC) -> None:
        self._prompt_seconds = prompt_seconds

    # -- the D-Bus calls ---------------------------------------------------------

    def _connect(self) -> Any:
        try:
            from jeepney.io.blocking import open_dbus_connection
        except ImportError as e:
            raise NoKeyring("jeepney isn't installed") from e
        try:
            return open_dbus_connection(bus="SESSION")
        except (KeyError, OSError, ValueError) as e:  # no address, or no bus
            raise NoKeyring(f"no session bus ({type(e).__name__})") from None

    def _call(
        self,
        connection: Any,
        path: str,
        interface: str,
        method: str,
        signature: str | None = None,
        body: tuple[Any, ...] = (),
    ) -> tuple[Any, ...]:
        from jeepney import DBusAddress, new_method_call
        from jeepney.wrappers import DBusErrorResponse, unwrap_msg

        address = DBusAddress(path, bus_name=BUS_NAME, interface=interface)
        message = new_method_call(address, method, signature, body)
        try:
            reply = connection.send_and_get_reply(message, timeout=CALL_SEC)
            return tuple(unwrap_msg(reply))
        except DBusErrorResponse as e:
            if e.name in NO_SERVICE:
                raise NoKeyring(f"no keyring ({e.name})") from None
            raise KeyringRefused(f"the keyring refused {method} ({e.name})") from None
        except TimeoutError:
            raise KeyringRefused(f"the keyring didn't answer {method}") from None

    def _service(self, connection: Any, method: str, signature: str | None = None,
                 body: tuple[Any, ...] = ()) -> tuple[Any, ...]:  # fmt: skip
        return self._call(
            connection, SERVICE_PATH, "org.freedesktop.Secret.Service", method,
            signature, body,
        )  # fmt: skip

    def _session(self, connection: Any) -> str:
        """A plain session: the secret crosses the user's own bus as it is."""
        _output, session = self._service(
            connection, "OpenSession", "sv", ("plain", ("s", ""))
        )
        return str(session)

    def _prompted(self, connection: Any, prompt: str) -> Any:
        """Runs a Prompt (the keyring's own password box) and waits for the
        learner's answer; `KeyringRefused` if dismissed or not answered."""
        if prompt in ("", "/"):
            return None
        from jeepney import MatchRule, message_bus
        from jeepney.io.blocking import Proxy

        rule = MatchRule(
            type="signal",
            interface="org.freedesktop.Secret.Prompt",
            member="Completed",
            path=prompt,
        )
        Proxy(message_bus, connection).AddMatch(rule)
        with connection.filter(rule) as signals:
            self._call(connection, prompt, "org.freedesktop.Secret.Prompt",
                       "Prompt", "s", ("",))  # fmt: skip
            try:
                signal = connection.recv_until_filtered(
                    signals, timeout=self._prompt_seconds
                )
            except TimeoutError:
                raise KeyringRefused(
                    "the keyring's password box wasn't answered"
                ) from None
        dismissed, result = signal.body
        if dismissed:
            raise KeyringRefused("the keyring's password box was dismissed")
        return result

    def _unlocked(self, connection: Any, paths: list[str]) -> None:
        if not paths:
            return
        _done, prompt = self._service(connection, "Unlock", "ao", (paths,))
        self._prompted(connection, str(prompt))

    @staticmethod
    def _attributes(entry: str) -> dict[str, str]:
        return {"xdg:schema": SCHEMA, "application": APP_ID, "service": entry}

    def _collection(self, connection: Any) -> str:
        """The default collection ("Login"), opened - made first where the
        keyring has none yet (its own box asks for a password then)."""
        (found,) = self._service(connection, "ReadAlias", "s", ("default",))
        collection = str(found)
        if collection in ("", "/"):
            label = {"org.freedesktop.Secret.Collection.Label": ("s", "Login")}
            made, prompt = self._service(
                connection, "CreateCollection", "a{sv}s", (label, "default")
            )
            collection = str(made)
            if collection in ("", "/"):
                result = self._prompted(connection, str(prompt))
                collection = str(result[1]) if result else ""
            if collection in ("", "/"):
                raise KeyringRefused("the keyring has no collection to keep it in")
        self._unlocked(connection, [collection])
        return collection

    def _items(self, connection: Any, entry: str) -> list[str]:
        unlocked, locked = self._service(
            connection, "SearchItems", "a{ss}", (self._attributes(entry),)
        )
        self._unlocked(connection, list(locked))
        return [*unlocked, *locked]

    # -- Keyring -----------------------------------------------------------------

    def read(self, entry: str) -> tuple[str, bytes] | None:
        connection = self._connect()
        try:
            items = self._items(connection, entry)
            if not items:
                return None
            session = self._session(connection)
            (secrets,) = self._service(
                connection, "GetSecrets", "aoo", (items[:1], session)
            )
            secret = secrets.get(items[0])
            if secret is None:
                return None
            (attributes,) = self._call(
                connection, items[0], "org.freedesktop.DBus.Properties", "Get",
                "ss", ("org.freedesktop.Secret.Item", "Attributes"),
            )  # fmt: skip
            account = dict(attributes[1]).get("account", "")
            return str(account), bytes(secret[2])
        finally:
            connection.close()

    def write(self, entry: str, account: str, secret: bytes) -> None:
        connection = self._connect()
        try:
            collection = self._collection(connection)
            session = self._session(connection)
            attributes = {**self._attributes(entry), "account": account}
            properties = {
                "org.freedesktop.Secret.Item.Label": ("s", LABEL),
                "org.freedesktop.Secret.Item.Attributes": ("a{ss}", attributes),
            }
            _item, prompt = self._call(
                connection, collection, "org.freedesktop.Secret.Collection",
                "CreateItem", "a{sv}(oayays)b",
                (properties, (session, b"", secret, "text/plain"), True),
            )  # fmt: skip
            self._prompted(connection, str(prompt))
        finally:
            connection.close()

    def delete(self, entry: str) -> None:
        connection = self._connect()
        try:
            for item in self._items(connection, entry):
                (prompt,) = self._call(
                    connection, item, "org.freedesktop.Secret.Item", "Delete"
                )
                self._prompted(connection, str(prompt))
        finally:
            connection.close()


class SecretServiceStore:
    """`CredentialStore` in the desktop's keyring under `entry` - or, when
    there's no keyring at all, in a file only the user can read.

    **The keyring is read once a run** (polyglotic-hq 561, decision 0269):
    the first question - the start's, before the window is built - reads
    it, and every later one, on any thread, is answered from what that
    read found, as the app's own saves and sign-outs change it. So a locked
    keyring shows its password box at most once a run, at the start: the
    app asks whether it's signed in on its interface thread many times
    (Home's state, feedback, the sign-in), and each used to read the
    keyring again - a locked one asking again each time and holding the
    interface up to PROMPT_SEC, after a box dismissed or left unanswered
    too. A read the keyring refused is kept as "not signed in" for the run;
    signing in writes the token, which asks the keyring again."""

    def __init__(
        self,
        entry: str = SERVICE,
        keyring: Keyring | None = None,
        fallback: Keyring | None = None,
    ) -> None:
        self._entry = entry
        self._keyring = keyring if keyring is not None else SecretService()
        self._fallback = fallback if fallback is not None else FileKeyring()
        self._said: set[str] = set()
        self._lock = threading.Lock()
        """One read at a time: a second asker waits for the first's answer."""
        self._known: tuple[str, bytes] | None = None
        self._read_yet = False

    def _say(self, kind: str, error: OSError) -> None:
        """One log line per kind of trouble: its type and words (never the
        token: no message here holds it)."""
        if kind not in self._said:
            self._said.add(kind)
            log.warning("credentials: %s (%s: %s)", kind, type(error).__name__, error)

    def _read(self) -> tuple[str, bytes] | None:
        """What the keyring holds, as the run's one read found it."""
        with self._lock:
            if not self._read_yet:
                self._known, self._read_yet = self._ask(), True
            return self._known

    def _ask(self) -> tuple[str, bytes] | None:
        try:
            return self._keyring.read(self._entry)
        except NoKeyring as e:
            self._say("no keyring: the token is kept in a file only you can read", e)
            try:
                return self._fallback.read(self._entry)
            except OSError as f:
                self._say("the token's file can't be read", f)
                return None
        except OSError as e:  # locked and not opened, or an error: not signed in
            self._say("the keyring wouldn't open: not signed in", e)
            return None

    def _write(self, account: str, secret: bytes) -> None:
        with self._lock:
            try:
                self._keyring.write(self._entry, account, secret)
            except NoKeyring as e:
                self._say(
                    "no keyring: the token is kept in a file only you can read", e
                )
                self._fallback.write(self._entry, account, secret)
            self._known, self._read_yet = (account, secret), True

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
        return (found[0] or None) if found is not None else None

    def save(self, credentials: DeviceCredentials) -> None:
        self._write(credentials.install_id, credentials.device_token.encode("utf-8"))

    def forget(self) -> None:
        """The token goes; the item stays with the install id and an empty
        secret (decision 0080)."""
        install_id = self.install_id()
        if install_id is not None:
            self._write(install_id, b"")

    def delete(self) -> None:
        """The whole item, install id and all: for tests and trials under an
        entry of their own, which leave nothing behind. The app never calls
        it."""
        with self._lock:
            try:
                self._keyring.delete(self._entry)
            except NoKeyring:
                self._fallback.delete(self._entry)
            self._known, self._read_yet = None, True
