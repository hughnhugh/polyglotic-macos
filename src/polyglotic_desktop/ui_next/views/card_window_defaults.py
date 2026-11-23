"""Settings for the card stack drawn by CaptionWindow (plain Python)."""

from polyglotic_desktop.core.shared.tunables import Applies, tunable

CARD_READ_SEC = tunable(
    "caption_window.card_read",
    1.9,
    "seconds",
    (1.0, 4.0),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""How long the newest card stands before the next may push it: a line
isn't pushed while it is new (the user, 2026-11-20: "lines getting pushed
too much whilst I'm reading it")."""

CARD_STEP_SEC = tunable(
    "caption_window.card_step",
    0.5,
    "seconds",
    (0.2, 1.5),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""A burst of cards (text held back, then let go) comes in one card at a
time, this far apart - so long as no more than `CARDS_KEPT_MOST` wait."""

CARD_WAIT_SEC = tunable(
    "caption_window.card_wait",
    0.6,
    "seconds",
    (0.0, 1.5),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""The most a new card is kept back for that: its words are never later
than this."""

TRANSLATION_WAIT_SEC = tunable(
    "caption_window.translation_wait",
    2.5,
    "seconds",
    (1.0, 6.0),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""A translation never waits longer than this to land, moving or not."""

TRANSLATION_WIDTH_RATIO = tunable(
    "caption_window.translation_width_ratio",
    2.0,
    "ratio",
    (1.0, 3.0),
    source="726: Mandarin to English can wrap at nearly twice the source width",
)
"""Estimated translation width over the original, at equal text sizes."""

CARD_CLEAR_PX = tunable(
    "caption_window.card_clear",
    0.0,
    "pixels",
    (0.0, 12.0),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""A new card shows at full ink once the card before is this near to clear
of it."""

CARD_BAR_PX = tunable(
    "caption_window.card_bar",
    6,
    "pixels",
    (2.0, 16.0),
    source="552 card stack; 556 subtitles; 583 depth",
    applies=Applies.NEW_WINDOWS,
)
"""The cards' scroll bar's width: in the window's padding, beside the text."""

VIEW_GRACE_SEC = tunable(
    "caption_window.view_grace",
    0.5,
    "seconds",
    (0.2, 2.0),
    source="552 card stack; 556 subtitles; 583 depth",
)
"""The mouse came off the words: the view it held goes live this long
after - one glide - unless it comes back (polyglotic-hq 583, the user,
2026-11-21: "The mouse shouldn't hold up delivery, could hold up pushing
text by introducing back to live / new messages alert right?"). Captions
are never held for the mouse: until 583 they waited while it moved over
the words, 2 s at most (554)."""

OWN_SUBTITLE_SIZE = tunable(
    "subtitle.own_size", 0.85, "fraction", (0.5, 1.0), source="668 Video own speech"
)
"""Size of the two own-speech rows as a share of the window's caption size."""


OWN_SUBTITLE_ROOM = tunable(
    "subtitle.own_room", 0.25, "fraction", (0.1, 0.4), source="668 Video own speech"
)
"""Maximum share of the usable Video window for both own-speech rows in a shallow window."""


LIFT = tunable(
    "video_motion.lift",
    0.28,
    "seconds",
    (0.1, 0.8),
    source="686 Video motion; 707 release gate",
)
"""Move a finished caption into its reading area."""


HANDOVER = tunable(
    "video_motion.handover",
    0.15,
    "seconds",
    (0.05, 0.4),
    source="686 Video motion; 707 release gate",
)
"""Clear the outgoing row before admitting its successor."""


TRANSLATION_FADE = tunable(
    "video_motion.translation_fade",
    0.18,
    "seconds",
    (0.05, 0.5),
    source="686 Video motion; 707 release gate",
)
"""Bring a finished translation into an existing block."""


CATCHUP = tunable(
    "video_motion.catchup",
    0.2,
    "seconds",
    (0.05, 0.2),
    source="686 Video motion; 707 release gate",
)
"""Deadline for new word ink after arrival or row clearance."""


MAX_STEP = tunable(
    "video_motion.max_step",
    128.0,
    "pixels per frame",
    (16.0, 160.0),
    source="686 Video motion; 707 release gate",
)
"""Limit one paint of the burst slide, including after a stalled frame."""


GLIDE = tunable(
    "video_motion.glide",
    360.0,
    "pixels per second",
    (100.0, 800.0),
    source="686 Video motion; 707 release gate",
)
"""Pan at ordinary reading speed between bursts."""


SETTLE = tunable(
    "video_motion.settle",
    0.5,
    "seconds",
    (0.5, 1.0),
    source="743 Video finished line minimum",
)
"""Keep the finished line at its painted position before its capped reading time."""


WAIT_CAP = tunable(
    "video_motion.wait_cap",
    1.0,
    "seconds",
    (0.0, 3.0),
    source="686 Video motion; 707 release gate",
)
"""Bound how long the next caption waits for finished text."""


READ_CPS = tunable(
    "video_motion.read_cps",
    15.0,
    "characters per second",
    (5.0, 30.0),
    source="686 Video motion; 707 release gate",
)
"""Reading rate used to schedule release of a finished original."""


TRANSLATION_RATIO = tunable(
    "video_motion.translation_ratio",
    0.5,
    "fraction",
    (0.2, 1.0),
    source="686 Video motion; 707 release gate",
)
"""Translation reading rate as a fraction of the original rate."""
