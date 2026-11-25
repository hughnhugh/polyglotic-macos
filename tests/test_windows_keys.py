"""Esc or a click read without being taken (platform.windows.keys) - for
the new interface's settings popover, which never has the focus
(polyglotic-hq project 112). No key is pressed."""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform.windows.keys import held


def test_esc_and_the_mouse_buttons_are_read_by_name() -> None:
    assert isinstance(held("escape"), bool)
    assert isinstance(held("mouse"), bool)
    assert isinstance(held("copy"), bool)
    with pytest.raises(KeyError):
        held("space")
