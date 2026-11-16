"""What the app writes to its log file, as the app sets it up (start_logging):
no caption, translation, looked-up word or token reaches it - not in a
message, not in an exception's text, not in a dropped message's error
(polyglotic-hq project 081; CLAUDE.md, Privacy). Canary strings stand in
for real text."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fake_server import FakeServer, wait_until
from tests.test_protocol import example
from tests.test_session import Harness, answering, finished, live

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.main import CAPTION_LOG, CAPTION_LOG_FILE, start_logging

CANARY = "CANARY-caption-zebra"
TRANSLATION = "CANARY-translation-quokka"
WORD = "CANARY-word-lookup"
TOKEN = "pgd_CANARY0TOKEN0" + "z" * 27


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    captions = logging.getLogger(CAPTION_LOG)
    start_logging(tmp_path)
    yield tmp_path / "logs" / "polyglotic.log"
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    for handler in list(captions.handlers):  # the caption log's own file
        captions.removeHandler(handler)
        handler.close()
    captions.propagate = True


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def written(file: Path) -> str:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return file.read_text("utf-8")


def test_an_exception_is_logged_as_its_type_and_place_only(log_file: Path) -> None:
    log = logging.getLogger("polyglotic_desktop.test")
    try:
        raise ValueError(f"{CANARY} {TRANSLATION} {WORD} {TOKEN}")
    except ValueError:
        log.exception("it failed")
    text = written(log_file)
    assert "it failed" in text
    assert "ValueError" in text
    assert "Traceback" not in text
    for secret in (CANARY, TRANSLATION, WORD, TOKEN):
        assert secret not in text


def test_a_message_the_server_sent_wrongly_is_dropped_without_its_values(
    log_file: Path,
) -> None:
    bad = example("caption_update.finished")
    bad["clauses"] = [{"original": CANARY, "translations": {"zh": TRANSLATION}}]
    bad["processing_ms"] = f"not a number {WORD}"
    with pytest.raises(protocol.ProtocolError) as raised:
        protocol.decode(json.dumps(bad))
    logging.getLogger("polyglotic_desktop.connection.session").warning(
        "a message from the server was dropped: %s", raised.value
    )
    text = written(log_file)
    assert "dropped" in text
    for secret in (CANARY, TRANSLATION, WORD):
        assert secret not in text


def test_a_listening_session_logs_no_caption_or_translation(
    server: FakeServer, log_file: Path
) -> None:
    with Harness(server) as app:
        wait_until(lambda: app.listener.listening(1), timeout=5)
        app.speech.put(finished("c1"), b"OggS audio")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
        server.send_to_all(
            {
                "type": "caption_update",
                "caption_id": "c999",
                "source_id": "app",
                "kind": "finished",
                "language": "en",
                "languages_heard": ["en"],
                "clauses": [{"original": CANARY, "translations": {"zh": TRANSLATION}}],
                "replaces": [],
                "processing_ms": "bad",
            }
        )
        wait_until(lambda: "dropped" in written(log_file))
    text = written(log_file)
    assert "listening" in text
    for secret in (CANARY, TRANSLATION, WORD, TOKEN):
        assert secret not in text


def test_the_caption_log_has_each_captions_events_and_none_of_its_text(
    server: FakeServer, log_file: Path
) -> None:
    """polyglotic-hq 271: a line per caption event, in a file of its own -
    ids, sizes and times, and nothing that was said."""

    def caption(header: protocol.SpeechHeader) -> dict[str, object]:
        return {
            "type": "caption_update",
            "caption_id": header.caption_id,
            "source_id": header.source.id,
            "kind": header.kind,
            "language": "en",
            "languages_heard": ["en"],
            "clauses": [{"original": CANARY, "translations": {"zh": TRANSLATION}}],
            "replaces": [],
            "processing_ms": 41,
        }

    server.script = [answering(lambda header: [caption(header)])]
    with Harness(server) as app:
        wait_until(lambda: app.listener.listening(1), timeout=5)
        app.speech.put(live("c1"), b"OggS audio")
        app.speech.put(finished("c1"), b"OggS audio")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 2)
        update = app.listener.captions[-1]
    assert update.times is not None and update.processing_ms == 41

    assert update.times.speech_start < update.times.speech_end
    assert update.times.sent <= update.times.received
    for handler in logging.getLogger(CAPTION_LOG).handlers:
        handler.flush()
    captions = (log_file.parent / CAPTION_LOG_FILE).read_text("utf-8")
    lines = [line.split(" ", 2)[2] for line in captions.splitlines()]
    sent = [line for line in lines if line.startswith("caption sent id=c1 ")][-1]
    assert "kind=finished" in sent and "source=" in sent and "audio_s=2.00" in sent
    answered = [line for line in lines if line.startswith("caption answered")][-1]

    assert f"chars={len(CANARY)} clauses=1 translated=1 server_ms=41" in answered
    assert "round_trip_ms=" in answered and "since_end_ms=" in answered
    assert "caption" not in written(log_file)  # none of it in the app's own log
    for secret in (CANARY, TRANSLATION, WORD, TOKEN):
        assert secret not in captions
