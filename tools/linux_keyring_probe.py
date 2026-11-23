r"""Which keyring answers the Secret Service, and whether it takes the plain
session the app uses (polyglotic-hq 546 section 1.6, 550): on GitHub's
runner, inside a session where one keyring runs - gnome-keyring, or KDE's
(ksecretd or kwalletd6).

    python -m tools.linux_keyring_probe NAME OUT.json

Asks the bus who owns `org.freedesktop.secrets`, opens a plain session,
then keeps, reads and deletes a token under an entry of its own through
the app's own store (`platform/linux/secret_service.py`), its password box
given 20 s - nobody answers one here, so a keyring that asks is said, not
waited for. Prints and writes what each step found; exit 0 whatever it
found (a finding, not a failure).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


def main(argv: list[str]) -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith(
        "linux"
    ):
        sys.exit("550: this runs only on GitHub's Linux runners")
    name, out = argv[0], Path(argv[1])
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    from jeepney.wrappers import unwrap_msg

    from polyglotic_desktop.platform.linux.secret_service import (
        FileKeyring,
        NoKeyring,
        SecretService,
        SecretServiceStore,
    )
    from polyglotic_desktop.ports.credentials import DeviceCredentials

    found: dict[str, Any] = {"keyring": name}
    bus = open_dbus_connection(bus="SESSION")
    try:
        dbus = DBusAddress(
            "/org/freedesktop/DBus", "org.freedesktop.DBus", "org.freedesktop.DBus"
        )
        owner = new_method_call(dbus, "GetNameOwner", "s", ("org.freedesktop.secrets",))
        found["owner"] = str(unwrap_msg(bus.send_and_get_reply(owner, timeout=10))[0])
        pid = new_method_call(
            dbus, "GetConnectionUnixProcessID", "s", (found["owner"],)
        )
        process = int(unwrap_msg(bus.send_and_get_reply(pid, timeout=10))[0])
        found["program"] = Path(f"/proc/{process}/comm").read_text().strip()
    except Exception as error:  # noqa: BLE001 - a finding
        found["owner"] = f"none: {type(error).__name__}: {error}"
    try:
        service = DBusAddress(
            "/org/freedesktop/secrets",
            "org.freedesktop.secrets",
            "org.freedesktop.Secret.Service",
        )
        opened = new_method_call(service, "OpenSession", "sv", ("plain", ("s", "")))
        session = unwrap_msg(bus.send_and_get_reply(opened, timeout=20))[1]
        found["plain_session"] = f"accepted ({session})"
    except Exception as error:  # noqa: BLE001 - a finding
        found["plain_session"] = f"refused: {type(error).__name__}: {error}"
    finally:
        bus.close()

    entry = f"Polyglotic/probe-550-{uuid.uuid4().hex[:8]}"
    token = DeviceCredentials("install-probe-550", "pgd_" + "p" * 43)
    keyring = SecretService(prompt_seconds=20)
    store = SecretServiceStore(entry, keyring, FileKeyring(Path("/nonexistent-550")))
    try:
        keyring.write(entry, token.install_id, token.device_token.encode())
        found["kept"] = "yes"
        read = keyring.read(entry)
        found["read_back"] = (
            "the same"
            if read and read[1] == token.device_token.encode()
            else repr(read is not None)
        )
        store.forget()
        found["signed_out_keeps_install_id"] = store.install_id() == token.install_id
        keyring.delete(entry)
        found["deleted"] = keyring.read(entry) is None
    except NoKeyring as error:
        found["kept"] = f"no keyring: {error}"
    except OSError as error:
        found["kept"] = f"refused: {type(error).__name__}: {error}"
    text = json.dumps(found, indent=1)
    print(text)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
