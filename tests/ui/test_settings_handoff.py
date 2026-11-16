"""The listening settings reach the session once a change settles, and
only when what the server needs changed (polyglotic-hq 273): dragging the
panel's slider in the user's log sent the server a settings message on
every mouse move - it answered `rate_limited` six times - and each hand-over
held the interface up to 410 ms."""

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built

from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.main import SETTLE_MS, SettingsHandoff, listening_settings
from polyglotic_desktop.ui_next.panels import LookPanel

DRAG_STEP_MS = 16
"""A mouse move a frame, as a drag sends them (60 a second)."""


class FakeSession:
    """The listening session: the settings it was handed."""

    def __init__(self) -> None:
        self.handed: list[ListeningSettings] = []

    def change_settings(self, settings: ListeningSettings) -> None:
        self.handed.append(settings)


def wired(built: Built, session: FakeSession) -> SettingsHandoff:
    """The hand-over as `main` wires it: every settings change, and every
    caption window's languages - to a session started with the settings
    as they were."""

    def chosen() -> ListeningSettings:
        return listening_settings(
            built.desktop.settings.value,
            built.windows.targets(),
            built.windows.spoken_languages(),
        )

    handoff = SettingsHandoff(lambda: session, chosen, built.desktop)
    handoff.started(session, chosen())
    built.desktop.settings.changed.connect(handoff.changed)
    built.windows.languages_changed.connect(handoff.changed)
    return handoff


def settled(qapp: QApplication) -> None:
    QTest.qWait(SETTLE_MS + 100)
    qapp.processEvents()


def test_a_drag_of_the_panels_slider_hands_the_session_nothing(
    qapp: QApplication,
) -> None:
    built = Built()
    session = FakeSession()
    handoff = wired(built, session)
    panel = LookPanel(built.panels.look)
    for step in range(60):  # a second of dragging, a move a frame
        panel.background.setValue(20 + step)
        QTest.qWait(DRAG_STEP_MS)
        assert session.handed == []  # never on a mouse move
    settled(qapp)
    assert built.desktop.settings.value.opacity == 0.79
    settled(qapp)  # the save's own change, settled too
    assert not handoff.waiting
    assert session.handed == []  # the look isn't the server's
    panel.deleteLater()
    built.close()


def test_a_change_the_server_needs_goes_once_it_settles_with_the_last_value(
    qapp: QApplication,
) -> None:
    built = Built()
    session = FakeSession()
    handoff = wired(built, session)
    spoken = ["ja", "ko", "fr", "de", "es"] * 6
    for code in spoken:  # changed faster than it settles
        built.desktop.settings.update(spoken_language=code)
        QTest.qWait(DRAG_STEP_MS)
        assert session.handed == []
    assert handoff.waiting
    settled(qapp)
    assert [s.spoken_language for s in session.handed] == ["es"]
    settled(qapp)
    assert len(session.handed) == 1  # handed once
    built.close()


def test_what_the_session_has_already_isnt_handed_again(qapp: QApplication) -> None:
    built = Built()
    first, second = FakeSession(), FakeSession()
    now: list[FakeSession | None] = [first]
    handoff = SettingsHandoff(
        lambda: now[0],
        lambda: listening_settings(built.desktop.settings.value),
        built.desktop,
    )
    handoff.started(first, listening_settings(built.desktop.settings.value))
    handoff.hand_over()
    assert first.handed == []  # it started with them
    built.desktop.settings.update(spoken_language="ja")
    handoff.hand_over()
    handoff.hand_over()
    assert [s.spoken_language for s in first.handed] == ["ja"]
    now[0] = second  # a new session, not told it yet
    handoff.hand_over()
    assert [s.spoken_language for s in second.handed] == ["ja"]
    now[0] = None  # none open: nothing to hand
    handoff.hand_over()
    built.close()
