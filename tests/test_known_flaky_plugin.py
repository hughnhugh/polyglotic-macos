"""The dated, machine-scoped known-flaky pytest policy."""

import ast
import socket
from datetime import date, timedelta
from pathlib import Path

import pytest
from tests.known_flaky_plugin import DEFAULT_LIST, KNOWN_MACHINES, _read

pytest_plugins = ("pytester",)
ROOT = Path(__file__).resolve().parents[1]


def listed(
    path: Path, *, machine: str = "gpubox-windows", expires: str = "2099-01-01"
) -> None:
    path.write_text(
        f'''[[flaky]]
test = "test_sample.py::test_sample"
machine = "{machine}"
why = "intermittent clock"
owner = "Claude"
expires = {expires}
''',
        encoding="utf-8",
    )


def run(pytester: pytest.Pytester, body: str):
    registry = pytester.path / "known.toml"
    listed(registry)
    pytester.makepyfile(test_sample=body)
    return pytester.runpytest(
        "-p", "tests.known_flaky_plugin", "--known-flaky-file", str(registry)
    )


def test_runner_name_matches_hermetically(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POLYGLOTIC_TEST_MACHINE", raising=False)
    monkeypatch.setenv("RUNNER_NAME", "gpubox-windows")
    monkeypatch.setattr(socket, "gethostname", lambda: "unlisted-host")
    result = run(pytester, "def test_sample(): assert False")
    result.assert_outcomes(xfailed=1)


def test_hostname_matches_hermetically(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POLYGLOTIC_TEST_MACHINE", raising=False)
    monkeypatch.delenv("RUNNER_NAME", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "gpubox-windows")
    result = run(pytester, "def test_sample(): assert False")
    result.assert_outcomes(xfailed=1)


def test_a_failure_is_not_expected_on_another_machine(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POLYGLOTIC_TEST_MACHINE", raising=False)
    monkeypatch.delenv("RUNNER_NAME", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "somewhere-else")
    result = run(pytester, "def test_sample(): assert False")
    result.assert_outcomes(failed=1)


def test_an_expired_entry_fails_only_its_test_at_setup_on_every_machine(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POLYGLOTIC_TEST_MACHINE", raising=False)
    monkeypatch.delenv("RUNNER_NAME", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "somewhere-else")
    listed(pytester.path / "known.toml", expires="2000-01-01")
    pytester.makepyfile(
        test_sample="def test_sample(): pass",
        test_other="def test_other(): pass",
    )
    result = pytester.runpytest(
        "-p", "tests.known_flaky_plugin", "--known-flaky-file", "known.toml"
    )
    result.assert_outcomes(errors=1, passed=1)
    result.stdout.fnmatch_lines(["*known-flaky entry expired 2000-01-01*"])


def test_a_listed_pass_is_reported(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POLYGLOTIC_TEST_MACHINE", raising=False)
    monkeypatch.setenv("RUNNER_NAME", "gpubox-windows")
    monkeypatch.setattr(socket, "gethostname", lambda: "unlisted-host")
    result = run(pytester, "def test_sample(): pass")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "*known flaky tests that passed; remove their entries*",
            "PASSED test_sample.py::test_sample*",
        ]
    )


def test_checked_in_entries_are_current_known_tests_on_known_runners() -> None:
    """The registry cannot silently point at nowhere or become long-lived."""
    today = date.today()
    for entry in _read(DEFAULT_LIST):
        assert entry.machine.casefold() in KNOWN_MACHINES
        assert today <= entry.expires <= today + timedelta(days=30)

        file_name, separator, test_name = entry.test.partition("::")
        assert separator, entry.test
        path = ROOT / file_name
        assert path.is_file(), entry.test
        function_name = test_name.partition("[")[0]
        definitions = {
            node.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_name in definitions, entry.test
