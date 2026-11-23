"""W3, the lookup card's states (polyglotic-hq project 109's structure,
section 6; project 113), on a caption window over the made-up
conversation, with the sample dictionary (CI has no dictionary files):
hover, pinned, a part (after a click on it), not in the dictionary as a
whole, Save to open, after Add to deck, the learner's dictionary damaged
(polyglotic-hq 199), the speaker saying the word and no voice for it (286)
- and two of W1's marks: a word's links on hover, and
a word both linked and in the deck. And other learners' cards (215): an
English learner's (ECDICT's meanings are Chinese; and in English,
polyglotic-hq 447) and a Japanese word's
(a basic dictionary, Sudachi's word split), each pinned, checked by the
font checks (`japanese_font`, `chinese_font`) like every state.

Timed: the lookup after the hover delay (30 ms budget), pinned (30 ms),
a part and Back (a click: 30 ms), and Learning's actions (Add to deck,
Known - shown within 30 ms, the captions holding the word repainted).
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from functools import partial

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QRegion
from PySide6.QtWidgets import QWidget
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import FakeDictionaryFile, chinese_sample, english_sample

from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.display import (
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.listening.playout import PlayoutRules, ReadingPath
from polyglotic_desktop.core.listening.selection import Place, Selection
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordStatus
from polyglotic_desktop.main import LearningOffer
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ports.dictionary import DictionaryProblem, EntryRecord
from polyglotic_desktop.ports.speaker import Ended, Quality, Sounding, Spoken, Voice
from polyglotic_desktop.ports.word_classes import WordClass
from polyglotic_desktop.ui import recorded_captions as recorded
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, EN, MIC, ZH, clause
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.caption_selection import held_rects
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, Marked
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, TextEdge
from polyglotic_desktop.ui_next.views.presets import BY_KEY, LARGE_TEXT
from polyglotic_desktop.ui_next.views.speech import BetterVoice
from polyglotic_desktop.ui_next.word_speech import WordSpeech
from tools.ui_lab.caption_window import LABELS, _areas
from tools.ui_lab.lab import SCENE, Lab, State
from tools.ui_lab.new_parts import finished

CAPTIONS = 150
"""A caption window keeps 150: the lookup's lab fills it."""


def sample_tools(problem: DictionaryProblem | None = None) -> LearningTools:
    """The learning tools on the sample dictionary, learning kept in memory;
    with `problem`, the dictionary file said to be out (polyglotic-hq 199)."""
    dictionary = ChineseDictionary(chinese_sample())

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    dictionary.prepare()  # the word split's data read, as at the app's start
    vocabulary = Vocabulary(MemoryLearningStore(), facts, "hsk-2025", Clock())
    return LearningTools(vocabulary, dictionary, dictionary_problem=lambda: problem)


def windows(
    lab: Lab, look: CaptionLook | None = None, problem: DictionaryProblem | None = None
) -> CaptionWindows:
    """One caption window over the conversation, with the lookup card."""
    tools = sample_tools(problem)
    found = CaptionWindows(None, MIC, _areas, learner=tools)
    tools.changed.connect(found.learning_changed)
    found.set_labels(LABELS, "You")
    if look is not None:
        found.set_look(look)
    found.set_captioned([("lab", APP)])
    for update in finished(CAPTIONS):
        found.apply(update)
    shown = found.windows["lab"]
    shown.always_shown = True
    shown.setGeometry(480, 600, 960, 360)  # room for three captions
    lab.pump()
    shown.canvas.repaint()
    lab.closing.append(found.close)
    return found


def window_of(found: CaptionWindows) -> CaptionWindow:
    return found.windows["lab"]


def marked(shown: CaptionWindow, text: str, newest: int = 0) -> Marked:
    """`text` in the newest lines in view (skipping `newest` finds)."""
    for line, laid, rect in reversed(shown.canvas.placed):
        for row in laid.rows:
            if rect.top() + row.top < shown.canvas.clear_top:
                continue  # not in view
            at = row.row.text.find(text)
            if at >= 0:
                if newest == 0:
                    return Marked(line.key, row.index, at, at + len(text))
                newest -= 1
    raise LookupError("the lab's word isn't drawn")


class _Together(QWidget):
    """A caption window and the lookup card where they are on the screen,
    over the stand-in video: the photograph."""

    def __init__(self, shown: list[QWidget]) -> None:
        super().__init__()
        self.shown = [w for w in shown if w.isVisible()]
        area = QRect()
        for each in self.shown:
            area = area.united(each.geometry())
        self.area = area.adjusted(-12, -12, 12, 12)
        self.resize(self.area.size())

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        """Each window and where it's drawn (`checks.place_in`)."""
        return [
            (each, each.geometry().topLeft() - self.area.topLeft(), 1.0)
            for each in self.shown
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(SCENE))
        for each, at, _scale in self.places():
            each.render(painter, at, QRegion(), QWidget.RenderFlag.DrawChildren)
        painter.end()


def _photo(found: CaptionWindows) -> QWidget:
    card = found.card
    assert card is not None
    return _Together([window_of(found), card])


def _hovered(found: CaptionWindows, text: str) -> None:
    shown = window_of(found)
    word = marked(shown, text)
    shown.canvas.hovered = word
    shown.canvas.update()
    request = shown.word_at(word)
    assert request is not None and found.card is not None
    found.card.hover(request)
    found.card._show_pending()  # the hover delay, gone by


def _pinned(found: CaptionWindows, text: str) -> None:
    shown = window_of(found)
    request = shown.word_at(marked(shown, text))
    assert request is not None and found.card is not None
    found.card.pin(request)


def _alternately(*texts: str) -> Iterator[str]:
    while True:
        yield from texts


# -- the states --------------------------------------------------------------------------


def hover(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    assert card is not None
    words = _alternately("电脑", "游戏", "这个")
    for _ in range(12):
        card.close_card()
        lab.time(
            "lookup_hover",
            partial(_hovered, found, next(words)),
            budget=budgets.LOOKUP_HOVER,
        )
    card.close_card()
    _hovered(found, "电脑")
    lab.pump()
    return _photo(found)


def pinned(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    assert card is not None
    words = _alternately("电脑", "游戏", "这个")
    for _ in range(12):
        card.close_card()
        lab.time(
            "lookup_pinned",
            partial(_pinned, found, next(words)),
            budget=budgets.LOOKUP_PINNED,
        )
    card.close_card()
    _pinned(found, "电脑")
    lab.pump()
    return _photo(found)


def part(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    assert card is not None
    _pinned(found, "电脑")
    for _ in range(6):
        lab.time("lookup_part", partial(card.do, "part:0"), budget=budgets.CLICK)
        lab.time("lookup_back", partial(card.do, "back"), budget=budgets.CLICK)
    card.do("part:1")
    lab.pump()
    return _photo(found)


def not_found(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    shown = window_of(found)
    assert card is not None
    request = shown.word_at(marked(shown, "画面"))  # a phrase dragged across
    assert request is not None
    lab.time("lookup_pinned", partial(card.pin, request), budget=budgets.LOOKUP_PINNED)
    return _photo(found)


def learning_action(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    assert card is not None
    _pinned(found, "电脑")
    for what in ("deck", "known") * 6:
        lab.time("learning_action", partial(card.do, what), budget=budgets.CLICK)
    tools = found.learner
    assert tools is not None
    status = tools.vocabulary.status(tools.facts(tools.lookup("电脑")[0])).status
    if status is not WordStatus.LEARNING:
        card.do("deck")
    lab.pump()
    return _photo(found)


def save_to(lab: Lab) -> QWidget:
    found = windows(lab)
    card = found.card
    assert card is not None
    _pinned(found, "游戏")
    lab.time("save_to", partial(card.do, "save"), budget=budgets.CLICK)
    lab.time("save_to", partial(card.do, "save:saved"), budget=budgets.CLICK)
    card.do("save")  # open again: the categories, Saved ticked
    lab.pump()
    return _photo(found)


def links_on_hover(lab: Lab) -> QWidget:
    found = windows(lab, CaptionLook(word_links=WordLinks.HOVER))
    _hovered(found, "电脑")
    lab.pump()
    return _photo(found)


def linked_and_in_deck(lab: Lab) -> QWidget:
    found = windows(lab, CaptionLook(word_links=WordLinks.COLOURS))
    tools = found.learner
    assert tools is not None
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    lab.pump()
    shown = window_of(found)
    shown.canvas.repaint()
    return shown


def linked_arrows(lab: Lab) -> QWidget:
    """Word links as Arrows: each linked word's underline, and a curve down
    to its counterpart (F7, 249)."""
    found = windows(lab, CaptionLook(word_links=WordLinks.ARROWS))
    lab.pump()
    shown = window_of(found)
    shown.canvas.repaint()
    return shown


MATCHED = CaptionLook(
    word_links=WordLinks.COLOURS,
    reading_lines=("zh",),
    reading_size=ReadingSize.MEDIUM,  # Small's 11 px is under the lab's 12 (369)
    reading_colour=ReadingColour.LINK,
    said_in_link_colours=True,
    translation_in_link_colours=True,
)
"""Pinyin in its word link's colour, and the linked words too: a word, its
pinyin and its translation all match (polyglotic-hq 395)."""


def _drawn(lab: Lab, look: CaptionLook) -> QWidget:
    found = windows(lab, look)
    lab.pump()
    shown = window_of(found)
    shown.canvas.repaint()
    return shown


def pinyin_in_link_colours(lab: Lab) -> QWidget:
    """395: pinyin, the word and its translation in the link's colour."""
    return _drawn(lab, MATCHED)


def translation_in_link_colours(lab: Lab) -> QWidget:
    """431: each side on its own (the user, 2026-11-17: "toggleable
    separately") - only the translation's linked words in their link's
    colour, what was said and its pinyin in their own; readable on
    Classic's panel at its own 72 %."""
    look = replace(
        MATCHED,
        said_in_link_colours=False,
        reading_colour=ReadingColour.SAME,
    )
    return _drawn(lab, look)


def pinyin_in_link_colours_paper(lab: Lab) -> QWidget:
    """The same on Paper's light panel: the link colours darkened to read."""
    paper = BY_KEY["paper"]
    look = replace(
        MATCHED,
        original=paper.original,
        translation=paper.translation,
        background=paper.background,
        opacity=paper.opacity,
    )
    return _drawn(lab, look)


QUIET = CaptionLook(
    quiet=True,
    reading_lines=("zh",),
    reading_size=ReadingSize.MEDIUM,  # Small's under the lab's 12 px, as above
    quiet_words=frozenset({ChosenWords.SAVED}),
)
"""The quiet view (polyglotic-hq 477), saved words chosen: grey and gold,
italic, a size step bigger, pinyin over every word, the saved words in
blue."""


def _quiet(lab: Lab, look: CaptionLook) -> CaptionWindows:
    found = windows(lab, look)
    tools = found.learner
    assert tools is not None
    for word in ("电脑", "游戏"):
        entry = tools.lookup(word)[0].entry_id
        tools.vocabulary.save(entry, word, word, "", word, "saved", LookupContext(word))
    lab.pump()
    window_of(found).canvas.repaint()
    return found


def quiet(lab: Lab) -> QWidget:
    """477: the quiet view, two saved words in blue, their pinyin too."""
    return window_of(_quiet(lab, QUIET))


def quiet_hover(lab: Lab) -> QWidget:
    """477: a word pointed at in the quiet view - it and its partner lit
    quietly, no lines, no link colours - with its lookup."""
    found = _quiet(lab, QUIET)
    _hovered(found, "游戏")  # a size step bigger: fewer captions in view
    lab.pump()
    return _photo(found)


def quiet_paper(lab: Lab) -> QWidget:
    """477: the quiet view on Paper's light panel: the blue darkened to read."""
    paper = BY_KEY["paper"]
    look = replace(
        QUIET,
        original=paper.original,
        translation=paper.translation,
        background=paper.background,
        opacity=paper.opacity,
    )
    return window_of(_quiet(lab, look))


TONE_ENDS = {
    "soft": {"contrast": -100},
    "crisp": {"contrast": 100},
    "muted": {"vibrance": -100},
    "vivid": {"vibrance": 100},
    "light": {"thickness": 300},
    "bold": {"thickness": 700},
    "shadow": {"edge": TextEdge.SHADOW},
    "outline": {"edge": TextEdge.OUTLINE},
}
"""Each end of the caption text's controls (polyglotic-hq 481): contrast,
vibrance, thickness - and Visibility's edges."""


def _on_paper(look: CaptionLook) -> CaptionLook:
    paper = BY_KEY["paper"]
    return replace(
        look,
        original=paper.original,
        translation=paper.translation,
        background=paper.background,
        opacity=paper.opacity,
    )


def _toned(base: CaptionLook, end: str, paper: bool) -> Callable[[Lab], QWidget]:
    """481: `base` (word links in colour, or the quiet view) at one end of a
    slider, on Classic's dark panel or Paper's light one - two saved words
    in it, in their category's colour (the quiet view's blue)."""
    look = replace(base, **TONE_ENDS[end])  # type: ignore[arg-type]
    if paper:
        look = _on_paper(look)

    def run(lab: Lab) -> QWidget:
        shown = window_of(_quiet(lab, look))
        if look.contrast < 0:  # the learner chose text under WCAG's 4.5:1
            shown.setProperty("contrast_floor", LARGE_TEXT)
        return shown

    return run


TONE_STATES = [
    (f"w1_{view}_{end}{'_paper' if paper else ''}", _toned(base, end, paper), True)
    for view, base in (("links", MATCHED), ("quiet", QUIET))
    for paper in (False, True)
    for end in TONE_ENDS
    if not (paper and end in ("light", "bold"))
]
"""Every slider's ends, word links and the quiet view, dark and light - a
weight on the dark panel only: the panel doesn't change what it draws."""


def pinyin_custom(lab: Lab) -> QWidget:
    """395: pinyin in one colour picked (the default custom one)."""
    return _drawn(
        lab,
        CaptionLook(
            reading_lines=("zh",),
            reading_size=ReadingSize.MEDIUM,
            reading_colour=ReadingColour.CUSTOM,
        ),
    )


def zhuyin(lab: Lab) -> QWidget:
    """395: zhuyin (bopomofo) above Chinese in place of pinyin."""
    return _drawn(
        lab,
        CaptionLook(
            reading_lines=("zh",),
            reading_size=ReadingSize.MEDIUM,
            reading_system=ReadingSystem.ZHUYIN,
        ),
    )


def dictionary_out(lab: Lab) -> QWidget:
    """The learner's dictionary damaged: a pinned card says so, and how to
    fix it (polyglotic-hq 199)."""
    found = windows(lab, problem=DictionaryProblem.DAMAGED)
    _pinned(found, "电脑")
    lab.pump()
    return _photo(found)


class _Speaker:
    """The `Speaker` port, made up (polyglotic-hq 286): `voices` it has, and
    nothing is ever played."""

    def __init__(self, voices: tuple[Voice, ...]) -> None:
        self.installed = voices

    def voices(self) -> tuple[Voice, ...]:
        return self.installed

    def say(
        self, text: str, voice: Voice, rate: float, sounding: Sounding, ended: Ended
    ) -> None:
        pass

    def read(
        self,
        chunks: Sequence[str],
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
        spoken: Spoken,
    ) -> None:
        """The `Reader` port too (495): the first word said, at once."""
        if chunks:
            spoken(0, 0, 2)

    def stop(self) -> None:
        pass


def _speaking(
    lab: Lab, voices: tuple[Voice, ...], better: BetterVoice | None = None
) -> CaptionWindows:
    found = windows(lab)
    assert found.card is not None
    speech = WordSpeech(
        _Speaker(voices), open_url=lambda url: None, parent=found.card, better=better
    )
    found.card.use_speech(speech)
    _pinned(found, "电脑")
    return found


def say_it(lab: Lab) -> QWidget:
    """A pinned word's speaker, while it says the word (286): the speaker
    beside Close, with its two waves."""
    found = _speaking(lab, (Voice("zh", "Microsoft Huihui", "zh-CN"),))
    card = found.card
    assert card is not None
    for _ in range(6):  # a click says it, the next stops it
        lab.time("say_it", partial(card.do, "say"), budget=budgets.CLICK)
    card.do("say")
    lab.pump()
    return _photo(found)


def say_it_long(lab: Lab) -> QWidget:
    """The card on a long clause looked up, with Say it and Close: the
    lab's two newest Chinese lines in view as one clause (18 characters,
    as long as real captions' clauses run: 522's picture's had 19). Its
    headword wraps at its own size and its pinyin under it, clear of the
    buttons (polyglotic-hq 522, 533)."""
    found = windows(lab)
    assert found.card is not None
    found.card.use_speech(
        WordSpeech(
            _Speaker((Voice("zh", "Microsoft Huihui", "zh-CN"),)),
            open_url=lambda url: None,
            parent=found.card,
        )
    )
    shown = window_of(found)
    rows = [
        (line.key, row)
        for line, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is RowKind.ORIGINAL and row.row.language == ZH
    ]
    (_, first), (key, last) = rows[-2:]
    text = last.row.text.rstrip("。，！？")
    request = shown.word_at(Marked(key, last.index, 0, len(text)))
    assert request is not None
    clause = first.row.text.rstrip("。，！？") + "，" + text
    found.card.pin(replace(request, word=clause))
    lab.pump()
    return _photo(found)


def no_voice(lab: Lab) -> QWidget:
    """No Chinese voice on this PC (an English-only Windows), after a click
    on the crossed-out speaker: how Windows adds one, and its button (286)."""
    found = _speaking(lab, (Voice("en", "Microsoft David", "en-US"),))
    card = found.card
    assert card is not None
    card.do("say")
    lab.pump()
    return _photo(found)


TINGTING = Voice("compact.zh-CN.Tingting", "Tingting", "zh-CN", Quality.BASIC)
"""A Mac's compact Chinese voice (polyglotic-hq 518)."""


def _better() -> BetterVoice:
    return BetterVoice(lambda: (), lambda _language: None)


def better_voice(lab: Lab) -> QWidget:
    """A pinned word said in a Mac's basic Chinese voice: how to add a
    better one, "Don't show again" and Dismiss (518)."""
    found = _speaking(lab, (TINGTING,), _better())
    card = found.card
    assert card is not None
    card.do("say")
    lab.pump()
    return _photo(found)


# -- other learners' cards (polyglotic-hq 215) ---------------------------------------

JA = Language("ja")
ENGLISH_CAPTIONS = (
    clause(
        "That was an awkward thing to say.",
        "那句话说得很尴尬。",
        (("awkward", "尴尬"),),
        into=ZH,
    ),
    clause(
        "I left early to keep running.",
        "我早早离开，继续跑步。",
        (("left", "离开"),),
        into=ZH,
    ),
)
JAPANESE_CAPTIONS = (
    clause(
        "毎日日本語を勉強しています。",
        "I study Japanese every day.",
        (("勉強", "study"),),
    ),
    clause("日本の映画が好きです。", "I like Japanese films.", (("映画", "films"),)),
)
JAPANESE_SAMPLE = FakeDictionaryFile(
    [
        EntryRecord("jmdict:1", "勉強", "", "べんきょう", ("study", "diligence"), 400),
        EntryRecord("jmdict:2", "日本", "", "にほん", ("Japan",), 120),
        EntryRecord("jmdict:3", "映画", "", "えいが", ("movie", "film"), 800),
        EntryRecord("jmdict:4", "毎日", "", "まいにち", ("every day",), 300),
    ],
    {
        "勉強": ["jmdict:1"],
        "日本": ["jmdict:2"],
        "映画": ["jmdict:3"],
        "毎日": ["jmdict:4"],
    },
)
"""A few JMdict-style entries: the lab has no dictionary packs (CI has none)."""
RU = Language("ru")
RUSSIAN_CAPTIONS = (
    clause("Дай мне руку, пожалуйста.", "请把手给我。", (("руку", "手"),), into=ZH),
    clause("У меня болят руки.", "我的手疼。", (("руки", "手"),), into=ZH),
)
RUSSIAN_SAMPLE = FakeDictionaryFile(
    [
        EntryRecord("wiktru:1", "рука", "", "рука́", ("(noun) hand", "(noun) arm"), 300),
        EntryRecord("wiktru:2", "дать", "", "да́ть", ("(verb) to give",), 90),
    ],
    {"рука": ["wiktru:1"], "дать": ["wiktru:2"]},
    lemmas={"руку": "рука", "руки": "рука", "дай": "дать"},
    form_readings={"руку": "ру́ку", "руки": "руки́, ру́ки"},
)
"""Wiktionary-style Russian entries: stress marked on the headword and on
each inflected form (polyglotic-hq 298)."""


DE = Language("de")
GERMAN_CAPTIONS = (
    clause(
        "Die Internetmaterialien sind gut.",
        "The internet materials are good.",
        (("Internetmaterialien", "internet materials"),),
        into=EN,
    ),
)
GERMAN_SAMPLE = FakeDictionaryFile(
    [
        EntryRecord(
            "wiktde:1", "Internet", "", "/ˈɪntɐnɛt/", ("(noun) Internet",), 900
        ),
        EntryRecord(
            "wiktde:2",
            "Material",
            "",
            "/mateˈʁi̯aːl/",
            ("(noun) material", "(noun) equipment"),
            1500,
        ),
    ],
    {"Internet": ["wiktde:1"], "Material": ["wiktde:2"]},
    lemmas={"Materialien": "Material"},
)
"""A German compound the pack hasn't got whole, made of two it has
(polyglotic-hq 390)."""


def _other_learners_windows(
    lab: Lab,
    tools: LearningTools,
    captions: tuple[Clause, ...],
    language: Language,
    into: Language | None = None,
) -> CaptionWindows:
    """One caption window over captions in `language`, with `tools`' card;
    translated `into` a language (None: an English learner's into Chinese,
    the others' into English)."""
    found = CaptionWindows(None, MIC, _areas, learner=tools)
    found.set_labels(LABELS, "You")
    found.set_captioned([("lab", APP)])
    if into is not None:
        found.set_language("lab", into)
    elif language == EN:
        found.set_language("lab", ZH)  # an English learner's: into Chinese
    for n, said in enumerate(captions * 3):
        found.apply(recorded.finished(f"lab-{n:03d}", said, language=language))
    shown = found.windows["lab"]
    shown.always_shown = True
    shown.setGeometry(480, 600, 960, 360)
    lab.pump()
    shown.canvas.repaint()
    lab.closing.append(found.close)
    return found


def english_card(lab: Lab) -> QWidget:
    """An English learner's card in a Chinese interface (ECDICT's meanings
    are Chinese): the commonest Chinese on a card, which 198 found in MS UI
    Gothic."""
    dictionary = EnglishDictionary(english_sample())
    tools = _tools(dictionary, ENGLISH_FREQUENCY.id)
    found = _other_learners_windows(lab, tools, ENGLISH_CAPTIONS, EN)
    _pinned(found, "awkward")
    lab.pump()
    return _photo(found)


ENGLISH_IN_ENGLISH = FakeDictionaryFile(
    [
        EntryRecord(
            "ecdict:awkward",
            "awkward",
            "",
            "ˈɔ:kwəd",
            (
                '(adj) causing inconvenience: "they arrived at an awkward time"',
                "(adj) lacking grace or skill in manner or movement or performance",
                "(adj) difficult to handle or manage especially because of shape",
            ),
            2500,
        ),
        EntryRecord(
            "ecdict:thing",
            "thing",
            "",
            "θiŋ",
            ("(noun) an object; something you do not name exactly",),
            180,
        ),
    ],
    {"awkward": ["ecdict:awkward"], "thing": ["ecdict:thing"]},
)
"""An English learner's dictionary in English (`ecdict-en.sqlite`,
decision 0211), as built from Open English WordNet: "awkward"'s."""


def english_card_in_english(lab: Lab) -> QWidget:
    """An English learner's card in an interface that isn't Chinese: its
    meanings in English, each with its part of speech, the first with an
    example (polyglotic-hq 447)."""
    dictionary = EnglishDictionary(ENGLISH_IN_ENGLISH)
    tools = _tools(dictionary, ENGLISH_FREQUENCY.id)
    found = _other_learners_windows(lab, tools, ENGLISH_CAPTIONS, EN)
    _pinned(found, "awkward")
    lab.pump()
    return _photo(found)


def japanese_card(lab: Lab) -> QWidget:
    """A Japanese word's card (a basic dictionary, Sudachi's word split),
    for a Mandarin learner hearing Japanese: its Japanese in a Japanese
    face."""
    chinese = ChineseDictionary(chinese_sample())
    chinese.prepare()
    tools = _tools(chinese, "hsk-2025")
    tools.basic["ja"] = BasicDictionary(JAPANESE_SAMPLE, JapaneseSplit(), "ja")
    found = _other_learners_windows(lab, tools, JAPANESE_CAPTIONS, JA)
    _pinned(found, "勉強")
    lab.pump()
    return _photo(found)


def sense_classes_english(lab: Lab) -> QWidget:
    entry = EntryRecord(
        "ecdict:guarantee",
        "guarantee",
        "",
        "ˌɡærənˈtiː",
        ("(verb) to promise", "(noun) an assurance", "(law) a written undertaking"),
        2300,
        sense_classes=((WordClass.VERB,), (WordClass.NOUN,), None),
        sense_prefixes=(7, 7, 0),
    )
    dictionary = EnglishDictionary(
        FakeDictionaryFile([entry], {"guarantee": [entry.entry_id]})
    )
    tools = _tools(dictionary, ENGLISH_FREQUENCY.id)
    lines = (clause("We guarantee the work.", "我们保证工程质量。", into=ZH),)
    found = _other_learners_windows(lab, tools, lines, EN)
    _pinned(found, "guarantee")
    lab.pump()
    return _photo(found)


def sense_classes_japanese(lab: Lab) -> QWidget:
    tools = sample_tools()
    entry = replace(
        JAPANESE_SAMPLE.by_id["jmdict:1"],
        sense_classes=((WordClass.NOUN,), (WordClass.NOUN,)),
    )
    file = FakeDictionaryFile([entry], {"勉強": [entry.entry_id]})
    tools.basic["ja"] = BasicDictionary(file, JapaneseSplit(), "ja")
    found = _other_learners_windows(lab, tools, JAPANESE_CAPTIONS, JA)
    _pinned(found, "勉強")
    lab.pump()
    return _photo(found)


def sense_classes_chinese(lab: Lab) -> QWidget:
    entry = EntryRecord(
        "cedict:baozheng",
        "保证",
        "保證",
        "bao3 zheng4",
        ("to promise; to guarantee", "a guarantee"),
        1600,
        sense_classes=((WordClass.VERB,), (WordClass.NOUN,)),
    )
    dictionary = ChineseDictionary(
        FakeDictionaryFile(
            [entry], {"保证": [entry.entry_id], "保證": [entry.entry_id]}
        )
    )
    dictionary.prepare()
    tools = _tools(dictionary, "hsk-2025")
    lines = (clause("我保证会来。", "I promise I'll come."),)
    found = _other_learners_windows(lab, tools, lines, ZH)
    _pinned(found, "保证")
    lab.pump()
    return _photo(found)


def russian_card(lab: Lab) -> QWidget:
    """A Russian word's card (a basic dictionary) for a Mandarin learner: an
    inflected form with its own stress (ру́ку) under the word it belongs
    to, stressed (рука́) - polyglotic-hq 298."""
    chinese = ChineseDictionary(chinese_sample())
    chinese.prepare()
    tools = _tools(chinese, "hsk-2025")
    tools.basic["ru"] = BasicDictionary(RUSSIAN_SAMPLE, SpacedSplit("ru"), "ru")
    # The lookup fixture supplies no translation into the window's usual target.
    found = _other_learners_windows(lab, tools, RUSSIAN_CAPTIONS, RU, into=Language(""))
    _pinned(found, "руку")
    lab.pump()
    return _photo(found)


def german_compound(lab: Lab) -> QWidget:
    """A German compound the pack hasn't got (Internetmaterialien) for an
    English learner: not in the dictionary as a whole, its parts' meanings
    joined, and each part below - polyglotic-hq 390."""
    english = EnglishDictionary(english_sample())
    tools = _tools(english, ENGLISH_FREQUENCY.id)
    tools.basic["de"] = BasicDictionary(GERMAN_SAMPLE, SpacedSplit("de"), "de")
    found = _other_learners_windows(lab, tools, GERMAN_CAPTIONS, DE)
    _pinned(found, "Internetmaterialien")
    lab.pump()
    return _photo(found)


def learn_too(lab: Lab) -> QWidget:
    """The Japanese word's card for a Chinese learner, asking once whether
    to learn Japanese too (DECISIONS.md #65, polyglotic-hq 262)."""
    chinese = ChineseDictionary(chinese_sample())
    chinese.prepare()
    tools = _tools(chinese, "hsk-2025")
    tools.basic["ja"] = BasicDictionary(JAPANESE_SAMPLE, JapaneseSplit(), "ja")
    found = _other_learners_windows(lab, tools, JAPANESE_CAPTIONS, JA)
    assert found.card is not None
    settings = Settings(None)
    settings.update(learning="zh")
    found.card.model.offer = LearningOffer(settings)
    _pinned(found, "勉強")
    lab.pump()
    return _photo(found)


# -- the word's counterpart in its line (polyglotic-hq 328) ---------------------------

VI = Language("vi")
KO = Language("ko")
INTO_VIETNAMESE = (
    clause(
        "That was an awkward thing to say.",
        "Nói như vậy thật là ngượng ngùng.",
        (("awkward", "ngượng ngùng"),),
        into=VI,
    ),
    clause(
        "Phones are ubiquitous now.",
        "Giờ đây điện thoại có mặt ở khắp mọi nơi trên thế giới.",
        (("ubiquitous", "có mặt ở khắp mọi nơi trên thế giới"),),
        into=VI,
    ),
)
"""An English learner whose translation is Vietnamese: ECDICT's meanings
are Chinese, the line's are Vietnamese."""
KOREAN_CAPTIONS = (
    clause("내일 은행에 가요.", "I'm going to the bank tomorrow.", (("은행", "bank"),)),
    clause("은행이 문을 닫았어요.", "The bank is closed.", (("은행", "bank"),)),
)
"""Korean, with no dictionary on this PC: the counterpart is the card."""


def _into_vietnamese(lab: Lab) -> CaptionWindows:
    tools = _tools(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    found = _other_learners_windows(lab, tools, INTO_VIETNAMESE, EN, into=VI)
    return found


def counterpart_vietnamese(lab: Lab) -> QWidget:
    """An English learner reading Vietnamese (328): the card says "Here:
    ngượng ngùng" above ECDICT's Chinese meaning - a meaning in their own
    language, from the line's own translation."""
    found = _into_vietnamese(lab)
    _pinned(found, "awkward")
    lab.pump()
    return _photo(found)


def counterpart_long(lab: Lab) -> QWidget:
    """A long counterpart, hovered (328): a paraphrase of one word - the
    hover card as wide as it may be, the words wrapping in it."""
    found = _into_vietnamese(lab)
    _hovered(found, "ubiquitous")
    lab.pump()
    return _photo(found)


def counterpart_no_dictionary(lab: Lab) -> QWidget:
    """A word in a language with no dictionary here (Korean), pinned (328):
    what it is in the line's translation is the card's main content."""
    chinese = ChineseDictionary(chinese_sample())
    chinese.prepare()
    found = _other_learners_windows(
        lab, _tools(chinese, "hsk-2025"), KOREAN_CAPTIONS, KO
    )
    _pinned(found, "은행에")
    lab.pump()
    return _photo(found)


def counterpart_none(lab: Lab) -> QWidget:
    """A word with no link in its line (这个), pinned (328): no "Here:"
    line - never an empty one."""
    found = windows(lab)
    _pinned(found, "这个")
    lab.pump()
    return _photo(found)


def _tools(
    dictionary: ChineseDictionary | EnglishDictionary, scheme: str
) -> LearningTools:
    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    vocabulary = Vocabulary(MemoryLearningStore(), facts, scheme, Clock())
    return LearningTools(vocabulary, dictionary)


def _let_go(shown: CaptionWindow) -> QPoint:
    """Where a drag across the held selection lets go, on the screen: the
    end of its last line (the sentence card opens there, 522)."""
    chosen = shown.held.selection
    assert chosen is not None
    last = max(held_rects(shown.canvas.placed, chosen), key=lambda r: r.bottom())
    return shown.mapToGlobal(QPoint(round(last.right()), round(last.center().y())))


def _sentence_offered(lab: Lab) -> CaptionWindow:
    """Words selected across the newest captions in view (up to three),
    from part way through the first: the card that saves them as a
    sentence, at the mouse (polyglotic-hq 459, 522)."""
    shown = window_of(windows(lab))
    lines = [line for line, _, _ in shown.canvas.placed]
    first, last = lines[-min(3, len(lines))], lines[-1]
    shown.held.hold(
        Selection(
            Place(first.key, 0, 2, RowKind.ORIGINAL),
            Place(last.key, 0, 4, RowKind.ORIGINAL),
        )
    )
    at = _let_go(shown)
    lab.time(
        "sentence_offered", lambda: shown._offer_sentence(at), budget=budgets.CLICK
    )
    lab.pump()
    return shown


def sentence_offered(lab: Lab) -> QWidget:
    card = _sentence_offered(lab).sentence_card
    assert card is not None and card.isVisible()
    return card


def _say_it_offered(
    lab: Lab, voices: tuple[Voice, ...], better: BetterVoice | None = None
) -> CaptionWindow:
    """The sentence card with Say it (polyglotic-hq 495): a stand-in reader
    with `voices`."""
    found = windows(lab)
    found.use_say_it(
        SelectionReading(
            _Speaker(voices), open_url=lambda url: None, parent=found, better=better
        )
    )
    shown = window_of(found)
    lines = [line for line, _, _ in shown.canvas.placed]
    first, last = lines[-min(3, len(lines))], lines[-1]
    shown.held.hold(
        Selection(
            Place(first.key, 0, 2, RowKind.ORIGINAL),
            Place(last.key, 0, 4, RowKind.ORIGINAL),
        )
    )
    shown._offer_sentence(_let_go(shown))
    lab.pump()
    return shown


HUIHUI = Voice("zh", "Microsoft Huihui", "zh-CN")
DAVID = Voice("en", "Microsoft David", "en-US")


def sentence_say_it(lab: Lab) -> QWidget:
    """The card's second row: Say it, a button a language (495)."""
    card = _say_it_offered(lab, (HUIHUI, DAVID)).sentence_card
    assert card is not None and card.isVisible()
    return card


def sentence_reading(lab: Lab) -> QWidget:
    """Say it reading what was said: its button turned to Stop, the word
    being said lit in the window under the selection (495)."""
    shown = _say_it_offered(lab, (HUIHUI, DAVID))
    card = shown.sentence_card
    assert card is not None
    card.sides[0][0].click()
    lab.pump()
    shown.canvas.repaint()
    return _Together([shown, card])


def sentence_no_voice(lab: Lab) -> QWidget:
    """No Chinese voice on this PC: what was said's button says to add one
    (495)."""
    card = _say_it_offered(lab, (DAVID,)).sentence_card
    assert card is not None and card.isVisible()
    return card


def sentence_better_voice(lab: Lab) -> QWidget:
    """What was said read in a Mac's basic Chinese voice: the card says how
    to add a better one, "Don't show again" and Dismiss (518)."""
    shown = _say_it_offered(lab, (TINGTING, DAVID), _better())
    card = shown.sentence_card
    assert card is not None
    card.sides[0][0].click()
    lab.pump()
    assert card.better.isVisible()
    return card


def sentence_look_it_up(lab: Lab) -> QWidget:
    """Four characters dragged across within one clause - too many for a
    lookup of their own (522): the sentence card with Say it and a third
    row, Look it up (polyglotic-hq 533)."""
    found = windows(lab)
    found.use_say_it(
        SelectionReading(
            _Speaker((HUIHUI, DAVID)), open_url=lambda url: None, parent=found
        )
    )
    shown = window_of(found)
    line, laid, _ = next(
        (line, laid, rect)
        for line, laid, rect in reversed(shown.canvas.placed)
        if laid.rows
        and laid.rows[0].row.kind is RowKind.ORIGINAL
        and all("一" <= c <= "鿿" for c in laid.rows[0].row.text[:4])
    )
    row = laid.rows[0]
    clause = row.row.clause
    shown.held.hold(
        Selection(
            Place(line.key, clause, 0, RowKind.ORIGINAL),
            Place(line.key, clause, 4, RowKind.ORIGINAL),
        )
    )
    shown._offer_sentence(_let_go(shown), Marked(line.key, row.index, 0, 4))
    lab.pump()
    card = shown.sentence_card
    assert card is not None and card.look_up.isVisible()
    return card


def sentence_saved(lab: Lab) -> QWidget:
    """The same, a category clicked: "Saved to Tricky" for a moment."""
    card = _sentence_offered(lab).sentence_card
    assert card is not None
    card.buttons[-1].click()
    lab.pump()
    return card


class _LabClock:
    """The playout's clock in the lab: it moves when the lab says."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _steady(
    lab: Lab, rules: PlayoutRules, more: int = 4, cards: bool = False
) -> CaptionWindows:
    """Steady's two zones (polyglotic-hq 526, decision 0251): the captions
    already there are the transcript; `more` come word by word into the
    live lines below, every word's moment come. With `cards`, its card
    stack instead (552, decision 0260)."""
    found = windows(lab)
    found.set_cards(cards)
    clock = _LabClock()
    found.word_clock = clock
    found.set_playout(rules)
    found.set_timing(CaptionMode.STEADY)
    for update in finished(more, start=CAPTIONS):
        found.apply(update)
        for _ in range(200):  # every word shown; a held translation waits
            due = found.playout.due()
            if due is None or due - clock.now > 0.5:
                break
            clock.now = max(clock.now, due) + 0.1
            found.release_words()
    lab.pump()
    window_of(found).repaint()
    return found


def steady_two_zones(lab: Lab) -> QWidget:
    """526: the live reading lines below, the settled transcript above."""
    return window_of(_steady(lab, PlayoutRules(delay=0.0, hold_back=0)))


def steady_cards(lab: Lab) -> QWidget:
    """552, decision 0260: Steady's card stack - each line a card with its
    translation's room, the older ones turning away above."""
    return window_of(_steady(lab, PlayoutRules(delay=0.0, hold_back=0), cards=True))


def steady_follow(lab: Lab) -> QWidget:
    """526, decision 0253: Follow - the translation leads, what was said
    smaller and fainter, in both zones."""
    found = _steady(lab, PlayoutRules(delay=0.0, hold_back=0))
    found.set_path(ReadingPath.FOLLOW)
    lab.pump()
    window_of(found).repaint()
    return window_of(found)


def steady_acquisition(lab: Lab) -> QWidget:
    """526, decision 0253: Acquisition - the newest caption said in full,
    its translation still held back."""
    rules = PlayoutRules(delay=0.0, hold_back=0, translation_after=2.0)
    return window_of(_steady(lab, rules))


STATES = [
    State(f"ui_next.{name}", run, gated=True, scene=scene)
    for name, run, scene in (
        ("w3_hover", hover, False),
        ("w3_pinned", pinned, False),
        ("w3_part", part, False),
        ("w3_not_found", not_found, False),
        ("w3_learning_action", learning_action, False),
        ("w3_save_to", save_to, False),
        ("w3_sentence_offered", sentence_offered, False),
        ("w3_sentence_saved", sentence_saved, False),
        ("w3_sentence_look_it_up", sentence_look_it_up, False),
        ("w3_sentence_say_it", sentence_say_it, False),
        ("w3_sentence_reading", sentence_reading, False),
        ("w3_sentence_no_voice", sentence_no_voice, False),
        ("w3_sentence_better_voice", sentence_better_voice, False),
        ("w3_dictionary_out", dictionary_out, False),
        ("w3_say_it", say_it, False),
        ("w3_say_it_long", say_it_long, False),
        ("w3_no_voice", no_voice, False),
        ("w3_better_voice", better_voice, False),
        ("w1_links_on_hover", links_on_hover, False),
        ("w1_linked_and_in_deck", linked_and_in_deck, True),
        ("w1_linked_arrows", linked_arrows, True),
        ("w1_pinyin_in_link_colours", pinyin_in_link_colours, True),
        ("w1_pinyin_in_link_colours_paper", pinyin_in_link_colours_paper, True),
        ("w1_translation_in_link_colours", translation_in_link_colours, True),
        ("w1_pinyin_custom", pinyin_custom, True),
        ("w1_quiet", quiet, True),
        ("w1_quiet_hover", quiet_hover, False),
        ("w1_quiet_paper", quiet_paper, True),
        ("w1_zhuyin", zhuyin, True),
        ("w1_steady_two_zones", steady_two_zones, True),
        ("w1_steady_cards", steady_cards, True),
        ("w1_steady_follow", steady_follow, True),
        ("w1_steady_acquisition", steady_acquisition, True),
        ("w3_english_card", english_card, False),
        ("w3_english_card_in_english", english_card_in_english, False),
        ("w3_japanese_card", japanese_card, False),
        ("w3_sense_classes_english", sense_classes_english, False),
        ("w3_sense_classes_japanese", sense_classes_japanese, False),
        ("w3_sense_classes_chinese", sense_classes_chinese, False),
        ("w3_russian_card", russian_card, False),
        ("w3_german_compound", german_compound, False),
        ("w3_learn_too", learn_too, False),
        ("w3_counterpart_vietnamese", counterpart_vietnamese, False),
        ("w3_counterpart_long", counterpart_long, False),
        ("w3_counterpart_no_dictionary", counterpart_no_dictionary, False),
        ("w3_counterpart_none", counterpart_none, False),
        *TONE_STATES,
    )
]
