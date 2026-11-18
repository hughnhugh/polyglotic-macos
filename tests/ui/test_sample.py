"""Home's sample (polyglotic-hq 176): when nothing is playing, a short
FLEURS recording in the language learned, played and captioned by the app
like any app - so the first caption never waits on the learner finding
something to play. Fakes for the pipeline and the connection; the real
recording, delivered as fast as it's taken, for the capture."""

from collections.abc import Callable

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import MemorySettingsStore, tools_for
from tests.ui.test_main_start import Recording
from tests.ui.test_main_wiring import ChangingAppList, FakeCapture, FakePipeline

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.sources import SAMPLE, Source
from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE, CaptionTiming
from polyglotic_desktop.main import (
    Sources,
    follow_choice,
    follow_settings,
    new_interface,
    sample_language,
)
from polyglotic_desktop.platform.sample import SAMPLES, SampleCapture, sample_file
from polyglotic_desktop.platform.speech_detection import Audio
from polyglotic_desktop.ports.capture import AppList, PlayingApp, SourceCategory
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.views.home import AddableApp, Sample, sample_state

QUIET = AddableApp("Chat App", "Chat App", playing=False)
PLAYING = AddableApp("Video Player", "Video Player", playing=True)
NOTHING = AppSettings(whole_system=False)
"""Nothing chosen to caption: the sample is offered (a new learner captions
everything the PC plays since 484)."""


def test_a_sample_for_each_language_learned_with_its_credits() -> None:
    assert sample_file("zh") == SAMPLES / "zh.flac"
    assert sample_file("en") == SAMPLES / "en.flac"
    assert sample_file(None) is None  # not chosen yet
    assert sample_file("ja") is None
    credits = (SAMPLES / "CREDITS.md").read_text(encoding="utf-8")
    assert "FLEURS" in credits and "CC BY 4.0" in credits


def test_the_capture_delivers_the_recording_and_plays_it_aloud() -> None:
    played: list[int] = []
    stopped: list[bool] = []

    def play(audio: Audio, rate: int) -> Callable[[], None]:
        played.append(rate)
        return lambda: stopped.append(True)

    capture = SampleCapture(SAMPLES / "zh.flac", play, speed=None)
    assert 20 < capture.seconds < 40  # four sentences
    assert capture.capturing == "sample" and capture.error is None
    pieces: list[bytes] = []
    capture.start(lambda at, samples: pieces.append(samples))
    capture._replay.finished.wait(10)
    assert played == [VAD_SAMPLE_RATE] and capture.finished
    assert capture.capturing is None  # ended, as an app that closed
    heard = np.frombuffer(b"".join(pieces), dtype=np.float32)
    assert len(heard) == len(capture.audio) and np.abs(heard).max() > 0.3
    capture.stop()
    assert stopped == [True]


def test_offered_while_nothing_is_captioned_or_playing() -> None:
    assert sample_state(True, False, False, ()) is Sample.OFFERED
    assert sample_state(True, False, False, (QUIET,)) is Sample.OFFERED
    assert sample_state(True, False, False, (PLAYING,)) is Sample.NONE
    assert sample_state(True, False, True, ()) is Sample.NONE  # an app chosen
    assert sample_state(False, False, False, ()) is Sample.NONE  # none to play
    assert sample_state(True, True, False, (PLAYING,)) is Sample.PLAYING


def test_once_it_has_ended_it_says_the_next_step_until_an_app_is_chosen() -> None:
    """203's item 5, option B (208): offered again, with the next step,
    even once an app plays - until one is chosen."""
    assert sample_state(True, False, False, (), ended=True) is Sample.ENDED
    assert sample_state(True, False, False, (PLAYING,), ended=True) is Sample.ENDED
    assert sample_state(True, False, True, (), ended=True) is Sample.NONE
    assert sample_state(True, True, False, (), ended=True) is Sample.PLAYING


def sources_with_sample(pipeline: FakePipeline, apps: AppList) -> Sources:
    return Sources(
        pipeline,  # type: ignore[arg-type]
        apps,
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
        sample_capture=lambda: FakeCapture("sample"),
    )


def test_the_sample_is_a_source_of_its_own_until_an_app_is_chosen() -> None:
    pipeline = FakePipeline()
    apps = ChangingAppList(PlayingApp(30, "Chat App", True, SourceCategory.CALL))
    sources = sources_with_sample(pipeline, apps)
    sources.follow(NOTHING)  # the first run: nothing chosen
    assert pipeline.calls == []
    sources.play_sample(True)
    assert pipeline.calls == [f"sample:{SourceCategory.OTHER}:sample:False"]
    sources.play_sample(False)
    assert pipeline.calls[-1] == "remove:sample"
    sources.play_sample(True)  # again: from its start
    assert pipeline.calls[-1] == f"sample:{SourceCategory.OTHER}:sample:False"
    sources.follow(
        AppSettings(whole_system=False, apps=("Chat App",))
    )  # an app chosen ends it
    assert not sources.sample_on
    assert "remove:sample" in pipeline.calls
    assert pipeline.calls[-1].startswith("app-1:")


class Recorded(FakeCapture):
    """A sample's capture that ends when told, as the recording does."""

    def __init__(self) -> None:
        super().__init__("sample")
        self.over = False

    @property
    def capturing(self) -> str | None:
        return None if self.over else self.name


class Hearing(FakePipeline):
    """The pipeline, and whose speech is under way."""

    def __init__(self) -> None:
        super().__init__()
        self.heard: frozenset[str] = frozenset()

    def hearing(self) -> frozenset[str]:
        return self.heard


def test_played_to_its_end_it_ends_and_its_window_stays() -> None:
    """203's item 5: after its 28 s nothing said what was next and "Stop
    the sample" stayed. Now, once the recording is over and its last
    sentence finished, it ends: off, its window kept for lookups until it's
    closed, tried again, or an app is chosen (208, option B)."""
    pipeline = Hearing()
    captures: list[Recorded] = []

    def recorded() -> Recorded:
        captures.append(Recorded())
        return captures[-1]

    sources = Sources(
        pipeline,  # type: ignore[arg-type]
        ChangingAppList(PlayingApp(30, "Chat App", True, SourceCategory.CALL)),
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
        sample_capture=recorded,
    )
    sources.follow(NOTHING)
    sources.play_sample(True)
    assert not sources.sample_done  # playing
    pipeline.heard = frozenset({SAMPLE})
    captures[-1].over = True
    assert not sources.sample_done  # its last sentence still under way
    pipeline.heard = frozenset()
    assert sources.sample_done
    sources.end_sample()
    assert (sources.sample_on, sources.sample_kept, sources.sample_shown) == (
        False,
        True,
        True,
    )
    assert pipeline.calls[-1] == "remove:sample" and not sources.sample_done
    sources.play_sample(False)  # its window closed
    assert not sources.sample_shown
    sources.play_sample(True)  # tried again: from its start
    captures[-1].over = True
    sources.end_sample()
    sources.play_sample(True)
    assert sources.sample_on and not sources.sample_kept
    captures[-1].over = True
    sources.end_sample()
    sources.follow(
        AppSettings(whole_system=False, apps=("Chat App",))
    )  # an app chosen: it goes
    assert not sources.sample_shown


def test_its_window_stays_after_the_end(qapp: QApplication) -> None:
    store = MemorySettingsStore({"learning": "zh", "whole_system": False})
    desktop = DesktopApp(store, None, QuietApps())
    built = new_interface(desktop, store, None, per_app=True)
    sources = sources_with_sample(FakePipeline(), ChangingAppList())
    sources.follow(NOTHING)
    sources.sample_kept = True  # ended
    follow_settings(built.windows, desktop, sources)
    assert "sample" in built.windows.windows
    sources.sample_kept = False
    follow_settings(built.windows, desktop, sources)
    assert "sample" not in built.windows.windows
    built.close()
    desktop.close()


def test_each_sample_ends_with_its_last_sentence_finished() -> None:
    """`Sources.sample_done` waits for the speech detector to have none of
    the sample under way; each recording ends in silence, so that's true
    once it has played (the real detector, as fast as it takes it)."""
    from polyglotic_desktop.platform.speech_detection import (
        SpeechDetector,
        load_model,
    )
    from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline

    model = load_model()
    for language in ("zh", "en"):
        found = sample_file(language)
        assert found is not None
        pipeline = SpeechPipeline(
            lambda: SpeechDetector(model), CaptionTiming(None), on_ready=lambda: None
        )
        capture = SampleCapture(found, speed=None)
        try:
            pipeline.add_source(Source(SAMPLE, SourceCategory.OTHER), capture)
            assert capture._replay.finished.wait(30)
            assert SAMPLE not in pipeline.hearing(), language
            assert pipeline.take() is not None  # it was heard
        finally:
            pipeline.stop()


def test_signing_out_while_it_plays_stops_it_and_its_window_goes() -> None:
    """Polyglotic-hq 223: signed out mid-sample, with no app chosen, the
    plan didn't change - the sample isn't in it - so the sample went on
    playing aloud with nothing to caption it. It stops, as an app does."""
    pipeline = FakePipeline()
    sources = sources_with_sample(pipeline, ChangingAppList())
    sources.follow(NOTHING)
    sources.play_sample(True)
    assert pipeline.calls == [f"sample:{SourceCategory.OTHER}:sample:False"]
    sources.set_signed_in(False)
    assert pipeline.calls[-1] == "remove:sample"
    assert not sources.sample_on and not sources.sample_shown
    sources.set_signed_in(True)  # signed in again: it doesn't start by itself
    assert pipeline.calls[-1] == "remove:sample"


def test_nothing_is_played_while_signed_out_or_with_no_sample() -> None:
    pipeline = FakePipeline()
    sources = sources_with_sample(pipeline, ChangingAppList())
    sources.set_signed_in(False)
    sources.follow(NOTHING)
    sources.play_sample(True)
    assert pipeline.calls == []
    none = Sources(
        pipeline,  # type: ignore[arg-type]
        ChangingAppList(),
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
        sample_capture=lambda: None,  # none in the language learned
    )
    none.follow(NOTHING)
    none.play_sample(True)
    assert pipeline.calls == []


def test_listening_while_the_sample_is_on() -> None:
    """Nothing is chosen on a first run, so no listening session (#25) -
    but the sample is something to caption."""
    connection = Recording()
    follow_choice(
        connection,  # type: ignore[arg-type]
        NOTHING,
        connection.listen,
        sample=True,
    )
    assert connection.calls == ["listen", "start"]
    follow_choice(
        connection,  # type: ignore[arg-type]
        NOTHING,
        connection.listen,
        sample=False,
    )
    assert connection.calls[-1] == "stop listening"


class QuietApps:
    """An app with sound open, not playing: the first run's usual PC."""

    def playing_apps(self) -> list[PlayingApp]:
        return [PlayingApp(10, "Video Player", False, SourceCategory.VIDEO)]


def test_home_offers_it_and_turns_it_on_and_off(qapp: QApplication) -> None:
    store = MemorySettingsStore({"learning": "zh", "whole_system": False})
    desktop = DesktopApp(store, None, QuietApps())
    built = new_interface(desktop, store, None, per_app=True)
    hub, wanted = built.hub, []
    card = hub.home.picker_card
    assert card.sample.isHidden()  # not wired to listening: not offered

    def turn(on: bool) -> None:
        wanted.append(on)
        hub.sample_on = on

    hub.sample = turn
    hub.follow()
    assert not card.sample.isHidden()
    assert card.sample_button.text() == "Try it on a sample"
    card.sample_button.click()
    hub.follow()
    assert wanted == [True] and card.sample_button.text() == "Stop the sample"
    card.sample_button.click()
    assert wanted == [True, False]
    built.close()
    desktop.close()


def test_with_no_language_chosen_the_sample_is_the_running_dictionarys(
    qapp: QApplication,
) -> None:
    """The first run asks no language (polyglotic-hq 293): until one is
    chosen on Learning, the sample is in the language whose dictionary
    runs, so a learner with nothing chosen still has one to try (a first
    start captions everything the PC plays since 484)."""
    store = MemorySettingsStore({"whole_system": False})
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    assert sample_language(AppSettings(), tools) == "zh"
    assert sample_language(AppSettings(learning="en"), tools) == "en"  # chosen
    assert sample_language(AppSettings(), None) is None
    desktop = DesktopApp(store, tools, QuietApps())
    built = new_interface(desktop, store, tools, per_app=True)
    built.hub.sample = lambda on: None
    built.hub.follow()
    assert not built.hub.home.picker_card.sample.isHidden()
    built.close()
    desktop.close()


def test_home_follows_it_while_it_plays_and_says_whats_next_after(
    qapp: QApplication,
) -> None:
    """203's item 5: while it played, Home said "Pick what to caption /
    nothing is captioned yet" under a window that was captioning; after its
    end, nothing said what was next (208, option B)."""
    store = MemorySettingsStore({"learning": "zh", "whole_system": False})
    desktop = DesktopApp(store, None, QuietApps())
    built = new_interface(desktop, store, None, per_app=True)
    hub, wanted = built.hub, list[bool]()
    card = hub.home.picker_card
    hub.sample = wanted.append
    desktop.set_connection(ConnectionState.LISTENING)
    hub.sample_on = True
    hub.follow()
    assert hub.home.state.title_label.text() == "Listening"
    assert card.sample_next.isHidden()
    hub.sample_on, hub.sample_ended = False, True
    desktop.set_connection(ConnectionState.NOT_CONNECTED)
    hub.follow()
    assert card.sample_button.text() == "Try it on a sample"
    assert not card.sample_next.isHidden()
    assert card.sample_next.text() == "Pick an app to caption yours"
    card.sample_button.click()
    assert wanted == [True]  # from its start again
    built.close()
    desktop.close()


def test_once_it_has_ended_home_names_no_language_for_its_window(
    qapp: QApplication,
) -> None:
    """208's finding: after the sample ended, Home read "nothing is
    captioned yet · captions in English" - the window kept for lookups
    counted as a language in use. While it plays, it's captioning: its
    language is named (213)."""
    store = MemorySettingsStore({"learning": "zh", "whole_system": False})
    desktop = DesktopApp(store, None, QuietApps())
    built = new_interface(desktop, store, None, per_app=True)
    hub = built.hub
    sources = sources_with_sample(FakePipeline(), ChangingAppList())
    sources.follow(NOTHING)
    sources.play_sample(True)
    follow_settings(built.windows, desktop, sources)
    desktop.set_connection(ConnectionState.LISTENING)
    hub.sample_on = True
    hub.follow()
    assert "captions in" in hub.home.state.detail.text()  # it's captioning

    sources.end_sample()
    follow_settings(built.windows, desktop, sources)
    assert "sample" in built.windows.windows  # kept for lookups
    hub.sample_on, hub.sample_ended = False, sources.sample_kept
    desktop.set_connection(ConnectionState.NOT_CONNECTED)
    hub.follow()
    detail = hub.home.state.detail.text()
    assert detail.startswith("nothing is captioned yet")
    assert "captions in" not in detail
    assert "without translation" not in detail
    built.close()
    desktop.close()


@pytest.mark.windows_only  # Windows' PlaySound (0038)
def test_windows_plays_it_from_memory_and_stops_it() -> None:
    """PlaySound's own path, with silence: False only where there's no
    output device - the sample is captioned either way."""
    from polyglotic_desktop.platform.windows.sound import PlayAloud

    aloud = PlayAloud()
    aloud.stop()  # nothing playing: nothing to stop
    assert isinstance(aloud.play(np.zeros(1600, np.float32), VAD_SAMPLE_RATE), bool)
    aloud.stop()
    assert aloud._playing is None
