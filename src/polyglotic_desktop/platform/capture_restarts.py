"""A capture that fails tries again by itself, and the log says so (polyglotic-hq 557, decision 0266).

polyglotic-hq 529 (B1): a capture thread that hit an error nobody foresaw
- in the speech detection or the timing its callback runs, say - ended for
good with nothing in the log, and the "no captions?" check then said
nothing was playing; an app whose capture failed to open was never tried
again. Now each capture, Windows' and the Mac's:

- **opens, fails and stops in the log:** by its kind (`app`, `everything
  else`, `system`, `mic`) and the error's type and code (`why`) - never an
  app's or a device's name, nor the error's text, which could hold either;
- **starts again** after an error nobody foresaw, and **tries a failed
  open again**, each after `Backoff`'s wait: FIRST_SEC, doubling, at most
  MAX_SEC;
- meanwhile its `error` says why it isn't capturing, and the "no
  captions?" check names it (`core.listening.check`, `CAPTURE_STOPPED`).

Plain Python, no clock of its own: the capture says how long it ran.
"""

FIRST_SEC = 1.0
"""The first wait after a failure."""
MAX_SEC = 30.0
"""The longest wait: a capture that failed is back within this long of
whatever stopped it going away."""
RESET_AFTER_SEC = 60.0
"""A capture that ran this long before failing starts again from FIRST_SEC."""


class Backoff:
    """The waits between one capture's tries after failures in a row."""

    def __init__(self) -> None:
        self.failures = 0
        """Failures in a row."""

    def failed(self, ran: float = 0.0) -> float:
        """It failed after running `ran` seconds: how long to wait before
        trying again - FIRST_SEC, doubling, at most MAX_SEC; from FIRST_SEC
        again after a run of RESET_AFTER_SEC or more."""
        if ran >= RESET_AFTER_SEC:
            self.failures = 0
        wait = min(MAX_SEC, FIRST_SEC * 2.0**self.failures)
        self.failures += 1
        return wait


def why(error: BaseException) -> str:
    """An error as the log may give it: its type, and Windows' code when it
    carries one (`winerror`, an HRESULT) - never its text."""
    code = getattr(error, "winerror", None)
    name = type(error).__name__
    return f"{name} {code & 0xFFFFFFFF:#010x}" if isinstance(code, int) else name
