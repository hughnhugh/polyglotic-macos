"""Settings > Captions > Lab: experimental caption settings, for the user
and the testers to tune by feel (polyglotic-hq 284; the values and their
measured ranges are `views.lab`'s). Marked as experimental, with its own
preview - the look's, so a change shows beside the control that made it -
and "Reset the lab".

Every control changes the running caption windows and both previews at
once (the look's view, `LookView.set_lab`), and is saved once it settles,
as the look is (`main.Panels`). A card of its own, in a file of its own,
so other sections of the page don't meet it.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QWidget,
)

from polyglotic_desktop.core.releases import flags
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import LINK_PX
from polyglotic_desktop.ui_next.caption_preview import CaptionPreview
from polyglotic_desktop.ui_next.controls import INSET, Row, Segmented, SwitchRow, label
from polyglotic_desktop.ui_next.panels import Panel
from polyglotic_desktop.ui_next.views.lab import (
    ARRIVAL_GAP_RANGE,
    ARRIVAL_GAP_STEP,
    CAPTION_GAP_RANGE,
    LINE_GAP_RANGE,
    LINE_GAP_STEP,
    LINK_PX_RANGE,
    LINK_PX_STEP,
    NEW_FOR_RANGE,
    NEW_FOR_STEP,
    OLDER_RANGE,
    OLDER_STEP,
    OLDER_STEPS_RANGE,
    ROW_GAP_RANGE,
    SPACING_STEP,
    CaptionLab,
    Fill,
    Join,
    Loading,
    NewFade,
    OwnLabel,
    Palette,
    Placing,
    Unfinished,
)
from polyglotic_desktop.ui_next.views.panels import LanguagesView, LookView

DEFAULT = CaptionLab()
"""The Lab untouched: each slider's own value, a notch on its scale."""


def _tr(text: str) -> str:
    return QApplication.translate("Lab", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Lab", text, None, n)


class Slider(QWidget):
    """A slider over `steps` of `step` from `low`, with its value said
    beside it (`say`). `default`: the setting's own value, where the
    slider shows it - the notch nearest to it is the default itself, so
    the slider moved away and back gives the default, not its neighbour
    on the scale (polyglotic-hq 287: Older captions' 72 % isn't a
    multiple of 5 % from 45 %, and came back as 70 %)."""

    def __init__(
        self,
        name: str,
        title: str,
        low: float,
        high: float,
        step: float,
        default: float | None = None,
    ) -> None:
        super().__init__()
        self.low, self.step, self.default = low, step, default
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName(name)
        self.slider.setAccessibleName(title)
        self.slider.setRange(0, round((high - low) / step))
        self.slider.setMinimumWidth(160)  # its handle doesn't grow with the text
        self.shown = label("", "Dim")
        self.shown.setMinimumWidth(style.px(96))
        line.addWidget(self.slider, 1)
        line.addWidget(self.shown)

    def value(self) -> float:
        if self.default is not None and self.slider.value() == self._at(self.default):
            return self.default
        return round(self.low + self.slider.value() * self.step, 2)

    def _at(self, value: float) -> int:
        return round((value - self.low) / self.step)

    def show_value(self, value: float, text: str) -> None:
        position = self._at(value)
        if position != self.slider.value():
            blocked = self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(blocked)
        self.shown.setText(text)


def _left(control: QWidget) -> QWidget:
    """`control` at the left of a row as wide as the card."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(control)
    row.addStretch(1)
    return box


def _pixels(value: float) -> str:
    return _tr("{px} px").format(px=f"{value:g}")


def _seconds(value: float) -> str:
    return _tr("{seconds}s").format(seconds=f"{value:g}")


def _percent(value: float) -> str:
    return _tr("{percent}%").format(percent=round(value * 100))


class LabPanel(Panel):
    """The Lab's controls, bound to the look's view."""

    load_wanted = Signal()
    """ "Open it on Learning", under Learning load: Learning's page, at the
    load's card for the language in use (polyglotic-hq 342)."""

    def __init__(
        self,
        view: LookView,
        parent: QWidget | None = None,
        languages: LanguagesView | None = None,
    ) -> None:
        """`languages`: the session's - its preview shows Mandarin in their
        characters (polyglotic-hq 400)."""
        super().__init__(
            _tr("Lab - experimental"),
            _tr(
                "Settings to try by feel. Each changes the caption windows and "
                "the preview at once. Tell us what works - they may change or go."
            ),
            parent=parent,
        )
        self.setObjectName("Card")
        self.view = view
        self.preview = CaptionPreview(view, unfinished=True, languages=languages)
        self.preview.setObjectName("lab.preview")
        self.add(self.preview)

        self.new_for = Slider(
            "lab.new_for",
            _tr("New captions stay bright"),
            *NEW_FOR_RANGE,
            NEW_FOR_STEP,
            DEFAULT.new_for,
        )
        self.new_for.slider.valueChanged.connect(
            lambda _: self._set(new_for=self.new_for.value())
        )
        self.add(
            Row(
                _tr("New captions stay bright"),
                _tr(
                    "How long a caption stays at full brightness after it arrives, "
                    "so several arriving together all look new. 0 s: only the "
                    "newest."
                ),
                self.new_for,
            )
        )
        self.new_fade = Segmented(
            [
                (NewFade.INSTANT, _tr("At once")),
                (NewFade.GRADUAL, _tr("Gradually")),
            ]
        )
        self.new_fade.setObjectName("lab.new_fade")
        self.new_fade.changed.connect(lambda v: self._set(new_fade=NewFade(v)))
        self.add(
            Row(
                _tr("Then it dims"),
                _tr("At once, or fading over a second and a half."),
                _left(self.new_fade),
            )
        )
        self.older = Slider(
            "lab.older", _tr("Older captions"), *OLDER_RANGE, OLDER_STEP, DEFAULT.older
        )
        self.older.slider.valueChanged.connect(
            lambda _: self._set(older=self.older.value())
        )
        self.add(
            Row(
                _tr("Older captions"),
                _tr(
                    "How bright the captions before the newest stay. 100%: as "
                    "bright as the newest. The translation dims a little less."
                ),
                self.older,
            )
        )
        self.older_steps = Slider(
            "lab.older_steps",
            _tr("Older captions dim"),
            *OLDER_STEPS_RANGE,
            1,
            DEFAULT.older_steps,
        )
        self.older_steps.slider.valueChanged.connect(
            lambda _: self._set(older_steps=round(self.older_steps.value()))
        )
        self.add(
            Row(
                _tr("Older captions dim"),
                _tr(
                    "All at once to Older captions' brightness, or step by step: "
                    "each caption back a little dimmer, over this many captions."
                ),
                self.older_steps,
            )
        )
        self.unfinished = Segmented(
            [
                (Unfinished.AS_NOW, _tr("As now")),
                (Unfinished.SAME, _tr("Same as finished")),
                (Unfinished.DIMMER, _tr("Dimmer")),
                (Unfinished.ITALIC, _tr("Italic")),
                (Unfinished.COLOUR, _tr("Colour")),
            ]
        )
        self.unfinished.setObjectName("lab.unfinished")
        self.unfinished.changed.connect(lambda v: self._set(unfinished=Unfinished(v)))
        self.add(
            Row(
                _tr("Text still being spoken"),
                _tr(
                    "How a line that may still change looks beside finished text. "
                    "As now: Steady's and Quick preview's dim italic line, Live "
                    "updates' a little dim. Colour: the theme's blue."
                ),
                _left(self.unfinished),
            )
        )
        self.loading = Segmented(
            [
                (Loading.BAR, _tr("Bar")),
                (Loading.DOTS, _tr("Three dots")),
                (Loading.ELLIPSIS, _tr("Ellipsis")),
            ]
        )
        self.loading.setObjectName("lab.loading")
        self.loading.changed.connect(lambda v: self._set(loading=Loading(v)))
        self.add(
            Row(
                _tr("While a caption is on its way"),
                _tr(
                    "The sign under the captions that speech was heard. Ellipsis: "
                    "the line still being spoken ends in one; with none yet, one "
                    "stands where the bar would."
                ),
                _left(self.loading),
            )
        )
        self.link_px = Slider(
            "lab.link_px", _tr("Underline thickness"), *LINK_PX_RANGE, LINK_PX_STEP
        )
        self.link_px.slider.valueChanged.connect(
            lambda _: self._set(link_px=self.link_px.value())
        )
        self.add(
            Row(
                _tr("Underline thickness"),
                _tr(
                    "A word link's underline, finer than Word links' Thin, Medium "
                    "and Thick. Picking one of those there again puts it back."
                ),
                self.link_px,
            )
        )
        self.row_gap = Slider(
            "lab.row_gap", _tr("Space above the translation"), *ROW_GAP_RANGE,
            SPACING_STEP, DEFAULT.row_gap,
        )  # fmt: skip
        self.row_gap.slider.valueChanged.connect(
            lambda _: self._set(row_gap=self.row_gap.value())
        )
        self.add(
            Row(
                _tr("Space above the translation"),
                _tr("Between what was said and its translation."),
                self.row_gap,
            )
        )
        self.caption_gap = Slider(
            "lab.caption_gap", _tr("Space between captions"), *CAPTION_GAP_RANGE,
            SPACING_STEP, DEFAULT.caption_gap,
        )  # fmt: skip
        self.caption_gap.slider.valueChanged.connect(
            lambda _: self._set(caption_gap=self.caption_gap.value())
        )
        self.add(
            Row(
                _tr("Space between captions"),
                _tr("Between one caption and the next."),
                self.caption_gap,
            )
        )
        self.arrival_gap = Slider(
            "lab.arrival_gap",
            _tr("Gap between new captions"),
            *ARRIVAL_GAP_RANGE,
            ARRIVAL_GAP_STEP,
            DEFAULT.arrival_gap,
        )
        self.arrival_gap.slider.valueChanged.connect(
            lambda _: self._set(arrival_gap=self.arrival_gap.value())
        )
        self.add(
            Row(
                _tr("Gap between new captions"),
                _tr(
                    "Captions that arrive together come in one at a time, at least "
                    "this far apart and in order - none is dropped. 0 s: as they "
                    "come. None waits longer than the longest wait for text."
                ),
                self.arrival_gap,
            )
        )
        self.line_gap = Slider(
            "lab.line_gap",
            _tr("Gap between new lines"),
            *LINE_GAP_RANGE,
            LINE_GAP_STEP,
            DEFAULT.line_gap,
        )
        self.line_gap.slider.valueChanged.connect(
            lambda _: self._set(line_gap=self.line_gap.value())
        )
        self.add(
            Row(
                _tr("Gap between new lines"),
                _tr(
                    "A new caption's lines show one at a time, this far apart, "
                    "instead of all together. 0 s: together, as now. None waits "
                    "longer than the longest wait for text."
                ),
                self.line_gap,
            )
        )

        self._own_speech()
        self._fill()
        self._learning_load()

        self.reset = QPushButton(_tr("Reset the lab"))
        self.reset.setObjectName("lab.reset")
        self.reset.setToolTip(_tr("Every setting in the Lab as Polyglotic has it."))
        self.reset.clicked.connect(view.reset_lab)
        reset = QHBoxLayout()
        reset.setContentsMargins(INSET - 1, 0, 0, 0)
        reset.addWidget(self.reset)
        reset.addStretch(1)
        self.add(reset)
        self.bind(view)
        self.refresh()

    def _own_speech(self) -> None:
        """Your own speech's look, to try (305): on the right, tinted, a bar
        at its side, its "You" label - each off, or as now, by default."""
        self.own: dict[str, SwitchRow] = {}
        for name, title, detail in (
            (
                "own_right",
                _tr("Your speech on the right"),
                _tr("What you say lines up on the right, as in a chat."),
            ),
            (
                "own_tint",
                _tr("A tint behind your speech"),
                _tr("A soft panel of your label's colour behind what you say."),
            ),
            (
                "own_bar",
                _tr("A bar beside your speech"),
                _tr("A line of your label's colour at the side of what you say."),
            ),
        ):
            row = SwitchRow(title, detail, f"lab.{name}")
            row.switch.toggled.connect(
                lambda on, name=name: self._set(**{name: bool(on)})
            )
            self.own[name] = row
            self.add(row)
        self.own_label = Segmented(
            [
                (OwnLabel.AS_NOW, _tr("As now")),
                (OwnLabel.BADGE, _tr("Badge")),
                (OwnLabel.NONE, _tr("None")),
            ]
        )
        self.own_label.setObjectName("lab.own_label")
        self.own_label.changed.connect(lambda v: self._set(own_label=OwnLabel(v)))
        self.add(
            Row(
                _tr("Your speech's label"),
                _tr('"You" over what you say: as now, in a badge, or not shown.'),
                _left(self.own_label),
            )
        )

    def _fill(self) -> None:
        """Captions fill the width, to try (309): a clause a row as now, or
        each caption poured into lines as wide as the window - and what
        stands between its clauses then."""
        self.fill = Segmented(
            [
                (Fill.CLAUSES, _tr("Off")),
                (Fill.STACKED, _tr("Translation below")),
                (Fill.PAIRED, _tr("Line by line")),
            ]
        )
        self.fill.setObjectName("lab.fill")
        self.fill.setToolTip(
            _tr(
                "Line by line: a line of what was said, then the line of its "
                "translation, both cut where their words match. A long clause "
                "that can't be cut so wraps as it does now."
            )
        )
        self.fill.changed.connect(lambda v: self._set(fill=Fill(v)))
        self.fill_row = Row(
            _tr("Captions fill the width"),
            _tr(
                "Off: each clause on a row of its own, as now. Translation "
                "below: a caption's clauses run on in lines as wide as the "
                "window, and its translation fills the lines under them. No "
                "Arrows while captions fill the width."
            ),
            _left(self.fill),
        )
        self.add(self.fill_row)
        self.join = Segmented(
            [
                (Join.ELLIPSIS, _tr("Ellipsis")),
                (Join.LINE_ENDS, _tr("At line ends too")),
                (Join.SPACE, _tr("Space")),
            ]
        )
        self.join.setObjectName("lab.join")
        self.join.changed.connect(lambda v: self._set(join=Join(v)))
        self.join_row = Row(
            _tr("Between clauses"),
            _tr(
                "When captions fill the width: an ellipsis where one clause "
                "ends and the next begins, one at the end of every line that "
                "runs on as well, or only a space. Choosing one while Captions "
                "fill the width is Off sets it to Translation below."
            ),
            _left(self.join),
        )
        self.add(self.join_row)
        # the one layout (340, decision 0132): off by default, to try
        self.flow = SwitchRow(
            _tr("New layout"),
            _tr(
                "Captions are laid out a new way, however they fill the width: "
                "Arrows and word links work in all of them and in Learning "
                "load, and Line by line always fills its lines."
            ),
            "lab.flow",
        )
        self.flow.switch.toggled.connect(lambda on: self._set(flow=bool(on)))
        self.add(self.flow)
        self.run_on = SwitchRow(
            _tr("Captions run on"),
            _tr(
                "A caption carries on in the line the one before ended in, "
                "instead of starting a line of its own. Turning it on also turns "
                "on New layout and Line by line."
            ),
            "lab.run_on",
        )
        self.run_on.switch.toggled.connect(lambda on: self._set(run_on=bool(on)))
        self.add(self.run_on)
        # captions filling the width: behind their flag, off (polyglotic-hq
        # 555) - each of these rows pours them
        for poured in (self.fill_row, self.join_row, self.run_on):
            poured.setHidden(not flags.on(flags.FILL_THE_WIDTH))
        self.aligned = SwitchRow(
            _tr("Parts lined up"),
            _tr(
                "Each part of what was said starts at the same place as its "
                "translation, so a word's translation is under it - however "
                "captions fill the width. Turning it on also turns on New layout."
            ),
            "lab.aligned",
        )
        self.aligned.switch.toggled.connect(lambda on: self._set(aligned=bool(on)))
        self.add(self.aligned)
        # where a line's parts go in its room (458): packed, as now, by default
        self.placing = Segmented(
            [
                (Placing.PACKED, _tr("Packed")),
                (Placing.NEAREST, _tr("Nearest their links")),
                (Placing.EVENLY, _tr("Evenly")),
            ]
        )
        self.placing.setObjectName("lab.placing")
        self.placing.changed.connect(lambda v: self._set(placing=Placing(v)))
        self.add(
            Row(
                _tr("Parts placed"),
                _tr(
                    "Where the parts of a line go in the room the line has. "
                    "Packed: each straight after the one before, as now. Nearest "
                    "their links: each part moves over its translation's words, "
                    "so the word links are as short as they can be. Evenly: a "
                    "full line's parts are spread over the width. "
                    "Choosing one also turns on New layout."
                ),
                _left(self.placing),
            )
        )

    def _learning_load(self) -> None:
        """Learning load's viewing mode (324, 489): on or off, and its
        colours. The load's words and its rules are on Learning."""
        self.load = SwitchRow(
            _tr("Learning load"),
            _tr(
                "Every word in a colour by how well you know it: red, never "
                "met or far past what you know; the colours between, words you "
                "have heard or partly know; green, mastered. In place of the "
                "marks under new words."
            ),
            "lab.load",
        )
        self.load.switch.toggled.connect(lambda on: self._set(load=bool(on)))
        self.add(self.load)
        # where its words are: a link to them while it's on (342)
        self.to_load = label(
            _tr("{open} - its words, the check and its settings.").format(
                open=f"<a href='load'>{_tr('Open it on Learning')}</a>"
            ),
            "Faint",
            wrap=True,
        )
        self.to_load.setContentsMargins(INSET, 0, 0, 0)
        self.to_load.linkActivated.connect(lambda _: self.load_wanted.emit())
        self.add(self.to_load)
        self.load_colours = Segmented(
            [
                (Palette.RED_GREEN, _tr("Red to green")),
                (Palette.ORANGE_BLUE, _tr("Orange to blue")),
            ]
        )
        self.load_colours.setObjectName("lab.load_colours")
        self.load_colours.changed.connect(lambda v: self._set(load_colours=Palette(v)))
        self.add(
            Row(
                _tr("Its colours"),
                _tr(
                    "Red to green, or orange to blue if red and green look alike "
                    "to you. Both go from darker to lighter as you know a word "
                    "better. Choosing one turns Learning load on."
                ),
                _left(self.load_colours),
            )
        )

    def _set(self, **changes: object) -> None:
        # a choice brings what it needs with it (`CaptionLab.choose`, 365)
        self.view.set_lab(self.view.value.lab.choose(**changes))

    def refresh(self) -> None:
        lab: CaptionLab = self.view.value.lab
        self.new_for.show_value(
            lab.new_for,
            _tr("Only the newest") if lab.new_for <= 0 else _seconds(lab.new_for),
        )
        self.new_fade.set_value(lab.new_fade)
        self.unfinished.set_value(lab.unfinished)
        self.older_steps.show_value(
            lab.older_steps,
            _tr("All at once")
            if lab.older_steps <= 1
            else _trn("Over %n caption(s)", lab.older_steps),
        )
        self.loading.set_value(lab.loading)
        thickness = (
            LINK_PX[self.view.value.link_line] if lab.link_px is None else lab.link_px
        )
        self.link_px.show_value(thickness, _pixels(thickness))
        self.row_gap.show_value(lab.row_gap, _pixels(lab.row_gap))
        self.caption_gap.show_value(lab.caption_gap, _pixels(lab.caption_gap))
        self.new_fade.setEnabled(lab.new_for > 0)
        self.older.show_value(
            lab.older, _tr("No dimming") if lab.older >= 1.0 else _percent(lab.older)
        )
        for name, row in self.own.items():
            row.switch.set_quietly(bool(getattr(lab, name)))
        self.own_label.set_value(lab.own_label)
        self.fill.set_value(lab.fill)
        # never greyed: a choice there brings Translation below with it (368)
        self.join.set_value(lab.join)
        self.flow.switch.set_quietly(lab.flow)
        # each shows what the captions do: off where it has no effect (its
        # value kept for when it does), and a click there makes it work (365)
        self.run_on.switch.set_quietly(lab.run_on and lab.line_by_line)
        self.aligned.switch.set_quietly(lab.lined_up)
        # as the switches above: Packed where New layout is off (its value kept)
        self.placing.set_value(lab.placing if lab.flow else Placing.PACKED)
        self.load.switch.set_quietly(lab.load)
        self.load_colours.set_value(lab.load_colours)
        self.to_load.setVisible(lab.load)
        self.arrival_gap.show_value(
            lab.arrival_gap,
            _tr("As they come") if lab.arrival_gap <= 0 else _seconds(lab.arrival_gap),
        )
        self.line_gap.show_value(
            lab.line_gap,
            _tr("Together") if lab.line_gap <= 0 else _seconds(lab.line_gap),
        )
