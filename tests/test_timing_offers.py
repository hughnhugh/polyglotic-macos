"""Which timings each use offers on the bar's timing chip (polyglotic-hq
593, 585's rule 11 and its starting list)."""

from polyglotic_desktop.core.listening.offers import OFFERED, Use, offered, use_of
from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode

STEADY, WHOLE = CaptionMode.STEADY, CaptionMode.WHOLE
INSTANT, CALM = CaptionMode.INSTANT, CaptionMode.CALM


def test_watching_offers_both_live_original_timings() -> None:
    video = offered(Use.WATCHING)
    assert video.timings == (INSTANT, CaptionMode.SCROLLING)
    assert not video.allows(WHOLE)
    assert not video.allows(STEADY) and not video.allows(CALM)
    assert video.paths == ()  # never "translation after" on Video's cards


def test_talking_offers_steady_and_instant() -> None:
    talking = offered(Use.TALKING)
    assert set(talking.timings) == {STEADY, INSTANT}
    assert not talking.allows(CALM) and not talking.allows(WHOLE)  # too late
    assert talking.paths == ()


def test_studying_offers_steady_calm_and_the_translations_timing() -> None:
    studying = offered(Use.STUDYING)
    assert studying.timings == (INSTANT, STEADY, CALM)
    assert studying.paths == (ReadingPath.ACQUISITION, ReadingPath.BOTH)


def test_everyday_offers_all_four() -> None:
    assert offered(Use.EVERYDAY).timings == OFFERED_MODES
    assert set(OFFERED_MODES) == {STEADY, WHOLE, INSTANT, CALM}


def test_every_use_offers_something_and_never_the_retired_preview() -> None:
    assert set(OFFERED) == set(Use)
    for each in OFFERED.values():
        assert each.timings and CaptionMode.PREVIEW not in each.timings


def test_a_timing_not_offered_has_the_uses_best_as_its_nearest() -> None:
    assert offered(Use.WATCHING).nearest(STEADY) is INSTANT
    assert offered(Use.WATCHING).nearest(CALM) is INSTANT
    assert offered(Use.WATCHING).nearest(INSTANT) is INSTANT
    assert offered(Use.WATCHING).nearest(WHOLE) is INSTANT
    assert offered(Use.TALKING).nearest(CALM) is INSTANT
    assert offered(Use.STUDYING).nearest(INSTANT) is INSTANT


def test_a_presets_use() -> None:
    assert use_of("video") is Use.WATCHING
    assert use_of("conversation") is Use.TALKING
    assert use_of("learning") is Use.STUDYING
    assert use_of("everyday") is Use.EVERYDAY
    # a learner's own, and Custom, say nothing of their use: Everyday's
    assert use_of("own1") is Use.EVERYDAY
    assert use_of("custom") is Use.EVERYDAY


def test_the_uses_are_the_built_in_presets() -> None:
    from polyglotic_desktop.ui import use_presets

    assert {u.value for u in Use} == set(use_presets.ORDER)
