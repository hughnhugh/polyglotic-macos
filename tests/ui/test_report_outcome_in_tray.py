"""A report's outcome is said in the tray too, wherever the learner is
(polyglotic-hq 279): Home's banner alone was never seen by a tester in a
game or a call. Not when the banner is in front of them."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from tests.ui.fakes import Built, RecordingTray, make_app

THANKS = ("Polyglotic", "Thanks - we have your report.")


def test_each_outcome_home_shows_is_said_in_the_tray_too(qapp: QApplication) -> None:
    app = make_app()
    app.tray = tray = RecordingTray()
    home: list[str] = []
    app.home_notice.connect(home.append)
    app.show_feedback("sent", just_sent=True)
    app.show_feedback("waiting", just_sent=True)
    app.show_feedback("sign_in", just_sent=True)
    app.show_feedback("refused", just_sent=True)
    app.show_feedback("sent", just_sent=False)  # one kept for later, through now
    assert tray.messages == [
        THANKS,
        (
            "Polyglotic",
            "Your report is saved, and will be sent when the server can be reached.",
        ),
        ("Polyglotic", "Your report is saved, and will be sent once you're signed in."),
        (
            "Polyglotic",
            "The server couldn't take your report. Please write to us instead.",
        ),
        ("Polyglotic", "Thanks - your earlier report reached us."),
    ]
    assert home == [text for _, text in tray.messages]  # the same words
    app.show_feedback("waiting", just_sent=False)  # tried again, still waiting
    assert len(tray.messages) == 5 and len(home) == 5  # neither says it again
    tray.deleteLater()
    app.close()


def test_not_in_the_tray_while_homes_banner_is_in_front(qapp: QApplication) -> None:
    app = make_app()
    app.tray = tray = RecordingTray()
    home: list[str] = []
    app.home_notice.connect(home.append)
    app.banner_in_view = lambda: True
    app.show_feedback("sent", just_sent=True)
    assert home == [THANKS[1]] and tray.messages == []
    tray.deleteLater()
    app.close()


def test_without_a_tray_home_still_says_it(qapp: QApplication) -> None:
    app = make_app()
    assert app.tray is None  # offscreen: no tray
    home: list[str] = []
    app.home_notice.connect(home.append)
    app.show_feedback("sent", just_sent=True)
    assert home == [THANKS[1]]
    app.close()


def test_the_banner_is_in_front_only_on_home_in_the_window_in_front(
    qapp: QApplication,
) -> None:
    built = Built()
    hub, desktop = built.hub, built.desktop
    desktop.tray = tray = RecordingTray()
    assert not hub.banner_in_view()  # the window isn't open: in a game, say
    desktop.show_feedback("sent", just_sent=True)
    assert tray.messages == [THANKS]
    hub.show()
    qapp.processEvents()
    assert QApplication.activeWindow() is hub.window
    assert hub.banner_in_view()
    desktop.show_feedback("sent", just_sent=True)
    assert tray.messages == [THANKS]  # Home's banner says it, in front
    over = QDialog(hub.window)  # the report window, Send just pressed
    over.show()
    over.activateWindow()
    qapp.processEvents()
    assert QApplication.activeWindow() is over and hub.banner_in_view()
    over.close()
    over.deleteLater()
    elsewhere = QWidget(None, Qt.WindowType.Tool)  # a caption window, clicked
    elsewhere.show()
    elsewhere.activateWindow()
    qapp.processEvents()
    assert QApplication.activeWindow() is elsewhere and not hub.banner_in_view()
    elsewhere.close()
    elsewhere.deleteLater()
    hub.show()
    qapp.processEvents()
    assert hub.banner_in_view()
    hub.window.go_to("account")  # in front, but not on Home
    assert not hub.banner_in_view()
    desktop.show_feedback("sent", just_sent=True)
    assert tray.messages == [THANKS, THANKS]
    hub.window.go_to("home")
    hub.window.showMinimized()
    qapp.processEvents()
    assert not hub.banner_in_view()
    tray.deleteLater()
    built.close()
