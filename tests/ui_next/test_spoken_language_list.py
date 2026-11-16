"""Every language the speech model hears can be chosen, Detect says how many
it covers, and the list is the same wherever the choice is (polyglotic-hq
317, decision 0108): the order (named last, the learner's own, the rest by
name), finding one by any of its names, made only when first opened, and
the languages named last remembered."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.spoken import (
    RECENT_KEPT,
    SPOKEN_LANGUAGES,
    with_recent,
)
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.languages import (
    detect_short,
    own_name,
    spoken_choice_text,
    spoken_matches,
    spoken_name,
    spoken_order,
)
from polyglotic_desktop.ui_next.panels import LanguagesPanel
from polyglotic_desktop.ui_next.spoken_list import SpokenLanguageList, chip_text
from polyglotic_desktop.ui_next.views.caption_window import (
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.panels import LanguagesView, SessionLanguages
from polyglotic_desktop.ui_next.views.placement import Rect


class Store:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = CaptionWindow(
        "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
        mic=MIC, areas=areas,
    )  # fmt: skip
    shown.resize(960, 300)
    shown.show()
    yield shown
    shown.close()
    shown.deleteLater()


# -- the languages ------------------------------------------------------------------------


def test_the_spoken_languages_are_the_speech_models_thirty_and_dictations() -> None:
    assert len(SPOKEN_LANGUAGES) == 30 == len(set(SPOKEN_LANGUAGES))
    assert DICTATION_LANGUAGES == SPOKEN_LANGUAGES  # one list (317)
    assert "uk" not in SPOKEN_LANGUAGES  # a caption language it can't be told
    assert "zh-hant" not in SPOKEN_LANGUAGES  # a script, not something it hears


def test_every_spoken_language_has_a_name_and_its_own(qapp: QApplication) -> None:
    """Before 317 a line Detect heard in Swedish was labelled "SV"."""
    for code in SPOKEN_LANGUAGES:
        assert spoken_name(code) != code.upper(), code
        assert own_name(code), code
    assert spoken_name("sv") == "Swedish"
    assert spoken_name("zh") == "Mandarin"
    assert spoken_choice_text("ru") == "Russian · Русский"
    assert spoken_choice_text("en") == "English"  # its own name is the same


def test_the_order_is_named_last_then_the_learners_own_then_by_name(
    qapp: QApplication,
) -> None:
    order = spoken_order(SPOKEN_LANGUAGES, recent=("ru", "ja"), own=["zh-hant", "en"])
    assert order[:4] == ["ru", "ja", "zh", "en"]  # Chinese in either script: Mandarin
    rest = [spoken_name(c) for c in order[4:]]
    assert rest == sorted(rest)
    assert sorted(order) == sorted(SPOKEN_LANGUAGES)  # each once


@pytest.mark.parametrize(
    ("typed", "found"),
    [
        ("russ", "ru"),
        ("РУС", "ru"),  # its own name, any case
        ("espanol", "es"),  # without the accent
        ("mandarin", "zh"),
        ("普通", "zh"),
        ("tl", "tl"),  # its code
    ],
)
def test_a_language_is_found_by_any_of_its_names(
    qapp: QApplication, typed: str, found: str
) -> None:
    assert spoken_matches(found, typed)
    assert not spoken_matches("de", typed)


def test_detect_says_how_many_languages_it_covers(qapp: QApplication) -> None:
    assert chip_text(None) == "Detect · 30 languages" == detect_short(30)
    assert chip_text("ru") == "Always Russian"


# -- the list -----------------------------------------------------------------------------


def test_the_list_is_made_only_when_first_opened(qapp: QApplication) -> None:
    """Settings is built at start (314): a list of 31 made then is time
    taken from every start."""
    view = LanguagesView(SessionLanguages())
    panel = LanguagesPanel(view, speech=True)
    assert not panel.spoken.list.built
    panel.spoken.toggle()
    assert panel.spoken.list.built and not panel.spoken.list.isHidden()
    panel.deleteLater()


def test_settings_finds_a_language_as_it_is_typed_and_enter_chooses_it(
    qapp: QApplication,
) -> None:
    view = LanguagesView(SessionLanguages(recent_spoken=("ja",)))
    panel = LanguagesPanel(view, speech=True)
    picker = panel.spoken
    picker.toggle()
    shown = picker.list.codes_shown()
    assert shown[0] == "" and shown[1] == "ja" and len(shown) == 31
    search = picker.list.search
    assert search is not None and picker.list.nothing is not None
    search.setText("рус")
    assert picker.list.codes_shown() == ["ru"]  # Detect and the heading hide too
    search.setText("xyz")
    assert picker.list.codes_shown() == [] and not picker.list.nothing.isHidden()
    search.setText("russ")
    search.returnPressed.emit()
    assert view.value.spoken == "ru" and picker.value() == "ru"
    assert picker.list.isHidden()
    assert picker.chip.text().startswith("Always Russian")
    panel.deleteLater()


def test_the_popover_list_never_takes_the_keyboard(window: CaptionWindow) -> None:
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    assert not popover.spoken_choices.built  # not until opened
    popover.spoken.click()
    assert popover.spoken_choices.search is None  # no box: it would need the keyboard
    items = popover.spoken_choices.items
    assert items is not None and not items.focusPolicy().value


# -- the languages named last -------------------------------------------------------------


def test_the_languages_named_last_newest_first_each_once() -> None:
    assert with_recent((), "ru") == ("ru",)
    assert with_recent(("ru", "ja"), "ja") == ("ja", "ru")
    assert with_recent(("ru",), None) == ("ru",)  # Detect: unchanged
    assert with_recent(("ru",), "uk") == ("ru",)  # not one it hears
    assert with_recent(("Klingon", "ru"), None) == ("ru",)  # a stored oddity goes
    many = with_recent(("a", "ru", "ja", "ko", "th"), "de")
    assert many == ("de", "ru", "ja") and len(many) == RECENT_KEPT


def test_a_window_named_is_remembered_and_first_in_every_list(
    qapp: QApplication,
) -> None:
    store = Store({"targets": ["en"]})
    windows = CaptionWindows(store, MIC, areas)
    windows.set_captioned([("a", APP), ("b", SourceId("app-2"))])
    windows.windows["a"].set_spoken_language("ru")
    windows.windows["b"].set_spoken_language("ja")
    windows.windows["b"].set_spoken_language(None)  # Detect again: kept
    assert windows.recent_spoken() == ("ja", "ru")
    assert windows.windows["a"].recent_spoken() == ("ja", "ru")
    windows.save_now()
    windows.close()
    again = CaptionWindows(store, MIC, areas)
    assert again.recent_spoken() == ("ja", "ru")
    again.close()


def test_stored_recent_languages_read_back_and_odd_ones_left_out() -> None:
    stored = StoredWindows(recent_spoken=("ru", "ja"))
    read = StoredWindows.from_stored(stored.to_stored(), WindowChoices())
    assert read.recent_spoken == ("ru", "ja")
    odd = StoredWindows.from_stored({"recent_spoken": "ru"}, WindowChoices())
    assert odd.recent_spoken == ()
    mixed = {"recent_spoken": ["ru", 3, None, "xx"]}
    assert StoredWindows.from_stored(mixed, WindowChoices()).recent_spoken == ("ru",)


def test_a_standalone_list_has_detect_first_and_every_language(
    qapp: QApplication,
) -> None:
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    found = SpokenLanguageList(holder, searchable=False, own=["en"])
    found.open("ru")
    codes = found.codes_shown()
    assert codes[0] == "" and codes[1] == "en" and len(codes) == 31
    assert found.items is not None
    current = found.items.currentItem()
    assert current is not None and current.text() == "Russian · Русский"
    holder.deleteLater()
