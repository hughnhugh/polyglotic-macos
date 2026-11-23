r"""Chinese and Japanese typed into the app's own box on Linux, through the
desktop's input method (polyglotic-hq 546 section 1.7, 571): on GitHub's
runner, on X11, inside a session where an input method framework runs -
IBus with a pinyin and a Japanese engine, or Fcitx5 with pinyin - and Qt
reads it through its input method plugin (`QT_IM_MODULE`).

    python -m tools.linux_typing_check OUT MODE [--app-env]

Shows the app's Words page, as the UI lab builds it (made-up words), in a
real window; puts the keyboard in its search box; sets the engine; and
presses the keys a learner would - `xdotool`, through the X server, as a
keyboard does - then reads what the box holds. MODE says which input
method runs and what the session asked Qt for (the session script sets
it): `ibus...` types "nihao" and Space with IBus's pinyin (libpinyin) and
wants 你好 - plain `ibus` also "nihongo", Space and Enter with a Japanese
engine (Anthy, else Mozc) and wants 日本語, or its kana at least;
`fcitx5...` the same pinyin with Fcitx5's. `--app-env`: the environment
as the app sets it before Qt starts (`platform/linux/input_method`), not
as the session left it.

OUT gets `checks.json` (checks and facts, as `tools.app_tour`'s) and the
window's own picture after each typing (`grab()`, never the screen's).
Exit 0 when every check passed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

HAN = range(0x4E00, 0xA000)
KANA = range(0x3040, 0x3100)


@dataclass(frozen=True)
class Attempt:
    """One way to type a case: the commands that set the engine first (each
    an argument list), then xdotool's key presses, in order."""

    engine: tuple[tuple[str, ...], ...]
    keys: tuple[str, ...]


@dataclass(frozen=True)
class Case:
    name: str
    wanted: str
    """The text a learner means: the check passes when the box holds it."""
    attempts: tuple[Attempt, ...]
    accept_kana: bool = False
    """Japanese: kana typed, not converted, still counts as typed - the
    conversion is the engine's, not the app's."""
    notes: dict[str, str] = field(default_factory=dict)


PINYIN = tuple("nihao") + ("space",)
JAPANESE = tuple("nihongo") + ("space", "Return")

IBUS = (
    Case("pinyin", "你好", (Attempt((("ibus", "engine", "libpinyin"),), PINYIN),)),
    Case(
        "japanese",
        "日本語",
        (
            Attempt((("ibus", "engine", "anthy"),), JAPANESE),
            Attempt((("ibus", "engine", "mozc-jp"),), JAPANESE),
            # Mozc may start in direct input: its own keys turn it on
            Attempt((("ibus", "engine", "mozc-jp"),), ("Zenkaku_Hankaku", *JAPANESE)),
            Attempt((("ibus", "engine", "mozc-jp"),), ("Hiragana_Katakana", *JAPANESE)),
        ),
        accept_kana=True,
    ),
)
FCITX5 = (
    Case("pinyin", "你好", (Attempt((("fcitx5-remote", "-s", "pinyin"),), PINYIN),)),
    Case(
        "japanese",
        "日本語",
        (Attempt((("fcitx5-remote", "-s", "mozc"),), JAPANESE),),
        accept_kana=True,
    ),
)


def cases(mode: str) -> tuple[Case, ...]:
    """What `mode` types: IBus's pinyin (and Japanese, plain `ibus`), or
    Fcitx5's pinyin."""
    if mode == "ibus":
        return IBUS
    if mode.startswith("ibus-"):
        return IBUS[:1]
    if mode == "fcitx5":
        return FCITX5
    if mode.startswith("fcitx5-"):
        return FCITX5[:1]
    raise ValueError(f"571: no cases for {mode!r}")


RESULTS: dict[str, Any] = {"checks": [], "facts": {}, "pictures": []}


def check(name: str, ok: object, detail: object = "") -> bool:
    RESULTS["checks"].append(
        {"check": name, "ok": bool(ok), "detail": str(detail)[:800]}
    )
    print(f"[{'pass' if ok else 'FAIL'}] {name} {str(detail)[:200]}", flush=True)
    return bool(ok)


def typed(text: str, case: Case) -> bool:
    """Whether the box holds what the case means to type."""
    if case.wanted in text:
        return True
    return case.accept_kana and any(ord(c) in KANA for c in text)


def han_or_kana(text: str) -> bool:
    return any(ord(c) in HAN or ord(c) in KANA for c in text)


def input_plugins() -> list[str]:
    """The input method plugins this process has loaded (its memory map)."""
    try:
        maps = Path("/proc/self/maps").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = {
        line.split()[-1].rsplit("/", 1)[-1]
        for line in maps.splitlines()
        if "platforminputcontexts" in line
    }
    return sorted(found)


def run(out: Path, im: str, app_env: bool) -> int:
    from PySide6.QtWidgets import QApplication, QScrollArea

    from polyglotic_desktop.ui import interface_language
    from polyglotic_desktop.ui_next import style
    from polyglotic_desktop.ui_next.words_page import WordsPage
    from tools.ui_lab.lab import Lab
    from tools.ui_lab.pages import made_up_tools, window_with

    out.mkdir(parents=True, exist_ok=True)
    if app_env:  # as `main.use_input_methods` sets it, before Qt starts
        from polyglotic_desktop.platform.linux import input_method

        RESULTS["facts"]["app_env_added"] = input_method.use_carried_plugins()
    app = QApplication(["polyglotic-typing-check"])
    interface_language.install(app, interface_language.ENGLISH)
    style.use_interface_language(interface_language.ENGLISH)
    lab = Lab(app, out)
    tools = made_up_tools(40)
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    window = window_with(lab, "words", page)
    window.go_to("words")
    box = page.first.search

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            lab.pump()
            time.sleep(0.02)

    RESULTS["facts"] |= {
        "im": im,
        "QT_IM_MODULE": os.environ.get("QT_IM_MODULE", ""),
        "QT_IM_MODULES": os.environ.get("QT_IM_MODULES", ""),
        "IBUS_USE_PORTAL": os.environ.get("IBUS_USE_PORTAL", ""),
        "ibus_daemon_installed": bool(__import__("shutil").which("ibus-daemon")),
        "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", ""),
        "qt": __import__("PySide6.QtCore").QtCore.qVersion(),
    }
    code = 0
    for case in cases(im):
        done = ""
        for n, attempt in enumerate(case.attempts):
            box.clear()
            window.raise_()
            window.activateWindow()
            box.setFocus()
            pump(1.0)
            for command in attempt.engine:
                said = subprocess.run(
                    command, capture_output=True, text=True, timeout=20, check=False
                )
                RESULTS["facts"][f"{case.name}.{n}.{command[0]}"] = (
                    f"{' '.join(command)} -> {said.returncode} "
                    f"{(said.stdout + said.stderr).strip()[:200]}"
                )
            pump(1.0)
            for key in attempt.keys:
                pressing = subprocess.Popen(["xdotool", "key", "--clearmodifiers", key])
                while pressing.poll() is None:
                    pump(0.05)
                pump(0.25)
            pump(2.0)
            done = box.text()
            RESULTS["facts"][f"{case.name}.{n}.typed"] = done
            if typed(done, case):
                break
        RESULTS["facts"]["focus_in_box"] = QApplication.focusWidget() is box
        if not check(
            f"{im}: {case.name} typed into Words' search box",
            typed(done, case),
            f"wanted {case.wanted!r}, the box holds {done!r}",
        ):
            code = 1
        name = f"typing-{im}-{case.name}"
        scrolled = (
            page.findChild(QScrollArea) if not isinstance(page, QScrollArea) else page
        )
        if scrolled is not None:
            scrolled.ensureWidgetVisible(box, 50, 200)
        pump(0.5)
        window.grab().save(str(out / f"{name}.png"))
        holder = box.parentWidget() or box
        holder.grab().save(str(out / f"{name}-box.png"))
        RESULTS["pictures"].append({"file": f"{name}.png", "box": done})
    RESULTS["facts"]["input_plugins_loaded"] = input_plugins()
    window.close()
    lab.pump()
    for closing in lab.closing:
        closing()
    return code


def main(argv: list[str]) -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith(
        "linux"
    ):
        sys.exit("571: this runs only on GitHub's Linux runners")
    out, im, app_env = Path(argv[0]), argv[1], "--app-env" in argv[2:]
    cases(im)  # an unknown mode stops here
    try:
        code = run(out, im, app_env)
    except Exception as error:  # noqa: BLE001 - said in checks.json, not lost
        check(f"{im}: the check ran", False, repr(error))
        code = 1
    out.mkdir(parents=True, exist_ok=True)
    (out / "checks.json").write_text(
        json.dumps(RESULTS, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
