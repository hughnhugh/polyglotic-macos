"""A learner's Mac on GitHub's Mac (polyglotic-hq 523): the parts that judge,
on any OS - what a Mach-O file loads and whether a learner's Mac has it,
Gatekeeper's verdict, the quarantine a browser writes, what may be hidden.
The checks themselves run on GitHub's Mac (the macOS job's learner part)."""

import re
import struct
import sys
from pathlib import Path

import pytest

from tools import macos_learner_checks as learner

LC_LOAD_DYLIB, LC_RPATH, LC_SEGMENT_64 = 0xC, 0x8000001C, 0x19


def _command(cmd: int, name: str) -> bytes:
    text = name.encode() + b"\0"
    size = (12 + len(text) + 7) // 8 * 8
    return struct.pack("<III", cmd, size, 12) + text.ljust(size - 12, b"\0")


def macho(*names: str, rpaths: tuple[str, ...] = ()) -> bytes:
    """A thin 64-bit Mach-O with these libraries and rpaths (and a segment
    command, which is skipped)."""
    commands = [struct.pack("<II", LC_SEGMENT_64, 72) + bytes(64)]
    commands += [_command(LC_LOAD_DYLIB, n) for n in names]
    commands += [_command(LC_RPATH, r) for r in rpaths]
    body = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 6, len(commands), len(body), 0, 0
    )
    return header + body


def fat(*slices: bytes) -> bytes:
    """A universal binary of these slices (fat_arch, big-endian)."""
    head = struct.pack(">II", 0xCAFEBABE, len(slices))
    offset = 4096
    arches = b""
    data = b""
    for piece in slices:
        arches += struct.pack(
            ">iiIII", 0x0100000C, 0, offset + len(data), len(piece), 12
        )
        data += piece
    return (head + arches).ljust(offset, b"\0") + data


def test_a_mach_o_says_what_it_loads() -> None:
    found = learner.loads(
        macho(
            "@rpath/QtCore.framework/QtCore",
            "/usr/lib/libSystem.B.dylib",
            rpaths=("@loader_path/../Frameworks",),
        )
    )
    assert found == (
        ["@rpath/QtCore.framework/QtCore", "/usr/lib/libSystem.B.dylib"],
        ["@loader_path/../Frameworks"],
    )


def test_every_slice_of_a_universal_binary_is_read() -> None:
    found = learner.loads(
        fat(macho("/usr/lib/libz.1.dylib"), macho("/opt/homebrew/lib/x"))
    )
    assert found == (["/usr/lib/libz.1.dylib", "/opt/homebrew/lib/x"], [])


def test_what_isnt_a_mach_o_is_none() -> None:
    assert learner.loads(b"PK\x03\x04 a zip") is None
    # a Java class file starts 0xcafebabe too, with a version where a count is
    assert learner.loads(struct.pack(">II", 0xCAFEBABE, 0x34)) is None


@pytest.mark.parametrize(
    ("reference", "outside"),
    [
        ("@rpath/libpython3.12.dylib", False),
        ("@loader_path/../Frameworks/libssl.3.dylib", False),
        ("/usr/lib/libSystem.B.dylib", False),
        ("/System/Library/Frameworks/AVFoundation.framework/AVFoundation", False),
        ("/opt/homebrew/opt/libsndfile/lib/libsndfile.1.dylib", True),
        ("/usr/local/lib/libportaudio.2.dylib", True),
        ("/Library/Frameworks/Python.framework/Versions/3.12/Python", True),
        ("/Users/runner/.local/share/uv/python/cpython-3.12.15/lib", True),
    ],
)
def test_only_the_app_and_macos_are_where_a_learner_has_them(
    reference: str, outside: bool
) -> None:
    assert learner.outside(reference) is outside


def test_an_app_that_loads_from_homebrew_is_named_with_what(tmp_path: Path) -> None:
    app = tmp_path / "Polyglotic.app" / "Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "Frameworks").mkdir()
    (app / "MacOS" / "Polyglotic").write_bytes(macho("/usr/lib/libSystem.B.dylib"))
    (app / "Frameworks" / "_soundfile.so").write_bytes(
        macho("@rpath/x.dylib", "/opt/homebrew/lib/libsndfile.1.dylib")
    )
    (app / "Resources").mkdir()
    (app / "Resources" / "notes.txt").write_text("not a binary", encoding="utf-8")
    found = learner.linkage_of(tmp_path / "Polyglotic.app")
    assert found == {
        str(Path("Contents/Frameworks/_soundfile.so")): [
            "/opt/homebrew/lib/libsndfile.1.dylib"
        ]
    }
    (app / "Frameworks" / "_soundfile.so").write_bytes(macho("@rpath/x.dylib"))
    assert learner.linkage_of(tmp_path / "Polyglotic.app") == {}


@pytest.mark.parametrize(
    ("said", "verdict"),
    [
        ("Polyglotic.app: rejected\nsource=no usable signature", "rejected"),
        ("Polyglotic.app: rejected\nsource=Unnotarized Developer ID", "rejected"),
        ("Polyglotic.app: accepted\nsource=Notarized Developer ID", "accepted"),
        ("Polyglotic.app: a sealed resource is missing or invalid", "broken"),
        (
            "Polyglotic.app: invalid signature (code or signature have been modified)",
            "broken",
        ),
    ],
)
def test_gatekeepers_verdict_tells_a_broken_seal_from_no_developer_id(
    said: str, verdict: str
) -> None:
    assert learner.gatekeeper_said(said) == verdict


def test_the_quarantine_is_a_browsers() -> None:
    value = learner.quarantine_value(at=0x6730A1B2)
    assert re.fullmatch(r"0083;6730a1b2;Safari;[0-9A-F-]{36}", value)


def test_what_the_checks_run_on_is_never_hidden() -> None:
    kept = ["/Library/Frameworks/Python.framework/Versions/3.12"]
    assert not learner.hideable("/Library/Frameworks/Python.framework", kept)
    assert learner.hideable("/opt/homebrew", kept)


def test_the_plan_runs_anywhere_and_the_checks_only_on_a_mac(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert learner.main([str(tmp_path), "--dry-run"]) == 0
    assert "fresh_account" in capsys.readouterr().out
    if sys.platform != "darwin":
        assert learner.main([str(tmp_path), "--app", str(tmp_path)]) == 2
    # nothing hidden: nothing to put back
    assert learner.main([str(tmp_path), "--show"]) == 0
    assert "put back: nothing" in capsys.readouterr().out


def test_a_path_that_cant_be_seen_yet_isnt_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """523's first run: mid-unpacking, Archive Utility's folders couldn't
    be read, and `exists()` raised PermissionError instead of saying no."""
    assert learner.there(tmp_path)
    assert not learner.there(tmp_path / "missing")

    def refused(_self: Path, **_kw: object) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "exists", refused)
    assert not learner.there(tmp_path)


def test_the_move_is_clicked_on_the_apps_own_offer() -> None:
    """The app brought to the front by its PID, then its own button - the
    label `ui.move_to_applications` gives it - else Return."""
    from polyglotic_desktop.ui.move_to_applications import move_button

    script = learner.press_move(4321)
    assert "first process whose unix id is 4321" in script
    assert "set frontmost of p to true" in script
    assert f'click button "{move_button()}"' in script
    assert "keystroke return" in script
