"""Dated, machine-specific exceptions for tests known to be flaky.

An entry is deliberately narrower than an ordinary ``xfail``: it applies only
on the named runner, and an expired entry is an error.  A passing listed test
stays a pass and is called out in the summary so the exception can be removed.
"""

from __future__ import annotations

import os
import socket
import tomllib
from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

DEFAULT_LIST = Path(__file__).with_name("known_flaky.toml")
MACHINE_ENV = "POLYGLOTIC_TEST_MACHINE"
KNOWN_MACHINES = frozenset({"gpubox-windows"})


@dataclass(frozen=True)
class KnownFlaky:
    test: str
    machine: str
    why: str
    owner: str
    expires: date


def _machines() -> set[str]:
    """Names by which this runner may be listed.

    ``POLYGLOTIC_TEST_MACHINE`` lets a runner state a label such as ``gpubox``;
    GitHub's runner name and the host name cover runners named directly.
    """
    names = {
        os.environ.get(MACHINE_ENV, ""),
        os.environ.get("RUNNER_NAME", ""),
        socket.gethostname(),
    }
    return {name.strip().casefold() for name in names if name.strip()}


def _read(path: Path) -> list[KnownFlaky]:
    if not path.is_file():
        return []
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[KnownFlaky] = []
    seen: set[tuple[str, str]] = set()
    for number, item in enumerate(raw.get("flaky", []), 1):
        try:
            entry = KnownFlaky(
                test=item["test"],
                machine=item["machine"],
                why=item["why"],
                owner=item["owner"],
                expires=item["expires"],
            )
        except (KeyError, TypeError) as error:
            raise pytest.UsageError(
                f"{path}: invalid flaky entry {number}: {error}"
            ) from error
        if not all(
            (entry.test, entry.machine, entry.why, entry.owner)
        ) or not isinstance(entry.expires, date):
            raise pytest.UsageError(f"{path}: invalid flaky entry {number}")
        key = (entry.test, entry.machine.casefold())
        if key in seen:
            raise pytest.UsageError(
                f"{path}: duplicate flaky entry for {entry.test} on {entry.machine}"
            )
        seen.add(key)
        entries.append(entry)
    return entries


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--known-flaky-file",
        type=Path,
        default=DEFAULT_LIST,
        help="dated machine-specific flaky-test list",
    )


def pytest_configure(config: pytest.Config) -> None:
    entries = _read(config.getoption("known_flaky_file"))
    matching = [entry for entry in entries if entry.machine.casefold() in _machines()]
    config._known_flaky_entries = {entry.test: entry for entry in entries}  # type: ignore[attr-defined]
    config._known_flaky = {entry.test: entry for entry in matching}  # type: ignore[attr-defined]
    config._known_flaky_passed = []  # type: ignore[attr-defined]


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Fail an expired exception at its own test, without hiding other results."""
    entry = item.config._known_flaky_entries.get(item.nodeid)  # type: ignore[attr-defined]
    if entry is not None and entry.expires < date.today():
        pytest.fail(
            f"known-flaky entry expired {entry.expires.isoformat()}; "
            f"owner {entry.owner}: {entry.why}"
        )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.when != "call":
        return report
    entry = item.config._known_flaky.get(item.nodeid)  # type: ignore[attr-defined]
    if entry is None:
        return report
    reason = f"{entry.why}; owner {entry.owner}; expires {entry.expires.isoformat()}"
    if report.failed:
        report.outcome = "skipped"
        report.wasxfail = reason
    elif report.passed:
        item.config._known_flaky_passed.append((item.nodeid, reason))  # type: ignore[attr-defined]
    return report


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    passed = config._known_flaky_passed  # type: ignore[attr-defined]
    if not passed:
        return
    terminalreporter.write_sep(
        "=", "known flaky tests that passed; remove their entries"
    )
    for nodeid, reason in passed:
        terminalreporter.write_line(f"PASSED {nodeid} - {reason}")
