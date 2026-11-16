"""Where a save dialog opens: the folder the learner saved to last, or
their Documents - never the install folder (polyglotic-hq 244).

Given only a file name, Windows' save dialog opens in the folder the app
was started in, and the installer starts the app in its install folder's
`current`, which every install and update replaces (decision 0014). So
until 244 a transcript or Anki file saved without looking where went into
the install folder, and the first update deleted it (242's dress
rehearsal found it, on a private desktop). Every save dialog - Save
transcript as..., Export for Anki, the Anki deck file - starts here
instead.

The folder saved to last is kept in the settings file under its own key,
beside the others' (`adapters.json_settings`), on this PC only; a folder
in the install folder is never remembered. Holds no caption text.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from polyglotic_desktop.ports.settings import SettingsStore

STORED_KEY = "save_folder"
"""The folder saved to last, in the settings file."""
MAX_STORED = 1_000  # characters: anything longer was never a folder of ours


def install_folder() -> Path | None:
    """The installer's folder the packed app runs from - `current`'s parent,
    which holds the packages and the updater too, all replaced or removed
    on install, update and uninstall (decision 0014) - or the packed
    folder itself, run without installing. On a Mac, the whole `.app`
    bundle the executable runs from (`Polyglotic.app/Contents/MacOS`),
    which an update or a new copy replaces (polyglotic-hq 409, 410). None
    run from source."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).resolve().parent
    bundle = next(
        (f for f in (folder, *folder.parents) if f.suffix.lower() == ".app"), None
    )
    if bundle is not None:
        return bundle
    return folder.parent if folder.name.lower() == "current" else folder


def documents_folder() -> Path | None:
    """The user's Documents, as Windows has it (moved into OneDrive, too)."""
    found = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    return Path(found) if found else None


class SaveFolder:
    """The folder every save dialog starts in (`start`), and the one saved
    to last (`saved`), shared by the transcripts and Words."""

    def __init__(
        self,
        store: SettingsStore | None = None,
        *,
        documents: Path | None = None,
        home: Path | None = None,
        install: Path | None = None,
    ) -> None:
        """`store`: the settings, to keep the folder saved to last between
        runs (none: this run only). `documents`, `home` and `install` are
        Windows' own (`documents_folder`, the user's home and
        `install_folder`) unless given - the tests give their own."""
        self._store = store
        self._read: dict[str, object] = store.load() if store else {}
        """The settings file as last read: kept if a read finds nothing."""
        self.documents = documents if documents is not None else documents_folder()
        self.home = home if home is not None else Path.home()
        self.install = install if install is not None else install_folder()
        self.last = _folder(self._read.get(STORED_KEY))
        """The folder saved to last, if any."""

    def folder(self) -> Path:
        """Where the next save dialog opens: the folder saved to last while
        it's still there, else Documents, else the user's home - never in
        the install folder, nor (as Windows would) the folder the app was
        started in."""
        for found in (self.last, self.documents, self.home):
            if found is not None and self._usable(found):
                return found
        return self.home  # even gone, an absolute path: never the start folder

    def start(self, name: str) -> str:
        """What a save dialog is given: `name` in `folder()`, absolute."""
        return str(self.folder() / name)

    def saved(self, path: Path) -> None:
        """A file was saved at `path`: the next save dialog opens in its
        folder - unless that's in the install folder, which an update
        would empty."""
        folder = path.parent
        if not folder.is_absolute() or self._in_install(folder):
            return
        if folder == self.last:
            return
        self.last = folder
        if self._store is None:
            return
        read = self._store.load()
        if read:
            self._read = read
        # nothing read - the file gone or unreadable for a moment - keeps the
        # settings as last read rather than losing them (`Settings.update`)
        self._read = {**self._read, STORED_KEY: str(folder)}
        self._store.save(self._read)

    def _usable(self, folder: Path) -> bool:
        return folder.is_absolute() and folder.is_dir() and not self._in_install(folder)

    def _in_install(self, folder: Path) -> bool:
        if self.install is None:
            return False
        try:
            return folder.resolve().is_relative_to(self.install.resolve())
        except OSError:
            return True  # can't tell: not somewhere to start


def _folder(stored: object) -> Path | None:
    """A folder kept in the settings, if it's one: an absolute path."""
    if not isinstance(stored, str) or not 0 < len(stored) <= MAX_STORED:
        return None
    found = Path(stored)
    return found if found.is_absolute() else None
