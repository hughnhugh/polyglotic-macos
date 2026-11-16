"""Listening settings: each source's own target languages, or the session's (the server's decision 0033)."""

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.settings import (
    ListeningSettings,
    agreed_language,
)
from polyglotic_desktop.core.listening.sources import MIC, SourceId

EN, JA, ZH = Language("en"), Language("ja"), Language("zh")
APP_1, APP_2 = SourceId("app-1"), SourceId("app-2")


def test_without_languages_of_its_own_a_source_has_the_targets() -> None:
    """Today's interface sets `targets` only: every source the same, as before."""
    today = ListeningSettings(targets=(EN, ZH))
    assert today.targets_of(APP_1) == today.targets_of(MIC) == (EN, ZH)
    assert today.all_targets == (EN, ZH)


def test_a_source_with_its_own_languages_or_none() -> None:
    chosen = ListeningSettings(
        targets=(EN,), source_targets={APP_1: (JA,), MIC: (), APP_2: (EN, JA)}
    )
    assert chosen.targets_of(APP_1) == (JA,)
    assert chosen.targets_of(MIC) == ()  # Original only
    assert chosen.targets_of(SourceId("app-3")) == (EN,)
    assert chosen.all_targets == (EN, JA)  # each once, the targets first


# -- each source's own spoken language (polyglotic-hq 263; the server's 0051) ----------


def test_a_source_with_its_own_spoken_language_or_the_sessions() -> None:
    chosen = ListeningSettings(
        spoken_language=EN, source_spoken={APP_1: ZH, APP_2: None}
    )
    assert chosen.spoken_language_of(APP_1) == ZH
    assert chosen.spoken_language_of(APP_2) is None  # Detect, its own
    assert chosen.spoken_language_of(MIC) == EN  # none of its own: the session's


def test_the_one_language_every_window_names_or_detect() -> None:
    """What a server from before 2026-11-09 is sent for every source."""
    assert agreed_language([ZH, ZH]) == ZH
    assert agreed_language([ZH, EN]) is None
    assert agreed_language([ZH, None]) is None  # one detecting: Detect
    assert agreed_language([None]) is None
    assert agreed_language([]) is None
