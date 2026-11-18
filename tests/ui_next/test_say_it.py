"""The lookup card's "say it" (polyglotic-hq 286): a pinned card's speaker
says its word in the right voice, at its own pace every time (518); a click
while it speaks stops it, and so does the card closing or another word; R
does the same unless a text field has the keyboard; with no voice it says
so and leads to Windows' speech settings; the app's own sound is handed
to the captions' hush; a screen reader gets the state. A stand-in speaker:
nothing is played."""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from tests.ui_next.test_lookup_view import learner

from polyglotic_desktop.ports.speaker import Ended, Quality, Sounding, Voice
from polyglotic_desktop.ui_next import glyphs
from polyglotic_desktop.ui_next.lookup_card import LookupCard, better_voice_steps
from polyglotic_desktop.ui_next.views.lookup import LookupContext, WordAt
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.speech import (
    MAC_SPEECH_SETTINGS,
    SPEECH_SETTINGS,
    BetterVoice,
)
from polyglotic_desktop.ui_next.word_speech import WordSpeech

AREA = Rect(0, 0, 1920, 1040)
HUIHUI = Voice("zh-cn-1", "Microsoft Huihui", "zh-CN")
HANHAN = Voice("zh-tw-1", "Microsoft Hanhan", "zh-TW")
DAVID = Voice("en-us-1", "Microsoft David", "en-US")


class Speaker:
    """The `Speaker` port, made up: it remembers what it was asked."""

    def __init__(self, voices: tuple[Voice, ...] = (HUIHUI, HANHAN, DAVID)) -> None:
        self.installed = voices
        self.said: list[tuple[str, str, float]] = []
        self.stops = 0
        self.ended: Ended | None = None
        self.sounding: Sounding | None = None

    def voices(self) -> tuple[Voice, ...]:
        return self.installed

    def say(
        self, text: str, voice: Voice, rate: float, sounding: Sounding, ended: Ended
    ) -> None:
        self.said.append((text, voice.id, rate))
        self.sounding, self.ended = sounding, ended

    def stop(self) -> None:
        self.stops += 1


class Opened:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> None:
        self.urls.append(url)


@pytest.fixture
def speaker() -> Speaker:
    return Speaker()


@pytest.fixture
def opened() -> Opened:
    return Opened()


@pytest.fixture
def hushed() -> list[tuple[float, float]]:
    return []


@pytest.fixture
def shown(
    qapp: QApplication,
    speaker: Speaker,
    opened: Opened,
    hushed: list[tuple[float, float]],
) -> Iterator[LookupCard]:
    made = LookupCard(learner())
    speech = WordSpeech(
        speaker, hush=lambda s, n: hushed.append((s, n)), open_url=opened
    )
    made.use_speech(speech)
    yield made
    made.close_card()
    made.close()
    made.deleteLater()
    speech.deleteLater()
    qapp.processEvents()


def pin(card: LookupCard, word: str) -> None:
    at = Rect(900, 600, 40, 30)
    context = LookupContext(f"我的{word}坏了")
    card.pin(
        WordAt(
            word,
            context,
            (2, 2 + len(word)),
            at,
            Rect(500, 600, 900, 30),
            AREA,
            (1, 0, 0, len(word)),
        )
    )


def glyph(card: LookupCard) -> glyphs.Glyph | None:
    return next((g for g, _, _ in card._painted.glyphs), None)


def has(card: LookupCard, hit: str) -> bool:
    return any(h == hit for _, h in card._hits)


def finish(qapp: QApplication, speaker: Speaker) -> None:
    """The speaker says the word was heard to its end (from its thread)."""
    assert speaker.ended is not None
    speaker.ended(True)
    qapp.processEvents()  # the queued signal


def test_a_pinned_card_says_its_word_and_a_hover_card_has_no_button(
    qapp: QApplication, shown: LookupCard, speaker: Speaker
) -> None:
    shown.model.show("电脑", LookupContext("电脑"), pinned=False)
    assert shown._saying(shown.model.card()) is None  # hover: no actions
    pin(shown, "电脑")
    assert has(shown, "say") and glyph(shown) is glyphs.Glyph.SPEAKER
    assert shown.tip("say") == "Say it (R)"
    shown.do("say")
    assert speaker.said == [("电脑", "zh-cn-1", 1.0)]
    assert glyph(shown) is glyphs.Glyph.SPEAKING and shown.tip("say") == "Stop (R)"
    finish(qapp, speaker)
    assert glyph(shown) is glyphs.Glyph.SPEAKER
    assert shown.tip("say") == "Say it (R)"
    shown.do("say")  # every time at its own pace, never slower (518)
    finish(qapp, speaker)
    shown.do("say")
    assert speaker.said == [("电脑", "zh-cn-1", 1.0)] * 3
    assert shown.tip("say") == "Stop (R)"


def test_a_click_while_it_speaks_stops_it(
    qapp: QApplication, shown: LookupCard, speaker: Speaker
) -> None:
    pin(shown, "电脑")
    shown.do("say")
    shown.do("say")
    assert len(speaker.said) == 1 and speaker.stops >= 1
    assert glyph(shown) is glyphs.Glyph.SPEAKER
    finish(qapp, speaker)  # its late "ended" changes nothing
    assert glyph(shown) is glyphs.Glyph.SPEAKER


def test_a_traditional_form_is_said_by_taiwans_voice(
    shown: LookupCard, speaker: Speaker
) -> None:
    pin(shown, "電腦")
    shown.do("say")
    assert speaker.said == [("電腦", "zh-tw-1", 1.0)]


def test_closing_the_card_or_another_word_stops_it(
    shown: LookupCard, speaker: Speaker
) -> None:
    pin(shown, "电脑")
    shown.do("say")
    stops = speaker.stops
    shown.close_card()  # the tile closed mid-word
    assert speaker.stops == stops + 1
    pin(shown, "电脑")
    shown.do("say")
    pin(shown, "电")  # another word pinned
    assert speaker.stops == stops + 2
    shown.do("say")
    assert speaker.said[-1][2] == 1.0  # a new word starts at its own pace


def test_the_apps_own_sound_is_handed_to_the_captions_hush(
    shown: LookupCard, speaker: Speaker, hushed: list[tuple[float, float]]
) -> None:
    pin(shown, "电脑")
    shown.do("say")
    assert speaker.sounding is not None
    speaker.sounding(123.0, 0.5)  # from the speaker's thread, as the sound starts
    assert hushed == [(123.0, 0.5)]


def test_no_voice_says_so_and_leads_to_windows_speech_settings(
    qapp: QApplication,
    opened: Opened,
    hushed: list[tuple[float, float]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")  # Windows' words (a Mac's: below)
    english_only = Speaker((DAVID,))  # a Chinese learner on an English Windows
    card = LookupCard(learner())
    card.use_speech(WordSpeech(english_only, open_url=opened, parent=card))
    try:
        pin(card, "电脑")
        assert glyph(card) is glyphs.Glyph.NO_VOICE and has(card, "say")
        assert card.tip("say") == "No Chinese voice on this PC"
        assert card.accessibleDescription() == "No Chinese voice on this PC"
        assert not has(card, "add_voice")
        card.do("say")  # never a dead button: how Windows adds one
        texts = [b.layout.text() for b in card._painted.blocks]
        assert any(
            "Settings > Time & language > Speech > Add voices" in t for t in texts
        )
        assert has(card, "add_voice") and english_only.said == []
        card.do("add_voice")
        assert opened.urls == [SPEECH_SETTINGS] == ["ms-settings:speech"]
        english_only.installed = (DAVID, HUIHUI)  # a voice added meanwhile
        card._render()
        assert glyph(card) is glyphs.Glyph.SPEAKER and not has(card, "add_voice")
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        qapp.processEvents()


def test_on_a_mac_no_voice_leads_to_spoken_content(
    qapp: QApplication, opened: Opened, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Mac's words and its System Settings page (polyglotic-hq 428)."""
    monkeypatch.setattr(sys, "platform", "darwin")
    english_only = Speaker((DAVID,))
    card = LookupCard(learner())
    card.use_speech(WordSpeech(english_only, open_url=opened, parent=card))
    try:
        pin(card, "电脑")
        assert card.tip("say") == "No Chinese voice on this Mac"
        card.do("say")
        texts = [b.layout.text() for b in card._painted.blocks]
        assert any("Spoken Content > System voice > Manage Voices" in t for t in texts)
        assert card.tip("add_voice") == "Opens System Settings, where voices are added"
        card.do("add_voice")
        assert opened.urls == [MAC_SPEECH_SETTINGS]
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        qapp.processEvents()


def test_a_voice_added_while_the_card_shows_is_found_shortly(
    qapp: QApplication, opened: Opened
) -> None:
    english_only = Speaker((DAVID,))
    card = LookupCard(learner())
    speech = WordSpeech(english_only, open_url=opened, parent=card)
    card.use_speech(speech)
    try:
        pin(card, "电脑")
        assert speech._recheck.isActive()  # asked again shortly
        english_only.installed = (DAVID, HUIHUI)
        speech._recheck.timeout.emit()
        qapp.processEvents()
        assert glyph(card) is glyphs.Glyph.SPEAKER
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        qapp.processEvents()


def press_r(target: QWidget) -> bool:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier, "r"
    )
    return QApplication.sendEvent(target, event)


def test_r_says_it_unless_a_text_field_has_the_keyboard(
    qapp: QApplication,
    shown: LookupCard,
    speaker: Speaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = QWidget()  # the Words page, say
    field = QLineEdit(page)
    try:
        pin(shown, "电脑")
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: page))
        press_r(page)
        assert speaker.said == [("电脑", "zh-cn-1", 1.0)]
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: field))
        press_r(field)  # typing an "r" in a search box
        assert len(speaker.said) == 1 and field.text() == "r"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_a_screen_reader_gets_the_word_and_what_its_speaker_does(
    shown: LookupCard,
) -> None:
    pin(shown, "电脑")
    assert shown.accessibleName() == "电脑"
    assert shown.accessibleDescription() == "Say it (R)"
    shown.do("say")
    assert shown.accessibleDescription() == "Stop (R)"


def test_without_speech_wired_the_card_is_as_it_was(qapp: QApplication) -> None:
    card = LookupCard(learner())
    try:
        pin(card, "电脑")
        assert not has(card, "say") and card._painted.glyphs == []
        assert card.accessibleDescription() == ""
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        qapp.processEvents()


TINGTING = Voice("compact.zh-CN.Tingting", "Tingting", "zh-CN", Quality.BASIC)
"""A Mac's compact Chinese voice (polyglotic-hq 515's Mac)."""


def test_a_basic_voice_brings_the_better_voice_notice_until_silenced(
    qapp: QApplication,
) -> None:
    """518: each time the word plays in a basic voice the card says how to
    add a better one, with "Don't show again" and Dismiss; ticked and
    dismissed, never again for the language."""
    quiet: list[str] = []
    speaker = Speaker((TINGTING, DAVID))
    speech = WordSpeech(
        speaker, open_url=Opened(), better=BetterVoice(lambda: quiet, quiet.append)
    )
    card = LookupCard(learner())
    card.use_speech(speech)
    try:
        pin(card, "电脑")
        assert not has(card, "voice_dismiss")
        card.do("say")
        assert speaker.said == [("电脑", TINGTING.id, 1.0)]
        assert has(card, "voice_never") and has(card, "voice_dismiss")
        steps = [t.text for t in card._painted.texts]
        assert better_voice_steps("zh") in steps  # where a Mac adds a better one
        card.do("voice_dismiss")  # not ticked: gone for now only
        assert not has(card, "voice_dismiss") and quiet == []
        finish(qapp, speaker)
        card.do("say")  # every time it plays
        assert has(card, "voice_dismiss")
        card.do("voice_never")
        assert any("☑" in run.text for run in card._painted.runs)
        card.do("voice_dismiss")
        assert quiet == ["zh"] and not has(card, "voice_dismiss")
        finish(qapp, speaker)
        card.do("say")
        assert len(speaker.said) == 3 and not has(card, "voice_dismiss")
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        speech.deleteLater()
        qapp.processEvents()


def test_a_good_voice_or_a_recording_brings_no_notice(qapp: QApplication) -> None:
    """518: Windows' voices are the best it lets apps use; a recording is
    ours - neither brings the notice."""
    speaker = Speaker((HUIHUI, DAVID))
    speech = WordSpeech(
        speaker, open_url=Opened(), better=BetterVoice(lambda: (), lambda _l: None)
    )
    card = LookupCard(learner())
    card.use_speech(speech)
    try:
        pin(card, "电脑")
        card.do("say")
        assert speaker.said and not has(card, "voice_dismiss")
    finally:
        card.close_card()
        card.close()
        card.deleteLater()
        speech.deleteLater()
        qapp.processEvents()
