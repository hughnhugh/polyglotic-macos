"""The main window sidebar's visual states.

The sidebar is photographed in both themes, with every destination selected,
at both large text settings, and at the window's narrowest supported size.
These states keep the navigation's decorative glyphs visible in the UI lab
without making the individual page states responsible for sidebar coverage.
"""

from collections.abc import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.main_window import minimum_size
from tools.ui_lab import lab as lab_driver
from tools.ui_lab.home import _theme, hub
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.lookup import sample_tools


def _sidebar(lab: Lab, selected: str = "home", *, light: bool = False) -> QWidget:
    built = hub(lab, {"learning": "zh"}, tools=sample_tools())
    if light:
        built.window.set_theme(_theme("light", "margin"))
    built.window.go_to(selected)
    lab.pump()
    return built.window


def _selected(page: str) -> Callable[[Lab], QWidget]:
    return lambda lab: _sidebar(lab, page)


def narrow(lab: Lab) -> QWidget:
    window = _sidebar(lab)
    window.resize(*minimum_size())
    lab.pump()
    return window


def largest(lab: Lab) -> QWidget:
    lab.closing.append(lambda: style.use_app_text_size("normal"))
    style.use_app_text_size("largest")
    return _sidebar(lab)


def windows_200(lab: Lab) -> QWidget:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    previous_font = QFont(app.font())
    previous_scale = style.windows_text_scale()

    def restore() -> None:
        app.setFont(previous_font)
        style.use_text_scale(previous_scale)

    lab.closing.append(restore)
    lab_driver.use_text_size(200)
    return _sidebar(lab)


STATES = [
    State("ui_next.sidebar_dark", _selected("home"), gated=True),
    State("ui_next.sidebar_light", lambda lab: _sidebar(lab, light=True), gated=True),
    *[
        State(f"ui_next.sidebar_selected_{page}", _selected(page), gated=True)
        for page in ("home", "words", "learning", "account", "settings", "help")
    ],
    State("ui_next.sidebar_largest", largest, gated=True),
    State("ui_next.sidebar_windows_200", windows_200, gated=True),
    State("ui_next.sidebar_narrow", narrow, gated=True),
]
