"""Qt's own parts the interface shows with no window's stylesheet naming
their fonts (polyglotic-hq 215): the tray's menu, a caption window's
tooltip, and a Qt dialog with no window under it (the sign-out question).
Their Chinese is in the interface's Chinese face, which the app puts
behind every font at start (`style.use_chinese_behind_every_font`) -
before it, in MS UI Gothic, a Japanese face, as Windows draws Chinese a
font list has no face for in an English locale; the `japanese_font` check
finds that in zh_CN and zh_TW.

Not timed: Qt's own, and nothing of the interface's runs in them."""

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QHBoxLayout,
    QLabel,
    QSystemTrayIcon,
    QToolTip,
    QWidget,
)

from polyglotic_desktop.main import problem_report_parts
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.feedback import FeedbackDialog
from polyglotic_desktop.ui.icons import TRAY_SIZES, tray_icon
from polyglotic_desktop.ui.problem_report import Part, ProblemReportDialog
from polyglotic_desktop.ui.sign_in import sign_out_question
from polyglotic_desktop.ui_next import style
from tools.ui_lab import caption_window
from tools.ui_lab.home import MadeUpApps, Memory
from tools.ui_lab.lab import Lab, State


def tray_menu(lab: Lab) -> QWidget:
    """The tray's menu as the app makes it, for a dark taskbar."""
    desktop = DesktopApp(Memory({}), None, MadeUpApps())
    desktop._style_tray_menu(light=False)
    menu = desktop.tray_menu
    style.size_qt_parts(menu)  # at the app's text size, as `main` has it
    menu.popup(QPoint(200, 200))
    lab.pump()
    lab.closing.append(menu.close)
    lab.closing.append(desktop.close)
    return menu


def tray_needs_source(lab: Lab) -> QWidget:
    """The icon and tooltip assigned to a dark Windows tray, at its largest
    native scale, inside the lab. Never show a real system-tray icon."""
    desktop = DesktopApp(
        Memory({"whole_system": False}), None, MadeUpApps(), light_taskbar=lambda: False
    )
    desktop.tray_icons = tray_icon
    desktop.tray = QSystemTrayIcon(desktop)
    desktop._show_tray_state()
    tile = QWidget()
    tile.setObjectName("Page")
    tile.setStyleSheet(style.stylesheet(style.current()))
    line = QHBoxLayout(tile)
    mark = QLabel(tile)
    mark.setPixmap(desktop.tray.icon().pixmap(max(TRAY_SIZES)))
    line.addWidget(mark)
    line.addWidget(QLabel(desktop.tray.toolTip(), tile))
    tile.show()
    lab.closing.append(desktop.close)
    return tile


def caption_tooltip(lab: Lab) -> QWidget:
    """A caption window's button's tooltip (Qt's: a window of its own, in
    Qt's tooltip font - the caption window has no stylesheet)."""
    shown = caption_window.window(lab, captions=3)
    caption_window.hovered(lab, shown)
    button = next(
        b for b in shown.findChildren(QAbstractButton) if b.toolTip() and b.isVisible()
    )
    QToolTip.showText(
        button.mapToGlobal(QPoint(0, button.height())), button.toolTip(), button
    )
    lab.pump()
    lab.closing.append(QToolTip.hideText)
    lab.closing.append(shown.close)
    return next(
        w
        for w in QApplication.topLevelWidgets()
        if w.metaObject().className() == "QTipLabel" and w.isVisible()
    )


def timing_tooltip(lab: Lab) -> QWidget:
    """A caption timing's tooltip in the bar's timing dropdown (593; the
    window's settings had them before): what Whole captions does (F22,
    249)."""
    shown = caption_window.window(lab, captions=3)
    caption_window.hovered(lab, shown)
    shown.toggle_timings()
    popover = shown.timings
    assert popover is not None
    button = next(
        b
        for b in popover.findChildren(QAbstractButton)
        if b.objectName() == "timings.timing.steady"
    )
    lab.pump()  # the popover's own events first: one of them hides a tooltip
    # at the screen's corner: the lab's work area is bigger than its screen,
    # and Qt shows no tooltip off every screen
    # Production sets the tooltip font when it sizes the tray. An isolated
    # timing photograph also needs that font, regardless of the preceding state.
    QToolTip.setFont(style.at_app_text_size(QApplication.font()))
    QToolTip.showText(QPoint(10, 10), button.toolTip())
    lab.closing.append(QToolTip.hideText)
    lab.closing.append(shown.close)
    return next(
        w
        for w in QApplication.topLevelWidgets()
        if w.metaObject().className() == "QTipLabel" and w.isVisible()
    )


def dialog(lab: Lab) -> QWidget:
    """The sign-out question, with no window under it: Qt's message box."""
    box = sign_out_question(None, unsent=True)
    box.show()
    lab.pump()
    return box


SAMPLE_LOG = "2026-11-25 16:15:00 INFO connection: session opened\n"


def _sample_report_parts() -> list[Part]:
    return problem_report_parts(
        SAMPLE_LOG,
        {"caption_mode": "steady"},
        {"app": {"version": "0.1.12"}},
        [],
        [],
        {},
        None,
    )


def problem_report(lab: Lab) -> QWidget:
    """The unified modal in Report a problem mode with ticked attachments."""
    form = ProblemReportDialog(
        _sample_report_parts(),
        "Polyglotic 0.1.12, windows-11 (10.0.26200)",
        mode="problem",
        with_session=True,
    )
    form.setStyleSheet(style.stylesheet(style.current()))
    form.text.setPlainText("Captions paused after I switched speakers.")
    form.show()
    lab.pump()
    lab.closing.append(form.close)
    return form


def suggestion(lab: Lab) -> QWidget:
    """The unified modal in Make a suggestion mode with optional reply and log."""
    form = ProblemReportDialog(
        _sample_report_parts(),
        "Polyglotic 0.1.12, windows-11 (10.0.26200)",
        mode="suggestion",
        with_session=False,
        read_suggestion_log=lambda: SAMPLE_LOG,
    )
    form.setStyleSheet(style.stylesheet(style.current()))
    form.text.setPlainText("Make saved words easier to practise.")
    form.show()
    lab.pump()
    lab.closing.append(form.close)
    return form


def feedback_counter(lab: Lab) -> QWidget:
    """A report at its limit, including the counter and cutting note."""
    form = FeedbackDialog("problem", lambda: None, "Polyglotic 0.1.12", False)
    form.text.setPlainText("x" * 2_001)
    form.show()
    lab.closing.append(form.close)
    return form


STATES = [
    State(f"ui_next.qt_{name}", run, gated=True)
    for name, run in (
        ("tray_menu", tray_menu),
        ("tray_needs_source", tray_needs_source),
        ("caption_tooltip", caption_tooltip),
        ("timing_tooltip", timing_tooltip),
        ("dialog", dialog),
        ("problem_report", problem_report),
        ("feedback_suggestion", suggestion),
        ("feedback_counter", feedback_counter),
    )
]
