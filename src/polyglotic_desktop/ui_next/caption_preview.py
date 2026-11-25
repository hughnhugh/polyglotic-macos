"""The live preview at the top of Settings > Captions > Look (polyglotic-hq
248's section 2.1; built by 261): two made-up captions over a still, drawn
in the look now - its colours, panel, font, what's shown and word links -
by the caption windows' own layout engine (`caption_layout`), so it looks
as a caption window will. A change anywhere in the look redraws it.

The still is the app's own picture, painted here (a warm room, a bright
window, a blue shadow): never a capture of the screen. The captions are
made-up text, never the learner's - in the characters Mandarin's captions
are shown in, Simplified or Traditional (polyglotic-hq 375's "Show Mandarin
in", 400).
"""

from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QRadialGradient,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.display import DisplayOptions
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, Ink
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.caption_surface import PAD, CaptionSurface
from polyglotic_desktop.ui_next.caption_window import (
    MARK_THICK,
    caption_style,
    high_contrast,
    look_ink,
    marks_panel,
    paint_loading,
)
from polyglotic_desktop.ui_next.languages import spoken_names
from polyglotic_desktop.ui_next.reading_lines import language_of
from polyglotic_desktop.ui_next.views.arrivals import older_alphas
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Labels, Line
from polyglotic_desktop.ui_next.views.lab import older_translation
from polyglotic_desktop.ui_next.views.panels import LanguagesView, LookView

HEIGHT = 230
"""The preview's height at 100 % text size."""
UNFINISHED_HEIGHT = 300
"""The Lab's preview's, with its third caption, still being spoken."""
PANEL_WIDTH = 0.82
"""The caption panel's share of the preview's width (at most `PANEL_MAX`)."""
PANEL_MAX = 640
PREVIEW_TEXT_SIZE = 1.1
"""Preview captions are 110% so every script keeps at least 12 px of ink."""
SAMPLE = SourceId("preview")
ZH, EN = Language("zh"), Language("en")
WHEN = datetime(2026, 11, 9, tzinfo=UTC)
"""The made-up captions' time: the same every run."""


def _tr(text: str) -> str:
    return QApplication.translate("CaptionPreview", text)


def _clause(
    original: str, translation: str, pairs: tuple[tuple[str, str], ...]
) -> Clause:
    links = []
    for said, meant in pairs:
        a, c = original.index(said), translation.index(meant)
        links.append(WordLink((a, a + len(said)), (c, c + len(meant)), True, 0.9))
    return Clause(original, {EN: translation}, {EN: tuple(links)})


TRADITIONAL = str.maketrans("这个数错们毕项周来", "這個數錯們畢項週來")
"""The made-up captions in Traditional, as the app's converter writes them
(`core.lexicon.traditional`, Taiwan's forms: 下周 is 下週) - a test holds
the two to the same text. Their few characters, not the converter's 1 MB
table read for a picture (polyglotic-hq 400)."""

_Pairs = tuple[tuple[str, str], ...]
_SAMPLES: tuple[tuple[str, str, _Pairs], ...] = (
    (
        "这个季度的数字看起来不错。",
        "The figures for this quarter look good.",
        (("季度", "quarter"), ("数字", "figures"), ("不错", "good")),
    ),
    (
        "我们毕竟要完成这个项目。",
        "After all, we have to finish this project.",
        (("毕竟", "After all"), ("完成", "finish"), ("项目", "project")),
    ),
)
_UNFINISHED: tuple[str, str, _Pairs] = (
    "那我们下周再",
    "Then next week we'll",
    (("下周", "next week"),),
)


def _written(text: str, traditional: bool) -> str:
    return text.translate(TRADITIONAL) if traditional else text


def _sample(said: str, meant: str, pairs: _Pairs, traditional: bool) -> Clause:
    return _clause(
        _written(said, traditional),
        meant,
        tuple((_written(word, traditional), its) for word, its in pairs),
    )


def sample_clauses(traditional: bool = False) -> tuple[Clause, ...]:
    """Two made-up captions, Chinese with English, their words linked - in
    Traditional characters if `traditional`."""
    return tuple(_sample(*sample, traditional) for sample in _SAMPLES)


def sample_unfinished(traditional: bool = False) -> Clause:
    """A made-up caption still being spoken, for the Lab's preview (284)."""
    return _sample(*_UNFINISHED, traditional)


SAMPLE_CLAUSES = sample_clauses()
"""Two made-up captions, Chinese with English, their words linked."""
SAMPLE_UNFINISHED = sample_unfinished()
"""A made-up caption still being spoken, for the Lab's preview (284)."""
_PINYIN = {
    "这个季度的数字看起来不错。": "这个 zhè ge|季度 jì dù|的 de|数字 shù zì|看起来 kàn qǐ lái|不错 bù cuò",
    "我们毕竟要完成这个项目。": "我们 wǒ men|毕竟 bì jìng|要 yào|完成 wán chéng|这个 zhè ge|项目 xiàng mù",
    "那我们下周再": "那 nà|我们 wǒ men|下周 xià zhōu|再 zài",
}  # fmt: skip
SAMPLE_PINYIN = _PINYIN | {
    _written(text, True): _written(words, True) for text, words in _PINYIN.items()
}
"""The made-up captions' pinyin, word by word, in either script: the
preview shows a reading line without a dictionary (369)."""


def sample_readings(text: str, language: str | None) -> list[Reading]:
    """The made-up captions' reading lines (`SAMPLE_PINYIN`); a live
    caption's text may end in its trail."""
    words = next((w for t, w in SAMPLE_PINYIN.items() if text.startswith(t)), None)
    if words is None or language_of(language) != "zh":
        return []
    found, at = [], 0
    for word in words.split("|"):
        written, *syllables = word.split()
        at = text.index(written, at)
        for n, syllable in enumerate(syllables):
            found.append(Reading(at + n, at + n + 1, syllable, n == len(syllables) - 1))
        at += len(written)
    return found


class PreviewSurface(CaptionSurface):
    """The preview's captions: the newest at full ink, the one before it a
    step back, as a caption window draws them (`views.arrivals`; the Lab's
    Older captions, 284)."""

    older: Ink | None = None

    def ink_for(self, line: Line) -> Ink:
        newest = next(
            (each.key for each in reversed(self.view.lines) if not each.provisional),
            None,
        )
        if self.older is not None and newest is not None and line.key < newest:
            return self.older
        return self.ink


class CaptionPreview(QWidget):
    """Two captions over a still, in `view`'s look, redrawn as it changes."""

    def __init__(
        self,
        view: LookView,
        parent: QWidget | None = None,
        unfinished: bool = False,
        languages: LanguagesView | None = None,
    ) -> None:
        """`unfinished`: a third caption, still being spoken, after the two
        (the Lab's preview: how such text looks, 284); `languages`: the
        session's, whose "Show Mandarin in" the made-up captions follow
        (polyglotic-hq 400) - without it, Simplified."""
        super().__init__(parent)
        self.setObjectName("look.preview")
        self.setAccessibleName(_tr("Preview of the caption windows"))
        self.view = view
        self.unfinished = unfinished
        self.lines = CaptionLines(
            [SAMPLE],
            EN,
            keep=len(SAMPLE_CLAUSES) + 1,
            text_size=PREVIEW_TEXT_SIZE,
            clock=lambda: WHEN,
        )
        self.languages = languages
        self.traditional = False
        """The made-up captions are in Traditional characters."""
        self._write(traditional=False)
        self.marks = CaptionMarks(None)
        self.surface = PreviewSurface(self.lines, parent=self, marks=self.marks)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._look: CaptionLook | None = None
        stop = view.subscribe(self.follow)
        self.destroyed.connect(lambda *_: stop())
        if languages is not None:
            stop_script = languages.subscribe(self.follow_script)
            self.destroyed.connect(lambda *_: stop_script())
            self.follow_script()
        self.follow()

    def _write(self, traditional: bool) -> None:
        """The made-up captions, in Traditional characters or Simplified -
        the same captions again, so they replace those shown."""
        self.traditional = traditional
        for n, clause in enumerate(sample_clauses(traditional)):
            self.lines.apply(
                CaptionUpdate(
                    CaptionId(f"preview-{n}"),
                    SAMPLE,
                    CaptionKind.FINISHED,
                    (clause,),
                    ZH,
                    (ZH,),
                )
            )
        if self.unfinished:
            self.lines.apply(
                CaptionUpdate(
                    CaptionId("preview-unfinished"),
                    SAMPLE,
                    CaptionKind.LIVE,
                    (sample_unfinished(traditional),),
                    ZH,
                    (ZH,),
                )
            )

    def follow_script(self) -> None:
        """ "Show Mandarin in" changed: the captions in its characters."""
        assert self.languages is not None
        traditional = self.languages.value.traditional
        if traditional != self.traditional:
            self._write(traditional)
            self._place()
            self.update()

    def _tall(self) -> int:
        return style.px(UNFINISHED_HEIGHT if self.unfinished else HEIGHT)

    def sizeHint(self) -> QSize:
        return QSize(style.px(PANEL_MAX), self._tall())

    def minimumSizeHint(self) -> QSize:
        return QSize(style.px(240), self._tall())

    def follow(self) -> None:
        """The look now: drawn again - laid out again only if its font or
        word links' room changed."""
        look = self.view.value
        if look == self._look:
            return
        self._look = look
        surface = self.surface
        wanted = caption_style(look)
        if wanted != surface.engine.style:
            surface.engine = CaptionLayout(
                wanted, lines_kept=self.lines.keep, readings=sample_readings
            )
        surface.ink = look_ink(
            Ink(QColor(look.original), QColor(look.translation)), look
        )
        older, translation = older_alphas(
            high_contrast(),
            following=True,
            older=(look.lab.older, older_translation(look.lab.older)),
        )
        surface.older = replace(
            surface.ink, alpha=older, translation_alpha=translation / older
        )
        # its links in the colours its look's window takes (554)
        self.marks.set_look(look.word_links, look.introductions, marks_panel(look))
        self.lines.set_options(
            DisplayOptions(
                look.show_original,
                look.word_links,
                look.link_detail,
                preview=look.preview and self.unfinished,
            )
        )
        self.lines.set_labels(
            Labels(
                {SAMPLE: SourceLabel(_tr("Video"), "#4dd0e1")},
                show_source=look.show_source,
                show_language=look.show_language,
                spoken=lambda heard: spoken_names(str(lang) for lang in heard),
            )
        )
        self._place()
        self.update()

    def panel_rect(self) -> QRectF:
        """Where the caption panel is: centred near the foot, as tall as
        its captions."""
        width = min(self.width() * PANEL_WIDTH, style.px(PANEL_MAX))
        inner = max(1, int(width) - 2 * PAD)
        lines = self.lines.lines
        size = self.lines.text_size
        tall = sum(self.surface.engine.laid(line, inner, size).height for line in lines)
        gap = self.surface.engine.style.caption_gap
        tall += gap * size * max(0, len(lines) - 1) + 2 * PAD
        tall = min(tall, self.height() - style.px(16))
        foot = self.height() - style.px(14)
        return QRectF((self.width() - width) / 2, foot - tall, width, tall)

    def _place(self) -> None:
        self.surface.setGeometry(self.panel_rect().toAlignedRect())
        self.surface.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._place()
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        whole = QRectF(self.rect())
        self._still(painter, whole)
        look = self.view.value
        panel = QColor(look.background)
        panel.setAlphaF(look.opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(panel)
        rect = self.panel_rect()
        painter.drawRoundedRect(rect, 10, 10)
        if self.unfinished:  # the Lab's: the loading sign, standing still
            scale = min(self.lines.text_size, 1.6)
            lines = self.lines.lines
            paint_loading(
                painter,
                look.lab.loading,
                QPointF(
                    rect.left() + PAD + 3,
                    rect.bottom() - PAD / 2 - MARK_THICK * scale / 2 - 1,
                ),
                scale,
                QColor(look.original),
                None,
                newest_live=bool(lines) and lines[-1].live,
            )
        painter.end()

    @staticmethod
    def _still(painter: QPainter, area: QRectF) -> None:
        """The app's own still: a warm room lit by a window, a blue shadow."""
        painter.save()
        painter.setClipRect(area)
        room = QLinearGradient(area.topLeft(), area.bottomRight())
        room.setColorAt(0.0, QColor("#7a5a32"))
        room.setColorAt(0.45, QColor("#8c7046"))
        room.setColorAt(1.0, QColor("#1f3b5c"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(room)
        painter.drawRoundedRect(area, 10, 10)
        light = QRadialGradient(
            QPointF(
                area.left() + area.width() * 0.74, area.top() + area.height() * 0.32
            ),
            area.height() * 0.7,
        )
        light.setColorAt(0.0, QColor(246, 236, 214, 235))
        light.setColorAt(0.35, QColor(240, 226, 196, 150))
        light.setColorAt(1.0, QColor(240, 226, 196, 0))
        painter.setBrush(light)
        painter.drawRect(area)
        shadow = QRadialGradient(
            QPointF(area.left() + area.width() * 0.18, area.bottom()),
            area.height() * 0.8,
        )
        shadow.setColorAt(0.0, QColor(16, 30, 52, 170))
        shadow.setColorAt(1.0, QColor(16, 30, 52, 0))
        painter.setBrush(shadow)
        painter.drawRect(area)
        painter.restore()
