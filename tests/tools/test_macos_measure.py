"""What the macOS job measures for Mac capture (polyglotic-hq 410): the
commands, the permission row's form and the summary - here on any OS; the
commands themselves run on GitHub's macOS machine."""

import json
from pathlib import Path

from tools import macos_measure


def test_the_permission_row_has_the_images_seventeen_columns() -> None:
    row = macos_measure.grant("io.polyglotic.desktop", 0, 1_700_000_000)
    values = row[row.index("(") + 1 : row.rindex(")")]
    assert len(values.split(",")) == 17
    assert values.startswith("'kTCCServiceAudioCapture','io.polyglotic.desktop',0,2,")


def test_core_audio_is_restarted_and_nothing_is_stopped_by_name() -> None:
    steps = macos_measure.plan(Path("dist/Polyglotic.app"), 0)
    commands = [" ".join(command) for _, command, _ in steps]
    assert any(
        "launchctl kickstart -k system/com.apple.audio.coreaudiod" in c
        for c in commands
    )
    assert not [
        c for c in commands if c.startswith(("killall", "pkill", "sudo killall"))
    ]
    assert "app_requirement" in [name for name, _, _ in steps]
    assert "app_requirement" not in [name for name, _, _ in macos_measure.plan(None, 0)]


def test_the_summary_says_what_411_needs() -> None:
    devices = {"SPAudioDataType": [{"_items": [{"_name": "BlackHole 2ch"}]}]}
    read = {"ok": True, "out": "kTCCServiceAudioCapture|x|2"}
    steps = {
        "devices_before": {"ok": True, "out": json.dumps({"SPAudioDataType": []})},
        "devices_after": {"ok": True, "out": json.dumps(devices)},
        "tcc_system_write_agent": {"ok": True, "out": ""},
        "tcc_system_read_agent": read,
        "tcc_user_write_app": {
            "ok": False,
            "said": "attempt to write a readonly database",
        },
        "tcc_user_read_app": {"ok": True, "out": ""},
    }
    summary = macos_measure.summary(steps)
    assert summary["devices_before"] == []
    assert summary["blackhole"] is True
    assert summary["system_audio_grant_written"] == {
        "system_agent": True,
        "system_app": False,
        "user_agent": False,
        "user_app": False,
    }


def test_a_dry_run_only_prints(capsys: object) -> None:
    assert macos_measure.main(["unused.json", "--dry-run"]) == 0
    assert not Path("unused.json").exists()
