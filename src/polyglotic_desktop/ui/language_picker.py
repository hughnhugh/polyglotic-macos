"""Step 1 of the first run: choosing the interface language (polyglotic-hq 658).

Lists every offered interface language by its own name ("Deutsch", "日本語"),
preselected from the OS's display language (else English), with full keyboard
and screen-reader support. Choosing the language already showing continues to
step 2 without a restart; choosing another saves it and relaunches the app into
it at once.

Also explains in one line that translations default to the chosen language
until changed in Settings.
"""

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui.consent import WINDOW_FRAME
from polyglotic_desktop.ui.first_run import add_back
from polyglotic_desktop.ui.widgets import TextDialog

# Named layout tunables (unit, range, reason).
LEAST_WIDTH_PX = 460
"""Minimum dialog width in px at text-size factor 1.0 (range 380-640): fits the
restart sentence and translation note cleanly without awkward wrapping."""
DIALOG_MARGIN_X_PX = 24
"""Horizontal outer dialog margin in px (range 12-32, 4 px grid): matches
ConsentDialog and SignInDialog."""
DIALOG_MARGIN_Y_PX = 20
"""Vertical outer dialog margin in px (range 12-32, 4 px grid): matches
ConsentDialog and SignInDialog."""
DIALOG_SPACING_PX = 12
"""Vertical spacing between dialog sections in px (range 8-20, 4 px grid)."""
LIST_MIN_HEIGHT_PX = 160
"""Minimum height of the language list in px (range 120-280): keeps several
rows visible on short screens while Continue stays above the taskbar."""
LIST_IDEAL_HEIGHT_PX = 280
"""Preferred height of the language list in px at text-size factor 1.0
(range 200-420): shows about eight languages at once while fitting a 150 %
laptop at 150 % text."""


class LanguagePicker(TextDialog):
    """First-run step 1: pick the app's interface language."""

    def __init__(
        self,
        languages: Sequence[tuple[str, str]],
        chosen: str,
        parent: QWidget | None = None,
    ) -> None:
        """`languages`: `(code, own_name)` pairs in picker order
        (`ui.interface_language.picker`); `chosen`: preselected language code."""
        super().__init__(parent)
        self.setObjectName("LanguagePicker")
        self.setWindowTitle(self.tr("Your language"))
        self.set_least_width(LEAST_WIDTH_PX)
        self._languages = tuple(languages)
        self._fitting = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            DIALOG_MARGIN_X_PX,
            DIALOG_MARGIN_Y_PX,
            DIALOG_MARGIN_X_PX,
            DIALOG_MARGIN_Y_PX,
        )
        layout.setSpacing(DIALOG_SPACING_PX)

        title = QLabel(self.tr("Your language"))
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.intro = QLabel(self.tr("Polyglotic will restart in this language."))
        self.intro.setObjectName("Dim")
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)

        self.languages = QListWidget(self)
        self.languages.setObjectName("language.list")
        self.languages.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.languages.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.languages.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.languages.setAccessibleName(self.tr("Your language"))
        self.languages.setAccessibleDescription(self.intro.text())
        for code, own_name in self._languages:
            item = QListWidgetItem(own_name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.languages.addItem(item)
        self.languages.currentRowChanged.connect(self._selection_changed)
        self.languages.itemDoubleClicked.connect(lambda _: self.accept())
        self.languages.installEventFilter(self)
        layout.addWidget(self.languages, 1)

        self.translation_note = QLabel("")
        self.translation_note.setObjectName("language.translation_note")
        self.translation_note.setProperty("role", "Faint")
        self.translation_note.setWordWrap(True)
        layout.addWidget(self.translation_note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText(self.tr("Continue"))
        self.ok.setProperty("kind", "primary")
        self.ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        self.back = add_back(self, buttons)
        layout.addWidget(buttons)

        self.choose(chosen)

    def choose(self, code: str) -> None:
        """Selects the row for `code` (or the first row if not present) and
        scrolls it into view."""
        row = next(
            (i for i, (c, _) in enumerate(self._languages) if c == code),
            0,
        )
        if self.languages.count() > 0:
            self.languages.setCurrentRow(row)
            item = self.languages.item(row)
            if item is not None:
                self.languages.scrollToItem(
                    item, QAbstractItemView.ScrollHint.PositionAtCenter
                )
        self._selection_changed(row)

    def chosen(self) -> str:
        """The code of the currently selected interface language."""
        item = self.languages.currentItem()
        if item is not None:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, str) and data:
                return data
        return self._languages[0][0] if self._languages else "en"

    def _selection_changed(self, row: int) -> None:
        if 0 <= row < len(self._languages):
            _, own_name = self._languages[row]
            #: {name}: the chosen language's own name, e.g. "Deutsch" or "日本語"
            self.translation_note.setText(
                self.tr(
                    "Translations into {name} - change any time in Settings"
                ).format(name=own_name)
            )
            self.translation_note.setHidden(False)
        else:
            self.translation_note.setText("")
            self.translation_note.setHidden(True)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Pressing Enter/Return while the list has focus continues."""
        if (
            watched is self.languages
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self.accept()
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.languages.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        item = self.languages.currentItem()
        if item is not None:
            self.languages.scrollToItem(
                item, QAbstractItemView.ScrollHint.PositionAtCenter
            )
        QTimer.singleShot(0, self, self._fit)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        """Size the list cleanly for the available screen height so Continue
        always stays above the taskbar (150 % laptop at 100-150 % text)."""
        screen = self.screen()
        layout = self.layout()
        if screen is None or layout is None or self._fitting:
            return
        self._fitting = True
        try:
            self.languages.setFixedHeight(0)
            layout.invalidate()
            rest = layout.totalHeightForWidth(self.width())
            if rest < 0:
                rest = layout.totalSizeHint().height()
            room = screen.availableGeometry().height() - WINDOW_FRAME - rest
            ideal = self.at_text_size(LIST_IDEAL_HEIGHT_PX)
            height = (
                min(ideal, room)
                if room < LIST_MIN_HEIGHT_PX
                else min(ideal, max(LIST_MIN_HEIGHT_PX, room))
            )
            self.languages.setFixedHeight(max(1, height))
            layout.invalidate()
            total = layout.totalHeightForWidth(self.width())
            if total < 0:
                total = layout.totalSizeHint().height()
            self.setMinimumHeight(total)
            if self.height() != total:
                self.resize(self.width(), total)
        finally:
            self._fitting = False
        self.keep_on_screen()
