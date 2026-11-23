"""Home's views, as plain Python - no Qt (polyglotic-hq project 109's
structure, sections 5 and 7).

- **The state line** (today's hero card): `state_line` says what Home's
  first line shows - its tone, title, the details after it and its button
  - from the session's state (`HomeState`), with today's rules: Paused
  first (and how to resume); "Pick what to caption" while nothing is
  chosen and no session needs to be (DECISIONS.md #25; since 484 a new
  learner's first run captions everything the PC plays); otherwise the connection's state - signed
  out with Sign in in place of Pause (109's section 7); an update needed
  with what to do (polyglotic-hq 137); stopped with how to start again
  (polyglotic-hq 228); waiting to try again with why the server can't be
  reached, whose side that's on and what to do - check the internet, wait
  for us, try another network, set the clock (polyglotic-hq 251).
- **The app picker** (`Picker`, `PickerView`): the captioned apps' rows
  (at most `LIMIT`, DECISIONS.md #53), each with its window's language
  and my-speech mark; the apps with sound that could be added - greyed,
  with the reason, at 3 of 3; or everything the PC plays. With one app,
  everything else the PC plays can be captioned beside it, in a window of
  its own (polyglotic-hq DECISIONS.md #59): Windows leaves only one app
  out of a capture, so the switch is off with 2 or 3 apps, saying so,
  and while it's on no app can be added (the Add list greys, with the
  reason). The picker hands the learner's actions to `PickerCommands`,
  which `main` carries out; what it shows comes back through `follow`.

Holds apps' names, which stay on this PC; no caption text.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.listening.unreachable import Side, Unreachable, side
from polyglotic_desktop.core.releases.updates import UpdateNow
from polyglotic_desktop.ui_next.views.caption_window import LIMIT, ORIGINAL_ONLY
from polyglotic_desktop.ui_next.views.panels import Shared

SYSTEM = "system"
"""The key of everything the PC plays (today's `SOURCE_KEY_SYSTEM`)."""
MIC = "mic"
"""The key of my own speech's label (today's `SOURCE_KEY_MIC`)."""
EVERYTHING_ELSE = "everything_else"
"""The key of everything else the PC plays, beside one app
(`SOURCE_KEY_EVERYTHING_ELSE`)."""


# -- the state line -------------------------------------------------------------------


class ListeningState(StrEnum):
    """The listening session's state as Home shows it (today's
    `ConnectionState`'s values; `main` maps one onto the other)."""

    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    LISTENING = "listening"
    WAITING = "waiting"
    SERVER_BUSY = "server_busy"
    SIGN_IN_NEEDED = "sign_in_needed"
    UPDATE_NEEDED = "update_needed"
    MOVED = "moved"
    PLUS_ENDED = "plus_ended"
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    CROSS_BORDER_CONSENT_REQUIRED = "cross_border_consent_required"
    STOPPED = "stopped"


class Title(StrEnum):
    PAUSED = "paused"
    PICK = "pick"
    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    LISTENING = "listening"
    RECONNECTING = "reconnecting"
    SERVER_BUSY = "server_busy"
    NOT_SIGNED_IN = "not_signed_in"
    UPDATE_NEEDED = "update_needed"
    MOVED = "moved"
    PLUS_ENDED = "plus_ended"
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    CROSS_BORDER_CONSENT_REQUIRED = "cross_border_consent_required"
    STOPPED = "stopped"
    # waiting to try again: why the server can't be reached (251)
    CANT_REACH = "cant_reach"
    SERVER_RESTARTING = "server_restarting"
    SERVER_PROBLEM = "server_problem"
    BLOCKED = "blocked"
    NOT_SECURE = "not_secure"
    CLOCK = "clock"
    TOO_MANY_SESSIONS = "too_many_sessions"
    TOO_MANY_TRIES = "too_many_tries"
    MAINTENANCE = "maintenance"  # planned, and until when (319)


class Detail(StrEnum):
    RESUME = "resume"  # how: Ctrl+Alt+P, or the tray
    WINDOWS_PAUSED = "windows_paused"  # every window hidden too long: show them
    SIGN_IN = "sign_in"
    NOTHING_CHOSEN = "nothing_chosen"
    RETRY_IN = "retry_in"  # seconds
    HELP_CHECKS = "help_checks"  # not connected: Help's check says why (176)
    CAPTIONS_IN = "captions_in"  # the windows' languages
    ORIGINAL_ONLY = "original_only"  # every window: no translation
    SPEECH_NOT_CAPTIONED = "speech_not_captioned"
    # update needed - what to do (polyglotic-hq 137)
    UPDATING = "updating"  # getting it; restarts by itself
    RESTART_TO_INSTALL = "restart_to_install"  # downloaded: quit and start again
    NO_UPDATE_YET = "no_update_yet"  # looks again; or ask us for the installer
    INSTALL_BY_HAND = "install_by_hand"  # this copy can't update itself
    UPDATE_FROM_STORE = "update_from_store"  # the Microsoft Store updates it (0056)
    # Plus ended (polyglotic-hq 185): what stays, and what to do
    WORDS_STAY = "words_stay"  # captions stopped; words and lookups stay (235)
    # stopped (polyglotic-hq 228): start again; Help if it keeps stopping
    START_AGAIN = "start_again"
    # waiting to try again (251): whose side it's on, and what to do
    CHECK_INTERNET = "check_internet"  # offline: check it; if it works, it's us
    INTERNET_OR_US = "internet_or_us"  # no telling: check it, else we're down
    OURS = "ours"  # not your internet: captions come back by themselves
    BACK_IN_A_MOMENT = "back_in_a_moment"  # restarting
    NETWORK_BLOCKS = "network_blocks"  # a firewall or proxy: another network
    NETWORK_IN_THE_WAY = "network_in_the_way"  # TLS: Wi-Fi sign-in, antivirus
    SET_THE_CLOCK = "set_the_clock"  # the date it says is wrong: set it automatically
    CERT_IN_THE_WAY = (
        "cert_in_the_way"  # an out-of-date certificate: antivirus, VPN (313)
    )
    QUIT_ON_ANOTHER_PC = "quit_on_another_pc"  # too many sessions: starts here then
    TRIES_SOON = "tries_soon"  # too many failed sign-ins from this network
    MAINTENANCE = "maintenance"  # down for planned maintenance; back by themselves


class Tone(StrEnum):
    """The state's colour: the theme's SUCCESS, WARNING, DANGER or TEXT_FAINT."""

    GOOD = "SUCCESS"
    WAIT = "WARNING"
    BAD = "DANGER"
    QUIET = "TEXT_FAINT"


_BY_CONNECTION = {
    ListeningState.NOT_CONNECTED: (Tone.QUIET, Title.NOT_CONNECTED),
    ListeningState.CONNECTING: (Tone.WAIT, Title.CONNECTING),
    ListeningState.LISTENING: (Tone.GOOD, Title.LISTENING),
    ListeningState.WAITING: (Tone.WAIT, Title.RECONNECTING),
    ListeningState.SERVER_BUSY: (Tone.WAIT, Title.SERVER_BUSY),
    ListeningState.SIGN_IN_NEEDED: (Tone.BAD, Title.NOT_SIGNED_IN),
    ListeningState.UPDATE_NEEDED: (Tone.BAD, Title.UPDATE_NEEDED),
    ListeningState.MOVED: (Tone.WAIT, Title.MOVED),
    ListeningState.PLUS_ENDED: (Tone.BAD, Title.PLUS_ENDED),
    ListeningState.ALLOWANCE_EXHAUSTED: (Tone.BAD, Title.ALLOWANCE_EXHAUSTED),
    ListeningState.CROSS_BORDER_CONSENT_REQUIRED: (
        Tone.BAD,
        Title.CROSS_BORDER_CONSENT_REQUIRED,
    ),
    ListeningState.STOPPED: (Tone.BAD, Title.STOPPED),
}


_UNREACHABLE: dict[Unreachable, tuple[Title, Detail]] = {
    Unreachable.OFFLINE: (Title.CANT_REACH, Detail.CHECK_INTERNET),
    Unreachable.NO_ANSWER: (Title.CANT_REACH, Detail.INTERNET_OR_US),
    # what it knows: not the learner's internet, and no restart said (368)
    Unreachable.DOWN: (Title.CANT_REACH, Detail.OURS),
    Unreachable.RESTARTING: (Title.SERVER_RESTARTING, Detail.BACK_IN_A_MOMENT),
    Unreachable.SERVER_ERROR: (Title.SERVER_PROBLEM, Detail.OURS),
    Unreachable.BLOCKED: (Title.BLOCKED, Detail.NETWORK_BLOCKS),
    Unreachable.NOT_SECURE: (Title.NOT_SECURE, Detail.NETWORK_IN_THE_WAY),
    Unreachable.CLOCK: (Title.CLOCK, Detail.SET_THE_CLOCK),
    Unreachable.OUT_OF_DATE: (Title.NOT_SECURE, Detail.CERT_IN_THE_WAY),
    Unreachable.TOO_MANY_SESSIONS: (Title.TOO_MANY_SESSIONS, Detail.QUIT_ON_ANOTHER_PC),
    Unreachable.TOO_MANY_TRIES: (Title.TOO_MANY_TRIES, Detail.TRIES_SOON),
    Unreachable.MAINTENANCE: (Title.MAINTENANCE, Detail.MAINTENANCE),
}
"""Waiting to try again: what Home says, by why the server can't be reached."""

STATUS_PAGE_HELPS = frozenset(
    {
        Unreachable.NO_ANSWER,
        Unreachable.DOWN,
        Unreachable.RESTARTING,
        Unreachable.SERVER_ERROR,
        Unreachable.MAINTENANCE,
    }
)
"""Why the server can't be reached where the site's status page can say
more: the problem is ours, or may be (polyglotic-hq 540, 563). Not this
PC offline (the page won't open either), nor its network or clock in the
way, nor the account's refusals."""


_UPDATE_DETAIL = {
    None: Detail.UPDATING,
    UpdateNow.RESTARTING: Detail.UPDATING,
    UpdateNow.DOWNLOADED: Detail.RESTART_TO_INSTALL,
    UpdateNow.NONE_YET: Detail.NO_UPDATE_YET,
    UpdateNow.NOT_INSTALLED: Detail.INSTALL_BY_HAND,
    UpdateNow.FROM_STORE: Detail.UPDATE_FROM_STORE,
}
"""Update needed: what Home says to do, by what the updater found."""


@dataclass(frozen=True)
class HomeState:
    """What Home's state line is made from. `chosen`: apps, or everything
    the PC plays, are picked. `languages`: the caption windows'
    translation languages; `windows`: how many there are. `speech_shown`:
    a window shows my speech. `retry_at`: when the next try to reconnect
    is, on the clock `state_line`'s `now` reads - so the line counts down
    to it, as the caption windows' notice does (polyglotic-hq 133)."""

    connection: ListeningState = ListeningState.NOT_CONNECTED
    retry_at: float | None = None
    paused: bool = False
    chosen: bool = False
    languages: tuple[str, ...] = ()
    windows: int = 0
    speech_shown: bool = False
    update_found: UpdateNow | None = None
    """What the updater found after the server refused this version (None:
    still looking)."""
    failing: bool = False
    """Captions failing on the server (core.listening.failing): the state
    isn't all well, whatever the connection says (184's QA, 176)."""
    unreachable: Unreachable | None = None
    """Waiting to try again: why the server can't be reached, if it's
    known (core.listening.unreachable; polyglotic-hq 251)."""
    windows_paused_after: int | None = None
    """Every captioned app's window paused after being hidden: the longest
    it was hidden before it paused (minutes; `every_window_paused`); None
    while any listens (polyglotic-hq 335, 368)."""


class Action(StrEnum):
    """The state line's button: Pause captions / Resume, Sign in, Get
    Plus, or none while nothing is captioned."""

    NONE = "none"
    PAUSE = "pause"
    SIGN_IN = "sign_in"
    GET_PLUS = "get_plus"
    UPGRADE = "upgrade"
    REVIEW_CONSENT = "review_consent"


@dataclass(frozen=True)
class StateLine:
    tone: Tone
    title: Title
    details: tuple[tuple[Detail, object], ...] = ()
    action: Action = Action.PAUSE
    status_page: bool = False
    """The site's status page is offered (`STATUS_PAGE_HELPS`)."""

    @property
    def pulse(self) -> bool:
        """The state's dot breathes while the app is trying to connect - it
        is doing something (151's W8; 176)."""
        return self.title in TRYING


TRYING = (
    Title.CONNECTING,
    Title.RECONNECTING,
    Title.SERVER_BUSY,
    *(title for title, _ in _UNREACHABLE.values()),
)
"""The titles said while the app is trying to connect, or waiting to try again."""


def retry_in(state: HomeState, now: float) -> int | None:
    """Whole seconds until the next try to reconnect, while waiting for it
    - None once it's due (it tries then), as the caption windows count."""
    waiting = (ListeningState.WAITING, ListeningState.SERVER_BUSY)
    if state.connection not in waiting or state.retry_at is None:
        return None
    return max(0, round(state.retry_at - now)) or None


def state_line(state: HomeState, now: float = 0.0) -> StateLine:
    """Home's first line: Paused before anything, with how to resume; then
    "Pick what to caption" while nothing is chosen and the session's state
    doesn't say more (listening to the mic alone, no session needed, or
    stopped after the last app was unticked); then the connection's state
    - with the details that apply. Signed out, it says what's needed, and
    its button is Sign in (109's section 7). Stopped, it says to start
    again, and where to look if it keeps stopping (228). `now`: the time on
    `retry_at`'s clock."""
    nothing_chosen = not state.chosen and state.connection in (
        ListeningState.LISTENING,
        ListeningState.NOT_CONNECTED,
        ListeningState.STOPPED,
    )
    if state.paused:
        return StateLine(Tone.WAIT, Title.PAUSED, ((Detail.RESUME, None),))
    if nothing_chosen:
        tone, title = Tone.WAIT, Title.PICK
    else:
        tone, title = _BY_CONNECTION[state.connection]
    if title is Title.LISTENING and state.windows_paused_after is not None:
        # nothing is sent: not "Listening" (336's Q2, 368) - and how to go on
        paused = ((Detail.WINDOWS_PAUSED, state.windows_paused_after),)
        return StateLine(Tone.WAIT, Title.PAUSED, paused)
    if title is Title.NOT_SIGNED_IN:
        return StateLine(tone, title, ((Detail.SIGN_IN, None),), Action.SIGN_IN)
    action = Action.PAUSE if state.chosen else Action.NONE
    if title is Title.UPDATE_NEEDED:  # what to do, and nothing else
        return StateLine(
            tone, title, ((_UPDATE_DETAIL[state.update_found], None),), action
        )
    if title is Title.PLUS_ENDED:  # what ended, what stays, what to do (185)
        return StateLine(tone, title, ((Detail.WORDS_STAY, None),), Action.GET_PLUS)
    if title is Title.ALLOWANCE_EXHAUSTED:
        return StateLine(tone, title, (), Action.UPGRADE)
    if title is Title.CROSS_BORDER_CONSENT_REQUIRED:
        return StateLine(tone, title, (), Action.REVIEW_CONSENT)
    if title is Title.SERVER_BUSY:
        return StateLine(tone, title, (), action)
    if title is Title.STOPPED:  # what to do, as every other bad state (228)
        return StateLine(tone, title, ((Detail.START_AGAIN, None),), action)
    if title is Title.RECONNECTING and state.unreachable is not None:
        return _unreachable(state.unreachable, retry_in(state, now), action)
    if state.failing and tone is Tone.GOOD:  # the banner says why
        tone = Tone.WAIT
    details: list[tuple[Detail, object]] = []
    if nothing_chosen:
        details.append((Detail.NOTHING_CHOSEN, None))
    if title is Title.NOT_CONNECTED:  # a next step (135's finding 14; 176)
        details.append((Detail.HELP_CHECKS, None))
    seconds = retry_in(state, now)
    if seconds is not None:
        details.append((Detail.RETRY_IN, seconds))
    if state.languages:
        details.append((Detail.CAPTIONS_IN, state.languages))
    elif state.windows:
        details.append((Detail.ORIGINAL_ONLY, None))
    if not state.speech_shown:
        details.append((Detail.SPEECH_NOT_CAPTIONED, None))
    return StateLine(tone, title, tuple(details), action)


def every_window_paused(rows: Sequence["AppRow"]) -> int | None:
    """The longest any captioned app's window was hidden before it paused
    (minutes), when every one of them is paused - nothing is sent then;
    None while any listens, or nothing is captioned (polyglotic-hq 368)."""
    if not rows or any(row.sight is not Sight.PAUSED for row in rows):
        return None
    return max((row.paused_after or 0 for row in rows), default=0)


def unreachable_line(why: Unreachable) -> tuple[Title, Detail]:
    """What Home says of `why`: its title, and whose side and what to do -
    Help's check says the same (251)."""
    return _UNREACHABLE[why]


def _unreachable(
    why: Unreachable, seconds: int | None, action: Action = Action.PAUSE
) -> StateLine:
    """Waiting to try again, and why the server can't be reached: what's
    wrong (the title), whose side it's on and what to do, then the
    countdown - and nothing else: what's captioned can wait (251). The
    learner's side is a problem to fix; ours, or no telling, a wait."""
    title, detail = _UNREACHABLE[why]
    tone = Tone.BAD if side(why) is Side.YOURS else Tone.WAIT
    details: list[tuple[Detail, object]] = [(detail, None)]
    # a planned window says until when, in the title: a countdown to the
    # next try would be noise for half an hour (319)
    if seconds is not None and why is not Unreachable.MAINTENANCE:
        details.append((Detail.RETRY_IN, seconds))
    return StateLine(
        tone, title, tuple(details), action, status_page=why in STATUS_PAGE_HELPS
    )


# -- the app picker -------------------------------------------------------------------


class AppStatus(StrEnum):
    PLAYING = "playing"
    QUIET = "quiet"
    NOT_OPEN = "not_open"  # captioned when it opens
    EVERYTHING = "everything"  # the PC's whole sound
    EVERYTHING_ELSE = "everything_else"  # the PC's sound but the app's


@dataclass(frozen=True, slots=True)
class AppRow:
    """A captioned app's row: its key (the app's name, SYSTEM or
    EVERYTHING_ELSE), its label and colour as the learner set them,
    whether it's playing, and
    its window's language (or ORIGINAL_ONLY) and my-speech mark; and, its
    window hidden, whether it's captioning still or paused, and after how
    many minutes (polyglotic-hq 335)."""

    key: str
    label: str
    colour: str
    status: AppStatus
    translate_into: str = "en"
    show_mic: bool = False
    sight: Sight = Sight.SHOWN
    paused_after: int | None = None

    @property
    def original_only(self) -> bool:
        return self.translate_into == ORIGINAL_ONLY


@dataclass(frozen=True, slots=True)
class AddableApp:
    """An app with sound open that isn't captioned: its name (the key) and
    what it's called on screen."""

    name: str
    title: str
    playing: bool


class Sample(StrEnum):
    """Home's sample (polyglotic-hq 176): a short recording in the language
    learned, played and captioned by the app - offered while nothing is
    captioned and no app is playing, so the first caption never waits on
    the learner finding something to play."""

    NONE = "none"
    """Not offered: something is captioned or playing, or there's no
    sample in the language learned."""
    OFFERED = "offered"
    PLAYING = "playing"
    """On: its caption window shows, until stopped or an app is added."""
    ENDED = "ended"
    """Played to its end: offered again, its window kept for lookups, and
    the next step said - an app of the learner's own (208, 203's option B)."""


@dataclass(frozen=True)
class Picker:
    """What the picker shows. `per_app`: this PC can caption one app alone
    (not on Windows 10 before version 2004, nor where trying it failed:
    everything the PC plays is the only choice). `fell_back`: it was tried
    here and failed - the note says so, with "Try apps again" (decision
    0076). `hidden`: the caption windows are hidden (Ctrl+Alt+H).
    `everything_else`: everything else the PC plays is captioned beside
    the one app - its row is after the app's in `captioned`."""

    captioned: tuple[AppRow, ...] = ()
    available: tuple[AddableApp, ...] = ()
    whole_system: bool = False
    per_app: bool = True
    fell_back: bool = False
    hidden: bool = False
    limit: int = field(default=LIMIT)
    you: AppRow | None = None
    """My speech's label and colour ("You", blue, unless the learner
    changed them) - today's Labels card had it beside the apps'."""
    everything_else: bool = False
    sample: Sample = Sample.NONE
    listening: bool = True  # the session can currently caption the selected sources

    @property
    def apps(self) -> tuple[AppRow, ...]:
        """The rows of apps captioned on their own."""
        return tuple(
            row for row in self.captioned if row.key not in (SYSTEM, EVERYTHING_ELSE)
        )

    @property
    def full(self) -> bool:
        """At the limit - 3 apps, or one beside everything else: the Add
        list greys, with the reason."""
        if self.whole_system:
            return False
        return len(self.apps) >= self.limit or self.everything_else

    @property
    def everything_else_allowed(self) -> bool:
        """Everything else can be turned on: one app is captioned on its
        own (Windows leaves only one app out of a capture)."""
        return self.per_app and not self.whole_system and len(self.apps) == 1

    @property
    def speech_shown_in(self) -> tuple[str, ...]:
        """The labels of the windows that show my speech."""
        return tuple(row.label for row in self.captioned if row.show_mic)


def sample_state(
    exists: bool,
    on: bool,
    chosen: bool,
    available: tuple[AddableApp, ...],
    ended: bool = False,
) -> Sample:
    """What Home says of the sample: on while it's on; ended once it has
    played to its end (`ended`, until an app is chosen); offered while
    nothing is chosen to caption and no app with sound is playing - if
    there's a sample in the language learned (`exists`)."""
    if not exists or chosen:
        return Sample.NONE
    if on:
        return Sample.PLAYING
    if ended:
        return Sample.ENDED
    if any(app.playing for app in available):
        return Sample.NONE
    return Sample.OFFERED


GOOD_FIRST_SESSION = 20
"""Finished captions shown in one run that make a good session - a few
minutes of talk - before "Start with Windows?" is asked (polyglotic-hq
176; 160's day 2)."""


def offer_start_with_windows(
    captions: int, asked: bool, enabled: bool, possible: bool
) -> bool:
    """Whether Home asks "Start Polyglotic with Windows?" now: after a
    good session (`captions` finished captions shown in this run), once
    ever (`asked`), not if it already starts with Windows (`enabled`), and
    only where it can (`possible`: the installed app, not one run from
    source)."""
    return possible and not asked and not enabled and captions >= GOOD_FIRST_SESSION


def addable(
    found: list[tuple[str, str, bool]], captioned: tuple[str, ...]
) -> tuple[AddableApp, ...]:
    """The apps with sound (name, title, playing) that could be added:
    not captioned, each name once (two of an app are one choice), playing
    first, then by name."""
    seen: dict[str, AddableApp] = {}
    for name, title, playing in found:
        if name in captioned:
            continue
        before = seen.get(name)
        if before is None or (playing and not before.playing):
            seen[name] = AddableApp(name, title, playing)
    return tuple(sorted(seen.values(), key=lambda a: (not a.playing, a.title.lower())))


class PickerCommands(Protocol):
    """What the picker asks for; `main` carries it out."""

    def start_captioning(self, app: str | None) -> None: ...
    def add(self, name: str) -> None: ...
    def remove(self, key: str) -> None: ...
    def rename(self, key: str, text: str) -> None: ...
    def recolour(self, key: str, colour: str) -> None: ...
    def show_window(self, key: str) -> None: ...
    def open_transcript(self, key: str) -> None: ...
    def set_whole_system(self, on: bool) -> None: ...
    def set_everything_else(self, on: bool) -> None: ...
    def set_show_mic(self, key: str, on: bool) -> None: ...
    def set_translate_into(self, key: str, code: str) -> None: ...
    def refresh(self) -> None: ...
    def try_sample(self, on: bool) -> None: ...
    def try_apps_again(self) -> None: ...


class PickerView(Shared[Picker]):
    """The picker: what it shows (`follow`) and the learner's actions,
    handed to `commands` - a 4th app isn't asked for."""

    def __init__(self, value: Picker, commands: PickerCommands) -> None:
        super().__init__(value)
        self.commands = commands
        self._recent: list[str] = []
        self._remember(value)

    def _remember(self, value: Picker) -> None:
        """Most recently observed starting first. Simultaneous starts keep
        the picker's stable display order. Forget sources once quiet."""
        playing = [app.name for app in value.available if app.playing]
        self._recent = [name for name in playing if name not in self._recent] + [
            name for name in self._recent if name in playing
        ]

    def follow(self, value: Picker) -> None:
        if value.available != self.value.available:
            self._remember(value)
        super().follow(value)

    @property
    def suggested(self) -> AddableApp | None:
        if self._recent and self.value.per_app:
            return next(
                (a for a in self.value.available if a.name == self._recent[0]), None
            )
        return None

    def start(self) -> None:
        if self.value.captioned or self.value.sample is Sample.PLAYING:
            return
        app = self.suggested
        self.commands.start_captioning(app.name if app else None)

    def add(self, name: str) -> None:
        if not self.value.full:
            self.commands.add(name)

    def remove(self, key: str) -> None:
        self.commands.remove(key)

    def rename(self, key: str, text: str) -> None:
        self.commands.rename(key, text.strip())

    def recolour(self, key: str, colour: str) -> None:
        self.commands.recolour(key, colour)

    def show_window(self, key: str) -> None:
        """Its window shown - hidden, every window shown again (and any
        paused listens again: 335)."""
        self.commands.show_window(key)

    def open_transcript(self, key: str) -> None:
        self.commands.open_transcript(key)

    def set_whole_system(self, on: bool) -> None:
        if on != self.value.whole_system:
            self.commands.set_whole_system(on)

    def set_everything_else(self, on: bool) -> None:
        """On with one app only; off any time."""
        if on != self.value.everything_else and (
            not on or self.value.everything_else_allowed
        ):
            self.commands.set_everything_else(on)

    def set_show_mic(self, key: str, on: bool) -> None:
        self.commands.set_show_mic(key, on)

    def set_translate_into(self, key: str, code: str) -> None:
        self.commands.set_translate_into(key, code)

    def refresh(self) -> None:
        self.commands.refresh()

    def try_sample(self, on: bool) -> None:
        """The sample on (where offered, or again once it has ended) or off."""
        if on and self.value.sample in (Sample.OFFERED, Sample.ENDED):
            self.commands.try_sample(True)
        elif not on and self.value.sample is Sample.PLAYING:
            self.commands.try_sample(False)

    def try_apps_again(self) -> None:
        """Capturing apps one by one tried again, where it failed (0076)."""
        if self.value.fell_back:
            self.commands.try_apps_again()
