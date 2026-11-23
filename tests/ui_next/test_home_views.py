"""Home's views without Qt (project 109's sections 5 and 7): the state
line's rules, and the app picker - at most 3 apps, the Add list, everything
the PC plays."""

from dataclasses import replace

from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.releases.updates import UpdateNow
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY
from polyglotic_desktop.ui_next.views.home import (
    Action,
    AddableApp,
    AppRow,
    AppStatus,
    Detail,
    HomeState,
    ListeningState,
    Picker,
    PickerView,
    Title,
    Tone,
    addable,
    retry_in,
    state_line,
)


def test_paused_comes_first() -> None:
    line = state_line(HomeState(ListeningState.WAITING, 4.0, paused=True))
    assert (line.tone, line.title) == (Tone.WAIT, Title.PAUSED)
    # how to resume, and nothing else (109's section 7); its button Resume
    assert line.details == ((Detail.RESUME, None),)
    assert line.action is Action.PAUSE


def test_signed_out_says_whats_needed_with_sign_in() -> None:
    """109's section 7: "Not signed in - you need an invite code from
    us" with Sign in in place of Pause captions."""
    line = state_line(
        HomeState(ListeningState.SIGN_IN_NEEDED, chosen=True, languages=("en",))
    )
    assert (line.tone, line.title) == (Tone.BAD, Title.NOT_SIGNED_IN)
    assert line.details == ((Detail.SIGN_IN, None),)
    assert line.action is Action.SIGN_IN
    paused = state_line(HomeState(ListeningState.SIGN_IN_NEEDED, paused=True))
    assert (paused.title, paused.action) == (Title.PAUSED, Action.PAUSE)


def test_the_first_runs_last_step_is_home_picking_what_to_caption() -> None:
    """DECISIONS.md #25: the first run ends on Home, paused until
    something is ticked - "Pick what to caption", nothing captioned."""
    line = state_line(HomeState(ListeningState.NOT_CONNECTED, chosen=False))
    assert (line.tone, line.title, line.action) == (Tone.WAIT, Title.PICK, Action.NONE)
    assert line.details[0] == (Detail.NOTHING_CHOSEN, None)


def test_no_pause_action_while_nothing_is_captioned() -> None:
    """polyglotic-hq 629: nothing is captioned, so there is nothing to pause.
    Pause returns once something is chosen; Sign in, Get Plus and Resume keep
    their own buttons."""
    for state in (
        HomeState(ListeningState.NOT_CONNECTED, chosen=False),
        HomeState(ListeningState.LISTENING, chosen=False),
        HomeState(ListeningState.STOPPED, chosen=False),
        HomeState(ListeningState.CONNECTING, chosen=False),
        HomeState(ListeningState.UPDATE_NEEDED, chosen=False),
        HomeState(
            ListeningState.WAITING, chosen=False, unreachable=Unreachable.OFFLINE
        ),
    ):
        assert state_line(state).action is Action.NONE, state
    assert state_line(HomeState(ListeningState.SIGN_IN_NEEDED)).action is Action.SIGN_IN
    assert state_line(HomeState(ListeningState.PLUS_ENDED)).action is Action.GET_PLUS
    assert (
        state_line(HomeState(ListeningState.NOT_CONNECTED, paused=True)).action
        is Action.PAUSE
    )
    assert (
        state_line(HomeState(ListeningState.LISTENING, chosen=True)).action
        is Action.PAUSE
    )


def test_pick_what_to_caption_until_something_is_chosen() -> None:
    line = state_line(HomeState(ListeningState.NOT_CONNECTED))
    assert line.title is Title.PICK
    assert line.details[0] == (Detail.NOTHING_CHOSEN, None)
    # signed out says so even with nothing chosen
    signed_out = state_line(HomeState(ListeningState.SIGN_IN_NEEDED))
    assert (signed_out.tone, signed_out.title) == (Tone.BAD, Title.NOT_SIGNED_IN)


def test_the_connections_state_and_its_details() -> None:
    line = state_line(
        HomeState(
            ListeningState.WAITING,
            retry_at=4.4,
            chosen=True,
            languages=("en", "ja"),
            windows=2,
        )
    )
    assert line.title is Title.RECONNECTING
    assert line.details == (
        (Detail.RETRY_IN, 4),
        (Detail.CAPTIONS_IN, ("en", "ja")),
        (Detail.SPEECH_NOT_CAPTIONED, None),
    )
    listening = state_line(
        HomeState(ListeningState.LISTENING, chosen=True, windows=1, speech_shown=True)
    )
    assert (listening.tone, listening.title) == (Tone.GOOD, Title.LISTENING)
    assert listening.details == ((Detail.ORIGINAL_ONLY, None),)  # no window translates


def test_the_seconds_to_the_next_try_count_down() -> None:
    """polyglotic-hq 133: Home said "trying again in 22s" while the
    caption windows, at the same moment, said 13 s - Home's never moved.
    The line is drawn from when the next try is, and the time now."""
    state = HomeState(ListeningState.WAITING, retry_at=122.0, chosen=True)
    assert state_line(state, now=100.0).details[0] == (Detail.RETRY_IN, 22)
    assert state_line(state, now=109.0).details[0] == (Detail.RETRY_IN, 13)
    # once it's due, it's trying: no "in 0 s" (the windows say "Reconnecting")
    assert all(d is not Detail.RETRY_IN for d, _ in state_line(state, 122.4).details)
    assert retry_in(state, 130.0) is None
    # only while waiting to reconnect
    assert retry_in(HomeState(ListeningState.CONNECTING, retry_at=122.0), 100) is None


def test_the_apps_that_could_be_added() -> None:
    found = [
        ("Steam", "Steam", False),
        ("Discord", "Discord", True),
        ("Spotify", "Spotify", False),
        ("Spotify", "Spotify", True),  # two of one app: one choice, playing
    ]
    shown = addable(found, captioned=("Discord",))
    assert [(a.name, a.playing) for a in shown] == [("Spotify", True), ("Steam", False)]


def _row(key: str, mic: bool = False) -> AppRow:
    return AppRow(key, key, "#4dd0e1", AppStatus.PLAYING, "en", mic)


class Commands:
    def __init__(self) -> None:
        self.asked: list[tuple[str, object]] = []

    def __getattr__(self, name: str) -> object:
        return lambda *args: self.asked.append((name, args))


def test_at_three_the_add_list_is_full() -> None:
    commands = Commands()
    full = Picker(captioned=(_row("a", True), _row("b"), _row("c", True)))
    assert full.full and full.speech_shown_in == ("a", "c")
    view = PickerView(full, commands)  # type: ignore[arg-type]
    view.add("d")
    assert commands.asked == []  # no 4th asked for
    view.follow(Picker(captioned=(_row("a"),)))
    view.add("d")
    assert commands.asked == [("add", ("d",))]
    assert not Picker(whole_system=True).full


def test_the_pickers_commands() -> None:
    commands = Commands()
    view = PickerView(Picker(captioned=(_row("a"),), hidden=True), commands)  # type: ignore[arg-type]
    view.show_window("a")  # hidden: every window shown again (335)
    view.set_whole_system(False)  # no change
    view.rename("a", "  Chat  ")
    view.set_translate_into("a", ORIGINAL_ONLY)
    view.set_show_mic("a", True)
    view.remove("a")
    assert [name for name, _ in commands.asked] == [
        "show_window",
        "rename",
        "set_translate_into",
        "set_show_mic",
        "remove",
    ]
    assert commands.asked[1] == ("rename", ("a", "Chat"))


def test_update_needed_says_what_to_do() -> None:
    """polyglotic-hq 133: "Update needed" said "captions in English · your
    speech not captioned". It says what to do, by what the updater found -
    and only that."""
    needed = HomeState(ListeningState.UPDATE_NEEDED, chosen=True, languages=("en",))
    for found, detail in (
        (None, Detail.UPDATING),
        (UpdateNow.RESTARTING, Detail.UPDATING),
        (UpdateNow.DOWNLOADED, Detail.RESTART_TO_INSTALL),
        (UpdateNow.NONE_YET, Detail.NO_UPDATE_YET),
        (UpdateNow.NOT_INSTALLED, Detail.INSTALL_BY_HAND),
        (UpdateNow.FROM_STORE, Detail.UPDATE_FROM_STORE),  # decision 0056
    ):
        line = state_line(replace(needed, update_found=found))
        assert (line.tone, line.title) == (Tone.BAD, Title.UPDATE_NEEDED)
        assert line.details == ((detail, None),)
    # what was found shows only while an update is needed
    listening = replace(
        needed, connection=ListeningState.LISTENING, update_found=UpdateNow.NONE_YET
    )
    assert state_line(listening).details[0] == (Detail.CAPTIONS_IN, ("en",))


def test_not_connected_says_what_to_do_and_connecting_breathes() -> None:
    """151's W8 (176): "Not connected" had no next step (135's finding 14);
    the dot pulses while the app is trying to connect."""
    line = state_line(HomeState(ListeningState.NOT_CONNECTED, chosen=True))
    assert line.title is Title.NOT_CONNECTED
    assert line.details[0] == (Detail.HELP_CHECKS, None)
    assert not line.pulse
    assert state_line(HomeState(ListeningState.CONNECTING, chosen=True)).pulse
    assert state_line(HomeState(ListeningState.WAITING, chosen=True)).pulse
    assert not state_line(HomeState(ListeningState.LISTENING, chosen=True)).pulse
    picking = state_line(HomeState(ListeningState.NOT_CONNECTED))  # nothing chosen
    assert (Detail.HELP_CHECKS, None) not in picking.details


def test_stopped_says_to_start_again_as_every_other_bad_state() -> None:
    """polyglotic-hq 228 (224's finding 1): the red "Stopped" was the one bad
    state with no next step. It says to start again, and nothing else -
    as Update needed and Plus has ended do; the last app unticked is still
    "Pick what to caption"."""
    line = state_line(HomeState(ListeningState.STOPPED, chosen=True, languages=("en",)))
    assert (line.tone, line.title) == (Tone.BAD, Title.STOPPED)
    assert line.details == ((Detail.START_AGAIN, None),)
    unticked = state_line(HomeState(ListeningState.STOPPED))
    assert unticked.title is Title.PICK
    assert (Detail.START_AGAIN, None) not in unticked.details


def test_suggestion_returns_to_the_last_app_still_playing() -> None:
    a, b, c = (AddableApp(key, key, True) for key in ("a", "b", "c"))
    view = PickerView(Picker(available=(a, b)), Commands())  # type: ignore[arg-type]
    assert view.suggested == a  # simultaneous discoveries keep display order
    view.follow(Picker(available=(a, b, c)))
    assert view.suggested == c
    view.follow(Picker(available=(a, b, replace(c, playing=False))))
    assert view.suggested == a
    view.follow(Picker(available=(b,)))
    assert view.suggested == b
    view.follow(Picker(available=(b,), per_app=False))
    assert view.suggested is None
