"""Every setting changed and put back (polyglotic-hq 523, from 515's sweep):
the verdict on what the sweep saw. The sweep itself drives the app on
GitHub's Mac (the macOS job's learner part); here, made-up sweeps."""

from typing import Any

import pytest

from tools import macos_settings_sweep as sweep

RAN = [{"check": "sweep: settings ran", "ok": True, "detail": ""}]


def row(where: str, what: str, stored: dict[str, Any] | None = None,
        log: list[str] | None = None) -> dict[str, Any]:  # fmt: skip
    return {"where": where, "what": what, "stored": stored or {}, "log": log or [],
            "error_boxes": []}  # fmt: skip


def swept(
    *rows: dict[str, Any], first: Any = None, final: Any = None
) -> dict[str, Any]:
    padding = [row("Settings > look", f"slider {n}") for n in range(sweep.ENOUGH)]
    return {
        "changes": [*padding, *rows],
        "first_stored": first if first is not None else {"word_links": "arrows"},
        "final_stored": final if final is not None else {"word_links": "arrows"},
    }


def judged(found: list[dict[str, Any]]) -> dict[str, str]:
    return {c["check"]: c["outcome"] for c in found}


def test_a_sweep_that_put_everything_back_passes() -> None:
    found = sweep.verdict(
        swept(
            row("Settings > links", "toggle Off", {"word_links": ["arrows", "off"]}),
            row(
                "Settings > links",
                "toggle Off: back",
                {"word_links": ["off", "arrows"]},
            ),
        ),
        RAN,
    )
    assert judged(found) == {
        "every_part_ran": "pass",
        "enough_changed": "pass",
        "no_error": "pass",
        "put_back": "pass",
        "warnings": "pass",
    }


def test_a_setting_not_put_back_fails_naming_the_control() -> None:
    found = sweep.verdict(
        swept(
            row(
                "Settings > app",
                "toggle Larger",
                {"app_text_size": ["normal", "larger"]},
            ),
            row("Settings > app", "toggle Larger: back"),
            first={"app_text_size": "normal"},
            final={"app_text_size": "larger"},
        ),
        RAN,
    )
    (put_back,) = [c for c in found if c["check"] == "put_back"]
    assert put_back["outcome"] == "fail"
    assert put_back["facts"]["left"] == {
        "app_text_size": {
            "was_then": ["normal", "larger"],
            "by": ["Settings > app / toggle Larger"],
        }
    }


def test_a_preset_put_back_by_a_later_change_passes() -> None:
    """A preset's pair may leave colours changed that a later one puts
    back: only what the end holds is judged."""
    found = sweep.verdict(
        swept(
            row("Settings > look", "toggle Broadcast", {"opacity": [0.72, 1.0]}),
            row("Settings > look", "toggle Broadcast: back"),
            row("Settings > look", "toggle Custom", {"opacity": [1.0, 0.72]}),
            first={"opacity": 0.72},
            final={"opacity": 0.72},
        ),
        RAN,
    )
    assert judged(found)["put_back"] == "pass"


def test_a_control_known_not_to_put_back_is_a_note_until_fixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    where, what = "Settings > links", "toggle Quiet view"
    monkeypatch.setattr(sweep, "KNOWN", {f"{where} / {what}": "being fixed"})
    found = sweep.verdict(
        swept(
            row(where, what, {"word_links": ["arrows", "off"]}),
            row(where, f"{what}: back"),
            first={"word_links": "arrows"},
            final={"word_links": "off"},
        ),
        RAN,
    )
    assert judged(found)["put_back"] == "pass"
    assert judged(found)["put_back_known"] == "note"


def test_what_use_moves_and_what_the_sweep_first_wrote_arent_judged() -> None:
    found = sweep.verdict(
        swept(
            first={"geometry": [1, 2], "changed": ["learning"]},
            final={
                "geometry": [3, 4],
                "changed": ["learning", "theme"],
                "caption_lab": {"fill": "paired"},
            },
        ),
        RAN,
    )
    (put_back,) = [c for c in found if c["check"] == "put_back"]
    assert put_back["outcome"] == "pass"
    assert put_back["facts"]["first_written"] == ["caption_lab.fill"]


def test_an_error_too_few_changes_or_a_part_that_broke_fails() -> None:
    errored = sweep.verdict(
        swept(row("menu bar", "Pause", log=["ERROR polyglotic: it broke"])), RAN
    )
    assert judged(errored)["no_error"] == "fail"
    few = sweep.verdict({"changes": [], "first_stored": {}, "final_stored": {}}, RAN)
    assert judged(few)["enough_changed"] == "fail"
    broke = sweep.verdict(
        swept(), [{"check": "settings ran", "ok": False, "detail": "x"}]
    )
    assert judged(broke)["every_part_ran"] == "fail"
    warned = sweep.verdict(swept(row("app", "x", log=["WARNING a: b"])), RAN)
    assert judged(warned)["warnings"] == "note"
