"""Captions failing on the server: said, and over once captions are back.

protocol.md, `error` `processing_failed`: a finished caption failed on the
server, and the app counts it dropped. One can be a one-off. When the
speech model stopped mid-session, every finished caption failed - 8 in
90 s - while Home said Listening and the caption windows stayed blank
(polyglotic-hq 145). `FAILING_AFTER` failed in a row, with no caption
between, is said on the caption windows and Home until a caption arrives
again (the model is back) or the session's state changes.
"""

FAILING_AFTER = 2
"""Finished captions failed in a row before the learner is told: one could
be a one-off; two lines lost is already noticeable."""


class FailingCaptions:
    """Whether captions are failing on the server now (`failing`)."""

    def __init__(self) -> None:
        self._in_a_row = 0

    @property
    def failing(self) -> bool:
        return self._in_a_row >= FAILING_AFTER

    def failed(self) -> bool:
        """A finished caption failed on the server: True if captions are
        failing from now (and weren't before)."""
        before = self.failing
        self._in_a_row += 1
        return self.failing and not before

    def captioned(self) -> bool:
        """A caption arrived (or the session's state changed): True if that
        ends a failing time."""
        before = self.failing
        self._in_a_row = 0
        return before
