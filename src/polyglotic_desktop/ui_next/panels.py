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
  When they already speak the window's language (its second language,
  named by the window's: 465), a row per language in use; Names and slang.
  Settings > Captions shows it as **Speech**, without what's learned (the
  Learning page's).
- **Timing:** Caption timing, with the chosen one's sentence, and under
  it only the chosen timing's own settings, in seconds, each with what it
  trades (polyglotic-hq 295): Steady, the longest wait for text; Quick
  preview, when its dim lines come (fixed) and the longest wait; Live
  updates, how often and the longest wait - one longest wait for every timing (polyglotic-hq 277,
  DECISIONS.md #117), and the page says so.
- **Look:** in Settings, a live preview (`caption_preview`); three
  recommended looks (`colour_controls.RecommendedTiles`, polyglotic-hq
  532); the colour presets (`colour_controls.PresetTiles`), each
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

import math
from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.curriculum import SIZES as CURRICULUM_SIZES
from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.lexicon.pack_download import Step
from polyglotic_desktop.core.lexicon.readings import RESPELLED_WORD_LIMIT
from polyglotic_desktop.core.listening.display import (
    READING_LANGUAGES,
    JapaneseReading,
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.hidden import PAUSE_CHOICES
from polyglotic_desktop.core.listening.offers import Use
from polyglotic_desktop.core.listening.offers import offered as timing_offer
from polyglotic_desktop.core.listening.playout import Ahead, ReadingPath
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next import caption_faces, style
from polyglotic_desktop.ui_next.caption_preview import CaptionPreview
from polyglotic_desktop.ui_next.colour_controls import (
    CaptionTextSliders,
    ExactColour,
    PresetTiles,
    RecommendedTiles,
)
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
    in_sentence,
    language_name,
    not_offered_note,
    target_languages,
)
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui_next.spoken_list import SpokenPicker
from polyglotic_desktop.ui_next.timing_popover import (
    menu_recommendation,
    recommended_tag,
    timing_name,
    timing_tip,
)
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY, MarksIn
from polyglotic_desktop.ui_next.views.panels import (
    COLOUR_CHOICES,
    FADE_CHOICES,
    TRANSLATION_AFTER_CHOICES,
    JapaneseReadingsView,
    LanguagesView,
    LookView,
    Shared,
    TimingView,
    WindowLanguageView,
    interval_choices,
    settle_choices,
    wait_choices,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetsView
from polyglotic_desktop.ui_next.views.presets import look_of, preset_of, readable_on
from polyglotic_desktop.ui_next.views.tone import offered
from polyglotic_desktop.ui_next.word_classes import WordClassLegend


def _tr(text: str) -> str:
    return QApplication.translate("Panels", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Panels", text, None, n)


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


def _row(layout: QHBoxLayout | QVBoxLayout, widget: QWidget) -> QHBoxLayout:
    """`widget` at the left of a row of its own (it keeps its own width)."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch(1)
    layout.addLayout(row)
    return row


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
                        "Each caption window picks its own language, or Original "
                        "only, and whether your speech shows in it."
                    ),
                    "Dim",
                    wrap=True,
                )
            )
        else:
            self._this_window(window)
            # after the window's own two rows, the rest is every window's
            self.add(label(_tr("Every caption window").upper(), "SectionLabel"))

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

        # songs mode for music players on Detect, under what it depends on
        # (polyglotic-hq 595, decision 0287): Settings' half of the switch a
        # music player's window offers
        self.lyrics: SwitchButton | None = None
        if speech:
            lyrics = SwitchRow(
                _tr("Lyrics in music players"),
                _tr(
                    "Captions singing in Spotify and other music players whose "
                    "spoken language is Detect. Their sound is sent even without "
                    "speech, a few seconds at a time. Off: only speech is sent."
                ),
                "languages.lyrics",
            )
            self.lyrics = lyrics.switch
            self.lyrics.set_quietly(value.lyrics)
            self.lyrics.toggled.connect(session.set_lyrics)
            self.add(lyrics)

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
                "The characters Mandarin captions are written in, with Detect too. "
                "Lookups, transcripts, copies and Anki use the same. Translations "
                "into Chinese keep the script you translate into."
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
                # named by the window's language, as each caption window
                # names it (polyglotic-hq 465, 449: one name)
                _tr("Lines already in a window's language"),
                _tr(
                    "They aren't translated there unless you pick a second "
                    "language for them."
                ),
                self.second_box,
            )
        )

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
            _tr("Your mic is sent for your captions only while this is on."),
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
        if self.lyrics is not None:
            self.lyrics.set_quietly(value.lyrics)
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
                    _tr(
                        "Add an app on Home first: each caption window's language "
                        "gets a row here."
                    ),
                    "Faint",
                    wrap=True,
                )
            )
        for target in in_use:
            box = Combo()
            box.setObjectName(f"languages.second.{target}")
            box.setAccessibleName(
                in_sentence(
                    _tr(
                        "For windows translating into {language}, translate "
                        "{language} lines into"
                    ),
                    language=language_name(target),
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
                    # the user, 2026-11-17: "Why english? what if you're
                    # targetting chinese translation?" - each row is the
                    # windows translating into its language (465)
                    in_sentence(
                        _tr(
                            "For windows translating into {language}, translate "
                            "{language} lines into:"
                        ),
                        language=language_name(target),
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

RECOMMENDED_TAG_GAP = 6
"""Logical px (2..12): gap between a timing mode's name and its quiet Recommended tag (638)."""
RECOMMENDED_TAG_PAD = (6, 1)
"""Logical px (0..10): horizontal and vertical padding inside the Recommended tag (638)."""
RECOMMENDED_TAG_RADIUS = 6
"""Logical px (2, 3, 6, 8, 9, 10, 12 design scale): corner radius of the Recommended tag in Settings > Timing (638)."""
RECOMMENDED_TAG_BG_ALPHA = 0.14
"""Opacity (0.05..0.30): subtle accent fill behind the Recommended tag (638)."""
RECOMMENDED_TAG_BORDER_ALPHA = 0.34
"""Opacity (0.10..0.50): soft accent border around the Recommended tag (638)."""


def _blend_hex(base: str, tint: str, alpha: float) -> str:
    b, t = QColor(base), QColor(tint)
    r = round(b.red() * (1 - alpha) + t.red() * alpha)
    g = round(b.green() * (1 - alpha) + t.green() * alpha)
    bl = round(b.blue() * (1 - alpha) + t.blue() * alpha)
    return f"#{r:02x}{g:02x}{bl:02x}"


class _TaggedChoiceButton(QPushButton):
    """A segmented timing button that can carry a quiet Recommended tag (638)."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.tag = ""

    def set_tag(self, text: str) -> None:
        if text == self.tag:
            return
        self.tag = text
        self.setProperty("recommended", bool(text))
        self.updateGeometry()
        self.update()

    def _tag_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(style.px(12))
        return font

    def _tag_size(self) -> QSize:
        if not self.tag:
            return QSize(0, 0)
        fm = QFontMetricsF(self._tag_font())
        pad_x, pad_y = RECOMMENDED_TAG_PAD
        return QSize(
            math.ceil(fm.horizontalAdvance(self.tag)) + 2 * pad_x + 2,
            math.ceil(fm.height()) + 2 * pad_y,
        )

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        if not self.tag:
            return base
        tag = self._tag_size()
        return QSize(
            base.width() + RECOMMENDED_TAG_GAP + tag.width(),
            max(base.height(), tag.height() + 4),
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.tag:
            super().paintEvent(event)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        bevel = QStylePainter(self)
        bevel.drawControl(QStyle.ControlElement.CE_PushButton, option)
        bevel.end()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        content = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents, option, self
        )
        tag_size = self._tag_size()
        text_fm = QFontMetricsF(self.font())
        text_w = math.ceil(text_fm.horizontalAdvance(self.text()))
        total_w = text_w + RECOMMENDED_TAG_GAP + tag_size.width()
        left = content.x() + max(0, (content.width() - total_w) // 2)

        theme = style.current()
        text_ink = (
            theme["TEXT"]
            if (self.isChecked() or self.underMouse())
            else theme["TEXT_DIM"]
        )
        painter.setFont(self.font())
        painter.setPen(QColor(text_ink))
        painter.drawText(
            QRectF(left, content.y(), text_w + 2, content.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )

        base_bg = theme["SURFACE_3"] if self.isChecked() else theme["SURFACE_2"]
        bg = QColor(theme["ACCENT"])
        bg.setAlphaF(RECOMMENDED_TAG_BG_ALPHA)
        border = QColor(theme["ACCENT"])
        border.setAlphaF(RECOMMENDED_TAG_BORDER_ALPHA)
        blended = _blend_hex(base_bg, theme["ACCENT"], RECOMMENDED_TAG_BG_ALPHA)
        tag_ink = QColor(readable_on(theme["TEXT_DIM"], blended))

        tag_rect = QRectF(
            left + text_w + RECOMMENDED_TAG_GAP,
            content.y() + (content.height() - tag_size.height()) / 2,
            tag_size.width(),
            tag_size.height(),
        )
        painter.setPen(border)
        painter.setBrush(bg)
        painter.drawRoundedRect(
            tag_rect, RECOMMENDED_TAG_RADIUS, RECOMMENDED_TAG_RADIUS
        )
        painter.setFont(self._tag_font())
        painter.setPen(tag_ink)
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, self.tag)
        painter.end()


class _ModeSegmented(Segmented):
    def _make_button(self, text: str) -> QPushButton:
        return _TaggedChoiceButton(text)


class TimingPanel(Panel):
    """When captions appear, for every window: the caption timing, and
    under it only the chosen timing's own settings, in seconds, each with
    one line saying what it trades (polyglotic-hq 295). With `presets`
    (Settings > Timing): the active preset's
    recommended timing carries a quiet Recommended tag (638)."""

    def __init__(
        self,
        view: TimingView,
        parent: QWidget | None = None,
        languages: LanguagesView | None = None,
        presets: PresetsView | None = None,
    ) -> None:
        super().__init__(_tr("Timing"), parent=parent)
        self.view = view
        self.languages = languages
        self.presets = presets
        self._modes: tuple[CaptionMode, ...] = ()
        self.mode = self._mode_choices(view.value.video)
        self.sentence = label("", "Faint", wrap=True)
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self._mode_row = _row(column, self.mode)
        column.addWidget(self.sentence)
        self.add(Row(_tr("Caption timing"), "", box))
        # Steady's own (526): the newest word, and the words ahead
        self.newest_row = SwitchRow(
            _tr("Show the newest word too"),
            _tr(
                "A quarter of a second sooner, but the newest word is the one "
                "most often corrected. Off: it waits until the next update "
                "confirms it."
            ),
            "timing.newest_word",
        )
        self.newest_row.switch.toggled.connect(view.set_newest_word)
        self.add(self.newest_row)
        self.cards_row = SwitchRow(
            _tr("Card stack"),
            _tr(
                "Each line keeps its place, with its translation under it, and the "
                "lines roll up together as new ones come. Off: live lines below, "
                "earlier lines above."
            ),
            "timing.cards",
        )
        self.cards_row.switch.toggled.connect(view.set_cards)
        self.add(self.cards_row)
        self.zones_row = SwitchRow(
            _tr("Live lines below, earlier above"),
            _tr(
                "The lines being spoken stay at the foot of the caption window; "
                "each caption moves up, with its translation, once it has been "
                "read. Off: one list of captions."
            ),
            "timing.two_zones",
        )
        self.zones_row.switch.toggled.connect(view.set_two_zones)
        self.add(self.zones_row)
        # what is read first (decision 0253): Follow, Both, Acquisition
        self.path = Segmented(
            [
                (ReadingPath.FOLLOW, _tr("Follow")),
                (ReadingPath.BOTH, _tr("Both")),
                (ReadingPath.ACQUISITION, _tr("Acquisition")),
            ],
            view.value.path,
        )
        self.path.setObjectName("timing.path")
        self.path.changed.connect(lambda p: view.set_path(ReadingPath(p)))
        self.path_row = Row(
            _tr("What you read first"),
            _tr(
                "Follow: the translation leads, and what was said is smaller. "
                "Acquisition: what was said first, its translation a moment "
                "after each part. Both: the two together."
            ),
            _left(self.path),
        )
        # These longer explanations share a readable text width at large window sizes.
        for detail in (self.cards_row.detail, self.path_row.detail):
            margins = detail.contentsMargins()
            detail.setMaximumWidth(style.px(380) + margins.left() + margins.right())
        self.add(self.path_row)
        self.after = Segmented(
            [(seconds, f"{seconds:g}s") for seconds in TRANSLATION_AFTER_CHOICES],
            view.value.translation_after,
        )
        self.after.setObjectName("timing.translation_after")
        self.after.changed.connect(lambda s: view.set_translation_after(float(s)))
        self.after_row = Row(
            _tr("Translation after"),
            _tr("How long after a part is shown its translation appears."),
            _left(self.after),
        )
        self.add(self.after_row)
        self.ahead = Segmented(
            [
                (Ahead.NONE, _tr("Off")),
                (Ahead.WAITING, _tr("Faint ahead")),
                (Ahead.ALL, _tr("With the newest word")),
            ],
            view.value.words_ahead,
        )
        self.ahead.setObjectName("timing.words_ahead")
        self.ahead.changed.connect(lambda a: view.set_words_ahead(Ahead(a)))
        self.ahead_row = Row(
            _tr("Words ahead"),
            _tr(
                "The words already heard wait in faint text, and each lights up "
                "at the speaker's pace."
            ),
            _left(self.ahead),
        )
        self.add(self.ahead_row)
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
            _tr("Shorter: text sooner, and more of it changes."),
            live,
            tip=_tr("The first update waits for a second of speech."),
        )
        self.add(self.live)
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
                "How long words on screen can still be corrected as more is heard. "
                "Shorter: fewer words change while you read, and more mistakes "
                "stay - most of all with live updates faster than every second."
            ),
            _left(self.settle),
        )
        self.add(self.settle_row)
        views: list[Shared[Any]] = [view]
        if languages is not None:
            views.append(languages)
        if presets is not None:
            views.append(presets)
        self.bind(*views)
        self.refresh()

    def _mode_choices(self, video: bool) -> _ModeSegmented:
        self._modes = timing_offer(Use.WATCHING).timings if video else OFFERED_MODES
        control = _ModeSegmented([(m, timing_name(m)) for m in self._modes])
        control.setObjectName("timing.mode")
        control.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        control.changed.connect(lambda mode: self.view.set_mode(CaptionMode(mode)))
        return control

    def refresh(self) -> None:
        value = self.view.value
        video = value.video or (
            self.presets is not None and self.presets.value.chosen == "video"
        )
        if video != (CaptionMode.SCROLLING in self._modes):
            old = self.mode
            self.mode = self._mode_choices(video)
            self._mode_row.removeWidget(old)
            self._mode_row.insertWidget(0, self.mode)
            old.hide()
            old.deleteLater()
        shown_mode = (
            timing_offer(Use.WATCHING).nearest(value.mode) if video else value.mode
        )
        self.mode.set_value(shown_mode)
        rec = (
            menu_recommendation(self.presets.value)
            if self.presets is not None
            else None
        )
        for button, mode in zip(self.mode.buttons, self._modes, strict=True):
            assert isinstance(button, _TaggedChoiceButton)
            if rec is not None and rec[0] is mode:
                button.set_tag(recommended_tag())
                button.setToolTip(f"{rec[1]}\n{timing_tip(mode, video=video)}")
                button.setAccessibleName(f"{timing_name(mode)}. {rec[1]}")
                button.setAccessibleDescription(rec[1])
            else:
                button.set_tag("")
                button.setToolTip(timing_tip(mode, video=video))
                button.setAccessibleName("")
                button.setAccessibleDescription("")
        if (mode_layout := self.mode.layout()) is not None:
            mode_layout.invalidate()
        self.mode.updateGeometry()
        sentence = timing_tip(shown_mode, video=video)
        if shown_mode is CaptionMode.WHOLE:
            # the longest wait for text's line (277)
            sentence += " " + _tr(
                "A dim line comes first if the speaker talks on for {seconds} seconds."
            ).format(seconds=f"{value.max_wait:g}")
        self.sentence.setText(sentence)
        self.newest_row.switch.set_quietly(value.newest_word)
        self.newest_row.setVisible(shown_mode is CaptionMode.STEADY)
        self.ahead.set_value(value.words_ahead)
        self.ahead_row.setVisible(shown_mode.paced)
        self.cards_row.switch.set_quietly(value.cards)
        self.cards_row.setVisible(shown_mode.paced)
        self.zones_row.switch.set_quietly(value.two_zones)
        self.zones_row.setVisible(shown_mode.paced and not value.cards)
        self.path.set_value(value.path)
        self.path_row.setVisible(shown_mode.paced)
        self.after.set_value(value.translation_after)
        self.after_row.setVisible(
            shown_mode.paced and value.path is ReadingPath.ACQUISITION
        )
        self.live.setVisible(shown_mode in (CaptionMode.INSTANT, CaptionMode.SCROLLING))
        slower = value.live_every < value.live_interval
        if slower:
            self.live_note.setText(
                _tr(
                    "Longest wait for text, below, is shorter, so text still comes "
                    "every {seconds}."
                ).format(seconds=_seconds(value.live_every))
            )
        self.live_note.setVisible(slower)
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
    """How every caption window looks: the colours, the panel and what's
    shown above and in each caption (248's Settings > Captions > Look);
    each language's font is the Fonts card's (`face_rows`, 482)."""

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
        self.recommended = RecommendedTiles()  # whole looks (polyglotic-hq 532)
        self.recommended.setObjectName("look.recommended")
        self.recommended.chosen.connect(view.set_recommended)
        self._row(
            _tr("Recommended looks"),
            _tr(
                "Colours, caption text, readings and Chinese fonts together, in "
                "one click. Change anything after; your other choices stay."
            ),
            self.recommended,
        )
        self.presets = PresetTiles()
        self.presets.setObjectName("look.presets")
        self.presets.chosen.connect(view.set_preset)
        self._row(
            _tr("Colours"),
            _tr(
                "Matched colours for the text and the panel. Pick a set, then "
                "change any colour."
            ),
            self.presets,
        )
        self.text = CaptionTextSliders()  # the caption text (polyglotic-hq 481)
        self.text.setObjectName("look.caption_text")
        self._thickness_for: tuple[object, ...] = ()
        self.text.show_text(
            value.contrast, value.vibrance, value.thickness, value.edge.value
        )
        self.text.contrast_moved.connect(view.set_contrast)
        self.text.edge_chosen.connect(view.set_edge)
        self.text.vibrance_moved.connect(view.set_vibrance)
        self.text.thickness_moved.connect(view.set_thickness)
        self._row(
            _tr("Caption text"),
            _tr(
                "Contrast, vibrance and thickness, in every caption window; "
                "contrast and vibrance in transcripts too. The middle of each is "
                "the default."
            ),
            self.text,
        )
        self.colours: dict[str, ExactColour] = {}
        for which, title, note in (
            (
                "original",
                _tr("What was said"),
                _tr("The colour of what was said."),
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
                _tr(
                    "The colour of the box behind the text. The slider below sets "
                    "how solid it is."
                ),
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

    def _offer_thickness(self) -> None:
        """Thickness's steps as the captions' faces can draw them
        (`views.tone.offered`; polyglotic-hq 532): from the lightest of
        their own weights - Medium with the app's faces, each cut at one
        weight; only a PC's face chosen for a language brings lighter ones
        (`caption_faces.lightest`) - worked out again when a face changes."""
        value = self.view.value
        chosen = {family for _, family in value.faces if family}
        used = tuple(sorted(chosen | {value.font or ""} - {""}))
        key = (used, caption_faces.generation)
        if key != self._thickness_for:
            self._thickness_for = key
            self.text.offer(offered(caption_faces.lightest(used)))

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
        self._offer_thickness()
        self.text.show_text(
            value.contrast, value.vibrance, value.thickness, value.edge.value
        )
        self.recommended.show_look(look_of(value))
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
    """Word links' style - a caption window's preset menu turns them off
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
                "Words in what was said and its translation that mean the same. On "
                "hover: point at a word. Underline: colours show word class. "
                "Arrows: curves join them. A caption window's preset menu turns "
                "them on and off, under Helpers."
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
            _tr("Words linked"),
            _tr(
                "Key words: content words only. Most words: pronouns, 是, 这个 and "
                "the like too."
            ),
            self.link_detail,
        )
        self.colour_links_by_word_class = self._switch(
            "colour_links_by_word_class",
            _tr("Colour word links by word class"),
            _tr("Use the class of the word that was said for both words in each link."),
            view.set_colour_links_by_word_class,
        )
        self.said_in_link_colours = self._switch(
            "said_in_link_colours",
            _tr("Colour linked words in what was said"),
            _tr("Linked words take their link's colour, like their underline."),
            view.set_said_in_link_colours,
        )
        self.translation_in_link_colours = self._switch(
            "translation_in_link_colours",
            _tr("Colour linked words in the translation"),
            _tr("Linked words take their word class's colour, like their underline."),
            view.set_translation_in_link_colours,
        )
        self.class_legend = WordClassLegend(self) if learning else None
        if self.class_legend is not None:
            self.add(self.class_legend)
            to_learning = label(
                _tr("Which words are marked as new is set on {learning}.").format(
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
        if self.class_legend is not None:
            self.class_legend.set_look(value)
        self.word_links.set_value(value.word_links)
        self.link_detail.set_value(value.link_detail)
        self.link_detail.setEnabled(value.word_links is not WordLinks.OFF)
        underlined = value.word_links in (WordLinks.COLOURS, WordLinks.ARROWS)
        self.link_line.set_value(value.link_line)
        self.link_gap.set_value(value.link_gap)
        self.link_line.setEnabled(underlined)  # On hover draws no underline
        self.link_gap.setEnabled(underlined)
        linked = value.word_links is not WordLinks.OFF  # no links: nothing to colour
        self.colour_links_by_word_class.set_quietly(value.colour_links_by_word_class)
        self.colour_links_by_word_class.setEnabled(linked)
        self.said_in_link_colours.set_quietly(value.said_in_link_colours)
        self.said_in_link_colours.setEnabled(linked)
        self.translation_in_link_colours.set_quietly(value.translation_in_link_colours)
        self.translation_in_link_colours.setEnabled(linked)
        if self.class_legend is not None:
            self.class_legend.setVisible(value.colour_links_by_word_class)


def _set_quiet_word(view: LookView, which: ChosenWords, on: bool) -> None:
    view.set_quiet_word(which, on)


class QuietViewPanel(_LookGroup):
    """The quiet view (polyglotic-hq 477): on or off - the quiet button on a
    caption window does the same - and which words it shows in blue, the
    union of what's ticked, with our curriculum's size."""

    def __init__(
        self,
        view: LookView,
        notes: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(_tr("Quiet view"), view, notes, parent=parent)
        value = view.value
        self.quiet = self._switch(
            "quiet",
            _tr("Quiet view"),
            _tr(
                "Captions in soft grey and gold, a little bigger, with pinyin over "
                "every word and only your chosen words in blue - no underlines or "
                "arrows. Point at a word to see the word it's linked to. Turns "
                "word links off."
            ),
            lambda on: view.set_quiet(on, READING_LANGUAGES),
        )
        self.words: dict[ChosenWords, SwitchButton] = {}
        for which, title, line in (
            (
                ChosenWords.CURRICULUM,
                _tr("Our curriculum"),
                _tr(
                    "A few words just past what you know: the ones the talk is "
                    "about, then the ones you hear most. A word from the talk "
                    "leaves once you know it; the others after three days."
                ),
            ),
            (
                ChosenWords.EDGE,
                _tr("Words at your edge"),
                _tr(
                    "Any word in your learning window, each time it's said - "
                    "never names, numbers or everyday talk."
                ),
            ),
            (
                ChosenWords.LOAD,
                _tr("Learning load"),
                _tr(
                    "The words you're learning now, coloured as in the Lab's "
                    "Learning load."
                ),
            ),
            (
                ChosenWords.SAVED,
                _tr("Saved words"),
                _tr("Words you saved, whatever their category."),
            ),
        ):
            self.words[which] = self._switch(
                f"quiet_{which.value}",
                title,
                line,
                partial(_set_quiet_word, view, which),
            )
        self.curriculum_size = Segmented(
            [(size, str(size)) for size in CURRICULUM_SIZES], value.curriculum_size
        )
        self.curriculum_size.setObjectName("look.curriculum_size")
        self.curriculum_size.changed.connect(lambda v: view.set_curriculum_size(int(v)))
        self._row(
            _tr("Curriculum words"),
            _tr("How many words our curriculum holds at a time."),
            self.curriculum_size,
        )
        self.marks_in = Segmented(
            [
                (MarksIn.LEARNED, _tr("The language I'm learning")),
                (MarksIn.BOTH, _tr("Both lines")),
                (MarksIn.SAID, _tr("What was said")),
            ],
            value.marks_in,
        )
        self.marks_in.setObjectName("look.marks_in")
        self.marks_in.changed.connect(lambda v: view.set_marks_in(MarksIn(v)))
        self._row(
            _tr("Mark my words in"),
            _tr(
                "Which line the quiet view marks your words in: the line in "
                "the language you're learning, every line in a language you "
                "learn, or only what was said."
            ),
            self.marks_in,
        )
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        self.quiet.set_quietly(value.quiet)
        for which, switch in self.words.items():
            switch.set_quietly(which in value.quiet_words)
        self.curriculum_size.set_value(value.curriculum_size)
        self.curriculum_size.setEnabled(ChosenWords.CURRICULUM in value.quiet_words)
        self.marks_in.set_value(value.marks_in)


class ReadingLinesPanel(_LookGroup):
    """Pinyin above Chinese (polyglotic-hq 369, decision 0155), Jyutping
    above Cantonese (polyglotic-hq 450, decision 0160) and furigana above
    Japanese (polyglotic-hq 511): a small reading over the characters, on
    whichever row is in that language - what was said or its translation -
    each with its own switch; over which words, how big and in what
    colour, for all - and Russian's stress marks (молоко́), Korean in
    Revised Romanization and Hindi in Latin letters (511). And
    English respelled as it sounds (KAY-oss, 511):
    its own switch and its own choice of words, past what you know at
    first."""

    def __init__(
        self,
        view: LookView,
        notes: bool = False,
        parent: QWidget | None = None,
        japanese_readings: JapaneseReadingsView | None = None,
    ) -> None:
        #: Settings > Readings: the card of reading lines over captions - pinyin above Chinese, Jyutping above Cantonese, furigana above Japanese, stress marks over Russian, romanization above Korean and Hindi, a respelling above English
        super().__init__(_tr("Readings"), view, notes, parent=parent)
        value = view.value
        self.chinese = self._switch(
            "reading_zh",
            _tr("Pinyin above Chinese"),
            _tr(
                "A small syllable over each Chinese character, in what was said "
                "and in translations into Chinese. Copying and lookups leave it "
                "out."
            ),
            lambda on: view.set_reading_line("zh", on),
        )
        chinese_row = self.chinese.parentWidget()
        assert isinstance(chinese_row, SwitchRow)
        # SwitchRow's side insets otherwise take this note just beyond the
        # readable measure with Segoe UI (about 82 characters on one line).
        # Leave room for its natural word breaks while keeping it below the
        # lab's 80-character limit on every native font.
        chinese_row.detail.setMaximumWidth(round(chinese_row.detail.measure() * 1.2))
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
            _tr("Chinese readings in"),
            _tr(
                "Zhuyin (bopomofo, ㄅㄆㄇㄈ) is how readers in Taiwan learn the sounds: "
                "the same readings as pinyin, in its symbols and tone marks."
            ),
            self.reading_system,
        )
        self.cantonese = self._switch(
            "reading_yue",
            _tr("Jyutping above Cantonese"),
            _tr(
                "A small syllable over each Cantonese character, its tone as a "
                "raised number (hai⁶), from the Cantonese dictionary - once you "
                "learn Cantonese and its dictionary is here."
            ),
            lambda on: view.set_reading_line("yue", on),
        )
        self.japanese = Segmented(
            [
                (JapaneseReading.KANA, _tr("Kana")),
                (JapaneseReading.ROMAJI, _tr("Romaji")),
                (JapaneseReading.BOTH, _tr("Both")),
                (JapaneseReading.OFF, _tr("Off")),
            ],
            value.japanese_reading,
        )
        self.japanese.setObjectName("look.japanese_reading")
        self.japanese.changed.connect(
            lambda v: view.set_japanese_reading(JapaneseReading(v))
        )
        self._row(
            _tr("Japanese readings"),
            _tr(
                "Kana stays above each word's kanji. Romaji uses modified Hepburn; "
                "Both keeps kana above and adds romaji below."
            ),
            self.japanese,
        )
        self.japanese_note = label("", "Faint", wrap=True)
        self.japanese_note.setObjectName("look.reading_ja_availability")
        self.add(self.japanese_note)
        self._japanese_readings = japanese_readings or JapaneseReadingsView()
        self._japanese_readings.subscribe(self._refresh_japanese)
        self._refresh_japanese()
        self.russian = self._switch(
            "reading_ru",
            _tr("Stress marks over Russian"),
            _tr(
                "An accent over the stressed vowel of each Russian word (молоко́), "
                "from the Russian dictionary - none where the dictionary has a word "
                "stressed two ways (ру́ки, руки́): its card shows both. Once you "
                "learn Russian and its dictionary is here."
            ),
            lambda on: view.set_reading_line("ru", on),
        )

        self.korean = self._switch(
            "reading_ko",
            _tr("Romanization above Korean"),
            _tr(
                "Each Korean word in Revised Romanization, the official system, "
                "written as it's said (한국어: hangugeo, 국물: gungmul) - by rule, "
                "no dictionary needed."
            ),
            lambda on: view.set_reading_line("ko", on),
        )
        self.hindi = self._switch(
            "reading_hi",
            _tr("Latin letters above Hindi"),
            _tr(
                "Each Hindi word in Latin letters, as dictionaries write it "
                "(किताब: kitāb), the a's that aren't said left out - by rule, no "
                "dictionary needed."
            ),
            lambda on: view.set_reading_line("hi", on),
        )
        self.reading_over = Segmented(
            [(False, _tr("Every word")), (True, _tr("Past what you know"))],
            value.reading_past,
        )
        self.reading_over.setObjectName("look.reading_past")
        self.reading_over.changed.connect(lambda v: view.set_reading_past(bool(v)))
        self._row(
            _tr("Readings over"),
            _tr(
                "Past what you know: only over the words past your known line on "
                "Learning, the ones word introductions mark. Less to read as you "
                "learn."
            ),
            self.reading_over,
        )
        self.english = self._switch(
            "reading_en",
            _tr("Respelling above English"),
            _trn(
                "How each English word sounds, in plain letters, its stressed part "
                "in capitals (KAY-oss, ri-SEET) - for the %Ln commonest word(s), "
                "in what was said and in translations into English, once you "
                "learn English.",
                RESPELLED_WORD_LIMIT,
            ),
            lambda on: view.set_reading_line("en", on),
        )
        self.respelling_over = Segmented(
            [(False, _tr("Every word")), (True, _tr("Past what you know"))],
            value.respelling_past,
        )
        self.respelling_over.setObjectName("look.respelling_past")
        self.respelling_over.changed.connect(
            lambda v: view.set_respelling_past(bool(v))
        )
        self._row(
            _tr("Respelling over"),
            _tr(
                "Past what you know: only over the English words past your known "
                "line on Learning, so the words you know read plainly."
            ),
            self.respelling_over,
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
            _tr("Reading size"),
            _tr("Relative to the characters. Medium reads better in a small window."),
            self.reading_size,
        )
        self.reading_colour = Segmented(
            [
                (ReadingColour.GREY, _tr("Grey")),  # the default (532)
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
            _tr("Reading colour"),
            _tr(
                "Grey keeps readings behind their text. With Grey or Its word "
                "link's colour, a linked word's reading takes its link's colour. "
                "Word links can colour the linked words too."
            ),
            self.reading_colour,
        )
        self.reading_custom = ExactColour(
            COLOUR_CHOICES["reading"],
            value.reading_custom,
            "look.reading_custom",
            _tr("Reading colour"),
        )
        self.reading_custom.chosen.connect(view.set_reading_custom)
        self.custom_row = self._row(
            _tr("Custom reading colour"),
            _tr("The one colour readings are drawn in, over any line."),
            self.reading_custom,
        )
        self.bind(view)
        self.refresh()

    def _refresh_japanese(self) -> None:
        state = self._japanese_readings.value
        progress = state.progress
        if not state.supported:
            words = _tr("Japanese readings aren't in this version yet.")
        elif progress is not None and progress.step not in (Step.DONE, Step.CANCELLED):
            words = _tr("The Japanese dictionary is downloading: {percent}%.").format(
                percent=round(progress.share * 100)
            )
        elif state.dictionary_here:
            words = ""
        else:
            words = _tr("Shows once the Japanese dictionary is here.")
        self.japanese_note.setText(words)
        self.japanese_note.setVisible(bool(words))

    def refresh(self) -> None:
        value = self.view.value
        chinese = "zh" in value.reading_lines
        self.chinese.set_quietly(chinese)
        self.cantonese.set_quietly("yue" in value.reading_lines)
        # The four-way choice is authoritative.  `reading_lines` is only
        # migration input for old settings files, not a second UI state.
        self.japanese.set_value(value.japanese_reading)
        self.russian.set_quietly("ru" in value.reading_lines)
        self.korean.set_quietly("ko" in value.reading_lines)
        self.hindi.set_quietly("hi" in value.reading_lines)
        english = "en" in value.reading_lines
        self.english.set_quietly(english)
        self.respelling_over.set_value(value.respelling_past)
        self.respelling_over.setEnabled(english)
        japanese = value.japanese_reading is not JapaneseReading.OFF
        # ``ja`` can remain in a migrated file as historical input, but the
        # four-way choice above is the only source of truth for whether a
        # Japanese reading is visible now.
        other_readings = set(value.reading_lines) - {"ja"}
        on = bool(other_readings) or japanese  # the rest are shared
        self.reading_size.set_value(value.reading_size)
        self.reading_size.setEnabled(on)
        self.reading_over.set_value(value.reading_past)
        # the scripts' readings: English's respelling has its own choice
        self.reading_over.setEnabled(
            japanese or any(code != "en" for code in other_readings)
        )
        self.reading_system.set_value(value.reading_system)
        self.reading_system.setEnabled(chinese)
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
            _tr("Fade after silence"),
            _tr(
                "Captions disappear after this long without speech. Never: they "
                "stay until the next one."
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
                _tr("Pause hidden windows after"),
                _tr(
                    "Nothing more of a hidden caption window's app is sent after "
                    "this long. Showing the window carries on."
                ),
                self.pause_hidden,
            )
            self.show_on_speech = self._switch(
                "show_on_speech",
                _tr("Show a hidden caption window when speech starts"),
                pc_mac_or_linux(
                    _tr(
                        "Off: it stays hidden, and the tray says it's still captioning."
                    ),
                    _tr(
                        "Off: it stays hidden, and the menu bar's icon says it's still "
                        "captioning."
                    ),
                    _tr("Off: it stays hidden, and Home says it's still captioning."),
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
                "Colours, panel, font, word links and fading. To move the windows "
                "back, use Reset positions on Home."
            )
        )
        self.reset.clicked.connect(view.reset)
        reset = QVBoxLayout()
        reset.setContentsMargins(INSET - 1, 0, 0, 0)
        _row(reset, self.reset)
        self.add(reset)
