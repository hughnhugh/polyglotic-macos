"""The interface's text follows Windows' Text size (polyglotic-hq 138, 135's
proposal A): one factor read from the system font as Qt reads it
(`style.text_scale_of`), applied to the stylesheet, the painted fonts, the
columns and the main window's minimum - and followed while running, when
Qt reports a change. Offscreen; the text size is simulated by the
application's font (the PC's own setting is never touched)."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QRect
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QApplication, QLabel
from tests.ui.fakes import chinese_tools

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.lookup_card import WIDTH, LookupCard
from polyglotic_desktop.ui_next.main_window import (
    FLOOR,
    FLOOR_SCALE,
    FRAME,
    ROOMY,
    SIDEBAR,
    MainWindow,
    minimum_size,
    roomy_size,
)
from polyglotic_desktop.ui_next.views.lookup import Card, Shows
from polyglotic_desktop.ui_next.views.transcript import rail_inline
from polyglotic_desktop.ui_next.views.words import WordRows
from polyglotic_desktop.ui_next.word_table import ROW, Column, WordTable


@pytest.fixture
def at_100(qapp: QApplication) -> Iterator[QApplication]:
    """Each test starts, and leaves the application, at 100 %."""
    font = QFont(qapp.font())
    style.use_text_scale(1.0)
    yield qapp
    qapp.setFont(font)
    style.use_text_scale(1.0)


def points(size: float) -> QFont:
    font = QFont("Segoe UI")
    font.setPointSizeF(size)
    return font


def test_standard_cocoa_font_is_normal_and_larger_fonts_still_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(style.QGuiApplication, "platformName", lambda: "cocoa")
    assert style.text_scale_of(points(13)) == 1.0
    assert style.text_scale_of(points(19.5)) == 1.5


def test_the_text_size_is_read_from_the_system_font() -> None:
    assert style.text_scale_of(points(9)) == 1.0  # Windows' 100 %
    assert style.text_scale_of(points(11.25)) == 1.25
    assert style.text_scale_of(points(13.5)) == 1.5
    assert style.text_scale_of(points(18)) == 2.0
    assert style.text_scale_of(points(30)) == 2.25  # Windows' largest
    assert style.text_scale_of(points(8)) == 1.0  # never smaller than 100 %
    in_pixels = QFont()
    in_pixels.setPixelSize(24)  # 18 pt
    assert style.text_scale_of(in_pixels) == 2.0


def test_one_factor_scales_every_size_the_stylesheet_gives_text(
    at_100: QApplication,
) -> None:
    at_one = style.stylesheet(style.current())
    assert "font-size: 13px" in at_one and "font-size: 24px" in at_one
    style.use_text_scale(1.5)
    assert style.px(13) == 20 and style.px(24) == 36
    at_one_and_a_half = style.stylesheet(style.current())
    assert "font-size: 20px" in at_one_and_a_half  # the base: 13 px
    assert "font-size: 36px" in at_one_and_a_half  # a page's title
    assert "font-size: 13px" not in at_one_and_a_half
    style.use_text_scale(5.0)
    assert style.text_scale() == 2.25  # kept to Windows' range


def test_the_main_window_grows_with_the_text_and_its_minimum_past_the_floor_scale(
    at_100: QApplication,
) -> None:
    """The size it opens at grows with the text; its minimum stays the
    floor up to FLOOR_SCALE and widens with the text past it (polyglotic-hq
    586) - never taller: the pages and the sidebar scroll down."""
    style.use_text_scale(2.0)
    window = MainWindow(QAction("Quit"))
    assert roomy_size() == (2 * ROOMY[0], 2 * ROOMY[1])
    assert minimum_size() == (round(FLOOR[0] * 2.0 / FLOOR_SCALE), FLOOR[1])
    assert (window.minimumWidth(), window.minimumHeight()) == minimum_size()
    window.resize(*roomy_size())
    window.show()
    at_app().processEvents()
    assert window.sidebar.width() == 2 * SIDEBAR  # 960 has room for all of it
    brand = window.findChild(QLabel, "Brand")
    assert brand is not None and brand.font().pixelSize() == 30
    window.keep_in_tray = False
    window.close()


def test_a_large_text_sizes_minimum_is_kept_to_the_screen(at_100: QApplication) -> None:
    """At 200 % on a 1920 x 1080 screen at 150 % scale (1280 x 672 for the
    window), 1920 x 1360 wouldn't fit: it opens as large as the screen has
    room for, and its minimum - 844 x 520 - is under that, so every edge
    can make it smaller (polyglotic-hq 586: the minimum was the room)."""
    style.use_text_scale(2.0)
    window = MainWindow(QAction("Quit"))
    area = QRect(0, 0, 1280, 672)
    window.fit_to(area)
    room = (area.width() - FRAME, area.height() - FRAME)
    assert (window.minimumWidth(), window.minimumHeight()) == minimum_size()
    assert (window.width(), window.height()) == room
    assert window.minimumWidth() < room[0] and window.minimumHeight() < room[1]
    style.use_text_scale(1.0)
    small = MainWindow(QAction("Quit"))
    small.fit_to(QRect(0, 0, 700, 500))  # never under the floor
    assert (small.minimumWidth(), small.minimumHeight()) == FLOOR


def at_app() -> QApplication:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    return app


def reported(app: QApplication, window: MainWindow, font: QFont) -> None:
    """The system font changed, as Qt reports it to a running app's windows
    (offscreen, without the event loop, it tells only the application)."""
    app.setFont(font)
    app.sendEvent(window, QEvent(QEvent.Type.ApplicationFontChange))


def test_a_change_qt_reports_restyles_the_main_window(at_100: QApplication) -> None:
    window = MainWindow(QAction("Quit"))
    changed: list[bool] = []
    window.text_size_changed.connect(lambda: changed.append(True))
    reported(at_100, window, points(13.5))  # 150 %
    assert style.text_scale() == 1.0 and not changed  # not following: as it was
    window.follows_text_size = True
    reported(at_100, window, points(18))  # 200 %
    assert style.text_scale() == 2.0 and changed == [True]
    assert "font-size: 26px" in window.sidebar.styleSheet()
    assert window.minimumWidth() >= FLOOR[0]  # kept to the (small) offscreen screen
    reported(at_100, window, points(18))  # the same size again: nothing
    assert changed == [True]
    window.close()


def test_the_lookup_card_grows_with_the_text(at_100: QApplication) -> None:
    card = LookupCard(chinese_tools())
    word = Card("电脑", Shows.ENTRY, pinned=True)
    width = card._width(word)
    height = card._lay_out(word, width).height()
    assert width == WIDTH
    style.use_text_scale(2.0)
    assert card._width(word) == 2 * WIDTH
    assert card._lay_out(word, 2 * WIDTH).height() > height
    card.close()


def test_words_rows_grow_with_the_text_even_while_open(at_100: QApplication) -> None:
    table = WordTable(
        "words", [Column.WORD, Column.MEANING], WordRows(lambda _: None), True
    )
    assert table.verticalHeader().defaultSectionSize() == ROW
    style.use_text_scale(1.5)
    table.setStyleSheet("QTableView { border: none; }")  # restyled, as by its window
    assert table.verticalHeader().defaultSectionSize() == style.px(ROW)
    table.close()


def test_a_transcripts_rail_is_beside_the_list_only_where_it_fits() -> None:
    assert rail_inline(700) and not rail_inline(699)
    assert not rail_inline(1000, 1.5) and rail_inline(1050, 1.5)  # the rail is wider


def test_a_centred_pages_column_follows_a_new_text_size(at_100: QApplication) -> None:
    """A page kept to a centred column (today's pages) is as wide as the
    text size now says after a restyle - not the width it was built at
    (polyglotic-hq 292: a change while the window is open)."""
    window = MainWindow(QAction("Quit"))
    page = QLabel("A page")
    window.add_page("page", "Page", page, width=600)
    assert page.maximumWidth() == 600 + 72
    style.use_text_scale(1.5)
    window.restyle()
    assert page.maximumWidth() == 900 + 72
    window.keep_in_tray = False
    window.close()
