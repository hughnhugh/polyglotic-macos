"""The app's icons from symbol A's SVG masters (polyglotic-hq project 098):
the app icon at the .ico's sizes, the tray's three states for a light and
a dark taskbar, the 16 px versions on the pixel grid, and the tray
following the app's state. Offscreen."""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from tests.ui.fakes import MemorySettingsStore, make_app
from tests.ui.test_window_theme import _contrast

from polyglotic_desktop.core.listening.hotkeys import Platform
from polyglotic_desktop.ui import icons, theme
from polyglotic_desktop.ui.app import DARK_TRAY_MENU, ConnectionState, DesktopApp
from polyglotic_desktop.ui.icons import TrayState

INK, PAPER = "#172033", "#f5f6f7"
PINK, PINK_INK, GREY = "#ffa8cc", "#b0185a", "#7f8796"
LIGHT_TASKBAR, DARK_TASKBAR = "#f3f3f3", "#1c1c1c"  # Windows 11's, near enough


def _at(image: QImage, x: int, y: int) -> str:
    color = image.pixelColor(x, y)
    return color.name() if color.alpha() == 255 else f"alpha {color.alpha()}"


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
@pytest.mark.parametrize("state", list(TrayState))
def test_the_tray_states_on_the_16_px_grid(
    qapp: QApplication, state: TrayState, light: bool
) -> None:
    image = icons.render(f"tray-{'light' if light else 'dark'}-{state}", 16)
    square, bar = (INK, PAPER) if light else (PAPER, INK)
    # crisp: whole pixels inside, nothing outside the square's straight edges
    assert (_at(image, 8, 0), _at(image, 0, 8)) == ("alpha 0", "alpha 0")
    assert (_at(image, 8, 1), _at(image, 1, 8), _at(image, 14, 8)) == (square,) * 3
    if state is TrayState.PAUSED:  # a pause mark: two 3 x 8 bars, 2 px apart
        for x in (5, 10):
            assert [_at(image, x, y) for y in range(3, 13)] == [
                square,
                *[bar] * 8,
                square,
            ]
        assert [_at(image, x, 8) for x in range(3, 14)] == [
            square, bar, bar, bar, square, square, bar, bar, bar, square, square
        ]  # fmt: skip
        return
    assert [_at(image, 8, y) for y in range(3, 8)] == [square, bar, bar, bar, square]
    dots = {TrayState.LISTENING: PINK if light else PINK_INK, TrayState.IDLE: GREY}[
        state
    ]
    for x in (3, 4, 7, 8, 11, 12):  # three 2 px dots
        assert _at(image, x, 10) == _at(image, x, 11) == dots
    assert _at(image, 6, 10) == square


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_paused_reads_apart_from_listening_at_16_px(
    qapp: QApplication, light: bool
) -> None:
    """141: paused differed from listening only by three 2 px dots (12
    pixels at 16 px) - not at a glance. Now the whole inside differs."""
    taskbar = "light" if light else "dark"
    paused = icons.render(f"tray-{taskbar}-paused", 16)
    for listening_or_idle in ("listening", "idle"):
        other = icons.render(f"tray-{taskbar}-{listening_or_idle}", 16)
        differ = sum(
            paused.pixelColor(x, y) != other.pixelColor(x, y)
            for x in range(16)
            for y in range(16)
        )
        assert differ >= 40, listening_or_idle  # 54 now; 12 before


def test_each_taskbar_gets_a_square_that_shows_on_it() -> None:
    """Why there are two sets: ink on a dark taskbar is 1.05:1."""
    assert _contrast(INK, DARK_TASKBAR) < 1.1
    assert _contrast(INK, LIGHT_TASKBAR) >= 3 and _contrast(PAPER, DARK_TASKBAR) >= 3
    for dots in (PINK, GREY):  # on the ink square
        assert _contrast(dots, INK) >= 3
    for dots in (PINK_INK, GREY):  # on the paper square
        assert _contrast(dots, PAPER) >= 3


def test_the_app_icon_has_the_ico_sizes(qapp: QApplication) -> None:
    sizes = sorted(s.width() for s in icons.app_icon().availableSizes())
    assert sizes == [16, 20, 24, 32, 48, 256]
    big = icons.app_image(256)  # the 64-unit master: four round dots
    assert big.pixelColor(128, 128).name() == INK
    assert big.pixelColor(70, 168).name() == PINK  # the first dot, (17.5, 42) x 4
    assert big.pixelColor(0, 0).alpha() == 0  # rounded corners
    assert icons.app_image(16).pixelColor(3, 10).name() == PINK  # the 16 px master


@pytest.mark.parametrize(
    ("size", "master"),
    [
        (16, "polyglotic-16"),
        (24, "polyglotic-16"),
        (32, "polyglotic-16"),
        (48, "polyglotic"),
    ],
)
def test_each_size_windows_asks_for_comes_from_its_master(
    qapp: QApplication, size: int, master: str
) -> None:
    """Windows picks the window icon's size - the small one 16 px at 100%
    scaling, 24 at 150%, the big one 32 and 48 - and Qt takes it from the
    app icon as its window code does (`createHIcon`: `actualSize`, then the
    pixmap at a ratio of 1): the 16-pixel master's for the small sizes, the
    64-unit master's above (polyglotic-hq 245)."""
    icon = icons.app_icon()
    image = icon.pixmap(icon.actualSize(QSize(size, size)), 1).toImage()
    other = "polyglotic" if master == "polyglotic-16" else "polyglotic-16"
    assert image.size() == QSize(size, size)
    assert image == icons.render(master, size).convertToFormat(image.format())
    assert image != icons.render(other, size).convertToFormat(image.format())


def test_a_missing_master_says_so(qapp: QApplication) -> None:
    with pytest.raises(FileNotFoundError):
        icons.render("nothing", 16)


def _tray_app(light: bool) -> DesktopApp:
    app = DesktopApp(
        MemorySettingsStore({"whole_system": False}),
        None,
        None,
        light_taskbar=lambda: light,
    )
    app.tray = QSystemTrayIcon(app)  # offscreen has no tray: as show_tray makes it
    app.tray_icons = icons.tray_icon  # Windows' (the Mac's template: below)
    return app


def _shows(app: DesktopApp, state: TrayState, light: bool) -> bool:
    assert app.tray is not None
    expected = icons.tray_icon(state, light)
    if not app.settings.value.source_chosen:
        expected = icons.with_idle_dot(expected, theme.WARNING)
    return app.tray.icon().cacheKey() == expected.cacheKey()


def test_the_tray_follows_listening_idle_and_paused(qapp: QApplication) -> None:
    app = _tray_app(light=False)
    app.settings.update(whole_system=True)  # something picked to caption
    assert app.tray_state is TrayState.IDLE and _shows(app, TrayState.IDLE, False)
    app.set_connection(ConnectionState.LISTENING)
    assert app.tray_state is TrayState.LISTENING
    assert _shows(app, TrayState.LISTENING, False)
    app.pause.setChecked(True)
    assert _shows(app, TrayState.PAUSED, False)
    app.pause.setChecked(False)
    assert _shows(app, TrayState.LISTENING, False)
    app.settings.update(whole_system=False)  # as Home: "Pick what to caption"
    assert _shows(app, TrayState.IDLE, False)
    assert app.tray is not None and "Not captioning yet" in app.tray.toolTip()
    assert app.tray.icon().pixmap(16).toImage().pixelColor(13, 13) == QColor(
        theme.WARNING
    )
    app.settings.update(whole_system=True)
    assert "Not captioning yet" not in app.tray.toolTip()
    app.set_connection(ConnectionState.WAITING)
    assert _shows(app, TrayState.IDLE, False)
    app.close()


def test_the_tray_icon_is_drawn_for_the_taskbar(qapp: QApplication) -> None:
    app = _tray_app(light=True)
    app.set_connection(ConnectionState.NOT_CONNECTED)
    assert _shows(app, TrayState.IDLE, True)
    app.close()
    light_tray = icons.tray_icon(TrayState.IDLE, True).pixmap(16).toImage()
    dark_tray = icons.tray_icon(TrayState.IDLE, False).pixmap(16).toImage()
    assert light_tray.pixelColor(8, 8) == QColor(INK)
    assert dark_tray.pixelColor(8, 8) == QColor(PAPER)


def test_without_a_taskbar_reader_the_tray_follows_windows_apps(
    qapp: QApplication,
) -> None:
    app = make_app()  # no light_taskbar: Qt's colour scheme stands in
    app.tray = QSystemTrayIcon(app)
    app.tray_icons = icons.tray_icon  # Windows
    app.set_connection(ConnectionState.NOT_CONNECTED)
    from polyglotic_desktop.ui import theme

    assert _shows(app, TrayState.IDLE, theme.system_theme() == "light")
    app.close()


def test_the_tray_says_the_state_home_shows(qapp: QApplication) -> None:
    app = make_app()
    app.tray = QSystemTrayIcon(app)
    app.show_state_title("Listening")
    assert app.tray.toolTip() == "Polyglotic - Listening"
    app.close()


def test_the_sidebar_logo_turns_paper_on_the_dark_window(qapp: QApplication) -> None:
    """Ink on the dark sidebar would vanish: paper for ink, as the dark
    taskbar's tray icon."""

    def middle(dark: bool) -> str:
        image = icons.logo(28, dark).toImage()
        return image.pixelColor(image.width() // 2, image.height() // 2).name()

    assert middle(True) == PAPER
    assert middle(False) == INK


def test_the_tray_menu_follows_the_taskbar_not_the_apps(qapp: QApplication) -> None:
    """141: Qt drew the tray menu light (the apps' mode) beside a dark
    taskbar; Windows' own tray menus follow the taskbar."""
    dark = _tray_app(light=False)
    dark.set_connection(ConnectionState.NOT_CONNECTED)
    assert dark.tray_menu.styleSheet() == DARK_TRAY_MENU
    image = dark.tray_menu.grab().toImage()
    assert image.pixelColor(image.width() // 2, 1).lightness() < 70  # dark, inside
    transcript = QMenu("Transcript")  # as main adds it, later, with no parent
    dark.tray_menu.addMenu(transcript)
    dark.tray_menu.aboutToShow.emit()  # just before it shows
    assert transcript.styleSheet() == DARK_TRAY_MENU
    dark.close()
    light = _tray_app(light=True)
    light.set_connection(ConnectionState.NOT_CONNECTED)
    assert light.tray_menu.styleSheet() == ""  # Windows' light menu, as Qt draws it
    light.close()


# --- the Mac's menu bar (polyglotic-hq 428) ---------------------------------------


@pytest.mark.parametrize("state", list(TrayState))
@pytest.mark.parametrize("size", icons.MENU_BAR_SIZES)
def test_the_menu_bar_icon_is_a_template(
    qapp: QApplication, state: TrayState, size: int
) -> None:
    """Black and its opacity only, so macOS draws it light or dark."""
    icon = icons.menu_bar_icon(state)
    assert icon.isMask()
    image = icon.pixmap(size).toImage()
    alphas = set()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha():
                assert (color.red(), color.green(), color.blue()) == (0, 0, 0)
                alphas.add(color.alpha())
    assert 255 in alphas


def test_the_menu_bar_states_read_apart_at_16_px(qapp: QApplication) -> None:
    """Listening has the dots cut out; idle the bar alone; paused a pause
    mark - a template has no pink to tell them apart."""

    def at(state: TrayState, x: int, y: int) -> int:
        return icons.render(f"tray-template-{state}", 16).pixelColor(x, y).alpha()

    for x in (3, 7, 11):  # the dots: holes when listening only
        assert at(TrayState.LISTENING, x, 10) == 0
        assert at(TrayState.IDLE, x, 10) == 255
    assert at(TrayState.LISTENING, 8, 5) == at(TrayState.IDLE, 8, 5) == 0  # the bar
    assert at(TrayState.PAUSED, 5, 8) == 0 and at(TrayState.PAUSED, 8, 8) == 255
    assert at(TrayState.LISTENING, 8, 0) == 0 and at(TrayState.LISTENING, 8, 1) == 255


def test_on_a_mac_the_tray_is_the_menu_bars_template(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polyglotic_desktop.ui import app as app_module

    monkeypatch.setattr(app_module, "on_a_mac", lambda: True)
    monkeypatch.setattr(app_module, "platform", lambda: Platform.MAC)  # its keys (567)
    app = DesktopApp(
        MemorySettingsStore({"whole_system": False}),
        None,
        None,
        light_taskbar=lambda: False,
    )
    app.tray = QSystemTrayIcon(app)
    app.set_connection(ConnectionState.NOT_CONNECTED)
    assert app.tray.icon().isMask()
    badged = icons.with_idle_dot(icons.menu_bar_icon(TrayState.IDLE), theme.WARNING)
    assert app.tray.icon().cacheKey() == badged.cacheKey()
    # the menus' keys: Control+Command, which Qt writes Meta+Ctrl on a Mac
    assert app.lock_windows.shortcut().toString() == "Meta+Ctrl+L"
    app.close()
