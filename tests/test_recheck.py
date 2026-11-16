""" "Looks wrong?" (project 101): what differs between two versions of a line,
how a check came out for the count, and the transcript keeping the better
line. Domain level, no Qt."""

from datetime import UTC, datetime

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech, RecentSpeech
from polyglotic_desktop.core.listening.recheck import (
    FlagOutcome,
    RecheckOutcome,
    RecheckResult,
    differences,
    flag_outcome,
    same_line,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ports.capture import SourceCategory

EN = Language("en")
SMALL = (Clause("Mình đi ăn chước nha.", {EN: "We'll go eat chước."}),)
BEST = (Clause("Mình đi ăn trước nha.", {EN: "Let's go eat first."}),)


def boxed(text: str, spans: list[tuple[int, int]]) -> list[str]:
    return [text[a:b] for a, b in spans]


def test_differences_are_whole_words_in_spaced_languages() -> None:
    before, after = "Mình đi ăn chước nha.", "Mình đi ăn trước nha."
    mine, theirs = differences(before, after)
    assert boxed(before, mine) == ["chước"] and boxed(after, theirs) == ["trước"]
    before, after = "We'll go eat chước.", "Let's go eat first."
    mine, theirs = differences(before, after)
    assert boxed(before, mine) == ["We'll", "chước"]  # "We" + "ll", joined
    assert boxed(after, theirs) == ["Let's", "first"]


def test_differences_are_characters_in_chinese() -> None:
    before, after = "这个操做有点难。", "这个操作有点难。"
    mine, theirs = differences(before, after)
    assert boxed(before, mine) == ["做"] and boxed(after, theirs) == ["作"]


def test_neighbouring_differences_make_one_box_and_punctuation_alone_none() -> None:
    before, after = "I saw a red car today", "I saw the blue bus today"
    mine, theirs = differences(before, after)
    assert boxed(before, mine) == ["a red car"]
    assert boxed(after, theirs) == ["the blue bus"]
    assert differences("Hello, world.", "Hello world!") == ([], [])
    assert differences("Hello", "hello") == ([], [])  # case isn't a mistake
    mine, theirs = differences("one two", "one two three")
    assert mine == [] and boxed("one two three", theirs) == ["three"]


def test_the_same_line_is_the_same_words_and_translations() -> None:
    assert same_line(SMALL, SMALL)
    assert not same_line(SMALL, BEST)
    same_words = (Clause(SMALL[0].original, {EN: "Something else."}),)
    assert not same_line(SMALL, same_words)
    # split differently into clauses, or a target only one has: still the same
    split = (Clause("Mình đi ăn"), Clause("chước nha."))
    assert same_line((Clause("Mình đi ăn chước nha."),), split)
    assert same_line(SMALL, (Clause(SMALL[0].original),))


def result(outcome: RecheckOutcome, clauses: tuple[Clause, ...] = ()) -> RecheckResult:
    return RecheckResult(CaptionId("c1"), outcome, clauses)


def test_how_a_check_came_out_for_the_count() -> None:
    checked = RecheckOutcome.CHECKED
    assert flag_outcome(SMALL, result(checked, BEST)) is FlagOutcome.DIFFERS
    assert flag_outcome(SMALL, result(checked, SMALL)) is FlagOutcome.SAME
    assert flag_outcome(SMALL, result(checked)) is FlagOutcome.NO_WORDS
    for outcome, counted in (
        (RecheckOutcome.BEST_UNAVAILABLE, FlagOutcome.BEST_UNAVAILABLE),
        (RecheckOutcome.TRY_LATER, FlagOutcome.TRY_LATER),
        (RecheckOutcome.NOT_HELD, FlagOutcome.NOT_HELD),
        (RecheckOutcome.FAILED, FlagOutcome.FAILED),
        (RecheckOutcome.NOT_LISTENING, FlagOutcome.FAILED),
        (RecheckOutcome.NO_ANSWER, FlagOutcome.FAILED),
    ):
        assert flag_outcome(SMALL, result(outcome)) is counted


def finished(caption: str, clauses: tuple[Clause, ...]) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption),
        SourceId("source-1"),
        CaptionKind.FINISHED,
        clauses,
        Language("vi"),
        (Language("vi"),),
    )


def test_the_transcript_keeps_the_best_models_line_in_its_place() -> None:
    history = CaptionHistory(clock=lambda: datetime(2026, 11, 6, tzinfo=UTC))
    history.apply(finished("c0", (Clause("Hôm nay trời nóng quá."),)))
    first = history.apply(finished("c1", SMALL))
    assert first is not None
    version = history.version
    checked = history.use_checked(CaptionId("c1"), BEST, Language("vi"), ())
    assert checked is not None and history.version == version + 1
    assert checked.checked and checked.first_shown == SMALL
    assert checked.clauses == BEST and checked.key == first.key
    assert [c.caption_id for c in history.captions] == ["c0", "c1"]
    assert history.caption(CaptionId("c1")) == checked
    # nothing to put in place: gone, live, or a version with no words
    assert history.use_checked(CaptionId("gone"), BEST, None, ()) is None
    assert history.use_checked(CaptionId("c0"), (), None, ()) is None
    live = CaptionUpdate(CaptionId("c2"), SourceId("s"), CaptionKind.LIVE, SMALL)
    history.apply(live)
    assert history.use_checked(CaptionId("c2"), BEST, None, ()) is None
    # a later join of the line replaces it as any finished update does
    joined = history.apply(finished("c1", (Clause("Mình đi ăn trước nha, đi."),)))
    assert joined is not None and not joined.checked


class NoDetector:
    def feed(self, start: float, audio: object) -> list[object]:
        return []


def test_the_pipeline_hands_out_held_speech_by_caption_id() -> None:
    pipeline = SpeechPipeline(
        NoDetector,  # type: ignore[arg-type]
        timing=None,  # type: ignore[arg-type]
        recent=RecentSpeech(lambda: 4.0),
    )
    held = HeldSpeech(
        CaptionId("c1"), SourceId("app"), SourceCategory.VIDEO, 1.0, 3.0, b"OggS"
    )
    pipeline.recent.add(held)
    assert pipeline.get(CaptionId("c1")) == held
    assert pipeline.get(CaptionId("c2")) is None  # not held (any more)
    pipeline.forget_recent()
    assert pipeline.get(CaptionId("c1")) is None
