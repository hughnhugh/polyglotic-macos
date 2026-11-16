"""A box of choices is marked as the chips are - the interface's own "▾"
in the text's colour - and Qt's bevelled arrow box, which poked past the
field's rounded border on every such box, is gone (polyglotic-hq 376, 403)."""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QComboBox, QVBoxLayout, QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import DROP_ROOM, Combo


@pytest.fixture
def boxes(qapp: QApplication) -> Iterator[tuple[QWidget, Combo]]:
    theme = style.current()
    window = QWidget()
    window.setStyleSheet(style.stylesheet(theme))
    column = QVBoxLayout(window)
    box = Combo()
    box.addItems(["Like this PC", "English"])
    column.addWidget(box)
    window.resize(240, 80)
    window.show()
    QApplication.processEvents()
    yield window, box
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def _picture(box: QComboBox) -> QImage:
    return box.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _near(a: QColor, b: QColor, by: int = 24) -> bool:
    mine, theirs = (a.red(), a.green(), a.blue()), (b.red(), b.green(), b.blue())
    return all(abs(x - y) <= by for x, y in zip(mine, theirs, strict=True))


def test_the_arrows_room_holds_only_the_mark(boxes: tuple[QWidget, Combo]) -> None:
    """Inside the border, the arrow's room is the field's own colour with
    the mark in the text's: no second box, no other colour."""
    _, box = boxes
    theme = style.current()
    field, text = QColor(theme["SURFACE_2"]), QColor(theme["TEXT"])
    picture = _picture(box)
    room = style.px(DROP_ROOM)
    marked = 0
    for x in range(box.width() - room, box.width() - 2):
        for y in range(2, box.height() - 2):
            pixel = picture.pixelColor(x, y)
            if _near(pixel, text, 60):
                marked += 1
            # the mark's soft edge is between the two colours, never darker
            # than the field (Qt's arrow box was near black)
            assert pixel.lightness() >= field.lightness() - 6, (x, y, pixel.name())
    assert marked > 0  # the mark is there


def test_the_right_corners_stay_round(boxes: tuple[QWidget, Combo]) -> None:
    """Nothing is drawn past the rounded border: the box's right corners
    are its left corners mirrored (Qt's arrow box squared them off)."""
    window, box = boxes
    picture = window.grab().toImage()
    left, top = box.x(), box.y()
    right, bottom = left + box.width() - 1, top + box.height() - 1
    for inset in range(3):
        for y, step in ((top, 1), (bottom, -1)):
            mirrored = picture.pixelColor(left + inset, y + inset * step)
            assert _near(
                picture.pixelColor(right - inset, y + inset * step), mirrored, 24
            )


def test_every_box_of_choices_in_the_interface_is_a_combo() -> None:
    """No page makes Qt's own box: each would bring the arrow box back."""
    from pathlib import Path

    import polyglotic_desktop.ui_next as package

    for source in Path(package.__file__).parent.glob("*.py"):
        assert "QComboBox()" not in source.read_text(encoding="utf-8"), source.name
