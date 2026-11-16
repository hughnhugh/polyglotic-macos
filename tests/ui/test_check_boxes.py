"""Check boxes and radio buttons in the window theme's colours, and the
first run's code box with an edge you can see (polyglotic-hq 425,
offscreen).

Preview 2 (the user, 2026-11-16): "a UI visibility bug with contrast,
particularly with the checkboxes for the consent screen". Windows' own
style drew them for Windows' light or dark mode: on a window in the other
mode, an empty box measured 1.1:1 against the window and a ticked one
1.7:1 (the radio buttons of the level picker too). Now the stylesheet
draws them from the theme - the same whatever the style underneath - at
least 3:1 against the window (WCAG 2.2's 1.4.11) in every theme, light
and dark."""

from collections import Counter
from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QStyle,
    QStyleFactory,
    QStyleOptionButton,
    QWidget,
)

from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui.consent import ConsentDialog
from polyglotic_desktop.ui.level_picker import LevelPicker
from polyglotic_desktop.ui.sign_in import SignInDialog
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.views import known_words
from polyglotic_desktop.ui_next.views.presets import contrast

LOOKS = [(name, mode) for name in theme.THEMES for mode in ("light", "dark")]
KEYS = set(QStyleFactory.keys())  # a list, not a dict
STYLES = [s for s in ("Fusion", "Windows", "windows11") if s in KEYS]
"""The styles under the stylesheet: Qt's own everywhere, and Windows 11's
- the app's on Windows, which drew the boxes unseen - where there is one."""

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted(qapp: QApplication) -> Iterator[None]:
    """Each dialog deleted as its test ends, Qt's style and the theme as
    they were (261's finding: one left over crashes the run at its exit)."""
    before = qapp.style().name()
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)
    qapp.setStyle(before)
    theme.use("dark", theme.DEFAULT_THEME)


def shown(qapp: QApplication, dialog: QWidget, look: tuple[str, str]) -> QWidget:
    theme.use(look[1], look[0])
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    dialog.resize(560, 900)
    dialog.show()
    qapp.processEvents()
    MADE.append(dialog)
    return dialog


def box_of(dialog: QWidget, button: QAbstractButton) -> QImage:
    """The button's box (its indicator), as drawn on the dialog."""
    option = QStyleOptionButton()
    button.initStyleOption(option)  # type: ignore[attr-defined]
    element = (
        QStyle.SubElement.SE_CheckBoxIndicator
        if button.metaObject().className() == "QCheckBox"
        else QStyle.SubElement.SE_RadioButtonIndicator
    )
    rect = button.style().subElementRect(element, option, button)
    rect.moveTopLeft(button.mapTo(dialog, rect.topLeft()))
    return dialog.grab().toImage().copy(rect)


def colours(image: QImage) -> list[QColor]:
    return [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
    ]


def edge(image: QImage, behind: str) -> float:
    """The box's strongest contrast with the window behind it: its edge."""
    return max(contrast(c.name(), behind) for c in colours(image))


def fill(image: QImage) -> str:
    """The colour most of a ticked box is."""
    return Counter(c.name() for c in colours(image)).most_common(1)[0][0]


@pytest.mark.parametrize("look", LOOKS)
def test_the_consent_screens_boxes_are_seen_in_every_theme(
    qapp: QApplication, look: tuple[str, str]
) -> None:
    pictures = []
    for name in STYLES:
        qapp.setStyle(name)
        dialog = shown(qapp, ConsentDialog(), look)
        assert isinstance(dialog, ConsentDialog)
        t = window_theme()
        empty = box_of(dialog, dialog.usage)
        assert edge(empty, t["BG"]) >= 3, name
        dialog.usage.setChecked(True)
        qapp.processEvents()
        ticked = box_of(dialog, dialog.usage)
        assert fill(ticked) == QColor(t["ACCENT"]).name(), name
        assert contrast(fill(ticked), t["BG"]) >= 3
        # the tick on it
        assert edge(ticked, t["ACCENT"]) >= 3, name
        pictures.append((empty, ticked))
    # drawn by the theme, not by the style underneath (Windows')
    assert all(p == pictures[0] for p in pictures), STYLES


@pytest.mark.parametrize("look", LOOKS)
def test_the_level_pickers_radio_buttons_are_seen_in_every_theme(
    qapp: QApplication, look: tuple[str, str]
) -> None:
    pictures = []
    for name in STYLES:
        qapp.setStyle(name)
        picker = LevelPicker(
            "Chinese", known_words.choices("zh"), known_words.not_sure("zh"), 2
        )
        shown(qapp, picker, look)
        t = window_theme()
        radios = [r for r in picker.findChildren(QAbstractButton) if r.isCheckable()]
        picked = next(r for r in radios if r.isChecked())
        other = next(
            r for r in radios[1:] if not r.isChecked()
        )  # not the focused first
        empty, chosen = box_of(picker, other), box_of(picker, picked)
        assert edge(empty, t["BG"]) >= 3, name
        assert contrast(fill(chosen), t["BG"]) >= 3, name
        pictures.append((empty, chosen))
    assert all(p == pictures[0] for p in pictures), STYLES


@pytest.mark.parametrize("look", LOOKS)
def test_the_tester_s_boxes_that_stay_on_still_read_as_ticked(
    qapp: QApplication, look: tuple[str, str]
) -> None:
    """A tester's usage statistics and crash reports are on and can't be
    turned off (275): drawn ticked, quieter - not empty."""
    dialog = shown(qapp, ConsentDialog(tester=True), look)
    assert isinstance(dialog, ConsentDialog)
    t = window_theme()
    locked = box_of(dialog, dialog.usage)
    assert not dialog.usage.isEnabled() and dialog.usage.isChecked()
    assert fill(locked) == QColor(t["TEXT_FAINT"]).name()
    assert edge(locked, t["TEXT_FAINT"]) >= 3  # its tick


@pytest.mark.parametrize("look", LOOKS)
def test_the_code_box_has_an_edge_you_can_see(
    qapp: QApplication, look: tuple[str, str]
) -> None:
    """The first run's code box: its edge was BORDER, 1.3:1 against the
    window - now at least 3:1 (WCAG 2.2's 1.4.11)."""
    dialog = shown(qapp, SignInDialog(lambda typed: None), look)
    assert isinstance(dialog, SignInDialog)
    dialog.code.clearFocus()
    qapp.processEvents()
    t = window_theme()
    image = dialog.grab().toImage()
    top = dialog.code.mapTo(dialog, dialog.code.rect().topLeft())
    middle = top.x() + dialog.code.width() // 2
    line = image.pixelColor(middle, top.y()).name()
    assert contrast(line, t["BG"]) >= 3, line


def test_a_tick_is_written_once_per_colour() -> None:
    first = style.tick("#ffffff")
    assert first.endswith(".svg") and first == style.tick("#FFFFFF")
    assert style.tick("#111317") != first
    with open(first, encoding="utf-8") as svg:
        assert 'stroke="#ffffff"' in svg.read()
