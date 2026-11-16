"""The app's name on the taskbar (polyglotic-hq 245, decision 0051): Windows
groups, pins and draws a process's windows by its AppUserModelID. The
installer's start-up names the installed app first (Velopack); from source
the app names itself. Each case in a fresh Python: a process keeps its ID
for as long as it runs."""

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.windows_only  # the taskbar's ID is Windows'

NAMED = """
import json
{first}
from polyglotic_desktop.platform.windows import taskbar
before = taskbar.explicit_app_id()
named = taskbar.app_identity("Polyglotic.Test245")
print(json.dumps([before, named, taskbar.explicit_app_id()]))
"""


def _run(first: str = "") -> list[str | None]:
    """In a fresh Python, after `first`: the process's ID before, what
    `app_identity` says, and the ID after."""
    done = subprocess.run(
        [sys.executable, "-c", NAMED.format(first=first)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    found: list[str | None] = json.loads(done.stdout)
    return found


def test_from_source_the_app_names_itself() -> None:
    """python.exe has no ID of its own: Windows would group the app with
    every other Python."""
    assert _run() == [None, "Polyglotic.Test245", "Polyglotic.Test245"]


def test_installed_the_installers_name_stands() -> None:
    """Velopack's start-up has named the process from the pack - the same
    ID its shortcuts get - so the app keeps it: a rehearsal pack's own
    pack ID keeps it apart from the real app."""
    first = (
        "import ctypes; ctypes.WinDLL('shell32')"
        ".SetCurrentProcessExplicitAppUserModelID('velopack.PolygloticRehearsal')"
    )
    assert _run(first) == ["velopack.PolygloticRehearsal"] * 3


def test_a_package_keeps_its_own_id_and_sets_none() -> None:
    """The Microsoft Store's copy (decision 0056): Windows knows an MSIX
    package's app by `<family name>!<app ID>`, and a package may use no
    other - an explicit ID would make the running app and its Start pin
    two buttons. Stood in for here: this Python isn't a package."""
    first = (
        "from polyglotic_desktop.platform.windows import package;"
        " package.packaged_app_id = lambda: 'PolygloticRehearsal_x1!Polyglotic'"
    )
    assert _run(first) == [None, "PolygloticRehearsal_x1!Polyglotic", None]


def test_from_source_the_app_isnt_a_package() -> None:
    from polyglotic_desktop.platform.windows import package

    assert package.store_package() is None
    assert package.packaged_app_id() is None
