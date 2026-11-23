from polyglotic_desktop.core.listening.caption_hold import CaptionResults
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM, Source
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory


def request(name: str, start: float, end: float) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(name),
        SpeechKind.FINISHED,
        Source(WHOLE_SYSTEM, SourceCategory.SYSTEM),
        start,
        end,
    )


def finished(name: str, start: float, end: float, words: str) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(name),
        WHOLE_SYSTEM,
        CaptionKind.FINISHED,
        (Clause(words),),
        times=SpeechTimes(start, end, end, end),
    )


def test_caption_hold_waits_for_latest_finish_and_keeps_display_order() -> None:
    results = CaptionResults(WHOLE_SYSTEM)
    first = finished("first", 1, 2, "First draft.")
    joined = finished("first", 1, 3, "First, joined.")
    second = finished("second", 4, 5, "Second.")
    requests = (request("first", 1, 3), request("second", 4, 5))

    for answer in (second, first):
        results.received(answer)
        results.applied(answer)
    assert results.lines(requests) is None

    results.received(joined)
    results.applied(joined)
    assert results.lines(requests) == (joined, second)


def test_caption_hold_uses_one_projected_continuation_and_ignores_other_sources() -> (
    None
):
    results = CaptionResults(WHOLE_SYSTEM)
    first = finished("first", 1, 2, "First.")
    child = finished("child", 2, 4, "First and second.")
    shown = CaptionUpdate(
        first.caption_id,
        first.source_id,
        CaptionKind.FINISHED,
        child.clauses,
        replaces=(child.caption_id,),
        times=child.times,
        display_member=child.caption_id,
    )
    wrong_source = CaptionUpdate(child.caption_id, MIC, CaptionKind.FINISHED)
    results.received(wrong_source)
    results.applied(wrong_source)
    results.received(first)
    results.applied(first)
    results.received(child)
    results.applied(shown)

    assert results.lines((request("child", 2, 4),)) == (shown,)
    assert results.lines((request("first", 1, 2), request("child", 2, 4))) == (shown,)


def test_caption_hold_resolves_a_dropped_finish_to_the_line_left_on_screen() -> None:
    results = CaptionResults(WHOLE_SYSTEM)
    line = CaptionUpdate(
        CaptionId("caption"), WHOLE_SYSTEM, CaptionKind.FINISHED, (Clause("Shown."),)
    )
    results.applied(line)
    results.dropped(line.caption_id)

    assert results.lines((request("caption", 1, 2),)) == (line,)
    assert results.lines((request("outside", 3, 4),)) is None
