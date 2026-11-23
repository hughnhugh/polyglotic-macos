"""The caption timelines' viewer (tools.trace; polyglotic-hq 543): a page from a
trace file, a logs folder or the older caption log, and a summary line."""

import json
from pathlib import Path

import pytest
from tests.test_trace_summary import update
from tools.trace.__main__ import main
from tools.trace.read import load

CAPTION_LOG = """\
2026-11-20 15:50:56,682 caption sent id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=live section=0 source=system mode=live audio_s=1.87 bytes=5936 since_end_ms=37
2026-11-20 15:50:56,737 caption answered id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=live chars=21 clauses=1 translated=0 server_ms=43 round_trip_ms=55 since_end_ms=92 since_start_ms=1964
2026-11-20 15:50:56,742 caption shown id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=live since_start_ms=1968 since_end_ms=96 interface_ms=4
2026-11-20 15:50:58,835 caption sent id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=finished source=system mode=live audio_s=3.73 bytes=10994 since_end_ms=334
2026-11-20 15:50:59,071 caption answered id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=finished chars=40 clauses=1 translated=1 server_ms=222 round_trip_ms=236 since_end_ms=569 since_start_ms=4297
2026-11-20 15:50:59,074 caption shown id=6f476f95-024b-4bd5-8c1c-1217907685b4 kind=finished since_start_ms=4301 since_end_ms=573 interface_ms=4
"""


def _trace_file(folder: Path) -> Path:
    records = [update(n, 10.0 + n * 0.5, 10.2 + n * 0.5) for n in range(4)]
    records += [
        update(n, 10.0 + n * 0.5, 15.2, held="mouse", windowed=15.19)
        for n in range(4, 10)
    ]
    path = folder / "trace.jsonl"
    path.write_text(
        "".join(
            f"2026-11-20 16:00:{n:02d},000 {json.dumps(r)}\n"
            for n, r in enumerate(records)
        ),
        "utf-8",
    )
    return path


def test_the_page_from_a_trace_file_shows_the_hang_and_its_cause(
    tmp_path: Path,
) -> None:
    _trace_file(tmp_path)
    out = tmp_path / "page.html"
    assert main([str(tmp_path), "--out", str(out)]) == 0
    page = out.read_text("utf-8")
    assert "hang " in page and "window_hold" in page
    assert page.count("<svg") >= 3  # the overview, the hang, the last 30 s
    assert "<title>Caption timelines</title>" in page


def test_the_summary_is_one_line_and_its_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _trace_file(tmp_path)
    assert main([str(tmp_path), "--summary"]) == 0
    line, numbers = capsys.readouterr().out.strip().splitlines()
    assert line.startswith("10 updates, 10 shown; hangs 1 (window_hold 1)")
    assert json.loads(numbers)["hang_causes"] == {"window_hold": 1}


def test_the_older_caption_log_is_read_as_far_as_it_goes(tmp_path: Path) -> None:
    (tmp_path / "captions.log").write_text(CAPTION_LOG, "utf-8")
    records, kind = load(tmp_path)
    assert kind == "caption log"
    assert [r["end"] for r in records] == ["applied", "applied"]
    live = records[0]
    assert round((live["t"]["sent"] - live["t"]["captured"]) * 1000) == 37
    assert live["srv"] == {"processing": 43}
    out = tmp_path / "page.html"
    assert main([str(tmp_path), "--out", str(out)]) == 0
    assert "older caption log" in out.read_text("utf-8")


def test_steadys_pace_is_drawn_as_its_own_neutral_span() -> None:
    """551: the playout's wait is the mode's pace (neutral, as the pause),
    not the window's hold; a mode without one has no `released` between
    applied and windowed, and its hold is still the window's colour."""
    from tests.test_trace_summary import paced
    from tools.trace.page import spans

    drawn = {
        group: round((b - a) * 1000)
        for a, b, group in spans(paced(1, 10.0, 10.81, 10.82))
    }
    assert drawn["gc"] == 660  # applied at 10.15, let out at 10.81
    assert "gu" not in drawn
    unpaced = spans(update(2, 10.0, 10.82, windowed=10.815))
    assert "gc" not in {g for *_, g in unpaced} and "gu" not in {g for *_, g in unpaced}


def test_the_page_has_a_lane_for_sound_without_speech(tmp_path: Path) -> None:
    """polyglotic-hq 549: a stretch of sound nothing heard as speech is a
    hang put down to sound_unheard, drawn in its source's own lane, with
    its levels and resets on hover; the summary line counts it."""
    from polyglotic_desktop.perf.trace import Unheard

    stretch = Unheard("video", 12.0, 40.2, (-38, -30, -24), 5, 0.4, "speech")
    records = [
        update(1, 10.0, 10.2),
        stretch.as_json(),
        update(2, 40.5, 40.7, audio=0.5),
    ]
    path = tmp_path / "trace.jsonl"
    path.write_text(
        "".join(
            f"2026-11-20 18:03:{n:02d},000 {json.dumps(r)}\n"
            for n, r in enumerate(records)
        ),
        "utf-8",
    )
    out = tmp_path / "page.html"
    assert main([str(path), "--out", str(out)]) == 0
    page = out.read_text("utf-8")
    assert "hang 28.2 s: sound_unheard" in page
    assert 'class="gs"' in page and "no speech heard" in page
    assert "sound without speech 28.2 s (speech)" in page
    assert "-38/-30/-24 dBFS" in page and "forgot its state 5 times" in page
    assert "sound unheard 1 over 3 s" in page
