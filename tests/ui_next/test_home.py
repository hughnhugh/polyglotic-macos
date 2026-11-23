"""Home and the new main window as widgets, offscreen (project 109's
sections 5, 7 and 10.5)."""

from dataclasses import asdict, replace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidgetAction

from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.releases.updates import UpdateNow
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import label
from polyglotic_desktop.ui_next.home import HomePage, StateCard
from polyglotic_desktop.ui_next.languages import not_offered_note
from polyglotic_desktop.ui_next.main_window import FLOOR, FRAME, MainWindow
from polyglotic_desktop.ui_next.os_words import hotkeys_here as keys
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui_next.views.home import (
    AddableApp,
    AppRow,
    AppStatus,
    Detail,
    HomeState,
    ListeningState,
    Picker,
    PickerView,
    Title,
    Tone,
    every_window_paused,
    state_line,
)
from polyglotic_desktop.ui_next.views.presets import AA_TEXT, contrast


class Commands:
    def __init__(self) -> None:
        self.asked: list[tuple[str, tuple[object, ...]]] = []

    def __getattr__(self, name: str) -> object:
        if name == "refresh":  # Home looks for apps whenever it shows
            return lambda: None
        return lambda *args: self.asked.append((name, args))


def _row(
    key: str, status: AppStatus = AppStatus.PLAYING, show_mic: bool = False
) -> AppRow:
    return AppRow(key, key.title(), "#4dd0e1", status, show_mic=show_mic)


def own_keys(letter: str) -> str:
    """The app's own hotkey with `letter`, as Qt reads it: Ctrl+Alt, and
    Ctrl+Alt+Shift on Linux (polyglotic-hq 570)."""
    modifiers = pc_mac_or_linux("Ctrl+Alt+", "Meta+Ctrl+", "Ctrl+Alt+Shift+")
    return modifiers + letter


def home(picker: Picker) -> tuple[HomePage, Commands]:
    commands = Commands()
    view = PickerView(picker, commands)  # type: ignore[arg-type]
    actions = [QAction(name) for name in ("Pause captions", "Lock", "Hide")]
    for action in actions[1:]:
        action.setCheckable(True)
    for action, key in zip(actions, "PLH", strict=True):  # as `DesktopApp`'s
        action.setShortcut(QKeySequence(own_keys(key)))
    pause, lock, hide = actions
    page = HomePage(
        view,
        pause,
        lock,
        hide,
        colours=("#4dd0e1", "#a5d66f"),
    )
    page._actions = actions  # type: ignore[attr-defined]  # kept alive
    return page, commands


def test_a_row_per_captioned_app_and_the_add_list(qapp: QApplication) -> None:
    page, commands = home(
        Picker(
            captioned=(_row("discord"), _row("player", AppStatus.NOT_OPEN)),
            available=(AddableApp("Spotify", "Spotify", True),),
        )
    )
    card = page.picker_card
    assert list(card.rows) == ["discord", "player"]
    assert card.rows["player"].status.text() == "not open - captioned when it opens"
    assert card.count.text() == "2 of 3"
    card.add_rows["Spotify"].add.click()
    card.rows["discord"].stop.click()
    card.rows["discord"].captions.click()
    card.rows["player"].transcript.click()
    card.rows["discord"].mic.click()
    assert [name for name, _ in commands.asked] == [
        "add",
        "remove",
        "show_window",
        "open_transcript",
        "set_show_mic",
    ]


def _shows_whole(found: QLabel) -> bool:
    """Whether a label shows all its text: on its line, or wrapped onto
    as many as it needs."""
    metrics = found.fontMetrics()
    if found.wordWrap():
        needed = metrics.boundingRect(
            QRect(0, 0, found.contentsRect().width(), 10_000),
            int(Qt.TextFlag.TextWordWrap),
            found.text(),
        )
        return needed.height() <= found.contentsRect().height()
    return metrics.horizontalAdvance(found.text()) <= found.contentsRect().width()


def test_a_paused_rows_line_shows_whole_in_a_narrow_window(
    qapp: QApplication,
) -> None:
    """A hidden window's row says it was paused and how to carry on, all of
    it, in the main window at its smallest (760 px, its page about 560):
    the line wraps rather than running under the row's buttons (polyglotic-
    hq 336: "einblenden, um fortzufahre" cut at the usual 1,000 px in
    German, and the English line at the smallest)."""
    paused = AppRow(
        "discord",
        "Discord",
        "#4dd0e1",
        AppStatus.PLAYING,
        sight=Sight.PAUSED,
        paused_after=15,
    )
    captioning = AppRow(
        "player", "Player", "#a5d66f", AppStatus.PLAYING, sight=Sight.CAPTIONING
    )
    page, _ = home(Picker(captioned=(paused, captioning)))
    page.resize(FLOOR[0] - 200, 700)
    page.show()
    qapp.processEvents()
    row = page.picker_card.rows["discord"]
    assert row.status.text() == "paused after 15 minutes hidden - show it to carry on"
    assert _shows_whole(row.status)
    assert _shows_whole(page.picker_card.rows["player"].status)
    assert row.status.geometry().bottom() <= row.contentsRect().bottom()
    page.close()
    page.deleteLater()


def test_a_double_click_on_plus_or_x_does_it_once(qapp: QApplication) -> None:
    """Adding or stopping an app moves the rows: a double-click's second
    click lands on the next app's + or x, within the double-click time -
    and is let go (polyglotic-hq 133: it captioned, or stopped, two)."""
    page, commands = home(
        Picker(
            captioned=(_row("discord"), _row("player")),
            available=(
                AddableApp("Spotify", "Spotify", True),
                AddableApp("Zoom", "Zoom", True),
            ),
        )
    )
    card = page.picker_card
    now = [100.0]
    card.add_once.clock = card.stop_once.clock = lambda: now[0]
    card.add_rows["Spotify"].add.click()
    card.add_rows["Zoom"].add.click()  # moved under the mouse
    card.rows["discord"].stop.click()
    card.rows["discord"].stop.click()  # the row now showing the next app
    assert commands.asked == [("add", ("Spotify",)), ("remove", ("discord",))]
    now[0] += 1.0  # a click of its own, later
    card.add_rows["Zoom"].add.click()
    card.rows["player"].stop.click()
    assert commands.asked[2:] == [("add", ("Zoom",)), ("remove", ("player",))]


def test_a_quick_click_on_another_apps_plus_still_adds_it(qapp: QApplication) -> None:
    """Only a double-click's second click is let go - one where the first
    was. A learner adding two apps quickly clicks the second app's + half a
    second after the first, elsewhere: it was ignored, silently
    (polyglotic-hq 141)."""
    page, commands = home(
        Picker(
            available=(
                AddableApp("Spotify", "Spotify", True),
                AddableApp("Zoom", "Zoom", True),
            ),
        )
    )
    card = page.picker_card
    now, at = [100.0], [QPoint(600, 400)]
    card.add_once.clock = lambda: now[0]
    card.add_once.where = lambda: at[0]
    card.add_rows["Spotify"].add.click()
    now[0] += 0.3
    at[0] = QPoint(600, 440)  # the next row down
    card.add_rows["Zoom"].add.click()
    assert commands.asked == [("add", ("Spotify",)), ("add", ("Zoom",))]


def test_two_quick_presses_by_keyboard_both_count(qapp: QApplication) -> None:
    """A keyboard has no double-click, and the mouse doesn't move between
    two presses: a second + pressed by the keyboard within the double-click
    time was dropped (141's limit, polyglotic-hq 158). A double-click by the
    mouse after them is still let go once."""
    page, commands = home(
        Picker(
            available=(
                AddableApp("Spotify", "Spotify", True),
                AddableApp("Zoom", "Zoom", True),
                AddableApp("Skype", "Skype", True),
            ),
        )
    )
    card = page.picker_card
    now, at = [100.0], [QPoint(600, 400)]  # the mouse never moves
    card.add_once.clock = lambda: now[0]
    card.add_once.where = lambda: at[0]
    QTest.keyClick(card.add_rows["Spotify"].add, Qt.Key.Key_Space)
    now[0] += 0.2
    QTest.keyClick(card.add_rows["Zoom"].add, Qt.Key.Key_Space)
    assert commands.asked == [("add", ("Spotify",)), ("add", ("Zoom",))]
    QTest.mouseClick(card.add_rows["Skype"].add, Qt.MouseButton.LeftButton)
    QTest.mouseClick(card.add_rows["Zoom"].add, Qt.MouseButton.LeftButton)
    assert commands.asked[2:] == [("add", ("Skype",))]  # a double-click: once


def test_an_addable_app_says_playing_or_quiet_in_the_same_place(
    qapp: QApplication,
) -> None:
    """The name is the name; the status is one dim word after it for both
    (not "(quiet)" in the name and "playing" beside it)."""
    page, _ = home(
        Picker(
            available=(
                AddableApp("Spotify", "Spotify", True),
                AddableApp("Steam", "Steam", False),
            )
        )
    )
    rows = page.picker_card.add_rows
    assert (rows["Spotify"].title.text(), rows["Spotify"].status.text()) == (
        "Spotify",
        "playing",
    )
    assert (rows["Steam"].title.text(), rows["Steam"].status.text()) == (
        "Steam",
        "quiet",
    )


@pytest.mark.parametrize("limit", [2, 3])
def test_at_the_limit_the_add_list_greys_with_the_reason(
    qapp: QApplication, limit: int
) -> None:
    page, commands = home(
        Picker(
            captioned=tuple(_row(str(index)) for index in range(limit)),
            available=(AddableApp("Spotify", "Spotify", True),),
            limit=limit,
        )
    )
    card = page.picker_card
    page.resize(900, 700)
    page.show()
    assert card.full.isVisible() and card.full.text().startswith(f"{limit} of {limit}")
    assert not card.add_rows["Spotify"].isEnabled()
    card.add_rows["Spotify"].add.click()
    assert commands.asked == []
    page.close()


def test_my_speechs_label_is_on_home(qapp: QApplication) -> None:
    you = AppRow("mic", "You", "#7c9cff", AppStatus.QUIET)
    page, commands = home(Picker(you=you))
    page.show()
    card = page.picker_card
    assert not card.you.isVisible() and not card.you_label.isVisible()
    page.picker_card.view.value = Picker(
        captioned=(_row("discord", show_mic=True),), you=you
    )
    card.refresh()
    assert card.you.isVisible() and card.you.name.text() == "You"
    assert card.speech.isVisible() and card.you_label.isVisible()
    # the row above says the label; the summary doesn't say it again
    assert card.speech.text() == (
        "My speech: shown in Discord - sent for your captions only while it's shown"
    )
    assert not card.you.chip.isVisible() and not card.you.stop.isVisible()
    # with an app captioned but the mic off: the row's microphone is there
    page.picker_card.view.value = Picker(captioned=(_row("discord"),), you=you)
    card.refresh()
    assert card.speech.text().startswith(
        "My speech: not shown in any window - turn it on"
    )
    # with nothing captioned there is no row to point at (135, 2026-11-07)
    page.picker_card.view.value = Picker(you=you)
    card.refresh()
    assert not card.speech.isVisible() and not card.you_label.isVisible()
    page.picker_card.view.value = Picker(
        captioned=(_row("discord", show_mic=True),), you=you
    )
    card.refresh()
    card.you.name.click()
    card.you.edit.setText("Me")
    card.you.edit.editingFinished.emit()
    assert commands.asked == [("rename", ("mic", "Me"))]
    page.close()


def test_rename_inline(qapp: QApplication) -> None:
    page, commands = home(
        Picker(captioned=(replace(_row("discord"), label="Arts & News"),))
    )
    row = page.picker_card.rows["discord"]
    page.show()
    assert row.name.text() == "Arts && News"
    row.name.click()
    assert row.edit.isVisible() and row.edit.text() == "Arts & News"
    row.edit.setText("Chat")
    row.edit.editingFinished.emit()
    assert commands.asked == [("rename", ("discord", "Chat"))]
    assert row.name.isVisible()
    page.close()


def test_everything_the_pc_plays_replaces_the_rows(qapp: QApplication) -> None:
    """A new learner's first launch (polyglotic-hq 484): its row, what it
    takes in - a call's voices too, said plainly - and one click on an app
    playing captions that app instead."""
    everything = pc_or_mac("Everything the PC plays", "Everything the Mac plays")
    page, commands = home(
        Picker(
            captioned=(AppRow("system", everything, "#fff", AppStatus.EVERYTHING),),
            available=(AddableApp("Zoom", "Zoom", True),),
            whole_system=True,
        )
    )
    card = page.picker_card
    page.show()
    assert card.count.text() == ""  # its row says it
    assert card.rows["system"].stop.isVisible()
    said = card.everything_said
    assert said.isVisible() and "a call's voices too" in said.text()
    assert "one app instead" in said.text()
    assert card.adding.isVisible()
    assert card.add_title.text() == "Caption one app instead"
    card.add_rows["Zoom"].add.click()
    assert commands.asked == [("add", ("Zoom",))]
    page.close()


def test_with_apps_alone_the_line_goes(qapp: QApplication) -> None:
    page, _ = home(Picker(captioned=(_row("discord"),)))
    card = page.picker_card
    page.show()
    assert not card.everything_said.isVisible()
    assert card.add_title.text() == "Add an app"
    page.close()


def test_where_apps_cant_be_alone_it_says_only_what_is_captioned(
    qapp: QApplication,
) -> None:
    page, _ = home(
        Picker(
            captioned=(AppRow("system", "x", "#fff", AppStatus.EVERYTHING),),
            whole_system=True,
            per_app=False,
        )
    )
    card = page.picker_card
    page.show()
    assert "a call's voices too" in card.everything_said.text()
    assert "instead" not in card.everything_said.text()
    assert card.adding.isHidden()
    page.close()


def test_nothing_captioned_says_so(qapp: QApplication) -> None:
    page, _ = home(Picker())
    page.show()
    assert page.picker_card.nothing.isVisible()
    assert page.picker_card.none_found.isVisible()
    page.show_state(HomeState(ListeningState.NOT_CONNECTED))
    assert page.state.title_label.text() == "Pick what to caption"
    # the card's yellow line says how; the state line doesn't say it again
    assert (
        page.state.detail.text()
        == "nothing is captioned yet · your speech not captioned"
    )
    assert page.state.pause.isHidden()
    assert page.state.sign_in.isHidden() and page.state.get_plus.isHidden()
    page.show_state(HomeState(ListeningState.NOT_CONNECTED, paused=True))
    assert not page.state.pause.isHidden()
    page.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert not page.state.pause.isHidden()
    page.show_state(HomeState(ListeningState.NOT_CONNECTED))
    assert page.state.pause.isHidden()
    page.show_state(HomeState(ListeningState.MOVED, chosen=True))
    assert page.moved.isVisible()
    page.close()
    page.deleteLater()


def test_signed_out_home_offers_sign_in_in_place_of_pause(
    qapp: QApplication,
) -> None:
    page, _ = home(Picker())
    wanted: list[bool] = []
    page.sign_in_wanted.connect(lambda: wanted.append(True))
    page.show_state(HomeState(ListeningState.SIGN_IN_NEEDED))
    state = page.state
    assert state.title_label.text() == "Not signed in"
    assert state.detail.text() == "sign in with your email to listen"
    assert not state.sign_in.isHidden() and state.pause.isHidden()
    state.sign_in.click()
    assert wanted == [True]
    assert page.picker_card.isEnabled()  # what's captioned: local
    page.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert state.sign_in.isHidden() and not state.pause.isHidden()


def test_reconnecting_counts_down_to_the_next_try(qapp: QApplication) -> None:
    """polyglotic-hq 133: Home stayed at "trying again in 22s" while the
    caption windows counted down to 13 s. It counts down now, in the
    windows' words, and stops ticking once the session isn't waiting."""
    now = [100.0]
    card = StateCard(QAction("Pause captions"), clock=lambda: now[0])
    card.show_state(HomeState(ListeningState.WAITING, retry_at=122.0, chosen=True))
    assert card.detail.text().startswith("trying again in 22 s")
    assert card._tick.isActive()
    now[0] = 109.0
    card._tick.timeout.emit()  # a second's tick (nine, here)
    assert card.detail.text().startswith("trying again in 13 s")
    card.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert "trying again" not in card.detail.text()
    assert not card._tick.isActive()


def test_every_window_paused_reads_paused_not_listening() -> None:
    """368 (336's Q2): every captioned app's window paused after being
    hidden - nothing sent - read "Listening". Paused, and how to go on,
    only while every one is; a bad connection state still comes first."""
    paused = AppRow("A", "A", "#fff", AppStatus.PLAYING, sight=Sight.PAUSED)
    rows = [replace(paused, paused_after=15), replace(paused, key="B", paused_after=30)]
    assert every_window_paused(rows) == 30
    assert every_window_paused([*rows, replace(paused, sight=Sight.CAPTIONING)]) is None
    assert every_window_paused([]) is None
    listening = HomeState(
        ListeningState.LISTENING, chosen=True, windows_paused_after=30
    )
    line = state_line(listening)
    assert (line.title, line.tone) == (Title.PAUSED, Tone.WAIT)
    assert line.details == ((Detail.WINDOWS_PAUSED, 30),)
    signed_out = replace(listening, connection=ListeningState.SIGN_IN_NEEDED)
    assert state_line(signed_out).title is Title.NOT_SIGNED_IN
    assert state_line(replace(listening, windows_paused_after=None)).title is (
        Title.LISTENING
    )


def test_a_full_server_says_so_on_homes_state_line(qapp: QApplication) -> None:
    """The existing backoff retries quietly while Home shows the busy message."""
    now = [100.0]
    card = StateCard(QAction("Pause captions"), clock=lambda: now[0])
    card.show_state(HomeState(ListeningState.SERVER_BUSY, retry_at=124.0, chosen=True))
    assert card.title_label.text() == "Polyglotic is busy — try again in a few minutes"
    assert card.detail.text() == ""
    assert not card._tick.isActive()
    assert (
        state_line(
            HomeState(ListeningState.SERVER_BUSY, retry_at=124.0, chosen=True), 100.0
        ).tone
        is Tone.WAIT
    )


def test_paused_home_says_how_to_resume(qapp: QApplication) -> None:
    page, _ = home(Picker())
    page.show_state(HomeState(ListeningState.LISTENING, chosen=True, paused=True))
    assert page.state.title_label.text() == "Paused"
    assert page.state.detail.text() == keys(
        pc_mac_or_linux(
            "resume with Ctrl+Alt+P, or from the tray",
            "resume with Ctrl+Alt+P, or from the menu bar",
            "resume with Ctrl+Alt+P, or here",  # no tray on GNOME (571)
        )
    )


def test_the_banner_in_the_windows_words(qapp: QApplication) -> None:
    """A brief notice for a while, else today's free minutes used."""
    page, _ = home(Picker())
    banner = page.state.notice
    assert banner.isHidden()
    page.state.set_minutes(20, 0)
    assert banner.text() == "Today's free minutes are used - more at midnight"
    page.state.set_notice("Busy time - live updates slowed; captions continue")
    assert banner.text().startswith("Busy time")
    page.state.set_notice(None)  # its two minutes over
    assert banner.text().startswith("Today's free minutes")
    page.state.set_minutes(20, 40)  # more again
    assert banner.isHidden()


def test_languages_and_timing_moved_to_settings(qapp: QApplication) -> None:
    """248's section 2.1 (261): Home keeps the state, the picker and the
    caption windows' row; Languages and Timing are Settings > Captions'."""
    from polyglotic_desktop.ui_next.panels import LanguagesPanel, TimingPanel

    page, _ = home(Picker())
    assert not page.findChildren(LanguagesPanel)
    assert not page.findChildren(TimingPanel)
    page.deleteLater()


def test_the_shell(qapp: QApplication) -> None:
    window = MainWindow(QAction("Quit"))
    page, _ = home(Picker())
    window.add_page("home", "Home", page)
    window.add_page("account", "Account", label("today's account page"), "top", 720)
    window.add_page("help", "Help", label("today's help"), "foot", 720)
    window.add_page("transcript", "Transcript", label("transcript"), None, 720)
    assert (window.minimumWidth(), window.minimumHeight()) == FLOOR  # 586
    window.go_to("home")
    window.nav_buttons["help"].click()
    assert window.current == "help"
    window.go_to("transcript")  # no button: none checked
    assert not any(b.isChecked() for b in window.nav_buttons.values())
    window.nav_buttons["help"].click()
    window.nav_buttons["help"].click()  # a second click keeps it checked
    assert window.current == "help" and window.nav_buttons["help"].isChecked()
    # no horizontal scrollbar at the minimum: the lab checks it, with
    # Windows' fonts (these tests have none)
    window.show()
    window.keep_in_tray = True
    window.close()
    assert not window.isVisible()


def test_the_machine_made_line_is_the_sidebars_quietest(qapp: QApplication) -> None:
    """The line under Settings and Help is faint and small, like the foot's
    buttons - not the brightest text in the sidebar (131)."""
    from PySide6.QtWidgets import QLabel

    window = MainWindow(QAction("Quit"))
    window.add_page("help", "Help", label("today's help"), "foot", 720)
    window.show()
    qapp.processEvents()
    line = window.findChild(QLabel, "machine_made")
    assert line is not None
    assert (
        line.font().pixelSize() == window.nav_buttons["help"].font().pixelSize() == 12
    )
    assert (
        line.palette().color(line.foregroundRole()).name() == window.theme["TEXT_FAINT"]
    )
    window.close()


def test_tab_walks_the_sidebar_top_to_bottom_then_the_page(qapp: QApplication) -> None:
    """Home, Words, Account, Settings, Help, Quit, then the page's controls
    - not Quit, the page, and the buttons last (131)."""
    from tests.ui_next.made_up import tab_stops

    window = MainWindow(QAction("Quit"))
    page, _ = home(Picker(available=(AddableApp("Spotify", "Spotify", True),)))
    window.add_page("home", "Home", page)
    window.add_page("words", "Words", label("words"), "top", 720)
    window.add_page("settings", "Settings", label("settings"), "foot", 720)
    window.add_page("account", "Account", label("account"), "top", 720)
    window.show()
    window.go_to("home")
    qapp.processEvents()
    sidebar = [
        window.nav_buttons[key] for key in ("home", "words", "account", "settings")
    ] + [window.quit_button]
    stops = tab_stops(window)
    assert stops[: len(sidebar)] == sidebar
    assert page.picker_card.add_rows["Spotify"].add in stops[len(sidebar) :]
    window.close()


def test_enter_on_a_sidebar_button_goes_there_as_space_does(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 133: Enter on a sidebar button did nothing (Space
    worked) - Qt's buttons take Enter only in a dialog. Enter and Return
    both go there now; Quit too."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    quit_action = QAction("Quit")
    quits: list[bool] = []
    quit_action.triggered.connect(lambda: quits.append(True))
    window = MainWindow(quit_action)
    window.add_page("home", "Home", label("home"))
    window.add_page("words", "Words", label("words"), "top", 720)
    window.add_page("help", "Help", label("help"), "foot", 720)
    window.show()
    window.go_to("home")
    QTest.keyClick(window.nav_buttons["words"], Qt.Key.Key_Return)
    assert window.current == "words"
    QTest.keyClick(window.nav_buttons["help"], Qt.Key.Key_Enter)  # the keypad's
    assert window.current == "help"
    QTest.keyClick(window.nav_buttons["home"], Qt.Key.Key_Space)  # as before
    assert window.current == "home"
    QTest.keyClick(window.quit_button, Qt.Key.Key_Return)
    assert quits == [True]
    window.close()


def test_the_theme_is_the_windows_alone(qapp: QApplication) -> None:
    before = qapp.styleSheet()
    window = MainWindow(QAction("Quit"))
    light = style.Theme({"BG": "#ffffff", "TEXT": "#111111"}, "Literata", dark=False)
    window.set_theme(light)
    assert style.current() == light
    assert "#ffffff" in window.sidebar.styleSheet() and qapp.styleSheet() == before
    style.use(style.Theme())


def test_the_main_window_fits_a_small_screen(qapp: QApplication) -> None:
    """Its first size within the screen's work area - a 1920 x 1080 laptop
    at 150 % has 1280 x 672 - title bar and all, never under its minimum;
    a big screen gets its usual size (polyglotic-hq 133: its foot, with
    Help and Quit, was under the taskbar)."""
    window = MainWindow(QAction("Quit"))
    laptop = QRect(0, 0, 1280, 672)
    window.fit_to(laptop)
    assert window.width() == 1000
    assert window.height() + FRAME <= laptop.height()
    assert window.y() >= 0 and window.x() + window.width() <= laptop.width()
    window.fit_to(QRect(0, 0, 800, 560))  # smaller than it can be
    assert (window.width(), window.height()) == FLOOR
    window.fit_to(QRect(1920, 0, 2560, 1400))  # a second, big screen
    assert (window.width(), window.height()) == (1000, 740)
    assert window.x() >= 1920
    window.close()


def test_update_needed_says_what_to_do(qapp: QApplication) -> None:
    page, _ = home(Picker())
    needed = HomeState(ListeningState.UPDATE_NEEDED, chosen=True, languages=("en",))
    page.show_state(needed)
    assert page.state.title_label.text() == "Update needed"
    assert page.state.detail.text().startswith("getting the update")
    page.show_state(
        HomeState(ListeningState.UPDATE_NEEDED, update_found=UpdateNow.NONE_YET)
    )
    assert "ask us for the newest installer" in page.state.detail.text()


def test_a_rows_language_chip_says_why_mongolian_and_kazakh_are_not_there(
    qapp: QApplication,
) -> None:
    """At the end of the chip's list, as the transcript rail's Translate
    into row says it (DECISIONS.md #40; polyglotic-hq 132's map, 144)."""
    page, _ = home(Picker(captioned=(_row("discord"),)))
    menu = page.picker_card.rows["discord"].chip.menu()
    names = [action.text() for action in menu.actions()]
    assert "Mongolian" not in names and "Kazakh" not in names
    (note,) = [a for a in menu.actions() if isinstance(a, QWidgetAction)]
    words = note.defaultWidget()
    assert isinstance(words, QLabel) and words.text() == not_offered_note()
    assert words.parent() is menu  # never a window of its own
    menu.aboutToShow.emit()  # wrapped to the items' width, not widening the list
    wide = menu.sizeHint().width()
    note.setVisible(False)
    assert menu.sizeHint().width() == wide
    assert words.height() >= 2 * words.fontMetrics().lineSpacing()


def test_the_dot_breathes_while_connecting_and_not_connected_has_a_next_step(
    qapp: QApplication,
) -> None:
    """151's W8 (176): the state's dot pulses - alpha only - while the app
    connects or reconnects, and stops after; "Not connected" says Help can
    check what's wrong."""
    from polyglotic_desktop.ui_next.controls import pulse_opacity

    card = StateCard(QAction("Pause captions"))
    card.show_state(HomeState(ListeningState.CONNECTING, chosen=True))
    assert card.dot.pulsing
    card.dot._breathe()
    assert 0.35 <= card.dot.opacity <= 1.0
    assert pulse_opacity(0.0) == 1.0 and abs(pulse_opacity(0.6) - 0.35) < 1e-9
    card.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert not card.dot.pulsing and card.dot.opacity == 1.0
    card.show_state(HomeState(ListeningState.NOT_CONNECTED, chosen=True))
    assert card.detail.text().startswith("Help can check what's wrong")
    assert not card.dot.pulsing


def test_stopped_has_a_next_step(qapp: QApplication) -> None:
    """polyglotic-hq 228 (224's finding 1): the red "Stopped" says what to
    do, in the words Help's check uses for it, and where to look if it
    keeps stopping."""
    card = StateCard(QAction("Pause captions"))
    card.show_state(HomeState(ListeningState.STOPPED, chosen=True))
    assert card.title_label.text() == "Stopped"
    assert card.detail.text() == pc_mac_or_linux(
        "quit from the tray and start Polyglotic again",
        "quit from the menu bar and start Polyglotic again",
        "quit Polyglotic and start it again",  # 571
    ) + (" - if it keeps stopping, Help can check what's wrong")


def test_homes_first_click_is_the_whole_row_and_a_caption_chip(
    qapp: QApplication,
) -> None:
    """151's W5 (176): a new learner's first click was a 24 px "+", under
    an orange line. The whole row is the target now, its button says
    Caption, and the first line is plain."""
    page, commands = home(Picker(available=(AddableApp("Spotify", "Spotify", True),)))
    card = page.picker_card
    row = card.add_rows["Spotify"]
    assert row.add.text() == "Caption"
    assert row.add.accessibleName() == "Caption Spotify"
    assert row.cursor().shape() is Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(row, Qt.MouseButton.LeftButton, pos=row.title.geometry().center())
    assert commands.asked == [("add", ("Spotify",))]
    QTest.mouseClick(row, Qt.MouseButton.RightButton, pos=row.title.geometry().center())
    assert len(commands.asked) == 1  # a left click only
    assert card.nothing.accessibleName() == "Not captioning yet"


def test_home_says_one_thing_about_captions_failing(qapp: QApplication) -> None:
    """184's QA (176): Home said "Listening" with a green dot under the
    yellow "Captions failing" banner; and with the speech model gone, the
    server's warm-up notice ("The speech model is starting", two minutes on
    Home) stood above the failing one every caption window showed. Failing
    comes first now, and the state isn't green while it lasts."""
    card = StateCard(QAction("Pause captions"))
    card.show_state(HomeState(ListeningState.LISTENING, chosen=True))
    assert card.dot.token == "SUCCESS"
    card.set_notice("The speech model is starting - the first captions may be slow.")
    card.set_failing(True)
    assert card.notice.text() == "Captions failing on the server - still trying"
    assert card.dot.token == "WARNING"
    assert card.title_label.text() == "Listening"  # connected: the banner says why
    card.set_failing(False)  # a caption came back
    assert card.dot.token == "SUCCESS"
    assert card.notice.text().startswith("The speech model is starting")


def test_failing_never_turns_a_worse_state_better() -> None:
    reconnecting = state_line(
        HomeState(ListeningState.WAITING, chosen=True, failing=True)
    )
    assert reconnecting.tone is Tone.WAIT
    signed_out = state_line(HomeState(ListeningState.SIGN_IN_NEEDED, failing=True))
    assert signed_out.tone is Tone.BAD


def test_home_names_only_the_hotkeys_that_work(qapp: QApplication) -> None:
    """polyglotic-hq 400 (found by 398): a hotkey another app has, or that was
    never registered - 398's preview build registers none - is cleared from
    its action (`DesktopApp.hotkeys_not_working`), and Home still said
    "Ctrl+Alt+L" on Lock all, "Ctrl+Alt+H" on Hide all and a hidden window,
    and "resume with Ctrl+Alt+P" - keys that did nothing."""
    page, _ = home(Picker(captioned=(_row("discord"),), hidden=True))
    page.show_state(HomeState(ListeningState.LISTENING, chosen=True, paused=True))
    row = page.picker_card.rows["discord"]
    assert page.lock.toolTip() == keys("Ctrl+Alt+L")
    assert page.hide_all.toolTip() == keys("Ctrl+Alt+H")
    assert row.captions.toolTip() == keys("Hidden - Ctrl+Alt+H")

    pause, lock, hide = page._actions  # type: ignore[attr-defined]
    for action in (pause, lock, hide):
        action.setShortcut(QKeySequence())  # as `hotkeys_not_working` does
    shown = [
        page.lock.toolTip(),
        page.hide_all.toolTip(),
        row.captions.toolTip(),
        page.state.detail.text(),
    ]
    assert not any(keys("Ctrl+Alt+L")[:-1] in text for text in shown), shown
    assert page.state.detail.text() == pc_mac_or_linux(
        "resume here or from the tray",
        "resume here or from the menu bar",
        "resume here",
    )
    assert row.captions.toolTip() == "Hidden - turn off Hide all to show it"

    lock.setShortcut(QKeySequence(own_keys("L")))  # one that works is named
    assert page.lock.toolTip() == keys("Ctrl+Alt+L") and not page.hide_all.toolTip()
    page.close()
    page.deleteLater()


def test_start_follows_the_last_app_to_begin_playing(qapp: QApplication) -> None:
    discord = AddableApp("Discord.exe", "Discord", True)
    player = AddableApp("player.exe", "Video Player", False)
    page, commands = home(Picker(available=(discord, player)))
    try:
        page.show()
        card = page.picker_card
        assert card.nothing.isVisible() and card.property("captionIdle")
        assert card.start.text() == "▶ Caption Discord"
        assert card.add_rows[discord.name].suggestion.isVisible()
        assert card.add_rows[discord.name].add.property("kind") == "primary"
        assert not card.add_rows[player.name].suggestion.isVisible()
        card.view.follow(Picker(available=(discord, replace(player, playing=True))))
        qapp.processEvents()  # the new rows have been laid out
        assert card.start.accessibleName() == "Caption Video Player"
        assert card.add_rows[player.name].suggestion.isVisible()
        card.start.click()
        assert commands.asked == [("start_captioning", (player.name,))]
        card.view.follow(Picker(captioned=(_row("discord"),)))
        assert card.nothing.isHidden() and card.start.isHidden()
        assert not card.property("captionIdle")
        assert (
            card.active.isVisible()
            and card.active.accessibleName() == "Captioning Discord"
        )
        card.rows["discord"].stop.click()
        assert commands.asked[-1] == ("remove", ("discord",))
        card.view.follow(Picker(captioned=(_row("discord"),), listening=False))
        assert card.active.isHidden()
    finally:
        page.close()
        page.deleteLater()


def test_quiet_sources_and_empty_list_offer_everything(qapp: QApplication) -> None:
    quiet = AddableApp("discord.exe", "Discord", False)
    for available in ((), (quiet,)):
        page, commands = home(Picker(available=available))
        try:
            card = page.picker_card
            assert card.start.accessibleName() == pc_or_mac(
                "Caption everything the PC plays", "Caption everything the Mac plays"
            )
            card.start.click()
            assert commands.asked == [("start_captioning", (None,))]
        finally:
            page.deleteLater()


def test_caption_badges_meet_text_contrast_in_every_window_theme(
    qapp: QApplication,
) -> None:
    page, _ = home(Picker())
    try:
        for look in theme.THEMES.values():
            for palette in (look.dark, look.light):
                page.setStyleSheet(style.stylesheet(style.Theme(asdict(palette))))
                card = page.picker_card
                for badge, background in (
                    (card.nothing, palette.WARNING),
                    (card.active, palette.SURFACE),
                ):
                    badge.ensurePolished()
                    ink = badge.palette().color(badge.foregroundRole()).name()
                    assert contrast(ink, background) >= AA_TEXT, (ink, background)
    finally:
        page.deleteLater()
