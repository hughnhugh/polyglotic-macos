"""Where every save dialog opens (`ui_next.save_folder`, polyglotic-hq 244):
the folder saved to last, or Documents - never the install folder, which
every install and update replaces (decision 0014), nor the folder the app
was started in. 242's dress rehearsal found Save transcript as... and both
Anki exports opening in the install's `current` folder: given only a file
name, Windows' dialog opens in the working folder, and the installer starts
the app there."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for
from tests.ui_next.made_up import EN, export_written, finished_updates

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import save_folder, transcript_window, words_page
from polyglotic_desktop.ui_next.save_folder import (
    STORED_KEY,
    SaveFolder,
    install_folder,
)
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.transcript import Transcript, TranscriptChoices
from polyglotic_desktop.ui_next.words_page import WordsPage

DISCORD = SourceLabel("Discord", "#4dd0e1")


class Store:
    """The settings port, in memory; `unreadable`: a load finds nothing,
    as when the file is gone or locked for a moment."""

    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = dict(values or {})
        self.unreadable = False

    def load(self) -> dict[str, object]:
        return {} if self.unreadable else dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def places(tmp_path: Path) -> dict[str, Path]:
    """An install folder as the installer makes it (`current` inside), the
    user's Documents and home - each a folder of the test's own."""
    found = {
        "install": tmp_path / "Local" / "Polyglotic",
        "documents": tmp_path / "home" / "Documents",
        "home": tmp_path / "home",
        "elsewhere": tmp_path / "home" / "Study",
    }
    for folder in found.values():
        folder.mkdir(parents=True, exist_ok=True)
    (found["install"] / "current").mkdir()
    return found


@pytest.fixture
def started_in_current(
    places: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The packed app as the installer starts it: run from, and started in,
    the install's `current` folder."""
    current = places["install"] / "current"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(current / "Polyglotic.exe"))
    monkeypatch.chdir(current)
    return current


def folder_for(places: dict[str, Path], store: Store | None = None) -> SaveFolder:
    return SaveFolder(
        store,
        documents=places["documents"],
        home=places["home"],
        install=places["install"],
    )


def under(path: Path, folder: Path) -> bool:
    return path.resolve().is_relative_to(folder.resolve())


# -- where a save dialog opens ----------------------------------------------------------


def test_the_first_save_opens_in_documents_with_the_name_given(
    places: dict[str, Path],
) -> None:
    start = Path(folder_for(places).start("transcript.txt"))
    assert start == places["documents"] / "transcript.txt"
    assert start.is_absolute()


def test_the_next_save_opens_where_the_last_went_and_a_new_run_remembers(
    places: dict[str, Path],
) -> None:
    store = Store({"theme": "glaze"})
    found = folder_for(places, store)
    found.saved(places["elsewhere"] / "words.csv")
    assert found.folder() == places["elsewhere"]
    assert store.values == {"theme": "glaze", STORED_KEY: str(places["elsewhere"])}
    assert folder_for(places, store).folder() == places["elsewhere"]  # next run


def test_a_folder_in_the_install_folder_is_never_where_a_save_opens(
    places: dict[str, Path],
) -> None:
    current = places["install"] / "current"
    store = Store({STORED_KEY: str(current)})  # kept by hand, or by an old bug
    found = folder_for(places, store)
    assert found.folder() == places["documents"]
    found.saved(current / "transcript.txt")  # the learner went there themself
    assert found.last == current  # what was stored, never used...
    assert store.values == {STORED_KEY: str(current)}  # ...nor written again
    assert found.folder() == places["documents"]


def test_a_save_in_the_install_folder_is_not_remembered(
    places: dict[str, Path],
) -> None:
    store = Store()
    found = folder_for(places, store)
    found.saved(places["elsewhere"] / "a.txt")
    found.saved(places["install"] / "current" / "b.txt")
    assert found.folder() == places["elsewhere"]
    assert store.values == {STORED_KEY: str(places["elsewhere"])}


def test_a_folder_gone_since_falls_back_to_documents_then_home(
    places: dict[str, Path],
) -> None:
    found = folder_for(places)
    found.saved(places["elsewhere"] / "a.txt")
    places["elsewhere"].rmdir()
    assert found.folder() == places["documents"]
    places["documents"].rmdir()
    assert found.folder() == places["home"]


def test_settings_unreadable_for_a_moment_are_kept_not_lost(
    places: dict[str, Path],
) -> None:
    store = Store({"theme": "glaze", "transcripts": {"x": 1}})
    found = folder_for(places, store)
    store.unreadable = True
    found.saved(places["elsewhere"] / "a.txt")
    assert store.values == {
        "theme": "glaze",
        "transcripts": {"x": 1},
        STORED_KEY: str(places["elsewhere"]),
    }


@pytest.mark.parametrize("stored", [3, "", "Study", "x" * 2_000, None])
def test_a_stored_folder_that_isnt_one_is_ignored(
    places: dict[str, Path], stored: object
) -> None:
    assert (
        folder_for(places, Store({STORED_KEY: stored})).folder()
        == (places["documents"])
    )


def test_the_install_folder_is_currents_parent_and_none_from_source(
    started_in_current: Path, places: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    found = install_folder()
    assert found is not None and found == places["install"].resolve()
    monkeypatch.setattr(sys, "executable", str(places["home"] / "Polyglotic.exe"))
    assert install_folder() == places["home"].resolve()  # packed, not installed
    monkeypatch.delattr(sys, "frozen")
    assert install_folder() is None


def test_windows_own_folders_are_used_unless_given(
    started_in_current: Path, places: dict[str, Path]
) -> None:
    found = SaveFolder()
    assert found.install == places["install"].resolve()
    assert found.documents == save_folder.documents_folder()
    start = Path(found.start("transcript.txt"))
    assert start.is_absolute()
    assert not under(start, places["install"])
    assert not under(start, Path.cwd())


# -- the dialogs ------------------------------------------------------------------------


class Dialog:
    """Windows' save dialog, answering `answer` - and noting the folder and
    name it was opened with."""

    def __init__(self, answer: Path | None = None) -> None:
        self.answer = answer
        self.opened: list[str] = []

    def __call__(self, _parent: object, _title: str, start: str, *_a: object) -> object:
        self.opened.append(start)
        return (str(self.answer) if self.answer else "", "")


@pytest.fixture
def dialog(monkeypatch: pytest.MonkeyPatch) -> Dialog:
    found = Dialog()
    monkeypatch.setattr(transcript_window.QFileDialog, "getSaveFileName", found)
    return found


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    said: list[str] = []
    monkeypatch.setattr(
        transcript_window.QMessageBox,
        "warning",
        lambda _parent, _title, text, *_a: said.append(text),
    )
    return said


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def transcript() -> Transcript:
    found = Transcript(APP, EN, mic=MIC)
    for update in finished_updates(3):
        found.apply(update)
    return found


@pytest.fixture
def tools() -> LearningTools:
    found = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    found.vocabulary.set_status(found.lookup("电脑")[0].entry_id, WordStatus.LEARNING)
    return found


def test_save_transcript_as_never_opens_in_the_install_folder(
    started_in_current: Path, places: dict[str, Path], dialog: Dialog
) -> None:
    """The window as `main` makes it, with Windows' own folders: before 244
    the dialog was given "transcript.txt" alone, and opened in `current`."""
    window = TranscriptWindow("Discord.exe", transcript(), DISCORD, TranscriptChoices())
    window.save_as()
    (start,) = dialog.opened
    assert Path(start).is_absolute()
    assert Path(start).name == "transcript.txt"
    assert not under(Path(start), places["install"])
    assert not under(Path(start), started_in_current)


def test_both_anki_exports_never_open_in_the_install_folder(
    qapp: QApplication,
    started_in_current: Path,
    places: dict[str, Path],
    dialog: Dialog,
    tools: LearningTools,
) -> None:
    page = WordsPage(tools, None)
    page.first._export_csv()
    export_written(page)
    page.first._export_deck()
    export_written(page)
    assert [Path(s).name for s in dialog.opened] == [
        "polyglotic-words.csv",
        "polyglotic-words.apkg",
    ]
    for start in dialog.opened:
        assert Path(start).is_absolute()
        assert not under(Path(start), places["install"])
        assert not under(Path(start), started_in_current)


def test_a_save_opens_the_next_dialog_where_it_went_transcripts_and_words_alike(
    qapp: QApplication,
    places: dict[str, Path],
    dialog: Dialog,
    tools: LearningTools,
) -> None:
    shared = folder_for(places, Store())
    window = TranscriptWindow(
        "Discord.exe", transcript(), DISCORD, TranscriptChoices(), save_folder=shared
    )
    page = WordsPage(tools, None, shared)
    window.save_as()  # cancelled: nothing remembered
    dialog.answer = places["elsewhere"] / "evening.srt"
    window.save_as()
    assert (places["elsewhere"] / "evening.srt").exists()
    dialog.answer = places["elsewhere"] / "words.csv"
    page.first._export_csv()
    export_written(page)  # on its own thread (273)
    assert (places["elsewhere"] / "words.csv").exists()
    assert dialog.opened == [
        str(places["documents"] / "transcript.txt"),
        str(places["documents"] / "transcript.txt"),
        str(places["elsewhere"] / "polyglotic-words.csv"),
    ]


def test_a_transcript_that_cant_be_saved_says_so_in_plain_words(
    places: dict[str, Path], dialog: Dialog, warnings: list[str]
) -> None:
    """A folder gone, read-only or a CSV open in Excel: before 244 the
    error went uncaught (Words' exports already said so: 145)."""
    shared = folder_for(places, Store())
    window = TranscriptWindow(
        "Discord.exe", transcript(), DISCORD, TranscriptChoices(), save_folder=shared
    )
    dialog.answer = places["home"] / "gone" / "evening.txt"
    window.save_as()
    assert warnings == [transcript_window.not_saved("evening.txt")]
    assert "Couldn't save evening.txt" in warnings[0]
    assert shared.folder() == places["documents"]  # not remembered


def test_an_export_that_cant_be_written_isnt_remembered(
    qapp: QApplication,
    places: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    tools: LearningTools,
) -> None:
    shared = folder_for(places, Store())
    gone = places["home"] / "gone" / "words.csv"
    monkeypatch.setattr(words_page.QFileDialog, "getSaveFileName", Dialog(gone))
    page = WordsPage(tools, None, shared)
    page.first._export_csv()
    export_written(page)
    assert f"Couldn't write {gone}" in page.first.export_result.text()
    assert shared.folder() == places["documents"]


def test_on_a_mac_the_install_folder_is_the_whole_app_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409, 410: the packed executable is in `Polyglotic.app/Contents/MacOS`;
    a save dialog must never start anywhere in the bundle, which an update
    replaces whole."""
    bundle = tmp_path / "Applications" / "Polyglotic.app"
    executable = bundle / "Contents" / "MacOS" / "Polyglotic"
    executable.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert install_folder() == bundle.resolve()
    saving = SaveFolder(
        documents=bundle / "Contents" / "Resources", home=tmp_path / "home"
    )
    (tmp_path / "home").mkdir()
    (bundle / "Contents" / "Resources").mkdir()
    assert saving.folder() == tmp_path / "home"
