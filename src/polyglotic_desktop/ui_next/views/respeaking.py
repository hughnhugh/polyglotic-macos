"""Settings for the caption bar microphone and re-speaking's status sign and tip."""

from polyglotic_desktop.core.shared.tunables import tunable

MIC_METER_WIDTH = tunable(
    "respeaking.meter_width",
    4,
    "logical pixels",
    (2, 8),
    source="A narrow level track beside the caption bar microphone",
)
MIC_LEVEL_MS = tunable(
    "own_speech.meter_ms",
    100,
    "milliseconds",
    (40, 500),
    source="651: how often the bar's own-speech mic button refreshes its level meter",
)
SIGN_GAP = tunable(
    "respeaking.sign_gap",
    6,
    "logical pixels",
    (0, 24),
    source="Space between the watched caption window and its status sign",
)
HINT_SEC = tunable(
    "respeaking.hint_seconds",
    10.0,
    "seconds",
    (1, 60),
    source="Allow the learner to read the one-time shortcut, as with the reading-line hint",
)
