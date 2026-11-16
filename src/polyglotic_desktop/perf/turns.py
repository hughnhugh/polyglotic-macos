"""Short turns at the interpreter while a thread runs a long stretch of
Python beside the interface (polyglotic-hq 436; decision 0207).

Python runs one thread at a time. A thread busy in Python keeps the
interpreter until it's asked for it and the switch interval (5 ms) has
passed - and the interface thread asks for it again at every call from Qt
into the app's code: a layout's size hints, a widget's events, a slot. A
page laid out while another thread ran Python waited up to 5 ms at each of
them: a pack's word split reading its data (simplemma's Spanish, about
0.4 s of Python) beside Learning's and Words' work froze the interface
0.4-0.7 s on real windows. `short_turns` lowers the interval to
`SHORT_TURN` seconds while such a thread runs, and sets it back when the
last one ends. The thread's own work takes a little longer - Spanish's
read 0.44-0.65 s at a start - while the interface answers.
"""

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

SHORT_TURN = 0.0005
"""The switch interval while a long stretch runs beside the interface, in
seconds: a tenth of Python's own. On real windows, 436's pack learner's
start went from 79-174 ms busy at once to at most 66 ms (Spanish, 3 starts
each)."""

_lock = threading.Lock()
_running = 0
_before = 0.0


@contextmanager
def short_turns() -> Iterator[None]:
    """The interpreter's switch interval at `SHORT_TURN` while this runs -
    and while any other `short_turns` does - then back to what it was."""
    global _running, _before
    with _lock:
        if _running == 0:
            _before = sys.getswitchinterval()
            sys.setswitchinterval(SHORT_TURN)
        _running += 1
    try:
        yield
    finally:
        with _lock:
            _running -= 1
            if _running == 0:
                sys.setswitchinterval(_before)
