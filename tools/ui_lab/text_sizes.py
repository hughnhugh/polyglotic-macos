"""The app's own text size (Settings > App: Smaller, Normal, Larger,
Largest - polyglotic-hq 292, decision 0084) on the main surfaces: the
lookup card's explanations first, Settings > App, Words, Help, a
transcript, a caption window's settings and the tray's menu.

- **Smaller:** built at it - the interface at its design sizes, 0.1.9's Normal
  (decision 0244).
- **Largest:** a window that stays open - the main window's pages, a
  transcript - built at Normal, then switched while open
  (`switch`), as the learner does it in Settings: what doesn't follow a
  change at once shows here, cut off or squashed, against its golden. The
  lookup card, a caption window's settings and the tray's menu are laid
  out each time they open: built at Largest.

The whole lab at Largest, built at it, is CI's own run
(`--app-text-size largest`): every state's checks, clipped text above all.
"""

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.main_window import MainWindow
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from tools.ui_lab import caption_window, lookup, pages, qt_parts, transcript
from tools.ui_lab.lab import Lab, State

SURFACES = {
    "w3_pinned": False,
    "w3_english_card": False,
    "w3_japanese_machine_simplified": False,
    "w3_japanese_machine_traditional": False,
    "w3_japanese_machine_english_fallback": False,
    "w3_japanese_person_then_machine": False,
    "w4_settings_app": True,
    "w4_words_full": True,
    "w4_help": True,
    "w2_1000": True,
    "w1_settings_popover": False,
    "qt_tray_menu": False,
}
"""The states shown again at Smaller and at Largest, by their names: True
if, at Largest, it's switched to while open."""


def switch(size: str) -> None:
    """The app's text size changed to `size` while the windows are open,
    as `main` follows it: the main window restyles and announces it
    (`MainWindow.set_app_text_size`), and Settings shows it; the
    transcripts and caption windows restyle (`text_size_changed`'s
    followers in `main`)."""
    shown = QApplication.topLevelWidgets()
    mains = [w for w in shown if isinstance(w, MainWindow)]
    for main in mains:
        main.set_app_text_size(size)
        for page in main.findChildren(SettingsPage):
            page.show_text_size(size)  # as the click in it shows it
    style.use_app_text_size(size)  # with no main window, too
    for other in shown:
        restyle = getattr(other, "restyle", None)
        if other not in mains and callable(restyle) and other.isVisible():
            restyle()


def _at(
    size: str, run: Callable[[Lab], QWidget], switched: bool
) -> Callable[[Lab], QWidget]:
    """`run` at the app's text size `size`: built at it, or `switched` to
    it once built at Normal. Normal again once photographed (and the lab
    sets the run's own before the next state)."""

    def state(lab: Lab) -> QWidget:
        lab.closing.append(lambda: style.use_app_text_size("normal"))
        if not switched:
            style.use_app_text_size(size)
            return run(lab)
        style.use_app_text_size("normal")
        widget = run(lab)
        switch(size)
        lab.pump()
        return widget

    return state


def _states() -> list[State]:
    every = {
        s.name: s
        for s in (
            *lookup.STATES,
            *pages.STATES,
            *transcript.STATES,
            *caption_window.STATES,
            *qt_parts.STATES,
        )
    }
    made = []
    for size in ("smaller", "largest"):
        for name, open_while_switched in SURFACES.items():
            shown = every[f"ui_next.{name}"]
            switched = size == "largest" and open_while_switched
            made.append(
                State(
                    f"ui_next.text_{size}_{name}",
                    _at(size, shown.run, switched),
                    gated=True,
                    scene=shown.scene,
                )
            )
    return made


STATES = _states()
