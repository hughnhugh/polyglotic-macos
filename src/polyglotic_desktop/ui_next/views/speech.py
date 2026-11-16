"""Hearing a looked-up word, as plain Python (polyglotic-hq 286, decision
0077): the language the lookup card's word is said in, the voice that says
it, and what its button shows.

- **The word's language decides the voice,** never the interface's: a
  Chinese word in Chinese (Taiwan's voice first for a traditional form,
  the mainland's for a simplified one - never Hong Kong's, which speaks
  Cantonese), an English word in English, a basic dictionary's word in its
  language, a word in a row with no dictionary in that row's language.
- **Which voice of several:** the language's usual region first (`REGIONS`:
  en-US before en-GB, pt-BR before pt-PT...), then any region of the
  language; within one, Windows' own order.
- **The button:** ready, speaking, or no voice for the language - never a
  dead button: no voice says so, and how Windows adds one.
- **The pace:** the voice's own the first time a word is said; a second
  click, once it has finished, says it slower (`SLOWER`), and so on in
  turn - the learner hears it as spoken, then slowly.
"""

from enum import StrEnum

from polyglotic_desktop.core.lexicon.chinese import has_han
from polyglotic_desktop.ports.speaker import Voice
from polyglotic_desktop.ui_next.views.lookup import Card

NORMAL = 1.0
"""The voice's own pace."""
SLOWER = 0.7
"""A learner's pace: a word takes about 40% longer (Windows' voices,
2026-11-11)."""
SPEECH_SETTINGS = "ms-settings:speech"
"""Windows' Settings > Time & language > Speech, where Manage voices > Add
voices adds a language's voices (Microsoft's ms-settings list, read
2026-11-11)."""

REGIONS: dict[str, tuple[str, ...]] = {
    "zh": ("zh-CN", "zh-SG", "zh-TW"),
    "zh-hant": ("zh-TW", "zh-CN", "zh-SG"),
    "yue": ("zh-HK", "yue-HK"),
    "en": ("en-US", "en-GB", "en-AU", "en-CA", "en-IE", "en-IN"),
    "es": ("es-ES", "es-MX"),
    "pt": ("pt-BR", "pt-PT"),
    "fr": ("fr-FR", "fr-CA", "fr-CH"),
    "de": ("de-DE", "de-AT", "de-CH"),
    "nl": ("nl-NL", "nl-BE"),
    "ja": ("ja-JP",),
    "ko": ("ko-KR",),
    "vi": ("vi-VN",),
    "ru": ("ru-RU",),
    "it": ("it-IT",),
}
"""Each language's voices in the order a learner of it would want them;
"zh-hant" is Mandarin written in traditional characters. A language not
here takes any voice of its own."""


class Say(StrEnum):
    """What the card's speaker button shows."""

    READY = "ready"
    SPEAKING = "speaking"
    NO_VOICE = "no_voice"


def word_language(card: Card) -> str | None:
    """The language the card's word is said in, as `REGIONS` names it: a
    basic dictionary's or the row's (`card.language`); else Chinese for a
    word in Chinese characters ("zh-hant" for a traditional form), English
    for the rest - the learner's own dictionary is one of the two, and an
    English word in a Chinese learner's caption is English. None: nothing
    to say."""
    if not card.word.strip():
        return None
    if card.language:
        return card.language
    if has_han(card.word):
        return "zh-hant" if card.traditional else "zh"
    return "en"


def voice_for(voices: tuple[Voice, ...], language: str) -> Voice | None:
    """The voice that says a word in `language`, if the PC has one."""
    wanted = REGIONS.get(language, ())
    by_tag = [(v.language.lower(), v) for v in voices]
    for tag in wanted:
        found = next((v for t, v in by_tag if t == tag.lower()), None)
        if found is not None:
            return found
    if language in ("zh", "zh-hant", "yue"):
        return None  # Mandarin isn't said in Cantonese, nor Cantonese in Mandarin
    primary = language.split("-")[0].lower()
    return next((v for t, v in by_tag if t.split("-")[0] == primary), None)


def pace(times_said: int) -> float:
    """The pace for a word said `times_said` times already on this card:
    its own, then slower, in turn."""
    return SLOWER if times_said % 2 else NORMAL
