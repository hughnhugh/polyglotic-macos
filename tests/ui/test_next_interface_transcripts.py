"""The transcript windows under the developer switch (`main.wire_transcripts`):
Open transcript and the tray open them, captions reach them, and their
commands are today's."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.main import (
    Panels,
    follow_transcripts,
    wire_caption_windows,
    wire_transcripts,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import LanguagesPanel, LookPanel, TimingPanel
from polyglotic_desktop.ui_next.transcripts import (
    QuitAnswer,
    QuitChoice,
    Transcripts,
    question,
)
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import TranscriptLength

APP_1 = SourceId("app-1")
KEY = "Web Browser"


@pytest.fixture
def switched(qapp: QApplication) -> Iterator[tuple[DesktopApp, Transcripts]]:
    store = MemorySettingsStore({"apps": [KEY], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    areas = [Rect(0, 0, 1920, 1040)]
    windows = CaptionWindows(store, MIC, lambda: areas)
    transcripts = Transcripts(windows, store, areas=lambda: areas)
    wire_caption_windows(windows, desktop, lambda: None)
    wire_transcripts(transcripts, desktop)
    windows.set_captioned([(KEY, APP_1)])
    yield desktop, transcripts
    transcripts.close()
    windows.close()
    desktop.close()


def test_open_transcript_opens_its_window(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    _, transcripts = switched
    transcripts.windows.windows[KEY].controls["transcript"].trigger()
    assert transcripts.shown[KEY].isVisible()


def test_the_tray_has_a_transcript_per_app_captioned(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    desktop, transcripts = switched
    menu = desktop.tray_menu
    entries = [a.menu() for a in menu.actions() if a.menu() is not None]
    # dictation's language is the tray's other menu (polyglotic-hq 283)
    assert entries == [desktop.dictation_language_menu, transcripts.menu]
    names = [a.text() for a in transcripts.menu.actions()]
    assert names == [KEY]
    transcripts.menu.actions()[0].trigger()
    assert transcripts.shown[KEY].isVisible()
    order = [a.text() for a in menu.actions()]
    assert order.index("Transcript") < order.index("Report a problem…")


def test_the_tray_and_a_transcript_take_the_apps_name_once_its_source_is_found(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    """At every start the windows open before capture finds the apps: the
    caption windows took the app's name then (141), but the tray's
    Transcript menu kept the file name ("vlc.exe") until a setting changed
    (polyglotic-hq 184)."""
    desktop, transcripts = switched
    transcripts.show(KEY)
    desktop.set_app_sources({APP_1: (KEY, "Browser")})
    assert [a.text() for a in transcripts.menu.actions()] == ["Browser"]
    shown = transcripts.shown[KEY]
    assert shown.label.name == "Browser"
    assert shown.windowTitle() == "Browser - Transcript"


def test_captions_reach_its_transcript_with_the_window_closed(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    desktop, transcripts = switched
    for update in finished_updates(3, source=APP_1):
        desktop.feed.apply(update)
    assert len(transcripts.transcripts[KEY].lines) == 3


def test_how_far_back_its_list_goes_is_the_settings(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    """Settings > App's Transcripts (polyglotic-hq 334): the newest 1,000
    lines until the learner chooses; chosen, every transcript lists that
    far back at once - its open window too."""
    desktop, transcripts = switched
    for update in finished_updates(1_030, source=APP_1):
        desktop.feed.apply(update)
    found = transcripts.transcripts[KEY]
    assert found.length is TranscriptLength.NEWEST
    assert len(found.lines) == 1_000
    transcripts.show(KEY)
    desktop.settings.update(transcript_length="session")
    assert transcripts.length is TranscriptLength.SESSION
    assert len(found.lines) == 1_030
    assert "1,030 lines" in transcripts.shown[KEY].foot.text()
    desktop.settings.update(transcript_length="newest")
    assert len(found.lines) == 1_000


class Asked:
    """Quit's question, answered as a test says: each time asked, what."""

    def __init__(self, *answers: QuitAnswer) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, int]] = []

    def __call__(self, name: str, lines: int) -> QuitAnswer:
        self.asked.append((name, lines))
        return self.answers.pop(0)


@pytest.fixture
def lecture(
    switched: tuple[DesktopApp, Transcripts],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[DesktopApp, Transcripts, list[int]]]:
    """Three hours kept, 400 lines heard, Quit's exit and the save dialog
    stood in for: the file is `tmp_path / "lecture.txt"`."""
    desktop, transcripts = switched
    desktop.settings.update(transcript_length="three_hours")
    for update in finished_updates(400, source=APP_1):
        desktop.feed.apply(update)
    exits: list[int] = []
    monkeypatch.setattr(
        type(QApplication.instance()), "exit", lambda *a: exits.append(0)
    )
    saved = str(tmp_path / "lecture.txt")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (saved, ""))
    yield desktop, transcripts, exits


def test_quit_asks_to_save_a_long_transcript_and_saves_it(
    lecture: tuple[DesktopApp, Transcripts, list[int]], tmp_path: Path
) -> None:
    """polyglotic-hq 334 (the user's "presave before exit"): Quit asks once;
    Save... writes the whole session where the learner chose, then quits."""
    desktop, transcripts, exits = lecture
    asked = transcripts.ask = Asked(QuitAnswer(QuitChoice.SAVE))
    desktop.quit.trigger()
    assert asked.asked == [(KEY, 400)]
    saved = (tmp_path / "lecture.txt").read_text(encoding="utf-8")
    assert saved.count("My computer froze again,") >= 80
    assert exits == [0]
    assert not transcripts.transcripts[KEY].needs_saving()


def test_cancel_or_a_save_not_made_keeps_the_app_running(
    lecture: tuple[DesktopApp, Transcripts, list[int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop, transcripts, exits = lecture
    transcripts.ask = Asked(QuitAnswer(QuitChoice.CANCEL))
    desktop.quit.trigger()
    assert exits == []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    transcripts.ask = Asked(QuitAnswer(QuitChoice.SAVE))  # then the dialog's Cancel
    desktop.quit.trigger()
    assert exits == []
    transcripts.ask = Asked(QuitAnswer(QuitChoice.QUIT))
    desktop.quit.trigger()
    assert exits == [0]


def test_dont_ask_again_is_kept_in_the_settings(
    lecture: tuple[DesktopApp, Transcripts, list[int]],
) -> None:
    desktop, transcripts, exits = lecture
    transcripts.ask = Asked(QuitAnswer(QuitChoice.QUIT, never_again=True))
    desktop.quit.trigger()
    assert exits == [0]
    assert desktop.settings.value.transcript_ask_at_quit is False
    assert transcripts.ask_at_quit is False


def test_quit_asks_nothing_when_not_needed(
    lecture: tuple[DesktopApp, Transcripts, list[int]], tmp_path: Path
) -> None:
    """Not with the newest 1,000 lines kept (the default: as before 334),
    nor after the whole transcript was saved, nor with asking turned off."""
    desktop, transcripts, _ = lecture
    asked = transcripts.ask = Asked()
    desktop.settings.update(transcript_length="newest")
    assert desktop.may_quit()
    transcripts._quit_answered = False  # a fresh Quit
    desktop.settings.update(transcript_length="session", transcript_ask_at_quit=False)
    assert desktop.may_quit()
    transcripts._quit_answered = False
    desktop.settings.update(transcript_ask_at_quit=True)
    transcripts.show(KEY)
    transcripts.shown[KEY].save_to(tmp_path / "saved.txt")
    assert desktop.may_quit()
    assert asked.asked == []


def test_a_transcript_whose_app_isn_t_captioned_now_is_asked_about_too(
    lecture: tuple[DesktopApp, Transcripts, list[int]], tmp_path: Path
) -> None:
    """Its caption window closed, its transcript stays for the session (and
    closing asked nothing): Quit still asks, by the app's name, and saves
    it - its window made for the save."""
    desktop, transcripts, exits = lecture
    transcripts.windows.set_captioned([])
    assert KEY not in transcripts.windows.windows and KEY not in transcripts.shown
    asked = transcripts.ask = Asked(QuitAnswer(QuitChoice.SAVE))
    desktop.quit.trigger()
    assert asked.asked == [(KEY, 400)]
    assert (tmp_path / "lecture.txt").exists() and exits == [0]


def test_quit_s_question_offers_save_quit_or_cancel(qapp: QApplication) -> None:
    box = question("Discord", 3_400)
    try:
        roles = {box.buttonRole(b): b.text() for b in box.buttons()}
        assert roles == {
            QMessageBox.ButtonRole.AcceptRole: "Save…",
            QMessageBox.ButtonRole.DestructiveRole: "Quit without saving",
            QMessageBox.ButtonRole.RejectRole: "Cancel",
        }
        assert box.defaultButton().text() == "Save…"
        assert "Discord" in box.text() and "3,400 lines" in box.informativeText()
        check = box.checkBox()
        assert check is not None and check.text() == "Don't ask again"
    finally:
        box.deleteLater()


def test_its_commands_are_today_s(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    desktop, transcripts = switched
    transcripts.show(KEY)
    shown = transcripts.shown[KEY]
    shown.timing_wanted.emit(CaptionMode.INSTANT.value)
    assert desktop.settings.value.caption_mode is CaptionMode.INSTANT
    transcripts.windows.set_timing(
        CaptionMode.INSTANT
    )  # as main's settings_changed does
    follow_transcripts(transcripts)
    assert shown.buttons["timing"].text() == "Instant ▾"
    desktop.pause.setChecked(True)
    assert shown.notice.text() == "Paused"
    desktop.pause.setChecked(False)
    desktop.set_connection(ConnectionState.WAITING, 5.0)
    assert shown.notice.text() == "Reconnecting"


def test_its_rail_shows_the_session_s_panels(
    switched: tuple[DesktopApp, Transcripts],
) -> None:
    desktop, transcripts = switched
    transcripts.panels = Panels(desktop.settings, transcripts.windows)
    transcripts.show(KEY)
    shown = transcripts.shown[KEY]
    shown.animate = False
    shown.toggle_rail()
    languages, timing, look = shown.rail.panels
    assert isinstance(languages, LanguagesPanel)
    assert isinstance(timing, TimingPanel) and isinstance(look, LookPanel)
    languages.spoken.choose("zh")  # a change in the rail: today's setting
    assert desktop.settings.value.spoken_language == "zh"
    follow_transcripts(transcripts)  # the window theme, today's
    assert shown.theme == transcripts.theme
