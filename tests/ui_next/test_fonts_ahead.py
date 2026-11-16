"""Windows' fonts read ahead of the first window (`ui_next/fonts_ahead.py`,
polyglotic-hq 322, decision 0112), and the interface's fonts set without a
look at Windows' while they are (`style.use_interface_language`)."""

import threading

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.fonts_ahead import THREAD, FontsAhead

YAHEI, JHENGHEI = "microsoft yahei ui", "microsoft jhenghei ui"  # as Qt keeps them
CHINESE = (YAHEI, JHENGHEI)


def test_offscreen_nothing_is_read_ahead(qapp: QApplication) -> None:
    """The tests, the start gate, `--check-install`: Qt reads its fonts
    another way there, at once."""
    read: list[str] = []
    fonts = FontsAhead(lambda: read.append(threading.current_thread().name))

    assert QGuiApplication.platformName() == "offscreen"
    assert not fonts.begin()
    fonts.wait()  # nothing to wait for

    assert read == []


def test_with_real_windows_the_fonts_are_read_on_a_thread_of_their_own(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "windows")
    let_go = threading.Event()
    read: list[str] = []

    def reading() -> None:
        let_go.wait(5)
        read.append(threading.current_thread().name)

    fonts = FontsAhead(reading)

    assert fonts.begin()
    assert not fonts.begin()  # once
    assert read == []  # this thread goes on meanwhile
    let_go.set()
    fonts.wait()

    assert read == [THREAD]
    fonts.wait()  # again: at once


def test_an_os_with_no_such_call_reads_them_as_before(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "windows")
    fonts = FontsAhead(None)
    assert not fonts.begin()
    fonts.wait()


def test_the_interfaces_fonts_are_set_without_listing_windows_fonts(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At start, while Windows' fonts are being read: listing Qt's families
    would wait for them (about 0.1 s, the first use of the font database).
    The fonts the interface names have its Chinese behind them all the same;
    every other family gets it from the whole call, once they're read."""
    other = next(
        family
        for family in QFontDatabase.families()
        if family not in style._WITH_SYMBOLS and family != qapp.font().family()
    )
    before = QFont.substitutes(other)
    QFont.removeSubstitutions(other)

    def listed(*_: object) -> list[str]:
        raise AssertionError("Windows' fonts were listed")

    try:
        with monkeypatch.context() as patched:
            patched.setattr(QFontDatabase, "families", listed)
            style.use_interface_language("zh_TW", listed=False)
        assert QFont.substitutes("Segoe UI")[1:3] == [JHENGHEI, YAHEI]
        # the application's own font too, whichever it is here (after the
        # symbols' face if the interface also names it)
        own = [f for f in QFont.substitutes(qapp.font().family()) if f in CHINESE]
        assert own == [JHENGHEI, YAHEI]
        assert style.UI_FAMILIES.index(
            "Microsoft JhengHei UI"
        ) < style.UI_FAMILIES.index("Microsoft YaHei UI")
        assert QFont.substitutes(other) == []  # not yet

        style.use_interface_language("zh_TW")  # the whole call

        assert QFont.substitutes(other)[:2] == [JHENGHEI, YAHEI]
    finally:
        style.use_interface_language("en")
        QFont.removeSubstitutions(other)
        QFont.insertSubstitutions(other, before)
