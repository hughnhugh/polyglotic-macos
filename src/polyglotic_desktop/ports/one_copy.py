"""One copy of the app per user and data folder (polyglotic-hq 310, decision
0101): a second start doesn't open, it asks the copy that runs to bring its
main window forward and ends.

What the app needs from the OS for it, implemented by
`platform/windows/one_copy.py` and picked by `main.os_adapters`:
- `CopyLock` - held by the copy that runs, from before it opens anything in
  its data folder until its process ends; the OS lets it go when the
  process ends, however it ends, so a crash leaves nothing stale;
- `LetToFront` - a second start, which the learner has just opened, lets
  the copy that runs bring its window in front (without it, Windows would
  only flash its taskbar button).

The asking itself is the interface's (`ui/one_copy.py`, a local socket
Qt keeps on each OS).
"""

from collections.abc import Callable
from typing import Protocol


class CopyLock(Protocol):
    def take(self) -> bool:
        """True when no other copy holds it: this copy runs, and holds it
        until its process ends (or `release`). False while another holds
        it; then asking again later may take it, once that copy has ended."""
        ...

    def release(self) -> None:
        """Lets go of it, if this copy holds it."""
        ...


LetToFront = Callable[[int], None]
"""Lets the process with this ID bring its window in front of the
learner's - for the next time it asks; quietly does nothing where the OS
won't."""
