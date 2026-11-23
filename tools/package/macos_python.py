"""The Python a Mac build packs, checked against its pin (polyglotic-hq 523,
512's finding): the macOS job sets `UV_PYTHON` to an exact version and
`UV_PYTHON_PREFERENCE=only-managed`, so uv builds the venv on its own
CPython (python-build-standalone) - never the runner image's python.org
Python, whose own root list hid 512's bug (0.1.7 was packed with the
image's 3.12.10), nor Homebrew's. PyInstaller packs the venv's interpreter,
so the app a learner gets carries exactly this one.

    uv run --no-sync python -m tools.package.macos_python   # in the macOS job

Prints what it found; exits 1 when the version isn't the pin or the
interpreter isn't uv's own.
"""

from __future__ import annotations

import os
import ssl
import sys

NOT_OURS = (
    "/Library/Frameworks/Python.framework",  # python.org's installer
    "/opt/homebrew",  # Homebrew on Apple silicon
    "/usr/local",  # Homebrew on Intel, and python.org's links
    "/Applications/Xcode",  # Xcode's own Python
    "/Library/Developer/CommandLineTools",  # the developer tools' Python
)
"""Where an interpreter a learner's Mac doesn't have would come from."""


def problems(version: str, base_prefix: str, pinned: str | None) -> list[str]:
    """What's wrong with an interpreter at `version` under `base_prefix`,
    pinned to `pinned` (the job's `UV_PYTHON`); none when it is the pin and
    uv's own."""
    found: list[str] = []
    if not pinned:
        found.append("UV_PYTHON isn't set: the build's Python isn't pinned")
    elif version != pinned:
        found.append(f"Python {version}, but the pin is {pinned}")
    if any(base_prefix.startswith(place) for place in NOT_OURS):
        found.append(f"{base_prefix} is the runner image's Python, not uv's own")
    elif not base_prefix.rstrip("/").rsplit("/", 1)[-1].startswith("cpython-"):
        # uv names each of its own installs cpython-<version>-<os>-<arch>-none,
        # wherever setup-uv puts them (UV_PYTHON_INSTALL_DIR)
        found.append(f"{base_prefix} isn't a Python uv installed")
    return found


def main() -> int:
    version = "{}.{}.{}".format(*sys.version_info[:3])
    pinned = os.environ.get("UV_PYTHON")
    print(f"Python {version} at {sys.base_prefix} (pin {pinned})")
    print(f"{ssl.OPENSSL_VERSION}; {ssl.get_default_verify_paths()}")
    found = problems(version, sys.base_prefix, pinned)
    for problem in found:
        print(f"not pinned: {problem}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
