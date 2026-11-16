"""The recent-speech store (core.listening.recent_speech)."""

from polyglotic_desktop.core.listening.recent_speech import HeldSpeech, RecentSpeech
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ports.capture import SourceCategory

A, B = SourceId("a"), SourceId("b")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def held(
    caption: str,
    end: float,
    source: SourceId = A,
    category: SourceCategory = SourceCategory.VIDEO,
    size: int = 100,
) -> HeldSpeech:
    return HeldSpeech(CaptionId(caption), source, category, end - 3.0, end, b"x" * size)


def test_a_finished_caption_is_found_by_id() -> None:
    clock = Clock()
    store = RecentSpeech(clock)
    store.add(held("c1", 999.0, size=7))
    got = store.get(CaptionId("c1"))
    assert got is not None and got.audio == b"x" * 7 and got.source_id == A
    assert (got.start, got.end, got.category) == (996.0, 999.0, SourceCategory.VIDEO)
    assert store.get(CaptionId("nope")) is None


def test_speech_expires_after_two_minutes() -> None:
    clock = Clock()
    store = RecentSpeech(clock)
    store.add(held("c1", 1000.0))
    clock.now = 1119.0
    assert store.get(CaptionId("c1")) is not None
    clock.now = 1121.0
    assert store.get(CaptionId("c1")) is None
    assert store.size() == 0


def test_old_entries_drop_first_and_sources_are_separate() -> None:
    clock = Clock()
    store = RecentSpeech(clock)
    store.add(held("a-old", 1000.0, A))
    store.add(held("b-old", 1000.0, B))
    clock.now = 1100.0
    store.add(held("a-new", 1100.0, A))
    clock.now = 1130.0
    assert store.get(CaptionId("a-old")) is None
    assert store.get(CaptionId("b-old")) is None
    assert store.get(CaptionId("a-new")) is not None
    # Only a source's own entries expire it: B being quiet doesn't keep A's.
    store.add(held("b-new", 1130.0, B))
    assert store.size(A) == 100 and store.size(B) == 100


def test_a_category_can_be_held_longer() -> None:
    clock = Clock()
    store = RecentSpeech(clock, category_hold={SourceCategory.VIDEO: 3600.0})
    store.add(held("v", 1000.0, A, SourceCategory.VIDEO))
    store.add(held("c", 1000.0, B, SourceCategory.CALL))
    clock.now = 2000.0
    assert store.get(CaptionId("v")) is not None
    assert store.get(CaptionId("c")) is None


def test_the_hold_is_a_setting() -> None:
    clock = Clock()
    store = RecentSpeech(clock, hold_seconds=10.0)
    store.add(held("c", 1000.0))
    clock.now = 1011.0
    assert store.get(CaptionId("c")) is None


def test_memory_is_bounded_whatever_the_hold() -> None:
    clock = Clock()
    store = RecentSpeech(clock, hold_seconds=1e9, max_bytes=1000)
    for i in range(50):
        store.add(held(f"c{i}", 1000.0 + i, size=300))
    assert store.size(A) <= 1000
    assert store.get(CaptionId("c49")) is not None
    assert store.get(CaptionId("c0")) is None


def test_one_huge_entry_is_still_held() -> None:
    store = RecentSpeech(Clock(), max_bytes=10)
    store.add(held("big", 1000.0, size=500))
    assert store.get(CaptionId("big")) is not None


def test_a_joined_caption_replaces_those_it_covers() -> None:
    store = RecentSpeech(Clock())
    store.add(held("c1", 990.0, size=10))
    store.add(held("c2", 995.0, size=10))
    joined = HeldSpeech(
        CaptionId("c3"), A, SourceCategory.VIDEO, 987.0, 999.0, b"y" * 40
    )
    store.add(joined, replaces=(CaptionId("c1"), CaptionId("c2")))
    assert store.get(CaptionId("c1")) is None and store.get(CaptionId("c2")) is None
    got = store.get(CaptionId("c3"))
    assert got is not None and (got.start, got.end) == (987.0, 999.0)
    assert store.size() == 40


def test_clear_and_removing_a_source() -> None:
    store = RecentSpeech(Clock())
    store.add(held("a", 999.0, A))
    store.add(held("b", 999.0, B))
    store.remove_source(A)
    assert store.get(CaptionId("a")) is None and store.get(CaptionId("b"))
    store.clear()
    assert store.get(CaptionId("b")) is None and store.size() == 0
