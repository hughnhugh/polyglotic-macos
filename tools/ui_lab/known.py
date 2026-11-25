"""Learning load's colours (polyglotic-hq 489): every word of a caption in
a colour by how well the learner knows it, for three learners - a
beginner (500 words), an intermediate learner (2,000, with a few words
said, saved, heard and looked up) and a near-native one (20,000) - on
Classic's panel, then orange to blue and Paper's cream. The sample
dictionary (CI has no dictionary files) with its words' real CC-CEDICT
ranks (`RANKS`), over the made-up conversation.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from zlib import crc32

from PySide6.QtWidgets import QWidget
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample

from polyglotic_desktop.core.learning.known_map import MAP_WORDS
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.known_map_card import KnownMapCard
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.known_map import known_map_view
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Palette
from polyglotic_desktop.ui_next.views.presets import BY_KEY
from tools.ui_lab.caption_window import LABELS, _areas
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.new_parts import finished
from tools.ui_lab.panels import page

RANKS = {
    "了": 1, "人": 10, "这": 14, "还": 29, "个": 41, "这个": 88, "研究": 157,
    "北京": 162, "女": 222, "个人": 605, "电": 608, "足": 845, "画": 1109,
    "生命": 1195, "满足": 1813, "电脑": 2453, "脑": 2791, "游戏": 2847,
    "蛇": 3331, "足球": 3810, "研究生": 4207, "起源": 4914, "添": 5202,
    "还款": 25807, "画蛇添足": 46844, "打游戏": 75719,
}  # fmt: skip
"""The sample's words' frequency ranks in CC-CEDICT as the Chinese pack
of 2026-11-16 ranks them (还钱 has none)."""

LEARNERS = {"beginner": 500, "intermediate": 2000, "near_native": 20000}
"""The three learners' lines: about how many words each knows."""


def tools_for(known: int) -> LearningTools:
    """A learner of `known` words on the sample dictionary with real ranks;
    the intermediate one has said, saved, heard and looked up a few."""
    dictionary = ChineseDictionary(chinese_sample(frequency_ranks=RANKS))

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    dictionary.prepare()
    clock = Clock()
    vocabulary = Vocabulary(MemoryLearningStore(), facts, "hsk-2025", clock)
    tools = LearningTools(vocabulary, dictionary)
    vocabulary.set_known_words(known)
    if known == LEARNERS["intermediate"]:
        _a_few_weeks(tools, clock)
    return tools


def _a_few_weeks(tools: LearningTools, clock: Clock) -> None:
    """What an intermediate learner did: 游戏 heard on four days, 足球 on
    one, 电脑 said known, 研究生 saved, 满足 looked up just now."""
    vocabulary = tools.vocabulary

    def entry(word: str) -> EntryId:
        return tools.lookup(word)[0].entry_id

    for day in range(4):
        words = "游戏 足球" if day == 0 else "游戏"
        vocabulary.caption_finished(f"heard-{day}", tools.words_in(words), False)
        clock.advance(days=1)
    vocabulary.set_status(entry("电脑"), WordStatus.KNOWN)
    found = tools.lookup("研究生")[0]
    vocabulary.save(
        found.entry_id, found.headword, found.traditional, found.reading, "",
        "saved", LookupContext("研究生"),
    )  # fmt: skip
    facts = tools.words_in("满足")[0].entry
    vocabulary.looked_up(facts, pinned=True)
    clock.advance(hours=1)


def _windows(
    lab: Lab, tools: LearningTools, look: CaptionLook, height: int = 360
) -> QWidget:
    found = CaptionWindows(None, MIC, _areas, learner=tools)
    tools.changed.connect(found.learning_changed)
    found.set_labels(LABELS, "You")
    found.set_look(look)
    found.set_captioned([("lab", APP)])
    shown = found.windows["lab"]
    shown.opacity_wanted.emit(look.opacity)
    for update in finished(150):
        found.apply(update)
    shown.always_shown = True
    shown.setGeometry(480, 600, 960, height)
    lab.pump()
    shown.canvas.repaint()
    lab.closing.append(found.close)
    return shown


def coloured(
    known: int, palette: Palette = Palette.RED_GREEN, preset: str = "classic"
) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        colours = BY_KEY[preset]
        look = replace(
            CaptionLook(),
            original=colours.original,
            translation=colours.translation,
            background=colours.background,
            opacity=colours.opacity,
            lab=CaptionLab(load=True, load_colours=palette),
        )
        # on Paper, the newest caption alone: an older one's source label,
        # stepped back, is 3.9:1 there - not this mode's (489's findings)
        height = 200 if preset == "paper" else 360
        return _windows(lab, tools_for(known), look, height)

    return run


STATES = [
    *(
        State(f"ui_next.known_{name}", coloured(words), gated=True, scene=True)
        for name, words in LEARNERS.items()
    ),
    State(
        "ui_next.known_orange_blue",
        coloured(LEARNERS["intermediate"], Palette.ORANGE_BLUE),
        gated=True,
        scene=True,
    ),
    State(
        "ui_next.known_paper",
        coloured(LEARNERS["intermediate"], preset="paper"),
        gated=True,
        scene=True,
    ),
]


# -- the map on Learning --------------------------------------------------------------

MAP_LINES = {"beginner": 500, "intermediate": 2000, "near_native": 20000}


def map_learner(known: int) -> tuple[Vocabulary, list[tuple[int, EntryFacts]]]:
    """A learner of `known` words over 20,000 made-up words in order; the
    intermediate one said, saved, heard and looked up some this week."""
    words = [
        (n, EntryFacts(EntryId(f"lab:{n}"), None, n, crc32(b"%d" % n) % 140 == 0))
        for n in range(1, MAP_WORDS + 1)
    ]  # about 1 in 140 a name, scattered: drawn neutral
    by_id = {f.entry_id: f for _, f in words}
    clock = Clock(datetime(2026, 11, 4, 9, 0, tzinfo=UTC))
    vocabulary = Vocabulary(
        MemoryLearningStore(), lambda e, _: by_id.get(e), "hsk-2025", clock
    )
    vocabulary.set_known_words(known)
    clock.advance(days=10)
    if known == MAP_LINES["intermediate"]:
        for day in range(3):
            heard = [WordInLine(0, 1, f) for _, f in words[2000:2600:3]]
            vocabulary.caption_finished(f"m{day}", heard, by_you=False)
            clock.advance(days=1)
        for _, f in words[3000:3400:2]:
            vocabulary.set_status(f.entry_id, WordStatus.KNOWN)
        for _, f in words[1200:1260:3]:
            vocabulary.looked_up(f, pinned=True)
    return vocabulary, words


def known_map(known: int) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        vocabulary, words = map_learner(known)
        card = KnownMapCard()
        view = known_map_view(
            "Mandarin",
            words,
            vocabulary.chances,
            vocabulary.chances_as_of,
            datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        )
        card.show_map(view, lambda e: str(e))
        return page(lab, 640, card)

    return run


MAP_STATES = [
    State(f"ui_next.known_map_{name}", known_map(words), gated=True)
    for name, words in MAP_LINES.items()
]
