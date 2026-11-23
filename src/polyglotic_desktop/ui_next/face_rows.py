"""Settings > Captions > Look's Fonts card (polyglotic-hq 482, decision
0223): a row per language the captions are in - "Chinese (Simplified)
captions in: Ma Shan Zheng (Default)" - each row's list grouped Sans /
Serif / Handwritten / Calligraphy (polyglotic-hq 532) / This PC's own /
Any font on this PC. The single Font
row Look had before is that last group now, in every row.

The faces a language offers are `fonts.CHOICES`'; its default is marked.
A face downloaded when it's chosen says its size until it's here; chosen,
it's asked for (`DownloadsView.want`) and its row says how the download
goes, as a dictionary's does on Learning, with a bar and the way on. Until
it's here, the captions are in the OS's own face. Every font on the PC is
listed only when a row's list first opens (there can be hundreds), so the
card opens at once.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QShowEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem, Step
from polyglotic_desktop.ui_next import fonts, languages, style
from polyglotic_desktop.ui_next.controls import Combo, Row, label
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.pack_row import (
    PackBar,
    megabytes,
    progress_text,
    size_text,
)
from polyglotic_desktop.ui_next.panels import Panel
from polyglotic_desktop.ui_next.views.caption_window import face_chosen
from polyglotic_desktop.ui_next.views.panels import (
    DownloadsView,
    FaceDownloads,
    LanguagesView,
    LookView,
    captioned,
)

FALLBACK_LANGUAGE = "en"
"""The row shown when no language is chosen yet: English, every window's
first translation."""


def _tr(text: str) -> str:
    return QApplication.translate("FaceRows", text)


def _groups() -> tuple[tuple[str, str], ...]:
    return (
        (fonts.SANS, _tr("Sans")),
        (fonts.SERIF, _tr("Serif")),
        (fonts.HANDWRITTEN, _tr("Handwritten")),
        (fonts.CALLIGRAPHY, _tr("Calligraphy")),
    )


def download_text(name: str, progress: PackProgress) -> str:
    """How a face's download goes, in plain words: `pack_row`'s for a
    connection, the storage or the disk; its own for the rest."""
    problem = progress.problem
    if problem is Problem.NOT_OFFERED:
        return _tr("{face} isn't ready to download yet.").format(face=name)
    if problem is Problem.NEEDS_NEWER_APP:
        return _tr("{face} needs a newer Polyglotic.").format(face=name)
    if problem is Problem.LIST_REFUSED:
        return _tr(
            "Refused: the list of downloads failed our signature check, so "
            "nothing was downloaded."
        )
    if problem is not None:
        return progress_text("", progress)
    if progress.step is Step.WAITING:
        return _tr("Waiting for another download to finish.")
    if progress.step is Step.DOWNLOADING:
        return _tr("Downloading {face}: {done} of {total} MB").format(
            face=name, done=megabytes(progress.done), total=megabytes(progress.total)
        )
    if progress.step in (Step.CHECKING, Step.OPENING):
        return _tr("Checking {face}.").format(face=name)
    return _tr("Getting {face}.").format(face=name)


class FaceBox(Combo):
    """One language's faces, grouped under headings no one can pick: each
    item's data is a family, or "" for the language's default."""

    chosen = Signal(object)
    """A family, or None for the language's default."""

    def __init__(self, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.script = fonts.script(language)
        self.downloads = FaceDownloads()
        self._listed = False
        self._fill()
        self.show_family(None)  # the default, never a heading
        self.currentIndexChanged.connect(self._picked)

    def _fill(self) -> None:
        """The list: the language's own faces by kind, this PC's, and every
        font on it once `_listed`."""
        blocked = self.blockSignals(True)
        self.clear()
        default = fonts.DEFAULTS.get(self.script)
        listed = fonts.listed_own(self.script)
        own = [family for family in listed if QFontDatabase.hasFamily(family)]
        own = own or list(listed[:1])  # named, even if missing here
        for kind, heading in _groups():
            faces = [
                fonts.FACES[family]
                for family in fonts.CHOICES.get(self.script, ())
                if fonts.FACES[family].kind == kind
            ]
            if faces:
                self._heading(heading)
                for face in faces:
                    self._face(face, face.family == default)
        self._heading(pc_or_mac(_tr("This PC's own"), _tr("This Mac's own")))
        for family in own:
            self.addItem(family, family)
        self._heading(
            pc_or_mac(_tr("Any font on this PC"), _tr("Any font on this Mac"))
        )
        if self._listed:
            shown = {self.itemData(n) for n in range(self.count())}
            for family in QFontDatabase.families():
                if not family.startswith("@") and family not in shown:  # "@": sideways
                    self.addItem(family, family)
        self.blockSignals(blocked)

    def _heading(self, text: str) -> None:
        self.addItem(text)
        model = self.model()
        assert isinstance(model, QStandardItemModel)
        found = model.item(self.count() - 1)
        found.setFlags(Qt.ItemFlag.NoItemFlags)  # can't be picked, or reached by keys
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        found.setFont(bold)

    def _face(self, face: fonts.Face, default: bool) -> None:
        self.addItem(self._text(face, default), "" if default else face.family)

    def _text(self, face: fonts.Face, default: bool) -> str:
        """Its name, "(Default)" if it is, and its size if it comes as a
        download not here yet."""
        name = _tr("{face} (Default)").format(face=face.name) if default else face.name
        size = self.downloads.sizes.get(face.pack)
        if face.pack and face.pack not in self.downloads.here and size:
            return f"{name} · {size_text(size)}"
        return name

    def show_downloads(self, downloads: FaceDownloads) -> None:
        """The downloaded faces' sizes as `downloads` has them now."""
        self.downloads = downloads
        default = fonts.DEFAULTS.get(self.script)
        for n in range(self.count()):
            data = self.itemData(n)
            family = default if data == "" else data
            face = fonts.FACES.get(family) if isinstance(family, str) else None
            if face is not None and face.pack:
                self.setItemText(n, self._text(face, data == ""))

    def show_family(self, family: str | None) -> None:
        """`family` shown as chosen (None: the default) - added under Any
        font if it isn't listed (not listed yet, or not on this PC)."""
        index = self.findData(family or "")
        if index < 0 and family:
            self.addItem(family, family)
            index = self.count() - 1
        if index != self.currentIndex():
            blocked = self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(blocked)

    def face(self) -> fonts.Face | None:
        """The face chosen now, if it's one of the language's own."""
        data = self.currentData()
        family = fonts.DEFAULTS.get(self.script) if data == "" else data
        return fonts.FACES.get(family) if isinstance(family, str) else None

    def showPopup(self) -> None:
        if not self._listed:
            self._listed = True
            chosen = self.currentData()
            self._fill()
            self.show_downloads(self.downloads)
            self.show_family(chosen or None)
        super().showPopup()

    def _picked(self, index: int) -> None:
        data = self.itemData(index)
        if isinstance(data, str):
            self.chosen.emit(data or None)


class FaceRow(QWidget):
    """A language's row: its face, and how its download goes while one is
    under way or stopped - words, a bar, Retry or Download anyway."""

    wanted = Signal(str, bool)
    """A face's pack asked for again (and on a metered connection)."""

    def __init__(self, title: str, box: FaceBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.box = box
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(style.px(6))
        column.addWidget(Row(title, "", box))
        self.status = QWidget(self)
        self.status.setObjectName("look.face_download")
        line = QHBoxLayout(self.status)
        line.setContentsMargins(style.px(14), 0, 0, 0)
        words = QVBoxLayout()
        words.setSpacing(style.px(4))
        self.words = label("", "Faint", wrap=True)
        self.bar = PackBar(self.status)
        words.addWidget(self.words)
        words.addWidget(self.bar)
        line.addLayout(words, 1)
        self.again = QPushButton(self.status)
        self.again.setProperty("kind", "ghost")
        self.again.setCursor(Qt.CursorShape.PointingHandCursor)
        self.again.clicked.connect(self._again)
        line.addWidget(self.again, 0, Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(self.status)
        self.status.hide()
        self._pack = ""
        self._anyway = False

    def show_download(self, downloads: FaceDownloads) -> None:
        """The chosen face's download, if one is under way or stopped."""
        face = self.box.face()
        progress = None
        if face is not None and face.pack and face.pack not in downloads.here:
            progress = downloads.progress.get(face.pack)
        if face is None or progress is None or progress.step is Step.DONE:
            self.status.hide()
            return
        self._pack = face.pack
        self._anyway = progress.problem is Problem.METERED
        self.words.setText(download_text(face.name, progress))
        downloading = progress.step is Step.DOWNLOADING and progress.total > 0
        self.bar.set_share(progress.done / progress.total if downloading else 0.0)
        self.bar.setVisible(downloading and progress.problem is None)
        stopped = progress.problem is not None and (
            progress.retry_in is None or self._anyway
        )
        self.again.setText(_tr("Download anyway") if self._anyway else _tr("Retry"))
        self.again.setVisible(stopped)
        self.status.show()

    def _again(self) -> None:
        if self._pack:
            self.wanted.emit(self._pack, self._anyway)


class FacesPanel(Panel):
    """The Fonts card: a row for each language captioned
    (`views.panels.captioned`), English's until one is chosen; its rows
    made again when the languages change."""

    def __init__(
        self,
        view: LookView,
        languages_view: LanguagesView,
        downloads: DownloadsView | None = None,
        notes: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            _tr("Fonts"),
            _tr("Each language's captions in a face of its own.") if notes else "",
            parent,
        )
        self.view = view
        self.languages_view = languages_view
        self.downloads = downloads or DownloadsView()
        self.rows = QWidget()
        self._column = QVBoxLayout(self.rows)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(style.px(12))
        self.add(self.rows)
        self.boxes: dict[str, FaceBox] = {}
        self.face_rows: dict[str, FaceRow] = {}
        self._codes: tuple[str, ...] = ()
        self._refreshed = False
        self.bind(view, languages_view, self.downloads)
        self.refresh()

    def refresh(self) -> None:
        codes = captioned(self.languages_view.value) or (FALLBACK_LANGUAGE,)
        if codes != self._codes:
            self._codes = codes
            self._make_rows()
        downloads = self.downloads.value
        for code, box in self.boxes.items():
            box.show_downloads(downloads)
            box.show_family(face_chosen(self.view.value, code))
            self.face_rows[code].show_download(downloads)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._refreshed:  # the sizes, once the card is first seen
            self._refreshed = True
            self.downloads.refresh()

    def _make_rows(self) -> None:
        while self._column.count():
            item = self._column.takeAt(0)
            if item is not None and (gone := item.widget()) is not None:
                gone.deleteLater()
        self.boxes, self.face_rows = {}, {}
        for code in self._codes:
            title = languages.in_sentence(
                _tr("{language} captions in"), language=languages.language_name(code)
            )
            box = FaceBox(code)
            box.setObjectName(f"look.face_{code}")
            box.setAccessibleName(title)
            box.setMinimumWidth(style.px(220))
            box.chosen.connect(lambda family, c=code: self._chosen(c, family))
            row = FaceRow(title, box)
            # looked up when asked: `main` hands the view its `want` later
            row.wanted.connect(lambda pack, anyway: self.downloads.want(pack, anyway))
            self._column.addWidget(row)
            self.boxes[code], self.face_rows[code] = box, row

    def _chosen(self, language: str, family: str | None) -> None:
        """A face chosen: it draws `language`'s captions from now - once
        it's here, if it comes as a download, which it's asked for."""
        self.view.set_face(language, family)
        face = self.boxes[language].face()
        if (
            face is not None
            and face.pack
            and face.pack not in self.downloads.value.here
        ):
            self.downloads.want(face.pack, False)
