"""English's "a" or "an" before a language's name goes by its first sound
(polyglotic-hq 551: preview 0.1.10-preview.1's sentence card said "Add a
English voice")."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.languages import an_before
from polyglotic_desktop.ui_next.lookup_card import better_voice_steps
from polyglotic_desktop.ui_next.sentence_card import add_voice_text

TRANSLATIONS = Path(__file__).resolve().parents[2] / "translations"


@pytest.mark.parametrize(
    ("name", "an"),
    [
        ("English", True),
        ("Arabic", True),
        ("Italian", True),
        ("Indonesian", True),
        ("Urdu", True),
        ("Ukrainian", False),
        ("Uyghur", False),
        ("French", False),
        ("Hindi", False),
        ("Chinese", False),
        ("", False),
    ],
)
def test_an_goes_by_the_first_sound_not_the_letter(name: str, an: bool) -> None:
    assert an_before(name) is an


def test_the_sentence_card_asks_for_an_english_voice(qapp: QApplication) -> None:
    assert add_voice_text("en") == "Add an English voice"
    assert add_voice_text("ar") == "Add an Arabic voice"
    assert add_voice_text("fr") == "Add a French voice"
    assert add_voice_text("uk") == "Add a Ukrainian voice"
    assert add_voice_text("zh-hant") == "Add a Chinese voice"


def test_the_macs_better_voice_steps_say_an_english_voice(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "then an English voice marked Enhanced" in better_voice_steps("en")
    assert "then an Italian voice marked Enhanced" in better_voice_steps("it")
    assert "then a German voice marked Enhanced" in better_voice_steps("de")


def _translations(path: Path) -> dict[str, str]:
    found = {}
    for message in ET.parse(path).getroot().iter("message"):
        source = message.findtext("source") or ""
        found[source] = message.findtext("translation") or ""
    return found


@pytest.mark.parametrize(
    "a",
    [
        "Add a {language} voice",
        (
            "That was macOS's basic {language} voice. A more natural one is free: "
            "System Settings > Accessibility > Spoken Content > System voice > "
            "Manage Voices, then a {language} voice marked Enhanced or Premium."
        ),
    ],
)
def test_every_language_says_the_an_twin_as_it_says_the_a_one(a: str) -> None:
    """None of the interface's other languages puts a sound-chosen article
    before a name: each says "an English voice" as "a French voice"."""
    an = a.replace(" a {language} voice", " an {language} voice", 1)
    for path in sorted(TRANSLATIONS.glob("polyglotic_*.ts")):
        if path.stem.endswith("_en"):
            continue
        found = _translations(path)
        assert found.get(an) == found.get(a) != "", path.name
