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

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app
from tests.ui.test_main_wiring import (
    BROWSER,
    CHAT,
    ChangingAppList,
    FakePipeline,
    sources_with,
)
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM, SourceId
from polyglotic_desktop.main import (
    Sources,
    captured,
    follow_settings,
    wire_caption_windows,
)
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY
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
                STORED_KEY: {
                    "windows": {"system": mine, "Chat App": mine, "Web Browser": mine}
                },
            }
        )
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
