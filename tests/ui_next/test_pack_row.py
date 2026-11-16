"""A language's pack on its Learning card says each state in words, with
the way on, and its bar never moves by itself (decision 0122)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem, Step
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.pack_row import PackRow, shown
from polyglotic_desktop.ui_next.views.learning import PackLine

MB = 1_000_000


def downloading(**fields: Any) -> PackLine:
    progress = PackProgress("ru", Step.DOWNLOADING, 12 * MB, 48 * MB, tries=1)
    return PackLine(size=48 * MB, progress=replace(progress, **fields))


THIS = pc_or_mac("PC", "Mac")
"""Where the pack is: 409's words."""

CASES = [
    (PackLine(size=62_400_000), "Its dictionary: 62.4 MB to download.", ("download",)),
    (  # its recorded words come by themselves after it: both sizes (#192 B)
        PackLine(size=9_400_000, recorded_offered=29_002_130),
        "Its dictionary: 9.4 MB to download, then 29.0 MB of recorded words.",
        ("download",),
    ),
    (PackLine(), "Checking the list of dictionaries.", ("download",)),
    (  # couldn't be read: no claim either way (330's addendum)
        PackLine(unlisted=True),
        "The list of dictionaries couldn't be checked.",
        ("retry",),
    ),
    (  # the list held has none for it: not "checking" with a Download (330)
        PackLine(not_offered=True),
        "Its dictionary isn't ready to download yet.",
        ("retry",),
    ),
    (
        PackLine(progress=PackProgress("ru", Step.WAITING)),
        "Waiting for another dictionary to finish.",
        ("cancel",),
    ),
    (
        PackLine(progress=PackProgress("ru", Step.LIST, tries=1)),
        "Checking the list of dictionaries.",
        ("cancel",),
    ),
    (downloading(), "Downloading: 12.0 of 48.0 MB", ("cancel",)),
    (
        downloading(seconds_left=30.0),
        "Downloading: 12.0 of 48.0 MB · less than a minute left",
        ("cancel",),
    ),
    (
        downloading(seconds_left=185.0),
        "Downloading: 12.0 of 48.0 MB · about 3 minutes left",
        ("cancel",),
    ),
    (downloading(step=Step.CHECKING), "Checking the file.", ("cancel",)),
    (downloading(step=Step.OPENING), "Opening the dictionary.", ("cancel",)),
    (
        downloading(problem=Problem.OFFLINE, retry_in=14.6),
        "No connection. Trying again in 15 s (try 2 of 6).",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.STALLED, retry_in=5.0, tries=2),
        "The download stalled: no data for 30 s. Trying again in 5 s (try 3 of 6).",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.SERVER, status=503, tries=6),
        "Our server answered with an error (503). It won't try again by itself.",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.METERED),
        "Paused: Windows says this connection is metered. 36.0 MB left to download.",
        ("anyway", "cancel"),
    ),
    (
        downloading(problem=Problem.NO_ROOM, needed=48 * MB),
        f"Not enough room on this {THIS}: it needs 48.0 MB free.",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.LIST_REFUSED),
        (
            "Refused: the list of dictionaries failed our signature check, so nothing "
            "was downloaded."
        ),
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.FILE_REFUSED),
        "Refused: the file didn't match our list, so it was deleted.",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.UNREADABLE),
        "Refused: the file isn't the Russian dictionary, so it was deleted.",
        ("retry", "cancel"),
    ),
    (
        downloading(problem=Problem.NEEDS_NEWER_APP),
        "Its dictionary needs a newer Polyglotic. Update the app to get it.",
        (),
    ),
    (
        PackLine(newer_app=True),
        "Its dictionary needs a newer Polyglotic. Update the app to get it.",
        (),
    ),
    (
        downloading(problem=Problem.NOT_OFFERED),
        "Its dictionary isn't ready to download yet.",
        ("retry",),
    ),
    (
        PackLine(installed_version="2026.11.14", installed_size=62_400_000),
        f"On this {THIS}: version 2026.11.14, 62.4 MB.",
        (),
    ),
    (  # its commonest words recorded (decision 0192)
        PackLine(
            installed_version="2026.11.16",
            installed_size=29_500_000,
            recorded_size=30_277_632,
        ),
        (
            f"On this {THIS}: version 2026.11.16, 29.5 MB. Its commonest words are "
            "recorded (30.3 MB)."
        ),
        (),
    ),
    (
        PackLine(
            installed_version="2026.11.14",
            installed_size=62_400_000,
            update_size=63 * MB,
        ),
        (
            f"On this {THIS}: version 2026.11.14, 62.4 MB. A newer version (63.0 MB)"
            " waits "
            "for a connection that isn't metered."
        ),
        ("update",),
    ),
]


@pytest.fixture
def row(qapp: QApplication) -> Iterator[PackRow]:
    parent = QWidget()
    made = PackRow("ru", parent)
    yield made
    parent.deleteLater()


@pytest.mark.parametrize(("line", "said", "buttons"), CASES)
def test_each_state_is_said_with_its_way_on(
    row: PackRow, line: PackLine, said: str, buttons: tuple[str, ...]
) -> None:
    assert shown("ru", line)[:2] == (said, buttons)
    row.show_line(line)
    assert row.said.text() == said
    assert [k for k, b in row.buttons.items() if not b.isHidden()] == sorted(
        buttons, key=list(row.buttons).index
    )


def test_the_bar_shows_how_far_along_and_only_while_it_matters(row: PackRow) -> None:
    row.show_line(downloading())
    assert not row.bar.isHidden() and row.bar.share == 0.25
    row.show_line(PackLine(installed_version="1", installed_size=1))
    assert row.bar.isHidden()
    row.show_line(downloading(problem=Problem.NO_ROOM))  # where it stood, kept
    assert not row.bar.isHidden() and row.bar.share == 0.25


def test_a_button_says_which_language_and_what(row: PackRow) -> None:
    asked: list[tuple[str, str]] = []
    row.wanted.connect(lambda code, action: asked.append((code, action)))
    row.show_line(PackLine(size=MB))
    row.buttons["download"].click()
    assert asked == [("ru", "download")]


def test_the_bar_has_no_timer_of_its_own(row: PackRow) -> None:
    """It moves only when told: nothing to stop with Windows' animations off."""
    from PySide6.QtCore import QTimer

    assert not row.bar.findChildren(QTimer)
