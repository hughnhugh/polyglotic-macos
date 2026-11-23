"""Starting at sign-in on Linux (polyglotic-hq 571): an XDG autostart entry
for the AppImage, off by default, set from Settings > App (and Home's
question), rewritten at each start while it's on so a moved file still
starts. Its folder is handed in, so these run on any OS; the packed
AppImage writing one for real is `.github/workflows/linux-manners.yml`'s."""

import sys
from pathlib import Path

import pytest

from polyglotic_desktop import main
from polyglotic_desktop.platform.linux import menu_entry
from polyglotic_desktop.platform.linux.startup import XdgAutostart, config_home

APPIMAGE = "/home/learner/Apps/Polyglotic.AppImage"


def appimage_here(
    tmp_path: Path, file: str = APPIMAGE, pack: str = "Polyglotic"
) -> dict:
    """An AppImage's environment as its runtime sets it (Velopack's manifest
    in its mount), with a config folder of the test's."""
    mount = tmp_path / "mount"
    (mount / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (mount / "usr" / "bin" / "sq.version").write_text(
        '<?xml version="1.0" encoding="utf-8"?><package xmlns="http://schemas.'
        'microsoft.com/packaging/2010/07/nuspec.xsd"><metadata>'
        f"<id>{pack}</id><version>0.0.2</version></metadata></package>",
        encoding="utf-8",
    )
    return {
        "APPIMAGE": file,
        "APPDIR": str(mount),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }


def entry_lines(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "[Desktop Entry]"
    return dict(line.split("=", 1) for line in lines[1:])


def test_off_by_default_then_on_starts_the_appimage_in_the_tray(tmp_path: Path) -> None:
    startup = XdgAutostart("/tmp/.mount_x/usr/bin/Polyglotic", appimage_here(tmp_path))
    assert (
        startup.path == tmp_path / "config/autostart/io.polyglotic.Polyglotic.desktop"
    )
    assert not startup.enabled()  # off by default: nothing written
    assert not startup.path.exists()
    startup.set_enabled(True)
    assert startup.enabled()
    said = entry_lines(startup.path)
    assert said["Exec"] == f"{APPIMAGE} --in-tray"  # the AppImage, never its mount
    assert said["TryExec"] == APPIMAGE  # a deleted AppImage: skipped at sign-in
    assert said["Type"] == "Application"
    assert said["X-GNOME-Autostart-enabled"] == "true"
    assert b"\r" not in startup.path.read_bytes()
    startup.set_enabled(False)
    assert not startup.path.exists() and not startup.enabled()
    startup.set_enabled(False)  # not there: nothing to do


@pytest.mark.parametrize(
    "off", ["Hidden=true", "X-GNOME-Autostart-enabled=false", "Hidden = True"]
)
def test_turned_off_in_the_desktop_s_own_settings_is_off(
    tmp_path: Path, off: str
) -> None:
    startup = XdgAutostart("", appimage_here(tmp_path))
    startup.set_enabled(True)
    assert startup.path is not None
    text = startup.path.read_text(encoding="utf-8").replace(
        "X-GNOME-Autostart-enabled=true", off
    )
    startup.path.write_text(text, encoding="utf-8")
    assert not startup.enabled()
    startup.follow()  # off stays off: not written back on
    assert startup.path.read_text(encoding="utf-8") == text


def test_a_moved_appimage_still_starts(tmp_path: Path) -> None:
    XdgAutostart("", appimage_here(tmp_path)).set_enabled(True)
    moved = XdgAutostart(
        "", appimage_here(tmp_path, "/home/learner/Polyglotic.AppImage")
    )
    assert moved.path is not None
    assert entry_lines(moved.path)["Exec"].startswith(APPIMAGE)
    moved.follow()  # the next start, from the new place
    assert (
        entry_lines(moved.path)["Exec"] == "/home/learner/Polyglotic.AppImage --in-tray"
    )


def test_while_off_a_start_writes_nothing(tmp_path: Path) -> None:
    startup = XdgAutostart("", appimage_here(tmp_path))
    startup.follow()
    assert startup.path is not None and not startup.path.exists()


def test_a_path_with_spaces_is_quoted(tmp_path: Path) -> None:
    file = "/home/learner/My Apps/Polyglotic.AppImage"
    startup = XdgAutostart("", appimage_here(tmp_path, file))
    startup.set_enabled(True)
    assert startup.path is not None
    assert entry_lines(startup.path)["Exec"] == f'"{file}" --in-tray'


def test_a_preview_s_pack_has_its_own_entry(tmp_path: Path) -> None:
    startup = XdgAutostart("", appimage_here(tmp_path, pack="PolygloticPreview"))
    assert startup.path is not None
    assert startup.path.name == f"{menu_entry.entry_id('PolygloticPreview')}.desktop"
    assert startup.path.name != "io.polyglotic.Polyglotic.desktop"


def test_from_source_there_is_nothing_to_start(tmp_path: Path) -> None:
    startup = XdgAutostart(sys.executable, {"XDG_CONFIG_HOME": str(tmp_path)})
    assert startup.path is None and not startup.enabled()
    startup.set_enabled(True)
    assert not startup.enabled() and not any(tmp_path.iterdir())


def test_a_folder_that_can_t_be_written_is_quietly_not_on(tmp_path: Path) -> None:
    env = appimage_here(tmp_path)
    (tmp_path / "config").write_text("a file, not a folder", encoding="utf-8")
    startup = XdgAutostart("", env)
    startup.set_enabled(True)  # the port's rule: quietly
    assert not startup.enabled()


def test_the_config_folder_is_xdg_s(tmp_path: Path) -> None:
    home = Path("/home/learner")
    assert config_home({}, home) == home / ".config"
    assert config_home({"XDG_CONFIG_HOME": "relative"}, home) == home / ".config"
    assert config_home({"XDG_CONFIG_HOME": str(tmp_path)}, home) == tmp_path


def test_linux_offers_starting_at_sign_in() -> None:
    """Before 571 Linux had none (`start_at_sign_in=None`): Home never asked
    and Settings had no switch."""
    found = main.linux_adapters()
    assert found.start_at_sign_in is not None
    made = found.start_at_sign_in(sys.executable)
    assert isinstance(made, XdgAutostart)
