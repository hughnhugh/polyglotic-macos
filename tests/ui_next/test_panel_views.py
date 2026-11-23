"""The three shared panels' views, without Qt (polyglotic-hq project 109's
structure, section 4): one value each, the learner's changes handed on,
changes made elsewhere only shown."""

import itertools
import statistics

import pytest

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SEC,
    LIVE_MIN_AUDIO_SEC,
    CaptionMode,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY, CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LIVE_CHOICES,
    MAX_HINTS,
    WAIT_CHOICES,
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
    WindowLanguage,
    WindowLanguageView,
    hints_from,
    interval_choices,
)


def test_a_change_is_shown_to_every_panel_then_handed_on() -> None:
    handed: list[SessionLanguages] = []
    view = LanguagesView(SessionLanguages(), handed.append)
    told: list[str] = []
    view.subscribe(lambda: told.append("home"))
    view.subscribe(lambda: told.append("rail"))
    view.set_spoken("zh")
    assert told == ["home", "rail"]
    assert handed == [SessionLanguages(spoken="zh")]
    view.set_spoken("zh")  # no change: nobody told, nothing handed on
    assert len(told) == 2 and len(handed) == 1


def test_a_change_made_elsewhere_is_shown_but_not_handed_on() -> None:
    handed: list[Timing] = []
    view = TimingView(Timing(), handed.append)
    told: list[bool] = []
    view.subscribe(lambda: told.append(True))
    view.follow(Timing(CaptionMode.INSTANT, 2.0))
    assert told == [True] and handed == []
    view.follow(Timing(CaptionMode.INSTANT, 2.0))
    assert told == [True]


def test_a_panel_that_goes_stops_being_told() -> None:
    view = TimingView(Timing())
    told: list[bool] = []
    stop = view.subscribe(lambda: told.append(True))
    stop()
    stop()  # twice is harmless
    view.set_mode(CaptionMode.CALM)
    assert told == []


def test_a_second_language_per_language_in_use() -> None:
    view = LanguagesView(SessionLanguages(in_use=("en", "ja")))
    view.set_second("en", "zh")
    assert view.value.second_languages == {"en": "zh"}
    view.set_second("en", "en")  # into itself: none
    view.set_second("ja", None)
    assert view.value.second_languages == {}


def test_names_and_slang_as_typed() -> None:
    assert hints_from(" Caleb, HSK,,Caleb , Valorant ") == ("Caleb", "HSK", "Valorant")
    assert len(hints_from(",".join(f"w{n}" for n in range(150)))) == MAX_HINTS
    view = LanguagesView(SessionLanguages())
    view.set_hints("a, b")
    assert view.value.spelling_hints == ("a", "b")


def test_this_windows_language_and_my_speech() -> None:
    handed: list[WindowLanguage] = []
    view = WindowLanguageView(WindowLanguage("Discord"), handed.append)
    view.set_translate_into(ORIGINAL_ONLY)
    view.set_show_mic(True)
    assert view.value.original_only and view.value.show_mic
    assert handed[-1] == WindowLanguage("Discord", ORIGINAL_ONLY, True)


def test_an_interval_set_by_hand_is_offered_in_order() -> None:
    assert interval_choices(1.5) == list(LIVE_CHOICES)
    found = interval_choices(10.0)
    assert found[-1] == 10.0 and found == sorted(found)


def test_reset_puts_back_the_look() -> None:
    view = LookView(CaptionLook(opacity=0.3, font="Arial", preview=True))
    view.reset()
    assert view.value == CaptionLook(preview=True)  # Quick preview is the timing's


def test_look_changes() -> None:
    view = LookView(CaptionLook())
    view.set_opacity(1.7)
    assert view.value.opacity == 1.0
    view.set_colour("translation", "#7fe3ff")
    view.set_face("zh", "")
    view.set_word_links(WordLinks.HOVER)
    view.set_fade_after(None)
    value = view.value
    assert value.translation == "#7fe3ff" and value.faces == (("zh", ""),)
    assert value.word_links is WordLinks.HOVER and value.fade_after is None
    try:
        view.set_colour("opacity", "#000000")
    except ValueError:
        pass
    else:
        raise AssertionError("only a colour's name")


# -- what the Timing panel says, against what core's timing does (295) ----------------

APP = Source(SourceId("app"), SourceCategory.VIDEO)


def _live_updates(
    timing: Timing, seconds: float, finished: bool = False
) -> list[float]:
    """When core's timing asks for live updates in `seconds` of unbroken
    speech, at `timing`'s mode, interval and longest wait - with
    `finished`, for finished captions too: any text."""
    mode = timing.mode
    followed = CaptionTiming(
        mode.live_update_interval(timing.live_interval),
        rules=mode.rules,
        max_wait=timing.max_wait,
    )
    followed.add_source(APP)
    asked = []
    for frame in range(1, int(seconds / FRAME_SEC) + 1):
        end = frame * FRAME_SEC
        for decision in followed.frame(APP.id, end, True):
            if isinstance(decision, TranscriptionRequest) and (
                finished or decision.kind is SpeechKind.LIVE
            ):
                asked.append(end)
    return asked


def test_live_updates_come_as_often_as_the_panel_says() -> None:
    """Live updates' text updates at its interval, or at the longest wait
    for text when that's shorter (core.listening.timing): `live_every`,
    which the panel says when it isn't the interval chosen. Before 295
    "every 6s" with the default 3s wait updated every 3s, unsaid. Since
    296 unbroken speech is finished in pieces of 6s, each starting its
    live updates afresh: text comes at least that often - a live update or
    a finished piece - and the first update of a piece waits for a second
    of speech, as the panel says of a caption's."""
    for interval in LIVE_CHOICES:
        for wait in WAIT_CHOICES:
            timing = Timing(CaptionMode.INSTANT, interval, wait)
            asked = _live_updates(timing, 18.0, finished=True)
            gaps = [b - a for a, b in itertools.pairwise(asked)]
            assert gaps, (interval, wait)
            longest = max(timing.live_every, LIVE_MIN_AUDIO_SEC) + FRAME_SEC
            assert all(gap <= longest for gap in gaps), (interval, wait, gaps)
            assert statistics.median_high(gaps) == pytest.approx(
                timing.live_every, abs=FRAME_SEC
            ), (interval, wait, gaps)
    assert Timing(CaptionMode.INSTANT, 6.0, 3.0).live_every == 3.0
    assert Timing(CaptionMode.INSTANT, 1.5, 3.0).live_every == 1.5


def test_an_interval_offered_can_be_followed() -> None:
    assert max(LIVE_CHOICES) <= max(WAIT_CHOICES)
