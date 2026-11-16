"""Each caption's delay and the caption log's lines (core.listening.delays)."""

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.delays import (
    CaptionDelay,
    answered_fields,
    delay,
    line,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

TIMES = SpeechTimes(speech_start=10.0, speech_end=12.5, sent=13.4, received=13.9)
SAID = "words nobody may log"


def update(**changes: object) -> CaptionUpdate:
    fields: dict[str, object] = {
        "caption_id": CaptionId("c1"),
        "source_id": SourceId("app"),
        "kind": CaptionKind.FINISHED,
        "clauses": (
            Clause(SAID, {Language("zh"): "translated"}),
            Clause("more"),
        ),
        "processing_ms": 400,
        "times": TIMES,
    }
    return CaptionUpdate(**{**fields, **changes})  # type: ignore[arg-type]


def test_a_captions_delay_from_its_speechs_start_and_end_and_the_servers_share() -> (
    None
):
    found = delay(update(), shown=14.0)
    assert found is not None
    assert (round(found.from_start, 3), round(found.from_end, 3)) == (4.0, 1.5)
    assert found.server == 0.4
    assert delay(update(processing_ms=None), 14.0) == CaptionDelay(
        found.from_start, found.from_end, None
    )


def test_an_update_whose_speech_this_session_didnt_send_has_no_delay() -> None:
    assert delay(update(times=None), shown=14.0) is None


def test_a_line_is_the_event_the_id_and_the_fields_given() -> None:
    said = line("sent", "c1", kind="live", section=0, mode=None, bytes=207)
    assert said == "caption sent id=c1 kind=live section=0 bytes=207"


def test_an_answers_fields_are_counts_and_milliseconds_never_text() -> None:
    fields = answered_fields(update(), TIMES)
    assert fields == {
        "kind": "finished",
        "chars": len(SAID) + len("more"),
        "clauses": 2,
        "translated": 1,
        "server_ms": 400,
        "round_trip_ms": 500,
        "since_end_ms": 1400,
        "since_start_ms": 3900,
    }
    assert SAID not in line("answered", "c1", **fields)
