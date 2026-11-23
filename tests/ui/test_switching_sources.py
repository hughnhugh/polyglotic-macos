"""From everything the PC plays to apps one by one, and apps added and taken
off, with the windows joined and my speech shown (polyglotic-hq 290).

The user, 2026-11-11, on 0.1.3: "the per app translation is buggy, it seems
to be taking all of the system audio rather than per app" - after switching
from everything the PC plays, with two apps joined, adding and taking off an
app several times in minutes (the log: 1, 2, 1, 2, 0, 1, 2, 1). `main`'s
wiring with stand-in sources: the sources captured, the caption windows,
the joined window's columns, and what each shows when every source sends a
caption - including one still on its way for an app just taken off. Made-up
apps and captions only, offscreen.
"""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem
from tests.ui.fakes import MemorySettingsStore, make_app
from tests.ui.test_main_wiring import (
    BROWSER,
    CHAT,
    ChangingAppList,
    FakePipeline,
    sources_with,
)
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.captions import CaptionKind
from polyglotic_desktop.core.listening.sources import (
    MIC,
    SAMPLE,
    WHOLE_SYSTEM,
    SourceId,
)
from polyglotic_desktop.core.listening.timing import CaptionMode, WithdrawalReason
from polyglotic_desktop.main import (
    Panels,
    Sources,
    captured,
    follow_settings,
    wire_caption_windows,
)
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import Rect

CHAT_ID, BROWSER_ID = SourceId("app-1"), SourceId("app-2")


class Wired:
    """The app's sources and caption windows as `main` wires them."""

    def __init__(self) -> None:
        # as the user's settings were: every window showing my speech
        mine = {"show_mic": True}
        store = MemorySettingsStore(
            {
                "whole_system": True,
                "caption_mic": True,
                # whole captions: these are about sources, not the words' pace (526)
                "caption_mode_chosen": "steady",
                STORED_KEY: {
                    "windows": {"system": mine, "Chat App": mine, "Web Browser": mine}
                },
            }
        )
        self.store = store
        self.desktop: DesktopApp = make_app(store)
        self.windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
        wire_caption_windows(self.windows, self.desktop, lambda: None)
        self.pipeline = FakePipeline()
        self.sources: Sources = sources_with(
            self.pipeline, ChangingAppList(CHAT, BROWSER)
        )
        self.sent = 0

    def choose(self, **changes: object) -> None:
        """The learner's choice, followed as `main` follows it."""
        self.desktop.settings.update(**changes)
        value = self.desktop.settings.value
        self.sources.follow(captured(value))
        follow_settings(self.windows, self.desktop, self.sources)
        # the windows say whether my speech is wanted ("Caption my own
        # speech" follows); the hub follows the settings again
        self.sources.follow(captured(self.desktop.settings.value))
        QApplication.processEvents()

    def every_source_speaks(self) -> None:
        """A finished caption from each source there could be."""
        for source in (WHOLE_SYSTEM, CHAT_ID, BROWSER_ID, MIC):
            update = finished_updates(1, source=source, start=self.sent)[0]
            self.desktop.feed.apply(update)
            self.sent += 1
        QApplication.processEvents()

    def shown(self) -> dict[str, set[SourceId]]:
        """Each window's key -> the sources of the lines it shows now."""
        return {
            key: {c.source_id for c in w.view.captions_of(w.view.lines)}
            for key, w in self.windows.windows.items()
        }

    def columns(self) -> list[str]:
        joined = self.windows.joined_window
        return [w.key for w in joined.columns] if joined is not None else []

    def captured(self) -> set[str]:
        """The sources captured now (source ids), from the pipeline's calls."""
        running: set[str] = set()
        for call in self.pipeline.calls:
            if call.startswith("remove reference"):
                continue
            if call.startswith("remove:"):
                running.discard(call.split(":", 1)[1])
            elif not call.startswith("reference"):
                running.add(call.split(":", 1)[0])
        return running

    def close(self) -> None:
        self.windows.close()
        self.desktop.close()


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[Wired]:
    built = Wired()
    yield built
    built.close()


def test_video_uses_instant_and_explains_the_fallback_once(
    wired: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    notices: list[str] = []
    monkeypatch.setattr(wired.windows, "show_notice", notices.append)
    wired.desktop.hide_windows.setChecked(True)
    wired.choose(preset="video", caption_mode_chosen=CaptionMode.STEADY.value)
    assert notices == []
    wired.desktop.hide_windows.setChecked(False)
    QApplication.processEvents()
    assert wired.windows.windows
    assert all(
        window.timing is CaptionMode.INSTANT and window.deck is None
        for window in wired.windows.windows.values()
    )
    assert notices == ["Video uses Instant when Steady is selected."]
    wired.choose()
    wired.choose(preset="everyday")
    assert wired.windows.timing is CaptionMode.STEADY
    wired.choose(preset="video")
    assert len(notices) == 1
    restarted = Settings(MemorySettingsStore(wired.desktop.settings.value.to_stored()))
    assert restarted.value.video_timing_explained == {"words": "live"}
    assert restarted.value.caption_mode_chosen == CaptionMode.STEADY.value


def test_one_rebuild_per_window_for_a_settings_change(
    wired: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    wired.every_source_speaks()
    views = [window.view for window in wired.windows.windows.values()]
    counts: dict[CaptionLines, list[bool]] = {view: [] for view in views}
    original = CaptionLines._rebuild

    def rebuild(view: CaptionLines, everything: bool) -> bool:
        counts[view].append(everything)
        return original(view, everything)

    monkeypatch.setattr(CaptionLines, "_rebuild", rebuild)
    wired.choose(caption_mode_chosen="words", show_source=False, show_translation=False)
    assert all(calls == [True] for calls in counts.values())
    for window in wired.windows.windows.values():
        assert window.deck is not None and window.view.target is None
        assert all(line.model is not None for line in window.view.lines)
    for calls in counts.values():
        calls.clear()
    wired.choose()
    assert not any(counts.values())

    panels = Panels(wired.desktop.settings, wired.windows)
    wired.desktop.settings.changed.connect(
        lambda: follow_settings(wired.windows, wired.desktop, wired.sources)
    )
    panels.choose_preset("conversation")
    assert all(calls == [True] for calls in counts.values())


def test_switching_from_everything_to_apps_leaves_nothing_of_everything(
    wired: Wired,
) -> None:
    """Everything the PC plays, then one app: the whole system's window
    goes, its capture stops being a caption source (it stays only as the
    mic's bleed reference, never added as a source), and a caption from it
    still on its way shows nowhere."""
    wired.choose()  # as stored: everything the PC plays, and my speech
    assert set(wired.windows.windows) == {"system"}
    assert wired.captured() == {"system", "mic"}
    wired.every_source_speaks()
    assert wired.shown() == {"system": {WHOLE_SYSTEM, MIC}}

    wired.pipeline.calls.clear()
    wired.choose(whole_system=False, apps=("Chat App",))
    assert set(wired.windows.windows) == {"Chat App"}
    assert wired.pipeline.calls[:2] == ["remove:system", "remove:mic"]
    assert "reference:system" in wired.pipeline.calls  # the mic's reference only
    assert WHOLE_SYSTEM not in {s.id for s in wired.pipeline.sources[-2:]}
    wired.every_source_speaks()
    assert wired.shown() == {"Chat App": {CHAT_ID, MIC}}  # no `system` line


def test_apps_added_and_taken_off_joined_each_column_shows_its_own(
    wired: Wired,
) -> None:
    """The user's sequence (polyglotic-hq 290): from everything, apps one by
    one - 1, 2 (joined), 1, 2, 0, 1, 2, 1. At every step each window, and
    each column of the joined window, shows its own app's captions and my
    speech - never the whole system's, never another app's - and a caption
    from an app just taken off shows nowhere. My speech shows in every
    column ("Caption my own speech" turns it on in every window)."""
    wired.choose()
    wired.choose(whole_system=False, apps=("Chat App",))
    steps: list[tuple[str, ...]] = [
        ("Chat App", "Web Browser"),
        ("Chat App",),
        ("Chat App", "Web Browser"),
        (),
        ("Chat App",),
        ("Chat App", "Web Browser"),
        ("Chat App",),
    ]
    own = {"Chat App": CHAT_ID, "Web Browser": BROWSER_ID}
    for step, apps in enumerate(steps):
        wired.choose(apps=apps)
        if step == 0:
            wired.windows.join()  # the user joined the two
        assert list(wired.windows.windows) == list(apps), step
        assert wired.columns() == (list(apps) if len(apps) >= 2 else []), step
        wired.every_source_speaks()
        for key, sources in wired.shown().items():
            assert sources == {own[key], MIC}, (step, key, sources)
        assert wired.captured() == {own[a] for a in apps} | ({"mic"} if apps else set())
    # the browser taken off at the last step: its caption on its way after
    later = finished_updates(1, source=BROWSER_ID, start=999)[0]
    wired.desktop.feed.apply(later)
    assert wired.shown() == {"Chat App": {CHAT_ID, MIC}}


def test_a_window_kept_for_everything_doesnt_come_back_as_a_column(
    wired: Wired,
) -> None:
    """The settings keep the whole system's window's choices beside the
    apps' (`caption_windows.windows.system`): kept for when everything is
    chosen again, never a window or a column while apps are."""
    wired.choose()
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    wired.windows.join()
    wired.windows.save_now()
    assert "system" in wired.windows.stored.by_key  # kept
    wired.choose(apps=("Chat App",))
    wired.choose(apps=("Chat App", "Web Browser"))
    assert wired.columns() == ["Chat App", "Web Browser"]
    assert "system" not in wired.windows.windows
    wired.choose(whole_system=True)  # back to everything: its window, alone
    assert list(wired.windows.windows) == ["system"] and wired.columns() == []


def test_language_chip_choices_save_per_window_and_preset(wired: Wired) -> None:
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    settings = wired.desktop.settings
    chat = wired.windows.windows["Chat App"]
    browser = wired.windows.windows["Web Browser"]
    baseline = chat.choices
    other = browser.choices
    chat.toggle_languages()
    assert chat.languages is not None
    target = QListWidgetItem()
    target.setData(Qt.ItemDataRole.UserRole, "ja")
    chat.languages._language_chosen(target)
    chat.languages._spoken_chosen("zh")
    chat.set_second("fr")
    assert chat.choices.translate_into == "ja"
    assert chat.choices.spoken_language == "zh"
    assert browser.choices == other
    assert settings.value.second_language_of("ja") == "fr"
    assert use_presets.edits(settings.value) == ()

    chat.resize(chat.width() + 10, chat.height())  # writes the window's own choices
    settings.change(use_presets.chosen(settings.value, use_presets.CONVERSATION))
    wired.choose()
    assert chat.choices.translate_into == baseline.translate_into
    assert chat.choices.spoken_language == baseline.spoken_language
    assert settings.value.second_language_of("ja") != "fr"
    settings.change(use_presets.chosen(settings.value, use_presets.CUSTOM))
    wired.choose()
    assert chat.choices.translate_into == "ja" and chat.choices.spoken_language == "zh"
    restarted = Settings(MemorySettingsStore(settings.value.to_stored())).value
    assert restarted.preset_languages["Chat App"] == {
        "translate_into": "ja",
        "spoken_language": "zh",
    }
    assert restarted.second_language_of("ja") == "fr"


def test_timing_and_lyrics_bar_signals_save_without_saving_the_settings_draft(
    wired: Wired,
) -> None:
    wired.choose()
    settings = wired.desktop.settings
    window = wired.windows.windows["system"]
    settings.update(opacity=0.4)
    window.timing_wanted.emit(CaptionMode.CALM.value)
    window.lyrics_wanted.emit(True)
    wired.choose()
    assert window.timing is CaptionMode.CALM and wired.windows.lyrics
    assert use_presets.edits(settings.value) == ("opacity",)
    assert settings.value.preset_values[settings.value.preset]["lyrics"] is True
    assert (
        settings.value.preset_values[settings.value.preset]["caption_mode_chosen"]
        == "calm"
    )


def test_re_speaking_light_follows_active_sources(wired: Wired) -> None:
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    windows = wired.windows
    windows.set_respeaking(True, "insert", True)
    windows.set_respeaking_sources((CHAT_ID,))
    assert windows.windows["Chat App"].respeak_offered()
    assert not windows.windows["Web Browser"].respeak_offered()
    windows.set_respeaking_sources((BROWSER_ID, MIC))
    assert not windows.windows["Chat App"].respeak_offered()
    assert windows.windows["Web Browser"].respeak_offered()


def test_watched_window_takes_precedence_over_the_last_speaker(wired: Wired) -> None:
    windows = wired.windows
    windows.set_respeaking(True, "f8", True)
    wired.choose(whole_system=True)
    windows.set_respeaking_sources(wired.sources.captured_now())
    system = windows.windows["system"]
    outside = QPoint(-10000, -10000)
    assert windows.respeaking_window(outside) is system  # even before speech
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    windows.set_respeaking_sources(wired.sources.captured_now())
    windows.join()
    chat, browser = windows.windows["Chat App"], windows.windows["Web Browser"]
    wired.every_source_speaks()  # browser spoke after chat
    assert windows.respeaking_window(chat.mapToGlobal(chat.rect().center())) is chat
    QApplication.sendEvent(chat, QEvent(QEvent.Type.WindowActivate))
    assert windows.respeaking_window(outside) is chat
    assert (
        windows.respeaking_window(browser.mapToGlobal(browser.rect().center()))
        is browser
    )
    assert windows.show_respeaking_level(chat.source, "listening", 0.42) is chat
    chat.set_show_mic(False)
    browser.set_show_mic(False)
    assert chat.mic_button.level is None and browser.mic_button.level is None
    chat.set_show_mic(True)
    windows.read_mic_peak = lambda: 0.25
    windows._poll_mic_level()
    assert chat.mic_button.level is not None and chat.mic_button.level > 0.5
    assert browser.mic_button.level is None
    chat.set_show_mic(False)
    assert chat.mic_button.level is None


def test_whole_system_can_be_watched_while_the_sample_spoke_last(wired: Wired) -> None:
    wired.choose(whole_system=True)
    windows = wired.windows
    windows.set_captioned([("system", WHOLE_SYSTEM), ("sample", SAMPLE)])
    windows.set_respeaking_sources((WHOLE_SYSTEM, SAMPLE))
    windows.set_respeaking(True, "f8", True)
    windows.join()
    wired.desktop.feed.apply(finished_updates(1, source=SAMPLE)[0])
    assert wired.desktop.feed.history.captions[-1].source_id == SAMPLE
    system = windows.windows["system"]
    assert (
        windows.respeaking_window(system.mapToGlobal(system.rect().center())) is system
    )
    assert windows.respeaking_window(QPoint(-10000, -10000)) is system


def test_recognition_miss_explains_the_configured_hold_once(
    wired: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired.choose(whole_system=True)
    windows = wired.windows
    system = windows.windows["system"]
    notices: list[str] = []
    monkeypatch.setattr(
        system, "show_notice", lambda text, seconds: notices.append(text)
    )
    windows.set_respeaking(True, "f9", True)
    update = finished_updates(1, source=WHOLE_SYSTEM)[0]
    miss = replace(
        update, kind=CaptionKind.WITHDRAWN, clauses=(), reason=WithdrawalReason.EMPTY
    )
    for ignored in (
        update,
        replace(miss, respoken=True),
        replace(miss, reason=WithdrawalReason.MIC_BLEED),
    ):
        wired.desktop.feed.apply(ignored)
    assert not notices
    wired.desktop.feed.apply(miss)
    wired.desktop.feed.apply(miss)
    assert notices == ["Didn't catch that? Hold F9 and say it."]
    assert stored_windows(wired.store.load()).respeaking_hinted


def test_second_joined_column_miss_shows_the_shared_gesture_in_the_visible_notice(
    wired: Wired,
) -> None:
    wired.choose(whole_system=False, apps=("Chat App", "Web Browser"))
    windows = wired.windows
    windows.join()
    windows.set_respeaking(True, "right_ctrl", False)
    update = finished_updates(1, source=BROWSER_ID)[0]
    wired.desktop.feed.apply(replace(update, clauses=()))
    joined = windows.joined_window
    assert joined is not None and joined.notice.isVisible()
    assert joined.notice.text() == pc_or_mac(
        "Didn't catch that? Tap Right Ctrl, then hold it and say it.",
        "Didn't catch that? Tap Right ⌘, then hold it and say it.",
    )
