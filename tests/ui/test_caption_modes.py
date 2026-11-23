"""Caption timing as the learner's choice (polyglotic-hq project 064;
DECISIONS.md #4, #107 and #230): Instant by default (626), with
Whole captions, Steady and Calm - in the settings
(and for settings saved by earlier versions), and in what the speech
pipeline follows (the Timing panel: tests/ui_next)."""

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.listening.settling import SETTLE_AFTER_SEC
from polyglotic_desktop.core.listening.timing import (
    LIVE_UPDATE_INTERVAL_SEC,
    MAX_WAIT_FOR_TEXT_SEC,
    OFFERED_MODES,
    PREVIEW_AFTER_SEC,
    CaptionMode,
    CaptionTiming,
    default_caption_mode,
)
from polyglotic_desktop.main import timing_of
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ui.settings import FOLLOW_DEFAULT, AppSettings, Settings


def test_a_new_install_has_instant() -> None:
    value = AppSettings.from_stored({})
    assert value.caption_mode is CaptionMode.INSTANT
    assert value.live_interval == value.live_update_interval
    assert value.caption_mode_chosen is None
    assert AppSettings().caption_mode is CaptionMode.INSTANT


def test_one_who_never_chose_moves_to_instant_and_a_choice_stays() -> None:
    """An implicit default follows Instant. Explicit choices survive."""
    never_chose = {"caption_mode_chosen": None, "caption_timing": "steady"}
    assert AppSettings.from_stored(never_chose).caption_mode is CaptionMode.INSTANT
    never_chose = {"caption_mode_chosen": None, "caption_timing": "preview"}
    assert AppSettings.from_stored(never_chose).caption_mode is CaptionMode.INSTANT
    chose = {"caption_mode_chosen": "steady", "caption_timing": "steady"}
    assert AppSettings.from_stored(chose).caption_mode is CaptionMode.WHOLE
    chose_live = {"caption_mode_chosen": "live", "caption_timing": "live"}
    assert AppSettings.from_stored(chose_live).caption_mode is CaptionMode.INSTANT


def test_one_who_chose_quick_preview_is_on_steady_as_a_choice() -> None:
    """Quick preview is retired (decision 0246): a learner who chose it has
    Steady, and as their choice - a later default doesn't move them."""
    value = AppSettings.from_stored({"caption_mode_chosen": "preview"})
    assert value.caption_mode_chosen == "words"
    assert value.caption_mode is CaptionMode.STEADY
    again = AppSettings.from_stored(value.to_stored())
    assert again.caption_mode_chosen == "words"


def test_steadys_options_are_kept_and_say_how_its_words_are_played_out() -> None:
    from polyglotic_desktop.core.listening.playout import (
        DELAY_SEC,
        EAGER_DELAY_SEC,
        Ahead,
        PlayoutRules,
    )

    assert AppSettings().playout_rules == PlayoutRules(DELAY_SEC, 1, Ahead.WAITING)
    value = AppSettings.from_stored(
        AppSettings(steady_newest_word=True, steady_words_ahead="waiting").to_stored()
    )
    assert value.playout_rules == PlayoutRules(EAGER_DELAY_SEC, 0, Ahead.WAITING)
    assert (
        AppSettings.from_stored({"steady_words_ahead": "far"}).steady_words_ahead
        == "waiting"  # the default (554)
    )
    calm = AppSettings(caption_mode_chosen="calm")
    assert calm.caption_mode is CaptionMode.CALM
    assert calm.playout_rules.established_only
    assert calm.live_interval == LIVE_UPDATE_INTERVAL_SEC


def test_the_default_moves_everyone_who_hasnt_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is decided in one place (a smarter preview, 183):
    whoever hasn't chosen follows it, a choice stays."""
    from polyglotic_desktop.ui import settings

    unchosen = AppSettings.from_stored(AppSettings().to_stored())
    chosen = AppSettings.from_stored(
        AppSettings(caption_mode_chosen="steady").to_stored()
    )
    monkeypatch.setattr(settings, "default_caption_mode", lambda: CaptionMode.CALM)
    assert unchosen.caption_mode is CaptionMode.CALM
    assert chosen.caption_mode is CaptionMode.WHOLE


def test_moving_the_longest_wait_isnt_choosing_a_mode(qapp: QApplication) -> None:
    """Settings > Timing saved its mode as chosen with any change, so a
    learner who only moved the longest wait kept Steady when the default
    became Quick preview (polyglotic-hq 522). Choosing a mode is kept."""
    built = Built()
    try:
        settings, timing = built.desktop.settings, built.panels.timing
        timing.set_max_wait(5.0)
        assert settings.value.max_wait_for_text == 5.0
        assert settings.value.caption_mode_chosen is None  # still the default's
        timing.set_mode(CaptionMode.WHOLE)
        assert settings.value.caption_mode_chosen == "steady"
        timing.set_max_wait(4.0)
        assert settings.value.caption_mode_chosen == "steady"  # kept
        timing.set_mode(CaptionMode.STEADY)  # chosen, though the default
        assert settings.value.caption_mode_chosen == "words"
        assert timing_of(settings.value).mode is CaptionMode.STEADY
    finally:
        built.close()


@pytest.mark.parametrize(
    ("stored", "chosen"),
    [
        # a version before 176 saved Steady, the default then, chosen or
        # not: it follows today's default
        ({"caption_timing": "steady"}, None),
        # Quick preview and Live updates were chosen: Instant stays, and
        # Quick preview, retired, is Steady
        ({"caption_timing": "preview"}, CaptionMode.STEADY),
        ({"caption_timing": "live", "live_update_interval": 3.0}, CaptionMode.INSTANT),
        # whatever the interval, once there were modes
        ({"caption_timing": "steady", "live_update_interval": 0.5}, None),
        # nothing valid to go on: the default
        ({"caption_timing": "rapid"}, None),
        ({"caption_timing": None}, None),
    ],
)
def test_settings_before_176_keep_only_a_mode_that_was_chosen(
    stored: dict[str, object], chosen: CaptionMode | None
) -> None:
    value = AppSettings.from_stored({"learning": "zh", **stored})
    assert value.caption_mode_chosen == chosen
    assert value.caption_mode is (chosen or default_caption_mode())


@pytest.mark.parametrize(
    ("stored", "chosen", "interval"),
    [
        # never changed: the old default interval wasn't a choice - today's
        # default (1.0 s since polyglotic-hq 494)
        ({"live_update_interval": 1.5}, None, LIVE_UPDATE_INTERVAL_SEC),
        # Off - finished captions only - was: Steady is the nearest mode
        ({"live_update_interval": None}, CaptionMode.WHOLE, LIVE_UPDATE_INTERVAL_SEC),
        # another interval was chosen: it stays, with Live updates
        ({"live_update_interval": 0.5}, CaptionMode.INSTANT, 0.5),
        ({"live_update_interval": 10.0}, CaptionMode.INSTANT, 10.0),
        # nothing valid to go on: the default
        ({"live_update_interval": "fast"}, None, LIVE_UPDATE_INTERVAL_SEC),
        ({"live_update_interval": 99.0}, None, LIVE_UPDATE_INTERVAL_SEC),
    ],
)
def test_settings_from_before_modes_keep_only_an_interval_that_was_chosen(
    stored: dict[str, object], chosen: CaptionMode | None, interval: float
) -> None:
    value = AppSettings.from_stored({"learning": "zh", **stored})
    assert (value.caption_mode_chosen, value.live_update_interval) == (
        chosen,
        interval,
    )


def test_a_mode_once_chosen_is_kept_whatever_the_interval() -> None:
    for mode in OFFERED_MODES:
        stored = AppSettings(caption_mode_chosen=mode.value, live_update_interval=0.5)
        value = AppSettings.from_stored(stored.to_stored())
        assert (value.caption_mode_chosen, value.caption_mode) == (mode, mode)
    preview = AppSettings(caption_mode_chosen="preview", live_update_interval=0.5)
    assert preview.live_interval == PREVIEW_AFTER_SEC
    assert AppSettings(caption_mode_chosen="steady").live_interval is None
    live = AppSettings(caption_mode_chosen="live", live_update_interval=3.0)
    assert live.live_interval == 3.0
    assert AppSettings.from_stored({"caption_mode_chosen": "rapid"}).caption_mode_chosen is None  # fmt: skip


def test_older_versions_read_the_mode_followed() -> None:
    """Versions before 176 read `caption_timing` (RELEASING.md section 5):
    it holds the mode the app follows, chosen or not."""
    assert AppSettings().to_stored()["caption_timing"] == "live"
    chosen = AppSettings(caption_mode_chosen="steady").to_stored()
    assert (chosen["caption_timing"], chosen["caption_mode_chosen"]) == (
        "steady",
        "steady",
    )


class _Detector:
    def feed(self, start: float, audio: object) -> list[object]:
        return []


def test_the_pipeline_follows_a_mode_chosen_while_listening() -> None:
    timing = CaptionTiming(None, rules=CaptionMode.WHOLE.rules)
    pipeline = SpeechPipeline(_Detector, timing)  # type: ignore[arg-type]
    pipeline.set_timing(CaptionMode.INSTANT.rules, 2.0, 3.0)
    assert (timing.rules, timing.live_update_interval) == (
        CaptionMode.INSTANT.rules,
        2.0,
    )
    pipeline.set_timing(CaptionMode.PREVIEW.rules, PREVIEW_AFTER_SEC, 4.0)
    assert timing.rules == CaptionMode.PREVIEW.rules
    assert timing.live_update_interval == PREVIEW_AFTER_SEC
    assert timing.max_wait == 4.0  # the longest wait for text, live (277)


def test_the_longest_wait_for_text_is_3s_and_kept_within_2_to_6s() -> None:
    """polyglotic-hq 277: 3s unless the learner chooses; a stored value
    out of range (or not a number) takes the default."""
    assert AppSettings.from_stored({}).max_wait_for_text == MAX_WAIT_FOR_TEXT_SEC == 3.0
    for kept in (2.0, 2.5, 6.0):
        stored = AppSettings(max_wait_for_text=kept).to_stored()
        assert AppSettings.from_stored(stored).max_wait_for_text == kept
    for wrong in (1.0, 7.0, "3", None):
        stored = {"max_wait_for_text": wrong}
        assert AppSettings.from_stored(stored).max_wait_for_text == 3.0


def test_whole_captions_lines_are_translated_and_dim() -> None:
    """Whole captions' only live updates - the longest wait's - are
    provisional lines: translated, dim, replaced (277). The paced modes'
    live updates are the caption itself, and always translated: a clause
    shows its translation as it ends (526)."""
    from polyglotic_desktop.main import caption_look, listening_settings

    value = AppSettings(caption_mode_chosen="steady", translate_live=False)
    assert caption_look(value).preview
    assert listening_settings(value).translate_live
    for mode in ("words", "calm"):
        value = AppSettings(caption_mode_chosen=mode, translate_live=False)
        assert not caption_look(value).preview
        assert listening_settings(value).translate_live
    live = AppSettings(caption_mode_chosen="live", translate_live=False)
    assert not caption_look(live).preview
    assert not listening_settings(live).translate_live


def test_how_long_text_may_still_change_is_3s_and_kept_within_0_to_3s() -> None:
    """polyglotic-hq 309: 3s (decision 0088's) unless the learner chooses
    less, down to none; a stored value out of range (or not a number)
    takes the default."""
    assert AppSettings.from_stored({}).text_settles_after == SETTLE_AFTER_SEC == 3.0
    for kept in (0.0, 1.0, 2.5):
        stored = AppSettings(text_settles_after=kept).to_stored()
        assert AppSettings.from_stored(stored).text_settles_after == kept
    for wrong in (-1.0, 3.5, "1", None):
        stored = {"text_settles_after": wrong}
        assert AppSettings.from_stored(stored).text_settles_after == 3.0


# -- Live updates every 1.0 s (polyglotic-hq 494, DECISIONS.md #211) ---------------


def test_live_updates_come_every_second_by_default() -> None:
    assert LIVE_UPDATE_INTERVAL_SEC == 1.0
    assert AppSettings().live_update_interval == 1.0
    assert (
        CaptionMode.INSTANT.live_update_interval(AppSettings().live_update_interval)
        == 1.0
    )


@pytest.mark.parametrize(
    ("stored", "interval"),
    [
        # saved before 494, at the old default: it follows today's
        ({"caption_mode_chosen": "live", "live_update_interval": 1.5}, 1.0),
        # saved before 494, chosen: it stays
        ({"caption_mode_chosen": "live", "live_update_interval": 2.0}, 2.0),
        ({"caption_mode_chosen": "live", "live_update_interval": 0.5}, 0.5),
        # saved since, with the record of changes (478): 1.5 changed on this
        # PC is a choice and stays
        (
            {
                "caption_mode_chosen": "live",
                "live_update_interval": 1.5,
                "changed": ["caption_mode_chosen", "live_update_interval"],
            },
            1.5,
        ),
        # never changed, saved under some other default: today's
        (
            {
                "caption_mode_chosen": "live",
                "live_update_interval": 0.75,
                "changed": ["caption_mode_chosen"],
            },
            1.0,
        ),
    ],
)
def test_an_interval_left_at_its_default_follows_todays(
    stored: dict[str, object], interval: float
) -> None:
    value = AppSettings.from_stored({"learning": "zh", **stored})
    assert value.live_update_interval == interval
    assert value.caption_mode_chosen == "live"


def test_steadys_words_ahead_are_faint_until_the_learner_changes_them() -> None:
    """The user, 2026-11-20 (polyglotic-hq 554): "Default faint ahead,
    acquisition is preferable for me but probably default to both". Faint
    words ahead by default - for a learner who never chose, as a file from
    the preview holds them ("none", not in the record of changes) - and
    Both stays the path; a learner's own choice is kept."""
    from polyglotic_desktop.core.listening.playout import Ahead, ReadingPath
    from polyglotic_desktop.main import timing_of
    from polyglotic_desktop.ui_next.views.panels import Timing

    assert "steady_words_ahead" in FOLLOW_DEFAULT
    assert AppSettings().playout_rules.ahead is Ahead.WAITING
    assert timing_of(AppSettings()).words_ahead is Ahead.WAITING
    assert Timing().words_ahead is Ahead.WAITING
    assert AppSettings().caption_path == ReadingPath.BOTH.value
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.update(opacity=0.6)
    preview = {**store.values, "steady_words_ahead": "none"}  # never chosen
    assert AppSettings.from_stored(preview).steady_words_ahead == "waiting"
    settings.update(steady_words_ahead="none")  # the learner's Off
    changed = store.values["changed"]
    assert isinstance(changed, list) and "steady_words_ahead" in changed
    assert AppSettings.from_stored(store.values).steady_words_ahead == "none"


def test_an_interval_follows_the_default_until_changed() -> None:
    """On the record of changes, as the switches that follow the default
    (`FOLLOW_DEFAULT`, decision 0220; 506)."""
    assert "live_update_interval" in FOLLOW_DEFAULT
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.update(opacity=0.6)
    untouched = {**store.values, "live_update_interval": 0.75}  # a later default
    assert AppSettings.from_stored(untouched).live_update_interval == 1.0
    settings.update(live_update_interval=1.5)
    assert store.values["changed"] == ["opacity", "live_update_interval"]
    assert AppSettings.from_stored(store.values).live_update_interval == 1.5
