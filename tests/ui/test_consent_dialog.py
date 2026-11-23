"""The consent screen and deleting learning data (offscreen): every choice
off until the user says yes, the current choices shown from settings,
what the service needs explained but not asked; deleting on this PC is a
choice of its own."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QPushButton,
)

from polyglotic_desktop.core.shared.papers import (
    PRIVACY_NOTICE,
    TESTER_AGREEMENT,
    TESTER_AGREEMENT_VERSION,
)
from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ui.consent import ConsentDialog, agreement_needed
from polyglotic_desktop.ui.delete_learning import DeleteLearningDialog
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.os_words import pc_or_mac

SCREENSHOTS = Path(__file__).resolve().parents[2] / "build" / "screenshots"


def test_every_choice_is_off_until_the_user_says_yes(qapp: QApplication) -> None:
    dialog = ConsentDialog()
    boxes = dialog.findChildren(QCheckBox)
    assert [b.objectName() for b in boxes] == [
        "consent.usage",
        "consent.crashes",
        "consent.exposures",
        "consent.agreement",
    ]
    assert [b.text() for b in boxes] == [
        "Usage statistics",
        "Crash reports",
        "Share how often you hear words",
        "I agree to the tester agreement.",
    ]
    assert not any(b.isChecked() for b in boxes)
    assert dialog.choices() == (False, False, False)
    dialog.exposures.setChecked(True)
    assert dialog.choices() == (False, False, True)


def test_settings_show_the_choices_so_far(qapp: QApplication) -> None:
    current = ConsentChoice("id", datetime(2026, 11, 4, tzinfo=UTC), True, False, True)
    assert ConsentDialog(current).choices() == (True, False, True)


AGREED = Agreement(TESTER_AGREEMENT_VERSION, datetime(2026, 11, 16, 9, tzinfo=UTC))


def test_no_further_without_the_yes_to_the_agreement(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 185: Continue waits for the yes, and the other way out
    is Quit. The screen names no age (the user, 2026-11-11): the papers do."""
    dialog = ConsentDialog(clock=lambda: AGREED.at)
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    shown = texts + [box.text() for box in dialog.findChildren(QCheckBox)]
    assert not any("or older" in text for text in shown)
    assert dialog.asks and not dialog.ok.isEnabled()
    assert dialog.quit.text() == "Quit Polyglotic"
    assert dialog.agreement() is None
    assert dialog.agree is not None
    # its words are never cut off: a check box doesn't wrap, so it has the
    # dialog's width to itself (cut by the button beside it, 185's pictures)
    dialog.show()
    dialog.resize(dialog.minimumWidth(), dialog.height())
    qapp.processEvents()
    assert dialog.agree.width() >= dialog.agree.sizeHint().width()
    dialog.close()
    dialog.agree.setChecked(True)
    assert dialog.ok.isEnabled()
    assert dialog.agreement() is None  # given with Continue (polyglotic-hq 250)
    dialog.ok.click()
    assert dialog.agreement() == AGREED
    dialog.agree.setChecked(False)
    assert not dialog.ok.isEnabled() and dialog.agreement() is None


def test_the_papers_open_in_the_browser(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    dialog = ConsentDialog()
    for name in ("consent.privacy_notice", "consent.tester_agreement"):
        button = dialog.findChild(QPushButton, name)
        assert button is not None
        button.click()
    assert opened == [PRIVACY_NOTICE, TESTER_AGREEMENT]


def test_enter_on_the_first_screen_never_opens_the_browser(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first screen opens with the focus on "Read the privacy notice":
    a keyboard user's Enter - to go on - opened the browser (polyglotic-hq
    203). Enter goes to Continue, which waits for the yes; Space on the
    focused button still opens the page."""
    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    dialog = ConsentDialog()
    dialog.show()
    button = dialog.findChild(QPushButton, "consent.privacy_notice")
    assert button is not None
    button.setFocus()
    qapp.processEvents()
    QTest.keyClick(button, Qt.Key.Key_Return)
    assert opened == [] and dialog.isVisible()  # Continue waits for the yes
    assert dialog.agree is not None
    dialog.agree.setChecked(True)
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Return)
    assert opened == [] and dialog.result() == QDialog.DialogCode.Accepted
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert opened == [PRIVACY_NOTICE]


class ShortScreen:
    """A screen's work area: 1920 x 1080 at 150 %, the taskbar left out."""

    def availableGeometry(self) -> QRect:
        return QRect(0, 0, 1280, 672)


@pytest.mark.parametrize("size", ["smaller", "normal", "largest"])
def test_the_first_screen_fits_a_150_percent_laptop_with_continue_in_view(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, size: str
) -> None:
    """At 150 % on a 1920 x 1080 laptop the first screen was 721 px tall
    with 672 px above the taskbar: Continue sat under the taskbar, and
    there's no going on without it (polyglotic-hq 203). The explanation and
    choices scroll now; the yes and Continue stay in view, nothing is cut -
    at each of the app's text sizes (Normal, the default, is 1.3: 524)."""
    style.use_app_text_size(size)
    dialog = ConsentDialog()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    monkeypatch.setattr(dialog, "screen", lambda: ShortScreen())
    dialog.show()
    qapp.processEvents()
    qapp.processEvents()
    assert dialog.height() + 40 <= 672  # with Windows' title bar
    assert dialog.agree is not None
    for shown in (dialog.agree, dialog.ok):
        bottom = shown.mapTo(dialog, shown.rect().bottomLeft()).y()
        assert shown.isVisible() and bottom <= dialog.height()
    wrapped = [found for found in dialog.body.findChildren(QLabel) if found.wordWrap()]
    cut = [
        found.accessibleName()
        for found in wrapped
        if found.heightForWidth(found.width()) > found.height()
    ]
    assert cut == []  # scrolled to, never cut off
    dialog.close()


class TallScreen:
    def availableGeometry(self) -> QRect:
        return QRect(0, 0, 1920, 1040)


TALL_SIZES = [("smaller", 1.0), ("normal", 1.0), ("normal", 1.1)]
"""The app's text sizes, and Windows': at Normal (1.3) and Windows' 110 %
the text is wider still - as Linux's fonts are at Normal, where the first
screen scrolled in CI (polyglotic-hq 524) - and the screen grows wider
rather than scroll (`ConsentDialog._fit`, `WIDEST`)."""


@pytest.mark.parametrize(("size", "windows"), TALL_SIZES)
def test_on_a_tall_screen_nothing_scrolls(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, size: str, windows: float
) -> None:
    """At the app's default text size too (polyglotic-hq 524: at 1.3 its
    fixed 520 px scrolled the first screen on a 1920 x 1080 screen): its
    least width grows with its text (`TextDialog.set_least_width`), and it
    grows wider before it scrolls."""
    style.use_app_text_size(size)
    style.use_text_scale(windows)
    dialog = ConsentDialog()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    monkeypatch.setattr(dialog, "screen", lambda: TallScreen())
    dialog.show()
    qapp.processEvents()
    qapp.processEvents()
    assert not dialog.scroll_area.verticalScrollBar().isVisible()
    assert dialog.scroll_area.height() >= dialog.body.heightForWidth(
        dialog.body.width()
    )
    dialog.close()


@pytest.mark.parametrize(("size", "windows"), TALL_SIZES)
def test_on_a_tall_screen_no_scroll_bar_flashes_at_the_first_paint(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, size: str, windows: float
) -> None:
    """269 and 278 saw it on real windows: the screen first painted with a
    scroll bar over its text - cutting words at the right and the
    explanation's last line - until a later layout pass took the bar away.
    It all fits, so no bar from the first paint on."""
    from PySide6.QtCore import QEvent, QObject

    style.use_app_text_size(size)
    style.use_text_scale(windows)
    dialog = ConsentDialog()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    monkeypatch.setattr(dialog, "screen", lambda: TallScreen())
    at_first_paint: list[bool] = []

    class FirstPaint(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            painted = watched is dialog and event.type() == QEvent.Type.Paint
            if painted and not at_first_paint:
                bar = dialog.scroll_area.verticalScrollBar()
                at_first_paint.append(bar.isVisible())
            return False

    watcher = FirstPaint()
    dialog.installEventFilter(watcher)
    dialog.show()
    qapp.processEvents()
    qapp.processEvents()
    assert at_first_paint == [False]
    dialog.removeEventFilter(watcher)
    dialog.close()


def test_asked_again_only_for_new_words_of_the_agreement(qapp: QApplication) -> None:
    at = datetime(2026, 11, 4, tzinfo=UTC)
    assert agreement_needed(None)  # the first run
    assert agreement_needed(ConsentChoice("a", at, True, False, False))  # before 185
    older = Agreement("tester-2026-11-05", at)
    assert agreement_needed(ConsentChoice("a", at, True, False, False, older))
    given = ConsentChoice("a", at, True, False, False, AGREED)
    assert not agreement_needed(given)
    # from Account: when, and no box to tick again
    dialog = ConsentDialog(given)
    assert not dialog.asks and dialog.agree is None and dialog.ok.isEnabled()
    assert dialog.findChild(QPushButton, "consent.quit") is None
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "You agreed to the tester agreement on" in texts
    assert dialog.agreement() is None  # nothing new: the exchange keeps the old


def test_what_the_service_needs_is_explained_not_asked(qapp: QApplication) -> None:
    dialog = ConsentDialog()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    for words in ("never stored", "never its name", "aren't optional", "delete"):
        assert words in texts
    # why learning data is kept, as the privacy notice says (project 041):
    # saved words and statuses sync; lookups aren't synced, they're kept to
    # learn how people learn
    assert (
        "saved words and word statuses follow you to another "
        + pc_or_mac("PC", "computer")
    ) in texts
    assert "your lookups show us how people learn" in texts
    # the server keeps a Windows version only with feedback the user sends
    assert "Windows version" not in texts
    if os.environ.get("POLYGLOTIC_SCREENSHOTS"):  # with QT_QPA_FONTDIR for glyphs
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        dialog.setStyleSheet(style.stylesheet(window_theme()))  # as shown
        dialog.exposures.setChecked(True)
        dialog.show()
        dialog.adjustSize()
        qapp.processEvents()
        dialog.grab().save(str(SCREENSHOTS / "consent.png"))
        dialog.close()


def test_deleting_on_this_pc_is_a_separate_choice_off_until_ticked(
    qapp: QApplication,
) -> None:
    dialog = DeleteLearningDialog()
    assert not dialog.delete_on_this_pc()
    dialog.on_this_pc.setChecked(True)
    assert dialog.delete_on_this_pc()


def test_deleting_says_every_language_goes_from_the_server_and_this_pc(
    qapp: QApplication,
) -> None:
    # `learning_delete` names no language: the server deletes every
    # language's learning data; this PC's copy is per language (project 043)
    # and every open language's file is emptied (DECISIONS #135, 306) - not
    # "for the language you're learning now", which with two open was
    # ambiguous.
    dialog = DeleteLearningDialog()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "in every language you learn" in texts
    box = dialog.on_this_pc.text()
    assert "in every language you're learning" in box
    assert "learning now" not in box


def test_usage_statistics_say_which_app_names_are_shared(qapp: QApplication) -> None:
    """Known app names (polyglotic-hq DECISIONS.md #30): the choice says
    the well-known app listened to most is included, and no other name."""
    dialog = ConsentDialog(None)
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "which well-known app you listen to most" in text
    assert "never the name of any other app" in text


def test_what_the_service_needs_is_shown_in_full(qapp: QApplication) -> None:
    """The intro paragraph is nine lines at the dialog's width; Qt's size
    hint for wrapped text guessed a shorter dialog and cut it off (135,
    2026-11-07)."""
    dialog = ConsentDialog()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    dialog.show()
    qapp.processEvents()
    qapp.processEvents()
    wrapped = [found for found in dialog.findChildren(QLabel) if found.wordWrap()]
    assert "needed" in [found.accessibleName() for found in wrapped]
    cut = {
        found.accessibleName(): (found.height(), found.heightForWidth(found.width()))
        for found in wrapped
        if found.heightForWidth(found.width()) > found.height()
    }
    dialog.close()
    assert cut == {}


def test_deleting_says_how_many_copies_set_aside_go_with_it(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 207: the copies set aside after damage hold the same
    data, and go with it - said only when there are some."""
    dialog = DeleteLearningDialog(set_aside=2)
    assert dialog.set_aside is not None
    assert dialog.set_aside.text() == (
        "This also deletes the 2 copies of your learning data set aside on this "
        + pc_or_mac("PC", "Mac")
        + " when it was found damaged."
    )
    one = DeleteLearningDialog(set_aside=1)
    assert one.set_aside is not None and "the 1 copy of" in one.set_aside.text()
    assert DeleteLearningDialog().set_aside is None


def test_the_copies_set_aside_are_said_to_go_only_while_this_pc_is_ticked(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 223: unticked, nothing on this PC is deleted, the copies
    set aside included - so "This also deletes the 1 copy..." shows only
    while "Also delete it from this PC" is ticked (QA saw it promised with
    the box unticked)."""
    dialog = DeleteLearningDialog(set_aside=1)
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    dialog.resize(865, dialog.heightForWidth(865))
    dialog.show()
    qapp.processEvents()
    line = dialog.set_aside
    assert line is not None
    assert not dialog.delete_on_this_pc() and not line.isVisible()
    dialog.on_this_pc.setChecked(True)
    qapp.processEvents()
    assert line.isVisible()
    # the dialog grew for it: nothing above it squeezed (QA saw the title cut)
    for label in dialog.findChildren(QLabel):
        if label.isVisible() and label.wordWrap():
            assert label.height() >= label.heightForWidth(label.width()), label.text()
    dialog.on_this_pc.setChecked(False)
    qapp.processEvents()
    assert not line.isVisible()
    dialog.close()


def test_nothing_runs_on_a_dialog_deleted_before_its_first_fit(
    qapp: QApplication,
) -> None:
    """The dialog fits itself a moment after it's shown. One deleted before
    that moment must not be fitted: the timer's call on a deleted dialog
    raised inside a later test's wait (polyglotic-hq 277: Linux's checks
    failed on main in test_look_drag.py and test_settings_handoff.py)."""
    import shiboken6

    dialog = ConsentDialog()
    dialog.show()  # asks for a fit, and to be kept on screen, once events are handled
    shiboken6.delete(dialog)
    QTest.qWait(20)  # pytest-qt fails the test if a call raised in here
