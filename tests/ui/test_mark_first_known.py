"""Learning's "Mark the most common words known", Undo and Reset, in the
app (polyglotic-hq 342): the card offers only numbers past the line, a
mark moves the line and offers Undo, Reset asks first with how many words
it changes and is kept in the settings. Offscreen, the sample dictionary."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.learning.first_known import Before
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ui_next.learning_page import LanguageCardView


@pytest.fixture
def built(qapp: QApplication) -> Iterator[Built]:
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    built.hub.window.go_to("learning")
    yield built
    built.close()


def card(built: Built) -> LanguageCardView:
    found = built.hub.learning.card("zh")
    assert found is not None
    return found


def mark(built: Built, first: int) -> None:
    view = card(built)
    assert view.first is not None and view.mark_known is not None
    at = view.first.findData(first)
    if at < 0:  # another number
        assert view.first_number is not None
        view.first.setCurrentIndex(view.first.findData(0))
        view.first.activated.emit(view.first.currentIndex())
        view.first_number.setValue(first)
    else:
        view.first.setCurrentIndex(at)
        view.first.activated.emit(at)
    assert view.mark_known.isEnabled()
    view.mark_known.click()


def test_only_numbers_past_the_line_are_offered(built: Built) -> None:
    view = card(built)
    assert view.first is not None and view.first_number is not None
    # no level set: estimated at HSK 3, about 1,000 words
    offered = [view.first.itemData(i) for i in range(view.first.count())]
    assert offered == [2000, 3000, 5000, 10000, 0]  # 0: another number
    assert view.first_number.isHidden()
    view.first.setCurrentIndex(view.first.findData(0))
    view.first.activated.emit(view.first.currentIndex())
    assert not view.first_number.isHidden()
    view.first_number.setValue(800)  # already known: nothing to mark
    assert view.mark_known is not None and not view.mark_known.isEnabled()
    assert view.undo_known is None and view.reset_known is None


def test_a_mark_moves_the_line_and_undo_takes_it_back(built: Built) -> None:
    vocabulary = built.desktop.tools.vocabulary  # type: ignore[union-attr]
    settings = built.desktop.settings
    mark(built, 3000)
    assert vocabulary.line == KnownLine.words(3000)
    assert settings.value.reset_point("zh") == Before(None)
    view = card(built)  # shown again, with Undo
    assert view.undo_known is not None and view.reset_known is not None
    assert "2,000 more words" in _texts(view)
    assert "Not set yet" in _texts(view) and ".." not in _texts(view)
    view.undo_known.click()
    assert vocabulary.line is None  # back to none set
    assert settings.value.reset_point("zh") is None
    view = card(built)
    assert view.undo_known is None and view.reset_known is None


def test_reset_asks_with_how_many_words_and_keeps_hand_marks(built: Built) -> None:
    tools = built.desktop.tools
    assert tools is not None
    vocabulary = tools.vocabulary
    vocabulary.set_known_words(500)
    computer = tools.lookup("电脑")[0].entry_id
    vocabulary.set_status(computer, WordStatus.NEW)  # their own mark
    mark(built, 2000)
    mark(built, 2500)  # a number typed
    assert vocabulary.line == KnownLine.words(2500)
    view = card(built)
    assert view.undo_known is not None
    view.undo_known.click()  # one step: back to 2,000, Reset still offered
    assert vocabulary.line == KnownLine.words(2000)
    asked: list[tuple[str, str]] = []
    answer = False

    def ask(title: str, said: str) -> bool:
        asked.append((title, said))
        return answer

    built.hub.ask_reset = ask
    view = card(built)
    assert view.reset_known is not None
    view.reset_known.click()
    assert vocabulary.line == KnownLine.words(2000)  # Cancel: nothing changed
    title, said = asked[-1]
    assert "Reset Chinese" in title
    assert "About 1,500 words" in said and "500 of the most common" in said
    answer = True
    card(built).reset_known.click()  # type: ignore[union-attr]
    assert vocabulary.line == KnownLine.words(500)
    assert vocabulary.status_of_entry(computer).status is WordStatus.NEW
    assert built.desktop.settings.value.reset_point("zh") is None
    assert card(built).reset_known is None


def test_reset_is_kept_after_a_restart(qapp: QApplication) -> None:
    store = MemorySettingsStore({"learning": "zh"})
    built = Built(store, tools=True)
    try:
        mark(built, 5000)
    finally:
        built.close()
    again = Built(store, tools=True)
    try:
        view = card(again)
        assert view.undo_known is None  # this session's only
        assert view.reset_known is not None  # kept
    finally:
        again.close()


def _texts(view: LanguageCardView) -> str:
    from PySide6.QtWidgets import QLabel

    return " ".join(label.text() for label in view.findChildren(QLabel))


def test_a_level_chosen_in_the_picker_ends_undo_and_reset(
    built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The picker says the level another way: what Reset would go back to
    no longer means anything."""
    from polyglotic_desktop import main

    mark(built, 5000)
    assert card(built).reset_known is not None
    monkeypatch.setattr(main.LevelPicker, "exec", lambda self: 1)
    monkeypatch.setattr(main.LevelPicker, "known", lambda self: 2000)
    built.hub.change_level("zh")
    vocabulary = built.desktop.tools.vocabulary  # type: ignore[union-attr]
    assert vocabulary.line == KnownLine.words(2000)
    assert built.desktop.settings.value.reset_point("zh") is None
    view = card(built)
    assert view.undo_known is None and view.reset_known is None
