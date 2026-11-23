"""The "no captions?" check's rule (project 096): five links, in order, the
first broken one named and those after it waiting. Made-up facts only."""

from polyglotic_desktop.core.listening.check import (
    Facts,
    Problem,
    SourceActivity,
    Status,
    Step,
    Ticked,
    run_check,
    summary,
)
from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM, SourceId
from polyglotic_desktop.core.listening.unreachable import Unreachable

APP = SourceId("app-1")
NOW = 1000.0
DISCORD = Ticked(APP, "Discord", "app")


def facts(**changes: object) -> Facts:
    """Everything working: one app ticked, heard 5 s ago, a caption 3 s ago."""
    base: dict[str, object] = {
        "now": NOW,
        "connection": "listening",
        "paused": False,
        "overlays_hidden": False,
        "ticked": [DISCORD],
        "activity": {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 5, NOW - 6)},
        "last_caption": NOW - 3,
    }
    base.update(changes)
    return Facts(**base)  # type: ignore[arg-type]


def statuses(f: Facts) -> list[str]:
    return [link.status.value for link in run_check(f)]


def first_broken(f: Facts) -> tuple[Step, Problem | None]:
    [link] = [x for x in run_check(f) if x.status is Status.BROKEN]
    return link.step, link.problem


def test_all_five_links_ok_when_everything_works() -> None:
    assert statuses(facts()) == ["ok"] * 5


def test_a_broken_link_stops_the_chain_and_the_rest_wait() -> None:
    f = facts(connection="sign_in_needed")
    assert statuses(f) == ["broken", "waiting", "waiting", "waiting", "waiting"]
    assert first_broken(f) == (Step.CONNECTED, Problem.SIGN_IN_NEEDED)


def test_connecting_is_waiting_not_broken() -> None:
    assert statuses(facts(connection="connecting"))[:2] == ["waiting", "waiting"]
    assert first_broken(facts(connection="update_needed"))[1] is Problem.UPDATE_NEEDED
    # 4009: Plus ended - said as that, not "not connected" (polyglotic-hq 185)
    assert first_broken(facts(connection="plus_ended"))[1] is Problem.PLUS_ENDED
    assert first_broken(facts(connection="stopped"))[1] is Problem.NOT_CONNECTED


def test_nothing_ticked() -> None:
    assert first_broken(facts(ticked=[])) == (Step.TICKED, Problem.NOTHING_TICKED)


def test_a_quiet_app_is_named_after_30_seconds_and_waits_before() -> None:
    quiet = {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 100, NOW - 100)}
    assert first_broken(facts(activity=quiet)) == (Step.SOUND, Problem.APP_QUIET)
    just_started = {APP: SourceActivity(NOW - 10)}
    assert statuses(facts(activity=just_started))[2] == "waiting"


def test_a_ticked_app_that_is_not_open() -> None:
    assert first_broken(facts(activity={})) == (Step.SOUND, Problem.APP_NOT_OPEN)


def test_quiet_system_and_mic_have_their_own_fixes() -> None:
    system = Ticked(WHOLE_SYSTEM, "This PC", "system")
    mic = Ticked(MIC, "You", "mic")
    old = SourceActivity(NOW - 300)
    assert first_broken(facts(ticked=[system], activity={WHOLE_SYSTEM: old})) == (
        Step.SOUND,
        Problem.SYSTEM_QUIET,
    )
    assert first_broken(facts(ticked=[mic], activity={MIC: old})) == (
        Step.SOUND,
        Problem.MIC_QUIET,
    )


def test_a_source_the_os_does_not_allow_is_named_at_once() -> None:
    """polyglotic-hq 411: macOS records silence when the learner hasn't
    allowed it. Said at once - waiting 30 s for sound won't bring any - with
    the Mac's own fix: system audio for an app or the Mac, the microphone
    for the mic."""
    refused = SourceActivity(NOW - 12, not_allowed=True)
    assert first_broken(facts(activity={APP: refused})) == (
        Step.SOUND,
        Problem.SOUND_NOT_ALLOWED,
    )
    system = Ticked(WHOLE_SYSTEM, "This Mac", "system")
    assert (
        first_broken(facts(ticked=[system], activity={WHOLE_SYSTEM: refused}))[1]
        is Problem.SOUND_NOT_ALLOWED
    )
    mic = Ticked(MIC, "You", "mic")
    assert first_broken(facts(ticked=[mic], activity={MIC: refused}))[1] is (
        Problem.MIC_NOT_ALLOWED
    )


def test_sound_from_another_source_counts_over_one_not_allowed() -> None:
    mic = Ticked(MIC, "You", "mic")
    heard = SourceActivity(NOW - 300, NOW - 200, NOW - 5, NOW - 6)
    refused = SourceActivity(NOW - 300, not_allowed=True)
    f = facts(ticked=[DISCORD, mic], activity={APP: heard, MIC: refused})
    assert statuses(f) == ["ok"] * 5


def test_a_capture_that_stopped_is_named_at_once_even_beside_sound() -> None:
    """polyglotic-hq 557 (529's B1): a capture whose thread died said
    "{name} is quiet" - nothing playing - while nothing could be heard from
    it. A stopped capture is its own problem, named at once, and even when
    another source is heard: that source's captions coming don't bring
    this one's back."""
    stopped = SourceActivity(NOW - 300, NOW - 200, NOW - 40, NOW - 40, stopped=True)
    assert first_broken(facts(activity={APP: stopped})) == (
        Step.SOUND,
        Problem.CAPTURE_STOPPED,
    )
    [link] = [x for x in run_check(facts(activity={APP: stopped})) if x.problem]
    assert link.source == "Discord"
    mic = Ticked(MIC, "You", "mic")
    heard = SourceActivity(NOW - 300, NOW - 200, NOW - 5, NOW - 6)
    f = facts(ticked=[mic, DISCORD], activity={MIC: heard, APP: stopped})
    assert first_broken(f) == (Step.SOUND, Problem.CAPTURE_STOPPED)
    assert "sound: broken (capture_stopped)" in summary(run_check(f))
    # the mic's own words, as for a mic not allowed: its name is "You"
    f = facts(ticked=[mic], activity={MIC: stopped})
    assert first_broken(f) == (Step.SOUND, Problem.MIC_STOPPED)


def test_sound_without_speech() -> None:
    music = {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 5, NOW - 100)}
    assert first_broken(facts(activity=music)) == (Step.SPEECH, Problem.NO_SPEECH)
    new_sound = {APP: SourceActivity(NOW - 300, NOW - 10, NOW - 5, None)}
    assert statuses(facts(activity=new_sound))[3] == "waiting"


def test_speech_but_no_caption_names_pause_or_hidden_overlays() -> None:
    spoke = {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 20, NOW - 20)}
    assert first_broken(facts(activity=spoke, last_caption=None, paused=True)) == (
        Step.CAPTIONS,
        Problem.PAUSED,
    )
    hidden = facts(activity=spoke, last_caption=None, overlays_hidden=True)
    assert first_broken(hidden)[1] is Problem.OVERLAYS_HIDDEN
    old = facts(activity=spoke, last_caption=NOW - 90)
    assert first_broken(old)[1] is Problem.NO_CAPTIONS


def test_a_caption_on_its_way_is_waiting() -> None:
    fresh = {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 2, NOW - 2)}
    assert statuses(facts(activity=fresh, last_caption=None))[4] == "waiting"


def test_the_summary_is_ticks_and_crosses_with_no_names() -> None:
    quiet = {APP: SourceActivity(NOW - 300, NOW - 200, NOW - 100, NOW - 100)}
    text = summary(run_check(facts(activity=quiet)))
    assert text.splitlines() == [
        "connected: ok",
        "ticked: ok",
        "sound: broken (app_quiet)",
        "speech: waiting",
        "captions: waiting",
    ]
    assert "Discord" not in text


def test_captions_failing_on_the_server_is_the_broken_link() -> None:
    """polyglotic-hq 184: the caption windows and Home said "Captions failing
    on the server" while the check showed five ticks - a caption drawn in
    the last minute counted as captions working."""
    assert statuses(facts(failing=True)) == ["ok", "ok", "ok", "ok", "broken"]
    assert first_broken(facts(failing=True)) == (Step.CAPTIONS, Problem.SERVER_FAILING)
    assert "captions: broken (server_failing)" in summary(
        run_check(facts(failing=True))
    )
    assert statuses(facts(failing=False)) == ["ok"] * 5


def test_waiting_to_try_again_says_why_the_server_cant_be_reached() -> None:
    """Help's check said "Connecting to the server..." whatever the cause,
    while Home said it (polyglotic-hq 251). Known, it's the broken link -
    with its cause, in the report too."""
    f = facts(connection="waiting", unreachable=Unreachable.DOWN)
    [link, *rest] = run_check(f)
    assert (link.status, link.problem, link.cause) == (
        Status.BROKEN,
        Problem.SERVER_UNREACHABLE,
        Unreachable.DOWN,
    )
    assert {x.status for x in rest} == {Status.WAITING}
    assert summary(run_check(f)).splitlines()[0] == (
        "connected: broken (server_unreachable: down)"
    )
    # not known yet (a first try, a dropped connection): still waiting
    assert statuses(facts(connection="waiting"))[0] == "waiting"


def test_a_busy_server_is_busy_not_not_connected() -> None:
    """It read "Not connected to the server - quit from the tray and start
    Polyglotic again"; a full server takes it back by itself (208)."""
    assert first_broken(facts(connection="server_busy")) == (
        Step.CONNECTED,
        Problem.SERVER_BUSY,
    )
