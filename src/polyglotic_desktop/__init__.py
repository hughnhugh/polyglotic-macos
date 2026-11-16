"""Polyglotic's Windows app: live captions, translations and word lookups.

The module map and the rules between modules are in ARCHITECTURE.md at the
repo root. In short: `core` is what the app does (plain Python, no I/O, no
Qt); `platform` captures audio and detects speech per operating system;
`connection` talks to the server; `ui` is Qt; `main` wires it all together.
"""

import os

# numpy's OpenBLAS reserves a working buffer per CPU thread as it loads:
# about 480 MB of committed memory on a 16-thread PC, two thirds of what
# the app used (polyglotic-hq project 136, 2026-11-07). The app does no
# linear algebra - its arrays are audio - so one thread is plenty. Set here
# because every entry point imports this package before anything imports
# numpy; a value already in the environment is kept.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
