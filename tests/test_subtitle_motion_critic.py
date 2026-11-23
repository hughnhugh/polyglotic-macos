"""The recorder critic distinguishes appended text, re-wrapping and actual motion."""

from typing import Any

import pytest
from tools.subtitle_motion_critic import Box, Row, episodes, frames, size_changes

KEY = ("app", 1, 0, "o", 0)


def row(x: float = 0.0, width: float = 12, text: str = "abc") -> Row:
    return Row(text, (Box(x, 0, width, 10, 0, len(text)),))


def test_appending_letters_changes_neither_size_nor_position() -> None:
    before = row()
    assert before.step(row(width=24, text="abcdef")) == 0
    assert before.step(row(width=20)) == 8


def test_a_word_moving_between_visual_lines_counts_with_a_stationary_paragraph() -> (
    None
):
    before = row(text="a word")
    after = Row("a word", (Box(0, 0, 3, 10, 0, 2), Box(0, 10, 9, 10, 2, 6)))
    assert before.step(after) == 10


@pytest.mark.parametrize(
    ("positions", "fast", "abrupt"),
    [
        ([0, 0, 1, 3, 4, 4], False, False),
        ([0, 0, 3, 3], False, True),
        ([0, 1, 2, 3, 3], False, True),
        ([0, 8, 24, 32, 32], True, False),
    ],
)
def test_one_episode_per_retained_row(
    positions: list[int], fast: bool, abrupt: bool
) -> None:
    results = episodes(
        ((i * 0.04, {KEY: row(x)}) for i, x in enumerate(positions)), 300
    )
    if fast or abrupt:
        assert len(results) == 1
        assert (results[0]["over_limit"], results[0]["no_easing"]) == (fast, abrupt)
    else:
        assert not results


def test_resize_during_a_glide_is_attributed_to_the_frame_that_exceeds_the_limit() -> (
    None
):
    frames = [(i, {KEY: row(x)}) for i, x in enumerate([0, 2, 5, 9, 509, 509])]
    (event,) = episodes(frames, 300)
    assert event["started"] == 1 and event["at"] == 4


def test_film_grab_records_the_last_painted_viewport_even_when_unchanged() -> None:
    grabs = list(
        frames(
            [
                {
                    "w": "app",
                    "t": 0,
                    "s": "f",
                    "sz": [800, 300],
                    "rows": [],
                    "clip": {},
                },
                {
                    "w": "app",
                    "t": 1,
                    "s": "p",
                    "sz": [780, 280],
                    "rows": [],
                    "clip": {},
                },
                {"w": "app", "t": 2, "s": "f", "same": True},
            ]
        )
    )
    assert [size for _, _, size in grabs] == [(800, 300), (780, 280)]


def test_size_changes_counts_each_visible_line_on_each_film_frame() -> None:
    records: list[dict[str, Any]] = [
        {
            "w": "app",
            "s": "p",
            "st": {"app": {"subtitle_sizes": {"lines": 4, "wrong": 2}}},
        },
        {"w": "app", "s": "f", "same": 1},
        {"w": "app", "s": "f", "same": 1},
        {
            "w": "app",
            "s": "f",
            "st": {"app": {"subtitle_sizes": {"lines": 2, "wrong": 0}}},
        },
    ]
    assert size_changes(records) == {"size_changes": 4, "visible_line_frames": 10}
    assert size_changes([{"w": "app", "s": "f", "st": {"app": {}}}]) is None
