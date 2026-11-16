"""Which of the interface's strings a learner sees most: every state of the
new interface run in English, and each string counted in the states that
show it (polyglotic-hq 294: a reviewer's sheet of the 60 seen most).

python -m tools.ui_lab seen    # build/ui-lab/seen.tsv

A string counts in a state when the state asked for its translation while
it was built (`Asked`, a translator that only listens) and the text is on
screen: a label's, a button's, a field's placeholder, a list's choice, a
window's title, or text a widget paints - matched with its `{names}` and
count as anything. Not a tooltip (it shows only on hover) and not a
caption surface's or the lookup card's painted words: those are the
learner's, never read (checks.py). Only each string's context and English
are written - never what was on screen.
"""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTranslator
from PySide6.QtWidgets import QWidget

from tools.ui_lab import checks

SEEN = Path("build/ui-lab/seen.tsv")

Key = tuple[str, str, str]
"""A string: its context, English and disambiguation (`extract.Message.key`)."""


class Asked(QTranslator):
    """Installed last, so asked first: notes every string asked for and
    translates none, so the files installed before it answer. (None, not
    "": Qt takes an empty answer as the translation.)"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.asked: set[Key] = set()

    def isEmpty(self) -> bool:
        return False

    def translate(
        self,
        context: str,
        source_text: str,
        disambiguation: str | None = None,
        n: int = -1,
    ) -> str | None:
        self.asked.add((context, source_text, disambiguation or ""))
        return None


_SPECIAL = re.compile(r"\{[a-z_]+\}|%L?n|\(e?s\)")
GAP = 60
"""The most a `{name}`, a count or English's "(s)" may stand for, in
characters with the spaces out."""


def pattern(source: str) -> list[str] | None:
    """`source`'s own parts - between its `{names}`, count and "(s)" - as
    they show, the spaces taken out. None if it's too little of its own to
    tell ("{app}", "%n")."""
    parts = [p for p in _SPECIAL.split("".join(source.split())) if p]
    return parts if len("".join(parts)) >= 2 else None


def shows(parts: list[str], text: str) -> bool:
    """`text` has `parts` in order, each at most `GAP` after the one before
    and within one piece of text (pieces are split by NUL)."""
    start = text.find(parts[0])
    while start != -1:
        at = start + len(parts[0])
        for part in parts[1:]:
            found = text.find(part, at, at + GAP + len(part))
            if found == -1 or "\x00" in text[at:found]:
                break
            at = found + len(part)
        else:
            return True
        start = text.find(parts[0], start + 1)
    return False


def _own(widget: QWidget) -> list[str]:
    texts = [widget.windowTitle()] if widget.isWindow() else []
    own = checks._own_text(widget)
    if own:
        texts.append(own)
    for name in ("placeholderText", "currentText"):
        found = getattr(widget, name, None)
        if callable(found) and isinstance(value := found(), str):
            texts.append(value)
    return texts


def on_screen(widget: QWidget) -> str:
    """The text the windows of a state show, spaces taken out (each window,
    each widget's own text, then what's painted, one after another)."""
    texts: list[str] = []
    for window in checks.shown_windows(widget):
        for shown in [window, *window.findChildren(QWidget)]:
            if shown.isVisibleTo(window) and not checks._is_content(shown):
                texts += _own(shown)
        texts += [p.text for p in checks.record_text(window) if p.text]
    return "\x00".join("".join(t.split()) for t in texts)


@dataclass
class Seen:
    """Which state shows which string."""

    states: dict[Key, list[str]]

    def ranked(self) -> list[tuple[Key, list[str]]]:
        """Seen most first; then by context and English, so ties keep an order."""
        return sorted(self.states.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def recorder(
    app: QCoreApplication,
) -> tuple[Asked, Seen, Callable[[str, QWidget], None]]:
    """A listening translator installed on `app`, what it finds, and the
    lab's `shown` hook that fills it in state by state."""
    asked = Asked(app)
    app.installTranslator(asked)
    seen = Seen(defaultdict(list))
    patterns: dict[str, list[str] | None] = {}

    def shown(state: str, widget: QWidget) -> None:
        text = on_screen(widget)
        for key in sorted(asked.asked):
            if key[1] not in patterns:
                patterns[key[1]] = pattern(key[1])
            parts = patterns[key[1]]
            if parts is not None and shows(parts, text):
                seen.states[key].append(state)
        asked.asked.clear()

    return asked, seen, shown


def write(seen: Seen, path: Path = SEEN) -> int:
    """`seen.tsv`: a line per string seen, most first - how many states,
    its context, English, disambiguation and the first few states."""
    lines = ["states\tcontext\tenglish\tdisambiguation\twhere"]
    for (context, source, comment), states in seen.ranked():
        lines.append(
            "\t".join(
                [str(len(states)), context, source, comment, " ".join(states[:4])]
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return len(lines) - 1


def read(path: Path = SEEN) -> list[tuple[Key, int, str]]:
    """What `write` wrote: each string's key, its count and where."""
    found = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        states, context, source, comment, where = line.split("\t")
        found.append(((context, source, comment), int(states), where))
    return found
