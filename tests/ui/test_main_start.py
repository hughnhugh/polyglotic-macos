"""At start and after signing in, listening comes before the start-up sync
(`main.listen_then_sync`; polyglotic-hq project 042, Low 9): a sync
session's `hello` already out when listening began made two sessions on the
server for a moment, and with another PC of the account listening, one was
refused `too_many_sessions`.

And a listening session opens only once something is chosen to caption
(`main.captioning`, `main.follow_choice`; project 061, from 051): the first
run starts paused (DECISIONS.md #25), and a session then held one of the
account's places on the server for nothing."""

import time
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.fake_server import FakeServer, wait_until
from tests.test_connection import AT, WORD, App
from tests.test_session import SETTINGS
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.core.shared import WordSaved
from polyglotic_desktop.main import captioning, follow_choice, listen_then_sync
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.settings import AppSettings

CHOSEN = AppSettings(whole_system=False, apps=("Web Browser",))
NOTHING = AppSettings(whole_system=False)


class Recording:
    """A connection that only records what's asked of it, in order."""

    def __init__(self, listening: object = None) -> None:
        self.listening = listening
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def listen(self) -> None:
        self.calls.append("listen")
        self.listening = object()

    def stop_listening(self) -> None:
        self.calls.append("stop listening")
        self.listening = None


def test_listening_is_asked_for_before_the_sync() -> None:
    connection = Recording()
    assert listen_then_sync(connection, connection.listen, CHOSEN)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start"]


def test_already_listening_it_isnt_asked_for_again() -> None:
    connection = Recording(listening=object())
    listen_then_sync(connection, connection.listen, CHOSEN)  # type: ignore[arg-type]
    assert connection.calls == ["start"]


def test_with_nothing_chosen_to_caption_only_the_sync() -> None:
    """Nothing picked - no app, not everything the PC plays, not the mic:
    no listening session; `start` syncs learning in a sync session."""
    assert not captioning(NOTHING)
    assert captioning(CHOSEN)
    assert captioning(AppSettings(whole_system=True))
    assert captioning(AppSettings(caption_mic=True))  # the mic alone is captioned
    connection = Recording()
    assert not listen_then_sync(connection, connection.listen, NOTHING)  # type: ignore[arg-type]
    assert connection.calls == ["start"]


def test_the_session_opens_once_something_is_chosen_and_closes_when_nothing_is() -> (
    None
):
    connection = Recording()
    follow_choice(connection, NOTHING, connection.listen)  # type: ignore[arg-type]
    assert connection.calls == []  # any other setting changed: nothing to do
    follow_choice(connection, CHOSEN, connection.listen)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start"]
    both = AppSettings(whole_system=False, apps=("Web Browser",), caption_mic=True)
    follow_choice(connection, both, connection.listen)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start"]  # already listening
    follow_choice(connection, NOTHING, connection.listen)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start", "stop listening"]


def test_dictation_opens_a_session_while_it_needs_one_and_lets_it_go() -> None:
    """Nothing captioned: the dictation key opens a listening session
    (polyglotic-hq 283), which closes once dictation no longer needs it -
    and a change of settings meanwhile doesn't close it."""
    connection = Recording()
    follow_choice(connection, NOTHING, connection.listen, dictating=True)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start"]
    follow_choice(connection, NOTHING, connection.listen, dictating=True)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start"]  # a setting changed meanwhile
    follow_choice(connection, NOTHING, connection.listen, dictating=False)  # type: ignore[arg-type]
    assert connection.calls == ["listen", "start", "stop listening"]
    # captioning, dictation letting go changes nothing
    follow_choice(connection, CHOSEN, connection.listen)  # type: ignore[arg-type]
    follow_choice(connection, CHOSEN, connection.listen, dictating=False)  # type: ignore[arg-type]
    assert connection.calls[-1] == "start"


def test_a_session_opened_by_picking_an_app_says_connecting_at_once(
    qapp: QApplication,
) -> None:
    """Home said "Stopped" - the session closed when the last app went -
    for the moment after + until the new session's first word (145)."""
    desktop = DesktopApp(
        MemorySettingsStore({"whole_system": False}), None, FakeAppList()
    )
    connection = Recording()
    desktop.set_connection(ConnectionState.STOPPED)  # the last app went
    follow_choice(connection, CHOSEN, connection.listen, desktop)  # type: ignore[arg-type]
    assert desktop.connection is ConnectionState.CONNECTING
    connection = Recording()
    desktop.set_connection(ConnectionState.SIGN_IN_NEEDED)  # says what's needed
    follow_choice(connection, CHOSEN, connection.listen, desktop)  # type: ignore[arg-type]
    assert desktop.connection is ConnectionState.SIGN_IN_NEEDED
    desktop.close()


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def test_only_the_listening_session_opens_and_it_syncs(server: FakeServer) -> None:
    """Against a stand-in server: one session, `listen`, never a `sync` -
    and what waited goes out on it, learning synced."""
    app = App(server.url)
    app.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    app.exchange.learning(WordSaved(WORD, AT))

    def listen() -> None:
        app.connection.start_listening(SETTINGS, app.speech.take)

    listen_then_sync(app.connection, listen, CHOSEN)

    wait_until(lambda: "learning_sync" in server.types())
    time.sleep(0.3)  # a sync session, had one been started, would be here by now
    assert [hello["purpose"] for hello in server.hellos] == ["listen"]
    assert server.connections == 1
    assert {"consent", "learning", "learning_sync"} <= set(server.types())
    app.connection.close()


def test_nothing_chosen_only_a_sync_session_opens(server: FakeServer) -> None:
    """Against a stand-in server, the first run's paused start: one sync
    session, which sends what waited and syncs learning, then closes -
    never a listening session holding a place."""
    app = App(server.url)
    app.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    app.exchange.learning(WordSaved(WORD, AT))

    def listen() -> None:
        app.connection.start_listening(SETTINGS, app.speech.take)

    assert not listen_then_sync(app.connection, listen, NOTHING)

    wait_until(lambda: "learning_sync" in server.types())
    wait_until(lambda: app.connection.idle)
    assert [hello["purpose"] for hello in server.hellos] == ["sync"]
    assert app.connection.listening is None
    assert {"consent", "learning", "learning_sync"} <= set(server.types())
    app.connection.close()
