"""The feedback form (offscreen) and where it opens from (project 053): the kind,
the text, a reply address (needed to work with us), the log shown before
it's sent; one click from the tray, Home and Account. Made-up text only."""

import os
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton
from tests.ui.fakes import Built
from tests.ui.test_consent_dialog import SCREENSHOTS

from polyglotic_desktop.adapters.feedback_files import FeedbackFolder
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.feedback import Outcome
from polyglotic_desktop.main import (
    QtFeedback,
    ask_for_feedback,
    new_report,
    window_theme,
)
from polyglotic_desktop.ui.feedback import FeedbackDialog, can_send
from polyglotic_desktop.ui_next import style

LOG = "2026-11-05 10:01:12 INFO connection: session opened\n"


def dialog(kind: Any = "problem", log: str | None = LOG) -> FeedbackDialog:
    return FeedbackDialog(kind, lambda: log, "Polyglotic 0.1.0, windows-11", True)


def test_what_can_be_sent() -> None:
    assert not can_send("problem", "   ", "")
    assert can_send("problem", "It froze.", "")
    assert not can_send("problem", "x" * 5001, "")
    assert not can_send("work_with_us", "Happy to help.", "  ")
    assert can_send("work_with_us", "Happy to help.", "tester_42")
    assert not can_send("question", "Why?", "two\nlines")


def test_a_problem_attaches_the_log_and_shows_it_first(qapp: QApplication) -> None:
    form = dialog()
    assert form.chosen_kind() == "problem"
    assert form.attach.isChecked()
    assert not form.log_view.isHidden()
    assert form.log_view.toPlainText() == LOG  # what's shown is what goes
    assert not form.send.isEnabled()  # nothing written yet
    form.text.setPlainText("  The overlay stayed empty.  ")
    form.reply.setText(" tester@example.com ")
    assert form.send.isEnabled()
    assert form.report() == (
        "problem",
        "The overlay stayed empty.",
        "tester@example.com",
        LOG,
    )
    form.attach.setChecked(False)
    assert form.log_view.isHidden()
    assert form.report()[3] is None


def test_a_suggestion_doesnt_attach_the_log_until_ticked(qapp: QApplication) -> None:
    form = dialog("suggestion")
    assert form.windowTitle() == "Suggest something"
    assert not form.attach.isChecked() and form.log_view.isHidden()
    form.text.setPlainText("A dark theme, please.")
    assert form.report() == ("suggestion", "A dark theme, please.", None, None)


def test_without_a_log_there_is_nothing_to_attach(qapp: QApplication) -> None:
    form = dialog(log=None)
    assert not form.attach.isChecked() and not form.attach.isEnabled()


def test_working_with_us_needs_a_way_to_reply(qapp: QApplication) -> None:
    form = dialog()
    form.kind.setCurrentIndex(form.kind.findData("work_with_us"))
    form.text.setPlainText("I build Qt apps.")
    assert not form.send.isEnabled()
    assert "needed" in form.reply_label.text()
    form.reply.setText("tester_42")
    assert form.send.isEnabled()


def test_the_form_says_what_else_goes_and_about_ai_help(qapp: QApplication) -> None:
    form = dialog()
    texts = " ".join(label.text() for label in form.findChildren(type(form.title)))
    assert "Polyglotic 0.1.0, windows-11" in texts
    assert "listening session's ID" in texts
    assert "No screenshot" in texts
    assert "AI tools (Anthropic's Claude)" in texts
    if os.environ.get("POLYGLOTIC_SCREENSHOTS"):  # with QT_QPA_FONTDIR for glyphs
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        form.setStyleSheet(style.stylesheet(window_theme()))  # as shown
        form.text.setPlainText("The overlay stayed empty after I switched to the mic.")
        form.show()
        form.adjustSize()
        qapp.processEvents()
        form.grab().save(str(SCREENSHOTS / "feedback.png"))
        form.close()


def test_one_click_from_the_tray_home_and_account(qapp: QApplication) -> None:
    built = Built()
    app = built.desktop
    asked: list[str] = []
    app.feedback_wanted.connect(asked.append)
    tray = [a.objectName() for a in app.tray_menu.actions()]
    assert "feedback.problem" in tray and "feedback.suggestion" in tray
    home = [
        b
        for b in built.hub.home.findChildren(QToolButton)
        if b.defaultAction() in (app.report_problem, app.suggest)
    ]
    assert len(home) == 2
    home[0].click()
    account = [
        b
        for b in built.hub.account.findChildren(QPushButton)
        if b.objectName() == "feedback.suggestion"
    ]
    account[0].click()
    assert asked == ["problem", "suggestion"]
    built.close()


def test_a_report_is_kept_with_what_goes_with_every_one(
    qapp: QApplication, tmp_path: Path, monkeypatch: Any
) -> None:
    folder = FeedbackFolder(tmp_path / "feedback")
    app_info = AppInfo("0.1.0", "windows-11", os_version="10.0.26200")

    def sent(self: FeedbackDialog) -> int:
        self.text.setPlainText("It froze.")
        return 1

    monkeypatch.setattr(FeedbackDialog, "exec", sent)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "polyglotic.log").write_text(LOG, "utf-8")
    report = ask_for_feedback("problem", tmp_path / "logs", app_info, "s-1", folder)
    assert report is not None
    assert folder.waiting() == [report]
    assert (report.kind, report.text, report.log) == ("problem", "It froze.", LOG)
    assert (report.app_version, report.os, report.session_id) == (
        "0.1.0",
        "windows-11",
        "s-1",
    )
    # the OS's version number as its adapters said it (decision 0038)
    assert report.os_version == "10.0.26200" and report.at.endswith("Z")


def test_what_became_of_a_report_shows_on_home(qapp: QApplication) -> None:
    built = Built()
    app, notice = built.desktop, built.hub.home.state.notice
    shown = QtFeedback(app)
    report = new_report(
        "problem", "x", None, None, AppInfo("0.1.0", "windows-11"), None
    )
    shown.just_sent = report.id
    shown.outcome(report, Outcome.WAITING)
    qapp.processEvents()
    assert "will be sent when the server can be reached" in notice.text()
    shown.outcome(report, Outcome.SENT)
    qapp.processEvents()
    assert notice.text() == "Thanks - we have your report."
    built.hub.home.state.set_notice(None)
    older = new_report("problem", "y", None, None, AppInfo("0.1.0", "windows-11"), None)
    shown.outcome(older, Outcome.WAITING)  # an older one still waiting: nothing said
    qapp.processEvents()
    assert notice.isHidden()
    built.close()


def test_a_quiet_line_in_settings_invites_people_to_work_with_us(
    qapp: QApplication,
) -> None:
    built = Built()
    app = built.desktop
    asked: list[str] = []
    app.feedback_wanted.connect(asked.append)
    account = built.hub.settings
    texts = " ".join(label.text() for label in account.findChildren(QLabel))
    assert "Want to help build Polyglotic?" in texts
    [tell_us] = [
        b
        for b in account.findChildren(QToolButton)
        if b.defaultAction() is app.work_with_us
    ]
    assert tell_us.text() == "Tell us"
    tell_us.click()
    assert asked == ["work_with_us"]
    # not a banner: nowhere else
    tray = [a.objectName() for a in app.tray_menu.actions()]
    assert "feedback.work_with_us" not in tray
    home = [
        b
        for b in built.hub.home.findChildren(QToolButton)
        if b.defaultAction() is app.work_with_us
    ]
    assert home == []
    assert account.version.isHidden()
    account.set_version("0.1.0", "win-x64-alpha")
    assert account.version.text() == "Version 0.1.0 (win-x64-alpha)."
    built.close()


def test_the_form_opened_to_work_with_us_needs_a_reply(qapp: QApplication) -> None:
    form = dialog("work_with_us")
    assert form.windowTitle() == "Help build Polyglotic"
    assert not form.attach.isChecked()  # no log for an introduction
    form.text.setPlainText("I build Qt apps and use the captions daily.")
    assert not form.send.isEnabled()
    form.reply.setText("tester@example.com")
    assert form.send.isEnabled()
    assert form.report()[:3] == (
        "work_with_us",
        "I build Qt apps and use the captions daily.",
        "tester@example.com",
    )


def test_tab_leaves_the_text_box(qapp: QApplication) -> None:
    """QA 278, by keyboard only: Tab in the text box typed a tab character
    instead of going on to what's below it."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    form = dialog()
    form.show()
    form.activateWindow()
    form.text.setFocus()
    qapp.processEvents()
    QTest.keyClick(form.text, Qt.Key.Key_Tab)
    assert form.text.toPlainText() == ""
    assert qapp.focusWidget() is not form.text
    form.close()
    form.deleteLater()
