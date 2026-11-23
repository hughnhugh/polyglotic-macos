r"""A button of the packed app pressed as a screen reader presses it
(polyglotic-hq 574): through the desktop's accessibility bus (AT-SPI), from
another process - the app's own widgets, found by their names, with nothing
of the tour inside the app. Qt serves AT-SPI when the app is started with
`QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`.

    /usr/bin/python3 tools/linux_atspi_press.py STEP [STEP...]

Each STEP is pressed in turn, in the app named Polyglotic: the button (or
menu item, or tab) whose accessible name is the STEP's - one on screen
first, else any. A STEP may be:
- `A || B`: whichever of the names is on screen (a window folds a button
  into a "More" menu when it's narrow);
- `menu:NAME`: a menu's item only;
- `?STEP`: pressed only if it's on screen within a few seconds; no fail
  if it isn't.

Says what it pressed, one JSON line a step; exits 1 if a step that isn't
`?` found nothing. A press that opens something modal (a menu, a file
dialog) gets no answer until it closes: that counts as pressed.

The system's Python with the distribution's pyatspi (`python3-pyatspi`), not
the app's environment: GitHub's runners only (`tools/linux_packed_tour.py`).
"""

import importlib
import json
import os
import sys
import time
from typing import Any

PRESSABLE = {
    "push button",
    "button",  # newer AT-SPI's name for it (Fedora 45's at-spi2-core)
    "toggle button",
    "radio button",
    "menu item",
    "page tab",
    "list item",
}
VERBS = ("press", "click", "activate", "toggle")


def apps(atspi: Any) -> list[Any]:
    desktop = atspi.Registry.getDesktop(0)
    return [
        a for a in desktop if a is not None and "polyglotic" in (a.name or "").lower()
    ]


def found(
    atspi: Any, node: Any, names: list[str], roles: set[str], depth: int = 0
) -> list[tuple[Any, bool]]:
    """Every node under `node` named one of `names` in one of `roles`, with
    whether it's on screen."""
    if node is None or depth > 60:
        return []
    out: list[tuple[Any, bool]] = []
    try:
        if (node.name or "") in names and node.getRoleName() in roles:
            showing = node.getState().contains(atspi.STATE_SHOWING)
            out.append((node, bool(showing)))
        for child in node:
            out += found(atspi, child, names, roles, depth + 1)
    except Exception:  # noqa: BLE001 - a node gone while it was read
        return out
    return out


def press(atspi: Any, step: str) -> dict[str, Any]:
    optional = step.startswith("?")
    step = step.lstrip("?")
    roles = PRESSABLE
    if step.startswith("menu:"):
        roles, step = {"menu item"}, step[len("menu:") :]
    names = [n.strip() for n in step.split("||")]
    end = time.monotonic() + (8.0 if optional else 30.0)
    while time.monotonic() < end:
        nodes = [m for a in apps(atspi) for m in found(atspi, a, names, roles)]
        shown = [n for n, showing in nodes if showing]
        node = shown[0] if shown else (nodes[0][0] if nodes and not optional else None)
        if node is not None:
            action = node.queryAction()
            verbs = [action.getName(i) for i in range(action.nActions)]
            # a button with a menu opens it ("ShowMenu"); a press alone
            # doesn't, for one that pops its menu up at once (run 44744836219)
            which = next(
                (i for i, v in enumerate(verbs) if "menu" in v.lower()),
                next((i for i, v in enumerate(verbs) if v.lower() in VERBS), 0),
            )
            answered = True
            try:
                action.doAction(which)
            except Exception:  # noqa: BLE001 - modal: no answer until it closes
                answered = False
            return {
                "pressed": node.name,
                "role": node.getRoleName(),
                "on_screen": bool(shown),
                "action": verbs[which] if verbs else None,
                "answered": answered,
            }
        time.sleep(1)
    seen = sorted({n.getRoleName() for a in apps(atspi) for n in walk(a)})[:40]
    return {"pressed": None, "wanted": step, "optional": optional, "roles_seen": seen}


def walk(node: Any, depth: int = 0) -> list[Any]:
    """Every node under `node` (for saying what roles there were)."""
    if node is None or depth > 60:
        return []
    out = [node]
    try:
        for child in node:
            out += walk(child, depth + 1)
    except Exception:  # noqa: BLE001 - a node gone while it was read
        return out
    return out


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        sys.exit("574: this runs only on GitHub's Linux runners")
    atspi = importlib.import_module("pyatspi")
    failed = False
    for step in sys.argv[1:]:
        said = press(atspi, step)
        print(json.dumps(said, ensure_ascii=False), flush=True)
        failed = failed or (said["pressed"] is None and not said.get("optional"))
        time.sleep(2)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
