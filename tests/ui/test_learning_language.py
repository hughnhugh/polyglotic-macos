"""The language being learned: never asked at the first run - the app opens
for anyone (polyglotic-hq 293, decision 0085) - and chosen on Learning,
from the next start; until then the dictionary in use is a guess from
Windows' display languages, and new settings translate into the first of
them captions are translated into. Each language keeps its own learning
data. Offscreen."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tests.ui.fakes import Built, MemorySettingsStore
from tests.ui.first_run_script import Built as FirstRunBuilt
from tests.ui.test_check_install import sample_dictionaries
from tools.i18n import extract

from polyglotic_desktop import main
from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.core.shared import papers
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.learning import StoredLevel
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui.widgets import TextDialog
from polyglotic_desktop.ui_next.languages import caption_language_of, own_targets

AT = datetime(2026, 11, 16, 9, tzinfo=UTC)
AGREED = ConsentChoice(
    "a", AT, False, False, False, Agreement(papers.TESTER_AGREEMENT_VERSION, AT)
)


def test_the_choice_is_read_leniently() -> None:
    assert AppSettings().learning is None  # not chosen yet
    assert AppSettings.from_stored({"learning": "en"}).learning == "en"
    assert AppSettings.from_stored({"learning": "fr"}).learning is None
    assert AppSettings.from_stored({"learning": 3}).learning is None


def started(
    monkeypatch: pytest.MonkeyPatch,
    store: MemorySettingsStore,
    windows: list[str],
    kept: tuple[str, ...] = (),
) -> str:
    """The first run on a PC whose display languages are `windows`, with
    learning data kept for `kept` (agreed and signed in before): the
    language whose tools it built. Nothing may be asked."""
    asked: list[str] = []

    def exec_(dialog: TextDialog) -> int:
        asked.append(type(dialog).__name__)
        return 0

    monkeypatch.setattr(TextDialog, "exec", exec_)
    run = main.first_run(
        store,
        FirstRunBuilt(),
        AGREED,
        None,
        windows_languages=windows,
        kept=lambda c: c in kept,
    )
    assert asked == []  # no language, no level (293)
    return "zh" if run.tools.is_chinese else "en"


def targets(store: MemorySettingsStore) -> tuple[str, ...]:
    return AppSettings.from_stored(store.values).targets


@pytest.mark.parametrize(
    ("windows", "translated", "learned"),
    [
        (["en-AU"], ("en",), "zh"),
        (["zh-Hans-CN", "en-US"], ("zh",), "en"),
        (["zh-Hant-TW"], ("zh-hant",), "en"),
        (["ja-JP"], ("ja",), "en"),
        (["mn-MN", "fr-FR"], ("fr",), "en"),  # Mongolian isn't offered (#40)
        (["sw-KE"], ("en",), "en"),  # no translation into Swahili: English
        ([], ("en",), "en"),
    ],
)
def test_the_first_run_asks_no_language_and_starts_from_windows(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    windows: list[str],
    translated: tuple[str, ...],
    learned: str,
) -> None:
    """polyglotic-hq 293 (the user, 2026-11-11: "Keep that in the main app
    configuration rather than a prerequisite step to entering the app"):
    "Translate into" is the PC's own language where captions are
    translated into it, else English; the spoken language is Detect; the
    dictionary is a guess - and no language is saved as learned."""
    store = MemorySettingsStore()
    assert started(monkeypatch, store, windows) == learned
    assert targets(store) == translated
    assert AppSettings.from_stored(store.values).spoken_language is None  # Detect
    assert store.values.get("learning") is None
    assert started(monkeypatch, store, windows) == learned  # the same next time
    assert targets(store) == translated


def test_saved_settings_are_kept_and_no_new_screen_asked(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install from before keeps every choice: the language learned and
    "Translate into" - even as it came, once anything was saved."""
    store = MemorySettingsStore({"learning": "zh", "targets": ["vi"]})
    assert started(monkeypatch, store, ["ja-JP"]) == "zh"
    assert targets(store) == ("vi",)
    store = MemorySettingsStore({"targets": ["en"], "theme": "glaze"})
    assert started(monkeypatch, store, ["zh-Hans-CN"]) == "en"
    assert targets(store) == ("en",)  # saved before: not the PC's


def test_an_install_from_before_with_no_language_keeps_its_words_in_view(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chinese ran until a language was chosen, and the first run asked
    again each start: on a Japanese PC its Chinese words stay in view."""
    store = MemorySettingsStore({"targets": ["ja"]})
    assert started(monkeypatch, store, ["ja-JP"], kept=("zh",)) == "zh"


def test_windows_languages_are_read_as_caption_languages() -> None:
    assert caption_language_of("en-AU") == "en"
    assert caption_language_of("zh-Hans-SG") == "zh"
    assert caption_language_of("zh-HK") == caption_language_of("zh-Hant-TW")
    assert caption_language_of("zh-Hant-TW") == "zh-hant"
    assert caption_language_of("fil-PH") == "tl"
    assert caption_language_of("pt_BR") == "pt"
    assert caption_language_of("mn-MN") is None  # taken off (#40)
    assert own_targets(["en-AU", "en-GB", "ja-JP", "sw"]) == ["en", "ja"]


def test_learning_switches_it_for_next_time(qapp: QApplication) -> None:
    """On Learning (polyglotic-hq 262; it was Home's Languages panel): English
    learned too, then used instead - from the next start, Chinese still
    learned and keeping its words."""
    store = MemorySettingsStore({"learning": "zh"})
    built = Built(store)
    page = built.hub.learning
    assert [c.code for c in page.cards] == ["zh"]
    page.choices.setCurrentIndex(page.choices.findData("en"))
    page.add.click()
    assert store.values["also_learning"] == ["en"]
    english = page.card("en")
    assert english is not None and english.switch is not None
    english.switch.click()
    assert store.values["learning"] == "en"
    assert store.values["also_learning"] == ["zh"]
    built.close()


def test_with_none_chosen_learning_says_so_and_offers_every_language(
    qapp: QApplication,
) -> None:
    """Where the language is chosen now (293): Learning, with none yet, says
    so and offers them; a full dictionary picked is the one learned."""
    store = MemorySettingsStore()
    built = Built(store)
    page = built.hub.learning
    assert page.cards == [] and not page.none_yet.isHidden()
    assert page.choices.findData("ja") >= 0 and page.choices.findData("zh") >= 0
    page.choices.setCurrentIndex(page.choices.findData("zh"))
    page.add.click()
    assert store.values["learning"] == "zh"
    built.close()


def test_each_language_keeps_its_own_learning_data(tmp_path: Path) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    main.learner_tools(folder, False, data)
    main.learner_tools(folder, True, data)
    assert sorted(p.name for p in data.glob("*.sqlite")) == [
        "learning-en.sqlite",
        "learning.sqlite",
    ]


def test_the_learning_store_is_handed_back_and_closes_after_its_writes(
    tmp_path: Path,
) -> None:
    """117 Low 11: `main` keeps the store it opened and closes it at the end
    (`stop`, last), not at finalisation: every write queued is in the file,
    and the file is let go - Windows can't move one still open."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    _, store = main.learner_tools(folder, False, data)
    store.save_level(StoredLevel("hsk-2025", 2.5))  # queued just before the end
    store.close()
    moved = (data / "learning.sqlite").rename(data / "moved.sqlite")
    again = SqliteLearningStore(moved)
    assert again.load().level == StoredLevel("hsk-2025", 2.5)
    again.close()


# -- no "captioned less accurately" line (the user, 2026-11-13) ----------------


def says_less_accurate(widget: QWidget) -> bool:
    """A line on `widget` says some spoken language is captioned less
    accurately."""
    return any("less accurate" in label.text() for label in widget.findChildren(QLabel))


def test_no_line_says_a_spoken_language_is_captioned_less_accurately(
    qapp: QApplication,
) -> None:
    """The user, 2026-11-13 (their feedback's item 20): "Remove the line
    'Cantonese and Vietnamese is captioned less accurately' in the
    detect-language section and anywhere else" - Settings > Captions'
    Spoken language said it, and so did a caption window's settings, and
    Help's "Which languages work best?" in other words."""
    built = Built()
    assert not says_less_accurate(built.hub.settings.speech)  # Settings > Captions
    built.close()
    said = [m.source for m in extract.read().messages if "accurate" in m.source]
    assert said == []  # nor anywhere else the interface could show it
