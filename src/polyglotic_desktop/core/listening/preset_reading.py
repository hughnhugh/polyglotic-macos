"""Reading-related preset defaults and timing recommendations (638);
'inherit' keeps Everyday's preset inheritance."""

from collections.abc import Mapping
from dataclasses import dataclass

from polyglotic_desktop.core.listening.timing import CaptionMode, default_caption_mode
from polyglotic_desktop.core.shared.tunables import Applies, tunable


def QT_TRANSLATE_NOOP(_context: str, text: str) -> str:
    """Mark a plain core string for tools.i18n without importing Qt."""
    return text


MODES = ("inherit", "steady", "instant", "whole", "calm")
PATHS = ("inherit", "both", "follow", "acquisition")
EVERYDAY_MODE = tunable(
    "presets.everyday.caption_mode",
    "inherit",
    "timing",
    MODES,
    source="556 preset; 585 rule 11; 638 Everyday recommendation",
    applies=Applies.RESTART,
)
EVERYDAY_PATH = tunable(
    "presets.everyday.caption_path",
    "inherit",
    "display",
    PATHS,
    source="556 preset; 585 rule 11",
    applies=Applies.RESTART,
)
CONVERSATION_MODE = tunable(
    "presets.conversation.caption_mode",
    "instant",
    "timing",
    MODES,
    source="626 Instant default; 585 rule 11; 638 Conversation recommendation",
    applies=Applies.RESTART,
)
CONVERSATION_PATH = tunable(
    "presets.conversation.caption_path",
    "inherit",
    "display",
    PATHS,
    source="556 preset; 585 rule 11",
    applies=Applies.RESTART,
)
VIDEO_MODE = tunable(
    "presets.video.caption_mode",
    "instant",
    "timing",
    (*MODES, "scrolling"),
    source="743 Video subtitle modes and default",
    applies=Applies.RESTART,
)
VIDEO_LINES = tunable(
    "presets.video.lines_shown",
    2,
    "lines",
    (1, 3),
    source="752 Video's adjustable subtitle window",
    applies=Applies.LIVE,
)
VIDEO_LINE_CHOICES = (1, 2, 3)
VIDEO_PATH = tunable(
    "presets.video.caption_path",
    "inherit",
    "display",
    PATHS,
    source="556 preset; 585 rule 11",
    applies=Applies.RESTART,
)
# One-value change to "calm" once 625's Steady/Calm fixes pass: both
# Learning's default timing and its recommendation read this tunable.
LEARNING_MODE = tunable(
    "presets.learning.caption_mode",
    "instant",
    "timing",
    MODES,
    source="626 Instant default; 585 rule 11; 638 Learning recommendation",
    applies=Applies.RESTART,
)
LEARNING_PATH = tunable(
    "presets.learning.caption_path",
    "acquisition",
    "display",
    PATHS,
    source="556 preset; 585 rule 11",
    applies=Applies.RESTART,
)
VIDEO_FADE = tunable(
    "presets.video.fade_after",
    4.0,
    "seconds",
    (1, 15),
    source="556 Video subtitles; 585 rule 9",
    applies=Applies.RESTART,
)

SIZE_BOUNDS = (0.6, 4.0)  # constant: matches CAPTION_TEXT_SIZES (60..400 %)
EVERYDAY_CAPTION_SIZE = tunable(
    "presets.everyday.caption_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Everyday default: caption and translation equal for balanced general listening",
    applies=Applies.LIVE,
)
EVERYDAY_TRANSLATION_SIZE = tunable(
    "presets.everyday.translation_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Everyday default: translation matches caption size",
    applies=Applies.LIVE,
)
CONVERSATION_CAPTION_SIZE = tunable(
    "presets.conversation.caption_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Conversation default: caption and translation equal for fast scanning in live talk",
    applies=Applies.LIVE,
)
CONVERSATION_TRANSLATION_SIZE = tunable(
    "presets.conversation.translation_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Conversation default: translation matches caption size in live talk",
    applies=Applies.LIVE,
)
VIDEO_CAPTION_SIZE = tunable(
    "presets.video.caption_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Video default: caption and translation equal for clean subtitle blocks",
    applies=Applies.LIVE,
)
VIDEO_TRANSLATION_SIZE = tunable(
    "presets.video.translation_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Video default: translation matches caption size for clean subtitle blocks",
    applies=Applies.LIVE,
)
LEARNING_CAPTION_SIZE = tunable(
    "presets.learning.caption_size",
    1.2,
    "scale",
    SIZE_BOUNDS,
    source="655 Learning default: original a little larger so the learned language leads the eye",
    applies=Applies.LIVE,
)
LEARNING_TRANSLATION_SIZE = tunable(
    "presets.learning.translation_size",
    1.0,
    "scale",
    SIZE_BOUNDS,
    source="655 Learning default: translation stays at base size while the original leads",
    applies=Applies.LIVE,
)

PRESET_SIZES = {
    "everyday": (EVERYDAY_CAPTION_SIZE, EVERYDAY_TRANSLATION_SIZE),
    "conversation": (CONVERSATION_CAPTION_SIZE, CONVERSATION_TRANSLATION_SIZE),
    "video": (VIDEO_CAPTION_SIZE, VIDEO_TRANSLATION_SIZE),
    "learning": (LEARNING_CAPTION_SIZE, LEARNING_TRANSLATION_SIZE),
}


def preset_sizes(preset: str, parent: str | None = None) -> tuple[float, float]:
    """Default (caption_size, translation_size) for `preset` (or its built-in `parent`)."""
    source = _source_preset(preset, parent)
    if source is None:
        return (EVERYDAY_CAPTION_SIZE.value, EVERYDAY_TRANSLATION_SIZE.value)
    caption, translation = PRESET_SIZES[source]
    return (caption.value, translation.value)


PRESETS = {
    "everyday": (EVERYDAY_MODE, EVERYDAY_PATH),
    "conversation": (CONVERSATION_MODE, CONVERSATION_PATH),
    "video": (VIDEO_MODE, VIDEO_PATH),
    "learning": (LEARNING_MODE, LEARNING_PATH),
}
TIMINGS = {
    "steady": CaptionMode.STEADY,
    "instant": CaptionMode.INSTANT,
    "whole": CaptionMode.WHOLE,
    "scrolling": CaptionMode.SCROLLING,
    "calm": CaptionMode.CALM,
}
OFFERED = {
    "everyday": set(MODES) - {"inherit"},
    "conversation": {"instant", "steady"},
    "video": {"instant", "scrolling"},
    "learning": {"instant", "steady", "calm"},
}
RECOMMENDATION_REASONS: Mapping[str, str] = {
    "everyday": QT_TRANSLATE_NOOP(
        "CaptionWindow",
        "Shows words right away for general listening.",
    ),
    "conversation": QT_TRANSLATE_NOOP(
        "CaptionWindow",
        "Shows words with the least delay so you can reply in time.",
    ),
    "video": QT_TRANSLATE_NOOP(
        "CaptionWindow",
        "Keeps the previous subtitle above the next one when space allows.",
    ),
    "learning": QT_TRANSLATE_NOOP(
        "CaptionWindow",
        "Shows words right away as you study.",
    ),
}
"""One-line recommendation reasons per built-in preset (638)."""


@dataclass(frozen=True, slots=True)
class PresetRecommendation:
    """A built-in preset's recommended timing and one-line reason (638)."""

    preset: str
    recommended_timing: CaptionMode
    reason: str


def _source_preset(preset: str, parent: str | None = None) -> str | None:
    if preset in PRESETS:
        return preset
    if parent in PRESETS:
        return parent
    return None


def _resolved_mode(preset: str) -> CaptionMode:
    configured = PRESETS[preset][0].configured
    if configured == "inherit":
        configured = EVERYDAY_MODE.configured
    if configured == "inherit":
        return default_caption_mode()
    return TIMINGS[configured]


def recommendation_for(
    preset: str, parent: str | None = None
) -> PresetRecommendation | None:
    """The timing recommendation for `preset` (or its built-in `parent`), or None."""
    source = _source_preset(preset, parent)
    if source is None:
        return None
    return PresetRecommendation(
        preset=source,
        recommended_timing=_resolved_mode(source),
        reason=RECOMMENDATION_REASONS[source],
    )


def preset_defaults(preset: str) -> dict[str, object]:
    """Only named fields override the learner's Everyday setup."""
    if preset not in PRESETS:
        return {}
    mode, path = PRESETS[preset]
    fields: dict[str, object] = {}
    if mode.configured != "inherit":
        fields["caption_mode_chosen"] = TIMINGS[mode.configured].value
    if path.configured != "inherit":
        fields["caption_path"] = path.configured
    if preset == "video":
        fields["fade_after"] = VIDEO_FADE.configured
    return fields


# A preset stores only its own differences. Its active flat copy can also
# carry a change made after rolling back to an older desktop.
NATIVE_FIELDS = {
    "caption_mode_chosen": "caption_mode",
    "caption_path": "caption_path",
    "fade_after": "fade_after",
}


def choice_key(preset: str, field: str) -> str | None:
    if (
        preset not in PRESETS
        or field not in NATIVE_FIELDS
        or (field == "fade_after" and preset != "video")
    ):
        return None
    return f"presets.{preset}.{NATIVE_FIELDS[field]}"


def choice_value(field: str, value: object) -> object:
    if field == "caption_mode_chosen":
        return next(
            (name for name, mode in TIMINGS.items() if mode.value == value), value
        )
    return value


def learner_choices(stored: Mapping[str, object]) -> dict[str, object]:
    """Translate saved differences to registry names; never import names of custom presets."""
    result: dict[str, object] = {}
    presets = stored.get("preset_values")
    active = stored.get("preset")
    changed = stored.get("changed", list(stored))
    for preset in PRESETS:
        own = presets.get(preset) if isinstance(presets, dict) else None
        fields = dict(own) if isinstance(own, dict) else {}
        if preset == active:
            for field in NATIVE_FIELDS:
                if field in stored and (
                    field in fields
                    or isinstance(changed, (list, tuple))
                    and field in changed
                ):
                    fields[field] = stored[field]
        for field, value in fields.items():
            key = choice_key(preset, field)
            # None means fade disabled or app timing; neither is a numeric
            # override or a request for a particular timing.
            if key is not None and value is not None:
                choice = choice_value(field, value)
                # Settings offers every timing, including choices with a
                # runtime fallback. The tuning layer only takes offered modes.
                if field != "caption_mode_chosen" or choice in OFFERED[preset]:
                    result[key] = choice
    return result
