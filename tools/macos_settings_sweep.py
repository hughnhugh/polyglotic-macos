r"""Every setting changed and put back, as a learner would, on GitHub's Mac
(polyglotic-hq 523, from 515's sweep): the macOS job's `learner` part.
The app from source as `tools.app_tour` runs it, with the Mac's own staying
on top, keys and voices, signed in to the stand-in server and captioning
the app's FLEURS sample; then each row of a caption window's settings
popover and of its language chip's, and each control of every Settings
section: changed, what changed in the settings file and the caption window
looked at (each window's own `grab()`), changed back; the menu bar's
menu; Words, the transcript, a lookup and the card's Say it. Each change
notes the log's warnings and errors and any error box.

    uv run --no-sync python -m tools.macos_settings_sweep OUT [--limit S]

OUT gets `sweep.json` (every change), `checks.json` (the run's own checks)
and `sweep-checks.json` (the verdict, in the parts' shape: each check's
outcome and what it said). The job fails on a fail:
- `every_part_ran`: each part of the sweep ran to its end without an error;
- `enough_changed`: at least `ENOUGH` changes were made (515's sweep made
  254): fewer means the sweep lost its way, not that all was well;
- `no_error`: no error box and nothing logged at ERROR during a change;
- `put_back`: the settings file at the end holds what it held at the
  start, outside what a window's own use moves (`MOVES`) and what the
  sweep first wrote (listed). Each setting left is put down to the controls
  whose change and change back left it changed; one left only by a control
  known not to put it back (`KNOWN`, with where it's being fixed) is a note
  until that's fixed.
Warnings logged during a change are listed (`warnings`), never failing.

Runs on any OS (offscreen too, to try it); on a Mac it is the Mac's look.
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QListWidget,
    QPushButton,
    QSlider,
    QWidget,
)

from tools import app_tour as kit

SWEEP: dict[str, Any] = {"changes": [], "notes": []}
NATIVE_WORDS = ("pick a colour",)
"""Buttons that open macOS's own panel (the colour panel), whose modal loop
nothing here can close: said, not pressed (run 3 waited on it for ever)."""
SKIP_WORDS = (
    "sign out", "delete", "quit", "reset", "remove", "export", "send",
    "report", "feedback", "uninstall", "stop captioning", "log out",
)  # fmt: skip
"""Buttons the generic sweep doesn't press (said, not pressed)."""


class Heard(logging.Handler):
    """The log's warnings and errors during one change."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if len(self.records) < 50:
            self.records.append(
                f"{record.levelname} {record.name}: {record.getMessage()[:200]}"
            )


HEARD = Heard()


def flat(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out.update(flat(v, f"{prefix}{k}."))
        return out
    return {prefix.rstrip("."): value}


def raw() -> dict[str, Any]:
    """The settings file as it is now."""
    path = kit.OUT / "data" / "settings.json"
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def stored() -> dict[str, Any]:
    return flat(raw())


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = set(before) | set(after)
    return {
        k: [before.get(k), after.get(k)]
        for k in sorted(keys)
        if before.get(k) != after.get(k)
    }


def name_of(widget: QWidget) -> str:
    text = widget.text() if isinstance(widget, QAbstractButton) else ""
    return (
        widget.accessibleName() or text or widget.objectName() or type(widget).__name__
    ).replace("\n", " ")[:60]


class Change:
    """One change: the stored settings and the log around it."""

    def __init__(self, where: str, what: str) -> None:
        self.where, self.what = where, what
        self.before = stored()
        HEARD.records.clear()
        self.boxes = len(kit.STATE.get("error_boxes", []))
        self.began = time.monotonic()

    def done(self, effect: Any = None, picture: str | None = None) -> dict[str, Any]:
        after = stored()
        boxes = kit.STATE.get("error_boxes", [])[self.boxes :]
        row = {
            "where": self.where,
            "what": self.what,
            "stored": diff(self.before, after),
            "effect": effect,
            "log": list(HEARD.records),
            "error_boxes": boxes,
            "picture": picture,
        }
        SWEEP["changes"].append(row)
        write()  # as it goes: a run cut off keeps what it saw
        return row


def shot(widget: QWidget | None, name: str) -> str | None:
    try:
        if widget is None or not widget.isVisible():
            return None
    except RuntimeError:  # deleted
        return None
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:80]
    try:
        widget.grab().save(str(kit.OUT / f"{safe}.png"))
    except Exception:  # noqa: BLE001
        return None
    return f"{safe}.png"


def alive(widget: Any) -> bool:
    try:
        widget.objectName()
    except RuntimeError:
        return False
    return True


OPENED: list[str] = []
"""What a click opened that runs its own loop (a menu's `exec`, a dialog's)."""


def _close_open() -> None:
    """A menu or dialog a click opened, pictured and closed: one that runs
    its own loop would otherwise hold the click (and the sweep) forever."""
    for opened in (QApplication.activePopupWidget(), QApplication.activeModalWidget()):
        if opened is not None and opened.isVisible():
            OPENED.append(type(opened).__name__)
            shot(opened, f"opened-{len(OPENED)}-{type(opened).__name__}")
            opened.close()


def click(widget: QWidget) -> None:
    QTimer.singleShot(900, _close_open)
    QTimer.singleShot(2000, _close_open)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.rect().center())


def _row_named(listed: QListWidget, chip: str) -> int:
    """The row of a list whose text is the chip's choice ("English ▾")."""
    wanted = chip.replace("▾", "").replace("▴", "").strip()
    head = wanted.split(" · ")[0].strip()
    for row in range(listed.count()):
        text = listed.item(row).text().strip()
        if text in (wanted, head):
            return row
    for row in range(listed.count()):
        if listed.item(row).text().strip().startswith(head):
            return row
    return -1


def open_list(popover: Any) -> QListWidget | None:
    for each in popover.findChildren(QListWidget):
        if each.isVisible():
            return each
    return None


def pick(listed: QListWidget, row: int) -> None:
    item = listed.item(row)
    listed.scrollToItem(item)
    at = listed.visualItemRect(item).center()
    QTest.mouseClick(listed.viewport(), Qt.MouseButton.LeftButton, pos=at)


def window_state(_was: Any = None) -> dict[str, Any]:
    """The player's caption window now (it may have been made again)."""
    captions = kit.caption_window()
    if captions is None:
        return {"window": None}
    try:
        return {
            "choices": repr(getattr(captions, "choices", None))[:400],
            "geometry": captions.geometry().getRect(),
            "lines": len(getattr(captions.view, "lines", [])),
        }
    except RuntimeError:
        return {"window": "deleted"}


# -- the popovers ---------------------------------------------------------------------


def popover_rows(captions: Any, popover: Any, where: str, reopen: Any) -> kit.Step:
    """Each row's buttons: a chip opens its list - another choice picked,
    then the first back; a switch or A-/A+ pressed and pressed back."""
    for row_name, row in list(popover.rows.items()):
        if row_name in (
            "stop",
            "join",
            "separate",
            "all_settings",
            "transcript",
            "copy_all",
        ):
            continue
        found = [row, *row.findChildren(QPushButton)]  # a switch row is its button
        buttons = [
            b for b in found
            if isinstance(b, QPushButton) and b.isVisible() and b.isEnabled()
        ]  # fmt: skip
        for i, button in enumerate(buttons):
            if not alive(popover) or not alive(button):
                SWEEP["notes"].append(f"{where}: {row_name}: the popover went")
                return
            label = name_of(button)
            if not popover.isVisible():
                reopen()
                yield kit.pause(0.6)
            change = Change(where, f"{row_name}: {label}")
            try:
                click(button)
            except RuntimeError:  # the button went with a re-made popover
                continue
            yield kit.pause(0.5)
            listed = open_list(popover) if popover.isVisible() else None
            if listed is not None and row_name == "app":
                # another app would end this window: the list looked at, shut
                change.done({"apps": [listed.item(r).text() for r in range(listed.count())]},
                            shot(popover, f"{where}-apps"))  # fmt: skip
                click(button)
                yield kit.pause(0.4)
                continue
            if listed is not None and listed.count() > 1:
                first = (
                    _row_named(listed, label)
                    if _row_named(listed, label) >= 0
                    else listed.currentRow()
                )
                other = 1 if first != 1 else 2 % listed.count()
                taken = listed.item(other).text()
                pick(listed, other)
                yield kit.pause(0.8)
                effect = {"picked": taken, "window": window_state(captions)}
                change.done(
                    effect, shot(kit.caption_window(), f"{where}-{row_name}-{i}-picked")
                )
                # back to what it was
                if not popover.isVisible():
                    reopen()
                    yield kit.pause(0.6)
                back = Change(where, f"{row_name}: back")
                try:
                    click(button)
                except RuntimeError:
                    continue
                yield kit.pause(0.5)
                listed = open_list(popover) if popover.isVisible() else None
                if listed is not None and first >= 0:
                    pick(listed, first)
                    yield kit.pause(0.6)
                back.done({"to": first})
                continue
            pressed: dict[str, Any] = {
                "window": window_state(captions),
                "checked": button.isChecked(),
            }
            change.done(pressed, shot(kit.caption_window(), f"{where}-{row_name}-{i}"))
            if label.startswith(("A-", "A+")) or "maller" in label or "igger" in label:
                continue  # the pair is pressed in turn: A- then A+ is back
            if button.isCheckable() or row_name.endswith(
                ("colours", "mic", "this", "set_up")
            ):
                back = Change(where, f"{row_name}: {label} back")
                if not popover.isVisible():
                    reopen()
                    yield kit.pause(0.6)
                try:
                    click(button)
                except RuntimeError:
                    continue
                yield kit.pause(0.4)
                back.done({"checked": button.isChecked()})


def popover_actions(captions: Any, popover: Any) -> kit.Step:
    interface = kit.STATE["interface"]
    actions = {
        name: popover.rows.get(name)
        for name in ("copy_all", "transcript", "all_settings")
    }
    for name, row in actions.items():
        if row is None:
            continue
        if not popover.isVisible():
            captions.toggle_settings()
            yield kit.pause(0.6)
        button = next((b for b in row.findChildren(QPushButton) if b.isVisible()), row)
        change = Change("caption popover", name)
        QApplication.clipboard().setText("")
        click(button)
        yield kit.pause(1.2)
        effect: dict[str, Any] = {}
        picture = None
        if name == "copy_all":
            text = QApplication.clipboard().text()
            effect = {"clipboard_chars": len(text), "starts": text[:60]}
        elif name == "transcript":
            shown = [w for w in QApplication.topLevelWidgets()
                     if w.isVisible() and "Transcript" in type(w).__name__]  # fmt: skip
            effect = {"transcript_open": bool(shown)}
            picture = shot(shown[0] if shown else None, "popover-transcript")
            for w in shown:
                w.close()
        else:
            window = kit.hub().window
            effect = {"main_window": window.isVisible(),
                      "page": getattr(window, "current", lambda: None)() if callable(getattr(window, "current", None)) else None}  # fmt: skip
            picture = shot(window, "popover-all-settings")
        change.done(effect, picture)
        yield kit.pause(0.4)
    _ = interface


# -- Settings -------------------------------------------------------------------------


def settings_sections(captions: Any) -> kit.Step:
    window = kit.hub().window
    settings = window.pages.get("settings")
    sections = next((w for w in [settings, *(settings.findChildren(QWidget) if settings else [])]
                     if hasattr(w, "show_section")), None)  # fmt: skip
    if sections is None:
        SWEEP["notes"].append("no Settings sections found")
        return
    window.show()
    window.go_to("settings")
    for key in (
        "look",
        "links",
        "readings",
        "timing",
        "speech",
        "dictation",
        "app",
        "lab",
    ):
        try:
            sections.show_section(key)
        except Exception as error:  # noqa: BLE001
            SWEEP["notes"].append(f"{key}: {error}")
            continue
        yield kit.pause(1.0)
        shot(window, f"settings-{key}")
        box = sections.section.get(key) if hasattr(sections, "section") else None
        if box is None:
            continue
        controls = [
            w for w in box.findChildren(QWidget) if w.isVisible() and w.isEnabled()
        ]
        for n, control in enumerate(controls):
            label = name_of(control)
            if isinstance(control, QComboBox):
                if control.count() < 2:
                    continue
                first = control.currentIndex()
                other = (first + 1) % control.count()
                change = Change(
                    f"Settings > {key}", f"combo {label}: {control.itemText(other)}"
                )
                control.setCurrentIndex(other)
                control.activated.emit(other)
                yield kit.pause(0.6)
                change.done({"window": window_state(captions)},
                            shot(kit.caption_window(), f"settings-{key}-{n}"))  # fmt: skip
                back = Change(f"Settings > {key}", f"combo {label}: back")
                control.setCurrentIndex(first)
                control.activated.emit(first)
                yield kit.pause(0.4)
                back.done()
            elif isinstance(control, QSlider):
                first = control.value()
                change = Change(f"Settings > {key}", f"slider {label}")
                control.setValue(min(control.maximum(), first + control.pageStep()))
                yield kit.pause(0.6)
                change.done(
                    {"value": control.value()},
                    shot(kit.caption_window(), f"settings-{key}-{n}"),
                )
                back = Change(f"Settings > {key}", f"slider {label}: back")
                control.setValue(first)
                yield kit.pause(0.3)
                back.done()
            elif isinstance(control, QAbstractButton):
                lowered = label.lower()
                if not control.isCheckable():
                    if sys.platform == "darwin" and any(
                        word in lowered for word in NATIVE_WORDS
                    ):
                        SWEEP["notes"].append(
                            f"{key}: macOS's own panel, not pressed: {label}"
                        )
                        continue
                    if any(word in lowered for word in SKIP_WORDS):
                        SWEEP["notes"].append(f"{key}: not pressed: {label}")
                        continue
                    if type(control).__name__ in ("QToolButton",) and not label:
                        continue
                    # a plain button: pressed once, what opened looked at and closed
                    change = Change(f"Settings > {key}", f"button {label}")
                    try:
                        click(control)
                    except RuntimeError:
                        continue
                    yield kit.pause(1.0)
                    modal = QApplication.activeModalWidget()
                    popup = QApplication.activePopupWidget()
                    opened = modal or popup
                    effect = {"opened": type(opened).__name__ if opened else None,
                              "closed_by_the_sweep": OPENED[-2:],
                              "links": list(kit.STATE.get("links_opened", []))[-2:]}  # fmt: skip
                    change.done(
                        effect, shot(opened or window, f"settings-{key}-{n}-button")
                    )
                    if popup is not None:
                        popup.close()
                    if modal is not None:
                        modal.close()
                    yield kit.pause(0.4)
                    continue
                if control.isChecked() and control.autoExclusive():
                    continue  # the choice made: its siblings are tried
                parent = control.parentWidget()
                siblings = parent.findChildren(QAbstractButton) if parent else []
                group = [b for b in siblings
                         if b.isCheckable() and b.isChecked() and b is not control]  # fmt: skip
                change = Change(f"Settings > {key}", f"toggle {label}")
                try:
                    click(control)
                except RuntimeError:
                    continue
                yield kit.pause(0.6)
                change.done({"checked": control.isChecked(), "window": window_state(captions)},
                            shot(kit.caption_window(), f"settings-{key}-{n}"))  # fmt: skip
                back = Change(f"Settings > {key}", f"toggle {label}: back")
                # back, by what the press did (523): when it unticked a sibling
                # that was chosen - a segmented row, a radio group - that one
                # is pressed again; otherwise - a switch, a checkbox among
                # others - this one is. (515's sweep pressed a ticked sibling
                # whenever there was just one, and left the readings' boxes
                # all ticked.)
                unticked = [b for b in group if alive(b) and not b.isChecked()]
                try:
                    click(unticked[0] if unticked else control)
                except RuntimeError:
                    continue
                yield kit.pause(0.4)
                back.done({"checked": control.isChecked()})
                modal = QApplication.activeModalWidget()
                if modal is not None:
                    SWEEP["notes"].append(
                        f"{key}: {label} left {type(modal).__name__} open"
                    )
                    modal.close()


# -- the rest --------------------------------------------------------------------------


def menu_bar() -> kit.Step:
    tray = getattr(kit.STATE.get("desktop"), "tray", None)
    if tray is None:
        SWEEP["notes"].append("no menu-bar icon")
        return
    menu = tray.contextMenu()
    if menu is None:
        SWEEP["notes"].append("the menu-bar icon has no menu")
        return
    menu.aboutToShow.emit()
    items = [(a.text(), a.isEnabled(), a.isCheckable(), a.isChecked())
             for a in menu.actions() if not a.isSeparator()]  # fmt: skip
    SWEEP["menu_bar"] = items
    for action in menu.actions():
        text = action.text().lower()
        if action.isSeparator() or not action.isEnabled() or "quit" in text:
            continue
        change = Change("menu bar", action.text())
        action.trigger()
        yield kit.pause(1.0)
        modal = QApplication.activeModalWidget()
        change.done({"modal": type(modal).__name__ if modal else None})
        if modal is not None:
            modal.close()
        if action.isCheckable():
            action.trigger()  # back
            yield kit.pause(0.5)


def lookup_and_say(_was: Any) -> kit.Step:
    captions = kit.caption_window()
    spot = None
    try:
        spot = kit.a_word(captions)
    except Exception:  # noqa: BLE001
        spot = None
    if spot is None:
        SWEEP["notes"].append("no word to look up")
        return
    change = Change("caption window", "a click on a word")
    QTest.mouseClick(captions, Qt.MouseButton.LeftButton, pos=spot.toPoint())
    card = lambda: kit.STATE["interface"].windows.card
    yield kit.wait(lambda: card() is not None and card().isVisible(), 8, "")
    yield kit.pause(1.0)
    shown = card() is not None and card().isVisible()
    change.done({"card": shown}, shot(card() if shown else None, "lookup-card"))
    if not shown:
        return
    for button in card().findChildren(QAbstractButton):
        label = name_of(button).lower()
        if "say" in label or "hear" in label or "listen" in label or "play" in label:
            said = Change("lookup card", name_of(button))
            click(button)
            yield kit.pause(2.5)
            said.done({"button": name_of(button)}, shot(card(), "lookup-card-said"))
            break
    card().hide()


def words_and_transcript(captions: Any) -> kit.Step:
    window = kit.hub().window
    for page in ("words", "learning", "home"):
        if page in getattr(window, "pages", {}):
            window.go_to(page)
            yield kit.pause(1.2)
            shot(window, f"page-{page}")
    kit.STATE["interface"].transcripts.show(kit.PLAYER)
    yield kit.pause(1.5)
    shown = [w for w in QApplication.topLevelWidgets()
             if w.isVisible() and "Transcript" in type(w).__name__]  # fmt: skip
    shot(shown[0] if shown else None, "transcript")
    for w in shown:
        w.close()


def sweep() -> kit.Step:
    import faulthandler

    hangs = (kit.OUT / "stacks.txt").open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(90, repeat=True, file=hangs)
    logging.getLogger().addHandler(HEARD)
    yield from first_run()
    window = kit.hub().window
    window.go_to("home")
    if kit.caption_window() is None:
        button = window.findChild(QAbstractButton, f"picker.add.{kit.PLAYER}")
        if button is not None:
            button.click()
    yield kit.wait(lambda: kit.caption_window() is not None
                   and kit.caption_window().isVisible(), 30, "the caption window")  # fmt: skip
    yield kit.wait(lambda: len(kit.finished_lines()) >= 1, 90, "a finished caption")
    captions = kit.caption_window()
    captions.setGeometry(START)
    if sys.platform == "darwin":
        activate()
    yield kit.pause(1.0)
    SWEEP["first_stored"] = raw()
    shot(kit.caption_window(), "caption-window-before")

    def reopen() -> None:
        now = kit.caption_window()
        if now is not None and not now.settings_open:
            now.toggle_settings()

    for part, steps in (
        ("caption popover", lambda: _caption_popover(captions, reopen)),
        ("language popover", lambda: _language_popover(captions)),
        ("settings", lambda: settings_sections(captions)),
        ("menu bar", menu_bar),
        ("lookup", lambda: lookup_and_say(captions)),
        ("pages", lambda: words_and_transcript(captions)),
    ):
        began = time.monotonic()
        yield from guarded(part, steps())
        SWEEP.setdefault("seconds", {})[part] = round(time.monotonic() - began, 1)
        kit.check(f"sweep: {part} ran", True)
    shot(kit.caption_window(), "caption-window-after")
    SWEEP["final_stored"] = raw()
    write()


def _caption_popover(_was: Any, reopen: Any) -> kit.Step:
    captions = kit.caption_window()
    captions.toggle_settings()
    yield kit.pause(0.8)
    popover = captions.popover
    if popover is None or not popover.isVisible():
        SWEEP["notes"].append("the caption popover didn't open")
        return
    shot(popover, "caption-popover")
    yield from popover_rows(captions, popover, "caption popover", reopen)
    now = kit.caption_window()
    if now is not None and now.popover is not None:
        yield from popover_actions(now, now.popover)
        now.close_settings()


def _language_popover(_was: Any) -> kit.Step:
    captions = kit.caption_window()
    if captions is None or not hasattr(captions, "toggle_languages"):
        return
    captions.toggle_languages()
    yield kit.pause(0.8)
    popover = captions.languages
    if popover is None or not popover.isVisible():
        SWEEP["notes"].append("the language chip's popover didn't open")
        return
    shot(popover, "language-popover")

    def reopen() -> None:
        if not popover.isVisible():
            captions.toggle_languages()

    yield from popover_rows(captions, popover, "language popover", reopen)
    now = kit.caption_window()
    if now is not None:
        now.close_settings()


def write() -> None:
    (kit.OUT / "sweep.json").write_text(
        json.dumps(SWEEP, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )


# -- the verdict ----------------------------------------------------------------------

PASS, FAIL, NOTE = "pass", "fail", "note"
ENOUGH = 100
"""Fewer changes than this and the sweep lost its way (515's made 254)."""
MOVES = (
    "geometry",
    "position",
    "screen",
    "seen",
    "shown",
    "last_",
    "_at",
    "offered",
    "asked",
    "count",
    "opened",
    "page",
    "first_run",
)
"""Parts of a stored key a window's own use moves - where it was, what was
last seen or offered - not a setting a learner changed."""


BOOKKEEPING = ("changed",)
"""Keys the app keeps about the settings, not settings: which ones the
learner has changed (`with_changed`)."""


def moved_by_use(key: str) -> bool:
    lowered = key.lower()
    return key in BOOKKEEPING or any(part in lowered for part in MOVES)


KNOWN = {
    "Settings > links / toggle Quiet view": (
        "polyglotic-hq 523's finding: Settings > Links' Quiet view on, then off,"
        " leaves word links off and six languages' reading lines on (LookView."
        "set_quiet alone puts the lines back: the switch's own path doesn't);"
        " a fix is proposed"
    ),
}
"""Controls known not to put back what they change, each with why and
where it's being fixed: said as a note, not a fail, until the fix lands -
then taken out, so the check holds it fixed."""


def not_put_back(changes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each control the sweep changed and then changed back (a row and the
    "back" row right after it), with the settings the two left changed -
    what it was before the change against what it is after the back -
    outside what use moves and what the change first wrote."""
    found: dict[str, dict[str, Any]] = {}
    for change, back in itertools.pairwise(changes):
        if "back" in change["what"] or "back" not in back["what"]:
            continue
        start: dict[str, Any] = {}
        end: dict[str, Any] = {}
        for row in (change, back):
            for key, (was, now) in (row.get("stored") or {}).items():
                start.setdefault(key, was)
                end[key] = now
        left = {
            k: [start[k], end[k]]
            for k in start
            if start[k] != end[k] and start[k] is not None and not moved_by_use(k)
        }
        if left:
            found[f"{change['where']} / {change['what']}"] = left
    return found


def _errors_of(change: dict[str, Any]) -> list[str]:
    logged = [r for r in change.get("log", []) if r.startswith(("ERROR", "CRITICAL"))]
    return [*logged, *(str(box) for box in change.get("error_boxes", []))]


def verdict(sweep: dict[str, Any], ran: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sweep judged (`sweep.json` and the run's own checks): each
    check's outcome and what it said."""
    out: list[dict[str, Any]] = []

    def add(check: str, outcome: str, said: str, **facts: Any) -> None:
        out.append({"check": check, "outcome": outcome, "said": said, "facts": facts})

    failed = [
        f"{c['check']}: {str(c.get('detail', ''))[-300:]}" for c in ran if not c["ok"]
    ]
    add(
        "every_part_ran",
        FAIL if failed else PASS,
        "; ".join(failed)[:900] if failed else "every part ran to its end",
    )
    changes = sweep.get("changes", [])
    add(
        "enough_changed",
        PASS if len(changes) >= ENOUGH else FAIL,
        f"{len(changes)} changes (at least {ENOUGH})",
    )
    errors = [
        f"{c['where']} / {c['what']}: {'; '.join(_errors_of(c))}"
        for c in changes
        if _errors_of(c)
    ]
    add(
        "no_error",
        FAIL if errors else PASS,
        " | ".join(errors)[:900]
        if errors
        else "no error box, nothing logged as an error",
    )
    # what isn't as it started, at the end - each key put down to the
    # controls whose change and change back left it changed (a preset's
    # pair may, and a later one put it back: only the end is judged)
    first, last = sweep.get("first_stored"), sweep.get("final_stored")
    if first is None or last is None:
        add("put_back", FAIL, "the settings file wasn't read at both ends")
    else:
        moved = diff(flat(first), flat(last))
        written = sorted(k for k, (was, _) in moved.items() if was is None)
        ended = {
            k: v for k, v in moved.items() if v[0] is not None and not moved_by_use(k)
        }
        by: dict[str, list[str]] = {}
        for control, left in not_put_back(changes).items():
            for key in left:
                by.setdefault(key, []).append(control)
        known = {
            k: by[k] for k in ended if by.get(k) and all(c in KNOWN for c in by[k])
        }
        failing = {
            k: {"was_then": v, "by": by.get(k, ["(no single control)"])}
            for k, v in ended.items()
            if k not in known
        }
        add(
            "put_back",
            FAIL if failing else PASS,
            f"{len(failing)} setting(s) not put back:"
            f" {json.dumps(failing, ensure_ascii=False)[:800]}"
            if failing
            else "every setting the file held at the start is as it was",
            left=failing,
            known=known,
            first_written=written,
        )
        for control in sorted({c for cs in known.values() for c in cs}):
            add("put_back_known", NOTE, f"{control}: {KNOWN[control]}")
    warned = sorted(
        {r for c in changes for r in c.get("log", []) if r.startswith("WARNING")}
    )
    add(
        "warnings",
        NOTE if warned else PASS,
        f"{len(warned)} different warning(s) logged during the changes",
        warnings=warned[:40],
    )
    return out


# -- the app, as the tour starts it ----------------------------------------------------

START = QRect(360, 300, 640, 220)
"""Where the caption window is put before the sweep."""


def activate() -> None:
    """The app in front, as a learner clicking it would bring it."""
    import ctypes

    from polyglotic_desktop.platform.macos import objc

    app = objc.send(objc.cls("NSApplication"), "sharedApplication")
    objc.send(
        app, "activateIgnoringOtherApps:", True, restype=None, argtypes=[ctypes.c_bool]
    )


def first_run() -> kit.Step:
    """The first questions answered as a learner would: consent agreed, the
    level taken, anything else closed."""
    for _ in range(5):
        yield kit.wait(
            lambda: QApplication.activeModalWidget() or kit.ready(),
            90,
            "the first question or the main window",
        )
        question = QApplication.activeModalWidget()
        if question is None:
            break
        name = type(question).__name__
        if name == "ConsentDialog" and getattr(question, "agree", None) is not None:
            question.agree.setChecked(True)  # type: ignore[attr-defined]
        if name in ("ConsentDialog", "LevelPicker"):
            question.accept()  # type: ignore[attr-defined]
        else:
            question.close()
        yield kit.pause(1.0)
    yield kit.wait(kit.ready, 60, "the main window")


def guarded(what: str, steps: kit.Step) -> kit.Step:
    try:
        yield from steps
    except Exception:  # noqa: BLE001 - said as a failed check
        kit.check(f"{what} ran", False, traceback.format_exc()[-1500:])


class Driver(kit.Driver):
    def __init__(self, limit: float) -> None:
        super().__init__(limit)
        self.steps = sweep()


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_settings_sweep")
    parser.add_argument("out", type=Path)
    parser.add_argument("--dictionaries", default="build/dictionaries")
    parser.add_argument("--limit", type=float, default=900.0, help="seconds")
    args = parser.parse_args(argv)
    kit.OUT = args.out
    kit.OUT.mkdir(parents=True, exist_ok=True)
    data = kit.OUT / "data"
    kit.seed_settings(data)
    from tests import fake_server

    from polyglotic_desktop import main as app
    from polyglotic_desktop.platform.replay import join, read_clip
    from polyglotic_desktop.platform.sample import sample_file

    sample = sample_file("zh")
    assert sample is not None
    audio = join([read_clip(sample)], gap=1.0)
    fake_server.caption_for = kit.caption_for
    server = fake_server.FakeServer()
    driver = Driver(args.limit)

    class Driven(QApplication):
        def __init__(self, qt_argv: list[str]) -> None:
            super().__init__(qt_argv)
            driver.start()

    real = app.os_adapters
    swapped = kit.adapters(real, audio)

    def os_adapters(system: str = sys.platform) -> Any:
        found = swapped(system)
        if system != "darwin":
            return found
        own = real(system)
        return dataclasses.replace(
            found,
            on_top=own.on_top,
            foreground_watch=own.foreground_watch,
            keys=own.keys,
            speaker=own.speaker,  # the Mac's voices, and its player
        )

    real_interface = app.new_interface

    def new_interface(*a: Any, **k: Any) -> Any:
        kit.STATE["interface"] = real_interface(*a, **k)
        return kit.STATE["interface"]

    class Recorded(app.DesktopApp):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            kit.STATE["desktop"] = self

    app.os_adapters = os_adapters
    app.QApplication = Driven  # type: ignore[misc, assignment]
    app.new_interface = new_interface
    app.DesktopApp = Recorded  # type: ignore[misc]
    try:
        app.main(
            [
                "--server",
                server.url,
                "--data",
                str(data),
                "--dictionaries",
                args.dictionaries,
            ]
        )
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001 - said as a failed check
        kit.check("the app started", False, traceback.format_exc()[-1500:])
    kit.write_results()
    server.stop()
    write()
    checks = verdict(SWEEP, kit.RESULTS["checks"])
    (kit.OUT / "sweep-checks.json").write_text(
        json.dumps({"checks": checks}, indent=1, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    for c in checks:
        print(f"{c['outcome']} {c['check']}: {c['said']}", flush=True)
    return 1 if any(c["outcome"] == FAIL for c in checks) else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    finally:
        try:
            write()
        except Exception:  # noqa: BLE001 - the verdict is already out
            traceback.print_exc()


if __name__ == "__main__":
    import os

    code = main()
    sys.stdout.flush()
    os._exit(code)
