"""`main`'s wiring of the connection's data (project 028), offscreen, with
the sample dictionary and an outbox in memory: the sign-in dialog's
problems from the connection's answers; statuses and saved words from the
server applied on the Qt thread and not sent back; deleting here only
when asked; finished days handed over with consent; the Account page."""

import threading
import time
from datetime import UTC, date, datetime

from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample, english_sample
from tests.ui.fakes import FakeAppList, MemorySettingsStore, tools_for

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection.addresses import server_address
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.connection.sign_in import (
    InviteNotValid,
    NotACode,
    PlusAlready,
    RedeemFailed,
    SignedIn,
    SignInAgain,
    SignOutFirst,
    SubscriptionEnded,
    TooManyAttempts,
)
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.shared import (
    LearningEvent,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)
from polyglotic_desktop.main import (
    SERVER,
    QtExchange,
    QtListener,
    learner_dictionary,
    share_finished_days,
    sign_in_problem,
)
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.sign_in import SignInFailed, SignInProblem
from polyglotic_desktop.ui_next.account_page import AccountPage

AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def process_until(qapp: QApplication, done: object, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not done() and time.monotonic() < deadline:  # type: ignore[operator]
        qapp.processEvents()
        time.sleep(0.01)


def test_the_connections_answers_as_the_dialog_shows_them() -> None:
    assert sign_in_problem(SignedIn("alpha")) is None
    assert sign_in_problem(NotACode()) == SignInFailed(SignInProblem.NOT_A_CODE)
    assert sign_in_problem(InviteNotValid()) == SignInFailed(SignInProblem.NOT_VALID)
    assert sign_in_problem(SubscriptionEnded()) == SignInFailed(
        SignInProblem.SUBSCRIPTION_ENDED
    )  # its words, not "doesn't work" (polyglotic-hq 258)
    assert sign_in_problem(TooManyAttempts(420)) == SignInFailed(
        SignInProblem.TOO_MANY_ATTEMPTS, 420
    )
    assert sign_in_problem(RedeemFailed("no server")) == SignInFailed(
        SignInProblem.UNREACHABLE
    )
    # why it couldn't be reached goes to the dialog (polyglotic-hq 251)
    down = RedeemFailed("the server answered 530", Unreachable.DOWN)
    assert sign_in_problem(down) == SignInFailed(
        SignInProblem.UNREACHABLE, unreachable=Unreachable.DOWN
    )
    # signed in, the code from a Plus email (polyglotic-hq 185, server #192)
    assert sign_in_problem(PlusAlready()) == SignInFailed(SignInProblem.PLUS_ALREADY)
    assert sign_in_problem(SignInAgain()) == SignInFailed(SignInProblem.SIGN_IN_AGAIN)
    # signed in, an invite code: refused, not a new account (208, server #205)
    assert sign_in_problem(SignOutFirst()) == SignInFailed(SignInProblem.SIGN_OUT_FIRST)


def test_learning_from_the_server_is_applied_on_the_qt_thread(
    qapp: QApplication,
) -> None:
    zh = ChineseDictionary(chinese_sample())
    tools = tools_for(zh, "hsk-2025")
    sent: list[object] = []
    tools.vocabulary.subscribe(sent.append)
    computer = zh.lookup("电脑")[0].entry_id
    exchanged = QtExchange(tools)
    events: list[LearningEvent] = [
        WordStatusChanged(computer, WordStatus.KNOWN, AT),
        WordSaved(computer, AT),
    ]
    worker = threading.Thread(target=exchanged.learning_arrived, args=(events,))
    worker.start()
    worker.join()
    process_until(qapp, lambda: tools.vocabulary.saved_word(computer) is not None)
    saved = tools.vocabulary.saved_word(computer)
    assert saved is not None and saved.headword == "电脑" and saved.meaning
    assert tools.vocabulary.status_of_entry(computer).status is WordStatus.KNOWN
    assert not [e for e in sent if isinstance(e, WordSaved | WordStatusChanged)]


def test_the_exchange_is_given_the_dictionary_entry_ids_start_with() -> None:
    """`DataExchange` keeps the server's statuses and saved words of the
    learner's dictionary only (an account learning both languages)."""
    zh = ChineseDictionary(chinese_sample())
    en = EnglishDictionary(english_sample())
    assert zh.lookup("电脑")[0].entry_id.startswith(f"{learner_dictionary(False)}:")
    assert en.lookup("awkward")[0].entry_id.startswith(f"{learner_dictionary(True)}:")


def test_deleting_here_only_when_asked(qapp: QApplication) -> None:
    zh = ChineseDictionary(chinese_sample())
    tools = tools_for(zh, "hsk-2025")
    computer = zh.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.KNOWN)
    exchanged = QtExchange(tools)
    exchanged.learning_deleted()
    qapp.processEvents()
    assert tools.vocabulary.vocabulary_list() != []  # the server's copy only
    exchanged.delete_here = True
    exchanged.learning_deleted()
    process_until(qapp, lambda: tools.vocabulary.vocabulary_list() == [])
    assert tools.vocabulary.vocabulary_list() == [] and not exchanged.delete_here


class Heard:
    def learning_arrived(self, events: object) -> None: ...

    def learning_deleted(self) -> None: ...


def test_finished_days_are_handed_over_with_consent_only() -> None:
    zh = ChineseDictionary(chinese_sample())
    for consented in (True, False):
        tools = tools_for(zh, "hsk-2025")
        store = tools.vocabulary._store
        store.save_exposures([], {date(2026, 11, 3): {"cedict:x": 2}})
        outbox = SqliteOutbox(":memory:")
        exchange = DataExchange(outbox, outbox, Heard(), "cedict")
        exchange.choose_consent(usage=False, crashes=False, exposures=consented)
        share_finished_days(tools.vocabulary, exchange)
        kinds = [w.kind for w in outbox.waiting()]
        assert kinds == (["consent", "exposures"] if consented else ["consent"])
        assert store.days_to_hand_over() == []  # handed over once (kept 8 weeks)


def test_the_account_page_shows_the_start_of_the_account_id(qapp: QApplication) -> None:
    # A tester quotes it to see, export or delete their data (project 041);
    # it comes in `welcome`, through main's listener.
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    page = AccountPage()
    assert page.account_id.isHidden()
    page.set_signed_in(True)
    listener = QtListener(desktop, None, None, page)
    listener.status_changed(Status(SessionState.LISTENING))  # an older server
    QApplication.processEvents()
    assert page.account_id.isHidden()
    listener.status_changed(
        Status(
            SessionState.LISTENING, account_id="4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e"
        )
    )
    QApplication.processEvents()
    assert not page.account_id.isHidden()
    assert "4f6a8c0e" in page.account_id.text()
    assert "4f6a8c0e-2d4f" not in page.account_id.text()
    page.set_signed_in(False)
    assert page.account_id.isHidden() and page.account_id.text() == ""
    desktop.close()


def test_the_built_in_server_is_the_live_one_over_https() -> None:
    """Every installed copy connects here (decision 0015): TLS only, at the
    live server's name (the tunnel to it, since 2026-11-11)."""
    assert server_address(SERVER) == SERVER
    assert SERVER == "https://api.polyglotic.io"
