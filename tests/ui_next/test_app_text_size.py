"""The app's own text size (Settings > App > Text size: Smaller, Normal,
Larger, Largest - polyglotic-hq 292, decision 0084; its steps shifted up
by 524, decision 0244): one factor on top of Windows' Text size, read from
the settings leniently, applied to every window of the app at once - Qt's
own parts (the tray's menu, tooltips) too - never under 12 px, and never
to the captions, which keep their own size. Offscreen; Windows' Text size
is simulated as `test_text_size` does."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QApplication, QMenu, QToolTip
from tests.ui.fakes import MemorySettingsStore
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.main import Panels
from polyglotic_desktop.ui import settings as app_settings
from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.main_window import ROOMY, MainWindow, roomy_size
from polyglotic_desktop.ui_next.settings_page import SettingsPage

SIZE = "interface_text_size"


@pytest.fixture
def at_normal(qapp: QApplication) -> Iterator[QApplication]:
    """Each test starts, and leaves the application, at Windows' 100 % and
    the app's Normal - and Qt's own fonts as they were."""
    font, tip = QFont(qapp.font()), QToolTip.font()
    style.use_text_scale(1.0)
    style.use_app_text_size("normal")
    yield qapp
    qapp.setFont(font)
    QToolTip.setFont(tip)
    style.use_text_scale(1.0)
    style.use_app_text_size("normal")


def test_the_four_steps_are_the_settings(at_normal: QApplication) -> None:
    assert list(style.APP_TEXT_SIZES) == list(app_settings.APP_TEXT_SIZES)
    assert style.APP_TEXT_SIZES["smaller"] == 1.0  # 0.1.9's Normal (decision 0244)


@pytest.mark.parametrize(
    ("size", "base", "faint", "title"),
    [
        ("smaller", 13, 12, 24),  # 0.1.9's Normal
        ("normal", 17, 16, 31),  # between 0.1.9's Larger (16) and Largest (19)
        ("larger", 19, 17, 35),  # 0.1.9's Largest
        ("largest", 23, 21, 42),
    ],
)
def test_each_step_sizes_the_text(
    at_normal: QApplication, size: str, base: int, faint: int, title: int
) -> None:
    style.use_app_text_size(size)
    assert (style.px(13), style.px(12), style.px(24)) == (base, faint, title)
    sheet = style.stylesheet(style.current())
    assert f"font-size: {base}px" in sheet and f"font-size: {title}px" in sheet


def test_no_step_is_smaller_than_the_interface_as_designed(
    at_normal: QApplication,
) -> None:
    """Smaller is the interface at its design sizes (0.1.9's Normal): no
    step shrinks text - 0.1.9's Smaller (0.9) took the base text to 12 px,
    the floor - nor a gap or an offset."""
    assert min(style.APP_TEXT_SIZES.values()) == 1.0
    style.use_app_text_size("smaller")
    assert (style.px(12), style.px(13), style.px(6), style.px(360)) == (12, 13, 6, 360)


def test_it_multiplies_windows_text_size(at_normal: QApplication) -> None:
    style.use_text_scale(1.5)  # Windows' 150 %
    style.use_app_text_size("normal")
    assert style.windows_text_scale() == 1.5
    assert style.text_scale() == pytest.approx(1.95)
    assert style.px(13) == 25
    assert roomy_size() == (round(ROOMY[0] * 1.95), round(ROOMY[1] * 1.95))


def test_together_they_stay_in_the_range_the_interface_is_laid_out_for(
    at_normal: QApplication,
) -> None:
    """At most Windows' largest Text size, 225 %: at Windows' 200 % and
    Largest (2.9) the UI lab found the App language picker's text and a
    caption window's notices cut off."""
    style.use_text_scale(2.0)
    style.use_app_text_size("largest")
    assert style.text_scale() == style.TEXT_SCALES[1] == 2.25
    windows = QFont()
    windows.setPointSizeF(18.0)  # Qt's own font at Windows' 200 %
    assert style.at_app_text_size(windows).pointSizeF() == pytest.approx(20.25)
    style.use_app_text_size("normal")  # 2.6: Normal too, since 0244
    assert style.text_scale() == 2.25
    style.use_app_text_size("smaller")
    assert style.text_scale() == pytest.approx(2.0)  # under it: a product


def test_a_size_it_doesnt_know_is_normal(at_normal: QApplication) -> None:
    style.use_app_text_size("huge")
    assert style.app_text_size() == 1.3


@pytest.mark.parametrize(
    ("stored", "read"),
    [
        ({}, "normal"),  # settings from before there was a choice
        ({"interface_text_size": "largest", "changed": [SIZE]}, "largest"),
        ({"interface_text_size": "huge", "changed": [SIZE]}, "normal"),
        ({"interface_text_size": 1.45, "changed": [SIZE]}, "normal"),
        ({"app_text_size": "huge"}, "normal"),  # 0.1.9's key
        ({"app_text_size": 1.45}, "normal"),
    ],
)
def test_the_setting_is_read_leniently(stored: dict[str, object], read: str) -> None:
    assert AppSettings.from_stored(stored).interface_text_size == read


def test_it_is_saved() -> None:
    store = MemorySettingsStore({})
    Settings(store).update(interface_text_size="larger")
    assert Settings(store).value.interface_text_size == "larger"


def test_settings_app_offers_it_and_shows_it(at_normal: QApplication) -> None:
    windows = CaptionWindows(None, MIC)
    panels = Panels(Settings(None), windows)
    page = SettingsPage(
        [("margin", "Margin")],
        QAction("Tell us"),
        look=panels.look,
        timing=panels.timing,
        speech=panels.languages,
    )
    chosen: list[str] = []
    page.text_size_chosen.connect(chosen.append)
    page.show_section("app")
    assert page.text_size.value() == "normal"
    page.text_size.choose("largest")
    assert chosen == ["largest"]
    page.show_text_size("smaller")
    assert page.text_size.value() == "smaller" and chosen == ["largest"]
    page.deleteLater()
    windows.close()


def test_the_main_window_follows_it_at_once(at_normal: QApplication) -> None:
    window = MainWindow(QAction("Quit"))
    changed: list[float] = []
    window.text_size_changed.connect(lambda: changed.append(style.text_scale()))
    window.set_app_text_size("largest")
    assert changed == [1.75]
    assert "font-size: 23px" in window.sidebar.styleSheet()
    assert window.minimumWidth() >= 760  # its minimum, kept to the screen
    window.set_app_text_size("largest")  # the same again: nothing
    assert changed == [1.75]
    window.keep_in_tray = False
    window.close()


def test_windows_text_size_is_still_followed_on_top_of_it(
    at_normal: QApplication,
) -> None:
    """Windows' Text size, read again while the app's is Larger: the same
    reading changes nothing (it was compared with the product, 1.45, and
    put the app back to Normal), and a new one multiplies."""
    window = MainWindow(QAction("Quit"))
    window.follows_text_size = True
    window.set_app_text_size("larger")
    changed: list[float] = []
    window.text_size_changed.connect(lambda: changed.append(style.text_scale()))
    _windows_font(at_normal, window, 9)  # Windows' 100 %, as before
    assert changed == [] and style.text_scale() == 1.45
    _windows_font(at_normal, window, 13.5)  # Windows' 150 %
    assert changed == [pytest.approx(2.175)]
    window.keep_in_tray = False
    window.close()


def _windows_font(app: QApplication, window: MainWindow, points: float) -> None:
    font = QFont("Segoe UI")
    font.setPointSizeF(points)
    app.setFont(font)
    app.sendEvent(window, QEvent(QEvent.Type.ApplicationFontChange))


def test_qt_s_own_parts_follow_it_never_under_12_px(at_normal: QApplication) -> None:
    """The tray's menu and its submenus, and tooltips with no stylesheet
    over them, are Qt's own: Windows' fonts, sized again from them."""
    menu = QMenu()
    sub = QMenu("Transcript")
    menu.addMenu(sub)
    base = QApplication.font(menu).pointSizeF()
    style.use_app_text_size("largest")
    style.size_qt_parts(menu)
    assert menu.font().pointSizeF() == pytest.approx(base * 1.75)
    assert sub.font().pointSizeF() == pytest.approx(base * 1.75)
    assert QToolTip.font().pointSizeF() == pytest.approx(
        QApplication.font().pointSizeF() * 1.75
    )
    style.size_qt_parts(menu)  # again: from Windows' fonts, not twice
    assert menu.font().pointSizeF() == pytest.approx(base * 1.75)
    style.use_app_text_size("smaller")
    style.size_qt_parts(menu)
    assert menu.font().pointSizeF() == pytest.approx(base)  # Windows' own
    menu.deleteLater()
    sub.deleteLater()


def test_a_font_in_pixels_follows_it_too(at_normal: QApplication) -> None:
    font = QFont()
    font.setPixelSize(12)
    style.use_app_text_size("largest")
    assert style.at_app_text_size(font).pixelSize() == 21
    style.use_app_text_size("smaller")
    assert style.at_app_text_size(font).pixelSize() == 12


def test_captions_keep_their_own_size(at_normal: QApplication) -> None:
    """A caption window's chrome grows with it; its captions don't - they
    have their own size, A- / A+ (the setting says so)."""
    before = window_of(at_normal)
    caption_px = before.canvas.engine.style.text_px
    style.use_app_text_size("largest")
    window = window_of(at_normal)
    assert window.canvas.engine.style.text_px == caption_px
    assert "font-size: 21px" in window.band.styleSheet()  # its 12 px chrome
    before.close()
    window.close()
