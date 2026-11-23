"""What a stretch of caption timelines says (perf.trace_summary; polyglotic-hq 543):
segments, hangs and their causes, bursts, drops - and the usage statistics
and problem report made from them."""

import json
from typing import Any

import pytest

from polyglotic_desktop.perf.trace import APP_STAGES, Tracer, Unheard
from polyglotic_desktop.perf.trace_summary import (
    SAMPLES_KEPT,
    SessionTimelines,
    Summary,
    compact,
    expand,
    report_text,
    segments,
    summarise,
    usage_properties,
)

# polyglotic-server's docs/tracking-plan.yaml, caption_timeline_summarised
PLAN = {
    "caption_mode", "live_interval_seconds", "listening_seconds", "platform",
    "updates", "shown", "hangs", "bursts", "drops", "held_mouse", "held_gap",
    "interface_stalls",
    *(
        f"{s}_p{p}_ms"
        for s in ("capture", "detect", "app_queue", "network", "server_queue",
                  "server_work", "interface_queue", "window_hold", "total")
        for p in (50, 95)
    ),
    *(
        f"hangs_{c}"
        for c in ("dropped", "not_asked", "pause", "capture", "detect", "encode",
                  "app_queue", "send", "network", "server_queue", "server_work",
                  "interface_queue", "apply", "window_hold", "paint", "unknown",
                  "sound_unheard")
    ),
}  # fmt: skip


def update(
    seq: int,
    captured: float,
    shown: float,
    source: str = "video",
    audio: float = 3.0,
    held: str | None = None,
    end: str = "painted",
    windowed: float | None = None,
) -> dict[str, Any]:
    """A live update heard at `captured`, quick all the way to the
    interface thread (0.15 s), then shown at `shown`."""
    t = {
        "captured": captured,
        "heard": captured,
        "delivered": captured + 0.01,
        "detected": captured + 0.02,
        "encoded": captured + 0.03,
        "taken": captured + 0.04,
        "sent": captured + 0.05,
        "received": captured + 0.14,
        "handed": captured + 0.145,
        "applied": captured + 0.15,
    }
    if end == "painted":
        t["windowed"] = windowed if windowed is not None else shown - 0.005
        t["painted"] = shown
    found: dict[str, Any] = {
        "seq": seq, "cap": "c1", "kind": "live", "sec": 0, "src": source,
        "audio": audio, "t": t, "end": end,
        "srv": {"waited": 10, "queued": 1, "server": 60},
    }  # fmt: skip
    if held:
        found["held"] = held
    return found


def test_an_updates_segments_split_the_network_from_the_server() -> None:
    parts = segments(update(1, 10.0, 10.2))
    assert round(parts["network"]) == 30  # a 90 ms round trip, 60 on the server
    assert parts["server_queue"] == 10 and parts["server_work"] == 50
    assert round(parts["total"]) == 200
    assert round(parts["capture"]) == 10 and round(parts["app_queue"]) == 10


def test_a_window_holding_updates_is_a_hang_put_down_to_it() -> None:
    """The user's symptom (2026-11-20): "delay and then process it all at
    once". Live updates every 0.5 s reach the interface at once, but the
    caption window lets them in 3 s later, together."""
    records = [update(n, 10.0 + n * 0.5, 10.0 + n * 0.5 + 0.2) for n in range(4)]
    held_until = 15.2
    records += [
        update(
            n,
            10.0 + n * 0.5,
            held_until + 0.01 * (n - 4),
            held="mouse",
            windowed=held_until,
        )
        for n in range(4, 10)
    ]
    found = summarise(records)
    assert [h.cause for h in found.hangs] == ["window_hold"]
    assert found.hangs[0].seconds > 2.0
    assert len(found.bursts) == 1 and found.bursts[0][1] == 6
    assert found.held["mouse"] == 6


def test_a_new_captions_updates_held_from_its_start_are_a_hang() -> None:
    """346's loop with the mouse over the window (543, 2026-11-20): the last
    caption showed at 21.5 s, the next began at 24.3 s, and its live updates
    from 25.6 s were let in together at 34.4 s. The speech began after the
    last update showed, so the hang runs from its start."""
    held = [
        update(
            n, 25.6 + n * 0.5, 34.4, audio=1.3 + n * 0.5, held="mouse", windowed=34.4
        )
        for n in range(1, 6)
    ]
    found = summarise([update(0, 21.0, 21.5, audio=3.0), *held])
    [hang] = found.hangs
    assert hang.cause == "window_hold"
    assert round(hang.seconds, 1) == round(34.4 - (26.1 - 1.8), 1)  # from 24.3 s


def test_a_sources_first_update_held_from_its_speechs_start_is_a_hang() -> None:
    """polyglotic-hq 566: report 40f40850's system source (timings only).
    Its first update in the trace, from speech that began at 268.9 s, was
    held under the mouse until 291.0 s with the 10 after it - 20.8 s from
    the sound to the screen - and the trace found no hang: a source's first
    update had no update before it to measure from. It's measured from its
    speech's start."""
    held = [
        update(n, 270.2 + n, 291.0, "system", audio=1.32, held="mouse", windowed=291.0)
        for n in range(11)
    ]
    found = summarise(held)
    [hang] = found.hangs
    assert (hang.source, hang.cause, hang.seq) == ("system", "window_hold", 0)
    assert round(hang.seconds, 1) == round(291.0 - (270.2 - 1.32), 1)  # 22.1 s


def test_a_sources_first_update_nothing_held_is_no_hang() -> None:
    """566: a first update shown at once is the caption mode's schedule or
    the speech's length - Steady's whole sentence, a long first live update
    - not a hang, as before. Only something holding it makes one."""
    found = summarise(
        [
            update(1, 10.0, 10.2, audio=6.0),  # nothing asked for 6 s
            update(2, 13.0, 13.2, "call", audio=4.0),  # nor for 4 s here
        ]
    )
    assert found.hangs == []
    slow = update(3, 20.0, 23.5, "mic", audio=1.0)  # the window kept it 3.3 s
    assert [h.cause for h in summarise([slow]).hangs] == ["window_hold"]


def test_nothing_asked_in_between_is_not_put_down_to_a_segment() -> None:
    """The speech paused (shorter than the hangover): no update was asked
    for 2.5 s, and the next was quick."""
    found = summarise(
        [update(1, 10.0, 10.2, audio=1.0), update(2, 12.6, 12.8, audio=3.6)]
    )
    assert [h.cause for h in found.hangs] == ["not_asked"]


def test_an_update_dropped_in_between_is_the_cause() -> None:
    dropped = update(2, 10.5, 0.0, end="unanswered:overtaken_waiting")
    found = summarise([update(1, 10.0, 10.2), dropped, update(3, 10.6, 13.0)])
    assert [h.cause for h in found.hangs] == ["dropped"]
    assert found.drops["overtaken_waiting"] == 1


def test_a_gap_while_nobody_spoke_is_no_hang() -> None:
    """The next caption's speech started after the last was shown."""
    found = summarise(
        [update(1, 10.0, 10.2, audio=1.0), update(2, 15.0, 15.2, audio=1.0)]
    )
    assert found.hangs == []


def test_each_segments_values_are_sampled_past_the_cap() -> None:
    found = Summary()
    for n in range(SAMPLES_KEPT + 500):
        found.add(update(n, 10.0 + n * 0.5, 10.2 + n * 0.5))
    assert len(found.by_segment["total"]) == SAMPLES_KEPT
    assert found.shown == SAMPLES_KEPT + 500


def test_the_usage_statistics_are_the_tracking_plans_properties() -> None:
    records = [update(n, 10.0 + n * 0.5, 10.2 + n * 0.5) for n in range(4)]
    records.append(update(9, 12.0, 15.5, held="mouse", windowed=15.49))
    props = usage_properties(summarise(records), stalls=3)
    assert set(props) <= PLAN
    assert props["hangs"] == 1 and props["hangs_window_hold"] == 1
    assert props["interface_stalls"] == 3 and props["held_mouse"] == 1
    assert all(isinstance(v, int) for v in props.values())


def test_a_sessions_timelines_are_its_own() -> None:
    now = [99.0]
    tracer = Tracer(clock=lambda: now[0])
    timelines = SessionTimelines(tracer)
    tracer.stalled(80)  # before the session: not its own
    now[0] = 100.0
    timelines.start()
    now[0] = 101.0
    tracer.stalled(120)
    for listener in list(tracer._listeners):  # what the tracer tells it
        listener(update(1, 100.5, 100.7))
    now[0] = 160.0
    timelines.stop()
    for listener in list(tracer._listeners):
        listener(update(2, 150.0, 150.2))
    assert timelines.summary.updates == 1
    assert timelines.stalls() == 1
    assert timelines.seconds() == 60.0


def test_a_compact_row_holds_the_whole_record() -> None:
    record = update(7, 10.0, 10.2, held="gap")
    again = expand(json.loads(json.dumps(compact(record))))
    assert (
        again["seq"] == 7 and again["held"] == "gap" and again["srv"] == record["srv"]
    )
    assert {k: round(v, 3) for k, v in again["t"].items()} == {
        k: round(v, 3) for k, v in record["t"].items()
    }


def test_a_reports_timelines_keep_to_their_size_newest_first() -> None:
    records = [update(n, 10.0 + n * 0.5, 10.2 + n * 0.5) for n in range(200)]
    text = report_text(records, limit=4000)
    assert len(text) <= 4000
    rows = [json.loads(line) for line in text.splitlines() if line.startswith("[")]
    assert rows[-1][0] == 199  # the newest kept
    assert "left out" in text


# -- a paced mode's own pace (polyglotic-hq 551) -----------------------------------


def paced(
    seq: int, captured: float, released: float, shown: float, audio: float = 1.32
) -> dict[str, Any]:
    """A live update Steady's playout let out at `released` (its pace
    1.75 s), shown at `shown`."""
    found = update(seq, captured, shown, audio=audio, windowed=shown - 0.005)
    found["t"]["released"] = released
    found["pace"] = 1.75
    return found


def test_steadys_pace_is_a_segment_of_its_own_not_a_windows_hold() -> None:
    parts = segments(paced(1, 10.0, 10.81, 10.82))
    assert round(parts["pace"]) == 660  # applied at 10.15, let out at 10.81
    assert round(parts["window_hold"]) == 5
    unpaced = segments(update(2, 10.0, 10.82, windowed=10.815))
    assert "pace" not in unpaced and round(unpaced["window_hold"]) == 665


def test_an_utterances_start_in_steady_is_no_hang() -> None:
    """548's traces (2026-11-20): every utterance's first word showed 2.0-
    2.8 s after its speech began - Steady's 1.75 s and the word's own
    moment - and each was a hang, of the window's or "not asked". A hang
    counts only what's beyond the pace."""
    before = update(0, 20.0, 20.3, audio=2.0)
    first = paced(1, 25.32, 26.11, 26.12)  # its speech began at 24.0
    found = summarise([before, first])
    assert found.hangs == []
    assert summarise([before, {**first, "pace": None}]).hangs != []  # as before 551


def test_a_hang_beyond_the_pace_is_never_put_down_to_it() -> None:
    """Nothing new for 3.5 s past the pace: a hang, its cause what held the
    update beyond its pace - here the network - not the pace."""
    before = update(0, 20.0, 20.3, audio=2.0)
    late = paced(1, 25.32, 30.2, 30.21)  # speech began at 24.0, shown at 30.21
    late["t"]["received"] = late["t"]["sent"] + 1.2
    for stage in ("handed", "applied"):
        late["t"][stage] += 1.2
    found = summarise([before, late])
    [hang] = found.hangs
    assert round(hang.seconds, 2) == round(30.21 - (24.0 + 1.75), 2)
    assert hang.cause == "network"
    assert "hangs_pace" not in usage_properties(found, stalls=0)


def test_a_paced_record_keeps_its_pace_in_a_report() -> None:
    record = paced(4, 10.0, 10.81, 10.82)
    again = expand(json.loads(json.dumps(compact(record))))
    assert again["pace"] == 1.75
    assert round(again["t"]["released"], 3) == 10.81


def test_an_older_apps_report_rows_read_back() -> None:
    """A problem report from an app before 551: no `released` among its
    stages' offsets, no pace on its rows."""
    stages = [s for s in APP_STAGES if s != "released"]
    offsets = [0, 0, 10, 20, 30, 40, 50, 140, 145, 150, 195, 200]
    assert len(offsets) == len(stages)
    row = [3, "c1", "live", 0, "video", 1.0, "painted", None, 10.0, offsets, {}]
    again = expand(row)
    assert "released" not in again["t"] and "pace" not in again
    assert round(again["t"]["windowed"], 3) == 10.195
    assert round(again["t"]["painted"], 3) == 10.2


def test_a_reports_note_of_what_was_left_out_fits_in_its_size_too() -> None:
    """The note saying how many were left out was added after the rows had
    filled the room: up to its own length over (found by polyglotic-hq 549,
    whose longer first line made the test above fail)."""
    records = [update(n, 10.0 + n * 0.5, 10.2 + n * 0.5) for n in range(200)]
    for limit in range(3000, 3300):
        text = report_text(records, limit=limit)
        assert len(text) <= limit, limit
        kept = sum(1 for line in text.splitlines() if line.startswith("["))
        assert f"# the oldest {200 - kept} left out (size)" in text


# -- sound without speech (polyglotic-hq 549, decision 0256) -------------------


def _stretch(
    began: float,
    ended: float,
    end: str = "speech",
    resets: int = 2,
    after: float | None = 0.4,
) -> dict[str, Any]:
    return Unheard("video", began, ended, (-40, -30, -24), resets, after, end).as_json()


def test_a_stretch_of_sound_without_speech_is_a_hang_of_its_own() -> None:
    """Sound went on for 28 s and nothing was heard as speech: the trace's
    updates alone show no hang (the next speech began after it); the
    stretch is one, put down to sound_unheard."""
    records = [update(n, 10.0 + n * 0.5, 10.2 + n * 0.5) for n in range(4)]
    records.append(_stretch(12.0, 40.2))
    records.append(update(9, 40.5, 40.7, audio=0.5))
    found = summarise(records)
    assert found.updates == 5  # the stretch isn't an update
    assert [(h.cause, round(h.seconds, 1)) for h in found.hangs] == [
        ("sound_unheard", 28.2)
    ]
    assert found.unheard.stretches == 1 and found.unheard.with_reset == 1
    assert found.unheard.heard_after_reset == 1
    props = usage_properties(found, stalls=0)
    assert set(props) <= PLAN
    assert props["hangs"] == 1 and props["hangs_sound_unheard"] == 1
    assert summarise(records[:4] + records[5:]).hangs == []  # without it: none


def test_heard_after_the_reset_is_speech_within_a_second_of_it() -> None:
    found = summarise(
        [
            _stretch(10.0, 20.0, after=2.5),  # heard, but long after the reset
            _stretch(30.0, 40.0, end="quiet", after=0.2),  # the sound stopped
            _stretch(50.0, 60.0, resets=0, after=None),  # no reset in it
        ]
    )
    assert found.unheard.stretches == 3 and found.unheard.with_reset == 2
    assert found.unheard.heard_after_reset == 0
    assert found.unheard.longest == pytest.approx(10.0)


def test_a_problem_report_carries_the_stretches_and_reads_them_back() -> None:
    records = [
        update(1, 10.0, 10.2),
        _stretch(12.0, 40.2),
        _stretch(41.0, 47.0, end="open", resets=1, after=None),
    ]
    text = report_text(records, limit=4000)
    assert "sound unheard 2 over 3 s" in text
    rows = [json.loads(line) for line in text.splitlines() if line.startswith("[")]
    assert rows[1][0] == "sound_unheard"
    assert [expand(row) for row in rows[1:]] == records[1:]
    assert compact(expand(rows[1])) == rows[1]


def test_a_sessions_stretches_are_its_own_and_one_going_on_counts_at_its_end() -> None:
    now = [99.0]
    tracer = Tracer(clock=lambda: now[0])
    tracer.unheard(1, Unheard("video", 80.0, 95.0, (-40, -30, -24), 2, 1.5, "quiet"))
    timelines = SessionTimelines(tracer)
    now[0] = 100.0
    timelines.start()
    tracer.unheard(2, Unheard("video", 101.0, 110.0, (-40, -30, -24), 1, 0.2, "speech"))
    tracer.sounding(3, Unheard("game", 90.0, 130.0, (-40, -30, -24), 7, 3.0, "open"))
    now[0] = 131.0
    timelines.stop()
    found = timelines.summary
    assert found.updates == 0 and found.unheard.stretches == 2
    assert sorted(round(h.seconds, 1) for h in found.hangs) == [
        9.0,
        30.0,
    ]  # from its start
    assert usage_properties(found, stalls=0)["hangs_sound_unheard"] == 2
