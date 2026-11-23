"""The AppImage's own menu entry and icon on Linux (polyglotic-hq 561):
written by `platform/linux/menu_entry` at each start, since Velopack's
AppImage installs none. The packed app writing them for real is checked
by `tools/package/linux_update_rehearsal.sh` on GitHub's Ubuntu runner."""

from pathlib import Path

import pytest

from polyglotic_desktop.platform.linux import menu_entry

ICON = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"/>'


def appimage_here(tmp_path: Path, pack: str = "Polyglotic", title: str = "") -> dict:
    """An AppImage's environment as its runtime sets it, with Velopack's
    manifest in its mount."""
    mount = tmp_path / "mount"
    (mount / "usr" / "bin").mkdir(parents=True)
    named = f"<title>{title}</title>" if title else ""
    (mount / "usr" / "bin" / "sq.version").write_text(
        '<?xml version="1.0" encoding="utf-8"?><package xmlns="http://schemas.'
        'microsoft.com/packaging/2010/07/nuspec.xsd"><metadata>'
        f"<id>{pack}</id>{named}<version>0.0.2</version></metadata></package>",
        encoding="utf-8",
    )
    return {  # the AppImage's path is only written down, never opened
        "APPIMAGE": "/home/learner/Apps/Polyglotic.AppImage",
        "APPDIR": str(mount),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }


def identified(env: dict, tmp_path: Path) -> tuple[str, list[str]]:
    icon = tmp_path / "polyglotic.svg"
    icon.write_bytes(ICON)
    told: list[str] = []
    found = menu_entry.taskbar_identity(
        "Polyglotic.Desktop", icon, env, tmp_path / "home", told.append
    )
    return found, told


def entry_text(env: dict, name: str = "io.polyglotic.Polyglotic") -> str:
    path = Path(env["XDG_DATA_HOME"]) / "applications" / f"{name}.desktop"
    return path.read_text(encoding="utf-8")


def test_the_appimage_writes_its_own_menu_entry_and_icon(tmp_path: Path) -> None:
    """Velopack's AppImage installs nothing: no menu entry, so the app could
    only be started from the file manager (550). Each start writes it."""
    env = appimage_here(tmp_path)
    found, told = identified(env, tmp_path)
    assert found == "io.polyglotic.Polyglotic" and told == [found]
    lines = entry_text(env).splitlines()
    assert lines[0] == "[Desktop Entry]"
    assert f"Exec={env['APPIMAGE']}" in lines
    assert f"TryExec={env['APPIMAGE']}" in lines  # gone with the file
    assert "Icon=io.polyglotic.Polyglotic" in lines
    assert "StartupWMClass=Polyglotic" in lines  # Qt's class: the app's name
    assert "Name=Polyglotic" in lines
    icon = Path(env["XDG_DATA_HOME"], "icons/hicolor/scalable/apps")
    assert (icon / "io.polyglotic.Polyglotic.svg").read_bytes() == ICON


def test_a_moved_appimage_is_started_from_where_it_is_now(tmp_path: Path) -> None:
    env = appimage_here(tmp_path)
    identified(env, tmp_path)
    desktop = Path(
        env["XDG_DATA_HOME"], "applications/io.polyglotic.Polyglotic.desktop"
    )
    before = desktop.stat().st_mtime_ns
    identified(env, tmp_path)  # the same: not written again
    assert desktop.stat().st_mtime_ns == before
    env["APPIMAGE"] = env["APPIMAGE"].replace("/Apps/", "/Downloads/")
    identified(env, tmp_path)
    assert f"Exec={env['APPIMAGE']}" in entry_text(env).splitlines()


def test_a_preview_has_its_own_entry_never_the_apps(tmp_path: Path) -> None:
    env = appimage_here(tmp_path, "PolygloticPreview", "Polyglotic Preview")
    found, _ = identified(env, tmp_path)
    assert found == "io.polyglotic.PolygloticPreview"
    assert "Name=Polyglotic Preview" in entry_text(env, found).splitlines()
    assert not (
        Path(env["XDG_DATA_HOME"]) / "applications" / "io.polyglotic.Polyglotic.desktop"
    ).exists()


def test_from_source_nothing_is_written(tmp_path: Path) -> None:
    env = {"XDG_DATA_HOME": str(tmp_path / "data")}
    found, told = identified(env, tmp_path)
    assert (found, told) == ("Polyglotic.Desktop", [])
    assert not (tmp_path / "data").exists()


def test_an_entry_that_cant_be_written_doesnt_stop_the_start(tmp_path: Path) -> None:
    env = appimage_here(tmp_path)
    (tmp_path / "data").write_text("a file where the folder would go")
    found, told = identified(env, tmp_path)
    assert found == "io.polyglotic.Polyglotic" and told == [found]


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("/home/a/Polyglotic.AppImage", "/home/a/Polyglotic.AppImage"),
        ("/home/a/My Apps/P.AppImage", '"/home/a/My Apps/P.AppImage"'),
        ("/home/a/$x/P.AppImage", '"/home/a/\\\\$x/P.AppImage"'),
        ('/home/a/"q"/P.AppImage', '"/home/a/\\\\"q\\\\"/P.AppImage"'),
        ("/home/a/100%/P.AppImage", "/home/a/100%%/P.AppImage"),
    ],
)
def test_exec_quotes_the_path_as_the_spec_asks(path: str, line: str) -> None:
    """The Desktop Entry spec: a reserved character quotes the argument; a
    quote, dollar, backtick or backslash is escaped inside the quotes; a per
    cent is doubled; and the whole value is then a string, its backslashes
    doubled."""
    assert menu_entry.exec_line(path) == line


def test_a_manifest_that_cant_be_read_is_the_released_apps(tmp_path: Path) -> None:
    assert menu_entry.read_pack(tmp_path) == ("Polyglotic", "Polyglotic")
