"""The spoken languages (glossary: the language a source's speech is in):
every language the speech model can be told to hear, and the ones the
learner named last (polyglotic-hq 317).

A source is heard as **Detect** - the speech model finds the language,
each caption, among all of these - or as one language the learner names:
the model is then told it, and hears every caption as it (the server's
`core/listening/language.py` still marks an English line under a named
Chinese or Vietnamese setting as English). Both work; naming one is what
the app suggests, since short or mumbled speech is then never taken for
another language (decision 0108).
"""

from collections.abc import Iterable

from polyglotic_desktop.core.listening.captions import Language

SPOKEN_LANGUAGES: tuple[Language, ...] = tuple(
    Language(code)
    for code in (
        "en", "zh", "yue", "ar", "de", "fr", "es", "pt", "id", "it", "ko", "ru",
        "th", "vi", "ja", "tr", "hi", "ms", "nl", "sv", "da", "fi", "pl", "cs",
        "tl", "fa", "el", "hu", "mk", "ro",
    )
)  # fmt: skip
"""Every language a source's speech, or dictation, can be named as: the
speech model's own list (Qwen3-ASR's 30 - polyglotic-server's
`adapters/qwen_asr.py`, `LANGUAGE_CODES`, read 2026-11-14). The server
takes any language code (protocol.md, `spoken_language`); one its model
doesn't know is heard as Detect, so only these are offered. Detect finds
the same 30. Mandarin is `zh` (its captions in Simplified characters) and
Cantonese `yue` (in Hong Kong characters): the server's scripts. No other
dialect or script can be told to the model."""

RECENT_KEPT = 3
"""How many named languages are remembered as the learner's recent ones."""


def with_recent(recent: Iterable[str], named: str | None) -> tuple[str, ...]:
    """`recent` (newest first) with `named` - a language just named - put
    first, each once, at most RECENT_KEPT; unchanged for Detect (None) or a
    language that isn't one of SPOKEN_LANGUAGES."""
    kept = [code for code in recent if code in SPOKEN_LANGUAGES]
    if named in SPOKEN_LANGUAGES:
        kept = [str(named), *(code for code in kept if code != named)]
    return tuple(dict.fromkeys(kept))[:RECENT_KEPT]


STEADY_CAPTIONS = 5
"""Finished captions in a row Detect hears in one language, and nothing
else, before the window asks whether to always hear it as that language."""


class SteadyLanguage:
    """One source heard as Detect: when it has spoken one language steadily
    - STEADY_CAPTIONS finished captions in a row in one of
    SPOKEN_LANGUAGES, none mixed with another - the language to suggest
    naming (polyglotic-hq 317: "This sounds like Russian. Always hear it as
    Russian?"). Said once a run: the caption that makes it steady says so,
    the ones after it don't; a caption in another language, a mixed one or
    one in no language known starts again. A language in `declined` (Not
    now, kept) is never suggested; one in `unanswered` (the question went by
    itself, polyglotic-hq 350) isn't while this lasts - the app's run, so
    it's asked again after the app starts again."""

    def __init__(self, steady: int = STEADY_CAPTIONS) -> None:
        self.steady = steady
        self.declined: set[str] = set()
        self.unanswered: set[str] = set()
        self._language: str | None = None
        self._run = 0

    def heard(self, language: str | None, languages_heard: Iterable[str]) -> str | None:
        """A finished caption, its language and every language heard in it:
        the language to suggest now, or None."""
        others = {code for code in languages_heard if code != language}
        if language not in SPOKEN_LANGUAGES or others:
            self.start_again()
            return None
        if language == self._language:
            self._run += 1
        else:
            self._language, self._run = language, 1
        if self._run == self.steady and language not in (
            self.declined | self.unanswered
        ):
            return language
        return None

    def start_again(self) -> None:
        """Nothing heard yet: the run begins at the next caption."""
        self._language, self._run = None, 0
