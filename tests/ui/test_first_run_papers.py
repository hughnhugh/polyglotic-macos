"""The first screen's yes at start (polyglotic-hq 185): the
tester agreement, or no further; asked again only for new words; and the
papers' addresses on the same domain as the server's."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore
from tests.ui.first_run_script import (
    Built,
    Press,
    agree,
    closed,
    nothing_asked,
    scripted,
)

from polyglotic_desktop.core.shared import papers
from polyglotic_desktop.main import (
    SERVER,
    UPDATES,
    FirstChoice,
    NotAgreed,
    first_run,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice

AT = datetime(2026, 11, 16, 9, tzinfo=UTC)


def agree_at_start(
    current: ConsentChoice | None, monkeypatch: pytest.MonkeyPatch, press: Press
) -> FirstChoice | None:
    """The first run's Your data for a learner whose language and level
    are chosen, signed in: only that screen, answered by `press`."""
    scripted(monkeypatch, [("ConsentDialog", press)])
    store = MemorySettingsStore({"learning": "zh"})
    return first_run(store, Built(level_picked=True), current, None).first


def test_closed_without_the_yes_the_app_goes_no_further(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(NotAgreed):
        agree_at_start(None, monkeypatch, closed)


def test_the_yes_comes_back_with_the_choices(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = agree_at_start(None, monkeypatch, agree())
    assert first is not None
    assert first.choices == (True, False, False)
    assert first.agreement is not None
    assert first.agreement.version == papers.TESTER_AGREEMENT_VERSION


def test_an_install_from_before_is_asked_once_with_its_choices_kept(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = ConsentChoice("a", AT, False, True, False)  # no agreement yet
    first = agree_at_start(before, monkeypatch, agree())
    assert first is not None and first.choices == (True, True, False)


def test_not_asked_again_once_these_words_are_agreed(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    agreed = Agreement(papers.TESTER_AGREEMENT_VERSION, AT)
    nothing_asked(monkeypatch)
    store = MemorySettingsStore({"learning": "zh"})
    current = ConsentChoice("a", AT, True, False, False, agreed)
    assert first_run(store, Built(level_picked=True), current, None).first is None


def domain(address: str) -> str:
    host = urlsplit(address).hostname or ""
    return ".".join(host.split(".")[-2:])


def test_the_website_is_on_the_servers_domain() -> None:
    """Bought, the domain changes in main's SERVER and UPDATES and in papers'
    SITE together (decision 0015)."""
    assert domain(papers.SITE) == domain(SERVER) == domain(UPDATES)
    for page in (
        papers.PRIVACY_NOTICE,
        papers.TESTER_AGREEMENT,
        papers.PLUS,
        papers.HELP_ANKI,
    ):
        assert page.startswith(papers.SITE + "/") and page.endswith("/")
