"""The colour dialog without Qt's eyedropper (261's decision 1, taken as 1b,
2026-11-09): "Pick Screen Color" reads the pixel under the mouse anywhere
on the screen while it picks, and Polyglotic never reads the user's screen
- the privacy notice says nothing of it. Both places that open the dialog
ask for it without: "Pick..." in the look's colours, and a category's
colour on Words."""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
import shiboken6
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QWidget
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.ui_next import colour_controls, words_page
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView

NO_EYEDROPPER = QColorDialog.ColorDialogOption.NoEyeDropperButton

MADE: list[QWidget] = []
"""Widgets a test made, deleted at its end, not at the interpreter's exit
(261)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            shiboken6.delete(made)


class Dialog:
    """The colour dialog, never shown: what it was asked, and "#123456"."""

    ColorDialogOption = QColorDialog.ColorDialogOption
    asked: ClassVar[list[tuple[Any, ...]]] = []

    @staticmethod
    def getColor(*args: Any, **kwargs: Any) -> QColor:
        Dialog.asked.append(args + tuple(kwargs.values()))
        return QColor("#123456")


@pytest.fixture
def dialog(monkeypatch: pytest.MonkeyPatch) -> type[Dialog]:
    Dialog.asked = []
    monkeypatch.setattr(colour_controls, "QColorDialog", Dialog)
    # Words opened the dialog itself before: never the real, modal one here
    monkeypatch.setattr(words_page, "QColorDialog", Dialog, raising=False)
    return Dialog


def without_eyedropper(asked: tuple[Any, ...]) -> bool:
    options = [a for a in asked if isinstance(a, QColorDialog.ColorDialogOption)]
    return bool(options) and bool(options[0] & NO_EYEDROPPER)


def test_pick_in_the_looks_colours_has_no_eyedropper(
    qapp: QApplication, dialog: type[Dialog]
) -> None:
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    MADE.append(panel)
    panel.colours["background"].pick.click()
    assert view.value.background == "#123456"
    assert len(dialog.asked) == 1 and without_eyedropper(dialog.asked[0])


def test_a_categorys_colour_on_words_has_no_eyedropper(
    qapp: QApplication, dialog: type[Dialog]
) -> None:
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    page = words_page.WordsPage(tools, None)
    MADE.append(page)
    page.resize(900, 700)
    page.show()
    QApplication.processEvents()
    category = tools.vocabulary.categories[0]
    row = next(
        r
        for r in page.first.categories.children()
        if getattr(r, "category", None) == category
    )
    row.colour.click()  # type: ignore[attr-defined]
    assert tools.vocabulary.category(category.id).color == "#123456"  # type: ignore[union-attr]
    assert len(dialog.asked) == 1 and without_eyedropper(dialog.asked[0])
