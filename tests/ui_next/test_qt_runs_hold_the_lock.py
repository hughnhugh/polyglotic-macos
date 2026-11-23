"""A Qt test on the user's PC runs holding the shared Qt lock, which the
run took before its first test (`tests/conftest.py`, `tools/qt_lock.py`,
polyglotic-hq 563): on 2026-11-20 two whole-suite runs started together,
neither holding it, took the PC to 0.5 GB free beside the live server."""

import os

import pytest

from tools import qt_lock


def test_a_qt_test_on_the_users_pc_runs_holding_the_shared_qt_lock() -> None:
    if not qt_lock.on_the_dev_pc():
        pytest.skip("the lock is the user's PC's, off CI")
    held_by = os.environ.get(qt_lock.HELD_ENV)
    lock = qt_lock.lock_file()
    if qt_lock.holder(lock) == qt_lock.OWN_WRAPPER or (
        held_by and held_by != str(os.getpid())
    ):
        pytest.skip("this run is under a run that holds the lock already")
    assert held_by == str(os.getpid())
    assert lock.read_text(encoding="utf-8").strip().endswith(f"pid={os.getpid()}")
