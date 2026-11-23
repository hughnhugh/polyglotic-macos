"""Qt's non-portal fallback QFileDialog in every window theme (polyglotic-hq 647).

On Linux sessions without xdg-desktop-portal (WSL, minimal window managers, or
a broken portal), QFileDialog.getSaveFileName falls back to Qt's built-in file
dialog. Inheriting the window's dark stylesheet set light text without styling
QTreeView / QListView backgrounds, drawing light filenames on white (644 bug 2).
"""

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QListView, QTreeView, QWidget

from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.views.presets import contrast

LOOKS = [(name, mode) for name in theme.THEMES for mode in ("light", "dark")]
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def cleanup(qapp: QApplication) -> Iterator[None]:
    yield
    while MADE:
        widget = MADE.pop()
        if shiboken6.isValid(widget):
            widget.close()
            shiboken6.delete(widget)
    qapp.processEvents()
    theme.use("dark", theme.DEFAULT_THEME)


def dominant_colour(image: QImage) -> str:
    """The colour covering most of an item view's viewport: its background."""
    counts = Counter(
        image.pixelColor(x, y).name()
        for y in range(0, image.height(), 2)
        for x in range(0, image.width(), 2)
    )
    return counts.most_common(1)[0][0]


@pytest.mark.parametrize("look", LOOKS)
def test_fallback_file_dialog_item_views_are_readable_in_every_theme(
    qapp: QApplication, tmp_path: Path, look: tuple[str, str]
) -> None:
    """Both the sidebar (QListView) and file list/tree (QTreeView/QListView)
    paint the theme's surface background so TEXT clears WCAG AA (4.5:1)."""
    (tmp_path / "transcript.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    theme.use(look[1], look[0])
    t = window_theme()
    parent = QWidget()
    parent.setStyleSheet(style.stylesheet(t))
    MADE.append(parent)

    dialog = QFileDialog(parent, "Save transcript", str(tmp_path))
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setViewMode(QFileDialog.ViewMode.Detail)
    dialog.resize(640, 420)
    dialog.show()
    qapp.processEvents()
    MADE.append(dialog)

    views = [
        v
        for v in (*dialog.findChildren(QTreeView), *dialog.findChildren(QListView))
        if v.isVisible() and v.viewport().width() > 20 and v.viewport().height() > 20
    ]
    assert views, "expected visible sidebar and file views in fallback QFileDialog"
    expected_surface = QColor(t["SURFACE"]).name()
    for view in views:
        image = view.viewport().grab().toImage()
        bg = dominant_colour(image)
        assert bg == expected_surface, (look, view.objectName(), bg, expected_surface)
        assert contrast(t["TEXT"], bg) >= 4.5, (look, view.objectName(), bg, t["TEXT"])
