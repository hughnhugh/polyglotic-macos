"""The app's memory over an evening, against `perf.budgets`' MEMORY_HOUR
(polyglotic-hq 239): what an evening's captioning leaves behind, found the
day a change starts to keep it.

The interface as `main` builds and wires it (`new_interface`,
`wire_caption_windows`, `wire_transcripts`), offscreen: two apps captioned,
both transcripts open, the learner's tools on the sample dictionary.
Captions - made-up lines (`recorded_captions`), each with text of its
own and after two live updates - go through the app's caption feed as fast as the interface takes
them, painted as they come, at 223's QA's rate (16 a minute); each minute a
lookup is pinned on the newest line and closed. Once the hours that fill
what is bounded have passed (each window's 150 lines, each transcript's
1,000 listed and 300 laid out), one more hour's growth in the process's
private memory - Python's and Qt's alike - is held to the budget (decision
0049). About 9 seconds; Windows' process counters, so Windows only.
"""

import ctypes
import gc
import itertools
import sys
from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app
from tests.ui_next.made_up import OTHER_APP

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import (
    Interface,
    new_interface,
    wire_caption_windows,
    wire_transcripts,
)
from polyglotic_desktop.perf.budgets import MEMORY_HOUR
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, recorded_captions
from polyglotic_desktop.ui_next.caption_window import Marked

PER_MINUTE = 16
"""Finished captions a minute, both apps together: what 223's hour of two
apps heard (953 in 60 minutes)."""
FILLED_MINUTES = 150
"""Minutes of captions before the hour judged: past each transcript's 1,000
lines listed (8 a minute each), so what's bounded is full."""


def private_mb() -> float:
    """This process's private memory (Windows' PrivateUsage), in MB."""
    if sys.platform != "win32":  # the test is Windows only; mypy checks the rest there
        raise NotImplementedError("Windows' process counters")
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in [
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
                "PrivateUsage",
            ]
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    assert psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    return int(counters.PrivateUsage) / 2**20


def _said_anew(clause: Clause, n: int) -> Clause:
    """`clause` as caption `n` says it: text of its own, as every caption's
    is - shared text would keep nothing (the word links stay where they
    were: the number goes at the end)."""
    return Clause(
        f"{clause.original}{n}",
        {language: f"{text}{n}" for language, text in clause.translations.items()},
        clause.links,
    )


class Evening:
    """Two apps captioned on the interface as `main` wires it."""

    KEYS = (("Discord.exe", APP), ("vlc.exe", OTHER_APP))

    def __init__(self, qapp: QApplication) -> None:
        self.qapp = qapp
        store = MemorySettingsStore({"learning": "zh"})
        self.desktop: DesktopApp = make_app(store, tools=True)
        self.interface: Interface = new_interface(
            self.desktop, store, self.desktop.tools, per_app=True
        )
        wire_caption_windows(self.interface.windows, self.desktop, lambda: None)
        wire_transcripts(self.interface.transcripts, self.desktop)
        self.interface.windows.set_captioned(list(self.KEYS))
        self.interface.transcripts.follow()
        for key, _ in self.KEYS:
            self.interface.transcripts.show(key)
        qapp.processEvents()
        pool = [u for _, u in recorded_captions() if u.kind is CaptionKind.FINISHED]
        self._said = itertools.cycle(pool)
        self._serial = itertools.count()

    def minutes(self, count: int) -> None:
        for _ in range(count):
            for _ in range(PER_MINUTE):
                self._caption()
            self._look_up()

    def _caption(self) -> None:
        n = next(self._serial)
        said: CaptionUpdate = next(self._said)
        heard = replace(
            said,
            caption_id=CaptionId(f"evening-{n}"),
            source_id=self.KEYS[n % 2][1],
            clauses=tuple(_said_anew(clause, n) for clause in said.clauses),
            replaces=(),
        )
        for _ in range(2):  # live updates first, as the timing rules send them
            self.desktop.feed.receive(replace(heard, kind=CaptionKind.LIVE))
            self.qapp.processEvents()
        self.desktop.feed.receive(heard)
        self.qapp.processEvents()

    def _look_up(self) -> None:
        """A lookup pinned on the newest line's first characters, then closed."""
        windows = self.interface.windows
        shown, card = windows.windows.get("Discord.exe"), windows.card
        if shown is None or card is None or not shown.canvas.placed:
            return
        line, laid, _ = shown.canvas.placed[-1]
        row = laid.rows[0]
        wanted = shown.word_at(
            Marked(line.key, row.index, 0, min(2, len(row.row.text)))
        )
        if wanted is not None:
            card.pin(wanted)
            self.qapp.processEvents()
            card.close_card()

    def close(self) -> None:
        self.interface.close()
        self.desktop.close()


@pytest.fixture
def evening(qapp: QApplication) -> Iterator[Evening]:
    found = Evening(qapp)
    yield found
    found.close()


@pytest.mark.windows_only  # Windows' process counters
def test_an_hour_of_captions_once_full_keeps_little(evening: Evening) -> None:
    """Once what is bounded is full, an hour more of captions grows the
    app's private memory by at most MEMORY_HOUR's megabytes: the session's
    own text (kept for Copy all and Save) and little else. Each surface
    keeping every line's layouts it ever showed grew it about 30 MB an hour
    (polyglotic-hq 239)."""
    evening.minutes(FILLED_MINUTES)
    gc.collect()
    before = private_mb()
    evening.minutes(60)
    gc.collect()
    grown = private_mb() - before
    lines = {
        key: len(shown.transcript.lines)
        for key, shown in evening.interface.transcripts.shown.items()
    }
    assert grown <= MEMORY_HOUR.mb, (
        f"{grown:.1f} MB more after an hour of captions (budget {MEMORY_HOUR.mb} MB;"
        f" transcripts listing {lines})"
    )
