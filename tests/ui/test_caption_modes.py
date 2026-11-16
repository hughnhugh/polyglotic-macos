"""Caption timing as the learner's choice (polyglotic-hq project 064;
DECISIONS.md #4 and #107): Steady by default (project 260, the user,
2026-11-09; Quick preview from 2026-11-07, project 176), Quick preview, or
Live updates - in the settings (and for settings saved by earlier
versions), and in what the speech pipeline follows (the Timing panel:
tests/ui_next)."""

import pytest

from polyglotic_desktop.core.listening.settling import SETTLE_AFTER_SEC
from polyglotic_desktop.core.listening.timing import (
    MAX_WAIT_FOR_TEXT_SEC,
    PREVIEW_AFTER_SEC,
    CaptionMode,
    CaptionTiming,
)
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ui.settings import AppSettings


def test_a_new_install_has_steady() -> None:
    value = AppSettings.from_stored({})
    assert value.caption_mode is CaptionMode.STEADY
    assert value.live_interval is None  # finished captions only
    assert value.caption_mode_chosen is None  # the default, not a choice
    assert AppSettings().caption_mode is CaptionMode.STEADY


def test_one_who_never_chose_moves_to_steady_and_a_choice_stays() -> None:
    """Settings saved while Quick preview was the default (176 to 260):
    the mode followed was Quick preview, but nothing was chosen - that
    learner is on Steady now. One who chose Quick preview keeps it."""
    never_chose = {"caption_mode_chosen": None, "caption_timing": "preview"}
    assert AppSettings.from_stored(never_chose).caption_mode is CaptionMode.STEADY
    chose = {"caption_mode_chosen": "preview", "caption_timing": "preview"}
    assert AppSettings.from_stored(chose).caption_mode is CaptionMode.PREVIEW
    chose_live = {"caption_mode_chosen": "live", "caption_timing": "live"}
    assert AppSettings.from_stored(chose_live).caption_mode is CaptionMode.LIVE


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
    monkeypatch.setattr(settings, "default_caption_mode", lambda: CaptionMode.PREVIEW)
    assert unchosen.caption_mode is CaptionMode.PREVIEW
    assert chosen.caption_mode is CaptionMode.STEADY


@pytest.mark.parametrize(
    ("stored", "chosen"),
    [
        # a version before 176 saved Steady, the default then, chosen or
        # not: it follows today's default
        ({"caption_timing": "steady"}, None),
        # Quick preview and Live updates were chosen: they stay
        ({"caption_timing": "preview"}, CaptionMode.PREVIEW),
        ({"caption_timing": "live", "live_update_interval": 3.0}, CaptionMode.LIVE),
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
    assert value.caption_mode is (chosen or CaptionMode.STEADY)


@pytest.mark.parametrize(
    ("stored", "chosen", "interval"),
    [
        # never changed: the old default interval wasn't a choice
        ({"live_update_interval": 1.5}, None, 1.5),
        # Off - finished captions only - was: Steady is the nearest mode
        ({"live_update_interval": None}, CaptionMode.STEADY, 1.5),
        # another interval was chosen: it stays, with Live updates
        ({"live_update_interval": 0.5}, CaptionMode.LIVE, 0.5),
        ({"live_update_interval": 10.0}, CaptionMode.LIVE, 10.0),
        # nothing valid to go on: the default
        ({"live_update_interval": "fast"}, None, 1.5),
        ({"live_update_interval": 99.0}, None, 1.5),
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
    for mode in CaptionMode:
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
    assert AppSettings().to_stored()["caption_timing"] == "steady"
    chosen = AppSettings(caption_mode_chosen="steady").to_stored()
    assert (chosen["caption_timing"], chosen["caption_mode_chosen"]) == (
        "steady",
        "steady",
    )


class _Detector:
    def feed(self, start: float, audio: object) -> list[object]:
        return []


def test_the_pipeline_follows_a_mode_chosen_while_listening() -> None:
    timing = CaptionTiming(None, rules=CaptionMode.STEADY.rules)
    pipeline = SpeechPipeline(_Detector, timing)  # type: ignore[arg-type]
    pipeline.set_timing(CaptionMode.LIVE.rules, 2.0, 3.0)
    assert (timing.rules, timing.live_update_interval) == (CaptionMode.LIVE.rules, 2.0)
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


def test_steady_s_lines_are_translated_and_dim_as_quick_preview_s() -> None:
    """Steady's only live updates - the longest wait's - are provisional
    lines as Quick preview's: translated, dim, replaced (277)."""
    from polyglotic_desktop.main import caption_look, listening_settings

    for mode in ("steady", "preview"):
        value = AppSettings(caption_mode_chosen=mode, translate_live=False)
        assert caption_look(value).preview
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
