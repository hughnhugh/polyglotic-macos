"""The rulebook's pictures: the app's own `grab()` of a replayed moment.

A picture is a recipe (`rulebook.Picture`): a stream, a set-up, the frames
to photograph, perhaps a planted fault. The replay is played on the patched
clock and each named frame is photographed through the UI lab's
`photograph` (`tools/ui_lab/lab.py`: the widget's own `grab()`, over the
lab's stand-in video for a see-through window). Several frames make a
filmstrip, oldest on top, each with its time.

Pictures are compared as the lab's goldens are: on the machine that made
them (the same PySide6, Qt and fonts), pixel by pixel within the lab's
tolerance; on another machine only their recipes are checked, and the run
says so.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from tools.scene_replay import drive, plants, streams
from tools.scene_replay.frames import FRAME
from tools.scene_replay.rulebook import Picture
from tools.ui_lab import goldens
from tools.ui_lab.lab import photograph

MADE_WITH = "pictures.json"
MARGIN = 96
"""Px at a filmstrip's left for each frame's time."""
RULE = 2
"""Px between a filmstrip's frames."""
PAPER = QColor("#20242b")
LABEL = QColor("#e6e9ef")


def draw(picture: Picture) -> QImage:
    """The picture `picture` describes, drawn now."""
    shots: dict[int, QImage] = {}

    def each(stage: drive.Stage, n: int) -> None:
        if n in picture.frames:
            shots[n] = photograph(stage.top, True)

    stream = streams.load(picture.stream)
    with plants.planted(picture.plant or None):
        for frame in drive.play(stream, drive.Setup.named(picture.setup), each=each):
            if frame.n > max(picture.frames):
                break
    taken = [shots[n] for n in picture.frames]
    width = MARGIN + max(shot.width() for shot in taken)
    height = sum(shot.height() for shot in taken) + RULE * (len(taken) - 1)
    strip = QImage(width, height, QImage.Format.Format_RGB888)
    strip.fill(PAPER)
    painter = QPainter(strip)
    font = QFont()
    font.setPixelSize(15)
    painter.setFont(font)
    painter.setPen(LABEL)
    y = 0
    for n, shot in zip(picture.frames, taken, strict=True):
        painter.drawImage(MARGIN, y, shot)
        painter.drawText(
            QRect(0, y, MARGIN, shot.height()),
            int(Qt.AlignmentFlag.AlignCenter),
            f"{n * FRAME:.2f} s",
        )
        y += shot.height() + RULE
    painter.end()
    return strip


def _made(book: Path) -> dict[str, object]:
    path = book / "pictures" / MADE_WITH
    if not path.is_file():
        return {}
    found = json.loads(path.read_text("utf-8"))
    assert isinstance(found, dict)
    return found


def take(pictures: list[Picture], book: Path) -> None:
    """Draw every picture and keep it, with what made it."""
    folder = book / "pictures"
    folder.mkdir(parents=True, exist_ok=True)
    recipes = {}
    for picture in pictures:
        goldens.save(draw(picture), folder / picture.file)
        recipes[picture.file] = picture.recipe()
    made = {"made_with": goldens.fingerprint(), "recipes": recipes}
    (folder / MADE_WITH).write_text(
        json.dumps(made, indent=1, sort_keys=True) + "\n", "utf-8", newline="\n"
    )


def _same(now: QImage, path: Path) -> bool:
    before = QImage(str(path))
    if before.size() != now.size():
        return False
    a, b = goldens.pixels(now), goldens.pixels(before)
    changed = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return not bool((changed > goldens.CHANNEL_TOLERANCE).any())


def problems(pictures: list[Picture], book: Path) -> tuple[list[str], str]:
    """Pictures that are not what their recipe draws, and a note when this
    machine cannot judge their pixels."""
    made = _made(book)
    recipes = made.get("recipes", {})
    assert isinstance(recipes, dict)
    found = []
    for picture in pictures:
        if recipes.get(picture.file) != picture.recipe():
            found.append(
                f"{picture.file}: made from another recipe (its stream, set-up or"
                " frames changed): run rulebook --write --pictures"
            )
    if found or not pictures:
        return found, ""
    if made.get("made_with") != goldens.fingerprint():
        return [], (
            "the pictures were made on another machine (other fonts or another"
            " Qt): their recipes match; their pixels were not drawn again here"
        )
    for picture in pictures:
        if not _same(draw(picture), book / "pictures" / picture.file):
            found.append(
                f"{picture.file}: a picture that no longer reproduces: the app"
                " draws this moment differently now"
            )
    return found, ""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
