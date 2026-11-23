"""Fakes the interface's tests share: settings in memory, made-up apps
with sound, the app built on them - with the caption windows and the main
window as `main` wires them - and learning tools on the sample
dictionaries. Made-up names only."""

from collections.abc import Callable, Mapping

import shiboken6
from PySide6.QtWidgets import QSystemTrayIcon
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample

from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.main import Hub, Panels, chinese_word_split
from polyglotic_desktop.ports.capture import PlayingApp, SourceCategory
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect


class MemorySettingsStore:
    def __init__(self, values: Mapping[str, object] | None = None) -> None:
        self.values: dict[str, object] = dict(values or {})
        self.saves = 0

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: Mapping[str, object]) -> None:
        self.values = dict(values)
        self.saves += 1


class FakeAppList:
    def playing_apps(self) -> list[PlayingApp]:
        return [
            PlayingApp(10, "Video Player", False, SourceCategory.VIDEO),
            PlayingApp(20, "Web Browser", True, SourceCategory.BROWSER),
        ]


def tools_for(
    dictionary: ChineseDictionary | EnglishDictionary,
    scheme: str,
    ready: bool = True,
    problem: DictionaryProblem | Callable[[], DictionaryProblem | None] | None = None,
) -> LearningTools:
    """`ready`: the word split's data read, as `main` has it soon after the
    start; False for a test of what happens before (project 136).
    `problem`: the dictionary file said to be out (polyglotic-hq 199) - or
    what says whether it is, asked each time."""

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    if ready and isinstance(dictionary, ChineseDictionary):
        dictionary.prepare()
    vocabulary = Vocabulary(
        MemoryLearningStore(), facts, scheme, Clock(), placed=dictionary.words_past
    )
    told = problem if callable(problem) else (lambda: problem)
    return LearningTools(vocabulary, dictionary, dictionary_problem=told)


def chinese_tools(
    ready: bool = True,
    problem: DictionaryProblem | Callable[[], DictionaryProblem | None] | None = None,
) -> LearningTools:
    return tools_for(ChineseDictionary(chinese_sample()), "hsk-2025", ready, problem)


def make_app(
    store: MemorySettingsStore | None = None, tools: bool = False
) -> DesktopApp:
    return DesktopApp(
        store or MemorySettingsStore(),
        chinese_tools() if tools else None,
        FakeAppList(),
    )


class Built:
    """The app with the caption windows and the main window, as `main`
    builds them (no capture, no connection); `close` closes them all."""

    def __init__(
        self,
        store: MemorySettingsStore | None = None,
        tools: bool = False,
        *,
        caption_learning: bool = False,
    ) -> None:
        """`tools`: a Chinese learner's (`chinese_tools`), else none.
        `caption_learning`: wire those tools into the caption windows as well.
        """
        store = store or MemorySettingsStore()
        self.desktop = make_app(store, tools)
        learner = self.desktop.tools if caption_learning else None
        self.windows = CaptionWindows(
            store, MIC, lambda: [Rect(0, 0, 1920, 1040)], learner=learner
        )
        if learner is not None:
            learner.changed.connect(self.windows.learning_changed)
            self.windows.word_split = chinese_word_split(learner)
        self.panels = Panels(self.desktop.settings, self.windows)
        assert self.desktop.apps is not None
        self.hub = Hub(self.desktop, self.windows, self.panels, self.desktop.apps, True)

    def close(self) -> None:
        self.panels.save_look()  # a look still settling: saved, as at quit (273)
        self.hub.close()
        self.windows.close()
        self.desktop.close()
        # the main window deleted now, its pages and their panels with it -
        # not left to the interpreter's exit, where panels still bound to
        # their views crashed Linux's run now and then (261)
        if shiboken6.isValid(self.hub.window):
            shiboken6.delete(self.hub.window)


class RecordingTray(QSystemTrayIcon):
    """The tray, offscreen (which has none): the messages it was asked to
    show."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[tuple[str, str]] = []

    def showMessage(self, title: str, text: str, *_: object) -> None:
        self.messages.append((title, text))
