"""The Sound card: which speakers, which mic, and whether what I say is
captioned (polyglotic-hq 372; `views.sound` says what each does). Home has
it under Caption; Settings > Speech has it too - two cards, one view, so
a choice in either shows in both.

Top to bottom:
- **What you hear**: the speakers everything the PC plays is heard from -
  Windows' default (naming the device it is now) or one plugged in - and,
  under it, that the apps added on Home are heard whichever speakers play
  them;
- **What you say**: Caption what I say (in every window - the tray's
  "Caption my own speech"), the mic, and its level while it's captioned.

A device chosen that isn't plugged in now says so: Windows' default is
used until it is. Devices' names stay on this PC.
"""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from polyglotic_desktop.ports.capture import SoundDevice
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Card, Combo, Row, SwitchRow, label
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.sound import Sound, SoundView

LEVEL_MS = 100
"""How often the mic's level is shown again, while it's captioned and the
card is on screen."""
METER_WIDTH, METER_HEIGHT = 96, 6


def _tr(text: str) -> str:
    return QApplication.translate("SoundCard", text)


def default_name(device: SoundDevice | None) -> str:
    """Windows' default, as a list shows it: with the device it is now."""
    if device is None:
        return pc_or_mac(_tr("This PC's default"), _tr("This Mac's default"))
    return pc_or_mac(
        _tr("This PC's default ({device})"), _tr("This Mac's default ({device})")
    ).format(device=device.name)


class LevelMeter(QWidget):
    """The mic's level: a bar filled as loud as it is (`views.sound.level_of`),
    in the theme's accent; empty and faint while the mic isn't captioned."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sound.level")
        self.level: float | None = None
        self.setFixedSize(style.px(METER_WIDTH), style.px(METER_HEIGHT) + 4)
        self.setAccessibleName(_tr("Microphone level"))

    def show_level(self, level: float | None) -> None:
        if level != self.level:
            self.level = level
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.palette().windowText().color()
        track = QColor(text)
        track.setAlphaF(0.18)
        bar = self.rect().adjusted(0, 2, 0, -2)
        radius = bar.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, radius, radius)
        if self.level:
            lit = QColor(style.current()["ACCENT"])
            filled = bar.adjusted(0, 0, -round(bar.width() * (1 - self.level)), 0)
            painter.setBrush(lit)
            painter.drawRoundedRect(filled, radius, radius)
        painter.end()


class SoundCard(Card):
    """Home's (and Settings') Sound card, bound to `view`."""

    def __init__(self, view: SoundView, parent: QWidget | None = None) -> None:
        super().__init__(_tr("Sound"), parent=parent)
        self.view = view
        self._shown: Sound | None = None

        self.add(label(_tr("What you hear"), "RowTitle"))
        self.speakers = Combo()
        self.speakers.setObjectName("sound.speakers")
        self.speakers.setAccessibleName(_tr("Speakers"))
        self.speakers.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.speakers.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.speakers.activated.connect(
            lambda index: view.set_speaker(self.speakers.itemData(index))
        )
        self.speakers_row = Row(
            _tr("Speakers"),
            pc_or_mac(
                _tr(
                    "Used for Everything the PC plays. Apps you add are captioned "
                    "whichever speakers they play on."
                ),
                _tr(
                    "Used for Everything the Mac plays. Apps you add are captioned "
                    "whichever speakers they play on."
                ),
            ),
            self.speakers,
        )
        self.add(self.speakers_row)

        self.add(label(_tr("What you say"), "RowTitle"))
        self.my_speech = SwitchRow(
            _tr("Show my speech in every window"),
            _tr("Your mic is sent for your captions only while this is on."),
            "sound.my_speech",
        )
        self.my_speech.switch.clicked.connect(lambda on: view.set_my_speech(bool(on)))
        self.add(self.my_speech)
        self.mics = Combo()
        self.mics.setObjectName("sound.mics")
        self.mics.setAccessibleName(_tr("Microphone"))
        self.mics.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.mics.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mics.activated.connect(
            lambda index: view.set_mic(self.mics.itemData(index))
        )
        self.meter = LevelMeter()
        mic = QWidget()
        line = QHBoxLayout(mic)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        line.addWidget(self.mics, 1)
        line.addWidget(self.meter, 0, Qt.AlignmentFlag.AlignVCenter)
        self.mics_row = Row(_tr("Microphone"), "", mic)
        self.add(self.mics_row)
        # a list opened: devices plugged in since are in it
        for box in (self.speakers, self.mics):
            box.installEventFilter(self)
        self.levels = QTimer(self)
        self.levels.setInterval(LEVEL_MS)
        self.levels.timeout.connect(view.read_level)
        stop = view.subscribe(self.refresh)
        self.destroyed.connect(lambda *_: stop())
        self.refresh()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and watched in (
            self.speakers,
            self.mics,
        ):
            self.view.look_again()
        return False

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # the devices, the first time (Windows takes 4-10 ms to list them:
        # measured 2026-11-16); after that, as a list is opened. Once the
        # window's shown, not while it's being shown: Home is the first page,
        # and listing them and filling both lists in its show held the
        # start's first paint back (polyglotic-hq 400)
        if not self._listed():
            QTimer.singleShot(0, self, self._first_look)
        self._read_levels()

    def _listed(self) -> bool:
        devices = self.view.value.devices
        return bool(devices.speakers or devices.mics)

    def _first_look(self) -> None:
        if self.isVisible() and not self._listed():
            self.view.look_again()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.levels.stop()

    def _read_levels(self) -> None:
        """The level is read while the card shows and the mic is captioned:
        never a timer on a page no one sees."""
        if self.isVisible() and self.view.value.my_speech:
            if not self.levels.isActive():
                self.levels.start()
        else:
            self.levels.stop()

    def refresh(self) -> None:
        value = self.view.value
        shown = self._shown
        self._shown = value
        if (
            shown is None
            or shown.devices != value.devices
            or (shown.speaker, shown.mic) != (value.speaker, value.mic)
        ):
            _fill(self.speakers, value.speakers(), value.speaker, value.speaker_missing)
            _fill(self.mics, value.mics(), value.mic, value.mic_missing)
        self.my_speech.switch.set_quietly(value.my_speech)
        self.meter.show_level(value.level if value.my_speech else None)
        self._read_levels()
        self.meter.setToolTip(
            _tr("Your microphone's level now")
            if value.my_speech
            else _tr("Your mic's level, shown while your speech is captioned")
        )


def _fill(
    box: QComboBox,
    choices: list[tuple[str | None, SoundDevice | None]],
    chosen: str | None,
    missing: bool,
) -> None:
    """`box` listing `choices` - Windows' default first - with `chosen`
    selected; one not plugged in now is listed first, as that."""
    box.blockSignals(True)
    box.clear()
    if missing:
        box.addItem(
            pc_or_mac(
                _tr("Not plugged in - this PC's default is used"),
                _tr("Not plugged in - this Mac's default is used"),
            ),
            chosen,
        )
    for device_id, device in choices:
        if device_id is None or device is None:
            box.addItem(default_name(device), None)
        else:
            box.addItem(device.name, device_id)
    box.setCurrentIndex(
        0 if missing or chosen is None else max(0, box.findData(chosen))
    )
    box.blockSignals(False)
