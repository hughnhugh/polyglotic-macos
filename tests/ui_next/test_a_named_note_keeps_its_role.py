"""A note given a name of its own stays the note it was.

`label(text, "Dim")` names the label "Dim" for the stylesheet; a later
`setObjectName("picker.my_speech")` - for a test or the lab to find it -
used to take the role with it, and the note drew at the full text colour
(and a faint one at the full size too): Home's "My speech: ..." line and
"0 of 3", Words' summary line, the load card's notes (polyglotic-hq 403).
"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import label


@pytest.fixture
def window(qapp: QApplication) -> Iterator[QWidget]:
    window = QWidget()
    window.setStyleSheet(style.stylesheet(style.current()))
    QVBoxLayout(window)
    yield window
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def _shown(window: QWidget, role: str, name: str | None) -> QWidget:
    note = label("A note", role)
    if name:
        note.setObjectName(name)
    layout = window.layout()
    assert layout is not None
    layout.addWidget(note)
    window.show()
    QApplication.processEvents()
    return note


def _ink(widget: QWidget) -> str:
    return widget.palette().color(QPalette.ColorRole.WindowText).name()


@pytest.mark.parametrize(
    ("role", "token"),
    [
        ("Dim", "TEXT_DIM"),
        ("PageSubtitle", "TEXT_DIM"),
        ("Faint", "TEXT_FAINT"),
        ("Warning", "WARNING"),
    ],
)
def test_a_renamed_note_keeps_its_colour(
    window: QWidget, role: str, token: str
) -> None:
    theme = style.current()
    note = _shown(window, role, "picker.my_speech")
    assert _ink(note) == QColor(theme[token]).name()
    assert _ink(note) != QColor(theme["TEXT"]).name()


def test_a_renamed_faint_note_keeps_its_size(window: QWidget) -> None:
    plain = _shown(window, "Faint", None)
    named = _shown(window, "Faint", "load.by_stage")
    assert named.fontInfo().pixelSize() == plain.fontInfo().pixelSize() == style.px(12)


def test_only_the_quiet_roles_are_found_by_property(window: QWidget) -> None:
    """A title renamed is the caller's business: its role isn't one the
    stylesheet looks up by property, so nothing else changes by this."""
    theme = style.current()
    title = _shown(window, "CardTitle", "picker.title")
    assert "CardTitle" not in style.QUIET_ROLES
    assert _ink(title) == QColor(theme["TEXT"]).name()
