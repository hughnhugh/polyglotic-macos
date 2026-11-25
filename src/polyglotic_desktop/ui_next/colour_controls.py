"""The look's colour controls (polyglotic-hq 248's sections 2.2 and 6, the
user's F11 and F16; built by 261):

- **`RecommendedTiles`** - the three recommended looks (polyglotic-hq
  532), each tile a caption in it - pinyin, Chinese in its face, English
  - with its name under it; picking one sets the whole look;
- **`PresetTiles`** - the ten colour presets as tiles, each drawn with its
  own panel and two lines in its two text colours, its name under them;
  a "Custom" tile, chosen, while the colours are no preset's;
- **`ExactColour`** - one colour: its swatch with a few that read well
  (`controls.ColourChoice`), its exact value as a hex field ("#ffd76e"),
  and "Pick..." - the colour dialog (`pick_colour`);
- **`CaptionTextSliders`** - the caption text (`views.tone`; polyglotic-hq
  481): contrast, soft to crisp; vibrance, muted to vivid; thickness,
  Light to Bold - today's look in the middle of each.

They draw what they're told (`show`) and say what the learner chose
(`chosen`); the look's panel binds them to its view.
"""

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QLineEdit,
    QPushButton,
    QSlider,
    QWidget,
)

from polyglotic_desktop.ui_next import caption_faces, fonts, style
from polyglotic_desktop.ui_next.controls import ColourChoice, Measured, Segmented, label
from polyglotic_desktop.ui_next.views.caption_window import TextEdge
from polyglotic_desktop.ui_next.views.presets import (
    BY_KEY,
    LOOKS,
    PRESETS,
    ColourPreset,
    RecommendedLook,
    hex_colour,
)
from polyglotic_desktop.ui_next.views.tone import (
    CONTRAST_RANGE,
    THICKNESS,
    THICKNESSES,
    VIBRANCE_RANGE,
    reading_grey,
)

TILE = (112, 60)
"""A preset's tile at 100 % text size: its sample, then its name."""
CUSTOM = "custom"


def _tr(text: str) -> str:
    return QApplication.translate("ColourControls", text)


def preset_name(key: str) -> str:
    return {
        "classic": _tr("Classic"),
        "broadcast": _tr("Broadcast"),
        "teletext": _tr("Teletext"),
        "ember": _tr("Ember"),
        "violet": _tr("Violet"),
        "forest": _tr("Forest"),
        "paper": _tr("Paper"),
        "quiet": _tr("Quiet"),
        "high_contrast": _tr("High contrast"),
        "clear": _tr("Clear"),
        CUSTOM: _tr("Custom"),
    }[key]


def preset_tip(key: str) -> str:
    """What a preset suits (248's section 6.2)."""
    return {
        "classic": _tr(
            "White and warm yellow on a dark panel: Polyglotic's own, for most video."
        ),
        "broadcast": _tr(
            "White and yellow on solid black, as on TV: for bright, busy scenes."
        ),
        "teletext": _tr(
            "White and cyan on solid black: for warm films where yellow blends in."
        ),
        "ember": _tr(
            "Pale blue and orange, a cool and a warm colour: safe for red-green "
            "colour blindness; for games and streams."
        ),
        "violet": _tr("Lilac and gold on deep violet: for anime and night scenes."),
        "forest": _tr(
            "Mint and green on dark green: easy on the eyes for long sessions, "
            "but the two rows are harder to tell apart with green colour blindness."
        ),
        "paper": _tr(
            "Dark text on cream: for bright rooms, light apps, documents and calls."
        ),
        "quiet": _tr(
            "Soft grey and amber on a faint panel: when the video matters more. "
            "Faint over bright scenes."
        ),
        "high_contrast": _tr("White and bright yellow on solid black: for low vision."),
        "clear": _tr(
            "White and orange on black, the rows furthest apart in brightness: "
            "safe for every kind of colour blindness."
        ),
    }[key]


def look_tip(key: str) -> str:
    """What a recommended look sets (532)."""
    return {
        "quiet": _tr(
            "Soft grey and amber on a dark panel, every line crisp and vivid, "
            "Semibold with a soft shadow, readings in grey, Chinese in "
            "calligraphy."
        ),
        "paper": _tr(
            "Dark ink on cream, a little crisper, readings in grey, Chinese in "
            "a textbook's handwriting: for bright rooms, light apps and calls."
        ),
        "broadcast": _tr(
            "White and yellow on solid black, as on TV: crisp and Bold, readings "
            "a size larger, Chinese in a plain sans. For bright, busy scenes."
        ),
    }[key]


LOOK_TILE = (176, 100)
"""A recommended look's tile at 100 % text size: its caption, then its
name."""
SAMPLE = ("nǐ hǎo", "你好", "Hello")
"""A recommended look's caption: a reading, Chinese, its translation."""


CHOSEN_RING_PX = 2
"""Logical pixels around the selected colour sample."""


def _paint_sample(
    painter: QPainter, button: QPushButton, sample: QRectF, panel: QColor
) -> None:
    painter.setBrush(panel)
    painter.setPen(
        QPen(QColor(style.current()["ACCENT"]), CHOSEN_RING_PX)
        if button.isChecked()
        else QPen(Qt.PenStyle.NoPen)
    )
    painter.drawRoundedRect(sample, 6, 6)
    if button.hasFocus():
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(style.current()["FOCUS"]), 1, Qt.PenStyle.DotLine))
        painter.drawRoundedRect(QRectF(button.rect()).adjusted(2, 2, -2, -2), 8, 8)


class RecommendedTile(QPushButton):
    """One recommended look (532): a caption in it - pinyin in its grey,
    Chinese in its face and weight, the translation - on its panel, and
    its name under it."""

    def __init__(self, look: RecommendedLook, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.look = look
        self.setObjectName(f"look.recommended.{look.key}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("tile", True)
        self.setText(preset_name(look.key))
        self.setAccessibleName(preset_name(look.key))
        self.setToolTip(look_tip(look.key))
        self.setAccessibleDescription(look_tip(look.key))

    def sizeHint(self) -> QSize:
        return QSize(style.px(LOOK_TILE[0]), style.px(LOOK_TILE[1]))

    def minimumSizeHint(self) -> QSize:
        return QSize(style.px(LOOK_TILE[0] * 0.8), style.px(LOOK_TILE[1]))

    def paintEvent(self, event: QPaintEvent) -> None:
        caption_faces.load()  # the faces drawn here, if no caption has been yet
        theme = style.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        chosen = self.isChecked()
        pad = style.px(6)
        sample = QRectF(box.left() + pad, box.top() + pad, box.width() - 2 * pad, 0)
        sample.setHeight(box.height() * 0.68)
        preset = self.look.preset
        _paint_sample(painter, self, sample, QColor(preset.background))
        families = list(fonts.caption_families("zh", dict(self.look.faces).get("zh")))
        size = sample.height() / 3.6
        grey = reading_grey(preset.background, preset.original)
        rows = (
            # at least 12 px, the interface's smallest (the UI lab's check)
            (
                SAMPLE[0],
                _font(
                    fonts.reading_families(families), max(style.px(12), size * 0.5), 600
                ),
                grey,
            ),
            (SAMPLE[1], _font(families, size, self.look.thickness), preset.original),
            (
                SAMPLE[2],
                _font(list(fonts.caption_families("en")), size * 0.8, 500),
                preset.translation,
            ),
        )
        heights = [QFontMetricsF(font).height() for _, font, _ in rows]
        y = sample.center().y() - sum(heights) / 2
        for (text, font, colour), height in zip(rows, heights, strict=True):
            painter.setFont(font)
            painter.setPen(QColor(colour))
            ascent = QFontMetricsF(font).ascent()
            painter.drawText(QPointF(sample.left() + style.px(10), y + ascent), text)
            y += height
        painter.setFont(self.font())
        painter.setPen(QColor(theme["TEXT" if chosen else "TEXT_DIM"]))
        words = QRectF(box.left() + pad, sample.bottom(), box.width() - 2 * pad, 0)
        words.setBottom(box.bottom() - 2)
        painter.drawText(
            words,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.fontMetrics().elidedText(
                self.text(), Qt.TextElideMode.ElideRight, int(words.width())
            ),
        )
        painter.end()


def _font(families: list[str], px: float, weight: int) -> QFont:
    font = QFont()
    font.setFamilies(families)
    font.setPixelSize(max(8, round(px)))
    font.setWeight(QFont.Weight(weight))
    return font


class RecommendedTiles(QWidget):
    """The three recommended looks side by side - fewer to a row where they
    don't fit - one chosen while the look is still all it set."""

    chosen = Signal(str)
    """A recommended look's key."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        # its minimum is `minimumSizeHint`'s - one tile wide - not the grid's
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(style.px(8))
        self.tiles: dict[str, RecommendedTile] = {}
        for look in LOOKS:
            tile = RecommendedTile(look, self)
            tile.clicked.connect(lambda _=False, k=look.key: self._clicked(k))
            self.tiles[look.key] = tile
        self.columns = 0
        self._place(len(LOOKS))

    def _place(self, columns: int) -> None:
        if columns == self.columns:
            return
        if self.columns:
            self.grid.setColumnStretch(self.columns, 0)
        self.columns = columns
        for tile in self.tiles.values():
            self.grid.removeWidget(tile)
        for index, tile in enumerate(self.tiles.values()):
            self.grid.addWidget(tile, index // columns, index % columns)
        self.grid.setColumnStretch(columns, 1)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        """As narrow as one tile: narrower, it puts fewer to a row."""
        hint = super().minimumSizeHint()
        hint.setWidth(style.px(LOOK_TILE[0]))
        return hint

    def resizeEvent(self, event: QResizeEvent) -> None:
        gap = self.grid.spacing()
        fit = (event.size().width() + gap) // (style.px(LOOK_TILE[0]) + gap)
        self._place(max(1, min(len(LOOKS), fit)))
        super().resizeEvent(event)

    def _clicked(self, key: str) -> None:
        self.tiles[key].setChecked(True)  # a click on the chosen one keeps it
        self.chosen.emit(key)

    def show_look(self, look: RecommendedLook | None) -> None:
        """`look`: the recommended look the look is now - None: none."""
        for key, tile in self.tiles.items():
            tile.setChecked(look is not None and key == look.key)


class PresetTile(QPushButton):
    """One preset: its panel, a line in each text colour, its name."""

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.colours = ("#ffffff", "#ffd76e", "#0a0c10")
        self.setObjectName(f"look.preset.{key}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("tile", True)
        self.setText(preset_name(key))  # its name, to a screen reader too
        self.setAccessibleName(preset_name(key))
        if key in BY_KEY:
            self.show_colours(BY_KEY[key])

    def show_colours(self, preset: ColourPreset | tuple[str, str, str]) -> None:
        colours = (
            (preset.original, preset.translation, preset.background)
            if isinstance(preset, ColourPreset)
            else preset
        )
        if colours != self.colours:
            self.colours = colours
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(style.px(TILE[0]), style.px(TILE[1]))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = style.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        chosen = self.isChecked()
        pad = style.px(6)
        sample = QRectF(box.left() + pad, box.top() + pad, box.width() - 2 * pad, 0)
        sample.setHeight(box.height() * 0.5)
        original, translation, panel = (QColor(c) for c in self.colours)
        _paint_sample(painter, self, sample, panel)
        painter.setPen(Qt.PenStyle.NoPen)
        bar = max(2.0, sample.height() / 7)
        for row, (colour, share) in enumerate(((original, 0.62), (translation, 0.74))):
            width = sample.width() * share
            top = sample.top() + sample.height() * (0.32 + 0.3 * row) - bar / 2
            painter.setBrush(colour)
            painter.drawRoundedRect(
                QRectF(sample.center().x() - width / 2, top, width, bar),
                bar / 2,
                bar / 2,
            )
        painter.setPen(QColor(theme["TEXT" if chosen else "TEXT_DIM"]))
        words = QRectF(box.left() + pad, sample.bottom(), box.width() - 2 * pad, 0)
        words.setBottom(box.bottom() - 2)
        painter.drawText(
            words,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.fontMetrics().elidedText(
                self.text(), Qt.TextElideMode.ElideRight, int(words.width())
            ),
        )
        painter.end()


class PresetTiles(QWidget):
    """The ten presets as tiles - as many to a row as fit, at most
    `COLUMNS` - and "Custom" after them while the colours are no preset's;
    one chosen at a time."""

    chosen = Signal(str)
    """A preset's key."""

    COLUMNS = 5
    """Tiles to a row at most: two rows of five in Settings' column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        # its minimum is `minimumSizeHint`'s - one tile wide - not the grid's
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(style.px(8))
        self.tiles: dict[str, PresetTile] = {}
        for preset in (*PRESETS, None):
            key = preset.key if preset is not None else CUSTOM
            tile = PresetTile(key, self)
            tile.setToolTip(preset_tip(key) if preset is not None else "")
            tile.clicked.connect(lambda _=False, k=key: self._clicked(k))
            self.tiles[key] = tile
        self.columns = 0
        self._place(self.COLUMNS)
        self.tiles[CUSTOM].hide()

    def _place(self, columns: int) -> None:
        """The tiles, `columns` to a row."""
        if columns == self.columns:
            return
        if self.columns:
            self.grid.setColumnStretch(self.columns, 0)
        self.columns = columns
        for tile in self.tiles.values():
            self.grid.removeWidget(tile)
        for index, tile in enumerate(self.tiles.values()):
            self.grid.addWidget(tile, index // columns, index % columns)
        self.grid.setColumnStretch(columns, 1)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        """As narrow as one tile: narrower, it puts fewer to a row."""
        hint = super().minimumSizeHint()
        hint.setWidth(style.px(TILE[0]))
        return hint

    def resizeEvent(self, event: QResizeEvent) -> None:
        gap = self.grid.spacing()
        fit = (event.size().width() + gap) // (style.px(TILE[0]) + gap)
        self._place(max(1, min(self.COLUMNS, fit)))
        super().resizeEvent(event)

    def _clicked(self, key: str) -> None:
        # a click on the chosen tile keeps it chosen: Qt unticks a ticked
        # button, and the look, already that preset, doesn't change to put
        # it back - the tiles showed no preset at all (269)
        self.tiles[key].setChecked(True)
        if key == CUSTOM:  # it is what's shown already: nothing to choose
            return
        self.chosen.emit(key)

    def show_preset(
        self,
        preset: ColourPreset | None,
        colours: tuple[str, str, str],
        started_from: str | None,
    ) -> None:
        """`preset`: the one the colours are, or None - "Custom", drawn in
        `colours` (what was said, the translation, the panel), from the
        preset it `started_from`."""
        chosen = preset.key if preset is not None else CUSTOM
        for key, tile in self.tiles.items():
            tile.setChecked(key == chosen)
        custom = self.tiles[CUSTOM]
        custom.setVisible(preset is None)
        if preset is None:
            custom.show_colours(colours)
            name = preset_name(started_from) if started_from else None
            custom.setToolTip(
                _tr("Your own colours, from {preset}.").format(preset=name)
                if name
                else _tr("Your own colours.")
            )


def pick_colour(colour: str, parent: QWidget, title: str) -> str | None:
    """The colour dialog, from `colour`: the one picked ("#rrggbb"), or None
    if it was cancelled.

    Without Qt's eyedropper ("Pick Screen Color"): it reads the pixel under
    the mouse anywhere on the screen while it picks, and Polyglotic never
    reads the user's screen - the privacy notice says nothing of it (261's
    decision 1, taken as 1b, 2026-11-09)."""
    picked = QColorDialog.getColor(
        QColor(colour),
        parent,
        title,
        QColorDialog.ColorDialogOption.NoEyeDropperButton,
    )
    return picked.name() if picked.isValid() else None


class ExactColour(QWidget):
    """One of the look's colours: a few that read well, its exact value, and
    "Pick..." (the colour dialog)."""

    chosen = Signal(str)
    """An exact colour, "#rrggbb"."""

    def __init__(
        self, choices: Sequence[str], colour: str, name: str, what: str
    ) -> None:
        """`name`: the object names' start ("look.original_colour"); `what`:
        which colour it is, as the row says it ("What was said")."""
        super().__init__()
        self.what = what
        self.colour = colour
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(style.px(6))
        self.swatches = ColourChoice(choices, colour, name)
        self.swatches.setAccessibleName(_tr("Colour: {what}").format(what=what))
        self.swatches.chosen.connect(self.chosen)
        row.addWidget(self.swatches)
        self.hex = QLineEdit(colour)
        self.hex.setObjectName(f"{name}.hex")
        self.hex.setAccessibleName(_tr("{what}: exact colour").format(what=what))
        self.hex.setPlaceholderText("#rrggbb")
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(style.px(84))
        self.hex.editingFinished.connect(self._typed)
        row.addWidget(self.hex)
        self.pick = QPushButton(_tr("Pick…"))
        self.pick.setObjectName(f"{name}.pick")
        self.pick.setAccessibleName(_tr("Pick a colour: {what}").format(what=what))
        self.pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pick.clicked.connect(self._pick)
        row.addWidget(self.pick)
        row.addStretch(1)

    def show_colour(self, colour: str) -> None:
        self.colour = colour
        self.swatches.show_colour(colour)
        if not self.hex.hasFocus():
            self.hex.setText(colour)

    def _typed(self) -> None:
        exact = hex_colour(self.hex.text())
        if exact is None:  # not a colour: back to the one there is
            self.hex.setText(self.colour)
        elif exact != self.colour:
            self.hex.setText(exact)
            self.chosen.emit(exact)

    def _pick(self) -> None:
        picked = pick_colour(
            self.colour, self, _tr("Pick a colour: {what}").format(what=self.what)
        )
        if picked is not None and picked != self.colour:
            self.chosen.emit(picked)


def thickness_name(weight: int) -> str:
    """A thickness by its weight's name (`views.tone.THICKNESSES`)."""
    return {
        300: _tr("Light"),
        400: _tr("Regular"),
        500: _tr("Medium"),
        600: _tr("Semibold"),
        700: _tr("Bold"),
    }[weight]


class CaptionTextSliders(QWidget):
    """Caption text (481): contrast, vibrance and thickness - a slider each,
    its name above it and its two ends named beside it (Soft and Crisp,
    Muted and Vivid, Light and Bold), today's look in the middle;
    thickness's step by name in its tip. The names over the sliders and
    the ends in columns as wide as their longest, so a language with long
    words still fits a transcript's rail (polyglotic-hq 503). Each says where it moved to as it moves
    (`contrast_moved`, `vibrance_moved`, `thickness_moved`: a weight), so
    the windows follow the drag; the arrow keys move it a step, Page Up
    and Page Down a bigger one, Home and End to an end."""

    contrast_moved = Signal(int)
    vibrance_moved = Signal(int)
    thickness_moved = Signal(int)
    edge_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(style.px(8))
        self.ends: dict[str, tuple[Measured, Measured]] = {}
        """Each slider's two ends' names, by its object name."""
        self.contrast = self._slider(
            grid,
            0,
            "look.contrast",
            _tr("Contrast"),
            (_tr("Soft"), _tr("Crisp")),
            CONTRAST_RANGE,
            _tr(
                "How strongly captions stand out from their panel. Soft is as "
                "faint as a line still being spoken, never too faint to read; "
                "Crisp draws every line at full strength."
            ),
        )
        self.vibrance = self._slider(
            grid,
            1,
            "look.vibrance",
            _tr("Vibrance"),
            (_tr("Muted"), _tr("Vivid")),
            VIBRANCE_RANGE,
            _tr(
                "How vivid captions' colours are. Dull colours change most; "
                "white and grey stay as they are, and word links keep their "
                "colours so you can tell them apart."
            ),
        )
        self.thickness = self._slider(
            grid,
            2,
            "look.thickness",
            _tr("Thickness"),
            (_tr("Light"), _tr("Bold")),
            (0, len(THICKNESSES) - 1),
            _tr(
                "How thick captions' letters are, and their readings a step "
                "thicker. A font without a weight draws the nearest it has."
            ),
        )
        self.thickness.setSingleStep(1)
        self.thickness.setPageStep(1)
        self.thickness.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.thickness.setTickInterval(1)
        self.thickness.setValue(THICKNESSES.index(THICKNESS))
        self._thickness_tip = self.thickness.toolTip()
        self._name_thickness(THICKNESS)
        self.edge = Segmented(
            [
                (TextEdge.NONE.value, _tr("None")),
                (TextEdge.SHADOW.value, _tr("Soft shadow")),
                (TextEdge.OUTLINE.value, _tr("Outline")),
            ],
            TextEdge.NONE.value,
        )
        self.edge.setObjectName("look.edge")
        self.edge.setToolTip(
            _tr(
                "What's drawn around captions' letters, to read over a busy "
                "video. The panel behind them has its own slider, below."
            )
        )
        self.edge.changed.connect(lambda v: self.edge_chosen.emit(str(v)))
        grid.addWidget(label(_tr("Around the letters")), 6, 0, 1, 3)
        grid.addWidget(self.edge, 7, 0, 1, 3, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(1, 1)
        self.contrast.valueChanged.connect(self.contrast_moved)
        self.vibrance.valueChanged.connect(self.vibrance_moved)
        self.thickness.valueChanged.connect(self._thickness_moved)

    def _thickness_moved(self, step: int) -> None:
        weight = THICKNESSES[step]
        self._name_thickness(weight)
        self.thickness_moved.emit(weight)

    def _name_thickness(self, weight: int) -> None:
        """The step by name - in its tip and to a screen reader - rather
        than beside it, where a narrow Look (the rail's) cut it off."""
        name = thickness_name(weight)
        self.thickness.setToolTip(f"{name}. {self._thickness_tip}")
        self.thickness.setAccessibleDescription(name)

    def offer(self, steps: tuple[int, ...]) -> None:
        """Only `steps` on the thickness slider (`views.tone.offered`;
        polyglotic-hq 532): its light end named as the lightest offered.
        A thickness chosen below them shows at the lightest, which is
        what it draws."""
        low = THICKNESSES.index(steps[0])
        if self.thickness.minimum() != low:
            blocked = self.thickness.blockSignals(True)
            self.thickness.setMinimum(low)
            self.thickness.blockSignals(blocked)
        self.ends["look.thickness"][0].setText(thickness_name(steps[0]))

    def thickness_now(self) -> str:
        """The step chosen, by name ("Medium")."""
        return thickness_name(THICKNESSES[self.thickness.value()])

    def _slider(
        self,
        grid: QGridLayout,
        at: int,
        name: str,
        title: str,
        ends: tuple[str, str],
        bounds: tuple[int, int],
        tip: str,
    ) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setObjectName(name)
        slider.setAccessibleName(title)
        slider.setAccessibleDescription(tip)
        slider.setToolTip(tip)
        slider.setRange(*bounds)
        slider.setSingleStep(5)
        slider.setPageStep(25)
        slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        slider.setMinimumWidth(style.px(100))
        grid.addWidget(label(title), 2 * at, 0, 1, 3)
        low, high = (label(end, "Dim") for end in ends)
        self.ends[name] = (low, high)
        grid.addWidget(low, 2 * at + 1, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(slider, 2 * at + 1, 1)
        grid.addWidget(high, 2 * at + 1, 2)
        return slider

    def show_text(
        self, contrast: int, vibrance: int, thickness: int, edge: str = "none"
    ) -> None:
        """Where the four are now - as told, not as moved: no signal."""
        self.edge.set_value(edge)
        step = THICKNESSES.index(thickness) if thickness in THICKNESSES else 2
        for slider, value in (
            (self.contrast, contrast),
            (self.vibrance, vibrance),
            (self.thickness, step),
        ):
            if slider.value() != value:
                blocked = slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(blocked)
        self._name_thickness(THICKNESSES[step])
