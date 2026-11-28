"""The movement family's rules, each held on a real window at 60 Hz.

Every test here pins one rule of `rules.toml` (`@pins`) or is that rule's
planted break (`@breaks`): the same replay with one fault put into the
running display, which the rule's property must see. The whole matrix is
judged by `python -m tools.scene_replay judge`; these are the quick cases.
"""

import pytest
from PySide6.QtWidgets import QApplication
from tools.scene_replay import drive, plants, properties, streams
from tools.scene_replay.frames import Frame
from tools.scene_replay.rulebook import breaks, pins

from polyglotic_desktop.ui_next.views.cards import GLIDE_FASTEST


def replay(stream: str, setup: str, plant: str | None = None) -> list[Frame]:
    with plants.planted(plant):
        return list(drive.play(streams.load(stream), drive.Setup.named(setup)))


FALLS = [
    ("rules/revised-shorter", "panel+narrow"),
    ("rules/revised-shorter", "panel+narrow+paired"),
    ("rules/revised-shorter", "zones+narrow"),
    ("rules/revised-shorter", "cards+narrow"),
    ("rules/revised-shorter", "joined+narrow"),
    ("rules/revised-shorter", "transcript+narrow"),
    ("rules/grows-a-second-line", "panel+readings+narrow"),
    ("lines/a", "panel"),
    ("lines/a", "video-instant"),
    ("rebuild/finished_replaces_live", "panel"),
    ("rebuild/live_supersedes_words", "zones"),
]


@pins("movement.words-never-fall")
@pytest.mark.parametrize(("stream", "setup"), FALLS)
def test_words_never_fall(qapp: QApplication, stream: str, setup: str) -> None:
    frames = replay(stream, setup)
    assert any(frame.rows for frame in frames)
    assert properties.never_fall(frames) == []


@pins("movement.words-never-fall")
@pytest.mark.xfail(
    strict=True,
    reason="Video breaks a revised two-line subtitle again and its second line"
    " starts lower (rules.toml: the rule's conflict with Video's line breaks)",
)
def test_words_never_fall_in_video_when_a_subtitle_is_revised(
    qapp: QApplication,
) -> None:
    assert properties.never_fall(replay("lines/motion", "video-instant+narrow")) == []


@breaks("movement.words-never-fall")
@pytest.mark.parametrize("setup", ["panel+narrow", "joined+narrow"])
def test_a_one_frame_fall_is_seen(qapp: QApplication, setup: str) -> None:
    broken = properties.never_fall(replay("rules/revised-shorter", setup, "fall"))
    assert broken, "a planted 3 px fall for one frame went unseen"
    assert "fell" in broken[0].what


SIDEWAYS = [
    ("rules/grows-a-second-line", "panel+narrow"),
    ("rules/grows-a-second-line", "panel+narrow+paired"),
    ("rules/revised-shorter", "panel+narrow"),
    ("lines/a", "panel"),
    ("lines/a", "zones"),
    ("lines/a", "cards"),
    ("lines/d", "video-instant"),
    ("lines/a", "transcript"),
]


@pins("movement.no-sideways-slide")
@pytest.mark.parametrize(("stream", "setup"), SIDEWAYS)
def test_no_row_slides_sideways(qapp: QApplication, stream: str, setup: str) -> None:
    assert properties.no_sideways_slide(replay(stream, setup)) == []


@pins("movement.no-sideways-slide")
def test_video_scrolling_is_where_a_row_does_pan(qapp: QApplication) -> None:
    """The rule's one exception, pinned so it stays the only one: a long
    row pans in Video Scrolling (686's agreed simulation)."""
    assert properties.no_sideways_slide(replay("lines/d", "video-scrolling"))


@breaks("movement.no-sideways-slide")
def test_a_row_sliding_in_from_the_right_is_seen(qapp: QApplication) -> None:
    broken = properties.no_sideways_slide(
        replay("rules/grows-a-second-line", "panel+narrow", "slide")
    )
    assert broken, "959's slide from the right, planted, went unseen"


GLIDES = [
    ("lines/a", "panel"),
    ("lines/b", "panel"),
    ("lines/a", "joined"),
    ("lines/c", "panel+narrow"),
    ("rules/grows-a-second-line", "panel+narrow"),
    ("rebuild/two_speakers", "panel"),
]


@pins("movement.the-approved-glide")
def test_the_glides_top_speed_is_the_one_the_rulebook_states() -> None:
    assert GLIDE_FASTEST.value == properties.GLIDE_FASTEST


@pins("movement.the-approved-glide")
@pytest.mark.parametrize(("stream", "setup"), GLIDES)
def test_rows_glide_and_never_jump(qapp: QApplication, stream: str, setup: str) -> None:
    frames = replay(stream, setup)
    assert properties.approved_glide(frames) == []


@pins("movement.the-approved-glide")
@pytest.mark.xfail(
    strict=True,
    reason="a word moved to the next row pulls that row to a new place in one"
    " frame (rules.toml: the rule's conflict with Words never fall)",
)
def test_rows_glide_when_a_word_moves_to_the_next_row(qapp: QApplication) -> None:
    frames = replay("lines/motion", "panel+narrow+paired")
    assert properties.approved_glide(frames) == []


@breaks("movement.the-approved-glide")
@pytest.mark.parametrize("stream", ["lines/a", "lines/b"])
def test_the_old_step_is_seen_as_a_jump(qapp: QApplication, stream: str) -> None:
    broken = properties.approved_glide(replay(stream, "panel", "step"))
    assert broken and "jump" in broken[0].what


@pins("movement.a-new-row-waits-then-fades-in")
@pytest.mark.parametrize(
    "setup", ["panel+narrow", "panel+readings+narrow", "joined+narrow"]
)
def test_a_second_line_waits_then_fades_in_where_it_stays(
    qapp: QApplication, setup: str
) -> None:
    frames = replay("rules/grows-a-second-line", setup)
    fading = [row for frame in frames for row in frame.rows if 0 < row.opacity < 64]
    assert fading, "no row faded in: the stream no longer carries on to a second line"
    assert properties.waits_then_fades(frames) == []


@pins("movement.a-new-row-waits-then-fades-in")
def test_a_captions_second_part_waits_too(qapp: QApplication) -> None:
    """The wide window: a live caption finishes as two parts, and the second
    waits below the first until it has moved up (984; drawn over it on the
    0.1.13 train before)."""
    frames = replay("lines/a", "panel")
    assert properties.waits_then_fades(frames) == []
    first = {
        kind: next(
            f.n
            for f in frames
            for r in f.rows
            if r.clause == 1 and r.kind == kind and r.opacity > 0
        )
        for kind in ("original", "translation")
    }
    assert first["translation"] >= first["original"], "its translation came first"


NEW_PARTS = [
    ("lines/a", "joined"),
    ("lines/b", "panel+readings"),
    ("lines/d", "panel+narrow"),
    ("lines/d", "panel+paired"),
    ("lines/e", "joined+narrow+paired"),
    ("lines/j", "panel"),
    ("lines/e", "panel+readings+narrow"),
]


@pins("movement.a-new-row-waits-then-fades-in")
@pytest.mark.parametrize(("stream", "setup"), NEW_PARTS)
def test_a_new_part_waits_in_every_arrangement(
    qapp: QApplication, stream: str, setup: str
) -> None:
    assert properties.waits_then_fades(replay(stream, setup)) == []


@breaks("movement.a-new-row-waits-then-fades-in")
def test_a_second_line_drawn_at_once_is_seen(qapp: QApplication) -> None:
    broken = properties.waits_then_fades(
        replay("rules/grows-a-second-line", "panel+narrow", "no-wait")
    )
    assert broken and "overlaps" in broken[0].what


@breaks("movement.a-new-row-waits-then-fades-in")
def test_a_second_part_drawn_at_once_is_seen(qapp: QApplication) -> None:
    broken = properties.waits_then_fades(replay("lines/a", "panel", "no-wait"))
    assert broken and "overlaps" in broken[0].what
