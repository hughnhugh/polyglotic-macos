"""The consent screen: at first run, and from settings any time after.

One plain screen, the same everywhere (project 012, agreed 2026-11-04).
What the service needs - the account, the minutes listened, connection
data, and learning data as dictionary entries and times - is explained,
not asked: it isn't optional. Three choices are asked, each off until the
user says yes:
- **Usage statistics** - how the app is used, with no words or audio;
- **Crash reports** - what went wrong in the code, with no captions;
- **Share how often you hear words** - daily counts per dictionary word,
  no sentences, no times, nothing from the user's own mic.

Before going on, the same screen asks for a yes to the tester agreement
(polyglotic-hq project 185) - both papers a button away, opened in the
browser, never shown in here. The minimum age is the papers' to say, not
this screen's (the user, 2026-11-11: no "I'm 14 or older" on the screen).
Asked at the first run, and again at start once the agreement's words
change (`agreement_needed`); Continue waits for the tick, and closing the
screen instead is Quit. From Account it says when the tester agreed.
On a screen too short for it all (a laptop at 150 %), the explanation and
the choices scroll; the yes and Continue stay in view (polyglotic-hq 203).

The screen only shows and returns the choices and the agreement; `main`
keeps and sends them (the connection's `DataExchange.choose_consent`).
Every string goes through `tr()`.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import QDate, QEvent, QLocale, QObject, Qt, QTimer
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.shared.papers import (
    PRIVACY_NOTICE,
    TESTER_AGREEMENT,
    TESTER_AGREEMENT_VERSION,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ui.first_run import add_back
from polyglotic_desktop.ui.os_words import pc_or_mac
from polyglotic_desktop.ui.widgets import TextDialog, page_button

WINDOW_FRAME = 40
"""Room for Windows' title bar and borders (about 31 px at 100 %), as the
main window leaves (`ui_next.main_window.FRAME`)."""
MIN_SCROLL = 120
"""The least the explanation and choices get on the tiniest screen: a few
lines, scrolling."""
WIDEST = 680
"""The widest it grows, in px at a text size factor of 1.0 (`TextDialog.
at_text_size`), before its explanation scrolls on a screen with the room
(`_fit`): at the app's Normal (1.3 since decision 0244) a screen 1040 px
tall scrolled it at its least width in Linux's fonts, wider than Windows'
(polyglotic-hq 524). Its paragraphs' lines stay readable at it."""
WIDEN_STEP = 20


def agreement_needed(current: ConsentChoice | None) -> bool:
    """Whether to ask at start: nothing chosen on this PC yet (the first
    run), or no yes to this version of the tester agreement."""
    return (
        current is None
        or current.agreement is None
        or current.agreement.version != TESTER_AGREEMENT_VERSION
    )


class ConsentDialog(TextDialog):
    def __init__(
        self,
        current: ConsentChoice | None = None,
        parent: QWidget | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        tester: bool | None = None,
    ) -> None:
        """`current`: the choices so far (from settings), or None at first
        run - then every choice starts off. `clock`: when the tester says
        yes. `tester`: whether the account is an alpha tester's - then usage
        statistics and crash reports are on, and stay on (polyglotic-hq
        275); None: not known yet (the first run asks before the code), and
        the screen says it as a fact for testers."""
        super().__init__(parent)
        self.asks = agreement_needed(current)
        """Whether the screen asks for the yes (else it says when it was given)."""
        self._clock = clock
        self._agreed: Agreement | None = None
        self._fitting = False
        self.setObjectName("ConsentDialog")
        self.setWindowTitle(self.tr("Your data"))
        self.set_least_width(520)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        # what's explained and the three choices scroll on a screen too short
        # for them all; the yes and Continue below stay in view (`_fit`)
        self.body = QWidget()
        self.body.setObjectName("consent.body")
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel(self.tr("What Polyglotic sends, and what you choose"))
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self._text(self._needed(), "needed"))
        notice = QHBoxLayout()
        notice.addWidget(
            page_button(
                self.tr("Read the privacy notice"),
                PRIVACY_NOTICE,
                "consent.privacy_notice",
            )
        )
        notice.addStretch(1)
        layout.addLayout(notice)

        choose = QLabel(self.tr("You choose - each stays off unless you turn it on:"))
        choose.setWordWrap(True)
        layout.addWidget(choose)
        self.usage = self._choice(
            "usage",
            self.tr("Usage statistics"),
            self.tr(
                "How you use the app: how long you listen, how quickly captions "
                "appear, how many words you look up, and which well-known app you "
                "listen to most (like Discord, Zoom or Chrome). Never the words "
                "themselves, never audio, never the name of any other app."
            ),
            layout,
        )
        self.crashes = self._choice(
            "crashes",
            self.tr("Crash reports"),
            self.tr(
                "When the app crashes, a report of what went wrong in its code - "
                "with no captions and no audio."
            ),
            layout,
        )
        self.exposures = self._choice(
            "exposures",
            self.tr("Share how often you hear words"),
            pc_or_mac(
                self.tr(
                    "Daily counts of how often you heard each dictionary word - no "
                    "sentences, no times of day, nothing from your own mic. They help "
                    "us improve levels and word suggestions. Your counts stay on this "
                    "PC either way."
                ),
                self.tr(
                    "Daily counts of how often you heard each dictionary word - no "
                    "sentences, no times of day, nothing from your own mic. They help "
                    "us improve levels and word suggestions. Your counts stay on this "
                    "Mac either way."
                ),
            ),
            layout,
        )
        if current is not None:
            self.usage.setChecked(current.usage)
            self.crashes.setChecked(current.crashes)
            self.exposures.setChecked(current.exposures)
        self.tester = tester
        if tester:
            for box in (self.usage, self.crashes):
                box.setChecked(True)
                box.setEnabled(False)
        if tester is not False:
            layout.addWidget(
                self._text(
                    self.tr(
                        "You're testing the alpha: usage statistics and crash "
                        "reports are on while you test, so we can find and fix "
                        "problems."
                    )
                    if tester
                    else self.tr(
                        "Testing the alpha? Then usage statistics and crash "
                        "reports are on while you test, so we can find and fix "
                        "problems."
                    ),
                    "testers",
                )
            )

        layout.addWidget(
            self._text(
                self.tr(
                    "You can change these any time on Account: Choose what to share."
                ),
                "later",
            )
        )
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("consent.scroll")
        self.scroll_area.setWidget(self.body)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.body.setAutoFillBackground(False)
        outer.addWidget(self.scroll_area, 1)
        self.body.installEventFilter(self)
        self.agree = self._agreement(current, outer)  # the yes: always in view
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText(self.tr("Continue"))
        buttons.accepted.connect(self.accept)
        if self.asks:  # no yes, no further: closing the screen is Quit
            self.quit = buttons.addButton(
                self.tr("Quit Polyglotic"), QDialogButtonBox.ButtonRole.RejectRole
            )
            self.quit.setObjectName("consent.quit")
            buttons.rejected.connect(self.reject)
            self.ok.setEnabled(False)
        self.back = add_back(self, buttons)  # at the first run: the level
        outer.addWidget(buttons)

    def _agreement(
        self, current: ConsentChoice | None, layout: QVBoxLayout
    ) -> QCheckBox | None:
        """The yes to the tester agreement - or, given already, when."""
        row = QHBoxLayout()
        box: QCheckBox | None = None
        if self.asks:
            box = QCheckBox(self.tr("I agree to the tester agreement."))
            box.setObjectName("consent.agreement")
            box.toggled.connect(self._ticked)
            # a row of its own: a check box doesn't wrap, and beside the
            # button its words were cut off (polyglotic-hq 185's pictures)
            layout.addWidget(box)
        elif current is not None and current.agreement is not None:
            given = current.agreement.at.astimezone()
            day = QLocale().toString(
                QDate(given.year, given.month, given.day),
                QLocale.FormatType.LongFormat,
            )
            row.addWidget(
                self._text(
                    self.tr("You agreed to the tester agreement on {date}.").format(
                        date=day
                    ),
                    "agreed",
                ),
                1,
            )
        row.addWidget(
            page_button(
                self.tr("Read the tester agreement"),
                TESTER_AGREEMENT,
                "consent.tester_agreement",
            )
        )
        if box is not None:
            row.addStretch(1)
        layout.addLayout(row)
        return box

    def showEvent(self, event: QShowEvent) -> None:
        """A check box doesn't wrap: the screen is at least as wide as the
        yes's words, in any language and text size, so none is cut off."""
        if self.agree is not None:
            margins = self.contentsMargins() + self.layout().contentsMargins()  # type: ignore[union-attr]
            needed = self.agree.sizeHint().width() + margins.left() + margins.right()
            self.setMinimumWidth(max(self.minimumWidth(), needed))
        super().showEvent(event)
        QTimer.singleShot(
            0, self, self._fit
        )  # again once styled: its fonts set its height

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)  # never shorter than its text needs
        self._fit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """The explanation's or a choice's size changed (styled, the text
        size): fitted again."""
        if watched is self.body and event.type() == QEvent.Type.LayoutRequest:
            QTimer.singleShot(0, self, self._fit)
        return False

    def _fit(self) -> None:
        """As tall as everything needs at this width - or, where that's
        taller than the screen's work area, wider first (up to `WIDEST`,
        and nine tenths of the screen) - or, on a screen too short for even
        that, as tall as its work area leaves room for, with the
        explanation and the choices scrolling above the yes and Continue
        (polyglotic-hq 203: at 150 % on a 1920 x 1080 laptop, 1280 x 672
        above the taskbar, the screen was 721 px tall and Continue sat under
        the taskbar)."""
        screen = self.screen()
        layout = self.layout()
        if screen is None or layout is None or self._fitting:
            return
        bar = self.scroll_area.verticalScrollBar().sizeHint().width()
        self._fitting = True
        try:
            self.scroll_area.setFixedHeight(0)
            layout.invalidate()
            rest = self._height(layout)
            area = screen.availableGeometry()
            room = area.height() - WINDOW_FRAME
            widest = min(self.at_text_size(WIDEST), area.width() * 9 // 10)
            width = self.width()
            while self._natural(width, bar) > room - rest and width < widest:
                width = min(widest, width + WIDEN_STEP)
            if width > self.width():
                self.setMinimumWidth(width)
                self.resize(width, self.height())
                layout.invalidate()
                rest = self._height(layout)
            # at the width it has beside a scroll bar: if it fits there, it fits
            natural = self._natural(max(width, self.width()), bar)
            # a scroll bar only on a screen too short for it all: shown "as
            # needed" it flashed over the text, cutting its words and last
            # line, until a later layout pass took it away (polyglotic-hq
            # 269, 278: seen on real windows at the first paint)
            self.scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                if natural <= room - rest
                else Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.scroll_area.setFixedHeight(max(MIN_SCROLL, min(natural, room - rest)))
            layout.invalidate()
            total = self._height(layout)
            self.setMinimumHeight(total)
            if self.height() != total:
                self.resize(self.width(), total)
        finally:
            self._fitting = False

    def _natural(self, width: int, bar: int) -> int:
        """The explanation's and choices' height with the screen `width`
        wide, beside a scroll bar `bar` wide."""
        margins = self.contentsMargins() + self.layout().contentsMargins()  # type: ignore[union-attr]
        natural = self.body.heightForWidth(
            width - margins.left() - margins.right() - bar
        )
        return natural if natural >= 0 else self.body.sizeHint().height()

    def _height(self, layout: QLayout) -> int:
        """What the screen's own layout needs at this width. Without a line
        that wraps in it (the age line was the last one), a layout has no
        height for a width and answers nothing: its size hint is the height."""
        if layout.hasHeightForWidth():
            return layout.totalHeightForWidth(self.width())
        return layout.totalSizeHint().height()

    def _ticked(self, on: bool) -> None:
        self.ok.setEnabled(on)
        if not on:
            self._agreed = None

    def accept(self) -> None:
        """Continue: the yes, if it's asked, given now. Ticked and then
        Back (the first run's) gives none (polyglotic-hq 250)."""
        if self.agree is not None and self.agree.isChecked():
            self._agreed = Agreement(TESTER_AGREEMENT_VERSION, self._clock())
        super().accept()

    def agreement(self) -> Agreement | None:
        """The yes given on this screen with Continue - the version and
        when - or None (not asked: given before; or not given)."""
        return self._agreed

    def _needed(self) -> str:
        return pc_or_mac(
            self.tr(
                "To caption what you hear, Polyglotic sends the speech it detects to "
                "our server. Audio and captions are used only to caption it for you - "
                "never stored. To run the service we keep your account, the minutes "
                "you listen, connection details (app version, the country you "
                "connect from, the kind of app you listen to - never its name) and "
                "your learning data: the dictionary words you look up, save or mark, "
                "and when - never the sentence around them. Your saved words and "
                "word statuses follow you to another PC; your lookups show us how "
                "people learn and what the dictionaries miss. You can delete your "
                "learning data any time. These aren't optional: without them "
                "there's no service."
            ),
            self.tr(
                "To caption what you hear, Polyglotic sends the speech it detects to "
                "our server. Audio and captions are used only to caption it for you - "
                "never stored. To run the service we keep your account, the minutes "
                "you listen, connection details (app version, the country you connect "
                "from, the kind of app you listen to - never its name) and your "
                "learning data: the dictionary words you look up, save or mark, and "
                "when - never the sentence around them. Your saved words and word "
                "statuses follow you to another computer; your lookups show us how "
                "people learn and what the dictionaries miss. You can delete your "
                "learning data any time. These aren't optional: without them there's "
                "no service."
            ),
        )

    def _text(self, text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Dim")
        label.setAccessibleName(name)
        label.setWordWrap(True)
        return label

    def _choice(
        self, name: str, title: str, explanation: str, layout: QVBoxLayout
    ) -> QCheckBox:
        box = QCheckBox(title)
        box.setObjectName(f"consent.{name}")
        box.setChecked(False)
        layout.addWidget(box)
        detail = self._text(explanation, f"{name}.detail")
        detail.setContentsMargins(24, 0, 0, 6)
        layout.addWidget(detail)
        return box

    def choices(self) -> tuple[bool, bool, bool]:
        """(usage statistics, crash reports, sharing exposure counts)."""
        return (
            self.usage.isChecked(),
            self.crashes.isChecked(),
            self.exposures.isChecked(),
        )
