"""The display's net, tested: the replay is the same twice and sees a 1 px
nudge and a one-frame fall; the rulebook's check passes as committed and
fails on each of its planted faults (polyglotic-hq 982; PLAN.md display-0)."""

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from tools.scene_replay import deciding, drive, frames, plants, rulebook, streams
from tools.scene_replay.clock import START, Hands

RUNS = [
    ("lines/a", "panel"),
    ("lines/a", "cards"),
    ("lines/a", "zones+readings"),
    ("lines/a", "joined"),
    ("lines/d", "video-scrolling"),
    ("rebuild/two_speakers", "transcript"),
    ("rules/revised-shorter", "panel+narrow+paired"),
]


def summary(stream: str, setup: str, plant: str | None = None) -> frames.Summary:
    with plants.planted(plant):
        played = drive.play(streams.load(stream), drive.Setup.named(setup))
        return frames.summarise(f"{stream}@{setup}", played)


@pytest.mark.parametrize(("stream", "setup"), RUNS)
def test_a_replay_is_the_same_twice(
    qapp: QApplication, stream: str, setup: str
) -> None:
    first, second = summary(stream, setup), summary(stream, setup)
    assert first.changed, "nothing was drawn"
    assert frames.first_difference(first, second) is None


@pytest.mark.parametrize("plant", ["nudge", "fall"])
def test_the_diff_sees_a_planted_fault(qapp: QApplication, plant: str) -> None:
    clean = summary("rules/revised-shorter", "panel+narrow")
    broken = summary("rules/revised-shorter", "panel+narrow", plant)
    assert frames.first_difference(clean, broken) is not None


def test_a_nudge_of_one_px_is_64_units(qapp: QApplication) -> None:
    stream, setup = streams.load("lines/a"), drive.Setup.named("panel")
    clean = list(drive.play(stream, setup))[-1]
    with plants.planted("nudge"):
        nudged = list(drive.play(stream, setup))[-1]
    moved = {b.top - a.top for a, b in zip(clean.rows, nudged.rows, strict=True)}
    assert moved == {frames.q(plants.NUDGE_PX)}
    assert any("top" in line for line in frames.explain(clean, nudged))


def test_characters_are_read_in_the_same_order_every_launch(qapp: QApplication) -> None:
    """A row in two fonts (an ellipsis after Japanese) is two glyph runs,
    which Qt orders differently from launch to launch: without the sort the
    whole-matrix diff called 2 of 1,404 replays different from themselves
    in about half its runs (this test, likewise, fails about half the time
    without it)."""
    stream = streams.load("rebuild/japanese_readings")
    played = list(drive.play(stream, drive.Setup.named("cards+narrow+paired")))
    rows = [row for frame in played for row in frame.rows]
    assert any(len({char.glyph for char in row.chars}) > 1 for row in rows)
    for row in rows:
        assert list(row.chars) == sorted(
            row.chars, key=lambda c: (c.index, c.left, c.top, str(c.glyph))
        )


def test_frames_keep_no_text_and_round_trip(qapp: QApplication) -> None:
    played = list(drive.play(streams.load("lines/a"), drive.Setup.named("panel")))
    busiest = max(played, key=lambda frame: len(frame.rows))
    kept = frames.to_json(busiest)
    assert frames.from_json(kept) == busiest
    assert kept.isascii() and "boat" not in kept


def test_every_stream_plays_and_the_two_formats_meet() -> None:
    names = streams.names()
    assert len([n for n in names if n.startswith("lines/")]) == 15
    assert len([n for n in names if n.startswith("rebuild/")]) == 12
    for name in names:
        stream = streams.load(name)
        assert stream.events
        assert [t for t, _ in stream.events] == sorted(t for t, _ in stream.events)
        assert {u.source_id for _, u in stream.events} <= {streams.FIRST, streams.OTHER}


def test_the_patched_clock_rings_timers_in_order(qapp: QApplication) -> None:
    hands = Hands()
    rung: list[tuple[str, float]] = []
    with hands.patched():
        once = QTimer(singleShot=True, interval=50)
        often = QTimer(interval=20)
        once.timeout.connect(lambda: rung.append(("once", round(hands.now - START, 3))))
        often.timeout.connect(
            lambda: rung.append(("often", round(hands.now - START, 3)))
        )
        once.start()
        often.start()
        QTimer.singleShot(
            30, lambda: rung.append(("shot", round(hands.now - START, 3)))
        )
        assert once.isActive()
        hands.advance(START + 0.06)
        assert not once.isActive() and often.isActive()
        often.stop()
        hands.advance(START + 1.0)
    assert rung == [
        ("often", 0.02),
        ("shot", 0.03),
        ("often", 0.04),
        ("once", 0.05),
        ("often", 0.06),
    ]
    real = QTimer(singleShot=True, interval=1)
    real.start()
    assert real.isActive()  # the real timer is back
    real.stop()


def test_the_kept_list_of_deciding_functions_is_a_list() -> None:
    kept = json.loads((rulebook.RULES / "deciding.json").read_text("utf-8"))
    assert len(kept["files"]) == 29 and len(kept["deciding"]) > 500
    today = {each.key for each in deciding.scan(rulebook.ROOT).listed}
    for rule in rulebook.load():
        assert {each["function"] for each in rule.decided} <= today


def test_every_display_file_is_scanned() -> None:
    found = deciding.scan(rulebook.ROOT)
    assert len(deciding.FILES) == 28
    assert set(found.files) == {*deciding.FILES, *deciding.LATER}


# --- the rulebook's check -------------------------------------------------------


def test_the_rulebook_as_committed_holds() -> None:
    assert list(rulebook.problems()) == []


@pytest.fixture
def book(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of the rules and the written book, to plant faults in."""
    rules, written = tmp_path / "tests" / "ui_next" / "rules", tmp_path / "book"
    shutil.copytree(rulebook.RULES, rules, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(rulebook.BOOK, written)
    assert list(rulebook.problems(rules, written)) == []
    return rules, written


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text("utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), "utf-8", newline="\n")


def test_a_rule_with_no_test_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    module = rules / "test_wrapping.py"
    text = module.read_text("utf-8")
    pinned = '@pins("wrapping.every-row-is-a-single-line")'
    assert pinned in text
    module.write_text(text.replace(pinned, '@pins("wrapping.another-rule")'), "utf-8")
    found = list(rulebook.problems(rules, written))
    assert any("a rule with no test" in each for each in found)
    assert any("which is not a rule" in each for each in found)


def test_a_rule_with_no_planted_break_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    _edit(
        rules / "test_wrapping.py", '@breaks("wrapping.every', '@pins("wrapping.every'
    )
    assert any("no planted break" in each for each in rulebook.problems(rules, written))


def test_a_test_that_names_no_rule_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    with (rules / "test_movement.py").open("a", encoding="utf-8") as out:
        out.write("\n\ndef test_something_nobody_ruled_on() -> None:\n    pass\n")
    found = list(rulebook.problems(rules, written))
    assert any("a test that names no rule" in each for each in found)


def test_a_stale_rulebook_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    _edit(written / "RULEBOOK.md", "Words never fall", "Words sometimes fall")
    assert "RULEBOOK.md is stale: run rulebook --write" in rulebook.problems(
        rules, written
    )


def test_a_marked_rule_whose_statement_changed_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    rule = next(r for r in rulebook.load(rules) if r.id == "movement.no-sideways-slide")
    _edit(
        rules / "rules.toml",
        'title = "No sideways slide"\n',
        'title = "No sideways slide"\nmark = "keep"\nmarked_on = "2026-11-27"\n'
        f'marked_statement = "{rule.statement_digest()}"\n',
    )
    (written / "RULEBOOK.md").write_text(rulebook.render(rulebook.load(rules)), "utf-8")
    assert list(rulebook.problems(rules, written)) == []  # marked, and unchanged
    _edit(rules / "rules.toml", "Text never slides in from the side.", "Text slides.")
    (written / "RULEBOOK.md").write_text(rulebook.render(rulebook.load(rules)), "utf-8")
    found = list(rulebook.problems(rules, written))
    assert any("its statement changed after the founder marked it" in e for e in found)


def test_a_picture_that_no_longer_reproduces_fails(
    qapp: QApplication, tmp_path: Path
) -> None:
    from PySide6.QtGui import QColor, QImage
    from tools.scene_replay import pictures

    picture = rulebook.Picture("one.png", "lines/a", "panel", (29, 36), "")
    pictures.take([picture], tmp_path)
    assert pictures.problems([picture], tmp_path) == ([], "")
    path = tmp_path / "pictures" / "one.png"
    image = QImage(str(path))
    for x in range(120, 220):
        for y in range(40, 60):
            image.setPixelColor(x, y, QColor("#ff00ff"))
    image.save(str(path))
    found, _ = pictures.problems([picture], tmp_path)
    assert found and "no longer reproduces" in found[0]
    moved = rulebook.Picture("one.png", "lines/a", "panel", (29, 37), "")
    found, _ = pictures.problems([moved], tmp_path)
    assert found and "another recipe" in found[0]


def test_a_rule_decided_in_a_function_that_is_gone_fails(
    book: tuple[Path, Path],
) -> None:
    rules, written = book
    _edit(rules / "rules.toml", "Canvas._reveal_wraps", "Canvas._reveal_wrap")
    (written / "RULEBOOK.md").write_text(rulebook.render(rulebook.load(rules)), "utf-8")
    found = list(rulebook.problems(rules, written))
    assert any("not on the list of deciding functions" in each for each in found)


def test_a_missing_picture_fails(book: tuple[Path, Path]) -> None:
    rules, written = book
    (written / "pictures" / "movement.no-sideways-slide.png").unlink()
    assert any("is missing" in each for each in rulebook.problems(rules, written))
