"""Release-gate tolerances for the Video frame comparer."""

from copy import deepcopy

import pytest
from tools.video_motion.compare import compare, counts, invariants, return_invariants


def trace() -> dict:
    settings = {"W": 560, "H": 96, "origPx": 28, "transPx": 22}
    row = {
        "kind": "original",
        "id": 0,
        "index": 0,
        "text": "Okay",
        "x": 10,
        "y": 50,
        "h": 36.4,
        "w": 80,
        "px": 28,
        "alpha": 1,
        "phase": "live",
    }
    return {
        "size": [560, 96],
        "settings": settings,
        "fps": 60,
        "frames": [
            {"frame": 0, "rows": [row]},
            {"frame": 1, "rows": [{**row, "x": 0, "y": 40, "text": "Okay then"}]},
        ],
        "events": [{"frame": 0, "text": "wait starts"}],
    }


def test_reference_matches_itself_when_its_rows_obey_the_rules() -> None:
    doc = trace()
    assert not list(compare(doc, doc))


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("x", -1.01, "glide speed"),
        ("y", 41.01, "lift speed"),
        ("alpha", 0.95, "opacity"),
        ("px", 27, "squeeze"),
        ("y", 51, "downward"),
        ("text", "Okay", "word late or missing"),
    ],
)
def test_fails_on_a_single_bad_frame(field: str, value: object, failure: str) -> None:
    target = trace()
    actual = deepcopy(target)
    actual["frames"][1]["rows"][0][field] = value
    assert (failure, 1) in list(compare(target, actual))


def test_position_and_speed_tolerances_are_inclusive() -> None:
    target = trace()
    actual = deepcopy(target)
    for f in actual["frames"]:
        f["rows"][0]["x"] += 2
    actual["frames"][1]["rows"][0]["x"] -= 1
    assert not list(compare(target, actual))
    actual["frames"][0]["rows"][0]["x"] += 0.01
    problems = dict(compare(target, actual))
    assert "position" in problems and "glide speed" in problems


def test_zero_word_slack_even_when_first_word_event_is_within_one_frame() -> None:
    target = trace()
    actual = deepcopy(target)
    actual["frames"][0]["rows"] = []
    problems = counts(compare(target, actual))
    assert problems["word late or missing"]["first"] == 0
    assert "event first words" not in problems


def test_wait_and_cut_events_must_be_observed_and_within_one_frame() -> None:
    target = trace()
    actual = deepcopy(target)
    actual["events"][0]["frame"] = 1
    assert not list(compare(target, actual))
    actual["events"][0]["frame"] = 2
    assert ("event wait/cut", 0) in list(compare(target, actual))
    del actual["events"]
    assert ("event wait/cut", 0) in list(compare(target, actual))


def test_overlap_fails_even_when_the_app_matches_the_reference() -> None:
    target = trace()
    rows = target["frames"][0]["rows"]
    rows.append({**rows[0], "id": 1, "text": "My grandmother"})
    assert ("overlap", 0) in list(invariants(target, target["settings"]))
    assert ("overlap", 0) in list(compare(target, target))


@pytest.mark.parametrize(
    ("caption_id", "phase", "collision"),
    [(0, "settled", False), (1, "settled", True), (0, "live", True)],
)
def test_only_a_captions_own_settling_crossfade_is_exempt(
    caption_id: int, phase: str, collision: bool
) -> None:
    target = trace()
    row = target["frames"][0]["rows"][0]
    row.update(phase="ghost", alpha=0.003)
    target["frames"][0]["rows"].append({**row, "id": caption_id, "phase": phase})
    assert (("overlap", 0) in invariants(target, target["settings"])) == collision


@pytest.mark.parametrize(("cut", "fails"), [(0, True), (59, True), (60, False)])
def test_unread_cut_must_reach_the_full_wait_cap(cut: int, fails: bool) -> None:
    doc = trace()
    doc["settings"]["maxWait"] = 1.0
    doc["events"].insert(0, {"frame": cut, "text": "Line 1 is cut short"})
    assert (("unread cut before cap", cut) in invariants(doc, doc["settings"])) == fails


@pytest.mark.parametrize("phase", ["live", "ghost", "settled"])
def test_visible_rows_fit_vertically_throughout_motion(phase: str) -> None:
    doc = trace()
    doc["frames"][0]["rows"][0].update(phase=phase, y=-0.1)
    assert ("row clipped vertically", 0) in invariants(doc, doc["settings"])


def test_source_caption_missing_from_all_frames_fails() -> None:
    doc = trace()
    doc["source"] = [{"id": 0}, {"id": 1}]
    assert ("caption never shown", 1) in invariants(doc, doc["settings"])


def test_switching_modes_keeps_a_held_rows_original_settle_start() -> None:
    doc = trace()
    doc["settings"]["minHold"] = 0.5
    row = {**doc["frames"][0]["rows"][0], "phase": "settled"}
    doc["frames"] = [
        {"frame": 0, "mode": "scrolling", "rows": [row]},
        {"frame": 30, "mode": "instant", "rows": [row]},
        {"frame": 31, "mode": "instant", "rows": [{**row, "y": 49}]},
    ]
    assert not list(invariants(doc, doc["settings"]))


def test_word_deadline_uses_ink_and_measures_the_queue_independently():
    from tools.video_motion.ink import audit, late

    frames = []
    for frame in range(8):
        rows = (
            [
                {
                    "id": 0,
                    "kind": "original",
                    "phase": "live",
                    "index": 0,
                    "text": "old",
                    "x": 0,
                    "y": 35,
                    "h": 10,
                    "alpha": 1,
                    "inkIndex": 0,
                }
            ]
            if frame < 3
            else []
        )
        if frame >= 4:
            rows.append(
                {
                    "id": 1,
                    "kind": "original",
                    "phase": "live",
                    "index": 0,
                    "text": "new new",
                    "x": 2 if frame < 7 else 0,
                    "y": 35,
                    "h": 10,
                    "alpha": 1,
                    "inkIndex": 1,
                }
            )
        frames.append({"frame": frame, "rows": rows})
    source = {
        "id": 1,
        "en": "new new",
        "zh": "",
        "finishT": 0.7,
        "transT": 0.7,
        "updates": [{"t": 0.05, "words": [{"t": "new new"}]}],
    }
    dump = {
        "glyphInk": [[["old", 0, 10]], [["new", 0, 10], ["new", 18, 30]]],
        "mode": "instant",
        "fps": 10,
        "settings": {"W": 30},
        "liveTop": 35,
        "frames": frames,
        "source": [source],
    }
    exposures, queues = audit(dump)
    assert queues == [0.25]
    assert [e.token for e in late(exposures, 0.2)] == [("new", 2)]


def test_wrapped_row_uses_shaped_ink_at_the_right_clip_edge() -> None:
    doc = trace()
    row = doc["frames"][0]["rows"][0]
    row.update(phase="settled", x=479, inkIndex=0, horizontalClip=[0, 560])
    doc["glyphInk"] = [[["Okay", 0, 82]]]
    assert ("settled glyph ink clipped horizontally", 0) in invariants(
        doc, doc["settings"]
    )
    row["compact"] = True  # an oversized caption still uses the reading track
    assert not list(invariants(doc, doc["settings"]))


def test_return_audits_both_copies_and_requires_the_entire_translation() -> None:
    doc = trace()
    scenario = {
        "actions": {"scroll": 0, "hold": 1, "leave": 2, "live": 3},
        "wrappedCaption": 0,
    }
    doc["source"] = [{"id": 0, "zh": "Two lines"}]
    doc["frames"] = [
        {"frame": i, "rows": [], "view": state}
        for i, state in enumerate(["history", "holding", "history", "live"])
    ]
    settled = {
        "id": 0,
        "kind": "translation",
        "index": 0,
        "text": "Two",
        "x": 10,
        "y": 10,
        "w": 30,
        "h": 12,
        "alpha": 1,
        "phase": "settled",
    }
    rows = doc["frames"][3]["rows"]
    rows.extend([settled, {**settled, "index": 1, "text": "lines", "y": 22}])
    assert not list(return_invariants(doc, scenario))
    doc["frames"][3].update(inkOverlap=True, duplicateInk=True)
    assert list(return_invariants(doc, scenario)) == [
        ("glyph ink overlaps after returning live", 3),
        ("caption painted twice after returning live", 3),
    ]
    doc["frames"][3].update(inkOverlap=False, duplicateInk=False)
    rows.append({**settled, "phase": "ghost", "alpha": 0.1})
    assert ("overlap after returning live", 3) in return_invariants(doc, scenario)
    rows.pop()
    rows[1]["text"] = "lin"
    assert ("return never showed the complete wrapped translation", 3) in (
        return_invariants(doc, scenario)
    )
