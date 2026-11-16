"""The packs workflow runs when what the packs read changes, and only then
(polyglotic-hq project 234): `dictionary-packs.yml`'s `paths:` name every
file in the repo that its two steps load - `python -m
tools.dictionaries.packs`, then pytest on the coverage probe and the Spanish
forms - and nothing more.

What they load is read as they load it: the modules, imported in a fresh
interpreter as each step starts, and the data files the packs open (the
probe's sentences, each pack's registry). An import added to the packs
fails the first test until its file is in the list; one taken away fails
the second until its line goes. The tests' shared set-up (`conftest.py`)
isn't counted: it runs in every pull request's own checks.

Before 234 the list held all of `tools/dictionaries/`, so a change to the
Chinese dictionary's `build.py` cost a packs run of 2-5 minutes on the one
Windows runner - and it missed eleven files the steps load, among them
`ports/dictionary.py` and `test_packs.py`. No pack imports `build.py`; the
packs' tests loaded it only for a MessagePack helper in `test_build.py`,
now in `wordfreq_data.py`."""

import json
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import yaml
from tools.dictionaries import coverage, packs

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "dictionary-packs.yml"

STEPS = (
    "tools.dictionaries.packs",  # the build step
    "tests.tools.test_coverage",  # the test step's two files
    "tests.tools.test_spanish_forms",
)
"""What the workflow's steps run, as modules."""

ALWAYS = (".github/workflows/dictionary-packs.yml", "uv.lock")
"""The workflow itself and the locked dependencies: what every run uses."""


def patterns() -> list[str]:
    """`dictionary-packs.yml`'s `on.pull_request.paths`, as GitHub reads them
    (YAML 1.1 reads the key `on` as true)."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    return list(triggers["pull_request"]["paths"])


def matches(pattern: str, path: str) -> bool:
    """GitHub's path filter: `**` any characters, `*` any but `/`, `?` one."""
    regex = ""
    for part in re.split(r"(\*\*/?|\*|\?)", pattern):
        if part in ("**", "**/"):
            regex += ".*"
        elif part == "*":
            regex += "[^/]*"
        elif part == "?":
            regex += "[^/]"
        else:
            regex += re.escape(part)
    return re.fullmatch(regex, path) is not None


@cache
def loaded() -> frozenset[str]:
    """Every repo file the steps load, relative to the repo, `/`-separated."""
    script = (
        "import importlib, json, sys\n"
        f"for name in {list(STEPS)!r}:\n"
        "    importlib.import_module(name)\n"
        "print(json.dumps([getattr(m, '__file__', None) for m in list(sys.modules.values())]))\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    files: set[str] = set()
    for name in json.loads(found.stdout.splitlines()[-1]):
        if not name:
            continue
        path = Path(name).resolve()
        if path.is_relative_to(REPO) and not path.is_relative_to(REPO / ".venv"):
            files.add(path.relative_to(REPO).as_posix())
    for pack in packs.PACKS.values():
        files.add(
            (coverage.PROBE / f"{pack.language}.txt").relative_to(REPO).as_posix()
        )
        files.add((packs.REGISTRY / f"{pack.name}.tsv").relative_to(REPO).as_posix())
    return frozenset(files)


def test_every_file_the_packs_load_starts_a_packs_run() -> None:
    missing = sorted(
        path for path in loaded() if not any(matches(p, path) for p in patterns())
    )
    assert missing == [], "add them to dictionary-packs.yml's paths"


def test_every_path_in_the_list_is_one_the_packs_load() -> None:
    read = loaded() | set(ALWAYS)
    stale = [p for p in patterns() if not any(matches(p, path) for path in read)]
    assert stale == [], "no step loads these: take them out of dictionary-packs.yml"


def test_the_filter_reads_globs_as_github_does() -> None:
    assert matches("tools/dictionaries/**", "tools/dictionaries/probe/es.txt")
    assert matches("src/a/*_split.py", "src/a/spaced_split.py")
    assert not matches("src/a/*_split.py", "src/a/b/spaced_split.py")
    assert not matches("tools/dictionaries/packs.py", "tools/dictionaries/build.py")
