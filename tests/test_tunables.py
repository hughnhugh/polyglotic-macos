"""Layer precedence, reading constraints and the file-free startup path."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from polyglotic_desktop import tunable_config
from polyglotic_desktop.core.shared.tunables import declarations, install
from polyglotic_desktop.ui_next.views import cards, dwell
from tools import tunables


@pytest.fixture(autouse=True)
def reset_store() -> Iterator[None]:
    yield
    install(tunable_config.configuration({}, {}, {}))


def test_all_declarations_are_collected_and_have_unique_names() -> None:
    written = [name for name, *_ in tunables.locations(tunables.SOURCE)]
    assert sorted(written) == sorted(declarations())


def test_layers_are_ordered_and_a_second_load_starts_from_shipped(
    tmp_path: Path,
) -> None:
    key = dwell.READ_START_SEC.name
    layers = [{key: n} for n in (0.4, 0.45, 0.5)]
    for n, expected in enumerate((0.35, 0.4, 0.45, 0.5)):
        result = tunable_config.configuration(*(layers[:n] + [{}] * (3 - n)))
        assert not result.warnings
        assert result.values[key] == expected
    (tmp_path / "tunables.toml").write_text("[dwell]\nread_start = 0.45")
    tunable_config.load(tmp_path, None, {}, cohort=layers[0])
    assert dwell.READ_START_SEC.value == 0.45
    (tmp_path / "tunables.toml").unlink()
    tunable_config.load(tmp_path, None, {})
    assert dwell.READ_START_SEC.value == dwell.READ_START_SEC.default


@pytest.mark.parametrize(
    ("rule", "breaking"),
    [
        ("R1", {"dwell.read_most": 1.2, "dwell.read_least": 1.5}),
        ("R2", {"cards.depth_scales": [1, 0.9]}),
        ("R2", {"dwell.reference_interval": 1.5}),
        ("R3", {"cards.depth_ink": [1, 0.74, 0.86]}),
        ("R3", {"cards.depth_ink": [1, 0.86]}),
        ("R4", {"presets.video.fade_after": 1.5}),
        ("R5", {"dwell.hold_video": 2.5}),
        ("R5", {"dwell.hold_conversation": 1.1}),
        ("R5", {"dwell.hold_everyday": 4.1}),
        ("R5", {"dwell.hold_learning": 8.1}),
        ("R6", {"dwell.read_least": 2}),
        ("R7", {"presets.video.caption_mode": "steady"}),
        ("R7", {"presets.video.caption_path": "acquisition"}),
        ("R7", {"presets.conversation.caption_mode": "whole"}),
        ("R7", {"presets.learning.caption_mode": "whole"}),
        ("R8", {"dwell.translation_awaited": 2.1}),
    ],
)
def test_a_broken_rule_refuses_the_whole_layer_and_keeps_resolving(
    rule: str, breaking: dict[str, object]
) -> None:
    key = "dwell.read_start"
    result = tunable_config.configuration(
        {key: 0.4}, {key: 0.5, **breaking}, {"cards.depth": 0.5}
    )
    assert len(result.warnings) == 1
    assert f"local: whole layer refused: {rule}:" in result.warnings[0]
    assert result.values[key] == 0.4
    assert result.values["cards.depth"] == 0.5


@pytest.mark.parametrize("bad", [False, "0.4", -1, float("inf"), float("nan")])
def test_a_bad_field_is_refused_and_a_future_field_is_ignored(bad: object) -> None:
    result = tunable_config.configuration(
        {}, {"dwell.read_start": bad, "future.thing": 2, "cards.depth": 0.5}, {}
    )
    assert result.values["dwell.read_start"] == 0.35
    assert result.values["cards.depth"] == 0.5
    assert "dwell.read_start refused" in result.warnings[0]
    assert "unknown tunable future.thing" in result.warnings[1]


def test_file_selection_parse_failure_and_rule_are_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    explicit = tmp_path / "experiment.toml"
    (tmp_path / "tunables.toml").write_text("[dwell]\nread_start = 0.42")
    explicit.write_text("[dwell]\nread_start = 0.5\ntranslation_awaited = 1")
    tunable_config.load(tmp_path, explicit, {}, cohort={"dwell.read_start": 0.4})
    assert "R8:" in caplog.text and dwell.READ_START_SEC.value == 0.4
    explicit.write_text("broken = [")
    tunable_config.load(tmp_path, explicit, {})
    assert "TOMLDecodeError" in caplog.text
    assert dwell.READ_START_SEC.value == 0.35


def test_existing_reading_and_depth_use_the_new_snapshot(tmp_path: Path) -> None:
    reading = dwell.Reading(0, 0, said="word", awaited=False)
    movement = cards.Depth()
    assert reading.read_by() == 1
    path = tmp_path / "longer.toml"
    path.write_text(
        "[dwell]\nread_least = 1.5\n[cards]\ndepth = 0.6\ndepth_scales = [1, 0.95, 0.83]"
    )
    assert not tunable_config.load(tmp_path, path, {}).warnings
    assert reading.read_by() == 1.5
    assert cards.depth_scale(1) == 0.95
    movement.came(0)
    assert movement.behind(0.3) == pytest.approx(0.5)


def test_cli_validates_before_promoting_and_preserves_other_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "feature.py"
    original = b'# untouched\r\nLEAST = tunable("dwell.read_least", 1.0, "s", (0.8, 3))  # why\r\n'
    source.write_bytes(original)
    monkeypatch.setattr(tunables, "SOURCE", tmp_path)
    config = tmp_path / "override.toml"
    config.write_text("[dwell]\nread_least = 2.1")
    assert tunables.main(["promote", str(config)]) == 1
    assert source.read_bytes() == original
    assert "R6" in capsys.readouterr().err
    config.write_text("[dwell]\nread_least = 1.25")
    assert tunables.main(["check", str(config)]) == 0
    assert source.read_bytes() == original
    assert tunables.main(["promote", str(config)]) == 0
    assert source.read_bytes() == original.replace(b"1.0", b"1.25")
    assert tunables.main(["list"]) == 0
    assert "dwell.read_least" in capsys.readouterr().out


def test_no_file_does_not_import_the_toml_parser(tmp_path: Path) -> None:
    import subprocess
    import sys

    script = """from pathlib import Path
import sys
from polyglotic_desktop.tunable_config import load
assert "tomllib" not in sys.modules
load(Path(sys.argv[1]), None, {})
assert "tomllib" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True)


def test_startup_collects_every_declaration_before_loading_overrides() -> None:
    import json
    import subprocess
    import sys

    # The CLI imports its own wiring; use a fresh process to check the app
    # independently of test collection and other tests' imports.
    script = """import json
import polyglotic_desktop.main
from polyglotic_desktop.core.shared.tunables import declarations
print(json.dumps(sorted(declarations())))
"""
    found = subprocess.check_output([sys.executable, "-c", script], text=True)
    assert json.loads(found) == sorted(
        name for name, *_ in tunables.locations(tunables.SOURCE)
    )
