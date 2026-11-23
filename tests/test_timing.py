"""The live-update timing rules (core.listening.timing), driven frame by frame.

Ported from the proof of concept's test_vad_segmentation.py and the join
and long-speech split cases of test_discord_segmentation.py (Discord's own
rules dropped), on `master-polyglotic` / `ui-overhaul-learning`. Speech is
a made-up pattern of speaking and silent stretches; no audio, no model.
"""

import dataclasses
import itertools
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    BREATH_CUTS,
    FINAL_MAX_SEC,
    FRAGMENT_SEC,
    FRAME_SEC,
    JOIN_GAP_SEC,
    LIVE_SECTION_SEC,
    ONSET_LEAD_IN_SEC,
    SILENCE_HANGOVER_SEC,
    SLICE_PAD_SEC,
    BreathCut,
    CaptionId,
    CaptionMode,
    CaptionTiming,
    Decision,
    LiveSchedule,
    SpeechKind,
    TimingRules,
    TranscriptionRequest,
    WithdrawalReason,
    WithdrawCaption,
)
from polyglotic_desktop.ports.capture import SourceCategory

APP = Source(SourceId("source-1"), SourceCategory.VIDEO)
MIC = Source(SourceId("source-mic"), SourceCategory.MIC)
T0 = 1000.0

Pattern = Sequence[tuple[float, bool]]


def frames(pattern: Pattern, start: float = T0) -> list[tuple[float, bool]]:
    """(frame end, speech?) for each 32ms frame of a [(seconds, speaking?)]
    pattern; a frame is speech if its middle falls in a speaking stretch."""
    spans, t = [], start
    for seconds, speaking in pattern:
        spans.append((t, t + seconds, speaking))
        t += seconds
    out: list[tuple[float, bool]] = []
    for i in range(int((t - start) / FRAME_SEC)):
        end = start + (i + 1) * FRAME_SEC
        middle = end - FRAME_SEC / 2
        out.append((end, any(a <= middle < b and s for a, b, s in spans)))
    return out


def poc_rules(**options: Any) -> TimingRules:
    """Timing rules with no lead-in, as the proof of concept's (project 038
    added one): these tests' arithmetic is about their own rule."""
    return dataclasses.replace(TimingRules(lead_in=0.0), **options)


def make_timing(interval: float | None = None) -> CaptionTiming:
    ids = (CaptionId(f"c{i}") for i in itertools.count(1))
    return CaptionTiming(
        live_update_interval=interval,
        new_caption_id=lambda: next(ids),
        rules=poc_rules(),
    )


def run(
    timing: CaptionTiming,
    streams: dict[Source, Pattern],
    bleed: Callable[[float, float], bool] | None = None,
) -> list[Decision]:
    """Feeds every source's frames in time order; returns all decisions."""
    for source in streams:
        timing.add_source(source, bleed if source is MIC else None)
    merged = sorted(
        (end, source.id, speech)
        for source, pattern in streams.items()
        for end, speech in frames(pattern)
    )
    out: list[Decision] = []
    for end, source_id, speech in merged:
        out.extend(timing.frame(source_id, end, speech))
    return out


def requests(decisions: list[Decision], kind: SpeechKind) -> list[TranscriptionRequest]:
    return [
        d for d in decisions if isinstance(d, TranscriptionRequest) and d.kind is kind
    ]


def span(request: TranscriptionRequest) -> float:
    return request.speech_end - request.speech_start


# -- test_vad_segmentation.py ------------------------------------------------


def test_short_speech_one_finished_caption() -> None:
    out = run(make_timing(), {MIC: [(0.5, False), (3.0, True), (1.5, False)]})
    assert len(out) == 1
    finished = out[0]
    assert isinstance(finished, TranscriptionRequest)
    assert finished.kind is SpeechKind.FINISHED and finished.source == MIC
    assert finished.replaces == () and finished.section is None
    assert 2.95 <= span(finished) <= 3.05
    assert abs(finished.speech_end - (T0 + 3.5)) < 0.05


def test_long_speech_live_updates_then_whole_finished() -> None:
    out = run(
        make_timing(interval=1.5), {APP: [(0.5, False), (9.0, True), (1.5, False)]}
    )
    lives, finished = requests(out, SpeechKind.LIVE), requests(out, SpeechKind.FINISHED)
    assert len(finished) == 1 and 5 <= len(lives) <= 6
    assert {d.caption_id for d in out} == {finished[0].caption_id}
    by_section: dict[int | None, list[float]] = {}
    for live in lives:
        by_section.setdefault(live.section, []).append(round(span(live), 1))
    # Each section grows from where the last one's text stopped, and never
    # gets much past LIVE_SECTION_SEC - so no live update re-reads all 9s.
    assert len(by_section) == 2
    assert all(v == sorted(v) for v in by_section.values())
    assert max(max(v) for v in by_section.values()) <= LIVE_SECTION_SEC + 1.6
    assert span(finished[0]) >= 8.9


def test_first_live_update_waits_for_one_second_of_audio() -> None:
    out = run(
        make_timing(interval=0.5), {APP: [(0.5, False), (3.0, True), (1.5, False)]}
    )
    first = requests(out, SpeechKind.LIVE)[0]
    assert 1.0 <= span(first) < 1.0 + FRAME_SEC


def test_very_long_speech_split() -> None:
    out = run(make_timing(), {APP: [(0.5, False), (25.0, True), (1.5, False)]})
    finished = requests(out, SpeechKind.FINISHED)
    assert len(finished) == 2 and finished[0].caption_id != finished[1].caption_id
    assert span(finished[0]) >= 19.9 and span(finished[1]) >= 4.9
    assert finished[1].speech_start == finished[0].speech_end
    assert finished[1].replaces == ()  # not joined: the whole would pass FINAL_MAX_SEC


def test_back_to_back_speech_joined() -> None:
    out = run(
        make_timing(),
        {MIC: [(0.5, False), (2.0, True), (1.2, False), (2.0, True), (1.5, False)]},
    )
    finished = requests(out, SpeechKind.FINISHED)
    assert len(out) == 2 and finished[0].caption_id == finished[1].caption_id
    assert finished[1].speech_start == finished[0].speech_start
    assert span(finished[1]) >= 5.1


def test_long_pause_not_joined() -> None:
    out = run(
        make_timing(),
        {MIC: [(0.5, False), (2.0, True), (3.0, False), (2.0, True), (1.5, False)]},
    )
    finished = requests(out, SpeechKind.FINISHED)
    assert len(out) == 2 and finished[0].caption_id != finished[1].caption_id


def test_blip_ignored() -> None:
    assert run(make_timing(), {MIC: [(0.5, False), (0.3, True), (1.5, False)]}) == []


def test_paused_sends_nothing() -> None:
    timing = make_timing(interval=1.5)
    timing.paused = True
    assert run(timing, {MIC: [(0.5, False), (9.0, True), (1.5, False)]}) == []


def test_resumed_mid_speech_picks_up_where_the_speech_started() -> None:
    timing = make_timing(interval=1.5)
    timing.add_source(APP)
    out: list[Decision] = []
    for end, speech in frames([(0.5, False), (6.0, True), (1.5, False)]):
        timing.paused = end < T0 + 3.0
        out.extend(timing.frame(APP.id, end, speech))
    finished = requests(out, SpeechKind.FINISHED)
    assert requests(out, SpeechKind.LIVE) and len(finished) == 1
    assert span(finished[0]) >= 5.9


def test_a_source_paused_on_its_own_sends_nothing_and_the_others_carry_on() -> None:
    """A caption window hidden too long (polyglotic-hq 335): its app's
    speech sends nothing - live or finished - and isn't heard; the mic's is
    sent as before."""
    timing = make_timing(interval=1.5)
    timing.paused_sources = frozenset({APP.id})
    speech = [(0.5, False), (9.0, True), (1.5, False)]
    timing.add_source(APP)
    timing.add_source(MIC)
    out: list[Decision] = []
    heard: set[SourceId] = set()
    for end, speaking in frames(speech):
        out.extend(timing.frame(APP.id, end, speaking))
        out.extend(timing.frame(MIC.id, end, speaking))
        heard |= timing.hearing()
    assert out and all(
        isinstance(d, TranscriptionRequest) and d.source == MIC for d in out
    )
    assert heard == {MIC.id}


def test_a_source_resumed_mid_speech_picks_up_where_the_speech_started() -> None:
    timing = make_timing(interval=1.5)
    timing.add_source(APP)
    out: list[Decision] = []
    for end, speech in frames([(0.5, False), (6.0, True), (1.5, False)]):
        timing.paused_sources = frozenset({APP.id}) if end < T0 + 3.0 else frozenset()
        out.extend(timing.frame(APP.id, end, speech))
    finished = requests(out, SpeechKind.FINISHED)
    assert len(finished) == 1 and span(finished[0]) >= 5.9


# -- the join and long-speech split cases of test_discord_segmentation.py --------


def test_three_back_to_back_stretches_joined() -> None:
    pattern = [
        (0.5, False),
        (2.0, True),
        (1.0, False),
        (2.0, True),
        (1.0, False),
        (1.5, True),
        (1.5, False),
    ]
    finished = requests(run(make_timing(), {APP: pattern}), SpeechKind.FINISHED)
    assert len(finished) == 3 and len({f.caption_id for f in finished}) == 1
    assert span(finished[2]) >= 7.4


def test_no_join_across_another_sources_caption_or_a_long_gap() -> None:
    app = [
        (0.5, False),
        (1.5, True),
        (1.2, False),
        (1.3, True),
        (2.5, False),
        (1.5, True),
        (1.5, False),
    ]
    mic = [(2.2, False), (0.8, True), (5.0, False)]
    out = run(make_timing(), {APP: app, MIC: mic})
    finished = requests(out, SpeechKind.FINISHED)
    assert [f.source for f in finished] == [APP, MIC, APP, APP]
    # The mic's caption came between the app's first two: no join.
    assert len({f.caption_id for f in finished}) == 4
    assert span(finished[2]) < 1.4
    # 2.5s after the app's last caption: no join either.
    assert span(finished[3]) < 1.6


def test_joined_caption_replaces_the_live_one() -> None:
    # 1.2s first: too short for a live update; then 7.5s with live updates.
    out = run(
        make_timing(interval=1.5),
        {APP: [(2.0, False), (1.2, True), (1.0, False), (7.5, True), (1.0, False)]},
    )
    finished = requests(out, SpeechKind.FINISHED)
    live_ids = {live.caption_id for live in requests(out, SpeechKind.LIVE)}
    assert len(finished) == 2 and len(live_ids) == 1
    joined = finished[1]
    assert joined.caption_id == finished[0].caption_id
    assert joined.replaces == tuple(live_ids)
    assert span(joined) >= 9.6


def test_live_caption_split_then_carries_on_in_a_new_one() -> None:
    out = run(
        make_timing(interval=1.5), {APP: [(0.5, False), (23.0, True), (1.0, False)]}
    )
    finished = requests(out, SpeechKind.FINISHED)
    first = finished[0]
    assert first.speech_end - first.speech_start >= FINAL_MAX_SEC - 0.01
    after = [
        live
        for live in requests(out, SpeechKind.LIVE)
        if live.speech_start >= first.speech_end
    ]
    assert after and all(live.caption_id != first.caption_id for live in after)
    assert after[0].section == 0 and 1.45 <= span(after[0]) <= 1.55
    assert finished[1].caption_id == after[0].caption_id and finished[1].replaces == ()


def test_live_updates_off_only_finished() -> None:
    out = run(
        make_timing(interval=None), {APP: [(0.5, False), (8.0, True), (1.5, False)]}
    )
    assert [d.kind for d in requests(out, SpeechKind.FINISHED)] == [SpeechKind.FINISHED]
    assert len(out) == 1


# -- mic bleed: the timing side (the audio check itself is platform's) -----------


def test_bleed_at_the_pause_withdraws_the_live_caption() -> None:
    out = run(
        make_timing(interval=1.5),
        {MIC: [(0.5, False), (4.0, True), (1.5, False)]},
        bleed=lambda start, end: (
            end - start > 3.0
        ),  # only the whole stretch looks like bleed
    )
    lives = requests(out, SpeechKind.LIVE)
    assert lives and out[-1] == WithdrawCaption(
        lives[0].caption_id, MIC, WithdrawalReason.MIC_BLEED
    )
    assert requests(out, SpeechKind.FINISHED) == []


def test_bleed_without_a_live_caption_sends_nothing() -> None:
    out = run(
        make_timing(),
        {MIC: [(0.5, False), (3.0, True), (1.5, False)]},
        bleed=lambda s, e: True,
    )
    assert out == []


def test_bleed_skips_live_updates_but_keeps_the_pace() -> None:
    checked: list[tuple[float, float]] = []

    def bleed(start: float, end: float) -> bool:
        checked.append((start, end))
        return True

    out = run(
        make_timing(interval=1.5),
        {MIC: [(0.5, False), (5.0, True), (1.5, False)]},
        bleed=bleed,
    )
    assert out == []
    live_checks = checked[:-1]  # the last check is the pause's
    assert len(live_checks) == 3
    assert all(1.45 < b[1] - a[1] < 1.55 for a, b in itertools.pairwise(live_checks))


def test_bleed_is_only_checked_for_the_source_given_one() -> None:
    out = run(
        make_timing(),
        {APP: [(0.5, False), (3.0, True), (1.5, False)]},
        bleed=lambda s, e: True,
    )
    assert len(requests(out, SpeechKind.FINISHED)) == 1


@pytest.mark.parametrize("interval", [0.5, 1.5, 3.0])
def test_live_updates_follow_the_interval(interval: float) -> None:
    out = run(
        make_timing(interval=interval), {APP: [(0.5, False), (5.5, True), (1.5, False)]}
    )
    ends = [live.speech_end for live in requests(out, SpeechKind.LIVE)]
    assert all(b - a >= interval - 1e-9 for a, b in itertools.pairwise(ends))
    assert all(b - a < interval + FRAME_SEC for a, b in itertools.pairwise(ends))


# -- the pace hint (protocol.md, `pace`) ------------------------------------------


@pytest.mark.parametrize(
    ("chosen", "hint", "followed"),
    [(1.5, None, 1.5), (1.5, 3.0, 3.0), (5.0, 3.0, 5.0), (None, 3.0, None)],
)
def test_the_pace_hint_only_stretches_the_interval(
    chosen: float | None, hint: float | None, followed: float | None
) -> None:
    timing = make_timing(interval=chosen)
    timing.pace_hint = hint
    assert timing.paced_interval == followed


def test_live_updates_slow_to_the_pace_hint_and_finished_is_not_held_back() -> None:
    pattern: Pattern = [(0.5, False), (7.5, True), (1.5, False)]
    plain = run(make_timing(interval=1.5), {APP: pattern})
    paced_timing = make_timing(interval=1.5)
    paced_timing.pace_hint = 3.0
    paced = run(paced_timing, {APP: pattern})
    ends = [live.speech_end for live in requests(paced, SpeechKind.LIVE)]
    assert len(ends) < len(requests(plain, SpeechKind.LIVE))
    assert all(
        3.0 - 1e-9 <= b - a < 3.0 + FRAME_SEC for a, b in itertools.pairwise(ends)
    )
    (finished,) = requests(paced, SpeechKind.FINISHED)
    (unpaced,) = requests(plain, SpeechKind.FINISHED)
    assert finished.speech_end == unpaced.speech_end
    assert finished == dataclasses.replace(unpaced, caption_id=finished.caption_id)


# -- TimingRules: the options project 033 added (polyglotic-hq), off by default --


def make_rules_timing(interval: float | None, rules: TimingRules) -> CaptionTiming:
    ids = (CaptionId(f"c{i}") for i in itertools.count(1))
    return CaptionTiming(
        live_update_interval=interval, new_caption_id=lambda: next(ids), rules=rules
    )


def test_defaults_are_the_proof_of_concepts_but_the_lead_in() -> None:
    assert TimingRules() == TimingRules(
        LiveSchedule.EVERY,
        SILENCE_HANGOVER_SEC,
        None,
        None,
        JOIN_GAP_SEC,
        None,
        ONSET_LEAD_IN_SEC,
    )
    pattern: Pattern = [(0.5, False), (9.0, True), (1.5, False)]
    assert run(make_timing(interval=1.5), {APP: pattern}) == run(
        make_rules_timing(1.5, TimingRules(lead_in=0.0)), {APP: pattern}
    )


def test_growing_updates_at_1_5_3_and_6_seconds_into_each_section() -> None:
    out = run(
        make_rules_timing(1.5, poc_rules(schedule=LiveSchedule.GROWING)),
        {APP: [(0.5, False), (13.0, True), (1.5, False)]},
    )
    lives = requests(out, SpeechKind.LIVE)
    offsets = [round(span(live), 1) for live in lives]
    assert offsets == [
        1.5,
        3.0,
        6.0,
        1.5,
        3.0,
        6.0,
    ]  # the 3rd section's 1.5s is at 13.5s
    assert [live.section for live in lives] == [0, 0, 0, 1, 1, 1]
    # Each section starts where the last one's final update ended.
    assert lives[3].speech_start == lives[2].speech_end
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert span(finished) >= 12.9 and finished.caption_id == lives[0].caption_id


def test_growing_paced_drops_the_early_offsets() -> None:
    timing = make_rules_timing(1.5, poc_rules(schedule=LiveSchedule.GROWING))
    timing.pace_hint = 3.0
    out = run(timing, {APP: [(0.5, False), (7.0, True), (1.5, False)]})
    offsets = [round(span(live), 1) for live in requests(out, SpeechKind.LIVE)]
    assert offsets == [3.0, 6.0]


def test_glimpse_is_one_live_update_then_the_finished_caption() -> None:
    out = run(
        make_rules_timing(1.5, poc_rules(schedule=LiveSchedule.GLIMPSE)),
        {APP: [(0.5, False), (9.0, True), (1.5, False)]},
    )
    lives, finished = requests(out, SpeechKind.LIVE), requests(out, SpeechKind.FINISHED)
    assert len(lives) == 1 and len(finished) == 1
    assert 1.5 <= span(lives[0]) < 1.5 + FRAME_SEC and lives[0].section == 0
    assert finished[0].caption_id == lives[0].caption_id and span(finished[0]) >= 8.9


def test_glimpse_waits_for_enough_audio() -> None:
    out = run(
        make_rules_timing(0.5, poc_rules(schedule=LiveSchedule.GLIMPSE)),
        {APP: [(0.5, False), (3.0, True), (1.5, False)]},
    )
    (live,) = requests(out, SpeechKind.LIVE)
    assert 1.0 <= span(live) < 1.0 + FRAME_SEC


@pytest.mark.parametrize("hangover", [0.5, 0.8])
def test_the_silence_hangover_sets_when_a_caption_finishes(hangover: float) -> None:
    out = run(
        make_rules_timing(None, poc_rules(silence_hangover=hangover)),
        {MIC: [(0.5, False), (3.0, True), (0.6, False), (2.0, True), (1.5, False)]},
    )
    finished = requests(out, SpeechKind.FINISHED)
    if hangover == 0.8:
        assert len(finished) == 1 and span(finished[0]) >= 5.5  # the 0.6s is a pause
    else:
        # A 0.6s pause ends the first caption; the second is joined onto it.
        assert len(finished) == 2
        assert finished[0].caption_id == finished[1].caption_id
        assert 2.95 <= span(finished[0]) <= 3.05 and span(finished[1]) >= 5.5


def test_breath_cut_finishes_at_the_first_short_pause_after_4s() -> None:
    rules = poc_rules(breath_cut=BreathCut(after=4.0, pause=0.3, limit=8.0))
    out = run(
        make_rules_timing(None, rules),
        {
            APP: [
                (0.5, False),
                (2.0, True),
                (0.4, False),  # a breath at 2s: too early to cut
                (3.0, True),
                (0.4, False),  # a breath at 5.4s: cut here
                (2.0, True),
                (1.5, False),
            ]
        },
    )
    finished = requests(out, SpeechKind.FINISHED)
    assert len(finished) == 2
    first, second = finished
    assert abs(first.speech_start - T0 - 0.5) < 0.05
    assert abs(first.speech_end - T0 - 5.9) < 0.05
    # The second piece starts when speech resumes, not at the cut, and is
    # not joined onto the cut piece.
    assert abs(second.speech_start - T0 - 6.3) < 0.05
    assert second.caption_id != first.caption_id and second.replaces == ()


def test_breath_cut_limit_splits_nonstop_speech() -> None:
    rules = poc_rules(breath_cut=BreathCut(after=4.0, pause=0.3, limit=8.0))
    out = run(
        make_rules_timing(None, rules),
        {APP: [(0.5, False), (19.0, True), (1.5, False)]},
    )
    finished = requests(out, SpeechKind.FINISHED)
    assert [round(span(f)) for f in finished] == [8, 8, 3]
    assert finished[1].speech_start == finished[0].speech_end
    assert len({f.caption_id for f in finished}) == 3
    assert all(f.replaces == () for f in finished)


def test_breath_cut_with_a_glimpse_gives_each_piece_its_own_glimpse() -> None:
    rules = poc_rules(schedule=LiveSchedule.GLIMPSE, breath_cut=BreathCut())
    out = run(
        make_rules_timing(1.5, rules), {APP: [(0.5, False), (12.0, True), (1.5, False)]}
    )
    lives, finished = requests(out, SpeechKind.LIVE), requests(out, SpeechKind.FINISHED)
    assert len(finished) == 2 and len(lives) == 2
    assert [live.caption_id for live in lives] == [f.caption_id for f in finished]


def test_turn_cut_finishes_the_quiet_source_when_another_starts() -> None:
    rules = poc_rules(turn_cut=0.3)
    app = [(0.5, False), (3.0, True), (5.0, False)]
    mic = [(3.9, False), (2.0, True), (2.6, False)]  # starts 0.4s after the app stops
    out = run(make_rules_timing(None, rules), {APP: app, MIC: mic})
    finished = requests(out, SpeechKind.FINISHED)
    assert [f.source for f in finished] == [APP, MIC]
    # The app's caption is finished at the mic's first speech frame (0.4s
    # after it stopped, not 0.8s); its speech_end is where its speech ended.
    assert abs(finished[0].speech_end - (T0 + 3.5)) < 0.05
    mic_frames = [end for end, speech in frames(mic) if speech]
    # Decisions came in time order: the app's finished caption was decided
    # at the mic's first speech frame, before the mic's own caption.
    assert mic_frames[0] < T0 + 3.5 + 0.8


def test_turn_cut_needs_the_quiet_to_have_lasted() -> None:
    rules = poc_rules(turn_cut=0.3)
    app = [(0.5, False), (3.0, True), (0.1, False), (5.0, False)]
    mic = [(3.6, False), (2.0, True), (3.0, False)]  # starts 0.1s after: too soon
    out = run(make_rules_timing(None, rules), {APP: app, MIC: mic})
    # Two captions, both whole; the app's waited for its full hangover.
    assert len(requests(out, SpeechKind.FINISHED)) == 2
    assert {f.source for f in requests(out, SpeechKind.FINISHED)} == {APP, MIC}


BACK_TO_BACK: Pattern = [
    (0.5, False),
    (3.0, True),
    (1.2, False),
    (2.0, True),
    (1.5, False),
]


def test_joins_can_be_turned_off() -> None:
    out = run(make_rules_timing(None, poc_rules(join_gap=0.0)), {MIC: BACK_TO_BACK})
    finished = requests(out, SpeechKind.FINISHED)
    assert len(finished) == 2 and finished[0].caption_id != finished[1].caption_id
    assert finished[1].speech_start > finished[0].speech_end


def test_joins_only_repair_fragments_when_asked() -> None:
    rules = poc_rules(join_only_under=2.0)
    # A 3s caption is a sentence, not a fragment: the speech after it is
    # its own caption.
    finished = requests(
        run(make_rules_timing(None, rules), {MIC: BACK_TO_BACK}), SpeechKind.FINISHED
    )
    assert len({f.caption_id for f in finished}) == 2
    # A 1.5s caption may be a fragment cut by a pause: joined, as today.
    short: Pattern = [
        (0.5, False),
        (1.5, True),
        (1.2, False),
        (2.0, True),
        (1.5, False),
    ]
    finished = requests(
        run(make_rules_timing(None, rules), {MIC: short}), SpeechKind.FINISHED
    )
    assert len(finished) == 2 and finished[0].caption_id == finished[1].caption_id


# -- The lead-in (project 038): a soft first word isn't clipped ----------------

FIRST_FRAME = T0 + 0.512  # the first speech frame after 0.5s of silence starts here


def test_a_caption_after_silence_starts_a_lead_in_before_its_first_speech() -> None:
    pattern: Pattern = [(0.5, False), (9.0, True), (1.5, False)]
    out = run(make_rules_timing(1.5, TimingRules()), {APP: pattern})
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert finished.speech_start == pytest.approx(FIRST_FRAME - ONSET_LEAD_IN_SEC)
    live = requests(out, SpeechKind.LIVE)
    assert live[0].speech_start == finished.speech_start  # the first section too
    later = [r for r in live if r.section]
    assert later and all(r.speech_start > FIRST_FRAME for r in later)  # mid-speech
    # only where the speech starts moves: what's sent when, and its ends, don't
    without = run(make_timing(interval=1.5), {APP: pattern})
    assert [(type(d), getattr(d, "speech_end", None)) for d in out] == [
        (type(d), getattr(d, "speech_end", None)) for d in without
    ]


def test_the_lead_in_stops_where_the_previous_captions_audio_ended() -> None:
    rules = TimingRules(silence_hangover=0.5, join_gap=0.0)
    pattern: Pattern = [
        (0.5, False),
        (2.0, True),
        (0.6, False),
        (2.0, True),
        (1.0, False),
    ]
    first, second = requests(
        run(make_rules_timing(None, rules), {APP: pattern}), SpeechKind.FINISHED
    )
    # 0.6s apart: 0.2s of lead-in, so the second's audio (its margin
    # included) starts where the first's ended - nothing sent twice
    assert second.speech_start - SLICE_PAD_SEC == pytest.approx(
        first.speech_end + SLICE_PAD_SEC
    )
    assert 0 < FIRST_FRAME + 2.6 - second.speech_start < ONSET_LEAD_IN_SEC


def test_no_lead_in_after_a_breath_or_a_split() -> None:
    rules = TimingRules(breath_cut=BreathCut(after=4.0, pause=0.3, limit=8.0))
    breath: Pattern = [
        (0.5, False),
        (5.0, True),
        (0.35, False),
        (3.0, True),
        (1.5, False),
    ]
    first, second = requests(
        run(make_rules_timing(None, rules), {APP: breath}), SpeechKind.FINISHED
    )
    assert first.speech_start == pytest.approx(FIRST_FRAME - ONSET_LEAD_IN_SEC)
    assert second.speech_start > first.speech_end + 0.3  # 0.35s apart: none
    long: Pattern = [(0.5, False), (25.0, True), (1.5, False)]
    first, second = requests(
        run(make_rules_timing(None, TimingRules()), {APP: long}), SpeechKind.FINISHED
    )
    assert second.speech_start == first.speech_end  # the speech went on


def test_a_joined_caption_starts_with_the_first_ones_lead_in() -> None:
    pattern: Pattern = [
        (0.5, False),
        (2.0, True),
        (1.0, False),
        (2.0, True),
        (1.5, False),
    ]
    first, joined = requests(
        run(make_rules_timing(None, TimingRules()), {APP: pattern}), SpeechKind.FINISHED
    )
    assert joined.caption_id == first.caption_id
    assert joined.speech_start == first.speech_start
    assert first.speech_start == pytest.approx(FIRST_FRAME - ONSET_LEAD_IN_SEC)


def test_a_short_sound_not_sent_doesnt_shorten_the_lead_in() -> None:
    pattern: Pattern = [
        (0.5, False),
        (0.2, True),
        (0.9, False),
        (3.0, True),
        (1.5, False),
    ]
    (finished,) = requests(
        run(make_rules_timing(None, TimingRules()), {APP: pattern}), SpeechKind.FINISHED
    )
    assert finished.speech_start == pytest.approx(
        T0 + 0.5 + 0.2 + 0.9 + 0.012 - ONSET_LEAD_IN_SEC, abs=FRAME_SEC
    )


# -- Caption modes (polyglotic-hq DECISIONS.md #4, project 064) ----------------


def mode_timing(mode: CaptionMode, chosen: float = 1.5) -> CaptionTiming:
    return make_rules_timing(mode.live_update_interval(chosen), mode.rules)


SENTENCE_THEN_MORE: Pattern = [  # a 2.2s sentence, 0.7s quiet, then 2s more
    (0.5, False),
    (2.2, True),
    (0.7, False),
    (2.0, True),
    (1.5, False),
]


def test_steady_is_each_caption_once_finished_at_a_0_6s_pause() -> None:
    """Project 033's Y: no live updates; a 0.7s pause finishes a caption
    (the proof of concept waited 0.8s), and the 2.2s caption before it is
    a sentence, not a fragment, so nothing is joined onto it. (Short of
    the breath cut's 3s: from there a 0.3s pause finishes it.)"""
    timing = mode_timing(CaptionMode.WHOLE)
    timing.add_source(APP)
    decided: list[tuple[float, Decision]] = []
    for end, speech in frames(SENTENCE_THEN_MORE):
        decided += [(end, d) for d in timing.frame(APP.id, end, speech)]
    out = [d for _, d in decided]
    assert requests(out, SpeechKind.LIVE) == []
    first, second = requests(out, SpeechKind.FINISHED)
    assert first.caption_id != second.caption_id and second.replaces == ()
    assert first.speech_end == pytest.approx(T0 + 2.7, abs=FRAME_SEC)
    # finished 0.6s after the speech stopped, not 0.8s
    assert decided[0][0] - first.speech_end == pytest.approx(0.6, abs=FRAME_SEC)


def test_steady_cuts_long_speech_at_a_breath_after_3s() -> None:
    pattern: Pattern = [
        (0.5, False),
        (1.0, True),
        (0.4, False),  # a breath 1s in: too early to cut
        (2.3, True),
        (0.4, False),  # a breath once it has run 3s: finished here
        (2.5, True),
        (1.5, False),
    ]
    first, second = requests(
        run(mode_timing(CaptionMode.WHOLE), {APP: pattern}), SpeechKind.FINISHED
    )
    assert first.speech_end == pytest.approx(T0 + 4.2, abs=FRAME_SEC)
    assert second.caption_id != first.caption_id and second.replaces == ()
    nonstop = run(
        mode_timing(CaptionMode.WHOLE),
        {APP: [(0.5, False), (17.0, True), (1.0, False)]},
    )
    assert [round(span(f)) for f in requests(nonstop, SpeechKind.FINISHED)][:2] == [
        6,
        6,
    ]


def test_continuous_speech_is_never_8s_without_a_caption() -> None:
    """The user's F34 in Steady (polyglotic-hq 268, from 243's phase 2):
    in continuous speech - no pause long enough for a breath - a caption
    arrives every 6s, not every 8s, in Steady and Quick preview alike."""
    for mode in (CaptionMode.WHOLE, CaptionMode.PREVIEW):
        timing = mode_timing(mode)
        timing.add_source(APP)
        shown = [T0 + 0.5]
        for end, speech in frames([(0.5, False), (30.0, True), (1.0, False)]):
            if requests(timing.frame(APP.id, end, speech), SpeechKind.FINISHED):
                shown.append(end)
        gaps = [b - a for a, b in itertools.pairwise(shown)]
        assert len(gaps) == 5
        assert max(gaps) == pytest.approx(6.0, abs=2 * FRAME_SEC)


def test_quick_preview_s_first_live_update_is_1_5s_in_replaced_by_the_finished() -> (
    None
):
    """Project 033's Z: Steady plus a provisional live update 1.5s in -
    whatever the learner's live-update interval - under the caption's id,
    so the finished caption replaces it."""
    out = run(
        mode_timing(CaptionMode.PREVIEW, chosen=0.5),
        {APP: [(0.5, False), (2.5, True), (1.5, False)]},
    )
    (live,) = requests(out, SpeechKind.LIVE)
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert live.speech_end - FIRST_FRAME == pytest.approx(1.5, abs=FRAME_SEC)
    assert finished.caption_id == live.caption_id
    assert out.index(live) < out.index(finished)
    # Its rules are Steady's, on the growing schedule (260)
    assert CaptionMode.PREVIEW.rules == dataclasses.replace(
        CaptionMode.WHOLE.rules, schedule=LiveSchedule.GROWING
    )


@pytest.mark.parametrize("mode", list(CaptionMode))
def test_each_mode_s_breath_cut_is_tuned_in_one_place(mode: CaptionMode) -> None:
    """polyglotic-hq 260: `BREATH_CUTS` is where a mode's breath cut is
    tuned; the mode's rules follow it. 3/0.3/6 since 268 (243's phase 2:
    021's 4/0.3/8 showed nothing for 8.2s at a time in continuous
    speech) - Live updates too, since 296 (decision 0088)."""
    assert mode.rules.breath_cut is BREATH_CUTS[mode]
    assert BREATH_CUTS[mode] == BreathCut(after=3.0, pause=0.3, limit=6.0)


def test_live_updates_finish_unbroken_speech_in_pieces() -> None:
    """polyglotic-hq 296 (the user, 2026-11-13: "We don't need to rewrite
    words spoken 3 seconds ago right?"): Live updates' finished caption
    redid the whole stretch - 20s of nonstop speech at once, 14 to 22
    clauses rewritten. Now it finishes in pieces of 6s at most, as Steady
    does, each a caption of its own, cut where the next begins; and a live
    update never hears further back than its own piece."""
    out = run(
        mode_timing(CaptionMode.INSTANT),
        {APP: [(0.5, False), (20.0, True), (1.5, False)]},
    )
    pieces = requests(out, SpeechKind.FINISHED)
    assert [round(span(p)) for p in pieces] == [6, 6, 6, 2]
    assert len({p.caption_id for p in pieces}) == 4
    assert all(p.replaces == () for p in pieces)
    assert [p.cut_after for p in pieces] == [True, True, True, False]
    lives = requests(out, SpeechKind.LIVE)
    for piece in pieces:
        own = [u for u in lives if u.caption_id == piece.caption_id]
        assert own, "each piece has its live updates"
        assert all(u.speech_start >= piece.speech_start - 1e-9 for u in own)
        assert all(u.section == 0 for u in own)
    assert max(span(r) for r in requests(out, SpeechKind.FINISHED)) < 6.5


def test_live_updates_finish_at_a_breath_once_a_caption_has_run_a_while() -> None:
    """...and at a 0.3s breath once a caption has run 3s, so most pieces
    end between phrases, not at the limit (296)."""
    out = run(
        mode_timing(CaptionMode.INSTANT),
        {APP: [(0.5, False), (4.0, True), (0.4, False), (3.0, True), (1.5, False)]},
    )
    first, second = requests(out, SpeechKind.FINISHED)
    assert round(span(first)) == 4 and round(span(second)) == 3
    assert first.caption_id != second.caption_id
    assert not first.cut_after and not second.cut_before


def test_quick_preview_keeps_updating_through_long_speech() -> None:
    """The user's F34 (polyglotic-hq 260, 2026-11-09): Quick preview "will
    not do anything for an extended period of time and then suddenly
    update all of the speech at once" - one glimpse at 1.5s, then nothing
    until the pause. On the growing schedule it updates 1.5 and 3s in, and
    again in each piece a breath cut starts (since 268 the cut's 6s limit
    comes before the schedule's 6s)."""
    out = run(
        mode_timing(CaptionMode.PREVIEW),
        {APP: [(0.5, False), (5.5, True), (1.5, False)]},
    )
    lives = requests(out, SpeechKind.LIVE)
    (finished,) = requests(out, SpeechKind.FINISHED)
    offsets = [round(live.speech_end - FIRST_FRAME, 1) for live in lives]
    assert offsets == [1.5, 3.0]
    assert {live.caption_id for live in lives} == {finished.caption_id}
    # nonstop past the breath cut's limit (6s): each piece updates again
    nonstop = run(
        mode_timing(CaptionMode.PREVIEW),
        {APP: [(0.5, False), (14.0, True), (1.5, False)]},
    )
    lives = requests(nonstop, SpeechKind.LIVE)
    pieces = requests(nonstop, SpeechKind.FINISHED)
    assert [round(span(p)) for p in pieces] == [6, 6, 2]
    assert [
        len([u for u in lives if u.caption_id == p.caption_id]) for p in pieces
    ] == [2, 2, 1]


def test_live_updates_are_the_proof_of_concepts_timing_at_the_chosen_interval() -> None:
    out = run(
        mode_timing(CaptionMode.INSTANT, chosen=1.0),
        {APP: [(0.5, False), (5.0, True), (1.5, False)]},
    )
    lives = requests(out, SpeechKind.LIVE)
    assert [round(live.speech_end - FIRST_FRAME) for live in lives] == [1, 2, 3, 4]
    rules = CaptionMode.INSTANT.rules
    assert rules.silence_hangover == SILENCE_HANGOVER_SEC
    assert CaptionMode.INSTANT.live_update_interval(1.0) == 1.0
    assert CaptionMode.WHOLE.live_update_interval(1.0) is None


@pytest.mark.parametrize("mode", list(CaptionMode))
def test_every_mode_joins_only_onto_a_fragment(mode: CaptionMode) -> None:
    """Whole-run joins are gone in every mode (project 021: the biggest
    waste): speech 1.2s after a 3s caption is a caption of its own; after
    a 1.2s fragment it is still joined on."""
    assert mode.rules.join_only_under == FRAGMENT_SEC
    sentence = requests(
        run(mode_timing(mode), {MIC: BACK_TO_BACK}), SpeechKind.FINISHED
    )
    assert len({f.caption_id for f in sentence}) == 2
    assert all(f.replaces == () for f in sentence)
    fragment: Pattern = [
        (0.5, False),
        (1.2, True),
        (1.2, False),
        (1.5, True),
        (1.5, False),
    ]
    joined = requests(run(mode_timing(mode), {MIC: fragment}), SpeechKind.FINISHED)
    assert len(joined) == 2 and joined[0].caption_id == joined[1].caption_id
    assert joined[1].speech_start == joined[0].speech_start


def test_the_mode_can_change_while_listening() -> None:
    """The learner picks another mode mid-session: from the next frame on,
    its rules and interval apply."""
    timing = mode_timing(CaptionMode.INSTANT)
    pattern: Pattern = [(0.5, False), (5.0, True), (1.5, False)]
    assert requests(run(timing, {APP: pattern}), SpeechKind.LIVE)
    timing.change(CaptionMode.WHOLE.rules, None)
    out = []
    for end, speech in frames(pattern, start=T0 + 10):
        out.extend(timing.frame(APP.id, end, speech))
    assert requests(out, SpeechKind.LIVE) == []
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert finished.speech_end == pytest.approx(T0 + 15.5, abs=FRAME_SEC)


def test_hearing_is_speech_under_way_long_enough_to_send() -> None:
    """What the listening mark shows is being heard: a source whose speech
    has gone on long enough to be sent (not a blip), until its pause has
    passed; nothing while paused."""
    timing = mode_timing(CaptionMode.WHOLE)
    timing.add_source(APP)
    heard: list[tuple[float, frozenset[SourceId]]] = []
    for end, speech in frames([(0.5, False), (2.0, True), (1.0, False)]):
        timing.frame(APP.id, end, speech)
        heard.append((round(end - T0, 3), timing.hearing()))
    under_way = [at for at, sources in heard if sources == {APP.id}]
    assert under_way[0] == pytest.approx(0.5 + 0.4, abs=2 * FRAME_SEC)
    assert under_way[-1] == pytest.approx(2.5 + 0.6, abs=2 * FRAME_SEC)
    assert under_way == [at for at, _ in heard if under_way[0] <= at <= under_way[-1]]
    blip = mode_timing(CaptionMode.WHOLE)
    blip.add_source(APP)
    for end, speech in frames([(0.5, False), (0.3, True), (1.0, False)]):
        blip.frame(APP.id, end, speech)
        assert blip.hearing() == frozenset()
    timing.paused = True
    for end, speech in frames([(2.0, True)], start=T0 + 10):
        timing.frame(APP.id, end, speech)
    assert timing.hearing() == frozenset()


# -- The longest wait for text (polyglotic-hq 277) ------------------------------

NONSTOP: Pattern = [(0.5, False), (30.0, True), (1.0, False)]
WITH_BREATHS: Pattern = [  # a talker who rarely stops: breaths, one short pause
    (0.5, False),
    (3.4, True),
    (0.35, False),
    (4.0, True),
    (0.2, False),
    (5.0, True),
    (0.35, False),
    (7.5, True),
    (0.15, False),
    (2.0, True),
    (1.5, False),
]


def waiting_timing(
    mode: CaptionMode, max_wait: float | None, chosen: float = 1.5
) -> CaptionTiming:
    ids = (CaptionId(f"c{i}") for i in itertools.count(1))
    return CaptionTiming(
        mode.live_update_interval(chosen),
        new_caption_id=lambda: next(ids),
        rules=mode.rules,
        max_wait=max_wait,
    )


def longest_without_text(timing: CaptionTiming, pattern: Pattern) -> float:
    """The most seconds of speech the source ran with no text asked for -
    neither a live update nor a finished caption - since its speech began
    or the last one."""
    timing.add_source(APP)
    without, longest = 0.0, 0.0
    for end, speech in frames(pattern):
        if any(
            isinstance(d, TranscriptionRequest)
            for d in timing.frame(APP.id, end, speech)
        ):
            without = 0.0
        elif speech:
            without += FRAME_SEC
            longest = max(longest, without)
    return longest


@pytest.mark.parametrize("max_wait", [2.0, 2.5, 3.0, 4.0, 5.0, 6.0])
@pytest.mark.parametrize(
    ("mode", "chosen"),
    [
        (CaptionMode.WHOLE, 1.5),
        (CaptionMode.PREVIEW, 1.5),
        (CaptionMode.INSTANT, 1.5),
        (CaptionMode.INSTANT, 10.0),  # a long interval chosen
    ],
)
@pytest.mark.parametrize("pattern", [NONSTOP, WITH_BREATHS], ids=["nonstop", "breaths"])
def test_no_mode_runs_longer_than_the_longest_wait_without_text(
    mode: CaptionMode, chosen: float, max_wait: float, pattern: Pattern
) -> None:
    """The user, 2026-11-11: "I just don't want these super long extended
    monologues causing the captioning to completely stop ... max 3s or
    something before displaying current text." Before 277: Steady ran 6s
    without text, Quick preview 3s at any setting, Live updates its
    interval."""
    timing = waiting_timing(mode, max_wait, chosen)
    assert longest_without_text(timing, pattern) <= max_wait + FRAME_SEC


def test_steady_s_provisional_line_comes_at_the_longest_wait_and_no_sooner() -> None:
    """Steady stays the calmest: a caption that ends within the wait gets
    no live update at all; one that runs on gets one at the wait, under
    its own id, so the finished caption replaces it - and in nonstop speech
    one in each 6s piece the breath cut makes."""
    short = run(waiting_timing(CaptionMode.WHOLE, 3.0), {APP: SENTENCE_THEN_MORE})
    assert requests(short, SpeechKind.LIVE) == []
    out = run(
        waiting_timing(CaptionMode.WHOLE, 3.0),
        {APP: [(0.5, False), (4.0, True), (1.5, False)]},
    )
    (live,) = requests(out, SpeechKind.LIVE)
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert live.speech_end - FIRST_FRAME == pytest.approx(3.0, abs=FRAME_SEC)
    assert live.caption_id == finished.caption_id
    assert out.index(live) < out.index(finished)
    nonstop = run(waiting_timing(CaptionMode.WHOLE, 3.0), {APP: NONSTOP})
    pieces = requests(nonstop, SpeechKind.FINISHED)
    lives = requests(nonstop, SpeechKind.LIVE)
    assert [round(span(p)) for p in pieces][:4] == [6, 6, 6, 6]
    assert [round(live.speech_end - FIRST_FRAME) for live in lives][:4] == [
        3,
        9,
        15,
        21,
    ]


def test_a_longer_wait_gives_steady_fewer_lines() -> None:
    """At 6s, Steady's breath cut comes first: no provisional lines in
    nonstop speech, as before 277. At 2s, two in each 6s piece."""
    six = run(waiting_timing(CaptionMode.WHOLE, 6.0), {APP: NONSTOP})
    assert requests(six, SpeechKind.LIVE) == []
    two = run(waiting_timing(CaptionMode.WHOLE, 2.0), {APP: NONSTOP})
    first = requests(two, SpeechKind.FINISHED)[0]
    assert (
        len(
            [
                u
                for u in requests(two, SpeechKind.LIVE)
                if u.caption_id == first.caption_id
            ]
        )
        == 2
    )


def test_live_updates_at_a_long_interval_still_update_within_the_wait() -> None:
    out = run(
        waiting_timing(CaptionMode.INSTANT, 3.0, chosen=10.0),
        {APP: [(0.5, False), (10.0, True), (1.5, False)]},
    )
    lives = requests(out, SpeechKind.LIVE)
    # 3s into each piece; at 6s the piece is finished instead (296)
    assert [round(live.speech_end - FIRST_FRAME) for live in lives] == [3, 9]
    pieces = requests(out, SpeechKind.FINISHED)
    assert [round(p.speech_end - FIRST_FRAME) for p in pieces] == [6, 10]


def test_the_pace_hint_stretches_the_wait_too() -> None:
    """A busy server's pace hint holds back every live update, the longest
    wait's too; finished captions never wait."""
    timing = waiting_timing(CaptionMode.WHOLE, 3.0)
    timing.pace_hint = 5.0
    assert timing.paced_max_wait == 5.0
    out = run(timing, {APP: [(0.5, False), (5.5, True), (1.5, False)]})
    (live,) = requests(out, SpeechKind.LIVE)
    assert live.speech_end - FIRST_FRAME == pytest.approx(5.0, abs=FRAME_SEC)
    timing.pace_hint = 2.0  # shorter than the learner's: theirs stands
    assert timing.paced_max_wait == 3.0


def test_steady_and_quick_preview_lines_are_provisional() -> None:
    assert CaptionMode.WHOLE.provisional_lines
    assert CaptionMode.PREVIEW.provisional_lines
    assert not CaptionMode.INSTANT.provisional_lines


def test_after_the_first_second_live_updates_come_at_the_interval_chosen() -> None:
    """polyglotic-hq 284 (270's triage): at 0.5 s the first live update
    still waits for a second of speech (LIVE_MIN_AUDIO_SEC), and then
    they come every 0.5 s - which the Timing panel's line now says."""
    out = run(
        make_timing(interval=0.5), {APP: [(0.5, False), (3.0, True), (1.5, False)]}
    )
    spans = [span(r) for r in requests(out, SpeechKind.LIVE)]
    assert spans[0] == pytest.approx(1.0, abs=FRAME_SEC)
    gaps = [b - a for a, b in itertools.pairwise(spans)]
    assert gaps and all(g == pytest.approx(0.5, abs=FRAME_SEC) for g in gaps)


# -- A cut while the speech goes on (polyglotic-hq 291, decision 0083) --------

LOUD, HUSH = 0.1, 0.001


def run_levels(
    timing: CaptionTiming, seconds: float, quiet: Sequence[tuple[float, float]] = ()
) -> list[Decision]:
    """Nonstop speech from T0 + 0.5 for `seconds` (speech detection never
    hears a pause, as in a tester's fast video), each frame `LOUD` but in
    the `quiet` stretches (seconds into the speech: start, length), and
    1.5s of silence after; returns every decision."""
    timing.add_source(APP)
    out: list[Decision] = []
    for end, speech in frames([(0.5, False), (seconds, True), (1.5, False)]):
        into = end - FRAME_SEC / 2 - (T0 + 0.5)
        hushed = any(a <= into < a + n for a, n in quiet)
        level = HUSH if hushed or not speech else LOUD
        out.extend(timing.frame(APP.id, end, speech, level))
    return out


def test_a_cut_at_the_limit_falls_at_the_quietest_moment_before_it() -> None:
    """A tester's fast video (291): Steady cut it at 6.02s, mid-word. The
    quietest moment of the 1.5s before the limit - here a 0.1s dip 5.2s
    in - is where it's cut, and the next caption starts there."""
    out = run_levels(mode_timing(CaptionMode.WHOLE), 9.0, quiet=[(5.2, 0.1)])
    first, second = requests(out, SpeechKind.FINISHED)
    dip = FIRST_FRAME + 5.2 - 0.012  # the dip, on the frames' clock
    assert first.speech_end == pytest.approx(dip + 0.05, abs=2 * FRAME_SEC)
    assert second.speech_start == first.speech_end


def test_a_dip_before_the_last_1_5s_isnt_where_it_is_cut() -> None:
    out = run_levels(mode_timing(CaptionMode.WHOLE), 9.0, quiet=[(3.5, 0.1)])
    first = requests(out, SpeechKind.FINISHED)[0]
    assert span(first) == pytest.approx(6.0 + ONSET_LEAD_IN_SEC, abs=2 * FRAME_SEC)


def test_the_two_sides_of_a_cut_say_so_and_their_audio_doesnt_overlap() -> None:
    """291: each piece's audio ran 0.2s past the cut each side, so 0.4s -
    a word or two of fast speech - was heard, and captioned, twice."""
    timing = mode_timing(CaptionMode.WHOLE)
    timing.max_wait = 2.0  # the friend's longest wait for text
    out = run_levels(timing, 14.0, quiet=[(5.2, 0.1)])
    pieces = requests(out, SpeechKind.FINISHED)
    assert len(pieces) == 3
    assert [(p.cut_before, p.cut_after) for p in pieces] == [
        (False, True),
        (True, True),
        (True, False),
    ]
    assert pieces[0].pads == (SLICE_PAD_SEC, 0.0)
    assert pieces[1].pads == (0.0, 0.0)
    assert pieces[2].pads == (0.0, SLICE_PAD_SEC)
    for before, after in itertools.pairwise(pieces):
        audio_ends = before.speech_end + before.pads[1]
        assert after.speech_start - after.pads[0] == pytest.approx(audio_ends)
    # a live update of a caption that began at a cut starts there too
    lives = [
        r
        for r in requests(out, SpeechKind.LIVE)
        if r.caption_id == pieces[1].caption_id
    ]
    assert lives and lives[0].cut_before and lives[0].pads[0] == 0.0
    assert not any(r.cut_after for r in requests(out, SpeechKind.LIVE))


def test_a_long_speech_split_is_cut_at_its_quietest_moment_too() -> None:
    # rules with no breath cut (the proof of concept's): every caption mode
    # has one since 296, so only these reach the 20s split
    timing = make_rules_timing(1.5, TimingRules())
    out = run_levels(timing, 24.0, quiet=[(19.0, 0.1)])
    first, second = requests(out, SpeechKind.FINISHED)
    assert first.cut_after and second.cut_before
    assert first.speech_end == pytest.approx(
        FIRST_FRAME + 19.0 + 0.04, abs=2 * FRAME_SEC
    )


def test_a_pause_ends_a_caption_as_before_with_its_margins() -> None:
    """Only a cut while the speech goes on loses its margins."""
    out = run_levels(mode_timing(CaptionMode.WHOLE), 4.0)
    (finished,) = requests(out, SpeechKind.FINISHED)
    assert not finished.cut_before and not finished.cut_after
    assert finished.pads == (SLICE_PAD_SEC, SLICE_PAD_SEC)


def test_without_loudness_the_cut_falls_at_the_limit_as_before() -> None:
    timing = mode_timing(CaptionMode.WHOLE)
    timing.add_source(APP)
    out: list[Decision] = []
    for end, speech in frames([(0.5, False), (9.0, True), (1.5, False)]):
        out.extend(timing.frame(APP.id, end, speech))
    first, second = requests(out, SpeechKind.FINISHED)
    assert span(first) == pytest.approx(6.0 + ONSET_LEAD_IN_SEC, abs=2 * FRAME_SEC)
    assert first.cut_after and second.cut_before


# -- the speech ceiling: live updates wait their turn (decision 0097) ----------------

APPS = (
    APP,
    Source(SourceId("source-2"), SourceCategory.GAME),
    Source(SourceId("source-3"), SourceCategory.CALL),
)


def live_mode_timing(interval: float, ceiling: float | None = 600.0) -> CaptionTiming:
    """Live updates as the app runs it, every `interval` seconds."""
    ids = (CaptionId(f"c{i}") for i in itertools.count(1))
    timing = CaptionTiming(
        live_update_interval=interval,
        new_caption_id=lambda: next(ids),
        rules=CaptionMode.INSTANT.rules,
        max_wait=3.0,
    )
    timing.speech_ceiling = ceiling
    return timing


def talk(
    timing: CaptionTiming, sources: Sequence[Source], seconds: float
) -> list[tuple[float, TranscriptionRequest]]:
    """Every source talking without a pause for `seconds`: each request
    with the time it was asked for."""
    for source in sources:
        timing.add_source(source)
    out: list[tuple[float, TranscriptionRequest]] = []
    for end, speech in frames([(seconds, True), (1.5, False)]):
        for source in sources:
            for decision in timing.frame(source.id, end, speech):
                assert isinstance(decision, TranscriptionRequest)
                out.append((end, decision))
    return out


def busiest_minute(sent: list[tuple[float, TranscriptionRequest]]) -> float:
    """The most audio asked for in any 60 seconds, margins and all - what
    the server's speech ceiling counts."""
    most = 0.0
    for n, (first, _) in enumerate(sent):
        total = 0.0
        for at, request in sent[n:]:
            if at - first >= 60.0:
                break
            total += request.audio_seconds
        most = max(most, total)
    return most


def test_three_apps_talking_stay_under_the_speech_ceiling() -> None:
    """polyglotic-hq 307: three apps in Live updates every 0.75s sent about
    1,000s of audio a minute against the server's 600, and it refused every
    live update for a third of each minute."""
    sent = talk(live_mode_timing(0.75), APPS, 150.0)
    assert busiest_minute(sent) <= 600.0
    # ... and nothing like as much is asked for without the rule
    assert busiest_minute(talk(live_mode_timing(0.75, None), APPS, 150.0)) > 800.0


def test_the_speech_ceiling_never_holds_finished_speech() -> None:
    held = talk(live_mode_timing(0.5), APPS, 150.0)
    free = talk(live_mode_timing(0.5, None), APPS, 150.0)

    def finished(sent: list[tuple[float, TranscriptionRequest]]) -> list[Any]:
        return [
            (at, r.source.id, r.speech_start, r.speech_end)
            for at, r in sent
            if r.kind is SpeechKind.FINISHED
        ]

    assert finished(held) == finished(free)


def test_under_the_speech_ceiling_each_app_gets_its_turn() -> None:
    timing = live_mode_timing(0.5)
    sent = talk(timing, APPS, 150.0)
    assert timing.live_updates_held > 0
    for source in APPS:
        ends = [
            at
            for at, r in sent
            if r.kind is SpeechKind.LIVE and r.source.id == source.id and at > T0 + 30
        ]
        # held, a live update comes late - never not at all: none of the
        # three goes more than a few seconds without one
        assert max(b - a for a, b in itertools.pairwise(ends)) < 6.5
    counts = [
        sum(r.kind is SpeechKind.LIVE and r.source.id == source.id for _, r in sent)
        for source in APPS
    ]
    assert max(counts) - min(counts) <= 0.1 * max(counts)


def test_one_app_talking_is_never_held_by_the_speech_ceiling() -> None:
    timing = live_mode_timing(0.75)
    sent = talk(timing, APPS[:1], 150.0)
    assert timing.live_updates_held == 0
    assert sent == talk(live_mode_timing(0.75, None), APPS[:1], 150.0)


@pytest.mark.parametrize("stops_after", [60.0 + n * 0.128 for n in range(12)])
def test_a_source_that_stops_talking_gives_up_its_turn(stops_after: float) -> None:
    """A held live update's turn goes with its speech: the others don't
    wait behind a source that has fallen silent."""
    timing = live_mode_timing(0.5)
    for source in APPS:
        timing.add_source(source)
    last_live: dict[SourceId, float] = {}
    for end, _ in frames([(120.0, True)]):
        for source in APPS:
            speaking = not (source is APPS[2] and end >= T0 + stops_after)
            for decision in timing.frame(source.id, end, speaking):
                if (
                    isinstance(decision, TranscriptionRequest)
                    and decision.kind is SpeechKind.LIVE
                ):
                    last_live[source.id] = end
    assert last_live[APPS[0].id] > T0 + 117.0
    assert last_live[APPS[1].id] > T0 + 117.0
