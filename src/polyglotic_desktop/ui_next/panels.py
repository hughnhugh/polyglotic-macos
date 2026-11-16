"""The shared panels - Languages, Timing and the look's groups (Look, Word
links, Behaviour, Reset) - each one widget class bound to one view
(`views.panels`), usable in any container: Settings > Captions, a
transcript's rail (polyglotic-hq project 109's structure, section 4;
248's Settings > Captions, section 2.2).

A panel draws its view's value and hands the learner's changes to it;
every panel bound to the same view shows a change at once (it's told
through `subscribe`, and stops being told when it goes). Content and
wording are today's Languages and Captions pages', less what moved to the
caption window - "Translate into", the text size, the position and the
width - and 248's copy (section 2.4).

- **Languages:** "This window" (its language - or
  Original only - and Show my speech here) only in a transcript's rail,
  otherwise one line saying each window picks its own; Spoken language;
  Second language, a row per language in use; Translate live captions;
  Names and slang. Settings > Captions shows it as **Speech**, without
  what's learned (the Learning page's) or live translation (Timing's).
- **Timing:** Caption timing, with the chosen one's sentence, and under
  it only the chosen timing's own settings, in seconds, each with what it
  trades (polyglotic-hq 295): Steady, the longest wait for text; Quick
  preview, when its dim lines come (fixed) and the longest wait; Live
  updates, how often, Translate live captions (in Settings) and the
  longest wait - one longest wait for every timing (polyglotic-hq 277,
  DECISIONS.md #117), and the page says so.
- **Look:** in Settings, a live preview (`caption_preview`); the colour presets (`colour_controls.PresetTiles`), each
  colour exactly (a hex field and "Pick...": `ExactColour`), how solid
  the panel is, the font, and the original / the language / the source
  shown.
- **Word links:** the style, the underline and its gap, the detail.
- **Behaviour:** New captions, Fade after quiet; and a hidden window -
  how long it still listens (5, 15 or 60 minutes, or never) and whether
  it's shown when speech starts (polyglotic-hq 335). (Which new words
  captions point out is Learning's: word introductions, on its page -
  polyglotic-hq 262.)
- **Reset:** the look to Polyglotic's defaults.

In Settings each setting has its line under its name (`notes`, F18); in a
transcript's narrow rail, on hover (176). No stylesheet of their own: the
window they're in dresses them (`style.stylesheet`), so they take its
theme.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.display import (
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.hidden import PAUSE_CHOICES
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_preview import CaptionPreview
from polyglotic_desktop.ui_next.caption_window import timing_tip
from polyglotic_desktop.ui_next.colour_controls import ExactColour, PresetTiles
from polyglotic_desktop.ui_next.controls import (
    INSET,
    Card,
    Combo,
    Row,
    Segmented,
    SwitchButton,
    SwitchRow,
    WrapButton,
    label,
)
from polyglotic_desktop.ui_next.languages import (
    language_name,
    not_offered_note,
    target_languages,
)
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.spoken_list import SpokenPicker
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY
from polyglotic_desktop.ui_next.views.panels import (
    COLOUR_CHOICES,
    FADE_CHOICES,
    PREVIEW_LINES_AT,
    LanguagesView,
    LookView,
    Shared,
    TimingView,
    WindowLanguageView,
    interval_choices,
    settle_choices,
    wait_choices,
)
from polyglotic_desktop.ui_next.views.presets import preset_of


def _tr(text: str) -> str:
    return QApplication.translate("Panels", text)


def _seconds(value: float) -> str:
    return _tr("{seconds}s").format(seconds=f"{value:g}")


def _minutes(value: int | None) -> str:
    """A hidden window's limit as Behaviour offers it: "5 min", "1 h",
    "Never" (polyglotic-hq 335)."""
    if value is None:
        return _tr("Never")
    if value % 60 == 0:
        return _tr("{hours} h").format(hours=value // 60)
    return _tr("{minutes} min").format(minutes=value)


def _row(layout: QHBoxLayout | QVBoxLayout, widget: QWidget) -> None:
    """`widget` at the left of a row of its own (it keeps its own width)."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch(1)
    layout.addLayout(row)


def _left(widget: QWidget) -> QWidget:
    """`widget` at the left of a box as wide as the row."""
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    _row(column, widget)
    return box


class Panel(Card):
    """A card bound to views: refreshed when any of them changes, and
    unbound when it goes."""

    def bind(self, *views: Shared[Any]) -> None:
        stops = [view.subscribe(self._changed) for view in views]
        self.destroyed.connect(lambda *_: [stop() for stop in stops])

    def _changed(self) -> None:
        with spans.span("panels.refresh"):
            self.refresh()

    def refresh(self) -> None:
        raise NotImplementedError


# -- Languages -------------------------------------------------------------------------


class LanguagesPanel(Panel):
    """The session's languages; with `window`, its transcript's "This
    window" rows too. `speech`: Settings > Captions' Speech - without
    what's learned (the Learning page's) or live translation (Timing's)."""

    def __init__(
        self,
        session: LanguagesView,
        window: WindowLanguageView | None = None,
        parent: QWidget | None = None,
        speech: bool = False,
    ) -> None:
        super().__init__(_tr("Speech") if speech else _tr("Languages"), parent=parent)
        self.setObjectName("Card")
        self.session = session
        self.this_window = window
        value = session.value

        self.translate_into: QComboBox | None = None
        self.show_mic: SwitchButton | None = None
        if window is None:
            self.add(
                label(
                    _tr(
                        "Each window picks its own language - or Original only - "
                        "and whether your speech shows there."
                    ),
                    "Dim",
                    wrap=True,
                )
            )
        else:
            self._this_window(window)
            # after the window's own two rows, the rest is every window's
            self.add(label(_tr("Every window").upper(), "SectionLabel"))

        # every language the speech model hears, findable by name, the
        # recent ones first (`spoken_list`; polyglotic-hq 317)
        self.spoken = SpokenPicker(
            value.spoken, recent=lambda: session.value.recent_spoken
        )
        self.spoken.changed.connect(lambda v: session.set_spoken(str(v) if v else None))
        spoken = Row(
            _tr("Spoken language"),
            _tr(
                "Detect finds the language each time someone speaks, and handles "
                "mixed talk. Name it and every caption is heard as that language: "
                "steadier for an app that speaks one, but a line in another may "
                "come out wrong."
            ),
            self.spoken,
        )
        self.add(spoken)

        # beside the language it's about: Mandarin's script, converted on
        # this PC - with Detect too (polyglotic-hq 375; decision 0164)
        self.mandarin_script = Segmented(
            [
                (False, _tr("Simplified ({sample})").format(sample="汉字")),
                (True, _tr("Traditional ({sample})").format(sample="漢字")),
            ],
            value.traditional,
        )
        self.mandarin_script.setObjectName("languages.mandarin_script")
        self.mandarin_script.changed.connect(
            lambda on: session.set_traditional(bool(on))
        )
        self.mandarin_row = Row(
            _tr("Show Mandarin in"),
            _tr(
                "The characters Mandarin's captions are written in, Detect "
                "included. Lookups, the transcript, copy and Anki use the "
                "same; translations into Chinese keep the language you picked."
            ),
            self.mandarin_script,
        )
        self.add(self.mandarin_row)

        self.second_box = QWidget()
        self.second_rows = QVBoxLayout(self.second_box)
        self.second_rows.setContentsMargins(0, 0, 0, 0)
        self.second_rows.setSpacing(6)
        self.second: dict[str, QComboBox] = {}
        self._in_use: tuple[str, ...] | None = None
        self.add(
            Row(
                _tr("Second language"),
                _tr(
                    "Lines already in a window's language get no translation there. "
                    "Pick a second language and they get one into it, in yellow like "
                    "every translation."
                ),
                self.second_box,
            )
        )

        self.translate_live: SwitchButton | None = None
        if not speech:
            live = SwitchRow(
                _tr("Translate live captions"),
                _tr(
                    "With Live updates (Timing). Off: live captions show what was "
                    "said, and the translation arrives at the pause."
                ),
                "languages.translate_live",
            )
            self.translate_live = live.switch
            self.translate_live.set_quietly(value.translate_live)
            self.translate_live.toggled.connect(session.set_translate_live)
            self.add(live)

        self.hints = QLineEdit(", ".join(value.spelling_hints))
        self.hints.setObjectName("languages.spelling_hints")
        self.hints.setAccessibleName(_tr("Names and slang"))
        # examples a learner knows at a glance, in both languages (F13, 249)
        self.hints.setPlaceholderText(_tr("e.g. rizz, no cap, yyds, 鸡你太美, 原神"))
        self.hints.editingFinished.connect(lambda: session.set_hints(self.hints.text()))
        self.add(
            Row(
                _tr("Names and slang"),
                _tr(
                    "Slang, memes and names the speech model might mishear, written "
                    "your way and separated by commas. Used only to recognise "
                    "speech; the server doesn't keep them."
                ),
                self.hints,
                tip=_tr(
                    "For example slang - rizz, no cap, yyds (永远的神), 绝绝子; "
                    "memes - 鸡你太美; a streamer's name or a game's - Valorant, "
                    "原神. Write each the way you want to see it."
                ),
            )
        )
        self.bind(session, *([window] if window is not None else []))
        self.refresh()

    def _this_window(self, window: WindowLanguageView) -> None:
        self.window_title = label("", "SectionLabel")
        self.add(self.window_title)
        box = Combo()
        box.setObjectName("languages.translate_into")
        box.setAccessibleName(_tr("Translate into"))
        box.addItem(_tr("Original only (no translation)"), ORIGINAL_ONLY)
        for code in target_languages():
            box.addItem(language_name(str(code)), str(code))
        box.currentIndexChanged.connect(
            lambda _: window.set_translate_into(str(box.currentData()))
        )
        self.translate_into = box
        self.add(Row(_tr("Translate into"), not_offered_note(), box))
        mic = SwitchRow(
            _tr("Show my speech here"),
            _tr("Your microphone is sent to the server only while this is on."),
            "languages.show_mic",
        )
        self.show_mic = mic.switch
        self.show_mic.set_quietly(window.value.show_mic)
        self.show_mic.toggled.connect(window.set_show_mic)
        self.add(mic)

    def refresh(self) -> None:
        value = self.session.value
        self.spoken.set_value(value.spoken)
        self.mandarin_script.set_value(value.traditional)
        # only where Mandarin can be heard: Detect, or Mandarin named
        self.mandarin_row.setHidden(value.spoken not in (None, "zh"))
        if self.translate_live is not None:
            self.translate_live.set_quietly(value.translate_live)
        if not self.hints.hasFocus():
            self.hints.setText(", ".join(value.spelling_hints))
        if value.in_use != self._in_use:
            self._second_rows(value.in_use)
        for target, box in self.second.items():
            index = max(0, box.findData(value.second_languages.get(target)))
            if index != box.currentIndex():
                blocked = box.blockSignals(True)
                box.setCurrentIndex(index)
                box.blockSignals(blocked)
        if self.this_window is not None and self.translate_into is not None:
            own = self.this_window.value
            self.window_title.setText(
                _tr("This window - {app}").format(app=own.label).upper()
            )
            box = self.translate_into
            index = max(0, box.findData(own.translate_into))
            if index != box.currentIndex():
                blocked = box.blockSignals(True)
                box.setCurrentIndex(index)
                box.blockSignals(blocked)
            if self.show_mic is not None:
                self.show_mic.set_quietly(own.show_mic)

    def _second_rows(self, in_use: tuple[str, ...]) -> None:
        """A row for each language in use - rebuilt only when they change."""
        self._in_use = in_use
        while self.second_rows.count():
            old = self.second_rows.takeAt(0)
            widget = old.widget() if old is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.second = {}
        if not in_use:
            self.second_rows.addWidget(
                label(
                    _tr("Add an app first: each window's language gets a row here."),
                    "Faint",
                    wrap=True,
                )
            )
        for target in in_use:
            box = Combo()
            box.setObjectName(f"languages.second.{target}")
            box.setAccessibleName(
                _tr("Lines already in {language} are translated into").format(
                    language=language_name(target)
                )
            )
            box.addItem(_tr("None"), None)
            for code in target_languages():
                if code != target:
                    box.addItem(language_name(str(code)), str(code))
            box.setMinimumWidth(style.px(160))
            box.currentIndexChanged.connect(
                lambda _, b=box, t=target: self.session.set_second(t, b.currentData())
            )
            line = QWidget()
            row = QVBoxLayout(line)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(3)
            row.addWidget(
                label(
                    _tr("Lines already in {language} are translated into:").format(
                        language=language_name(target)
                    ),
                    "Dim",
                    wrap=True,
                )
            )
            _row(row, box)
            self.second_rows.addWidget(line)
            self.second[target] = box
        # made after the panel: Tab reaches them where they are, under
        # Spoken language and Show Mandarin in, not after Names and slang
        before: QWidget = self.mandarin_script.buttons[-1]
        for second in self.second.values():
            QWidget.setTabOrder(before, second)
            before = second


# -- Timing ----------------------------------------------------------------------------


class TimingPanel(Panel):
    """When captions appear, for every window: the caption timing, and
    under it only the chosen timing's own settings, in seconds, each with
    one line saying what it trades (polyglotic-hq 295). With `languages`
    (Settings > Captions): Translate live captions too, under Live updates
    every."""

    def __init__(
        self,
        view: TimingView,
        parent: QWidget | None = None,
        languages: LanguagesView | None = None,
    ) -> None:
        super().__init__(_tr("Timing"), parent=parent)
        self.view = view
        self.languages = languages
        self.mode = Segmented(
            [
                (CaptionMode.STEADY, _tr("Steady")),
                (CaptionMode.PREVIEW, _tr("Quick preview")),
                (CaptionMode.LIVE, _tr("Live updates")),
            ],
            view.value.mode,
        )
        modes = (CaptionMode.STEADY, CaptionMode.PREVIEW, CaptionMode.LIVE)
        self.mode.setObjectName("timing.mode")
        for button, mode in zip(self.mode.buttons, modes, strict=True):
            button.setToolTip(timing_tip(mode))  # what each does (F22, 249)
        self.mode.changed.connect(lambda m: view.set_mode(CaptionMode(m)))
        self.sentence = label("", "Faint", wrap=True)
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        _row(column, self.mode)
        column.addWidget(self.sentence)
        self.add(Row(_tr("Caption timing"), "", box))
        # Quick preview's own: when its dim lines come - fixed, so shown as
        # seconds rather than offered (295)
        #: between the times in a list, "1.5s, 3s" (Chinese: 、)
        between = _tr(", ")
        self.preview_at = label(
            _tr("{times} into each caption").format(
                times=between.join(_seconds(s) for s in PREVIEW_LINES_AT)
            )
        )
        self.preview = Row(
            _tr("Dim lines at"),
            _tr("Fixed: a first guess at the words, replaced by the finished caption."),
            self.preview_at,
        )
        self.add(self.preview)
        self.interval = Combo()
        self.interval.setObjectName("timing.live_interval")
        self.interval.setAccessibleName(_tr("Live updates every"))
        self.interval.setMinimumWidth(style.px(120))
        self._intervals: list[float] = []
        self.interval.currentIndexChanged.connect(self._interval_chosen)
        live = _left(self.interval)
        # a longer interval than the longest wait isn't followed: said (295)
        self.live_note = label("", "Dim", wrap=True)
        self.live_note.hide()  # hidden before it has a parent: never a window
        live_column = live.layout()
        assert isinstance(live_column, QVBoxLayout)
        live_column.addWidget(self.live_note)
        self.live = Row(
            _tr("Live updates every"),
            _tr(
                "Shorter: text sooner, rewritten more often; the first update "
                "waits for a second of speech."
            ),
            live,
            tip=_tr(
                "Less than a second of speech is too little for the speech model "
                "to tell the language."
            ),
        )
        self.add(self.live)
        self.translate_live: SwitchButton | None = None
        self.translate_row: SwitchRow | None = None
        if languages is not None:
            self.translate_row = SwitchRow(
                _tr("Translate live captions"),
                _tr(
                    "With Live updates: translate the moving line too. Off: live "
                    "captions show what was said, and the translation arrives at "
                    "the pause."
                ),
                "timing.translate_live",
            )
            self.translate_live = self.translate_row.switch
            self.translate_live.toggled.connect(languages.set_translate_live)
            self.add(self.translate_row)
        self.wait = Combo()
        self.wait.setObjectName("timing.max_wait")
        self.wait.setAccessibleName(_tr("Longest wait for text"))
        self.wait.setMinimumWidth(style.px(120))
        self._waits: list[float] = []
        self.wait.currentIndexChanged.connect(self._wait_chosen)
        # one longest wait for every timing (277, DECISIONS.md #117): said
        self.wait_row = Row(
            _tr("Longest wait for text"),
            _tr(
                "Shorter: text sooner while someone talks on, more half "
                "sentences - the same in every timing."
            ),
            _left(self.wait),
        )
        self.add(self.wait_row)
        self.settle = Combo()
        self.settle.setObjectName("timing.settle_after")
        self.settle.setAccessibleName(_tr("Text can still change for"))
        self.settle.setMinimumWidth(style.px(120))
        self._settles: list[float] = []
        self.settle.currentIndexChanged.connect(self._settle_chosen)
        # what each choice costs: said in words, so the choice is an informed
        # one - the figures (309, read speech only) stay in decision 0099, as
        # no accuracy figure is said that polyglotic-hq hasn't cleared (330).
        # Shown in every timing, Steady too: its dim line at the longest wait
        # and a short caption joined to the next are heard again, and this
        # decides how much of them stays (core.listening.settling).
        self.settle_row = Row(
            _tr("Text can still change for"),
            _tr(
                "How long words on screen may still be corrected as more is "
                "heard. Shorter: fewer words change while you read, and more "
                "mistakes stay as first heard - most of all when Live updates "
                "come faster than every second."
            ),
            _left(self.settle),
        )
        self.add(self.settle_row)
        if languages is not None:
            self.bind(view, languages)
        else:
            self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        self.mode.set_value(value.mode)
        self.sentence.setText(
            {
                # what polyglotic-hq project 145 measured on the real models
                # (2026-11-07, p50): Steady's first words 4.5-5.5 s, the preview
                # line 1.9 s, the finished caption 0.4-0.6 s after the speech
                CaptionMode.STEADY: _tr(
                    "Steady: each sentence once, finished, about half a second after "
                    "it ends - with a dim line first if the speaker talks on for "
                    "{seconds} seconds."
                ).format(seconds=f"{value.max_wait:g}"),
                CaptionMode.PREVIEW: _tr(
                    "Quick preview: words in about 2 seconds, in a dim line; the full "
                    "caption and its translation about half a second after the "
                    "sentence ends."
                ),
                CaptionMode.LIVE: _tr(
                    "Live updates: the caption rewrites itself while the speaker "
                    "goes on."
                ),
            }[value.mode]
        )
        self.preview.setVisible(value.mode is CaptionMode.PREVIEW)
        self.live.setVisible(value.mode is CaptionMode.LIVE)
        slower = value.live_every < value.live_interval
        if slower:
            self.live_note.setText(
                _tr(
                    "Text still updates every {seconds}: the longest wait for "
                    "text, below, is shorter."
                ).format(seconds=_seconds(value.live_every))
            )
        self.live_note.setVisible(slower)
        if self.languages is not None and self.translate_row is not None:
            assert self.translate_live is not None
            self.translate_live.set_quietly(self.languages.value.translate_live)
            self.translate_row.setVisible(value.mode is CaptionMode.LIVE)
        choices = interval_choices(value.live_interval)
        blocked = self.interval.blockSignals(True)
        if choices != self._intervals:
            self._intervals = choices
            self.interval.clear()
            for seconds in choices:
                self.interval.addItem(_seconds(seconds), seconds)
        self.interval.setCurrentIndex(choices.index(value.live_interval))
        self.interval.blockSignals(blocked)
        waits = wait_choices(value.max_wait)
        blocked = self.wait.blockSignals(True)
        if waits != self._waits:
            self._waits = waits
            self.wait.clear()
            for seconds in waits:
                self.wait.addItem(_seconds(seconds), seconds)
        self.wait.setCurrentIndex(waits.index(value.max_wait))
        self.wait.blockSignals(blocked)
        settles = settle_choices(value.settle_after)
        blocked = self.settle.blockSignals(True)
        if settles != self._settles:
            self._settles = settles
            self.settle.clear()
            for seconds in settles:
                self.settle.addItem(_seconds(seconds), seconds)
        self.settle.setCurrentIndex(settles.index(value.settle_after))
        self.settle.blockSignals(blocked)

    def _interval_chosen(self, index: int) -> None:
        if 0 <= index < len(self._intervals):
            self.view.set_live_interval(self._intervals[index])

    def _wait_chosen(self, index: int) -> None:
        if 0 <= index < len(self._waits):
            self.view.set_max_wait(self._waits[index])

    def _settle_chosen(self, index: int) -> None:
        if 0 <= index < len(self._settles):
            self.view.set_settle_after(self._settles[index])


# -- Look ------------------------------------------------------------------------------


class FontBox(Combo):
    """The fonts on this PC - listed only when first opened (there can be
    hundreds), so the panel opens at once."""

    def __init__(self) -> None:
        super().__init__()
        self.addItem(_tr("Polyglotic (Default)"), None)
        self._listed = False

    def show_family(self, family: str | None) -> None:
        index = 0 if family is None else self.findData(family)
        if index < 0 and family is not None:  # not listed yet, or not on this PC
            self.addItem(family, family)
            index = self.count() - 1
        if index != self.currentIndex():
            blocked = self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(blocked)

    def showPopup(self) -> None:
        if not self._listed:
            self._listed = True
            chosen = self.currentData()
            blocked = self.blockSignals(True)
            self.clear()
            self.addItem(_tr("Polyglotic (Default)"), None)
            for family in QFontDatabase.families():
                if not family.startswith("@"):  # Windows' sideways copies
                    self.addItem(family, family)
            self.blockSignals(blocked)
            self.show_family(chosen)
        super().showPopup()


class _LookGroup(Panel):
    """A group of the look's settings, bound to the one `LookView`.
    `notes`: each setting's line under its name (Settings > Captions, F18);
    without, it's said on hover only (a transcript's narrow rail, 176)."""

    def __init__(
        self,
        title: str,
        view: LookView,
        notes: bool,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, subtitle, parent=parent)
        self.view = view
        self.notes = notes

    def _row(self, title: str, line: str, control: QWidget) -> Row:
        row = Row(title, line if self.notes else "", control, tip=line)
        self.add(row)
        return row

    def _switch(
        self,
        name: str,
        title: str,
        line: str,
        then: Callable[[bool], None],
    ) -> SwitchButton:
        row = SwitchRow(title, line if self.notes else "", f"look.{name}", line)
        row.switch.toggled.connect(then)
        self.add(row)
        return row.switch


class LookPanel(_LookGroup):
    """How every caption window looks: the colours, the panel, the font and
    what's shown above and in each caption (248's Settings > Captions >
    Look)."""

    def __init__(
        self,
        view: LookView,
        notes: bool = False,
        parent: QWidget | None = None,
        preview: bool = False,
        languages: LanguagesView | None = None,
    ) -> None:
        """`preview`: the live preview at its top (Settings > Captions), in
        the characters `languages` shows Mandarin in (polyglotic-hq 400)."""
        super().__init__(_tr("Look"), view, notes, _tr("Every caption window."), parent)
        value = view.value

        self.preview: CaptionPreview | None = None
        if preview:
            self.preview = CaptionPreview(view, languages=languages)
            self.add(self.preview)
        self.presets = PresetTiles()
        self.presets.setObjectName("look.presets")
        self.presets.chosen.connect(view.set_preset)
        self._row(
            _tr("Preset"),
            _tr(
                "A matched set of colours for the text and the panel. Pick one, "
                "then change any colour."
            ),
            self.presets,
        )
        self.colours: dict[str, ExactColour] = {}
        for which, title, note in (
            (
                "original",
                _tr("What was said"),
                _tr("The colour of the words as they were spoken."),
            ),
            (
                "translation",
                _tr("The translation"),
                _tr(
                    "The colour of the translation. Keep it different from what "
                    "was said, so you can tell the two apart at a glance."
                ),
            ),
            (
                "background",
                _tr("The panel"),
                _tr("The box behind the text. How solid it is is the slider below."),
            ),
        ):
            choice = ExactColour(
                COLOUR_CHOICES[which],
                getattr(value, which),
                f"look.{which}_colour",
                title,
            )
            choice.chosen.connect(lambda c, w=which: view.set_colour(w, c))
            self.colours[which] = choice
            self._row(title, note, choice)

        background = QWidget()
        line = QHBoxLayout(background)
        line.setContentsMargins(0, 0, 0, 0)
        self.background = QSlider(Qt.Orientation.Horizontal)
        self.background.setObjectName("look.background")
        self.background.setAccessibleName(_tr("Panel: how solid"))
        self.background.setRange(0, 100)
        self.background.setMinimumWidth(160)  # its handle doesn't grow with the text
        self.background.setValue(round(value.opacity * 100))
        self.background_shown = label("", "Dim")
        self.background_shown.setMinimumWidth(style.px(40))
        self.background.valueChanged.connect(self._background_moved)
        line.addWidget(self.background, 1)
        line.addWidget(self.background_shown)
        self._row(
            _tr("Panel: how solid"),
            _tr(
                "0 % is no box at all; 100 % hides the video behind the text. Over "
                "a bright film, 70 % or more keeps the text readable."
            ),
            background,
        )

        self.font_box = FontBox()
        self.font_box.setObjectName("look.font")
        self.font_box.setAccessibleName(_tr("Font"))
        self.font_box.setMinimumWidth(style.px(160))
        self.font_box.currentIndexChanged.connect(
            lambda _: view.set_font(self.font_box.currentData())
        )
        self._row(
            _tr("Font"),
            pc_or_mac(
                _tr(
                    "Any font on this PC. Chinese and Japanese fall back to a font "
                    "that has them if yours doesn't."
                ),
                _tr(
                    "Any font on this Mac. Chinese and Japanese fall back to a font "
                    "that has them if yours doesn't."
                ),
            ),
            _left(self.font_box),
        )

        self.original = self._switch(
            "show_original",
            _tr("Show the original above the translation"),
            _tr(
                "What was said, in its own language, over its translation. Off: "
                "just the translation."
            ),
            view.set_show_original,
        )
        self.language = self._switch(
            "show_language",
            _tr("Show the language"),
            _tr("Which language each caption was spoken in, in small type above it."),
            view.set_show_language,
        )
        self.source = self._switch(
            "show_source",
            _tr("Show the source"),
            _tr(
                "The app's name, or “You”, above each caption, in its colour. "
                "Names and colours are on Home."
            ),
            view.set_show_source,
        )
        self.bind(view)
        self.refresh()

    def _background_moved(self, percent: int) -> None:
        self.background_shown.setText(f"{percent}%")
        self.view.set_opacity(percent / 100)

    def refresh(self) -> None:
        value = self.view.value
        percent = round(value.opacity * 100)
        if percent != self.background.value():
            blocked = self.background.blockSignals(True)
            self.background.setValue(percent)
            self.background.blockSignals(blocked)
        self.background_shown.setText(f"{percent}%")
        self.font_box.show_family(value.font)
        self.presets.show_preset(
            preset_of(value),
            (value.original, value.translation, value.background),
            self.view.started_from,
        )
        for which, choice in self.colours.items():
            choice.show_colour(getattr(value, which))
        self.original.set_quietly(value.show_original)
        self.language.set_quietly(value.show_language)
        self.source.set_quietly(value.show_source)


class WordLinksPanel(_LookGroup):
    """Word links' style - the button on a caption window turns them off
    and back on to it (249, F9) - their underline, and how many words."""

    learning_wanted = Signal()
    """"Which words are pointed out as new is on Learning": its link."""

    def __init__(
        self,
        view: LookView,
        notes: bool = False,
        learning: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """`learning`: the line linking to the Learning page under it."""
        super().__init__(_tr("Word links"), view, notes, parent=parent)
        value = view.value
        self.word_links = Segmented(
            [
                (WordLinks.OFF, _tr("Off")),
                (WordLinks.HOVER, _tr("On hover")),
                (WordLinks.COLOURS, _tr("Underline")),
                (WordLinks.ARROWS, _tr("Arrows")),  # its curves back (F7, 249)
            ],
            value.word_links,
        )
        self.word_links.setObjectName("look.word_links")
        self.word_links.changed.connect(lambda v: view.set_word_links(WordLinks(v)))
        self._row(
            _tr("Style"),
            _tr(
                "Which words of what was said and its translation mean the same. On "
                "hover: point at a word. Underline: matching words share a colour. "
                "Arrows: curves join them. The button on a caption window turns "
                "this off and on."
            ),
            self.word_links,
        )
        self.link_line = Segmented(
            [
                (LinkLine.THIN, _tr("Thin")),
                (LinkLine.MEDIUM, _tr("Medium")),
                (LinkLine.THICK, _tr("Thick")),
            ],
            value.link_line,
        )
        self.link_line.setObjectName("look.link_line")
        self.link_line.changed.connect(lambda v: view.set_link_line(LinkLine(v)))
        self._row(
            _tr("Underline"),
            _tr(
                "How thick the line under linked words is. Thicker is easier to "
                "see under Chinese characters."
            ),
            self.link_line,
        )
        self.link_gap = Segmented(
            [
                (LinkGap.CLOSE, _tr("Close")),
                (LinkGap.MEDIUM, _tr("Medium")),
                (LinkGap.FAR, _tr("Far")),
            ],
            value.link_gap,
        )
        self.link_gap.setObjectName("look.link_gap")
        self.link_gap.changed.connect(lambda v: view.set_link_gap(LinkGap(v)))
        self._row(
            _tr("Underline gap"),
            _tr(
                "How far below the words the underline is - always below letters "
                "like g and y, never through them."
            ),
            self.link_gap,
        )
        self.link_detail = Segmented(
            [
                (LinkDetail.KEY, _tr("Key words")),
                (LinkDetail.MOST, _tr("Most words")),
            ],
            value.link_detail,
        )
        self.link_detail.setObjectName("look.link_detail")
        self.link_detail.changed.connect(lambda v: view.set_link_detail(LinkDetail(v)))
        self._row(
            _tr("Detail"),
            _tr(
                "Key words: content words only. Most words: pronouns, 是, 这个 and "
                "the like too."
            ),
            self.link_detail,
        )
        self.said_in_link_colours = self._switch(
            "said_in_link_colours",
            _tr("Colour linked words in what was said"),
            _tr("Each word a link joins takes its colour, as its underline has."),
            view.set_said_in_link_colours,
        )
        self.translation_in_link_colours = self._switch(
            "translation_in_link_colours",
            _tr("Colour linked words in the translation"),
            _tr(
                "Each word a link joins takes its colour. With both on, and pinyin "
                "in its word link's colour, a word, its pinyin and its translation "
                "all match."
            ),
            view.set_translation_in_link_colours,
        )
        if learning:
            to_learning = label(
                _tr("Which words are pointed out as new is on {learning}.").format(
                    learning=f"<a href='learning'>{_tr('Learning')}</a>"
                ),
                "Faint",
                wrap=True,
            )
            to_learning.setObjectName("look.to_learning")
            to_learning.setContentsMargins(INSET, 0, 0, 0)
            to_learning.linkActivated.connect(lambda _: self.learning_wanted.emit())
            self.add(to_learning)
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        self.word_links.set_value(value.word_links)
        self.link_detail.set_value(value.link_detail)
        self.link_detail.setEnabled(value.word_links is not WordLinks.OFF)
        underlined = value.word_links in (WordLinks.COLOURS, WordLinks.ARROWS)
        self.link_line.set_value(value.link_line)
        self.link_gap.set_value(value.link_gap)
        self.link_line.setEnabled(underlined)  # On hover draws no underline
        self.link_gap.setEnabled(underlined)
        linked = value.word_links is not WordLinks.OFF  # no links: nothing to colour
        self.said_in_link_colours.set_quietly(value.said_in_link_colours)
        self.said_in_link_colours.setEnabled(linked)
        self.translation_in_link_colours.set_quietly(value.translation_in_link_colours)
        self.translation_in_link_colours.setEnabled(linked)


class ReadingLinesPanel(_LookGroup):
    """Pinyin above Chinese (polyglotic-hq 369, decision 0155): a small
    syllable over each character, on whichever row is in Chinese - what
    was said or its translation - and how big it is."""

    def __init__(
        self, view: LookView, notes: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(_tr("Pinyin"), view, notes, parent=parent)
        value = view.value
        self.chinese = self._switch(
            "reading_zh",
            _tr("Pinyin above Chinese"),
            _tr(
                "A small syllable over each Chinese character, in what was said "
                "and in translations into Chinese. It isn't part of the text: "
                "copying and looking up words work as before."
            ),
            lambda on: view.set_reading_line("zh", on),
        )
        self.reading_system = Segmented(
            [
                (ReadingSystem.PINYIN, _tr("Pinyin")),
                (ReadingSystem.ZHUYIN, _tr("Zhuyin")),
            ],
            value.reading_system,
        )
        self.reading_system.setObjectName("look.reading_system")
        self.reading_system.changed.connect(
            lambda v: view.set_reading_system(ReadingSystem(v))
        )
        self._row(
            _tr("Readings above Chinese"),
            _tr(
                "Zhuyin (bopomofo, ㄅㄆㄇㄈ) is how readers in Taiwan learn the sounds: "
                "the same readings as pinyin, in its symbols and tone marks."
            ),
            self.reading_system,
        )
        self.reading_over = Segmented(
            [(False, _tr("Every word")), (True, _tr("Past what you know"))],
            value.reading_past,
        )
        self.reading_over.setObjectName("look.reading_past")
        self.reading_over.changed.connect(lambda v: view.set_reading_past(bool(v)))
        self._row(
            _tr("Pinyin over"),
            _tr(
                "Past what you know: only over the words past your known line "
                "on Learning, the ones word links point out. Less to read as you learn."
            ),
            self.reading_over,
        )
        self.reading_size = Segmented(
            [
                (ReadingSize.SMALL, _tr("Small")),
                (ReadingSize.MEDIUM, _tr("Medium")),
            ],
            value.reading_size,
        )
        self.reading_size.setObjectName("look.reading_size")
        self.reading_size.changed.connect(
            lambda v: view.set_reading_size(ReadingSize(v))
        )
        self._row(
            _tr("Pinyin size"),
            _tr(
                "Beside the characters' own size. Medium reads better in a small "
                "window."
            ),
            self.reading_size,
        )
        self.reading_colour = Segmented(
            [
                (ReadingColour.SAME, _tr("Same as its line")),
                (ReadingColour.LINK, _tr("Its word link's colour")),
                (ReadingColour.CUSTOM, _tr("Custom")),
            ],
            value.reading_colour,
        )
        self.reading_colour.setObjectName("look.reading_colour")
        self.reading_colour.changed.connect(
            lambda v: view.set_reading_colour(ReadingColour(v))
        )
        self._row(
            _tr("Pinyin colour"),
            _tr(
                "Its word link's colour: pinyin takes the colour of its word's "
                "link, where one joins it. Word links can colour the linked "
                "words too."
            ),
            self.reading_colour,
        )
        self.reading_custom = ExactColour(
            COLOUR_CHOICES["reading"],
            value.reading_custom,
            "look.reading_custom",
            _tr("Pinyin colour"),
        )
        self.reading_custom.chosen.connect(view.set_reading_custom)
        self.custom_row = self._row(
            _tr("Custom pinyin colour"),
            _tr("The one colour pinyin is drawn in, over any line."),
            self.reading_custom,
        )
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        on = "zh" in value.reading_lines
        self.chinese.set_quietly(on)
        self.reading_size.set_value(value.reading_size)
        self.reading_size.setEnabled(on)
        self.reading_over.set_value(value.reading_past)
        self.reading_over.setEnabled(on)
        self.reading_system.set_value(value.reading_system)
        self.reading_system.setEnabled(on)
        self.reading_colour.set_value(value.reading_colour)
        self.reading_colour.setEnabled(on)
        self.reading_custom.show_colour(value.reading_custom)
        self.custom_row.setVisible(value.reading_colour is ReadingColour.CUSTOM)
        self.reading_custom.setEnabled(on)


class BehaviourPanel(_LookGroup):
    """How new captions arrive (polyglotic-hq 267, DECISIONS.md #104), when
    captions fade, and - in Settings - what a hidden window does (335)."""

    def __init__(
        self,
        view: LookView,
        notes: bool = False,
        parent: QWidget | None = None,
        hidden_windows: bool = False,
    ) -> None:
        """`hidden_windows`: how long a hidden window listens, and whether
        it's shown when speech starts - Settings > Captions only: they're
        every window's, not a transcript's (its narrow rail shows the rest)."""
        super().__init__(_tr("Behaviour"), view, notes, parent=parent)
        value = view.value
        self.arrival = Segmented(
            [
                (Arrival.STEP_AND_SLIDE.value, _tr("Slide in")),
                (Arrival.STEP.value, _tr("Appear")),
            ],
            value.arrival.value,
        )
        self.arrival.setObjectName("look.arrival")
        self.arrival.changed.connect(view.set_arrival)
        self._row(
            _tr("New captions"),
            pc_or_mac(
                _tr(
                    "Slide in: a new caption rises into place from below - not while "
                    "the PC's animation effects are off. Appear: nothing moves."
                ),
                _tr(
                    "Slide in: a new caption rises into place from below - not while "
                    "the Mac's animation effects are off. Appear: nothing moves."
                ),
            ),
            self.arrival,
        )
        self.fade = Segmented(
            [(v, _tr("Never") if v is None else _seconds(v)) for v in FADE_CHOICES],
            value.fade_after,
        )
        self.fade.setObjectName("look.fade_after")
        self.fade.changed.connect(view.set_fade_after)
        self._row(
            _tr("Fade after quiet"),
            _tr(
                "Captions disappear after this long with nobody talking. Never: "
                "they stay until the next line."
            ),
            self.fade,
        )
        self.pause_hidden: Segmented | None = None
        self.show_on_speech: SwitchButton | None = None
        if hidden_windows:
            self.pause_hidden = Segmented(
                [(v, _minutes(v)) for v in PAUSE_CHOICES], value.pause_hidden_after
            )
            self.pause_hidden.setObjectName("look.pause_hidden_after")
            self.pause_hidden.changed.connect(view.set_pause_hidden_after)
            self._row(
                _tr("Stop listening when hidden"),
                _tr(
                    "A hidden caption window stops listening after this long, so "
                    "nothing more of its app is sent. Showing it starts it again."
                ),
                self.pause_hidden,
            )
            self.show_on_speech = self._switch(
                "show_on_speech",
                _tr("Show a hidden caption window when speech starts"),
                pc_or_mac(
                    _tr(
                        "Off: it stays hidden, and the tray says it's still captioning."
                    ),
                    _tr(
                        "Off: it stays hidden, and the menu bar's icon says it's still "
                        "captioning."
                    ),
                ),
                view.set_show_on_speech,
            )
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        self.arrival.set_value(value.arrival.value)
        self.fade.set_value(value.fade_after)
        if self.pause_hidden is not None:
            self.pause_hidden.set_value(value.pause_hidden_after)
        if self.show_on_speech is not None:
            self.show_on_speech.set_quietly(value.show_on_speech)


class ResetCard(Card):
    """Reset the look to Polyglotic's defaults - the look only: the
    windows' places are Home's "Reset positions" (248's section 2.2)."""

    def __init__(self, view: LookView, parent: QWidget | None = None) -> None:
        super().__init__(_tr("Reset"), parent=parent)
        self.reset = WrapButton(_tr("Reset the look to Polyglotic's defaults"))
        self.reset.setObjectName("look.reset")
        self.reset.setToolTip(
            _tr(
                "Colours, panel, font, word links and fading, as Polyglotic first "
                "had them. The windows' places are Home's Reset positions."
            )
        )
        self.reset.clicked.connect(view.reset)
        reset = QVBoxLayout()
        reset.setContentsMargins(INSET - 1, 0, 0, 0)
        _row(reset, self.reset)
        self.add(reset)
