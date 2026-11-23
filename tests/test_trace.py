"""Each caption update's timeline, from the sound to the screen (perf.trace; polyglotic-hq 543).

The tracer at the domain level (stages marked from several threads, how a
record ends, what's kept and written); then a listening session numbering
its frames and reading the server's trace; then where the timelines go -
the rolling file on a PC that asked for them, and a problem report.
"""

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fake_server import FakeServer, caption_for, wait_until
from tests.test_session import Harness, live
from websockets.asyncio.server import ServerConnection

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.core.listening.timing import TranscriptionRequest
from polyglotic_desktop.perf import trace
from polyglotic_desktop.perf.trace import (
    APP_STAGES,
    DONE_AFTER_SEC,
    TRACE_LOG,
    UNHEARD,
    Tracer,
    Unheard,
    speech_key,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def tracer(clock: Clock) -> Iterator[Tracer]:
    made = Tracer(clock=clock)
    before = trace.use(made)
    yield made
    trace.use(before)


def _through(
    tracer: Tracer, clock: Clock, caption: str = "c1-aaaaaaaa", end: float = 99.9
) -> int:
    """A live update from its decision to its answer; its number."""
    key = speech_key(caption, "live", 0, end)
    tracer.decided(key, delivered=100.01, detected=100.02, heard=end)
    tracer.encoded(key, 100.03)
    seq = tracer.sending(key, "video", 1.5, taken=100.04)
    tracer.mark(seq, "sent", 100.05)
    tracer.answered(
        seq, 100.30, {"waited": 20, "queued": 2, "server": 200, "speech_model": 150}
    )
    return seq


def test_an_update_is_timed_from_the_sound_to_the_screen(
    tracer: Tracer, clock: Clock
) -> None:
    seq = _through(tracer, clock)
    tracer.mark(seq, "handed", 100.31)
    tracer.mark(seq, "applied", 100.32)
    tracer.released(seq, 1.75, 100.325)  # a paced mode's playout let it out
    tracer.windowed(seq, 100.33)
    tracer.painted(100.35)
    clock.now = 100.4
    [done] = tracer.recent()
    assert done["end"] == "painted" and done["pace"] == 1.75
    assert done["seq"] == seq and done["cap"] == "c1-aaaaa"  # 8 characters
    assert [s for s in APP_STAGES if s in done["t"]] == list(APP_STAGES)
    assert done["srv"] == {
        "waited": 20,
        "queued": 2,
        "server": 200,
        "speech_model": 150,
    }
    assert set(done) <= {
        "seq",
        "cap",
        "kind",
        "sec",
        "src",
        "audio",
        "t",
        "end",
        "srv",
        "held",
        "pace",
    }


def test_a_decision_overtaken_before_the_send_loop_took_it_ends_there(
    tracer: Tracer, clock: Clock
) -> None:
    first = speech_key("c1", "live", 0, 99.0)
    second = speech_key("c1", "live", 0, 99.5)
    tracer.decided(first, 99.01, 99.02, 99.0)
    tracer.decided(second, 99.51, 99.52, 99.5)
    tracer.sending(second, "video", 1.0, taken=99.6)  # latest wins in the pipeline
    [done] = tracer.recent()
    assert done["end"] == "overtaken_in_app"
    assert done["seq"] is None


def test_the_servers_unanswered_updates_end_with_its_reason(
    tracer: Tracer, clock: Clock
) -> None:
    first = _through(tracer, clock, end=99.0)
    second = _through(tracer, clock, end=99.5)
    tracer.answered(second, 100.6, {"server": 90}, {first: "overtaken_waiting"})
    ended = {r["seq"]: r["end"] for r in tracer.recent()}
    assert ended == {first: "unanswered:overtaken_waiting"}


def test_held_by_the_mouse_shows_when_the_window_lets_it_in(
    tracer: Tracer, clock: Clock
) -> None:
    seq = _through(tracer, clock)
    tracer.mark(seq, "applied", 100.32)
    tracer.held(seq, "mouse")
    tracer.painted(100.4)  # a paint while it waits doesn't show it
    tracer.windowed(seq, 103.5)
    tracer.painted(103.52)
    clock.now = 104.0
    [done] = tracer.recent()
    assert done["held"] == "mouse"
    assert done["t"]["painted"] == 103.52


def test_a_record_nothing_marks_is_done_as_it_stands(
    tracer: Tracer, clock: Clock
) -> None:
    seq = _through(tracer, clock)
    tracer.mark(seq, "applied", 100.32)  # no window shows its source
    clock.now = 100.32 + DONE_AFTER_SEC + 1
    [done] = tracer.recent()
    assert done["end"] == "applied"
    lost = tracer.sending(
        speech_key("c2", "finished", None, 1.0), "mic", 1.0, clock.now
    )
    clock.now += DONE_AFTER_SEC + 1
    assert [r["end"] for r in tracer.recent() if r["seq"] == lost] == ["lost"]


def test_done_records_are_kept_for_five_minutes_only(
    tracer: Tracer, clock: Clock
) -> None:
    _through(tracer, clock)
    tracer.flush()
    assert len(tracer.recent()) == 1
    clock.now += tracer.keep_sec + 1
    assert tracer.recent() == []


def test_listeners_hear_each_done_record(tracer: Tracer, clock: Clock) -> None:
    heard: list[dict[str, Any]] = []
    tracer.listen(heard.append)
    _through(tracer, clock)
    tracer.flush()
    tracer.unlisten(heard.append)
    _through(tracer, clock)
    tracer.flush()
    assert len(heard) == 1 and heard[0]["end"] == "received"


class Lines(logging.Handler):
    """The trace logger's lines, caught on the logger itself - whatever
    other tests left on the root logger (Linux CI's whole run saw each
    line twice through caplog there)."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def test_the_detail_is_written_only_when_asked(tracer: Tracer, clock: Clock) -> None:
    logger = logging.getLogger(TRACE_LOG)
    caught = Lines()
    before = (logger.level, logger.propagate)
    logger.addHandler(caught)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        _through(tracer, clock)
        tracer.flush()
        assert caught.lines == []
        tracer.detail = True
        _through(tracer, clock)
        tracer.flush()
    finally:
        logger.removeHandler(caught)
        logger.setLevel(before[0])
        logger.propagate = before[1]
    [line] = caught.lines
    assert json.loads(line)["end"] == "received"


# --- sound without speech (polyglotic-hq 549, decision 0256) -----------------


def _going(ended: float = 99.0) -> Unheard:
    return Unheard("video", 90.0, ended, (-40, -30, -24), 1, 4.0, "open")


def test_sound_without_speech_is_given_as_it_stands_then_done(
    tracer: Tracer, clock: Clock
) -> None:
    """A problem report sent during a long stretch has it as it stands;
    once it ends it's a done record like any other: kept, heard by the
    listeners, written to the trace file when asked."""
    heard: list[dict[str, Any]] = []
    tracer.listen(heard.append)
    logger = logging.getLogger(TRACE_LOG)
    caught = Lines()
    before = (logger.level, logger.propagate)
    logger.addHandler(caught)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    tracer.detail = True
    try:
        tracer.sounding(7, _going())
        [now] = tracer.recent()
        assert now["kind"] == UNHEARD and now["end"] == "open" and heard == []
        tracer.sounding(7, _going(99.5))  # the same stretch, later
        assert [r["t"]["ended"] for r in tracer.recent()] == [99.5]
        ended = Unheard("video", 90.0, 100.0, (-40, -30, -24), 2, 0.3, "speech")
        tracer.unheard(7, ended)
    finally:
        logger.removeHandler(caught)
        logger.setLevel(before[0])
        logger.propagate = before[1]
    [done] = tracer.recent()
    assert done == ended.as_json() and heard == [done]
    [line] = caught.lines
    assert json.loads(line) == done


def test_a_stretch_given_as_it_stood_and_never_ended_is_forgotten(
    tracer: Tracer, clock: Clock
) -> None:
    """Its source went before it ended (a capture's last callback after
    its stop): it isn't kept going in every report after."""
    tracer.sounding(7, _going())
    clock.now = 99.0 + DONE_AFTER_SEC + 1
    assert tracer.recent() == []


def test_a_problem_reports_log_carries_the_stretches(tmp_path: Path) -> None:
    from tools.trace.read import load

    from polyglotic_desktop.main import log_with_timelines

    made = Tracer(clock=Clock())
    made.unheard(1, Unheard("game", 60.0, 88.2, (-38, -30, -24), 5, 0.4, "speech"))
    made.sounding(2, _going())
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "polyglotic.log").write_text("started\n", "utf-8")
    report = tmp_path / "report-log.txt"
    report.write_text(log_with_timelines(folder, made.recent()) or "", "utf-8")
    records, kind = load(report)
    assert kind == "report"
    assert [(r["kind"], r["src"], r["end"]) for r in records] == [
        (UNHEARD, "game", "speech"),
        (UNHEARD, "video", "open"),
    ]
    assert records[0]["len"] == 28.2 and records[0]["dbfs"] == [-38, -30, -24]


# --- a listening session numbers its frames and reads the server's trace ------


def _traced(header: protocol.SpeechHeader, **trace_fields: Any) -> dict[str, Any]:
    answer = caption_for(header)
    answer["trace"] = {
        "waited_ms": 0,
        "queued": 1,
        "stages_ms": {},
        "server_ms": 5,
        **trace_fields,
    }
    return answer


def test_a_live_updates_round_trip_is_its_own_frames(server: FakeServer) -> None:
    """Bug (polyglotic-hq 543): an answer to a live update was timed from the
    caption's latest live send, so one that waited behind a newer send
    looked quicker than it was. The frame's number, echoed by the server,
    times it from its own send."""
    made = Tracer()
    before = trace.use(made)
    held: list[protocol.SpeechHeader] = []

    async def behaviour(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        async for data in websocket:
            received = server.record(data)
            if not isinstance(received, protocol.SpeechHeader):
                for reply in server.answers(received):
                    await websocket.send(json.dumps(reply))
                continue
            held.append(received)
            if len(held) == 2:  # the first answered only once the second came
                first, second = held
                await websocket.send(json.dumps(_traced(first, seq=first.seq)))
                await websocket.send(
                    json.dumps(_traced(second, seq=second.seq, unanswered=[]))
                )

    server.script = [behaviour]
    try:
        with Harness(server) as app:
            wait_until(app.listener.listening)
            app.speech.put(live("c1"), b"OggS one")
            app.session.speech_ready()
            wait_until(lambda: len(server.speech) == 1)
            time.sleep(0.3)
            later = TranscriptionRequest(
                live("c1").caption_id,
                live("c1").kind,
                live("c1").source,
                10.0,
                11.5,
                section=0,
            )
            app.speech.put(later, b"OggS two")
            app.session.speech_ready()
            wait_until(lambda: len(app.listener.captions) == 2)
            first = app.listener.captions[0]
    finally:
        trace.use(before)
    headers = [h for h, _ in server.speech]
    assert [h.seq for h in headers] == [0, 1]
    assert first.times is not None and first.times.seq == 0
    assert first.times.received - first.times.sent >= 0.3  # from its own send
    done = {r["seq"]: r for r in made.recent()}
    made.flush()
    done = {r["seq"]: r for r in made.recent()}
    assert done[0]["srv"]["server"] == 5 and "sent" in done[0]["t"]


def test_an_older_servers_answers_mark_the_latest_frame_sent(
    server: FakeServer,
) -> None:
    """A server before its decision 0104 doesn't echo the number: its answer
    is taken to answer the caption's latest frame of its kind, as the
    caption log always took it - so the timelines carry on past the send."""

    def answer(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return [caption_for(header)]  # no trace

    from tests.test_session import answering, finished

    made = Tracer()
    before = trace.use(made)
    server.script = [answering(answer)]
    try:
        with Harness(server) as app:
            wait_until(app.listener.listening)
            app.speech.put(live("c1"), b"OggS one")
            app.speech.put(finished("c1"), b"OggS two")
            app.session.speech_ready()
            wait_until(lambda: len(app.listener.captions) == 2)
            updates = list(app.listener.captions)
    finally:
        trace.use(before)
    assert [u.times.seq if u.times else None for u in updates] == [0, 1]
    made.flush()
    done = {r["seq"]: r for r in made.recent()}
    assert "received" in done[1]["t"] and done[1]["srv"] == {"processing": 5}


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


# --- where the timelines go --------------------------------------------------


def test_the_rolling_file_only_on_a_pc_that_asked(tmp_path: Path) -> None:
    from polyglotic_desktop.main import TRACE_DETAIL, start_trace

    made = Tracer()
    before = trace.use(made)
    logger = logging.getLogger(TRACE_LOG)
    handlers = list(logger.handlers)  # whatever other tests left there
    state = (logger.level, logger.propagate)
    try:
        folder = tmp_path / "logs"
        folder.mkdir()
        assert start_trace(tmp_path, folder) is False
        assert made.detail is False and logger.handlers == handlers
        (tmp_path / TRACE_DETAIL).touch()
        assert start_trace(tmp_path, folder) is True
        assert made.detail is True
        _through(made, Clock())
        made.flush()
        for handler in logger.handlers:
            handler.flush()
        [line] = (folder / "trace.jsonl").read_text("utf-8").splitlines()
        stamp, _, record = line.partition(" {")
        assert stamp[:4].isdigit() and json.loads("{" + record)["seq"] == 0
    finally:
        for handler in list(logger.handlers):
            if handler not in handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(state[0])
        logger.propagate = state[1]
        trace.use(before)


def test_a_problem_reports_log_carries_the_last_minutes_timelines(
    tmp_path: Path,
) -> None:
    from tools.trace.read import load

    from polyglotic_desktop.main import log_with_timelines

    made = Tracer(clock=Clock())
    for n in range(5):
        _through(made, Clock(), caption=f"c{n}", end=99.0 + n / 10)
    made.flush()
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "polyglotic.log").write_text(
        "2026-11-20 16:00:00,000 INFO app: started\n", "utf-8"
    )
    text = log_with_timelines(folder, made.recent())
    assert text is not None and text.startswith("2026-11-20 16:00:00,000 INFO")
    report = tmp_path / "report-log.txt"
    report.write_text(text, "utf-8")
    records, kind = load(report)
    assert kind == "report" and len(records) == 5
    assert records[0]["srv"]["server"] == 200
    assert log_with_timelines(folder, []) == (folder / "polyglotic.log").read_text(
        "utf-8"
    )


@pytest.mark.parametrize("usage", [True, False])
def test_a_listening_sessions_timelines_go_with_consent_only(
    server: FakeServer, usage: bool
) -> None:
    """caption_timeline_summarised beside listening_session_ended, only with
    the user's consent to usage statistics: counts and milliseconds."""
    from tests.test_connection import App
    from tests.test_session import SETTINGS, finished

    made = Tracer()
    before = trace.use(made)
    try:
        app = App(server.url)
        app.exchange.choose_consent(usage=usage, crashes=False, exposures=False)
        session = app.connection.start_listening(SETTINGS, app.speech.take)
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS")
        session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
        update = app.listener.captions[0]
        assert update.times is not None
        made.mark(update.times.seq, "applied")  # the caption feed's
        app.connection.stop_listening()
        if usage:
            wait_until(lambda: len(server.app_closes) == 2)  # a sync after it
        else:
            wait_until(lambda: server.app_closes == [1000])
            time.sleep(0.5)
        events = {
            e["name"]: e["props"] for m in server.of_type("usage") for e in m["events"]
        }
        app.connection.close()
    finally:
        trace.use(before)
    if not usage:
        assert events == {}
        return
    props = events["caption_timeline_summarised"]
    assert props["updates"] == 1 and props["shown"] == 1 and props["hangs"] == 0
    assert props["caption_mode"] == "steady" and props["platform"] == "windows"
    assert "total_p50_ms" in props and "listening_seconds" in props


def test_a_session_that_sent_nothing_while_sound_went_unheard_says_so(
    server: FakeServer,
) -> None:
    """polyglotic-hq 549: a session where speech detection heard nothing in
    sound that went on is the one to see - its summary goes, with the hang
    put down to sound_unheard."""
    from tests.test_connection import App
    from tests.test_session import SETTINGS

    made = Tracer()
    before = trace.use(made)
    try:
        app = App(server.url)
        app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
        app.connection.start_listening(SETTINGS, app.speech.take)
        wait_until(app.listener.listening)
        at = time.perf_counter()
        made.unheard(
            1, Unheard("music", at, at + 28.2, (-38, -30, -24), 5, 0.4, "speech")
        )
        app.connection.stop_listening()
        wait_until(lambda: len(server.app_closes) == 2)  # a sync after it
        events = {
            e["name"]: e["props"] for m in server.of_type("usage") for e in m["events"]
        }
        app.connection.close()
    finally:
        trace.use(before)
    props = events["caption_timeline_summarised"]
    assert props["updates"] == 0 and props["hangs"] == 1
    assert props["hangs_sound_unheard"] == 1
