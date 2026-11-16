"""Report a problem for alpha testers (offscreen; polyglotic-hq 275): every part
ticked with its size and Look, other people's voices said, what's left
ticked is what goes; the consent screen's diagnostics for testers; and
main's parts, routing and diagnostics. Made-up text and bytes only."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton, QWidget
from tests.ui.test_consent_dialog import SCREENSHOTS

from polyglotic_desktop.core.listening.problem_report import SpeechPart
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import (
    diagnostics_on_for_testers,
    is_tester,
    problem_report_parts,
    window_theme,
)
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.consent import ConsentChoice
from polyglotic_desktop.ui.consent import ConsentDialog
from polyglotic_desktop.ui.problem_report import (
    LookDialog,
    OneReportWindow,
    Part,
    ProblemReportDialog,
)
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import style

PICTURES = Path(os.environ.get("POLYGLOTIC_275_PICTURES", SCREENSHOTS))
LOG = "2026-11-11 03:09:12 INFO connection: session opened\n"
CAPTIONS: list[dict[str, object]] = [
    {
        "caption_id": "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
        "source_id": "discord",
        "started_at": "2026-11-11T03:09:38.200Z",
        "original": "车票在柜台上。",
        "translations": {"en": "The tickets are on the counter."},
    }
]


def speech(source: str, category: SourceCategory, clips: int) -> SpeechPart:
    return SpeechPart(
        SourceId(source),
        category,
        tuple(
            HeldSpeech(
                CaptionId(f"0a1b2c3d-4e5f-4a6b-8c7d-{n:012d}"),
                SourceId(source),
                category,
                10.0 * n,
                10.0 * n + 2.5,
                b"OggS" + bytes(12_000),
            )
            for n in range(1, clips + 1)
        ),
    )


def parts(check: str | None = None) -> list[Part]:
    return problem_report_parts(
        LOG,
        {"caption_mode": "steady"},
        {"app": {"version": "0.4.0"}},
        CAPTIONS,
        [
            speech("app-1", SourceCategory.VIDEO, 3),
            speech("discord", SourceCategory.CALL, 1),
        ],
        {"app-1": "VLC", "discord": "Discord"},
        check,
    )


def dialog() -> ProblemReportDialog:
    return ProblemReportDialog(parts(), "Polyglotic 0.4.0, windows-11 (10.0.26200)")


def texts(widget: Any) -> list[str]:
    return [w.text() for w in widget.findChildren(QLabel)]


def test_everything_is_ticked_with_its_size_and_a_way_to_look(
    qapp: QApplication,
) -> None:
    form = dialog()
    ticks = {t.objectName(): t for t in form.findChildren(QCheckBox)}
    assert set(ticks) == {
        "problem_report.part.log",
        "problem_report.part.settings",
        "problem_report.part.facts",
        "problem_report.part.captions",
        "problem_report.part.speech:app-1",
        "problem_report.part.speech:discord",
    }
    assert all(t.isChecked() for t in ticks.values())
    assert "1 caption" in ticks["problem_report.part.captions"].text()
    audio = ticks["problem_report.part.speech:app-1"].text()
    assert audio.startswith("Audio from VLC (8 s of speech")
    assert audio.endswith(" kB)")
    looks = {b.objectName() for b in form.findChildren(QPushButton)}
    assert {f"problem_report.look.{k.split('.')[-1]}" for k in ticks} <= looks
    form.deleteLater()


def test_a_call_says_it_holds_other_peoples_voices_and_stays_ticked(
    qapp: QApplication,
) -> None:
    form = dialog()
    assert texts(form).count("This includes other people's voices.") == 1
    assert form.ticks["speech:discord"].isChecked()
    form.deleteLater()


def test_what_is_left_ticked_is_what_goes(qapp: QApplication) -> None:
    form = dialog()
    form.text.setPlainText("  The caption came late.  ")
    form.ticks["speech:discord"].setChecked(False)  # one click
    text, ticked = form.chosen()
    assert text == "The caption came late."
    assert ticked == {"log", "settings", "facts", "captions", "speech:app-1"}
    sent: list[bool] = []
    form.sent.connect(lambda: sent.append(True))
    form.send.click()
    assert sent == [True]
    form.deleteLater()


def test_nothing_ticked_and_nothing_written_sends_nothing(qapp: QApplication) -> None:
    form = dialog()
    for tick in form.ticks.values():
        tick.setChecked(False)
    assert not form.send.isEnabled()
    form.text.setPlainText("It froze.")
    assert form.send.isEnabled()
    form.deleteLater()


def test_look_shows_exactly_what_goes(qapp: QApplication) -> None:
    by_key = {p.key: p for p in parts("✓ sound heard\n✗ no captions")}
    assert by_key["log"].look() == LOG
    assert json.loads(by_key["settings"].look()) == {"caption_mode": "steady"}
    assert "The tickets are on the counter." in by_key["captions"].look()
    assert (
        "车票在柜台上。" in by_key["speech:discord"].look()
    )  # the caption it was heard as
    assert by_key["check"].look() == "✓ sound heard\n✗ no captions"
    form = ProblemReportDialog(list(by_key.values()), "Polyglotic 0.4.0")
    button = form.findChild(QPushButton, "problem_report.look.log")
    assert button is not None
    button.click()
    look = form.findChild(LookDialog)
    assert look is not None and look.view.toPlainText() == LOG
    form.deleteLater()


def test_a_part_with_nothing_in_it_isnt_offered(qapp: QApplication) -> None:
    keys = [p.key for p in problem_report_parts(None, {}, {}, [], [], {}, None)]
    assert keys == ["settings", "facts"]


def test_the_dialog_as_a_tester_sees_it(qapp: QApplication) -> None:
    if not os.environ.get("POLYGLOTIC_SCREENSHOTS"):  # with QT_QPA_FONTDIR for glyphs
        return
    PICTURES.mkdir(parents=True, exist_ok=True)
    form = dialog()
    form.setStyleSheet(style.stylesheet(window_theme()))
    form.text.setPlainText("The last caption came out in the wrong language.")
    form.adjustSize()
    form.grab().save(str(PICTURES / "report-a-problem.png"))
    button = form.findChild(QPushButton, "problem_report.look.captions")
    assert button is not None
    button.click()
    look = form.findChild(LookDialog)
    assert look is not None
    look.setStyleSheet(style.stylesheet(window_theme()))
    look.grab().save(str(PICTURES / "report-a-problem-look.png"))
    form.deleteLater()


def consent(**changes: Any) -> ConsentChoice:
    fields = {
        "id": "c1",
        "at": datetime(2026, 11, 11, tzinfo=UTC),
        "usage": False,
        "crashes": False,
        "exposures": False,
    }
    return ConsentChoice(**{**fields, **changes})


def test_a_tester_s_diagnostics_are_on_and_stay_on(qapp: QApplication) -> None:
    screen = ConsentDialog(consent(), tester=True)
    assert screen.usage.isChecked() and not screen.usage.isEnabled()
    assert screen.crashes.isChecked() and not screen.crashes.isEnabled()
    assert not screen.exposures.isChecked() and screen.exposures.isEnabled()
    assert screen.choices() == (True, True, False)
    assert any("You're testing the alpha" in t for t in texts(screen))
    screen.deleteLater()


def test_the_first_run_says_it_as_a_fact_for_testers(qapp: QApplication) -> None:
    first = ConsentDialog(None)  # the cohort isn't known before the code
    assert any(t.startswith("Testing the alpha?") for t in texts(first))
    assert first.usage.isEnabled() and not first.usage.isChecked()
    first.deleteLater()
    others = ConsentDialog(consent(), tester=False)
    assert not any("alpha" in t for t in texts(others))
    others.deleteLater()


class Exchange:
    def __init__(self, current: ConsentChoice | None) -> None:
        self.consent = current
        self.chosen: list[tuple[bool, bool, bool]] = []

    def choose_consent(self, usage: bool, crashes: bool, exposures: bool) -> None:
        self.chosen.append((usage, crashes, exposures))


def test_an_alpha_testers_diagnostics_go_on_once_word_counts_as_chosen() -> None:
    exchange = Exchange(consent(exposures=True))
    assert diagnostics_on_for_testers(exchange)  # type: ignore[arg-type]
    assert exchange.chosen == [(True, True, True)]
    already = Exchange(consent(usage=True, crashes=True))
    assert not diagnostics_on_for_testers(already)  # type: ignore[arg-type]
    first_run_not_done = Exchange(None)
    assert not diagnostics_on_for_testers(first_run_not_done)  # type: ignore[arg-type]
    assert already.chosen == first_run_not_done.chosen == []


def test_only_the_alpha_is_a_tester_for_this() -> None:
    assert is_tester(AppSettings(cohort="alpha"))
    assert not is_tester(AppSettings(cohort="beta"))
    assert not is_tester(AppSettings())
    assert AppSettings.from_stored({"cohort": "alpha"}).cohort == "alpha"
    assert AppSettings.from_stored({"cohort": 3}).cohort is None


def test_on_a_short_screen_the_parts_scroll_and_no_text_overlaps(
    qapp: QApplication,
) -> None:
    """More to say than the screen is tall (polyglotic-hq 300: German and
    Japanese at the Largest text size on a 1366 x 768 laptop): the window
    stays on the work area with Send in view, and no text is squeezed under
    the next - the line, the parts and what else goes scroll instead."""
    many = problem_report_parts(
        LOG,
        {"caption_mode": "steady"},
        {"app": {"version": "0.4.0"}},
        CAPTIONS,
        [speech(f"app-{n}", SourceCategory.CALL, 1) for n in range(12)],
        {f"app-{n}": f"App number {n}" for n in range(12)},
        "five rows, all green",
    )
    form = ProblemReportDialog(many, "Polyglotic 0.4.0, windows-11 (10.0.26200)")
    form.show()
    for _ in range(4):
        qapp.processEvents()
    screen = form.screen().availableGeometry()
    assert screen.contains(form.frameGeometry())
    assert form.send.isVisible()
    assert screen.contains(form.send.mapToGlobal(form.send.rect().bottomRight()))
    squeezed = [
        (label.text()[:30], label.height(), label.heightForWidth(label.width()))
        for label in form.findChildren(QLabel)
        if label.isVisible()
        and label.wordWrap()
        and label.heightForWidth(label.width()) > label.height() + 1
    ]
    assert not squeezed
    rows = [
        w.geometry() for w in form.body.findChildren(QWidget) if w.parent() is form.body
    ]
    assert all(not a.intersects(b) for i, a in enumerate(rows) for b in rows[i + 1 :])
    assert form.scroll_area.verticalScrollBar().maximum() > 0
    form.deleteLater()


def test_it_opens_ready_to_type_in_the_line(qapp: QApplication) -> None:
    """The first thing the keyboard reaches is the line for what happened,
    as before the parts could scroll - never the scrolling area itself."""
    form = dialog()
    form.show()
    qapp.processEvents()
    chain: list[QWidget] = []
    at = form.nextInFocusChain()
    while at is not None and at is not form and len(chain) < 50:
        chain.append(at)
        at = at.nextInFocusChain()
    takes = [
        w for w in chain if w.focusPolicy() & Qt.FocusPolicy.TabFocus and w.isEnabled()
    ]
    assert takes and takes[0] is form.text
    form.deleteLater()


def test_tab_leaves_the_text_box_for_the_ticks_and_send(qapp: QApplication) -> None:
    """QA 278, by keyboard only: Tab in the text box typed a tab character,
    and nothing else could be reached - not a tick, not Send."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    form = dialog()
    form.show()
    form.activateWindow()
    form.text.setFocus()
    qapp.processEvents()
    reached = []
    for _ in range(len(form.ticks) * 2 + 3):
        focused = qapp.focusWidget()
        assert focused is not None
        QTest.keyClick(focused, Qt.Key.Key_Tab)
        now = qapp.focusWidget()
        reached.append(now.objectName() if now is not None else "")
    assert form.text.toPlainText() == ""
    assert "problem_report.part.log" in reached
    assert "problem_report.send" in reached
    form.close()
    form.deleteLater()


def test_one_report_window_at_a_time(qapp: QApplication) -> None:
    """QA 278: a double-click on the caption window's Report a problem
    opened two report windows. Asked again while one is open, that one
    comes to the front; once it's sent or closed, the next ask makes one."""
    one = OneReportWindow()
    assert not one.front()  # none open: make one
    first = dialog()
    one.opened(first)
    first.show()
    qapp.processEvents()
    assert one.front()  # asked again: the open one, no second
    first.reject()  # closed (and deleted: WA_DeleteOnClose)
    qapp.processEvents()
    assert not one.front()
    second = dialog()
    one.opened(second)
    second.show()
    second._send()  # sent: closed too
    qapp.processEvents()
    assert not one.front()
