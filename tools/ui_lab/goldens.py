"""Golden images: each state of the new interface as approved, and the gate
on any difference (polyglotic-hq project 108's design, section 5; built in
project 119).

- **What is stored:** `tools/ui_lab/goldens/`, one PNG per state of the
  new interface (`<state>.png`, about 30 KB each; 30 states, under 1 MB,
  2026-11-07), and `goldens.json`: what made them (PySide6 and Qt, and a
  fingerprint of the fonts folder). Images rather than hashes: a pull
  request that approves new ones shows before and after in GitHub's own
  image diff ("Files changed"), and a failing run can draw a diff without
  rebuilding the old version. Each approval adds only the images that
  changed to the history.
- **How they're compared:** pixel by pixel. A pixel differs when any
  channel differs by more than `CHANNEL_TOLERANCE`; a state differs when
  more pixels differ than it's allowed - none, except a state that
  animates (`ALLOWED`). A different size always differs.
- **Where they're made:** on the user's PC, the self-hosted runner's
  machine, with Windows' fonts (`QT_QPA_FONTDIR`): CI there and a local run
  there draw the same pixels. On another machine (other fonts or another
  Qt) every state differs; the run says the machine differs from the one
  that made the goldens, and with `--gate` it fails. Approve on that PC.
- **Approving:** `python -m tools.ui_lab approve` runs every state of the
  new interface and rewrites each golden that differs or is new;
  `approve --only <state>...` runs only those (names, or patterns such as
  `ui_next.w4_words_*`). Approving never removes a golden: `python -m
  tools.ui_lab prune` removes those whose state is gone, as a step of its
  own (polyglotic-hq 258: approving a few states once removed every other
  golden, and 250 restored 90 by hand). Commit them: the pull request
  shows before and after.
"""

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtGui import QImage

GOLDENS = Path(__file__).resolve().parent / "goldens"
MADE_WITH = "goldens.json"
CHANNEL_TOLERANCE = 8
"""Out of 255: a channel within this is the same (anti-aliasing's noise)."""
ALLOWED = {
    "ui_next.w1_listening": 250,
    "ui_next.w1_listening_preview": 250,
    "ui_next.w1_listening_live": 250,
}
"""Pixels a state may differ by, with the reason: the listening mark's
lit part sweeps along its bar with the clock (164 pixels at most between
two moments, measured 2026-11-09; 267). Not `w1_listening_still`: its
bar stands still (reduced motion, 260)."""


@dataclass(frozen=True)
class Golden:
    """A state's picture against its golden: `same`, `differs`, `resized`
    or `new` (no golden yet); `changed` pixels of `total`."""

    state: str
    status: str
    changed: int = 0
    total: int = 0

    @property
    def failed(self) -> bool:
        return self.status != "same"

    def describe(self) -> str:
        if self.status == "differs":
            share = 100 * self.changed / max(1, self.total)
            return f"{self.changed} pixels differ ({share:.2f} %)"
        return {
            "same": "same as its golden",
            "resized": "a different size from its golden",
            "new": "no golden yet",
        }[self.status]


def fingerprint() -> dict[str, str]:
    """What draws the pictures here: PySide6, Qt, and the fonts folder
    (its files' names and sizes, hashed)."""
    folder = os.environ.get("QT_QPA_FONTDIR", "")
    listing: list[tuple[str, int]] = []
    if folder and os.path.isdir(folder):
        with os.scandir(folder) as found:
            listing = sorted(
                (entry.name.lower(), entry.stat().st_size)
                for entry in found
                if entry.is_file()
            )
    digest = hashlib.sha256(repr(listing).encode()).hexdigest()[:16]
    return {
        "pyside6": PySide6.__version__,
        "qt": qVersion(),
        "fonts": f"{len(listing)} files, {digest}",
    }


def made_with(store: Path | None = None) -> dict[str, str]:
    store = GOLDENS if store is None else store
    path = store / MADE_WITH
    if not path.is_file():
        return {}
    found = json.loads(path.read_text(encoding="utf-8"))
    return dict(found.get("made_with", {}))


def machine_note(store: Path | None = None) -> str:
    """Empty when this machine draws as the goldens' did; else what differs."""
    store = GOLDENS if store is None else store
    then, now = made_with(store), fingerprint()
    differ = [
        f"{key} {then.get(key)} -> {now[key]}"
        for key in now
        if then.get(key) != now[key]
    ]
    if not then or not differ:
        return ""
    return (
        "this machine differs from the one that made the goldens ("
        + "; ".join(differ)
        + "): every picture may differ - approve on the user's PC"
    )


def pixels(image: QImage) -> np.ndarray:
    """`image` as height x width x RGBA."""
    shown = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = shown.width(), shown.height()
    data = np.frombuffer(shown.constBits(), dtype=np.uint8, count=shown.sizeInBytes())
    rows = data.reshape(height, shown.bytesPerLine())[:, : width * 4]
    return rows.reshape(height, width, 4).copy()


def path_of(state: str, store: Path | None = None) -> Path:
    store = GOLDENS if store is None else store
    return store / f"{state}.png"


def compare(
    state: str, image: QImage, store: Path | None = None
) -> tuple[Golden, QImage | None, QImage | None]:
    """`image` against `state`'s golden: the verdict, the golden (if any)
    and, if they differ, a picture of where."""
    store = GOLDENS if store is None else store
    path = path_of(state, store)
    if not path.is_file():
        return Golden(state, "new"), None, None
    before = QImage(str(path))
    if before.size() != image.size():
        return Golden(state, "resized"), before, None
    now, then = pixels(image), pixels(before)
    changed = np.abs(now.astype(np.int16) - then.astype(np.int16)).max(axis=2)
    mask = changed > CHANNEL_TOLERANCE
    count, total = int(mask.sum()), int(mask.size)
    if count <= ALLOWED.get(state, 0):
        return Golden(state, "same", count, total), before, None
    return Golden(state, "differs", count, total), before, _diff(now, mask)


def _diff(now: np.ndarray, mask: np.ndarray) -> QImage:
    """The new picture faded to grey, each differing pixel in magenta."""
    grey = (now[:, :, :3].mean(axis=2) * 0.35 + 255 * 0.65).astype(np.uint8)
    shown = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
    shown[mask] = (230, 0, 160, 255)
    height, width = mask.shape
    image = QImage(
        shown.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888
    )
    return image.copy()  # its own pixels, not the array's


def save(image: QImage, path: Path) -> None:
    """A PNG at the strongest compression - without its alpha channel when
    every pixel is opaque (smaller)."""
    shown = image
    if int(pixels(image)[:, :, 3].min()) == 255:
        shown = image.convertToFormat(QImage.Format.Format_RGB888)
    shown.save(str(path), None, 0)  # the format from ".png"


def approve(pictures: dict[str, QImage], store: Path | None = None) -> list[str]:
    """Each picture that differs from its golden (or has none) becomes its
    golden. What changed, one line each. It never removes a golden - not
    one whose picture it wasn't given, nor one whose state is gone
    (`remove_stale`)."""
    store = GOLDENS if store is None else store
    store.mkdir(parents=True, exist_ok=True)
    changes = []
    for state, image in sorted(pictures.items()):
        verdict, _, _ = compare(state, image, store)
        if verdict.status == "same":
            continue
        save(image, path_of(state, store))
        changes.append(f"{state}: {verdict.describe()} - approved")
    (store / MADE_WITH).write_text(
        json.dumps({"made_with": fingerprint()}, indent=1) + "\n", encoding="utf-8"
    )
    return changes


def stale(states: Iterable[str], store: Path | None = None) -> list[Path]:
    """The goldens whose state is none of `states` (every state's name)."""
    store = GOLDENS if store is None else store
    names = set(states)
    return [p for p in sorted(store.glob("*.png")) if p.stem not in names]


def remove_stale(states: Iterable[str], store: Path | None = None) -> list[str]:
    """The goldens whose state is none of `states` - every state's name, not
    only those drawn - removed. What went, one line each."""
    gone = stale(states, store)
    for path in gone:
        path.unlink()
    return [f"{path.stem}: its state is gone - removed" for path in gone]
