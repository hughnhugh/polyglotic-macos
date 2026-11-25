"""A listening session's summary (core.listening.summary), and its event.

Caption delay as seen, minutes, captions and the main source category;
rewrite and erasure rates from live updates against finished captions
(by character for Chinese, by word otherwise); dropped captions - late,
failed, or never answered; reconnects; and the tracking plan's
`listening_session_ended` properties, exactly the server's example's.
"""

from dataclasses import replace
from pathlib import Path

import pytest
import sudachidict_small
from tests.lexicon.sample import chinese_sample
from tests.test_protocol import example

from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.spoken_words import spoken_word_counter
from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordTime,
)
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.summary import (
    ListeningSessionEnded,
    PresetStep,
    SessionAction,
    SessionSummary,
    words,
)
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    CaptionMode,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory

VIDEO = Source(SourceId("app"), SourceCategory.VIDEO)
MIC = Source(SourceId("mic"), SourceCategory.MIC)
EN = Language("en")
JA = Language("ja")
ZH = Language("zh")
SUDACHI_DIC = Path(sudachidict_small.__file__).parent / "resources" / "system.dic"


def finished(
    caption: str,
    start: float,
    end: float,
    source: Source = VIDEO,
    replaces: tuple[str, ...] = (),
    voiced_seconds: float | None = None,
) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption),
        SpeechKind.FINISHED,
        source,
        start,
        end,
        replaces=tuple(CaptionId(r) for r in replaces),
        voiced_seconds=voiced_seconds,
    )


def update(
    caption: str,
    kind: CaptionKind,
    text: str = "",
    translation: str = "",
    replaces: tuple[str, ...] = (),
    token_spans: tuple[tuple[int, int], ...] | None = None,
) -> CaptionUpdate:
    if token_spans is None:
        token_spans = tuple(
            (match.start(), match.end())
            for match in __import__("re").finditer(r"\S+", text)
        )
    tokens = tuple(
        WordTime(span, float(n), float(n + 1)) for n, span in enumerate(token_spans)
    )
    clauses = (Clause(text, {EN: translation}, words=tokens),) if text else ()
    return CaptionUpdate(
        CaptionId(caption),
        SourceId("app"),
        kind,
        clauses,
        replaces=tuple(CaptionId(r) for r in replaces),
    )


def test_words_count_chinese_by_character() -> None:
    assert words("你好，今天天气") == {"你": 1, "好": 1, "今": 1, "天": 2, "气": 1}
    assert words("Hello, today's weather") == {
        "hello": 1,
        "today": 1,
        "s": 1,
        "weather": 1,
    }


def test_delay_minutes_captions_and_the_main_source() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    for n, (end, back, source) in enumerate(
        [
            (10.0, 11.2, VIDEO),
            (20.0, 21.0, VIDEO),
            (30.0, 32.0, MIC),
            (40.0, 41.1, VIDEO),
        ]
    ):
        caption = f"c{n}"
        summary.speech_sent(finished(caption, end - 6.0, end, source), at=end + 0.8)
        summary.caption_updated(update(caption, CaptionKind.FINISHED, "好"), at=back)
    ended = summary.ended(at=50.0)
    assert (ended.captions, ended.speech_minutes) == (4, 0.4)
    assert ended.source_category is SourceCategory.VIDEO
    assert (ended.delay_p50_ms, ended.delay_p95_ms) == (1100, 2000)
    assert (ended.dropped, ended.reconnects, ended.live_interval_seconds) == (0, 0, 1.5)
    assert ended.caption_mode == "live"


def test_speaking_pace_separates_them_and_you_and_excludes_gaps_between_captions() -> (
    None
):
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("them", 0.0, 2.0, voiced_seconds=1.5), at=2.0)
    summary.caption_updated(
        update("them", CaptionKind.FINISHED, "one two three four"), at=3.0
    )
    summary.speech_sent(
        finished("you", 100.0, 101.0, MIC, voiced_seconds=0.8), at=200.0
    )
    summary.caption_updated(
        update("you", CaptionKind.FINISHED, "one two three"), at=201.0
    )
    ended = summary.ended(at=500.0)
    assert (ended.pace_them_mean, ended.pace_them_peak) == (120, 120)
    assert (ended.pace_you_mean, ended.pace_you_peak) == (180, 180)
    assert ended.pace_them_seconds_61_120 == 2
    assert ended.pace_you_seconds_121_180 == 1


def test_english_caption_counts_twenty_words_over_eight_second_span_as_150_wpm() -> (
    None
):
    text = (
        "The quick brown fox jumps over the lazy dog while twenty birds "
        "fly quietly across the bright blue morning sky."
    )
    # Deliberately give mismatched server timings and shorter voiced time.
    bogus_spans = tuple((i, i + 1) for i in range(30))
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("en20", 10.0, 18.0, voiced_seconds=6.5), at=18.0)
    caption = replace(
        update("en20", CaptionKind.FINISHED, text, token_spans=bogus_spans),
        language=EN,
    )
    assert summary.caption_updated(caption, at=18.2) == 150
    assert summary.pace(18.2)[:2] == (150, 150)


def test_japanese_caption_counts_sudachi_words_not_per_character_timings() -> None:
    text = "私は昨日、寿司を食べました。"
    # Server word timings split per character (12 non-punctuation characters).
    char_spans = tuple((i, i + 1) for i, ch in enumerate(text) if ch not in "、。")
    assert len(char_spans) == 12
    japanese = JapaneseSplit(SUDACHI_DIC)
    counter = spoken_word_counter(lambda code: japanese if code == "ja" else None)
    summary = SessionSummary(live_interval=1.5, target=EN, count_words=counter)
    # 8 Sudachi mode C words (私/は/昨日/寿司/を/食べ/まし/た) over 4.0 s -> 120 wpm.
    summary.speech_sent(finished("ja", 0.0, 4.0, voiced_seconds=3.2), at=4.0)
    caption = replace(
        update("ja", CaptionKind.FINISHED, text, token_spans=char_spans),
        language=JA,
    )
    assert summary.caption_updated(caption, at=4.1) == 120
    assert summary.pace(4.1)[:2] == (120, 120)


def test_chinese_caption_counts_dictionary_words_not_per_character_timings() -> None:
    text = "这个人打游戏，画蛇添足！"
    # Server word timings split per Han character (10 characters).
    char_spans = tuple((i, i + 1) for i, ch in enumerate(text) if ch not in "，！")
    assert len(char_spans) == 10
    chinese = ChineseDictionary(chinese_sample())
    counter = spoken_word_counter(lambda code: chinese if code == "zh" else None)
    summary = SessionSummary(live_interval=1.5, target=EN, count_words=counter)
    # 4 dictionary words (这个/人/打游戏/画蛇添足) over 2.0 s -> 120 wpm.
    summary.speech_sent(finished("zh", 0.0, 2.0, voiced_seconds=1.6), at=2.0)
    caption = replace(
        update("zh", CaptionKind.FINISHED, text, token_spans=char_spans),
        language=ZH,
    )
    assert summary.caption_updated(caption, at=2.1) == 120
    assert summary.pace(2.1)[:2] == (120, 120)


def test_pace_counts_every_clause_with_word_counter_even_when_timings_exist() -> None:
    seen: list[tuple[str, str | None]] = []

    def count_words(text: str, language: str | None) -> int:
        seen.append((text, language))
        return len(text.split())

    summary = SessionSummary(live_interval=None, count_words=count_words)
    summary.speech_sent(finished("both", 0.0, 1.0, voiced_seconds=0.8), at=1.0)
    timed = update(
        "both", CaptionKind.FINISHED, "wait", token_spans=((0, 1), (1, 2), (2, 4))
    )
    mixed = replace(
        timed,
        language=EN,
        clauses=(*timed.clauses, Clause("hold on", {Language("es"): "espera"})),
    )
    assert summary.caption_updated(mixed, at=1.1) == 180
    assert seen == [("wait", EN), ("hold on", EN)]
    assert summary.pace(1.1)[:2] == (180, 180)


def test_pace_falls_back_to_voiced_seconds_only_when_speech_span_is_missing() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("missing-span", 5.0, 5.0, voiced_seconds=2.0), at=5.0)
    assert (
        summary.caption_updated(
            update("missing-span", CaptionKind.FINISHED, "one two three four"), 5.1
        )
        == 120
    )
    assert summary.pace(5.1)[:2] == (120, 120)


def test_caption_pace_needs_one_second_of_spoken_span() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("short", 0.0, 0.9, voiced_seconds=0.9), at=0.9)
    assert (
        summary.caption_updated(update("short", CaptionKind.LIVE, "one"), 1.0) is None
    )
    assert (
        summary.caption_updated(update("short", CaptionKind.FINISHED, "one"), 1.1)
        is None
    )
    summary.speech_sent(finished("long", 5.0, 6.0, voiced_seconds=0.7), at=6.0)
    assert (
        summary.caption_updated(update("long", CaptionKind.FINISHED, "one two"), 6.3)
        == 120
    )


def test_joined_caption_refreshes_live_pace_using_its_additional_speech() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("joined", 0.0, 2.0, voiced_seconds=1.0), at=2.0)
    assert (
        summary.caption_updated(update("joined", CaptionKind.FINISHED, "one"), 2.1)
        == 30
    )
    summary.speech_sent(finished("joined", 0.0, 5.0, voiced_seconds=2.0), at=5.0)
    joined = update("joined", CaptionKind.FINISHED, "one two three")
    assert summary.caption_updated(joined, 5.3) == 36
    assert summary.pace(10.0)[:2] == (36, 30)
    assert summary.pace(12.5)[:2] == (18, 30)
    assert summary.pace(15.0)[:2] == (0, 30)


def test_continuation_caption_pace_uses_the_spoken_span_of_both_pieces() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("first", 0.0, 2.0, voiced_seconds=1.0), at=2.0)
    summary.caption_updated(update("first", CaptionKind.FINISHED, "one"), 2.1)
    summary.speech_sent(finished("second", 2.0, 4.0, voiced_seconds=1.0), at=4.0)
    combined = replace(
        update("second", CaptionKind.FINISHED, "one two three"),
        continues=CaptionId("first"),
    )
    assert summary.caption_updated(combined, 4.1) == 45
    assert summary.pace(4.1)[:2] == (45, 60)


def test_a_content_free_pace_line_is_logged_each_minute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary = SessionSummary(live_interval=1.5, target=EN, started=0.0)
    summary.speech_sent(finished("first", 0.0, 1.0, voiced_seconds=1.0), at=1.0)
    summary.caption_updated(update("first", CaptionKind.FINISHED, "one"), at=1.1)
    summary.speech_sent(finished("next", 60.0, 61.0, voiced_seconds=1.0), at=61.0)
    with caplog.at_level("INFO"):
        summary.caption_updated(
            update("next", CaptionKind.FINISHED, "two three"), at=61.1
        )
    assert "pace: them" in caplog.text
    assert "drawn original" in caplog.text
    assert "one" not in caplog.text and "two" not in caplog.text


def test_the_caption_mode_is_steady_when_live_updates_are_off() -> None:
    """Without a mode given: with live updates off, only finished
    captions are shown - steady (059, Low 8). Whether anything was
    captioned or not."""
    assert SessionSummary(live_interval=None).ended(5.0).caption_mode == "steady"
    assert SessionSummary(live_interval=1.5).ended(5.0).caption_mode == "live"
    summary = SessionSummary(live_interval=None, target=EN)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.8)
    summary.caption_updated(update("c1", CaptionKind.FINISHED, "好"), at=4.5)
    ended = summary.ended(at=10.0)
    assert (ended.captions, ended.caption_mode) == (1, "steady")
    assert listening.session_ended(ended)["caption_mode"] == "steady"


@pytest.mark.parametrize("mode", list(CaptionMode))
def test_the_caption_mode_is_the_learners(mode: CaptionMode) -> None:
    """The tracking plan's `caption_mode` is the mode the session started
    in - `steady`, `preview` or `live` (project 064) - with or without
    anything captioned."""
    interval = mode.live_update_interval(2.0)
    # The v1 telemetry contract groups both instant-original modes under live.
    expected = "live" if mode is CaptionMode.SCROLLING else mode.value
    assert SessionSummary(interval, mode=mode).ended(5.0).caption_mode == expected
    summary = SessionSummary(interval, target=EN, mode=mode)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.6)
    summary.caption_updated(update("c1", CaptionKind.FINISHED, "好"), at=4.5)
    ended = summary.ended(at=10.0)
    assert (ended.captions, ended.caption_mode) == (1, expected)
    assert ended.live_interval_seconds == interval
    assert listening.session_ended(ended)["caption_mode"] == expected


def test_rewrites_count_words_shown_live_that_didnt_survive() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.8)
    summary.caption_updated(update("c1", CaptionKind.LIVE, "今天天", "Today day"), 1.0)
    summary.caption_updated(
        update("c1", CaptionKind.LIVE, "今天田七", "Today field"), 2.0
    )
    summary.caption_updated(
        update("c1", CaptionKind.FINISHED, "今天天气", "Today's weather"), 4.5
    )
    ended = summary.ended(at=5.0)
    # live: 今天天 (all kept), 今天田七 (田 and 七 not kept); finished has 4 characters
    assert ended.rewrite_ratio == 0.5
    # live: "today day" (day gone), "today field" (field gone); finished: today, s, weather
    assert ended.erasure_ratio == round(2 / 3, 3)


def test_a_join_takes_in_the_live_caption_it_replaces() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("a", 0.0, 2.0), at=2.8)
    summary.caption_updated(update("a", CaptionKind.FINISHED, "你好"), at=3.5)
    summary.caption_updated(update("b", CaptionKind.LIVE, "朋有"), at=4.5)
    summary.speech_sent(finished("a", 0.0, 5.0, replaces=("b",)), at=5.8)
    summary.caption_updated(
        update("a", CaptionKind.FINISHED, "你好朋友", replaces=("b",)), at=6.5
    )
    ended = summary.ended(at=10.0)
    assert ended.captions == 1 and ended.speech_minutes == round(5 / 60, 2)
    assert ended.rewrite_ratio == 0.25  # 有 of 4 characters


def test_withdrawn_captions_dont_count() -> None:
    summary = SessionSummary(live_interval=None)
    summary.speech_sent(finished("a", 0.0, 2.0), at=2.8)
    summary.caption_updated(update("a", CaptionKind.WITHDRAWN), at=3.0)
    ended = summary.ended(at=4.0)
    assert (ended.captions, ended.source_category, ended.speech_minutes) == (
        0,
        None,
        0.0,
    )


def test_a_session_with_nothing_captioned_is_summarised_too() -> None:
    """project 034: the tracking plan takes it (S2b) - its dropped captions
    and reconnects are what such a session has to say. Before, nothing was
    sent."""
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("lost", 0.0, 2.0), at=2.8)
    summary.reconnected()
    ended = summary.ended(at=20.0)
    assert (ended.captions, ended.dropped, ended.reconnects) == (0, 1, 1)
    assert ended.delay_p50_ms is None and ended.delay_p95_ms is None
    props = listening.session_ended(ended)
    assert props == {
        "speech_minutes": 0.0,
        "captions": 0,
        "source_category": "none",
        "caption_mode": "live",
        "rewrite_ratio": 0.0,
        "erasure_ratio": 0.0,
        "dropped": 1,
        "reconnects": 1,
        "live_interval_seconds": 1.5,
        "lookups": 0,
        "saves": 0,
        **NOTHING_DONE,
        **NOTHING_RECOVERED,
        **NO_PACE,
    }  # no delays: optional in the tracking plan since S2b; no capture: not told


def test_dropped_late_failed_or_never_answered() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("ok", 0.0, 1.0), at=1.8)
    summary.caption_updated(update("ok", CaptionKind.FINISHED, "ok"), at=2.5)
    summary.speech_sent(finished("late", 2.0, 3.0), at=3.8)
    summary.caption_updated(update("late", CaptionKind.FINISHED, "late"), at=14.0)
    summary.speech_sent(finished("failed", 4.0, 5.0), at=5.8)
    summary.failed(CaptionId("failed"))
    summary.speech_sent(finished("lost", 6.0, 7.0), at=7.8)
    summary.speech_sent(finished("waiting", 8.0, 9.0), at=29.0)
    summary.reconnected()
    ended = summary.ended(at=30.0)
    assert ended.dropped == 3  # late, failed, lost - not the one just sent
    assert ended.reconnects == 1 and ended.captions == 2


NOTHING_DONE = {
    "transcripts_opened": 0,
    "lines_flagged": 0,
    "original_only": False,
    "joined_window": False,
}
"""What the learner did (project 134): always in the summary, 0 or no if nothing."""

NOTHING_RECOVERED = {
    "capture_restarts": 0,
    "session_failures": 0,
    "unreadable_dropped": 0,
}
"""What the app recovered from by itself (566): always in the summary, 0 if nothing."""

NO_PACE = {
    "pace_them_mean": 0,
    "pace_them_peak": 0,
    "pace_you_mean": 0,
    "pace_you_peak": 0,
    **{
        f"pace_them_seconds_{band}": 0
        for band in ("1_60", "61_120", "121_180", "181_240", "241_plus")
    },
    **{
        f"pace_you_seconds_{band}": 0
        for band in ("1_60", "61_120", "121_180", "181_240", "241_plus")
    },
}


def test_the_event_has_exactly_the_tracking_plans_properties() -> None:
    summary = ListeningSessionEnded(
        speech_minutes=18.5,
        captions=212,
        source_category=SourceCategory.VIDEO,
        caption_mode="live",
        delay_p50_ms=1180,
        delay_p95_ms=1720,
        rewrite_ratio=0.21,
        erasure_ratio=0.14,
        dropped=1,
        reconnects=0,
        live_interval_seconds=1.5,
        lookups=6,
        saves=2,
    )
    (_first, expected) = example("usage")["events"]
    assert expected["name"] == listening.SESSION_ENDED
    # the copy from before the server's example counted lookups and saves
    # (polyglotic-server, 051) lacks them; the refreshed copy has these
    counts = {"lookups": 6, "saves": 2}
    assert (
        listening.session_ended(summary)
        == expected["props"] | counts | NOTHING_DONE | NOTHING_RECOVERED | NO_PACE
    )
    off = ListeningSessionEnded(**{**summary.__dict__, "live_interval_seconds": None})
    assert "live_interval_seconds" not in listening.session_ended(off)  # optional


def test_the_summary_counts_what_the_app_recovered_from() -> None:
    """polyglotic-hq 566 (from 557; decision 0266): a session that failed
    inside the app and tried again, captures that restarted and waiting
    rows dropped unread were only in the log, which is seen only when a
    tester sends a report. The summary counts them: the session's own
    failures here, the others as `ended` is told them."""
    summary = SessionSummary(1.5, EN)
    summary.session_failed()
    summary.session_failed()
    summary.reconnected()  # the server closing it: not a failure
    ended = summary.ended(20.0, capture_restarts=3, unreadable_dropped=1)
    recovered = (ended.session_failures, ended.capture_restarts)
    assert recovered + (ended.unreadable_dropped, ended.reconnects) == (2, 3, 1, 1)
    props = listening.session_ended(ended)
    assert {name: props[name] for name in NOTHING_RECOVERED} == {
        "capture_restarts": 3,
        "session_failures": 2,
        "unreadable_dropped": 1,
    }
    nothing = SessionSummary(None).ended(1.0)
    assert (nothing.capture_restarts, nothing.session_failures) == (0, 0)


def test_lookups_and_saves_are_counted_per_session() -> None:
    """polyglotic-hq DECISIONS.md #20: lookups shown and words saved during
    the session are counts in its summary - the only usage statistics
    about them. Nothing captioned still counts them."""
    summary = SessionSummary(1.5, EN)
    for _ in range(3):
        summary.looked_up()
    summary.saved()
    ended = summary.ended(20.0)
    assert (ended.lookups, ended.saves) == (3, 1)
    props = listening.session_ended(ended)
    assert (props["lookups"], props["saves"]) == (3, 1)
    assert SessionSummary(None).ended(1.0).lookups == 0


def test_the_summary_names_the_platform_and_nothing_more_about_the_pc() -> None:
    """polyglotic-server's tracking plan (051): `platform` - windows, macos,
    linux, android or ios - so the summaries of a later phone app can be
    told apart. Never the OS version."""
    ended = SessionSummary(1.5, EN).ended(5.0)
    assert "platform" not in listening.session_ended(ended)
    props = listening.session_ended(ended, platform="windows")
    assert props["platform"] == "windows"


def test_the_known_app_heard_most_is_named_and_no_other_app() -> None:
    """Known app names (polyglotic-hq DECISIONS.md #30, the user,
    2026-11-05): the summary names the well-known app most of the speech
    came from, by its public name - an app not on the list never, even when
    it was heard most; nothing known, no name."""
    discord = Source(SourceId("app-1"), SourceCategory.CALL, "discord")
    chrome = Source(SourceId("app-2"), SourceCategory.BROWSER, "google-chrome")
    private = Source(SourceId("app-3"), SourceCategory.GAME)  # not on the list
    summary = SessionSummary(live_interval=None)
    for n, (source, seconds) in enumerate(
        [(discord, 4.0), (chrome, 6.0), (private, 20.0), (discord, 3.0)]
    ):
        caption = f"c{n}"
        summary.speech_sent(finished(caption, 0.0, seconds, source), at=seconds)
        summary.caption_updated(update(caption, CaptionKind.FINISHED, "好"), at=seconds)
    ended = summary.ended(at=60.0)
    assert ended.source_category is SourceCategory.GAME  # the most speech
    assert ended.known_app == "discord"  # the known app heard most: 7s
    props = listening.session_ended(ended)
    assert props["known_app"] == "discord"
    assert "Game" not in str(props) and "app-3" not in str(props)

    only_private = SessionSummary(live_interval=None)
    only_private.speech_sent(finished("p", 0.0, 5.0, private), at=5.0)
    only_private.caption_updated(update("p", CaptionKind.FINISHED, "好"), at=5.5)
    unnamed = only_private.ended(at=60.0)
    assert unnamed.known_app is None
    assert "known_app" not in listening.session_ended(unnamed)  # left out


def test_a_known_apps_name_never_goes_with_its_speech() -> None:
    """The speech frame carries the source's id and category only (and its
    own languages, when it has them)."""
    discord = Source(SourceId("app-1"), SourceCategory.CALL, "discord")
    header = listening.speech_header(finished("c1", 0.0, 2.0, discord))
    assert "discord" not in header.model_dump_json()
    assert protocol.dump(header)["source"] == {"id": "app-1", "category": "call"}


def test_preset_steps_are_counted_with_the_changes_they_carried() -> None:
    """polyglotic-hq 587: saves, saves as new and discards, each with how
    many settings it carried - numbers only, and nothing at all from a
    session without one (a server from before drops a summary with them)."""
    quiet = listening.session_ended(SessionSummary(live_interval=None).ended(5.0))
    assert not any(name.startswith("preset_") for name in quiet)
    summary = SessionSummary(live_interval=None)
    summary.preset_step(PresetStep.SAVED, 3)
    summary.preset_step(PresetStep.SAVED, 1)
    summary.preset_step(PresetStep.DISCARDED, 2)
    sent = listening.session_ended(summary.ended(5.0))
    assert {k: v for k, v in sent.items() if k.startswith("preset_")} == {
        "preset_saves": 2,
        "preset_saves_as": 0,
        "preset_discards": 1,
        "preset_changes_saved": 4,
        "preset_changes_saved_as": 0,
        "preset_changes_discarded": 2,
    }


def test_songs_mode_is_counted_only_where_it_was_used() -> None:
    """polyglotic-hq 595: how long a music player was heard in songs mode,
    and how often the Lyrics switch was turned - numbers only, and left
    out of a session that had neither (a server without them in its plan
    drops only the sessions that used it)."""
    quiet = listening.session_ended(SessionSummary(None, started=0.0).ended(60.0))
    assert "lyrics_seconds" not in quiet and "lyrics_switches" not in quiet

    summary = SessionSummary(None, started=0.0)
    summary.songs(True, 10.0)
    summary.songs(False, 25.0)
    summary.did(SessionAction.LYRICS_SWITCHED)
    summary.songs(True, 40.0)  # on again until the session ends
    props = listening.session_ended(summary.ended(60.0))
    assert props["lyrics_seconds"] == 35.0 and props["lyrics_switches"] == 1

    switched = SessionSummary(None, started=0.0)  # on and off, never heard
    switched.did(SessionAction.LYRICS_SWITCHED)
    switched.did(SessionAction.LYRICS_SWITCHED)
    ended = switched.ended(60.0)
    assert ended.lyrics_seconds == 0.0 and ended.lyrics_switches == 2
