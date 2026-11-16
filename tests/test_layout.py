"""Smoke test: the package layout imports, and each module says what belongs in it.

Also keeps the import-linter contracts in step with the layout: a new
context in `core` must be added to the independence contract.
"""

import importlib
import pkgutil
import tomllib
from pathlib import Path
from typing import Any

import pytest

import polyglotic_desktop

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "src" / "polyglotic_desktop" / "core"


def all_modules() -> list[str]:
    found = [
        info.name
        for info in pkgutil.walk_packages(
            polyglotic_desktop.__path__, prefix="polyglotic_desktop."
        )
    ]
    return ["polyglotic_desktop", *found]


def contract(contract_id: str) -> dict[str, Any]:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    contracts: list[dict[str, Any]] = config["tool"]["importlinter"]["contracts"]
    return next(c for c in contracts if c["id"] == contract_id)


def contexts_in_core() -> set[str]:
    return {
        f"polyglotic_desktop.core.{path.name}"
        for path in CORE.iterdir()
        if (path / "__init__.py").exists() and path.name != "shared"
    }


WINDOWS_ONLY = (
    "polyglotic_desktop.platform.windows",
    "polyglotic_desktop.adapters.windows_credentials",
    "polyglotic_desktop.harness",
)
"""Windows' own modules, which load Windows' libraries as they're imported,
and the developer's harness, which imports them (decision 0038)."""


def importable_here(names: list[str]) -> list[object]:
    return [
        pytest.param(name, marks=pytest.mark.windows_only)
        if name.startswith(WINDOWS_ONLY)
        else name
        for name in names
    ]


@pytest.mark.parametrize("name", importable_here(all_modules()))
def test_module_imports_and_has_a_docstring(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__ and module.__doc__.strip(), (
        f"{name} needs a docstring saying what belongs in it"
    )


def test_layout_matches_architecture() -> None:
    expected = {
        "polyglotic_desktop.main",
        "polyglotic_desktop.core",
        "polyglotic_desktop.core.shared",
        "polyglotic_desktop.core.listening",
        "polyglotic_desktop.core.learning",
        "polyglotic_desktop.core.lexicon",
        "polyglotic_desktop.core.releases",
        "polyglotic_desktop.platform",
        "polyglotic_desktop.platform.windows",
        "polyglotic_desktop.connection",
        "polyglotic_desktop.ui",
        "polyglotic_desktop.ui_next",
        "polyglotic_desktop.ui_next.views",
        "polyglotic_desktop.perf",
        "polyglotic_desktop.ports",
        "polyglotic_desktop.adapters",
    }
    missing = expected - set(all_modules())
    assert not missing, f"missing from the layout in ARCHITECTURE.md: {missing}"


def test_every_context_is_kept_independent() -> None:
    assert set(contract("contexts-independent")["modules"]) == contexts_in_core()


def test_shared_may_not_import_any_context() -> None:
    forbidden = set(contract("shared-imports-no-context")["forbidden_modules"])
    assert forbidden == contexts_in_core()
