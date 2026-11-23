"""Steady's card stack is on by default (polyglotic-hq 572; Claude for the
user, 2026-11-21: 553's recorded check passed #989 round 4 - jumps,
re-wraps, translation pushes and pushes while reading at or below main's
in every scenario). A new learner, and a 0.1.9 or 0.1.10-preview.1 file
(which never held the setting), start on the cards; a learner who turned
them off keeps that.

The files in `settings_files/` are what those versions saved (polyglotic-hq
555's `work/make_settings_files.py`)."""

import json
from pathlib import Path

import pytest

from polyglotic_desktop.main import timing_of
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.views.panels import Timing

FILES = Path(__file__).parent / "settings_files"


def test_a_new_learner_starts_on_the_cards() -> None:
    assert AppSettings().steady_cards is True
    assert Timing().cards is True  # the Timing panel's own default
    assert timing_of(AppSettings()).cards is True


@pytest.mark.parametrize("version", ["0.1.9", "0.1.10-preview.1"])
def test_an_older_file_starts_on_the_cards(version: str) -> None:
    files = json.loads((FILES / f"{version}.json").read_text(encoding="utf-8"))
    for learner, saved in files.items():
        assert "steady_cards" not in saved, learner
        assert AppSettings.from_stored(saved).steady_cards is True, learner


def test_a_learner_who_turned_them_off_keeps_that() -> None:
    off = AppSettings.from_stored({**AppSettings().to_stored(), "steady_cards": False})
    assert off.steady_cards is False
    assert AppSettings.from_stored(off.to_stored()).steady_cards is False
