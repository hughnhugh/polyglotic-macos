"""The UI lab's golden images (project 119): a picture against its golden,
the gate on an unapproved difference, the failing state's pictures kept,
one command to approve (all, or `--only` some), and another to remove
what's stale (258)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tools.ui_lab import __main__ as cli
from tools.ui_lab import goldens, lab, new_parts

from polyglotic_desktop.ui_next import style


@pytest.fixture
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    yield app


def picture(color: str = "#202830", size: tuple[int, int] = (60, 40)) -> QImage:
    image = QImage(*size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def with_block(image: QImage, color: str, side: int) -> QImage:
    changed = image.copy()
    for x in range(side):
        for y in range(side):
            changed.setPixelColor(x, y, QColor(color))
    return changed


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "goldens"


def test_a_picture_against_its_golden(store: Path) -> None:
    image = picture()
    assert goldens.compare("ui_next.a", image, store)[0].status == "new"
    assert goldens.approve({"ui_next.a": image}, store) == [
        "ui_next.a: no golden yet - approved"
    ]
    verdict, before, diff = goldens.compare("ui_next.a", image, store)
    assert verdict.status == "same" and before is not None and diff is None
    nearly = with_block(image, "#242c34", 5)  # within the channel tolerance
    assert goldens.compare("ui_next.a", nearly, store)[0].status == "same"
    changed = with_block(image, "#ffffff", 5)
    verdict, before, diff = goldens.compare("ui_next.a", changed, store)
    assert (verdict.status, verdict.changed, verdict.total) == ("differs", 25, 2400)
    assert verdict.describe() == "25 pixels differ (1.04 %)"
    assert diff is not None and diff.pixelColor(0, 0) == QColor(230, 0, 160)
    assert diff.pixelColor(30, 30) != QColor(230, 0, 160)
    bigger = picture(size=(61, 40))
    assert goldens.compare("ui_next.a", bigger, store)[0].status == "resized"


def test_a_state_that_animates_may_differ_by_its_allowance(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    goldens.approve({"ui_next.pulse": picture()}, store)
    pulsed = with_block(picture(), "#ffffff", 3)
    assert goldens.compare("ui_next.pulse", pulsed, store)[0].status == "differs"
    monkeypatch.setattr(goldens, "ALLOWED", {"ui_next.pulse": 9})
    assert goldens.compare("ui_next.pulse", pulsed, store)[0].status == "same"


def test_approving_writes_only_what_changed_and_never_removes_a_golden(
    store: Path,
) -> None:
    """258: approving a few states once removed every other golden (250
    restored 90 by hand). Approving now never removes one."""
    goldens.approve({"ui_next.a": picture(), "ui_next.b": picture()}, store)
    kept = (store / "ui_next.a.png").read_bytes()
    changes = goldens.approve(
        {"ui_next.a": picture(), "ui_next.c": with_block(picture(), "#fff", 4)},
        store,
    )
    assert changes == ["ui_next.c: no golden yet - approved"]
    assert (store / "ui_next.a.png").read_bytes() == kept
    assert sorted(p.name for p in store.glob("*.png")) == [
        "ui_next.a.png",
        "ui_next.b.png",  # not given: kept
        "ui_next.c.png",
    ]
    made = json.loads((store / goldens.MADE_WITH).read_text(encoding="utf-8"))
    assert made["made_with"] == goldens.fingerprint()
    assert goldens.machine_note(store) == ""


def test_a_golden_whose_state_is_gone_goes_only_when_removed(store: Path) -> None:
    goldens.approve({"ui_next.a": picture(), "ui_next.b": picture()}, store)
    assert goldens.stale(["ui_next.a"], store) == [store / "ui_next.b.png"]
    assert goldens.stale(["ui_next.a", "ui_next.b"], store) == []
    assert goldens.remove_stale(["ui_next.a"], store) == [
        "ui_next.b: its state is gone - removed"
    ]
    assert [p.name for p in store.glob("*.png")] == ["ui_next.a.png"]
    assert goldens.remove_stale(["ui_next.a"], store) == []


def test_another_machine_is_named_when_pictures_differ(store: Path) -> None:
    goldens.approve({"ui_next.a": picture()}, store)
    made = {"made_with": {**goldens.fingerprint(), "fonts": "3 files, 0"}}
    (store / goldens.MADE_WITH).write_text(json.dumps(made), encoding="utf-8")
    note = goldens.machine_note(store)
    assert "fonts 3 files, 0 ->" in note and "approve on the user's PC" in note


def _label(lab_: lab.Lab) -> QWidget:
    shown = QLabel("Captions appear here")
    shown.setObjectName("lab_label")
    # the interface's base text at the text size the lab runs at (the app's
    # Normal, 1.3 since decision 0244): Qt's own 12 px is off its type scale
    shown.setStyleSheet(
        f"background: #ffffff; color: #111111; padding: 8px; font-size: {style.px(13)}px;"
    )
    shown.setAlignment(Qt.AlignmentFlag.AlignCenter)
    shown.resize(240, 60)
    shown.show()
    return shown


@pytest.fixture
def one_state(
    store: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> Iterator[lab.State]:
    state = lab.State("ui_next.label", _label, gated=True)
    monkeypatch.setattr(new_parts, "STATES", [state])
    # Only this one state: the lab's list of the new interface's states is
    # replaced as a whole, so a state module added later (the panels, Home,
    # the transcript...) can't run here and fail this test on its own budgets
    # under load (it did, three times on 2026-11-07).
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(goldens, "GOLDENS", store)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    yield state


def test_an_unapproved_difference_fails_the_gate_and_keeps_its_pictures(
    one_state: lab.State, store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "lab"
    assert cli.main(["--gate", "--out", str(out)]) == 1  # new
    assert cli.main(["approve", "--reason", "a test", "--out", str(out)]) == 0
    assert (store / "ui_next.label.png").is_file()
    assert cli.main(["--gate", "--out", str(out)]) == 0
    assert not list((out / "failed").glob("*.png"))

    def changed(lab_: lab.Lab) -> QWidget:
        shown = _label(lab_)
        assert isinstance(shown, QLabel)
        shown.setText("Captions will appear here")
        return shown

    monkeypatch.setattr(
        new_parts, "STATES", [lab.State("ui_next.label", changed, True)]
    )
    assert cli.main(["--gate", "--out", str(out)]) == 1
    assert sorted(p.name for p in (out / "failed").glob("*.png")) == [
        "ui_next.label.diff.png",
        "ui_next.label.golden.png",
        "ui_next.label.png",
    ]
    written = json.loads((out / "ui_next.label.json").read_text(encoding="utf-8"))
    assert written["golden"]["status"] == "differs"
    assert "## Golden images" in (out / "summary.md").read_text(encoding="utf-8")
    assert cli.main(["--out", str(out)]) == 0  # no gate


def _labelled(text: str) -> lab.State:
    def run(lab_: lab.Lab) -> QWidget:
        shown = _label(lab_)
        assert isinstance(shown, QLabel)
        shown.setText(text)
        return shown

    return lab.State(f"ui_next.{text}", run, gated=True)


def test_approve_only_runs_the_states_named_and_prune_is_its_own_step(
    one_state: lab.State,
    store: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """258: `approve --only` draws and approves only the states it names
    (names or patterns) and leaves every other golden as it was; a name
    that matches no state runs nothing; only `prune` removes a golden, and
    only one whose state is gone."""
    out = str(tmp_path / "lab")
    states = [_labelled("one"), _labelled("two"), _labelled("three")]
    monkeypatch.setattr(new_parts, "STATES", states)
    assert cli.main(["approve", "--reason", "a test", "--out", out]) == 0
    before = {p.name: p.read_bytes() for p in store.glob("*.png")}
    assert sorted(before) == ["ui_next.one.png", "ui_next.three.png", "ui_next.two.png"]

    drawn: list[str] = []
    run = lab.run

    def noted(chosen: list[lab.State], out: Path) -> list[lab.Result]:
        drawn.extend(s.name for s in chosen)
        return run(chosen, out)

    monkeypatch.setattr(lab, "run", noted)
    (store / "ui_next.two.png").unlink()  # one to approve again
    assert (
        cli.main(
            ["approve", "--reason", "a test", "--only", "ui_next.t*o", "--out", out]
        )
        == 0
    )
    assert drawn == ["ui_next.two"]
    assert {p.name: p.read_bytes() for p in store.glob("*.png")} == before

    drawn.clear()
    with pytest.raises(SystemExit, match="no state is called ui_next.four"):
        cli.main(
            [
                "approve",
                "--reason",
                "a test",
                "--only",
                "ui_next.one",
                "ui_next.four",
                "--out",
                out,
            ]
        )
    assert drawn == []

    monkeypatch.setattr(new_parts, "STATES", states[:2])  # "three" is gone
    capsys.readouterr()
    assert (
        cli.main(
            ["approve", "--reason", "a test", "--only", "ui_next.one", "--out", out]
        )
        == 0
    )
    assert "1 golden(s) whose state is gone, kept" in capsys.readouterr().out
    assert (store / "ui_next.three.png").is_file()
    assert cli.main(["prune"]) == 0
    assert "ui_next.three: its state is gone - removed" in capsys.readouterr().out
    assert sorted(p.name for p in store.glob("*.png")) == [
        "ui_next.one.png",
        "ui_next.two.png",
    ]
    with pytest.raises(SystemExit):
        cli.main(["--only", "ui_next.one", "--out", out])  # only with approve


def test_every_new_state_has_a_golden_and_none_is_left_over() -> None:
    """Add a state, approve its golden (`python -m tools.ui_lab approve`)."""
    stored = {p.stem for p in goldens.GOLDENS.glob("*.png")}
    assert stored == {state.name for state in cli.visual_states()}


def test_approving_needs_a_reason_and_logs_it_with_what_changed(
    one_state: lab.State, store: Path, tmp_path: Path
) -> None:
    """polyglotic-hq 999: a golden is approved only for a named, intended
    change. `approve` refuses without `--reason`, approving nothing, and
    writes each approval's day, reason and changed states to the log beside
    the goldens; an approval that changes nothing writes nothing."""
    out = str(tmp_path / "lab")
    with pytest.raises(SystemExit):
        cli.main(["approve", "--out", out])
    assert not list(store.glob("*.png"))
    assert cli.main(["approve", "--reason", "952: the plain face", "--out", out]) == 0
    log = (store / goldens.APPROVALS).read_text(encoding="utf-8")
    assert log.startswith("# Approved goldens")
    assert "golden(s)\n\n952: the plain face\n\n- ui_next.label: no golden yet" in log
    assert cli.main(["approve", "--reason", "nothing new", "--out", out]) == 0
    assert (store / goldens.APPROVALS).read_text(encoding="utf-8") == log
    with pytest.raises(SystemExit):
        cli.main(["--reason", "not approving", "--out", out])


def test_the_log_names_utcs_day(store: Path) -> None:
    from datetime import date

    store.mkdir(parents=True)
    goldens.record(
        ["ui_next.a: 4 pixels differ (0.10 %) - approved"],
        "why",
        store,
        date(2026, 11, 27),
    )
    assert "\n## 2026-11-27: 1 golden(s)\n\nwhy\n\n- ui_next.a: 4 pixels" in (
        store / goldens.APPROVALS
    ).read_text(encoding="utf-8")
