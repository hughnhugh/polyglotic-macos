"""Words, Account, Settings and Help in the new main window (polyglotic-hq
project 109's structure, section 7; build step 6), held to their budgets:
each page's first show (a page switch, cold) and its next (warm); Words
empty and full - a few hundred made-up words, the level picked, words
heard, statuses set, saved words in three categories - and at the
window's minimum; a status changed and a search typed on the full list;
Words opened before the start's read ahead is back ("Reading your
words...", 229); Account signed out and in; Settings; Help's check with an app gone
quiet, and with the learning data set aside (206). No page may scroll
sideways.

Made-up words (pairs of common characters, their meanings the two
characters' put together) and made-up apps only; learning kept in memory.
"""

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import partial

from PySide6.QtCore import QCoreApplication, QPoint, QRect
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea, QWidget
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample, english_sample

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import (
    UNLIMITED,
    KnownLine,
    LanguageChoices,
    WindowSize,
)
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.sentences import SentencePart
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem
from polyglotic_desktop.core.lexicon.pack_download import Step as PackStep
from polyglotic_desktop.core.listening.check import Facts, SourceActivity, Ticked
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import default_caption_mode
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordStatus
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.perf.budgets import Budget
from polyglotic_desktop.ui import interface_language
from polyglotic_desktop.ui import theme as todays_theme
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.account_page import AccountPage
from polyglotic_desktop.ui_next.help_page import HelpPage
from polyglotic_desktop.ui_next.learning_page import LearningPage
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.main_window import (
    FLOOR,
    FLOOR_SCALE,
    FRAME,
    MainWindow,
    roomy_size,
)
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import CaptionLab, NewFade
from polyglotic_desktop.ui_next.views.learning import (
    InstalledPackLine,
    PackLine,
)
from polyglotic_desktop.ui_next.views.learning import cards as learning_cards
from polyglotic_desktop.ui_next.views.panels import (
    JapaneseReadings,
    JapaneseReadingsView,
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetsView
from polyglotic_desktop.ui_next.views.presets import PRESETS
from polyglotic_desktop.ui_next.word_bands import BY_FREQUENCY, BY_LEVEL
from polyglotic_desktop.ui_next.words_page import WordsPage
from tools.ui_lab.heard import (
    HEAVY,
    MONTH_IN,
    NEW_LEARNER,
    Learner,
    learner_tools,
    met_dictionary,
    met_learner_tools,
)
from tools.ui_lab.heard import dictionary as heard_dictionary
from tools.ui_lab.home import SET_ASIDE, hub, scaled
from tools.ui_lab.lab import Lab, State

NORMAL = (1000, 740)
CHARACTERS = {
    "天": ("tian1", "sky"),
    "山": ("shan1", "mountain"),
    "水": ("shui3", "water"),
    "火": ("huo3", "fire"),
    "木": ("mu4", "wood"),
    "日": ("ri4", "sun"),
    "月": ("yue4", "moon"),
    "风": ("feng1", "wind"),
    "雨": ("yu3", "rain"),
    "云": ("yun2", "cloud"),
    "花": ("hua1", "flower"),
    "草": ("cao3", "grass"),
    "鸟": ("niao3", "bird"),
    "鱼": ("yu2", "fish"),
    "马": ("ma3", "horse"),
    "牛": ("niu2", "cow"),
    "茶": ("cha2", "tea"),
    "书": ("shu1", "book"),
    "车": ("che1", "car"),
    "门": ("men2", "door"),
}
WORDS = 400
"""Made-up words in the full state's dictionary."""


def made_up_tools(words: int = WORDS, clock: Clock | None = None) -> LearningTools:
    """The learning tools on a dictionary of `words` made-up two-character
    words, learning kept in memory, on `clock` (a test clock if None)."""
    lines = ["# made up for the UI lab"]
    pairs = [(a, b) for a in CHARACTERS for b in CHARACTERS if a != b]
    for first, second in pairs[:words]:
        (p1, m1), (p2, m2) = CHARACTERS[first], CHARACTERS[second]
        word = first + second
        lines.append(f"{word} {word} [{p1} {p2}] /{m1} {m2}/{m2} of the {m1}/")
    dictionary = ChineseDictionary(chinese_sample("\n".join(lines) + "\n"))

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    dictionary.prepare()  # the word split's data read, as at the app's start
    vocabulary = Vocabulary(MemoryLearningStore(), facts, "hsk-2025", clock or Clock())
    return LearningTools(vocabulary, dictionary)


def full_tools() -> LearningTools:
    """A learner some weeks in: the level picked; 360 words heard, the most
    heard a dozen times; statuses set by hand (the 240 heard least known
    before they were heard, so the week has a coverage); 40 words saved in
    three categories; 8 h 20 min of listening, 2 h 15 min of it this week."""
    clock = Clock(datetime(2026, 10, 14, 19, 0, tzinfo=UTC))
    tools = made_up_tools(clock=clock)
    vocabulary = tools.vocabulary
    for days_on, minutes, category in [
        (0, 150, "video"),
        (6, 125, "game"),
        (8, 90, "call"),
        (7, 60, "video"),
        (4, 75, "video"),
    ]:
        clock.advance(days=days_on)
        listen(vocabulary, clock, minutes, category)
    clock.advance(days=2)
    vocabulary.set_level(Level("hsk-2025", 3))
    pairs = [(a, b) for a in CHARACTERS for b in CHARACTERS if a != b]
    heard = [a + b for a, b in pairs[:360]]
    ids = [tools.lookup(word)[0].entry_id for word in heard]
    for n, entry_id in enumerate(ids[40:120]):
        status = (WordStatus.KNOWN, WordStatus.LEARNING, WordStatus.IGNORED)[n % 3]
        vocabulary.set_status(entry_id, status)
    for entry_id in ids[120:]:  # the rarer ones known: coverage as they're heard
        vocabulary.set_status(entry_id, WordStatus.KNOWN)
    for n, word in enumerate(heard):
        for k in range(1 + (12 * (len(heard) - n)) // len(heard)):
            vocabulary.caption_finished(f"{n}.{k}", tools.words_in(word), k == 3)
    vocabulary.add_category("Food")
    categories = [c.id for c in vocabulary.categories]
    for n, word in enumerate(heard[100:140]):
        entry = tools.lookup(word)[0]
        vocabulary.save(
            entry.entry_id, entry.headword, entry.traditional, entry.reading,
            "", categories[n % len(categories)],
            LookupContext(f"{word}{heard[n]}" if n % 2 else word),
        )  # fmt: skip
    return tools


def listen(vocabulary: Vocabulary, clock: Clock, minutes: int, category: str) -> None:
    """A stretch of listening: a finished caption every 5 seconds."""
    for _ in range(minutes * 12 + 1):
        vocabulary.listened(category)
        clock.advance(seconds=5)
    clock.advance(minutes=30)


def _app(text: str) -> str:
    """The app's own words for its commands (`DesktopApp`'s), in the lab's
    interface language as the app would show them."""
    return QCoreApplication.translate("DesktopApp", text)


def _window(text: str) -> str:
    """A page's name in the main window's sidebar, as `main` names it."""
    return QCoreApplication.translate("MainWindow", text)


def window_with(
    lab: Lab, key: str, page: QWidget, size: tuple[int, int] | None = None
) -> MainWindow:
    """The new main window with a blank Home and `page`, shown on Home - in
    Margin, dark (today's default), with its heading face loaded, whatever
    the states before did - and `page` in the window's stylesheet ahead of
    its first show, as `main` has it a second after the start (decision
    0158): the first show a learner's first click meets."""
    todays_theme.load_heading_face("margin")
    style.use(style.Theme())
    quit_action = QAction(_app("Quit"))
    window = MainWindow(quit_action)
    window.quit_action = quit_action  # type: ignore[attr-defined]
    home = QWidget()
    home.setObjectName("Page")
    window.add_page("home", _window("Home"), home)
    place = "top" if key in ("words", "learning", "account") else "foot"
    window.add_page(key, _window(key.title()), page, place)
    window.resize(*(size or scaled(NORMAL)))
    window.show()
    window.go_to("home")
    lab.pump()
    window.style_ahead()
    lab.pump()
    lab.closing.append(window.close)
    return window


def scroll_holding(widget: QWidget) -> QScrollArea | None:
    """The scroll area `widget` is in: its nearest ancestor that is one. Not
    the window's first: since polyglotic-hq 524 that is the sidebar's, and
    w4_words_sentences scrolled it instead of the page (541)."""
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


def no_horizontal_scrollbar(window: MainWindow) -> None:
    for scroll in window.findChildren(QScrollArea):
        if scroll.isVisible():
            bar = scroll.horizontalScrollBar()
            assert not bar.isVisible(), f"a horizontal scrollbar: {scroll.objectName()}"


def switches(lab: Lab, window: MainWindow, key: str) -> None:
    """The page's first show, then going back and forth."""
    lab.time(
        "page_switch_cold", partial(window.go_to, key), budget=budgets.PAGE_SWITCH_COLD
    )
    for _ in range(3):
        for each in ("home", key):
            lab.time(
                "page_switch_warm",
                partial(window.go_to, each),
                budget=budgets.PAGE_SWITCH_WARM,
            )
    no_horizontal_scrollbar(window)


def words_empty(lab: Lab) -> QWidget:
    tools = made_up_tools(40)
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    window = window_with(lab, "words", page)
    switches(lab, window, "words")
    return window


def _full_words(lab: Lab, size: tuple[int, int]) -> tuple[MainWindow, WordsPage]:
    tools = full_tools()
    card = LookupCard(tools)
    lab.closing.append(card.close)
    page = WordsPage(tools, card)
    tools.changed.connect(page.learning_changed)
    window = window_with(lab, "words", page, size)
    switches(lab, window, "words")
    return window, page


def words_full(lab: Lab) -> QWidget:
    window, page = _full_words(lab, scaled(NORMAL))
    table = page.first.words
    first = table.words.items[0].entry_id
    statuses = [WordStatus.KNOWN, WordStatus.NEW]

    def change_status() -> None:
        page.first.learner.vocabulary.set_status(first, statuses[0])
        statuses.reverse()

    lab.time("status_change", change_status, repeat=6, budget=budgets.CLICK)
    terms = ["sky", "", "tian", ""]

    def search() -> None:
        page.first.search.setText(terms[0])
        page.first._searching.stop()
        page.first._refresh_words()  # what the search's pause runs
        terms.append(terms.pop(0))

    lab.time("search", search, repeat=4, budget=budgets.CLICK)
    assert page.first.words_all.isVisible()  # a few rows, then "Show all (360)"
    # Show all (300 rows) and Show fewer, in turn (polyglotic-hq 250)
    lab.time("show_all", page.first.words_all.click, repeat=4, budget=budgets.CLICK)
    assert not page.first.all_words and not page.first.words_note.isVisible()
    # Words you keep hearing: Show more and Show fewer, in turn (250)
    steps = [page.first.hearing_more, page.first.hearing_fewer]

    def more_or_fewer() -> None:
        steps[0].click()
        steps.reverse()

    lab.time("keep_hearing_more", more_or_fewer, repeat=4, budget=budgets.CLICK)
    assert (
        page.first.hearing_more.isVisible() and not page.first.hearing_fewer.isVisible()
    )
    cell = table.visualRect(table.words.index(0, 0))
    if page.first.card is not None:
        lab.time(
            "lookup_pinned",
            partial(page.first._acted, "word", str(first), cell),
            budget=budgets.LOOKUP_PINNED,
        )
        page.first.card.close_card()
    lab.pump()
    return window


SENTENCES = (
    ("我今天去超市买水果。", "I went to the supermarket today to buy fruit.", "saved"),
    ("你吃饭了吗?我们一起去吧。", "Have you eaten? Let's go together.", "tricky"),
    ("这个游戏很好玩,我天天玩。", "This game is fun, I play it every day.", "saved"),
    ("明天的天气怎么样?", "What's the weather like tomorrow?", "saved"),
)
"""Made-up saved sentences for Words' Saved sentences (polyglotic-hq 459)."""


def words_sentences(lab: Lab) -> QWidget:
    """Words' Saved sentences, scrolled into view, searched in either
    language (polyglotic-hq 459): "天 game" finds two, the one with both
    first."""
    window, page = _full_words(lab, scaled(NORMAL))
    vocabulary = page.first.learner.vocabulary
    for original, translation, category in SENTENCES:
        part = SentencePart(original, translation, (), "Discord")
        vocabulary.save_sentence((part,), original, translation, category, "en")
    lab.pump()
    card = page.first.sentences
    terms = ["天 game", "", "fruit", ""]

    def search() -> None:
        card.search.setText(terms[0])
        card._searching.stop()
        card.refresh()  # what the search's pause runs
        terms.append(terms.pop(0))

    lab.time("sentence_search", search, repeat=4, budget=budgets.CLICK)
    card.search.setText("天 game")
    card._searching.stop()
    card.refresh()
    settled = time.monotonic() + 0.4  # the field's clear button fades in
    while time.monotonic() < settled:
        lab.pump()
    scroll = scroll_holding(card)
    assert scroll is not None, "Saved sentences isn't in a scroll area"
    scroll.ensureWidgetVisible(card, 0, 0)
    assert scroll.verticalScrollBar().value() > 0, "Saved sentences wasn't scrolled to"
    lab.pump()
    return window


def words_two_languages(lab: Lab) -> QWidget:
    """Words for a learner of two languages (polyglotic-hq 250, the user's
    F23): a section each, under a heading with its count, the first open -
    as polyglotic-hq 248's model will have it (today's app has one, and no
    heading). Opening and closing the second is a click."""
    chinese = full_tools()
    english = english_tools()
    page = WordsPage([chinese, english], None)
    for tools, words in zip((chinese, english), page.languages, strict=True):
        tools.changed.connect(words.learning_changed)
    window = window_with(lab, "words", page)
    switches(lab, window, "words")
    lab.time(
        "open_or_close",
        page.sections[1].heading.click,
        repeat=4,
        budget=budgets.CLICK,
    )
    lab.pump()
    return window


def english_tools() -> LearningTools:
    """An English learner on the sample dictionary: a few words heard."""
    dictionary = EnglishDictionary(english_sample())

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    vocabulary = Vocabulary(MemoryLearningStore(), facts, "en-frequency", Clock())
    tools = LearningTools(vocabulary, dictionary)
    for n in range(3):
        words = tools.words_in("she keeps running to them, and they run")
        vocabulary.caption_finished(f"en{n}", words, False)
    return tools


def sideways(window: MainWindow) -> list[str]:
    """Every page of `window` - every Settings section - that scrolls
    sideways, or has a part wider than its own (a table's columns past its
    edge): "page: area by N px"."""
    found = []
    views: list[tuple[str, str]] = []
    for key in window.pages:
        if key == "settings":
            views += [("settings", section) for section in SECTIONS]
        else:
            views.append((key, ""))
    for key, section in views:
        window.go_to(key)
        if section:
            shown = window.pages[key]
            page = shown if isinstance(shown, SettingsPage) else None
            page = page or shown.findChild(SettingsPage)
            assert page is not None
            page.show_section(section)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()  # the scroll areas' bars, after the layout
        shown = window.pages[key]
        areas = shown.findChildren(QAbstractScrollArea)
        if isinstance(shown, QAbstractScrollArea):  # a page that scrolls itself
            areas.insert(0, shown)
        for area in areas:
            bar = area.horizontalScrollBar()
            if area.isVisible() and bar.maximum() > 0:
                name = area.objectName() or type(area).__name__
                found.append(
                    f"{key}{'/' + section if section else ''}: {name} by {bar.maximum()}"
                )
    return found


def at_floor(lab: Lab) -> QWidget:
    """The main window at its floor (760 x 520: 1280 x 720 at 150 %, or
    1366 x 768, has no more - `FLOOR`): no page, no Settings section,
    scrolls sideways, in the interface language and text size the lab runs
    at (polyglotic-hq 354: 16 of 21 languages did, by up to 153 px) - up to
    FLOOR_SCALE. Words full, three apps captioned; shown on Home. Over
    FLOOR_SCALE (CI's Windows 200 % run) it's photographed as tall as it
    opens (`roomy_size`), still at the floor's width: 520 px is shorter
    than its sidebar there (354's report), which isn't what this state is
    about. Home must still fit that width at 200 %."""
    built = hub(
        lab,
        {"apps": ["Discord", "Video Player", "Web Browser"], "learning": "zh"},
        tools=full_tools(),
    )
    window = built.window
    window.fit_to(QRect(0, 0, FLOOR[0] + FRAME, FLOOR[1] + FRAME))
    lab.pump()
    assert (window.width(), window.height()) == FLOOR, (window.width(), window.height())
    found = sideways(window)
    if style.text_scale() <= FLOOR_SCALE:
        assert not found, f"pages scroll sideways at the floor: {'; '.join(found)}"
    else:
        window.fit_to(QRect(0, 0, FLOOR[0] + FRAME, roomy_size()[1] + FRAME))
    window.go_to("home")
    lab.pump()
    no_horizontal_scrollbar(window)
    return window


def words_minimum(lab: Lab) -> QWidget:
    window, _page = _full_words(lab, roomy_size())
    assert (window.width(), window.height()) == roomy_size()
    return window


def learning(
    languages: LearningLanguages,
    choice: WordIntroductions,
    running: tuple[str, ...] = ("zh",),
    packs: Mapping[str, PackLine] | None = None,
    installed: Sequence[InstalledPackLine] = (),
    learning_window: WindowSize | None = None,
    recorded: Mapping[str, tuple[int, str]] | None = None,
) -> Callable[[Lab], QWidget]:
    """Learning (polyglotic-hq 262): the languages being learned, each card
    saying what its dictionary gives and its level, and word introductions
    with the caption they draw. `running`: the full languages open now (306:
    every one learned, open at once). `packs`: a basic language's pack line
    on its card; `installed`: the packs on this PC (decision 0122).
    `learning_window`: Chinese's level said in words (about 1,000) and this learning
    window chosen (decision 0144); None: the level picked as HSK 3.
    `recorded`: a full dictionary's recorded words, their size and credits
    (decision 0197)."""

    def run(lab: Lab) -> QWidget:
        tools = full_tools()  # Chinese, the level picked
        if learning_window is not None:
            tools.vocabulary.set_known_words(1000)
        delete = QAction(QCoreApplication.translate("Account", "Delete learning data…"))
        delete.setObjectName("account.delete_learning")
        page = LearningPage(delete)
        page.keep = delete  # type: ignore[attr-defined]

        def level_of(code: str) -> KnownLine | None:  # Chinese's picked; none else
            return tools.vocabulary.line if code == "zh" and code in running else None

        here = tuple(p.code for p in installed)
        page.show_learning(
            languages,
            learning_cards(
                languages,
                running,
                level_of,
                here,
                pack_line=(packs or {}).get,
                choices_of=lambda _code: LanguageChoices(window_size=learning_window),
                recorded_of=lambda code: (recorded or {}).get(code, (0, "")),
            ),
            choice,
            running[0],
            chinese=running[0] == "zh",
        )
        page.show_installed(installed)
        window = window_with(lab, "learning", page)
        switches(lab, window, "learning")
        return window

    return run


def account(signed_in: bool) -> Callable[[Lab], QWidget]:
    def run(lab: Lab) -> QWidget:
        page = AccountPage()
        report = QAction(_app("Report a problem…"))
        suggest = QAction(_app("Suggest something…"))
        report.setObjectName("feedback.problem")
        suggest.setObjectName("feedback.suggest")
        page.add_feedback(report, suggest)
        page.keep = (report, suggest)  # type: ignore[attr-defined]
        page.set_signed_in(signed_in)
        window = window_with(lab, "account", page)
        switches(lab, window, "account")
        lab.time(
            "sign_in_or_out",
            lambda: page.set_signed_in(not page.sign_out.isVisible()),
            repeat=4,
            budget=budgets.CLICK,
        )
        if signed_in:  # signing out forgets the ID; the next session says it
            page.show_account("3f9c2a7e-made-up")
        lab.pump()
        return window

    return run


def settings(
    section: str,
    size: tuple[int, int] | None = None,
    scrolled_into: int = -1,
    presets: PresetsView | None = None,
    timing: TimingView | None = None,
    pick_language: str | None = None,
    japanese_readings: JapaneseReadings | None = None,
    *,
    hotkeys_conflict: bool = False,
) -> Callable[[Lab], QWidget]:
    """Settings on `section` (one of `SECTIONS`: 304's six, and 470's Word
    links and Readings) - at `size` if given (the window's minimum) - the views made
    up as a learner might have them; on the Lab, some of its values moved
    (284). `scrolled_into`: scrolled into the section's card of that index,
    its own title under the pinned sections, which name it (470)."""

    def run(lab: Lab) -> QWidget:
        tell_us = QAction(_app("Tell us"))
        tell_us.setObjectName("settings.work_with_us")
        look = LookView(CaptionLook())
        page = SettingsPage(
            [("margin", "Margin"), ("glaze", "Glaze"), ("signal", "Signal")],
            tell_us,
            interface_language.picker(),
            look=look,
            timing=timing or TimingView(Timing(default_caption_mode())),
            speech=LanguagesView(SessionLanguages(in_use=("en",))),
            presets=presets,
            japanese_readings=JapaneseReadingsView(japanese_readings),
        )
        page.keep = (tell_us,)  # type: ignore[attr-defined]
        if section == "dictation":
            defaults = AppSettings()
            page.show_dictation(
                defaults.dictation,
                defaults.dictation_key,
                defaults.dictation_language,
                defaults.dictation_australian,
            )
            page.show_respeaking(defaults.type_theirs, defaults.respeak_key)
        page.show_theme("margin", "dark")
        page.show_running_language(
            interface_language.in_use(lab.app), interface_language.ENGLISH
        )
        page.show_interface_language("")
        if pick_language is not None:
            index = page.language_picker.findData(pick_language)
            if index >= 0:
                page.language_picker.setCurrentIndex(index)
        # a machine draft's "Tell us what reads wrong", as main shows it
        page.show_draft(interface_language.is_draft(interface_language.in_use(lab.app)))
        page.set_version("0.4.0", "win-x64-alpha")
        page.set_notices("Made-up notices for the lab.")
        window = window_with(lab, "settings", page, size)
        switches(lab, window, "settings")
        section_switches(lab, page, section)
        if section == "look":  # the preview and the panels redrawn
            order = [preset.key for preset in PRESETS]
            lab.time(
                "preset",
                lambda: look.set_preset(
                    order[(order.index(look.started_from or "") + 1) % len(order)]
                ),
                repeat=10,
                budget=budgets.CLICK,
            )
            look.set_preset("classic")
            lab.pump()
        if section == "hotkeys":
            if hotkeys_conflict:
                # 966: refused hotkey with two tested free alternatives, a
                # shared-hook hotkey with alternatives, and Everywhere on a
                # typing key showing the pass-through warning.
                page.show_hotkeys(
                    {"hide": "", "copy": "a", "live": "space"},
                    {"pause"},
                    scopes={"copy": "everywhere", "live": "app"},
                    shared={"lock"},
                    alternatives={
                        "pause": ("ctrl+alt+shift+p", "f9"),
                        "lock": ("ctrl+alt+shift+l", "f10"),
                    },
                )
            else:
                # every key in one place (567, 966): one changed, one cleared,
                # one another program has, and a modifier-only key refused
                page.show_hotkeys(
                    {"hide": "", "copy": "ctrl+alt+c"},
                    {"pause"},
                    alternatives={"pause": ("ctrl+alt+shift+p", "f9")},
                )
                page.hotkeys_card.lines["bigger"].box.pressed_key.emit("right_ctrl")
            lab.pump()
        if section == "lab":  # its own section, at its top (304)
            look.set_lab(CaptionLab(new_for=3.0, new_fade=NewFade.GRADUAL, older=0.55))
            lab.pump()
        if scrolled_into >= 0:
            card = page.cards(section)[scrolled_into]
            inner = page.widget()
            assert inner is not None
            top = card.mapTo(inner, QPoint(0, 0)).y()
            page.verticalScrollBar().setValue(top + 60)
            lab.pump()
        no_horizontal_scrollbar(window)
        return window

    return run


def section_switches(lab: Lab, page: SettingsPage, section: str) -> None:
    """Each section Settings hasn't shown yet, shown for the first time
    (`section_first_show`, held to a first show's budget), ending on
    `section`; then going round the sections twice, ending on it again
    (`section_switch`, a section shown again: a warm switch's budget). Both
    timed apart (polyglotic-hq 381): timed together, 5 of the 12 switches
    were first shows (9-45 ms), so the median held to 8 ms was in effect
    the slowest warm switches'."""
    others = [key for key in SECTIONS if key != section]
    shown = {key for key, box in page.section.items() if not box.isHidden()}
    for key in [*others, section]:
        if key not in shown:
            lab.time(
                "section_first_show",
                partial(page.show_section, key),
                budget=budgets.PAGE_SWITCH_COLD,
            )
            shown.add(key)
    for key in [*others, section] * 2:
        lab.time(
            "section_switch",
            partial(page.show_section, key),
            budget=budgets.PAGE_SWITCH_WARM,
        )


def help_page(lab: Lab) -> QWidget:
    now = time.monotonic()
    app = SourceId("app-1")

    def facts() -> Facts:
        return Facts(
            now=time.monotonic(),
            connection="listening",
            paused=False,
            overlays_hidden=False,
            ticked=[Ticked(app, "Video Player", "app")],
            activity={app: SourceActivity(now - 300, now - 200, now - 60, now - 70)},
            last_caption=now - 70,
        )

    page = HelpPage(facts)
    window = window_with(lab, "help", page)
    switches(lab, window, "help")
    return window


def words_heard(learner: Learner, by_level: bool = False) -> Callable[[Lab], QWidget]:
    """Words for a made-up learner with real-looking numbers (project 163):
    the summary line, the tiles and the bands - by HSK level if asked.

    Each learner's first show of Words is timed but not held to its
    budget: it grows with the words met - the made-up learners have 2,942,
    8,570 and 11,997 - and took 22-53, 43-80 and 50-122 ms on the user's PC
    (2026-11-07, at 100-150 % text, with CI's runner busy on the same PC).
    Most of it is the page's lists that were there before: "Your words"
    (about 24 ms for the heavy learner) and "Words you keep hearing" (15
    ms) go through every word met; "What you've heard" takes about 8 ms.
    Polyglotic-hq 163's report proposes the fix. The warm switch and the
    band switch are held to their budgets."""

    def run(lab: Lab) -> QWidget:
        tools = learner_tools(learner, heard_dictionary())
        page = WordsPage(tools, None)
        tools.changed.connect(page.learning_changed)
        window = window_with(lab, "words", page)
        lab.time("page_switch_cold", partial(window.go_to, "words"))
        for each in ("home", "words"):
            lab.time(
                "page_switch_warm",
                partial(window.go_to, each),
                budget=budgets.PAGE_SWITCH_WARM,
            )
        no_horizontal_scrollbar(window)
        views = [BY_LEVEL, BY_FREQUENCY]

        def switch_bands() -> None:
            page.first.heard.bands.view.choose(views[0])
            views.reverse()

        lab.time("bands_switch", switch_bands, repeat=4, budget=budgets.CLICK)
        if by_level:
            page.first.heard.bands.view.choose(BY_LEVEL)
        lab.pump()
        return window

    return run


WORDS_MET_GATED = 10_000
"""Words' first show is held to its budget up to this many words met
(polyglotic-hq 212); beyond, recorded."""


def words_met(met: int) -> Callable[[Lab], QWidget]:
    """Words for a made-up learner who has met `met` words (polyglotic-hq
    212), as at the app's start: every word's facts, the bands' sizes and
    every word's text read ahead on the dictionary's thread
    (`LearningTools.prepare`), then Words opened - its first show, a switch
    back, its refresh while shown (words heard while listening: at most
    once a second) and its first search held to their budgets up to
    `WORDS_MET_GATED` words, recorded beyond. Before 212 the first show
    took 126 ms at 10,000 words met and 377 ms at 30,000 on the user's PC;
    before 220 the first search 54-59 ms here at 10,000 (137-162 ms on
    CC-CEDICT). The first show is judged on the median of five fresh
    pages over the same learner (decision 0047): timed once, at 22-26 ms,
    a busy runner put it over 50 ms twice running (polyglotic-hq 234)."""

    def run(lab: Lab) -> QWidget:
        tools = met_learner_tools(met, met_dictionary(met))
        tools.prepare()
        deadline = time.monotonic() + 30
        while not tools.texts_read_ahead and time.monotonic() < deadline:
            lab.pump()  # the dictionary's thread, then the queued hand-backs
            time.sleep(0.005)
        assert tools.texts_read_ahead, "the read ahead never came back"
        shown: list[tuple[WordsPage, MainWindow]] = []

        def fresh() -> Callable[[], object]:
            """A new Words page and window, the last one closed."""
            if shown:
                last, window = shown[-1]
                tools.changed.disconnect(last.learning_changed)
                window.close()
            page = WordsPage(tools, None)
            tools.changed.connect(page.learning_changed)
            shown.append((page, window_with(lab, "words", page)))
            return partial(shown[-1][1].go_to, "words")

        def held(budget: Budget) -> Budget | None:
            return budget if met <= WORDS_MET_GATED else None

        lab.time_fresh("page_switch_cold", fresh, budget=held(budgets.PAGE_SWITCH_COLD))
        page, window = shown[-1]
        for each in ("home", "words"):
            lab.time(
                "page_switch_warm",
                partial(window.go_to, each),
                budget=held(budgets.PAGE_SWITCH_WARM),
            )
        no_horizontal_scrollbar(window)
        lab.time("heard_refresh", page.refresh, repeat=4, budget=held(budgets.SLOT))
        terms = ["sky", "tian", "", "sky"]

        def search() -> None:
            page.first.search.setText(terms[0])
            page.first._searching.stop()
            page.first._refresh_words()  # what the search's pause runs
            terms.append(terms.pop(0))

        lab.time("first_search", search, budget=held(budgets.CLICK))
        lab.time("search", search, repeat=4, budget=held(budgets.CLICK))
        page.first.search.setText("")
        page.first._searching.stop()
        page.first._refresh_words()
        # Show all (300 rows) and Show fewer, in turn (polyglotic-hq 250)
        lab.time(
            "show_all", page.first.words_all.click, repeat=4, budget=held(budgets.CLICK)
        )
        lab.pump()
        return window

    return run


def words_reading(lab: Lab) -> QWidget:
    """Words opened as the app starts, before the read ahead is back
    (polyglotic-hq 220's #338, 229): "Reading your words…" in place of
    the lists, which show when it's back. Its first show is held to a cold
    switch's budget: it reads nothing itself. The read ahead is held on
    its thread until the picture is taken, then let go - so the picture
    is the same every run."""
    met = 1_000
    zh = met_dictionary(met)
    tools = met_learner_tools(met, zh)
    go = threading.Event()
    lab.closing.append(go.set)
    ranks = zh.words_in_ranks

    def held(runs: Sequence[tuple[int, int]]) -> list[int]:
        go.wait(30)  # on the dictionary's thread: the read ahead's first read
        return ranks(runs)

    zh.words_in_ranks = held  # type: ignore[method-assign]
    page = WordsPage(tools, None)
    tools.read_ahead_done.connect(page.learning_changed)  # as main wires it
    tools.prepare()
    window = window_with(lab, "words", page)
    lab.time(
        "page_switch_cold",
        partial(window.go_to, "words"),
        budget=budgets.PAGE_SWITCH_COLD,
    )
    no_horizontal_scrollbar(window)
    assert page.first.reading.isVisible() and not page.first.words.isVisible(), (
        "Words didn't say it's reading"
    )
    assert tools.reading_ahead, "the read ahead came back before the picture"
    return window


def help_learning_set_aside(lab: Lab) -> QWidget:
    """Help's check with captions coming and the learner's learning data
    set aside at the start: what happened, that the words come back, and
    where the old file is - for a report (polyglotic-hq 206)."""
    app = SourceId("app-1")

    def facts() -> Facts:
        now = time.monotonic()
        return Facts(
            now=now,
            connection="listening",
            paused=False,
            overlays_hidden=False,
            ticked=[Ticked(app, "Video Player", "app")],
            activity={app: SourceActivity(now - 300, now - 200, now - 1, now - 2)},
            last_caption=now - 2,
        )

    page = HelpPage(facts, learning_set_aside=lambda: SET_ASIDE)
    window = window_with(lab, "help", page)
    window.go_to("help")
    lab.pump()
    no_horizontal_scrollbar(window)
    return window


STATES = [
    State(f"ui_next.w4_{name}", run, gated=True)
    for name, run in (
        ("words_empty", words_empty),
        ("words_full", words_full),
        ("words_sentences", words_sentences),
        ("words_minimum", words_minimum),
        ("pages_at_floor", at_floor),
        ("words_two_languages", words_two_languages),
        ("words_heard_new", words_heard(NEW_LEARNER)),
        ("words_heard_month", words_heard(MONTH_IN)),
        ("words_heard_heavy", words_heard(HEAVY, by_level=True)),
        ("words_met_1000", words_met(1_000)),
        ("words_met_10000", words_met(10_000)),
        ("words_met_30000", words_met(30_000)),
        ("words_reading", words_reading),
        (
            "learning",
            learning(LearningLanguages("zh"), WordIntroductions.A_FEW),
        ),
        (
            # Chinese and English both open (306), each with its level
            "learning_both_open",
            learning(
                LearningLanguages("zh", ("en",)),
                WordIntroductions.A_FEW,
                running=("zh", "en"),
            ),
        ),
        (
            # English main but not open (its learning data couldn't be: 306);
            # Japanese (basic, its pack not here) and Thai (no dictionary) too
            "learning_several",
            learning(
                LearningLanguages("en", ("zh", "ja", "th")), WordIntroductions.OFF
            ),
        ),
        # the learning window with no end, and of the learner's own size (0144)
        (
            "learning_window_unlimited",
            learning(
                LearningLanguages("zh"),
                WordIntroductions.A_FEW,
                learning_window=UNLIMITED,
            ),
        ),
        (
            "learning_window_custom",
            learning(
                LearningLanguages("zh"), WordIntroductions.A_FEW, learning_window=3000
            ),
        ),
        # a language's dictionary pack (decision 0122): offered, coming,
        # stopped, and on this PC with the list of them
        (
            "learning_pack_offer",
            learning(
                LearningLanguages("zh", ("ru",)),
                WordIntroductions.A_FEW,
                packs={"ru": PackLine(size=13_131_253)},
            ),
        ),
        (
            "learning_japanese_dictionary_missing",
            learning(
                LearningLanguages("zh", ("ja",)),
                WordIntroductions.A_FEW,
                packs={"ja": PackLine(size=42_439_181)},
            ),
        ),
        (
            "learning_japanese_runtime_unavailable",
            learning(
                LearningLanguages("zh", ("ja",)),
                WordIntroductions.A_FEW,
                packs={
                    "ja": PackLine(
                        size=42_439_181,
                        progress=PackProgress(
                            "ja",
                            PackStep.WAITING,
                            0,
                            42_439_181,
                            problem=Problem.SPLIT_UNAVAILABLE,
                        ),
                    )
                },
            ),
        ),
        (  # none in the list held (Vietnamese): no dictionary yet (330)
            "learning_pack_none_yet",
            learning(
                LearningLanguages("zh", ("vi", "ru")),
                WordIntroductions.A_FEW,
                packs={
                    "vi": PackLine(not_offered=True),
                    "ru": PackLine(size=13_131_253),
                },
            ),
        ),
        (  # the list couldn't be read: no promise either way (330's addendum)
            "learning_pack_unchecked",
            learning(
                LearningLanguages("zh", ("ru",)),
                WordIntroductions.A_FEW,
                packs={"ru": PackLine(unlisted=True)},
            ),
        ),
        (
            "learning_pack_downloading",
            learning(
                LearningLanguages("zh", ("ru",)),
                WordIntroductions.A_FEW,
                packs={
                    "ru": PackLine(
                        size=13_131_253,
                        progress=PackProgress(
                            "ru",
                            PackStep.DOWNLOADING,
                            4_500_000,
                            13_131_253,
                            tries=1,
                            seconds_left=140.0,
                        ),
                    )
                },
            ),
        ),
        (
            "learning_pack_failed",
            learning(
                LearningLanguages("zh", ("ru",)),
                WordIntroductions.A_FEW,
                packs={
                    "ru": PackLine(
                        size=13_131_253,
                        progress=PackProgress(
                            "ru",
                            PackStep.DOWNLOADING,
                            4_500_000,
                            13_131_253,
                            problem=Problem.OFFLINE,
                            tries=2,
                            retry_in=25.0,
                        ),
                    )
                },
            ),
        ),
        (
            "learning_pack_installed",
            learning(
                LearningLanguages("zh", ("ru", "es")),
                WordIntroductions.A_FEW,
                packs={
                    "ru": PackLine(
                        installed_version="2026.11.14", installed_size=62_439_424
                    ),
                    "es": PackLine(
                        installed_version="2026.11.14",
                        installed_size=29_500_000,
                        update_size=29_600_000,
                    ),
                },
                installed=(
                    InstalledPackLine("es", "2026.11.14", 29_500_000),
                    InstalledPackLine("ru", "2026.11.14", 62_439_424),
                ),
            ),
        ),
        (  # recorded words come after it: the offer says both sizes (423)
            "learning_pack_offer_recorded",
            learning(
                LearningLanguages("zh", ("es",)),
                WordIntroductions.A_FEW,
                packs={"es": PackLine(size=9_400_000, recorded_offered=29_002_130)},
            ),
        ),
        (
            "learning_pack_recorded",  # its commonest words recorded (418)
            learning(
                LearningLanguages("zh", ("es",)),
                WordIntroductions.A_FEW,
                packs={
                    "es": PackLine(
                        installed_version="2026.11.16",
                        installed_size=29_500_000,
                        recorded_size=30_277_632,
                    )
                },
                installed=(InstalledPackLine("es", "2026.11.16", 59_777_632),),
            ),
        ),
        (
            "learning_built_in_recorded",  # CC-CEDICT's words recorded (424)
            learning(
                LearningLanguages("zh", ("es",)),
                WordIntroductions.A_FEW,
                recorded={
                    "zh": (
                        30_512_640,
                        "Chatterbox Multilingual zh-cmn, built-in voice; MIT",
                    )
                },
            ),
        ),
        ("account_signed_out", account(False)),
        ("account_signed_in", account(True)),
        ("settings", settings("look")),
        ("settings_links", settings("links")),
        ("settings_readings", settings("readings")),
        (
            "settings_readings_japanese_dictionary_missing",
            settings("readings", japanese_readings=JapaneseReadings()),
        ),
        (
            "settings_readings_japanese_runtime_unavailable",
            settings("readings", japanese_readings=JapaneseReadings(supported=False)),
        ),
        (
            "settings_readings_japanese_missing",
            settings("readings", japanese_readings=JapaneseReadings()),
        ),
        (
            "settings_readings_japanese_failed",
            settings("readings", japanese_readings=JapaneseReadings(supported=False)),
        ),
        (
            "settings_readings_japanese_ready",
            settings(
                "readings", japanese_readings=JapaneseReadings(dictionary_here=True)
            ),
        ),
        ("settings_timing", settings("timing")),
        ("settings_speech", settings("speech")),
        ("settings_dictation", settings("dictation")),
        ("settings_hotkeys", settings("hotkeys")),
        (
            "settings_hotkeys_conflict",
            settings("hotkeys", hotkeys_conflict=True),
        ),
        (
            "settings_hotkeys_scrolled",
            settings("hotkeys", roomy_size(), scrolled_into=1),
        ),
        ("settings_app", settings("app")),
        ("settings_app_scrolled", settings("app", scrolled_into=2)),
        (
            "settings_language_restart",
            settings("app", pick_language="de"),
        ),
        ("settings_minimum", settings("look", roomy_size())),
        ("settings_lab", settings("lab")),
        ("help", help_page),
        ("help_learning_set_aside", help_learning_set_aside),
    )
]
