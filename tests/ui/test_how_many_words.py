"""About how many words do you know? (polyglotic-hq 323): the one question
a language asks when it's added on Learning, and what Change your level
asks after - a few choices in words, an HSK level beside each for Chinese,
"Not sure" a middle one. Offscreen."""

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QRadioButton
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import KnownLine, LinkChoice
from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.ui.level_picker import LevelPicker
from polyglotic_desktop.ui.settings import AppSettings, learning_changes
from polyglotic_desktop.ui_next.views import known_words
from polyglotic_desktop.ui_next.views.known_words import Choice
from polyglotic_desktop.ui_next.views.words import level_line

# -- the choices ---------------------------------------------------------------------


def test_chinese_choices_are_hsk_levels_said_in_words() -> None:
    offered = known_words.choices("zh")
    assert offered[0] == Choice(0)  # just starting
    assert [(c.known, c.level) for c in offered[1:]] == [
        (300, "1"), (500, "2"), (1000, "3"), (2000, "4"),
        (3600, "5"), (5400, "6"), (11000, "7-9"),
    ]  # fmt: skip
    assert known_words.not_sure("zh") == 1000  # HSK 3: the middle, as before


def test_english_choices_are_round_numbers() -> None:
    offered = known_words.choices("en")
    assert [c.known for c in offered] == [0, 500, 1000, 2000, 3000, 5000, 8000, 12000]
    assert [c.or_more for c in offered][-2:] == [False, True]
    assert all(not c.level for c in offered)
    assert known_words.not_sure("en") == 3000


@pytest.mark.parametrize(
    ("scheme", "words"),
    [
        ("hsk-2025", [0, 300, 500, 1000, 2000, 3600, 5400, 11000]),
        ("en-frequency", [0, 1000, 2000, 3000, 5000, 8000, 12000, 20000]),
        ("hsk-2021", [0, 500, 1239, 2190, 3157, 4209, 5327, 10896]),
    ],
)
def test_a_level_kept_before_323_is_said_in_words(
    scheme: str, words: list[int]
) -> None:
    """The mapping for existing learners: each level they could have
    picked, as about how many words it holds."""
    lines = [KnownLine.picked(Level(scheme, n)) for n in range(8)]
    assert [known_words.words_known(line) for line in lines] == words


def test_the_picker_opens_on_the_choice_nearest_the_level_now() -> None:
    zh, en = known_words.choices("zh"), known_words.choices("en")
    assert known_words.opens_on(zh, None) is None  # "Not sure"
    hsk3 = KnownLine.picked(Level("hsk-2025", 3))
    assert zh[known_words.opens_on(zh, hsk3) or 0].known == 1000
    band = [KnownLine.picked(Level("en-frequency", n)) for n in range(8)]
    assert [en[known_words.opens_on(en, line) or 0].known for line in band] == [
        0, 1000, 2000, 3000, 5000, 8000, 12000, 12000,
    ]  # fmt: skip
    old = [KnownLine.picked(Level("hsk-2021", n)) for n in range(8)]
    assert [zh[known_words.opens_on(zh, line) or 0].known for line in old] == [
        0, 500, 1000, 2000, 3600, 3600, 5400, 11000,
    ]  # fmt: skip
    assert zh[known_words.opens_on(zh, KnownLine.words(2500)) or 0].known == 2000
    assert known_words.opens_on(zh, KnownLine("from-a-newer-version", 2)) is None


def test_a_line_in_words_is_said_in_words() -> None:
    assert level_line(KnownLine.words(3000)).words == 3000
    assert level_line(KnownLine.words(0)).words == 0
    assert level_line(KnownLine.picked(Level("hsk-2025", 3))).words is None  # as it was


# -- the picker ----------------------------------------------------------------------


def picker_for(code: str, line: KnownLine | None) -> LevelPicker:
    offered = known_words.choices(code)
    return LevelPicker(
        "Chinese" if code == "zh" else "English",
        offered,
        known_words.not_sure(code),
        known_words.opens_on(offered, line),
    )


def test_the_picker_asks_one_question_in_words(qapp: QApplication) -> None:
    picker = picker_for("zh", None)
    texts = [b.text() for b in picker.findChildren(QRadioButton)]
    assert texts == [
        "I'm just starting",
        "About 300 - HSK 1",
        "About 500 - HSK 2",
        "About 1,000 - HSK 3",
        "About 2,000 - HSK 4",
        "About 3,600 - HSK 5",
        "About 5,400 - HSK 6",
        "About 11,000 - HSK 7-9",
        "Not sure - start at about 1,000",
    ]
    assert any(
        "Chinese words do you know" in w.text() for w in picker.findChildren(QLabel)
    )
    assert picker.not_sure.isChecked() and picker.known() == 1000  # no level yet
    picker.choose(4)
    assert picker.known() == 2000
    picker.deleteLater()
    english = picker_for("en", KnownLine.words(5000))
    texts = [b.text() for b in english.findChildren(QRadioButton)]
    assert texts[1:4] == ["About 500", "About 1,000", "About 2,000"]
    assert texts[-2:] == ["12,000 or more", "Not sure - start at about 3,000"]
    assert english.known() == 5000  # opens on the level now
    english.deleteLater()


# -- asked once, when a language is added ------------------------------------------------


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    """The picker answered without showing it: each `exec` takes the next
    answer - a number of words chosen then OK, or None for Cancel - and
    is counted in `asked`."""
    queue: list[int | None] = []

    def exec_(dialog: LevelPicker) -> int:
        answer = queue.pop(0)
        if answer is None:
            return 0
        choice = dialog.findChild(QRadioButton, f"level.{answer}")
        assert choice is not None
        choice.setChecked(True)
        return 1

    monkeypatch.setattr(LevelPicker, "exec", exec_)
    return queue


def test_adding_the_language_in_use_asks_how_many_words_once(
    qapp: QApplication, answers: list[int | None]
) -> None:
    """No language chosen yet (the first run asks none): choosing the one
    whose dictionary is in use asks about how many words, and the answer is
    the line. Before 323 nothing was asked; Home's line waited."""
    store = MemorySettingsStore()
    built = Built(store, tools=True)
    tools = built.desktop.tools
    assert tools is not None and tools.vocabulary.line is None
    answers.append(2000)
    built.hub.learning.languages_wanted.emit(LearningLanguages().added(tools.language))
    assert answers == []  # asked
    assert tools.vocabulary.line == KnownLine.words(2000)
    assert store.values["learning"] == tools.language
    # and every word of it is linked (polyglotic-hq 555; past what's known
    # from 323 until then)
    assert built.desktop.settings.value.choices_for(tools.language).links is (
        LinkChoice.EVERY
    )
    assert tools.choices.links is LinkChoice.EVERY
    # another language added: nothing asked (no level of its own to set here)
    languages = built.desktop.settings.value.learning_languages
    built.hub.learning.languages_wanted.emit(languages.added("vi"))
    assert built.desktop.settings.value.choices_for("vi").links is LinkChoice.EVERY
    assert "vi" not in built.desktop.settings.value.language_choices  # none written
    built.close()


def test_a_skipped_question_leaves_the_level_unset(
    qapp: QApplication, answers: list[int | None]
) -> None:
    built = Built(MemorySettingsStore(), tools=True)
    tools = built.desktop.tools
    assert tools is not None
    answers.append(None)  # Cancel: skipped
    built.hub.learning.languages_wanted.emit(LearningLanguages().added(tools.language))
    assert answers == [] and tools.vocabulary.line is None
    assert not built.hub.home.level_line.isHidden()  # Home's line still offers it
    built.close()


def test_change_your_level_opens_on_the_level_now_and_makes_it_words(
    qapp: QApplication, answers: list[int | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A learner at HSK 3 from before 323: the picker opens on "About 1,000
    - HSK 3"; OK without touching it makes the same line one in words."""
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    tools = built.desktop.tools
    assert tools is not None and tools.language == "zh"
    tools.vocabulary.set_level(Level("hsk-2025", 3))
    opened: list[int] = []
    accept = LevelPicker.exec

    def exec_(dialog: LevelPicker) -> int:
        opened.append(dialog.known())
        return accept(dialog)

    monkeypatch.setattr(LevelPicker, "exec", exec_)
    answers.append(1000)
    built.hub.change_level()
    assert opened == [1000]
    assert tools.vocabulary.line == KnownLine.words(1000)
    built.close()


def test_a_language_added_links_every_word() -> None:
    """A language added writes no choice of links for it: every word is
    linked, as in a language learned before (polyglotic-hq 555; 323 wrote
    "past what you know" for each language added until then). One stopped
    and added again keeps the choice it had."""
    value = AppSettings.from_stored({"learning": "zh", "also_learning": ["ja"]})
    changes = learning_changes(value.learning_languages.added("vi"))
    assert "language_choices" not in changes
    kept = AppSettings.from_stored(
        {"learning": "zh", "language_choices": {"ko": {"links": "off"}}}
    )
    again = learning_changes(kept.learning_languages.added("ko"))
    assert "language_choices" not in again
    assert kept.choices_for("ko").links is LinkChoice.OFF


def test_the_choices_scroll_on_the_dialogs_own_background(qapp: QApplication) -> None:
    """Its choices are in a scroll area for a short screen (polyglotic-hq
    524), which paints nothing of its own: Qt's `setWidget` turns the
    choices' background on, and a dark theme's light text sat on Qt's
    light grey (the UI lab's contrast check, 1.03:1)."""
    picker = picker_for("zh", None)
    holder = picker.choices.widget()
    assert holder is not None and not holder.autoFillBackground()
    assert not picker.choices.viewport().autoFillBackground()
    assert len(holder.findChildren(QRadioButton)) == 9
    picker.deleteLater()
