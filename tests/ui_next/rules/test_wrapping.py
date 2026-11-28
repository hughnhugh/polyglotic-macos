"""The wrapping family's rules, each held on a real window (see
`test_movement.py` for how a rule's test and its planted break are marked)."""

import pytest
from PySide6.QtWidgets import QApplication
from tools.scene_replay import drive, plants, properties, streams
from tools.scene_replay.frames import Frame
from tools.scene_replay.rulebook import breaks, pins


def replay(stream: str, setup: str, plant: str | None = None) -> list[Frame]:
    with plants.planted(plant):
        return list(drive.play(streams.load(stream), drive.Setup.named(setup)))


SINGLE = [
    "panel+narrow",
    "panel+narrow+paired",
    "panel+readings+narrow",
    "zones+narrow",
    "cards+narrow",
    "joined+narrow",
    "video-instant+narrow",
    "video-scrolling+narrow",
]


@pins("wrapping.every-row-is-a-single-line")
@pytest.mark.parametrize("setup", SINGLE)
def test_every_row_is_a_single_line(qapp: QApplication, setup: str) -> None:
    frames = replay("rules/one-long-line", setup)
    assert any(frame.rows for frame in frames)
    assert properties.single_line(frames) == []


@pins("wrapping.every-row-is-a-single-line")
def test_a_long_caption_carries_on_in_rows_of_its_own(qapp: QApplication) -> None:
    last = replay("rules/one-long-line", "panel+narrow")[-1]
    originals = [row for row in last.rows if row.kind == "original"]
    assert len(originals) > 1, "the caption fits one row: the stream is too short"
    assert len({row.top for row in originals}) == len(originals)


@pins("wrapping.every-row-is-a-single-line")
def test_the_transcript_is_where_a_row_does_wrap(qapp: QApplication) -> None:
    """The rule's one exception, pinned so it is seen when it goes: the
    transcript's rows are wrapped by Qt inside the row."""
    assert properties.single_line(replay("rules/one-long-line", "transcript+narrow"))


@breaks("wrapping.every-row-is-a-single-line")
def test_a_row_left_wrapped_is_seen(qapp: QApplication) -> None:
    broken = properties.single_line(
        replay("rules/one-long-line", "panel+narrow", "wrap")
    )
    assert broken and "lines" in broken[0].what
