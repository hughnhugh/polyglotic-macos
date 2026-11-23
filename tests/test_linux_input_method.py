"""Chinese and Japanese can be typed into the app on Linux whichever input
method the desktop runs (polyglotic-hq 571, decision 0279): the app carries
Qt's IBus plugin, not Fcitx's, so Kubuntu's `QT_IM_MODULE=fcitx` - and a
session that names none - left it with compose alone, and pinyin typed
"nihao" on GitHub's runner."""

import pytest

from polyglotic_desktop import main
from polyglotic_desktop.platform.linux import input_method
from polyglotic_desktop.platform.linux.input_method import plugins_to_try


def test_fcitx_asked_for_tries_ibus_after_it() -> None:
    assert plugins_to_try({"QT_IM_MODULE": "fcitx"}, ibus_installed=True) == {
        "QT_IM_MODULES": "fcitx;ibus"
    }


def test_without_ibus_installed_fcitx5_is_reached_as_the_portals_ibus() -> None:
    assert plugins_to_try({"QT_IM_MODULE": "fcitx5"}, ibus_installed=False) == {
        "QT_IM_MODULES": "fcitx5;ibus",
        "IBUS_USE_PORTAL": "1",
    }


def test_a_session_that_names_none_gets_ibus_where_it_is_installed() -> None:
    assert plugins_to_try({}, ibus_installed=True) == {"QT_IM_MODULES": "ibus;compose"}
    assert plugins_to_try({}, ibus_installed=False) == {}


@pytest.mark.parametrize(
    "environ",
    [
        {"QT_IM_MODULE": "ibus"},
        {"QT_IM_MODULE": "none"},
        {"QT_IM_MODULE": "xim"},
        {"QT_IM_MODULE": "fcitx", "QT_IM_MODULES": "fcitx;compose"},
    ],
)
def test_anything_else_is_as_asked(environ: dict[str, str]) -> None:
    assert plugins_to_try(environ, ibus_installed=True) == {}


def test_the_environment_gets_what_was_found() -> None:
    environ = {"QT_IM_MODULE": "fcitx"}
    added = input_method.use_carried_plugins(environ, which=lambda _name: None)
    assert added == {"QT_IM_MODULES": "fcitx;ibus", "IBUS_USE_PORTAL": "1"}
    assert environ["QT_IM_MODULES"] == "fcitx;ibus"


def test_only_x11_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def use() -> dict[str, str]:
        asked.append("asked")
        return {}

    monkeypatch.setattr(input_method, "use_carried_plugins", use)
    main.use_input_methods(None)
    main.use_input_methods("offscreen")
    assert asked == []
    main.use_input_methods("xcb")
    assert asked == ["asked"]
