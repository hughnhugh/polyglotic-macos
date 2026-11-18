"""Help's "no captions?" check on the app's facts (project 096), offscreen:
the check's links in order with their fixes, "Check again", the report
with the check's result attached (ticks and crosses, no names). Help's
page itself and Settings: tests/ui_next/test_account_settings_help.py.
Fakes only: no audio is captured. Made-up app names."""

import time

from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.core.listening.check import SourceActivity
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.feedback import FeedbackDialog
from polyglotic_desktop.ui_next.help_page import HelpPage

APP = SourceId("app-1")


def working_app() -> tuple[DesktopApp, dict[SourceId, SourceActivity]]:
    """An app that ticked 'chat' (shown as Chat App), captured, heard just now."""
    app = make_app(MemorySettingsStore({"apps": ["chat"], "whole_system": False}))
    now = time.monotonic()
    activity = {APP: SourceActivity(now - 300, now - 200, now - 2, now - 2)}
    app.set_app_sources({APP: ("chat", "Chat App")})
    app.set_activity(lambda: activity)
    app.set_connection(ConnectionState.LISTENING)
    return app, activity


def help_on(app: DesktopApp) -> HelpPage:
    """Help as `main`'s Hub builds it: on the app's facts, its report
    asked for through the app."""
    page = HelpPage(app.caption_facts)
    page.report_wanted.connect(app.check_report_wanted)
    return page


def lines(app: DesktopApp) -> dict[str, str]:
    help_page = help_on(app)
    help_page.refresh()
    return {  # each line as it reads: its mark, its words, its fix
        step.value: help_page.marks[step].text()
        + "  "
        + label.text()
        + " | "
        + help_page.fixes[step].text()
        for step, label in help_page.rows.items()
    }


def test_the_check_passes_when_everything_works(qapp: QApplication) -> None:
    app, _ = working_app()
    app._last_caption = time.monotonic() - 1
    shown = lines(app)
    assert "Chat App is added on Home" in shown["ticked"]
    assert all(v.startswith("✓") for v in shown.values())
    app.close()


def test_captions_failing_on_the_server_is_named_while_the_windows_say_so(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 184: two finished captions failed on the server, the
    caption windows and Home said "Captions failing on the server", and the
    check still showed five ticks - a caption was drawn under a minute ago."""
    app, _ = working_app()
    app._last_caption = time.monotonic() - 10
    app.caption_failed()
    app.caption_failed()
    shown = lines(app)
    assert shown["captions"].startswith("✗")
    assert "Captions are failing on the server" in shown["captions"]
    assert all(
        shown[s].startswith("✓") for s in ("connected", "ticked", "sound", "speech")
    )
    app.feed.captioned.emit(str(APP))  # a caption again: captions work
    assert all(v.startswith("✓") for v in lines(app).values())
    app.close()


def test_a_quiet_app_stops_the_chain_with_its_fix(qapp: QApplication) -> None:
    app, activity = working_app()
    now = time.monotonic()
    activity[APP] = SourceActivity(now - 300, now - 200, now - 100, now - 100)
    shown = lines(app)
    assert shown["ticked"].startswith("✓")
    assert shown["sound"].startswith("✗")
    assert "Chat App is quiet" in shown["sound"]
    assert "speakers or headset" in shown["sound"]
    assert shown["speech"].startswith("–")
    assert shown["captions"].startswith("–")
    app.close()


def test_not_signed_in_is_the_first_broken_link(qapp: QApplication) -> None:
    app, _ = working_app()
    app.set_connection(ConnectionState.SIGN_IN_NEEDED)
    shown = lines(app)
    assert shown["connected"].startswith("✗") and "Sign in" in shown["connected"]
    assert shown["sound"].startswith("–")
    app.close()


def test_nothing_ticked_then_the_mic_and_everything_the_pc_plays(
    qapp: QApplication,
) -> None:
    app = make_app(MemorySettingsStore({"whole_system": False}))  # all stopped
    app.set_connection(ConnectionState.LISTENING)
    assert lines(app)["ticked"].startswith("✗")
    app.settings.update(caption_mic=True)
    assert [t.kind for t in app.caption_facts().ticked] == ["mic"]
    app.settings.update(whole_system=True)
    assert [t.kind for t in app.caption_facts().ticked] == ["system", "mic"]
    app.close()


def test_check_again_runs_the_check_on_the_facts_as_they_are(
    qapp: QApplication,
) -> None:
    app, activity = working_app()
    help_page = help_on(app)
    now = time.monotonic()
    activity[APP] = SourceActivity(now - 300, None, None, None)
    help_page.check_again.click()
    assert help_page.marks[help_page.links[2].step].text() == "✗"
    activity[APP] = SourceActivity(now - 300, now - 1, now - 1, None)
    help_page.check_again.click()
    assert help_page.marks[help_page.links[2].step].text() == "✓"
    app.close()


def test_the_report_carries_the_check_as_ticks_and_crosses_only(
    qapp: QApplication,
) -> None:
    app, activity = working_app()
    now = time.monotonic()
    activity[APP] = SourceActivity(now - 300, now - 200, now - 100, now - 100)
    sent: list[str] = []
    app.check_report_wanted.connect(sent.append)
    page = help_on(app)
    page.report.click()
    [result] = sent
    assert "sound: broken (app_quiet)" in result
    assert "Chat App" not in result and "chat" not in result
    form = FeedbackDialog("problem", lambda: None, "v", False, None, result)
    form.text.setPlainText("No captions.")
    assert form.check_view.toPlainText() == result  # shown in full first
    kind, text, _, _ = form.report()
    assert kind == "problem" and text.startswith("No captions.")
    assert text.endswith(result)
    app.close()
