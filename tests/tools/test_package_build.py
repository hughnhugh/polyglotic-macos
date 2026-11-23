"""The packaging build's own rules (decision 0016), without PyInstaller:
what may never be in the packed app, the licences collected, Windows' file
properties. The build itself runs in CI (.github/workflows/package.yml)."""

import ast
import os
import struct
import subprocess
from pathlib import Path

import pytest
from tools.package import build

from polyglotic_desktop.ui.interface_language import OFFERED


def packed(tmp_path: Path) -> Path:
    """A packed folder with every part the app needs (empty files)."""
    folder = tmp_path / "Polyglotic"
    for need in build.NEEDED:
        (folder / need).parent.mkdir(parents=True, exist_ok=True)
        (folder / need).write_bytes(b"")
    return folder


@pytest.fixture
def code(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    modules = ["polyglotic_desktop.main", "polyglotic_desktop.core.listening.timing"]
    monkeypatch.setattr(build, "archive_modules", lambda exe: modules)
    return modules


def test_a_whole_folder_has_no_problems(tmp_path: Path, code: list[str]) -> None:
    assert build.problems(packed(tmp_path)) == []


def test_a_missing_part_is_a_problem(tmp_path: Path, code: list[str]) -> None:
    folder = packed(tmp_path)
    (folder / "dictionaries" / "cedict.sqlite").unlink()
    assert build.problems(folder) == ["missing: dictionaries/cedict.sqlite"]


def test_no_environment_file_or_device_token(tmp_path: Path, code: list[str]) -> None:
    folder = packed(tmp_path)
    (folder / "_internal" / ".env").write_text("SECRET=1")
    token = "pgd_" + "A" * 43
    (folder / "_internal" / "notes.dat").write_bytes(b"\x00" + token.encode() + b"\x00")
    found = build.problems(folder)
    assert "an environment file: _internal/.env" in found
    assert "something shaped like a device token: _internal/notes.dat" in found


def test_no_tests_or_tools_in_the_code(tmp_path: Path, code: list[str]) -> None:
    code += ["tests.fakes", "tools.dictionaries.build", "polyglotic_desktop.test_x"]
    found = build.problems(packed(tmp_path))
    assert found == [
        "a test or tool in the code: tests.fakes",
        "a test or tool in the code: tools.dictionaries.build",
        "a test or tool in the code: polyglotic_desktop.test_x",
    ]


def test_the_licences_cover_every_runtime_package_and_no_dev_tool() -> None:
    names = {d.metadata["Name"].lower() for d in build.runtime_distributions()}
    for bundled in ("numpy", "onnxruntime", "pydantic", "soundfile", "websockets"):
        assert bundled in names
    assert any(name.startswith("pyside6") for name in names)
    for never in ("pytest", "mypy", "ruff", "pyinstaller", "polyglotic-desktop"):
        assert never not in names


def test_windows_file_properties_carry_the_version() -> None:
    text = build.version_info("0.1.0")
    ast.parse(text)  # PyInstaller evaluates it as Python
    assert "filevers=(0, 1, 0, 0)" in text
    assert "StringStruct('ProductVersion', '0.1.0')" in text
    assert "StringStruct('ProductName', 'Polyglotic')" in text


def test_only_packages_in_the_packed_app_have_their_licences_copied(
    tmp_path: Path,
) -> None:
    (tmp_path / "_internal" / "numpy").mkdir(parents=True)
    dists = {d.metadata["Name"].lower(): d for d in build.runtime_distributions()}
    assert build.is_bundled(dists["numpy"], tmp_path, set())
    assert build.is_bundled(dists["pydantic"], tmp_path, {"pydantic"})
    assert not build.is_bundled(dists["pydantic"], tmp_path, {"numpy"})
    assert not build.is_bundled(dists["cffi"], tmp_path, set())
    (tmp_path / "_internal" / "_cffi_backend.cp312-win_amd64.pyd").write_bytes(b"")
    assert build.is_bundled(dists["cffi"], tmp_path, set())


def test_the_icon_is_one_ico_at_windows_six_sizes(tmp_path: Path) -> None:
    """Symbol A for the exe and Velopack's installer: 16-48 px as 32-bit
    bitmaps with their mask, 256 px as PNG (project 098)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    # the widgets' application, as the view tests' (it serves the build too)
    _app = QApplication.instance() or QApplication([])
    path = tmp_path / "Polyglotic.ico"
    build.write_icon(path)
    data = path.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, 6)
    sides = []
    for i in range(count):
        width, height, _, _, planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * i
        )
        side = width or 256
        sides.append(side)
        assert (height or 256, planes, bits) == (side, 1, 32)
        image = data[offset : offset + size]
        if side == 256:
            assert image.startswith(b"\x89PNG\r\n\x1a\n")
        else:
            header, w, h = struct.unpack_from("<Iii", image)
            assert (header, w, h) == (40, side, side * 2)  # colours, then mask
            assert size == 40 + side * side * 4 + (side + 31) // 32 * 4 * side
    assert sides == [16, 20, 24, 32, 48, 256]
    assert len(data) < 60_000


def test_the_icons_masters_and_heading_faces_are_needed_in_the_packed_app() -> None:
    needed = set(build.NEEDED)
    assert "_internal/PySide6/Qt6Svg.dll" in needed
    for part in (
        "icons/polyglotic.svg",
        "icons/tray-dark-listening.svg",
        "fonts/Literata-SemiBold.ttf",
        "fonts/Literata-OFL.txt",
    ):
        assert f"_internal/polyglotic_desktop/ui/assets/{part}" in needed


def test_the_interface_translations_are_needed_though_not_committed() -> None:
    """The build compiles them (decision 0034, amended 2026-11-08), so they're
    needed whether or not this checkout has built them yet."""
    needed = [n for n in build.NEEDED if n.endswith(".qm") and "assets" in n]
    assert needed == [
        f"_internal/polyglotic_desktop/ui/assets/translations/polyglotic_{code}.qm"
        for code in OFFERED
    ]
    assert (
        "_internal/polyglotic_desktop/ui/assets/translations/polyglotic_en.qm" in needed
    )
    # Qt's own words (OK, Cancel) for each language Qt has them in (294)
    qts = [n for n in build.NEEDED if "qtbase_" in n]
    assert qts == [
        f"_internal/PySide6/translations/qtbase_{code}.qm"
        for code in build.QT_LANGUAGES
    ]


@pytest.mark.windows_only
def test_the_package_keeps_qts_own_words_for_the_languages_qt_has() -> None:
    """Qt's words (OK, Cancel) are found where Windows' PySide6 keeps them,
    beside lrelease - the folder the packed app copies (294). Linux's wheel
    keeps them elsewhere, and the app is packed on Windows only."""
    assert {"zh_CN", "zh_TW", "es", "ja"} <= set(build.QT_LANGUAGES)
    assert not {"th", "vi", "id", "fil"} & set(build.QT_LANGUAGES)


def test_the_packed_apps_check_has_a_data_folder_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The build runs as the user on their PC (the self-hosted runner), so
    the packed app's check gets a fresh data folder under the build's own
    work folder, never the account's %APPDATA%\\Polyglotic (polyglotic-hq
    242): what a run before left there is gone first."""
    work = tmp_path / "work"
    left = work / "check-install-data" / "learning-zh.sqlite"
    left.parent.mkdir(parents=True)
    left.write_bytes(b"from an earlier build")
    started: list[list[str]] = []

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        started.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(build, "WORK", work)
    monkeypatch.setattr(build.subprocess, "run", run)
    build.check_install(tmp_path / "Polyglotic")
    (argv,) = started
    assert argv[argv.index("--data") + 1] == str(work / "check-install-data")
    assert (work / "check-install-data").is_dir()
    assert not left.exists()


def test_a_mac_judges_the_start_after_macos_first_look_at_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """polyglotic-hq 419: a newly signed app's first launch on a Mac carries
    Gatekeeper's first look (1.775 s on GitHub's Mac), once per build; that
    launch settles the app and is kept, the second is judged. Windows
    launches once, as before."""
    launches = iter([1.775, 0.82, 0.9])

    def check(folder: Path, layout: object = None) -> dict[str, object]:
        return {"exit_code": 0, "launch_seconds": next(launches), "version": "0.0.1"}

    monkeypatch.setattr(build, "check_install", check)
    judged = build.settled_check_install(Path("dist/Polyglotic.app"), build.MACOS)
    assert judged["launch_seconds"] == 0.82
    assert judged["first_launch"] == {
        "exit_code": 0,
        "launch_seconds": 1.775,
        "window_seconds": None,
        "wall_seconds": None,
    }
    assert build.over_start_budget(judged) == []
    assert build.first_launch_failed(judged) == []
    windows = build.settled_check_install(Path("dist/Polyglotic"), build.WINDOWS)
    assert windows["launch_seconds"] == 0.9 and "first_launch" not in windows
    assert build.first_launch_failed({"first_launch": {"exit_code": 1}}) == [
        "the first launch failed: {'exit_code': 1}"
    ]


def test_a_packed_window_over_its_budget_is_a_problem() -> None:
    """The packed app's main window within START_PACKED (DECISIONS.md #53;
    polyglotic-hq project 132), timed by its own install check."""
    assert build.over_start_budget({"launch_seconds": 0.7, "window_seconds": 0.2}) == []
    # the person's wait counts from the launch, not from the check's start
    # (polyglotic-hq 243): a window quick after the imports but slow to launch
    # is over
    assert build.over_start_budget({"launch_seconds": 1.2, "window_seconds": 0.3}) == [
        "the main window took 1.2 s from launch, over 1000 ms"
    ]
    assert build.over_start_budget({"window_seconds": 0.4}) == []
    assert build.over_start_budget({"window_seconds": 1.6}) == [
        (
            "the main window took 1.6 s from the check's start (launch time unread),"
            " over 1000 ms"
        )
    ]
    assert build.over_start_budget({}) == [
        "--check-install didn't time the main window"
    ]


def test_githubs_mac_holds_the_start_to_a_ceiling_of_its_own() -> None:
    """Decision 0193 (polyglotic-hq 420): GitHub's Mac VM settled the same
    code at 1.051 s and 1.627 s (419's runs 2 and 3). On that runner only,
    the start is held to 2.5 s - a doubling still fails - and the 1000 ms
    budget stays for a person's Mac and for Windows."""
    github = {"RUNNER_ENVIRONMENT": "github-hosted"}
    assert build.start_limit_ms(build.MACOS, github) == 2500
    assert build.start_limit_ms(build.MACOS, {}) == 1000
    assert (
        build.start_limit_ms(build.MACOS, {"RUNNER_ENVIRONMENT": "self-hosted"}) == 1000
    )
    assert build.start_limit_ms(build.WINDOWS, github) == 1000
    run3: dict[str, object] = {"launch_seconds": 1.627, "window_seconds": 0.816}
    assert (
        build.over_start_budget(run3, build.start_limit_ms(build.MACOS, github)) == []
    )
    assert build.over_start_budget(run3, build.start_limit_ms(build.MACOS, {})) == [
        "the main window took 1.627 s from launch, over 1000 ms"
    ]
    assert build.over_start_budget({"launch_seconds": 3.3}, 2500) == [
        "the main window took 3.3 s from launch, over 2500 ms"
    ]


def test_the_installer_gives_the_app_and_its_shortcuts_one_taskbar_id() -> None:
    """Decision 0057 (polyglotic-hq 245's option A): Velopack names the
    installed app's process and its Start-menu and desktop shortcuts by the
    pack's `--aumid`. Without it the shortcuts had no ID and the process
    `velopack.Polyglotic`, so a pinned shortcut and the running app were two
    buttons. The ID is the pack ID's `.Desktop` - the app's own from source
    (main.TASKBAR_ID) - so a rehearsal's own pack ID changes it too."""
    from polyglotic_desktop.main import TASKBAR_ID

    script = (Path(build.__file__).parent / "pack.sh").read_text(encoding="utf-8")
    pack_id = next(
        line.removeprefix("id=")
        for line in script.splitlines()
        if line.startswith("id=")
    )
    assert '--packId "$id"' in script
    assert '--aumid "$id.Desktop"' in script
    assert f"{pack_id}.Desktop" == TASKBAR_ID


def test_every_pack_of_a_version_carries_its_release_notes() -> None:
    """Decision 0090 (polyglotic-hq 299): the feed carries each version's
    notes (`vpk pack --releaseNotes`), and the app's offer to restart into
    an update shows their first lines. The build and each promotion pass
    the same notes - a promotion's manifest must be the build's but for the
    channel (`promote compare`)."""
    script = (Path(build.__file__).parent / "pack.sh").read_text(encoding="utf-8")
    assert "notes=${6:-}" in script
    assert '${notes:+--releaseNotes "$notes"}' in script
    repo = Path(build.__file__).parents[2]
    action = (repo / ".github" / "actions" / "build-and-pack" / "action.yml").read_text(
        encoding="utf-8"
    )
    release = (repo / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    for text in (action, release):
        packs = [
            line for line in text.splitlines() if "bash tools/package/pack.sh" in line
        ]
        assert packs and all(line.rstrip().endswith('"$notes"') for line in packs)
        assert 'python -m tools.package.release_notes "$TAG" --out "$notes"' in text


def test_a_downloaded_pack_must_work_in_the_packed_app_without_simplemma() -> None:
    """Decision 0123 (polyglotic-hq 327): the release build's check tries a
    pack, and fails a build that can't open one, or that carries simplemma."""
    tried = {"unpacked": True, "opened": True, "found": "рука", "simplemma": False}
    assert build.packs_as_decided({"dictionary_pack": tried}) == []
    assert build.packs_as_decided(
        {"dictionary_pack": {**tried, "simplemma": True}}
    ) == ["simplemma is in the build: decision 0123 keeps it out"]
    assert build.packs_as_decided({}) == [
        "--check-install didn't try a dictionary pack"
    ]


def test_packs_go_in_the_installer_only_when_asked(tmp_path: Path) -> None:
    """Decision 0124: `--packs ru` copies both of Russian's files and its
    credits, each stamped with the build's version; nothing otherwise."""
    from tests.packs_storage import tiny_pack

    from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary

    built = tmp_path / "built"
    tiny_pack(built)
    tiny_pack(built, meanings="zh")
    folder = tmp_path / "Polyglotic" / "dictionaries" / build.IN_THE_INSTALLER
    copied = build.bundle_packs(["ru"], built, folder, "0.1.5")
    assert sorted(p.name for p in folder.iterdir()) == [
        "wiktru-zh.sqlite",
        "wiktru.CREDITS.md",
        "wiktru.sqlite",
    ]
    for path in copied:
        file = SqliteDictionary(path)
        assert file.info["pack_version"] == "0.1.5"
        file.close()
    with pytest.raises(FileNotFoundError):
        build.bundle_packs(["es"], built, folder, "0.1.5")


def test_a_linux_build_carries_qts_x11_plugin_and_libxcb_cursor(
    tmp_path: Path, code: list[str]
) -> None:
    """polyglotic-hq 550 (547's spike): Qt's X11 plugin can't load without
    libxcb-cursor, which no desktop is sure to have - the app would exit at
    once, saying so only to a terminal. Both are needed in the build."""
    needed = build.needed(build.LINUX)
    assert "Polyglotic" in needed
    assert "_internal/PySide6/Qt/plugins/platforms/libqxcb.so" in needed
    assert "_internal/libxcb-cursor.so.0" in needed
    # 571: without IBus's input method plugin, nothing but Latin letters
    # could be typed into the app's boxes
    contexts = "_internal/PySide6/Qt/plugins/platforminputcontexts"
    assert f"{contexts}/libibusplatforminputcontextplugin.so" in needed
    assert f"{contexts}/libcomposeplatforminputcontextplugin.so" in needed
    assert "_internal/PySide6/Qt/lib/libQt6DBus.so.6" in needed
    # 574: without Qt's portal theme, Save transcript and the export for
    # Anki opened Qt's own dialog, never the desktop's (decision 0280)
    themes = "_internal/PySide6/Qt/plugins/platformthemes"
    assert f"{themes}/libqxdgdesktopportal.so" in needed
    # 647: without Qt's SVG imageformat plugin, checked checkboxes drew solid
    # accent squares with no tick (644 bug 1)
    assert "_internal/PySide6/Qt/plugins/imageformats/libqsvg.so" in needed
    assert "_internal/PySide6/Qt/plugins/iconengines/libqsvgicon.so" in needed
    folder = tmp_path / "Polyglotic"
    for need in needed:
        (folder / need).parent.mkdir(parents=True, exist_ok=True)
        (folder / need).write_bytes(b"")
    assert build.problems(folder, build.LINUX) == []
    (folder / "_internal" / "libxcb-cursor.so.0").unlink()
    assert build.problems(folder, build.LINUX) == [
        "missing: _internal/libxcb-cursor.so.0"
    ]


def test_a_linux_build_leaves_fontconfig_and_freetype_to_the_system(
    tmp_path: Path, code: list[str]
) -> None:
    """547: Ubuntu 22.04's fontconfig, bundled, complained 45 times at each
    start on Fedora; the system's own reads the system's own settings."""
    folder = tmp_path / "Polyglotic"
    for need in build.needed(build.LINUX):
        (folder / need).parent.mkdir(parents=True, exist_ok=True)
        (folder / need).write_bytes(b"")
    for name in ("libfontconfig.so.1", "libfreetype.so.6"):
        (folder / "_internal" / name).write_bytes(b"")
    assert build.problems(folder, build.LINUX) == [
        "the system's own, bundled: _internal/libfontconfig.so.1",
        "the system's own, bundled: _internal/libfreetype.so.6",
    ]
    spec = build.SPEC.read_text(encoding="utf-8")
    assert r'LINUX_SYSTEM = [r"^libfontconfig\.so", r"^libfreetype\.so"]' in spec


def test_linux_is_packed_as_one_unversioned_appimage() -> None:
    """One file, Polyglotic.AppImage, at every version: where the learner
    keeps it, and anything pointing at it, survive each update."""
    script = (Path(build.__file__).parent / "pack.sh").read_text(encoding="utf-8")
    linux = script[script.index("linux-*)") :]
    linux = linux[: linux.index(";;")]
    assert "--runtime linux-x64" in linux and "--mainExe Polyglotic " in linux
    assert 'mv -f "$outdir/$id-$channel.AppImage" "$outdir/$id.AppImage"' in linux
    assert "--aumid" not in linux  # Windows' taskbar ID only
