"""The tray's menu as a Linux desktop's tray gets it (polyglotic-hq 571): over
D-Bus, from another process, as KDE's tray and GNOME's AppIndicator read it.

    uv run --no-sync python -m tools.linux_tray_menu OUT.json [--pid PID] [--click LABEL]
    uv run --no-sync python -m tools.linux_tray_menu OUT.json --host

Finds the app's StatusNotifierItem through the desktop's watcher
(`org.kde.StatusNotifierWatcher`), reads its `Menu`, says "about to show"
as a tray does before it draws it, reads the whole layout
(`com.canonical.dbusmenu.GetLayout`) and writes every item - its label,
whether it's shown, enabled, checked, a separator or a submenu - to OUT.
`--click LABEL` then clicks that item as a tray does (`Event clicked`).
Exits 0 when the menu was read, 1 when there's no watcher or no item.

Linux only (jeepney); run on GitHub's runners by `tools/linux_manners_check.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

WATCHER = ("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
ITEM = "org.kde.StatusNotifierItem"
MENU = "com.canonical.dbusmenu"


def _item(node: Any) -> dict[str, Any]:
    """One `(ia{sv}av)` of the layout, its children within."""
    if len(node) == 2 and isinstance(node[0], str):  # a variant: (signature, value)
        node = node[1]
    number, props, children = node
    plain = {key: value[1] for key, value in props.items()}
    return {
        "id": number,
        "label": str(plain.get("label", "")).split("\t", 1)[0].replace("_", ""),
        "visible": bool(plain.get("visible", True)),
        "enabled": bool(plain.get("enabled", True)),
        "separator": plain.get("type") == "separator",
        "toggle": plain.get("toggle-type", ""),
        "checked": plain.get("toggle-state", 0) == 1,
        "submenu": plain.get("children-display") == "submenu",
        "children": [_item(child) for child in children],
    }


def read(pid: int | None, click: str | None, wait: float = 20.0) -> dict[str, Any]:
    if sys.platform != "linux":
        raise SystemExit("Linux only")
    from jeepney import DBusAddress, Properties, new_method_call
    from jeepney.io.blocking import open_dbus_connection

    found: dict[str, Any] = {"watcher": False, "items": []}
    with open_dbus_connection(bus="SESSION") as bus:
        watcher = DBusAddress(WATCHER[1], bus_name=WATCHER[0], interface=WATCHER[0])
        deadline = time.monotonic() + wait
        items: list[str] = []
        while time.monotonic() < deadline:
            try:
                reply = bus.send_and_get_reply(
                    Properties(watcher).get("RegisteredStatusNotifierItems"), timeout=3
                )
                found["watcher"] = True
                items = list(reply.body[0][1])
                host = bus.send_and_get_reply(
                    Properties(watcher).get("IsStatusNotifierHostRegistered"), timeout=3
                )
                found["host_registered"] = bool(host.body[0][1])
            except Exception as error:  # noqa: BLE001 - said in OUT
                found["error"] = f"{type(error).__name__}: {error}"
            if items:
                break
            time.sleep(0.5)
        found["items"] = items
        ours = [i for i in items if pid is not None and f"-{pid}-" in i] or items[:1]
        if not ours:
            return found
        service, path = _where(ours[0])
        item = DBusAddress(path, bus_name=service, interface=ITEM)
        for name in ("Id", "Title", "Status", "Menu", "ItemIsMenu"):
            try:
                value = bus.send_and_get_reply(Properties(item).get(name), timeout=3)
                found[name.lower()] = value.body[0][1]
            except Exception as error:  # noqa: BLE001 - said in OUT
                found[name.lower()] = f"unread: {error}"
        menu_path = found.get("menu")
        if not isinstance(menu_path, str) or not menu_path.startswith("/"):
            return found
        menu = DBusAddress(menu_path, bus_name=service, interface=MENU)
        bus.send_and_get_reply(
            new_method_call(menu, "AboutToShow", "i", (0,)), timeout=5
        )
        reply = bus.send_and_get_reply(
            new_method_call(menu, "GetLayout", "iias", (0, -1, [])), timeout=5
        )
        found["revision"] = reply.body[0]
        found["layout"] = _item(reply.body[1])
        if click:
            target = next(
                (x for x in _flat(found["layout"]) if x["label"].startswith(click)),
                None,
            )
            found["clicked"] = None if target is None else target["label"]
            if target is not None:
                event = new_method_call(
                    menu, "Event", "isvu", (target["id"], "clicked", ("i", 0), 0)
                )
                bus.send_and_get_reply(event, timeout=5)
    return found


def _where(item: str) -> tuple[str, str]:
    """A watcher's item as (bus name, object path): KDE's lists
    `name/path` (or the name alone: `/StatusNotifierItem`), GNOME's
    AppIndicator extension `name@path`."""
    if "@" in item:
        service, _, path = item.partition("@")
    else:
        service, _, path = item.partition("/")
        path = "/" + path if path else ""
    return service, path or "/StatusNotifierItem"


def host(out: Path) -> int:
    """A stand-in tray host for the desktop's watcher, where no tray of the
    desktop's registered one (KDE's watcher without Plasma's shell): it
    holds `org.kde.StatusNotifierHost-<pid>` and stays until it's ended,
    so Qt sees a tray. Does nothing where a host is registered already, or
    there's no watcher."""
    if sys.platform != "linux":
        raise SystemExit("Linux only")
    import os

    from jeepney import DBusAddress, Properties, new_method_call
    from jeepney.bus_messages import message_bus
    from jeepney.io.blocking import open_dbus_connection

    said: dict[str, Any] = {}
    bus = open_dbus_connection(bus="SESSION")
    watcher = DBusAddress(WATCHER[1], bus_name=WATCHER[0], interface=WATCHER[0])
    try:
        reply = bus.send_and_get_reply(
            Properties(watcher).get("IsStatusNotifierHostRegistered"), timeout=5
        )
        said["host_before"] = bool(reply.body[0][1])
    except Exception as error:  # noqa: BLE001 - said in OUT
        said["watcher"] = f"none: {error}"
        out.write_text(json.dumps(said), "utf-8")
        return 1
    if not said["host_before"]:
        name = f"org.kde.StatusNotifierHost-{os.getpid()}"
        bus.send_and_get_reply(message_bus.RequestName(name), timeout=5)
        register = new_method_call(watcher, "RegisterStatusNotifierHost", "s", (name,))
        bus.send_and_get_reply(register, timeout=5)
        said["stand_in_host"] = name
    out.write_text(json.dumps(said), "utf-8")
    while True:  # held until it's ended
        time.sleep(3600)


def _flat(item: dict[str, Any]) -> list[dict[str, Any]]:
    out = [item]
    for child in item["children"]:
        out += _flat(child)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.linux_tray_menu")
    parser.add_argument("out", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--click")
    parser.add_argument("--host", action="store_true", help="a stand-in tray host")
    args = parser.parse_args(argv)
    if args.host:
        return host(args.out)
    try:
        found = read(args.pid, args.click)
    except Exception as error:  # noqa: BLE001 - said in OUT
        found = {"error": f"{type(error).__name__}: {error}"}
    args.out.write_text(
        json.dumps(found, indent=1, ensure_ascii=False, default=str), "utf-8"
    )
    return 0 if "layout" in found else 1


if __name__ == "__main__":
    sys.exit(main())
