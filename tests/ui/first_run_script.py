"""The first run's screens answered by a script, offscreen (polyglotic-hq
250): each screen's `exec` takes the next line - the screen it expects and
what to press - and notes whether Back was offered."""

from collections.abc import Callable
from typing import Any

import pytest
from tests.lexicon.sample import chinese_sample, english_sample
from tests.ui.fakes import tools_for

from polyglotic_desktop.adapters.background_learning import BackgroundLearningStore
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.ui.first_run import BACK
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.widgets import TextDialog

Press = Callable[[Any], int]
Line = tuple[str, Press]


def scripted(
    monkeypatch: pytest.MonkeyPatch, script: list[Line]
) -> list[tuple[str, bool]]:
    """Every first-run screen answered from `script`, in order: what was
    shown, and whether with Back."""
    seen: list[tuple[str, bool]] = []

    def exec_(dialog: TextDialog) -> int:
        assert script, f"{type(dialog).__name__} asked, nothing left to press"
        name, press = script.pop(0)
        assert type(dialog).__name__ == name, (type(dialog).__name__, name)
        seen.append((name, not dialog.back.isHidden()))  # type: ignore[attr-defined]
        return press(dialog)

    monkeypatch.setattr(TextDialog, "exec", exec_)
    return seen


def nothing_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    def exec_(dialog: TextDialog) -> int:
        raise AssertionError(f"{type(dialog).__name__} asked")

    monkeypatch.setattr(TextDialog, "exec", exec_)


def next_(dialog: Any) -> int:
    dialog.accept()
    return 1


def back(dialog: Any) -> int:
    dialog.back.click()
    return int(dialog.result())


def closed(dialog: Any) -> int:
    dialog.reject()
    return 0


def agree(then: Press = next_, usage: bool = True) -> Press:
    """Usage statistics on (or not), the yes ticked, then `then`."""

    def press(dialog: Any) -> int:
        dialog.usage.setChecked(usage)
        dialog.agree.setChecked(True)
        return then(dialog)

    return press


def check(test: Callable[[Any], object], then: Press) -> Press:
    """`test` on the screen as shown (what was entered kept), then `then`."""

    def press(dialog: Any) -> int:
        assert test(dialog), "not as it was left"
        return then(dialog)

    return press


class Built:
    """A learner per language as `main` builds them, kept in memory: each
    one built is noted, with whether its store was closed."""

    def __init__(self, level_picked: bool = False) -> None:
        self.level_picked = level_picked
        self.made: dict[bool, LearningTools] = {}
        self.closed: list[bool] = []

    def __call__(self, english: bool) -> tuple[LearningTools, BackgroundLearningStore]:
        tools = (
            tools_for(EnglishDictionary(english_sample()), "en-frequency")
            if english
            else tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
        )
        if self.level_picked:
            tools.vocabulary.set_level(Level(tools.vocabulary.scheme, 1))
        self.made[english] = tools
        built = self

        class Store:
            def close(self) -> None:
                built.closed.append(english)

        return tools, Store()  # type: ignore[return-value]


__all__ = ["BACK"]
