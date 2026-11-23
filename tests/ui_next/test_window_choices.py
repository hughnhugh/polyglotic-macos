"""A caption window's own state (project 109's structure, sections 1.1 and
2): what it remembers by source, and the notice line - plain Python, no
Qt. Today's values moved over on first use: `test_migration`."""

from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    JoinedChoices,
    Notice,
    Notices,
    StoredWindows,
    WindowChoices,
    intro_seconds,
    minutes_used_up,
    shows,
    slowed_now,
    stepped,
)
from polyglotic_desktop.ui_next.views.migration import moved_over, stored_windows
from polyglotic_desktop.ui_next.views.placement import Preset, Rect

TODAY = {
    "targets": ["zh", "en"],
    "text_scale": 1.3,
    "caption_mic": True,
    "overlay_position": "custom",
    "overlay_geometry": {"zh": [100, 200, 700, 260], "en": [100, 500, 700, 260]},
}


def test_after_first_use_a_new_window_copies_the_last_and_starts_without_my_speech() -> (
    None
):
    last = WindowChoices("ja", 1.5, True, Preset.TOP_CENTRE, Rect(1, 2, 3, 4))
    stored = StoredWindows({}, last)
    assert stored.for_new(2) == WindowChoices("ja", 1.5)


def test_choices_are_kept_by_source_and_read_back() -> None:
    discord = WindowChoices("", 0.8, True, Preset.CUSTOM, Rect(5, 6, 400, 90))
    stored = StoredWindows({"Discord.exe": discord}, discord)
    saved = {**TODAY, STORED_KEY: stored.to_stored()}
    back = stored_windows(saved)
    assert back.by_key == {"Discord.exe": discord}
    assert back.by_key["Discord.exe"].target is None  # Original only
    assert not back.first_use


def test_choices_read_leniently() -> None:
    base = WindowChoices("en", 1.0)
    bad = {
        "translate_into": 3,
        "text_size": 9,
        "mode": "huge",
        "show_mic": "yes",
        "position": "middle",
        "geometry": [1, 2],
    }
    assert WindowChoices.from_stored(bad, base) == base
    assert WindowChoices.from_stored("nonsense", base) == base
    assert WindowChoices.from_stored({"geometry": None}, base).geometry is None


def test_todays_interface_keeps_its_own_values() -> None:
    """The windows' setting is one key; today's are untouched by it."""
    stored = moved_over(TODAY)
    assert set(stored.to_stored()) == {
        "windows",
        "last",
        "joined",
        "looked_up",
        "recent_spoken",
        "declined_spoken",
        "reading_hinted",
        "respeaking_hinted",
        "set_up",  # the first window's set-up answered (465)
        "start_like_this",
        "kept_languages",  # while every window shows the original only (556)
    }


def test_joined_or_separate_is_remembered_with_the_joined_place() -> None:
    joined = JoinedChoices(True, Preset.TOP_CENTRE, Rect(0, 40, 1500, 90))
    stored = StoredWindows(joined=joined)
    back = stored_windows({STORED_KEY: stored.to_stored()})
    assert back.joined == joined
    assert stored_windows({}).joined.on  # joined, at first (554)
    # the setting from before the joined window: the default, joined
    assert stored_windows({STORED_KEY: {"windows": {}}}).joined.on


def test_joined_choices_read_leniently() -> None:
    bad = {"on": "yes", "mode": "huge", "position": "middle", "geometry": [1, 2]}
    assert JoinedChoices.from_stored(bad) == JoinedChoices()
    assert JoinedChoices.from_stored(None) == JoinedChoices()


def test_text_size_steps_by_ten_percent_within_70_to_200() -> None:
    assert stepped(1.0, 1) == 1.1
    assert stepped(0.7, -1) == 0.7
    assert stepped(1.95, 2) == 2.0


def test_the_notice_line_shows_a_brief_notice_then_the_state() -> None:
    notices = Notices()
    assert notices.showing(0.0) == (None, None)
    notices.state = Notice.RECONNECTING
    notices.retry_at = 4.2
    assert notices.showing(0.0) == (Notice.RECONNECTING, None)
    assert notices.retry_in(0.0) == 4
    notices.brief("Bottom centre", 1.0, seconds=1.0)
    assert notices.showing(1.5) == (None, "Bottom centre")
    assert notices.showing(2.5) == (Notice.RECONNECTING, None)
    notices.paused = True  # paused says so before the connection
    assert notices.showing(3.0) == (Notice.PAUSED, None)


def test_free_minutes_used_after_paused_before_the_connection() -> None:
    notices = Notices()
    notices.state, notices.retry_at = Notice.STOPPED, None
    notices.minutes_used = True  # why it stopped, said until there are more
    assert notices.showing(0.0) == (Notice.MINUTES_USED, None)
    notices.paused = True
    assert notices.showing(0.0) == (Notice.PAUSED, None)
    notices.paused = False
    notices.brief("The server is restarting", 0.0)
    assert notices.showing(1.0) == (None, "The server is restarting")
    notices.state, notices.retry_at = Notice.RECONNECTING, 10.0
    assert notices.showing(7.0) == (Notice.MINUTES_USED, None)
    assert notices.next_change(7.0) is None  # no count shows under it


def test_captions_failing_after_minutes_used_before_the_connection() -> None:
    notices = Notices()
    notices.state = Notice.RECONNECTING
    notices.failing = True
    assert notices.showing(0.0) == (Notice.FAILING, None)
    notices.minutes_used = True
    assert notices.showing(0.0) == (Notice.MINUTES_USED, None)
    notices.minutes_used = False
    notices.brief("The server is restarting", 0.0)
    assert notices.showing(1.0) == (None, "The server is restarting")
    assert notices.showing(9.0) == (Notice.FAILING, None)


def test_an_unstable_connection_only_while_the_state_says_nothing() -> None:
    """polyglotic-hq 165: "Reconnecting" says more while it's down; between
    drops, listening, the unstable connection is said - under the others."""
    notices = Notices()
    notices.unstable = True
    assert notices.showing(0.0) == (Notice.UNSTABLE, None)
    notices.state = Notice.RECONNECTING
    assert notices.showing(0.0) == (Notice.RECONNECTING, None)
    notices.state = None
    notices.failing = True
    assert notices.showing(0.0) == (Notice.FAILING, None)
    notices.failing = False
    notices.paused = True
    assert notices.showing(0.0) == (Notice.PAUSED, None)


def test_minutes_are_used_up_when_the_server_says_none_are_left() -> None:
    assert not minutes_used_up(None)  # no limit
    assert not minutes_used_up(0.5)
    assert minutes_used_up(0)
    assert minutes_used_up(-0.2)


def test_a_busy_time_is_said_when_it_begins_and_only_over_live_updates() -> None:
    """The server's pace hint slows live updates; finished captions are
    never held back - so Steady's learner sees no change, and isn't told."""
    assert slowed_now(False, True, CaptionMode.INSTANT)
    assert slowed_now(False, True, CaptionMode.STEADY)
    assert slowed_now(False, True, CaptionMode.CALM)
    assert not slowed_now(False, True, CaptionMode.WHOLE)
    assert not slowed_now(True, True, CaptionMode.INSTANT)  # said once
    assert not slowed_now(True, False, CaptionMode.INSTANT)  # over: nothing said


def test_the_notice_line_says_when_it_changes_by_itself() -> None:
    notices = Notices()
    assert notices.next_change(0.0) is None
    notices.brief("Server restarting", 0.0)
    assert notices.next_change(0.0) == 6.0
    notices.state, notices.retry_at = Notice.RECONNECTING, 10.0
    assert notices.next_change(0.0) == 1.0  # the count ticks down


# -- showing or fading (DECISIONS.md #56) -----------------------------------------------


def _shows(**given: object) -> bool:
    state: dict[str, object] = {
        "awake": False,
        "introducing": False,
        "empty": False,
        "quiet": 0.0,
        "fade_after": 8.0,
    }
    return shows(**{**state, **given})  # type: ignore[arg-type]


def test_a_window_with_nothing_to_read_shows_waiting_for_audio() -> None:
    """123's finding: a window with no captions yet was invisible, so a
    learner who ticked an app couldn't tell it worked, or where it was -
    and the user (polyglotic-hq 272): it stays, waiting for audio, until
    its first captions, not only for its first seconds."""
    assert _shows(empty=True)
    assert _shows(empty=True, quiet=1e6)
    assert _shows(empty=True, quiet=1e6, fade_after=None)


def test_with_captions_it_fades_after_the_quiet_time_unless_never() -> None:
    assert _shows(quiet=7.9)
    assert not _shows(quiet=8.1)
    assert _shows(quiet=8.1, awake=True)
    assert _shows(quiet=8.1, introducing=True)
    assert _shows(quiet=1e6, fade_after=None)


def test_a_new_window_shows_for_the_fade_after_time_or_8_s() -> None:
    assert intro_seconds(5.0) == 5.0
    assert intro_seconds(None) == 8.0  # fading off: the default's time


# -- a language not offered (117 Low 10) -----------------------------------------------------

OFFERED = {"en", "zh", "ja", "fr"}
"""The translation languages that can be picked (the interface passes its list)."""


def test_a_language_not_offered_takes_the_last_windows_or_the_default() -> None:
    """Taken off the list (Mongolian, Kazakh: DECISIONS.md #40), a newer
    version's, edited by hand: not sent to the server as a source's targets."""
    stored = StoredWindows(
        {
            "kept": WindowChoices("ja"),
            "original": WindowChoices(""),  # Original only is always allowed
            "gone": WindowChoices("mn"),
            "unknown": WindowChoices("xx"),
        },
        WindowChoices("fr"),
    ).only_offered(OFFERED)
    assert {k: c.translate_into for k, c in stored.by_key.items()} == {
        "kept": "ja",
        "original": "",
        "gone": "fr",
        "unknown": "fr",
    }
    assert stored.last.translate_into == "fr"
    nothing_offered = StoredWindows({"a": WindowChoices("kk")}, WindowChoices("kk"))
    checked = nothing_offered.only_offered(OFFERED)
    assert checked.last.translate_into == "en"  # the default
    assert checked.by_key["a"].translate_into == "en"


def test_only_offered_keeps_everything_else() -> None:
    gone = WindowChoices("mn", 1.4, True, Preset.CUSTOM, Rect(5, 6, 400, 90))
    stored = moved_over(TODAY)
    stored.by_key["a"] = gone
    checked = stored.only_offered(OFFERED)
    assert checked.by_key["a"] == WindowChoices(
        "zh", 1.4, True, Preset.CUSTOM, Rect(5, 6, 400, 90)
    )
    assert checked.first_use
