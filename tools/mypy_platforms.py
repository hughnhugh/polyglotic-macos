"""mypy as macOS and Linux would see the code (polyglotic-hq 179; decision
0038): run in CI beside the usual mypy, which checks it as Windows sees it.

    uv run --no-sync python -m tools.mypy_platforms           # linux and darwin
    uv run --no-sync python -m tools.mypy_platforms linux     # one

Everything must type-check on every OS except the Windows-only modules -
`platform/windows/` and the Windows credential store - which use Windows'
APIs by design and which only `main.os_adapters` imports (import-linter's
`os-in-one-place`). Their errors are counted, not failed; any other error
fails, so a Windows call creeping into shared code is caught here, before
a Mac or Linux build would find it. Each platform keeps its own cache, so
the usual `mypy` run stays warm.
"""

import re
import subprocess
import sys
from collections.abc import Iterable

PLATFORMS = ("linux", "darwin")
WINDOWS_ONLY = (
    "src/polyglotic_desktop/platform/windows/",
    "src/polyglotic_desktop/adapters/windows_credentials.py",
)
ERROR = re.compile(r"^(?P<path>[^:]+(?::\\)?[^:]*):\d+: error: ")


def failing(output: Iterable[str]) -> tuple[list[str], int]:
    """mypy's error lines outside the Windows-only modules, and how many
    were inside them."""
    kept, windows_only = [], 0
    for line in output:
        found = ERROR.match(line)
        if found is None:
            continue
        if found["path"].replace("\\", "/").startswith(WINDOWS_ONLY):
            windows_only += 1
        else:
            kept.append(line)
    return kept, windows_only


def check(platform: str) -> list[str]:
    done = subprocess.run(
        [sys.executable, "-m", "mypy", "--platform", platform,
         "--cache-dir", f".mypy_cache/platform-{platform}"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if done.returncode not in (0, 1):  # 2: mypy itself failed
        return [done.stdout + done.stderr]
    kept, windows_only = failing(done.stdout.splitlines())
    print(
        f"mypy --platform {platform}: {len(kept)} error(s);"
        f" {windows_only} in the Windows-only modules, as expected"
    )
    return kept


def main(argv: list[str]) -> int:
    platforms = argv or list(PLATFORMS)
    wrong = [line for platform in platforms for line in check(platform)]
    for line in wrong:
        print(line)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
