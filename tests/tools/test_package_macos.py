"""The macOS side of packing (polyglotic-hq 410): the app bundle's layout,
its icon and Info.plist, Qt's cocoa plugin kept, and the packed app finding
the build's files in the bundle's Resources. Checked here on any OS; the
bundle itself is built and started on GitHub's macOS machine
(.github/workflows/macos.yml)."""

import ast
import plistlib
import re
import struct
from pathlib import Path

import pytest
from tools.package import build

from polyglotic_desktop.main import beside_the_app

SPEC = Path(build.__file__).with_name("polyglotic.spec")


def test_the_build_s_files_sit_beside_the_exe_on_windows_and_in_resources_on_macos(
    tmp_path: Path,
) -> None:
    """Contents/MacOS holds only code: a file there breaks the bundle's
    signature, so the dictionaries, notices and release notes go in
    Contents/Resources, where the packed app looks for them."""
    exe = tmp_path / "Polyglotic" / "Polyglotic.exe"
    assert beside_the_app(exe) == tmp_path / "Polyglotic"
    app = tmp_path / "Polyglotic.app"
    assert beside_the_app(app / "Contents" / "MacOS" / "Polyglotic") == (
        app / "Contents" / "Resources"
    )
    assert build.MACOS.beside == "Contents/Resources"
    assert build.MACOS.executable == "Contents/MacOS/Polyglotic"


def packed_app(tmp_path: Path) -> Path:
    """An app bundle with every part the app needs (empty files)."""
    folder = tmp_path / "Polyglotic.app"
    for need in build.needed(build.MACOS):
        (folder / need).parent.mkdir(parents=True, exist_ok=True)
        (folder / need).write_bytes(b"")
    return folder


def test_a_whole_app_bundle_has_no_problems_and_a_missing_part_is_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        build, "archive_modules", lambda exe: ["polyglotic_desktop.main"]
    )
    folder = packed_app(tmp_path)
    assert build.problems(folder, build.MACOS) == []
    (folder / "Contents/Resources/dictionaries/cedict.sqlite").unlink()
    assert build.problems(folder, build.MACOS) == [
        "missing: Contents/Resources/dictionaries/cedict.sqlite"
    ]


def test_the_app_bundle_needs_qts_cocoa_plugin_and_its_own_libraries() -> None:
    needed = build.needed(build.MACOS)
    code = "Contents/Frameworks/"
    assert f"{code}PySide6/Qt/plugins/platforms/libqcocoa.dylib" in needed
    assert f"{code}PySide6/Qt/lib/QtSvg.framework" in needed
    assert f"{code}_soundfile_data/libsndfile_arm64.dylib" in needed
    assert f"{code}polyglotic_desktop/release.json" in needed
    assert not [n for n in needed if n.endswith(".dll") or "_internal" in n]


def drop_patterns(linux: bool = False) -> list[str]:
    """The spec's DROP, evaluated as PyInstaller would for Mandarin - on
    Linux (`linux`), or elsewhere."""
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    (value,) = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DROP" for t in node.targets)
    ]
    found = eval(  # the spec's own expression, nothing else
        compile(ast.Expression(value), str(SPEC), "eval"),
        {
            "re": re,
            "QT_LANGUAGES": ["zh_CN"],
            "INPUT_METHODS": "" if linux else "|platforminputcontexts",
            "PLATFORM_THEMES": "" if linux else "|platformthemes",
        },
    )
    assert isinstance(found, list)
    return found


@pytest.mark.parametrize(
    ("path", "kept"),
    [
        ("PySide6/Qt/plugins/platforms/libqcocoa.dylib", True),
        ("PySide6/Qt/plugins/platforms/libqoffscreen.dylib", True),
        ("PySide6/Qt/plugins/platforms/libqminimal.dylib", False),
        ("PySide6/Qt/plugins/styles/libqmacstyle.dylib", True),
        ("PySide6/Qt/plugins/imageformats/libqsvg.dylib", True),
        ("PySide6/Qt/plugins/iconengines/libqsvgicon.dylib", True),
        ("PySide6/Qt/plugins/imageformats/libqjpeg.dylib", False),
        ("PySide6/Qt/translations/qtbase_zh_CN.qm", True),
        ("PySide6/Qt/translations/qtbase_de.qm", False),
        # Windows' as before
        ("PySide6/plugins/platforms/qwindows.dll", True),
        ("PySide6/plugins/platforms/qminimal.dll", False),
        ("PySide6/plugins/imageformats/qsvg.dll", True),
        ("PySide6/plugins/iconengines/qsvgicon.dll", True),
        ("PySide6/plugins/imageformats/qjpeg.dll", False),
        ("PySide6/translations/qtbase_zh_CN.qm", True),
    ],
)
def test_the_spec_keeps_cocoa_and_drops_what_it_drops_on_windows(
    path: str, kept: bool
) -> None:
    dropped = any(re.search(pattern, path) for pattern in drop_patterns())
    assert dropped is not kept


@pytest.mark.parametrize(
    ("path", "on_linux", "elsewhere"),
    [
        ("PySide6/Qt/plugins/platformthemes/libqxdgdesktopportal.so", True, False),
        ("PySide6/Qt/plugins/platformthemes/libqgtk3.so", False, False),
        (
            "PySide6/Qt/plugins/platforminputcontexts/libibusplatforminputcontextplugin.so",
            True,
            False,
        ),
        ("PySide6/Qt/plugins/platforms/libqxcb.so", True, True),
    ],
)
def test_the_spec_keeps_the_portals_theme_on_linux_only(
    path: str, on_linux: bool, elsewhere: bool
) -> None:
    """574 (decision 0280): Linux's package keeps Qt's portal theme, for the
    desktop's own file dialogs, and no other theme - GTK 3's would load the
    system's GTK beside the app's own GLib."""
    for linux, kept in ((True, on_linux), (False, elsewhere)):
        dropped = any(re.search(p, path) for p in drop_patterns(linux))
        assert dropped is not kept, (path, linux)


def test_the_spec_makes_an_app_bundle_on_macos_only() -> None:
    spec = SPEC.read_text(encoding="utf-8")
    assert "if MACOS:\n    INFO = json.loads" in spec
    assert 'name="Polyglotic.app"' in spec
    assert 'target_arch="arm64" if MACOS else None' in spec


def test_the_info_plist_asks_for_the_mic_and_system_audio_in_our_words() -> None:
    """Without these, macOS ends the app when it touches the microphone or
    a tap. The identifier keeps the learner's permissions (decision 0186)."""
    info = build.info_plist("0.2.0")
    assert info["CFBundleIdentifier"] == "io.polyglotic.desktop"
    assert info["CFBundleShortVersionString"] == "0.2.0"
    assert info["LSMinimumSystemVersion"] == "14.2"  # Core Audio taps
    assert str(info["NSMicrophoneUsageDescription"]).startswith("Polyglotic ")
    assert str(info["NSAudioCaptureUsageDescription"]).startswith("Polyglotic ")
    plistlib.dumps(info)  # what PyInstaller writes it as


def test_the_packed_app_is_an_accessory_from_its_start() -> None:
    """No Dock icon: a window first shown while an app is in the Dock never
    joins a full-screen app's Space (polyglotic-hq 429, decision 0201)."""
    assert build.info_plist("0.2.0")["LSUIElement"] is True


def test_the_icon_is_one_icns_of_pngs() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    data = build.icns({b"ic07": png, b"ic08": png + b"y"})
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)
    first = struct.unpack(">I", data[12:16])[0]
    assert data[8:12] == b"ic07" and first == 8 + len(png)
    assert data[8 + first : 12 + first] == b"ic08"
    assert set(build.ICNS_TYPES) == {32, 64, 128, 256, 512, 1024}


def test_the_app_bundle_needs_captures_native_libraries() -> None:
    """polyglotic-hq 411, 412: without catap's Core Audio library nothing
    the Mac plays is heard, and without PortAudio's the mic isn't; each is
    loaded from beside its package's code, where the spec puts it."""
    needed = build.needed(build.MACOS)
    code = "Contents/Frameworks/"
    assert f"{code}catap/native/libcatap_coreaudio.dylib" in needed
    assert f"{code}_sounddevice_data/portaudio-binaries/libportaudio.dylib" in needed
    assert not [
        n for n in build.needed(build.WINDOWS) if "catap" in n or "sounddevice" in n
    ]
    spec = SPEC.read_text(encoding="utf-8")
    assert 'NATIVE = collect_dynamic_libs("catap")' in spec
    assert "binaries=NATIVE," in spec


@pytest.mark.parametrize(
    ("path", "kept"),
    [
        ("_sounddevice_data/portaudio-binaries/libportaudio.dylib", True),
        ("_sounddevice_data/portaudio-binaries/libportaudio64bit.dll", False),
        ("_sounddevice_data/portaudio-binaries/libportaudioarm64-asio.dll", False),
        ("catap/native/libcatap_coreaudio.dylib", True),
    ],
)
def test_the_mac_bundle_keeps_portaudio_for_the_mac_only(path: str, kept: bool) -> None:
    """sounddevice's macOS wheel carries Windows' PortAudio DLLs too."""
    dropped = any(re.search(pattern, path) for pattern in drop_patterns())
    assert dropped is not kept


def test_portaudios_licence_goes_with_the_app_that_bundles_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sounddevice's wheel names PortAudio's licence but has no text of it."""
    monkeypatch.setattr(build, "archive_modules", lambda exe: [])
    monkeypatch.setattr(build, "runtime_distributions", list)
    mac = tmp_path / "Polyglotic.app"
    (mac / "Contents/Frameworks/_sounddevice_data/portaudio-binaries").mkdir(
        parents=True
    )
    copied = build.copy_licences(mac, build.MACOS)
    text = (mac / "Contents/Resources/licenses/PortAudio/LICENSE.txt").read_text(
        encoding="utf-8"
    )
    assert (
        "Ross Bencina and Phil Burk" in text and "Permission is hereby granted" in text
    )
    assert {
        "name": "PortAudio",
        "version": "19.7.0",
        "licence": "MIT",
        "files": 1,
    } in copied
    windows = tmp_path / "Polyglotic"
    (windows / "_internal").mkdir(parents=True)
    build.copy_licences(windows, build.WINDOWS)
    assert not (windows / "licenses" / "PortAudio").exists()


# Signing with the release's certificate, and the release's zip
# (polyglotic-hq 422, decision 0196).


def _codesign(said: dict[str, str], failing: tuple[str, ...] = ()) -> object:
    """A stand-in for subprocess.run on codesign: records each command,
    fails the ones whose flag is in `failing`, and says `said[flag]` on
    stderr."""
    commands: list[list[str]] = []

    class Done:
        def __init__(self, args: list[str]) -> None:
            flag = args[1]
            self.returncode = 1 if flag in failing else 0
            self.stdout = (
                "designated => identifier x" if "--requirements" in args else ""
            )
            self.stderr = said.get(flag, "")

    def run(args: list[str], **kwargs: object) -> Done:
        commands.append(list(args))
        return Done(args)

    run.commands = commands  # type: ignore[attr-defined]
    return run


def test_with_a_certificate_the_bundle_is_signed_with_it_and_its_authority_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _codesign(
        {
            "--display": "Identifier=io.polyglotic.desktop\nAuthority=Polyglotic Mac Signing\n"
        }
    )
    monkeypatch.setattr(build.subprocess, "run", run)
    monkeypatch.setenv("POLYGLOTIC_CODESIGN_IDENTITY", "ABCDEF0123")
    signature = build.sign(tmp_path / "Polyglotic.app")
    first = run.commands[0]  # type: ignore[attr-defined]
    assert first[:5] == ["codesign", "--force", "--deep", "--sign", "ABCDEF0123"]
    assert "--timestamp=none" in first
    assert signature["authority"] == ["Polyglotic Mac Signing"]
    assert signature["ad_hoc"] is False
    assert build.signature_problems(signature) == []


def test_ad_hoc_without_a_certificate_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _codesign(
        {"--display": "Identifier=io.polyglotic.desktop\nSignature=adhoc\n"}
    )
    monkeypatch.setattr(build.subprocess, "run", run)
    monkeypatch.delenv("POLYGLOTIC_CODESIGN_IDENTITY", raising=False)
    signature = build.sign(tmp_path / "Polyglotic.app")
    first = run.commands[0]  # type: ignore[attr-defined]
    assert first == [
        "codesign",
        "--force",
        "--deep",
        "--sign",
        "-",
        str(tmp_path / "Polyglotic.app"),
    ]
    assert signature["ad_hoc"] is True and signature["authority"] == []
    assert build.signature_problems(signature) == []


def test_a_certificate_that_didnt_take_is_a_problem_though_the_bundle_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PyInstaller's ad-hoc signature is underneath, so the bundle still
    verifies when signing with the certificate fails: that has to fail the
    build, or a release ships ad hoc and every learner is asked again."""
    run = _codesign({"--force": "errSecInternalComponent"}, failing=("--force",))
    monkeypatch.setattr(build.subprocess, "run", run)
    monkeypatch.setenv("POLYGLOTIC_CODESIGN_IDENTITY", "ABCDEF0123")
    signature = build.sign(tmp_path / "Polyglotic.app")
    assert signature["verified"] is True
    found = build.signature_problems(signature)
    assert any(
        "couldn't sign" in f and "errSecInternalComponent" in f for f in found
    ), found
    assert any("signed ad hoc although" in f for f in found), found
