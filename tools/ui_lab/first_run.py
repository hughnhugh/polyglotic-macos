"""The first run's screens - Your data (the consent screen), the level and
the code - as `main.first_run` shows them: today's dialogs, each in the
window theme's stylesheet (polyglotic-hq 425: the consent screen's check
boxes, drawn for Windows' mode, were unseen on a window in the other).
Your data in each theme, light and dark, a choice ticked; a tester's, its
two choices on for good; the level and the code in Margin, light and dark.

Not timed: shown once, at the first run."""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import interface_language, theme
from polyglotic_desktop.ui.consent import ConsentDialog
from polyglotic_desktop.ui.language_picker import LanguagePicker
from polyglotic_desktop.ui.level_picker import LevelPicker
from polyglotic_desktop.ui.sign_in import SignInDialog
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.views import known_words
from tools.ui_lab.lab import Lab, State

SIZE = (560, 820)
"""Your data's room. The lab's screen leaves it 760 px of height: in Margin
and Glaze, their heading faces loaded, the text scrolls there (437), as it
does on a screen that short; Signal's fits."""


def _shown(lab: Lab, dialog: QWidget, name: str, mode: str) -> QWidget:
    """`dialog` in theme `name`'s `mode`, as the first run styles it - its
    heading face loaded, as `main.first_run` has it (`theme.apply`), not
    only if a state before happened to load it (polyglotic-hq 437: train
    10's first-run titles came out in Margin's Literata, the goldens' in
    the fallback sans); the theme back to the lab's (Margin, dark) once
    photographed."""
    theme.apply(mode, name)
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    dialog.show()
    lab.pump()
    lab.closing.append(dialog.close)
    lab.closing.append(lambda: theme.use("dark", theme.DEFAULT_THEME))
    return dialog


def consent(name: str, mode: str) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        dialog = ConsentDialog()
        dialog.usage.setChecked(True)  # one ticked, two not
        dialog.resize(*SIZE)
        return _shown(lab, dialog, name, mode)

    return run


def tester(lab: Lab) -> QWidget:
    """A tester's: usage statistics and crash reports on, and staying on."""
    dialog = ConsentDialog(tester=True)
    dialog.resize(*SIZE)
    return _shown(lab, dialog, "margin", "dark")


def level(mode: str) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        picker = LevelPicker(
            "Chinese", known_words.choices("zh"), known_words.not_sure("zh"), 2
        )
        return _shown(lab, picker, "margin", mode)

    return run


def language(mode: str) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        picker = LanguagePicker(interface_language.picker(), "de")
        return _shown(lab, picker, "margin", mode)

    return run


def code(mode: str) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        return _shown(lab, SignInDialog(lambda typed: None), "margin", mode)

    return run


STATES = [
    *(
        State(f"ui_next.first_run_language_{mode}", language(mode), gated=True)
        for mode in ("light", "dark")
    ),
    *(
        State(
            f"ui_next.first_run_consent_{name}_{mode}", consent(name, mode), gated=True
        )
        for name in theme.THEMES
        for mode in ("light", "dark")
    ),
    State("ui_next.first_run_consent_tester", tester, gated=True),
    *(
        State(f"ui_next.first_run_level_{mode}", level(mode), gated=True)
        for mode in ("light", "dark")
    ),
    *(
        State(f"ui_next.first_run_code_{mode}", code(mode), gated=True)
        for mode in ("light", "dark")
    ),
]
