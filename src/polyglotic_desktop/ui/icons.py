"""The app's icons, drawn from the SVG masters in `assets/icons` - symbol A,
"Margin" (polyglotic-hq projects 091 and 098): an ink square, a paper bar
for the word, and the dotted mark that goes under a new word.

- The app icon: the window's and the taskbar's, and - through
  `tools/package/build.py` - the exe's and the installer's .ico; the logo
  in the window's sidebar, paper for ink on the dark modes.
- The tray icon in three states - listening (pink dots), idle (grey dots),
  paused (a pause mark in the square, in place of the bar and dots: the
  bar alone differed from listening by three 2 px dots at 16 px, which
  didn't read at a glance - polyglotic-hq 141, 146) - each for a light and
  a dark taskbar: ink on a dark taskbar is only 1.05:1, so a dark taskbar
  gets a paper square.
- The Mac's menu-bar icon in the same three states, as template images
  (polyglotic-hq 428): black and its opacity only, so macOS draws it in
  the menu bar's own colour, light or dark, as it does its own icons. A
  template has no pink: listening has the dots, idle the bar alone.

Up to 32 px the icons come from masters drawn on the 16-pixel grid (every
edge on a whole pixel; 32 is exactly twice 16), larger ones from the
64-unit master. The icons are the same whichever theme the window has:
themes change the window, not the mark.
"""

from enum import StrEnum
from functools import cache
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS = Path(str(files("polyglotic_desktop.ui") / "assets" / "icons"))
ICO_SIZES = (16, 20, 24, 32, 48, 256)  # the .ico's: Windows' usual set
TRAY_SIZES = (16, 20, 24, 32)  # the tray at 100%, 125%, 150% and 200% scaling
MENU_BAR_SIZES = (16, 18, 32, 36)  # the menu bar's icon, and on a Retina screen
SMALL_UP_TO = 32  # the 16-pixel master up to this size, the 64-unit one above


class TrayState(StrEnum):
    LISTENING = "listening"  # captioning: the dots pink
    IDLE = "idle"  # nothing being captioned: the dots grey
    PAUSED = "paused"  # the learner paused captions: a pause mark


def render(master: str, size: int) -> QImage:
    """The master `assets/icons/<master>.svg` drawn at `size` x `size`
    pixels. Raises if the master is missing: `--check-install` then says so
    for a packed app with a part left out."""
    renderer = QSvgRenderer(str(ICONS / f"{master}.svg"))
    if not renderer.isValid():
        raise FileNotFoundError(f"no icon master {master}.svg in {ICONS}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def app_image(size: int) -> QImage:
    """The app icon at one size, from the master that suits it."""
    return render("polyglotic-16" if size <= SMALL_UP_TO else "polyglotic", size)


@cache
def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICO_SIZES:
        icon.addPixmap(QPixmap.fromImage(app_image(size)))
    return icon


def logo(size: int, dark: bool) -> QPixmap:
    """The logo inside the window: on its dark modes, paper for ink (the
    ink square would vanish on a dark sidebar), as the dark taskbar's tray
    icon. `size` in device pixels."""
    return QPixmap.fromImage(render("polyglotic-dark" if dark else "polyglotic", size))


@cache
def tray_icon(state: TrayState, light_taskbar: bool) -> QIcon:
    """The tray icon in `state`, for a light or a dark taskbar."""
    master = f"tray-{'light' if light_taskbar else 'dark'}-{state}"
    icon = QIcon()
    for size in TRAY_SIZES:
        icon.addPixmap(QPixmap.fromImage(render(master, size)))
    return icon


def menu_bar_icon(state: TrayState, _light_menu_bar: bool = True) -> QIcon:
    """The Mac's menu-bar icon in `state`: a template (`isMask`), which macOS
    draws for a light or a dark menu bar itself (the flag is ignored)."""
    return _template(state)


@cache
def _template(state: TrayState) -> QIcon:
    icon = QIcon()
    for size in MENU_BAR_SIZES:
        icon.addPixmap(QPixmap.fromImage(render(f"tray-template-{state}", size)))
    icon.setIsMask(True)
    return icon
