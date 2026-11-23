"""Presets for use cases (polyglotic-hq 556; desktop decision 0264): named
ways of using captions - Everyday, Conversation, Video, Learning, Custom
(a setup from before presets) and the learner's own - each holding the
values of the caption settings named in `PRESET_SETTINGS`. Plain Python
over `AppSettings`, no Qt.

- **Everyday is the base:** the app's defaults - every helper on (478,
  555) - with whatever the learner changes in it, and where a new install
  starts (Claude for the user, 2026-11-20: starting on "Custom" when
  nothing was customised reads wrong).
- **A preset names only what it's about** (`BUILT_IN`) and takes the rest
  from Everyday: so a learner's colours and timing chosen there follow
  them into Video until they change them in Video.
- **Custom** is a learner's setup from before presets (`from_flat`), kept
  whole and chosen, so nothing they chose is lost and nothing on screen
  changes; it is there only for a learner who had changed something.
- **Settings edits are saved explicitly** (587, decision 0283); bar changes
  save the fields they set (626, decision 0290). A Settings edit applies
  to the windows at once, and the chosen preset is then
  "edited" (`edits`): what the settings hold that it doesn't, until it's
  saved (`saved_into`), saved as a new one (`added`), or discarded
  (`discarded`). Its own changes, saved, are what differs from what it
  would have (`base_of`), kept by its key in `AppSettings.preset_values`.
- **Picking one** (`chosen`) writes its values over the settings, so
  everything that reads a setting - the caption windows, Settings, the
  server's languages - follows without knowing about presets. What wasn't
  saved in the one before goes, kept aside for Undo (`before`,
  `restored`).
- **The settings file keeps the chosen preset's values as always**, one key
  each: an older version reads them, and they win when this one reads the
  file again - kept as the window's, the preset still as saved, so an
  edited preset is still edited after a restart, and a change made after a
  rollback is kept (`from_flat`).
- **A setting that follows the app's default** (`FOLLOW_DEFAULT`, decision
  0220) keeps following it in a preset that doesn't name it, and is "a
  choice" in one that does (Video's no readings).

Holds no caption text.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, fields, replace
from typing import Any

from polyglotic_desktop.core.listening.preset_reading import (
    choice_key,
    choice_value,
    preset_defaults,
)
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.core.shared.tunables import refused_choices
from polyglotic_desktop.ui.settings import (
    BUILT_INS,
    FOLLOW_DEFAULT,
    AppSettings,
    as_valid,
)

EVERYDAY = "everyday"
CONVERSATION = "conversation"
VIDEO = "video"
LEARNING = "learning"
CUSTOM = "custom"
ORDER = (EVERYDAY, CONVERSATION, VIDEO, LEARNING)
"""The built-in presets, as the bar's dropdown and Settings list them;
Custom (where there is one) and the learner's own follow, in the order
made (`AppSettings.own_presets`)."""
OWN_MOST = 5
"""Presets of the learner's own at most."""
OWN_PREFIX = "own"
"""An own preset's key: "own1", "own2"... - never its name, which is the
learner's words and stays on this PC."""

PRESET_SETTINGS = (
    # what each caption shows
    "show_original",
    "show_translation",
    "show_language",
    "show_source",
    "fade_after",
    # help with words
    "word_links",
    "quiet_view",
    "reading_lines",
    "reading_past",
    "marks_off",
    "common_words_only",
    # the look
    "opacity",
    "original_color",
    "translation_color",
    "background_color",
    "caption_edge",
    "caption_weight",
    "caption_contrast",
    "caption_vibrance",
    # timing
    "caption_mode_chosen",
    "caption_path",
    "translation_after",
    "steady_newest_word",
    "steady_words_ahead",
    "steady_two_zones",
    "steady_cards",
    # what a window listens for and translates
    "lyrics",
    "preset_languages",
    "preset_second_languages",
    # the windows
    "subtitles",
    "subtitle_size",
    "subtitle_width",
    "my_speech",
)
"""The settings a preset holds - every one, in every preset. The rest
(app-wide language defaults, sound, dictation, learning and the app's own)
are the same in all of them."""

BAR_SOURCE_SETTINGS = ("lyrics", "preset_languages", "preset_second_languages")
"""Saved per preset; language maps have local window keys and stay on this PC."""


BUILT_IN: Mapping[str, Mapping[str, object]] = {
    EVERYDAY: {},
    CONVERSATION: {
        "word_links": "hover",  # only the word pointed at: a busy call stays calm
        "steady_newest_word": True,  # a quarter second sooner (DECISIONS #233 B)
        "my_speech": True,  # what you said, as "You", in every window
    },
    VIDEO: {
        "subtitles": True,  # the bottom of the screen, wide, large, three lines
        "word_links": "off",
        "quiet_view": False,
        "reading_lines": (),
        "marks_off": True,
        "show_language": False,
        "show_source": False,
        "opacity": 0.0,  # no box: the letters outlined, as subtitles are
        "caption_edge": "outline",
        "steady_two_zones": False,
        # Instant (polyglotic-hq 587, from 585's recorder; the user,
        # 2026-11-21: "seems like instant mode is the only usable mode for
        # videos preset"): Video with Steady lost 19 of 43 translations and
        # never drew 7 cards, with Instant none. Steady's card stack (552,
        # decision 0260) stays named for a learner who picks Steady in it:
        # Video captions along the bottom (`CaptionWindows.set_subtitles`)
        "steady_cards": True,
        "my_speech": False,
    },
    LEARNING: {
        "word_links": "arrows",
        "quiet_view": False,
        "reading_past": False,
        "marks_off": False,
        "common_words_only": True,
    },
}
"""What each built-in preset names; anything else is Everyday's."""

BUILT_IN_BEFORE: Mapping[int, Mapping[str, Mapping[str, object]]] = {
    2: {VIDEO: {"caption_mode_chosen": "words"}},  # Steady, until 587
    3: {
        CONVERSATION: {"caption_mode_chosen": None},  # inherited Everyday
        LEARNING: {"caption_mode_chosen": None},
    },
    4: {VIDEO: {"caption_mode_chosen": "live"}},  # Instant, until 638
    5: {VIDEO: {"caption_mode_chosen": "steady"}},  # Subtitle blocks, until 705
}
"""What a built-in preset named before each version of `BUILT_IN`
(`settings.BUILT_INS`): the chosen one, untouched, follows its new value
when a file from before is read (`from_flat`); one the learner saved
another value in keeps theirs."""


def is_own(key: str) -> bool:
    """One the learner made (not Custom, which moved over)."""
    return key.startswith(OWN_PREFIX) and key[len(OWN_PREFIX) :].isdigit()


def parent_of(value: AppSettings, key: str) -> str | None:
    """The built-in preset `key` is or was saved from, or None (638)."""
    if key in ORDER:
        return key
    parent = value.preset_parents.get(key)
    return parent if parent in ORDER else None


def keys(value: AppSettings) -> tuple[str, ...]:
    """Every preset there is, in the dropdown's order."""
    return (*ORDER, *value.own_presets)


def exists(value: AppSettings, key: str) -> bool:
    return key in ORDER or key in value.own_presets


def can_add(value: AppSettings) -> bool:
    """Another of the learner's own can be made (OWN_MOST; Custom aside)."""
    return sum(1 for key in value.own_presets if is_own(key)) < OWN_MOST


def _defaults() -> dict[str, object]:
    defaults = AppSettings()
    return {name: getattr(defaults, name) for name in PRESET_SETTINGS}


def base_of(value: AppSettings, key: str) -> tuple[dict[str, object], frozenset[str]]:
    """What preset `key` would have without its own changes, and which of
    those values are named - by Everyday's changes or by the preset -
    rather than the app's defaults: Everyday's is the app's defaults; a
    built-in's, Everyday's values with its own named over them; Custom's
    and the learner's own, Everyday's."""
    values = _defaults()
    defaults = preset_defaults(EVERYDAY)
    values.update(defaults)
    if key == EVERYDAY:
        return values, frozenset(defaults)
    everyday = value.preset_values.get(EVERYDAY, {})
    named = {
        name: setting
        for name, setting in everyday.items()
        if name not in BAR_SOURCE_SETTINGS
    }
    named.update(BUILT_IN.get(key, {}))
    named.update(preset_defaults(key))
    values.update(named)
    return values, frozenset(named)


def values_of(value: AppSettings, key: str) -> tuple[dict[str, object], frozenset[str]]:
    """Preset `key`'s values - what it would have, with its own changes
    over them - and which are named (not the app's defaults)."""
    values, named = base_of(value, key)
    own = value.preset_values.get(key, {})
    values.update(own)
    return values, named | frozenset(own)


def own_changes(value: AppSettings) -> dict[str, object]:
    """The chosen preset's own changes as the settings have them now: each
    preset setting that differs from what the preset would have - and one
    that follows the app's default where the preset doesn't name it, made
    a choice on this PC (`changed`), even at the default's value (the
    learner turned every reading line off: () as a choice)."""
    base, named = base_of(value, value.preset)
    found: dict[str, object] = {}
    for name in PRESET_SETTINGS:
        now = getattr(value, name)
        if name in FOLLOW_DEFAULT:
            chosen = name in value.changed
            if chosen and (name not in named or now != base[name]):
                found[name] = now
            continue
        if now != base[name]:
            found[name] = now
    return found


def edits(value: AppSettings) -> tuple[str, ...]:
    """The preset settings the windows have changed from the chosen preset
    as it was saved - its changes not saved (587), in `PRESET_SETTINGS`'
    order; none while it's as saved. Only the preset's own settings: the
    app's language, hotkeys, account and the rest are never among them. A
    setting that follows the app's default and one chosen at the same value
    look the same, so neither is a change."""
    saved, _ = values_of(value, value.preset)
    return tuple(
        name for name in PRESET_SETTINGS if getattr(value, name) != saved[name]
    )


def saved_into(
    value: AppSettings, only: Collection[str] = PRESET_SETTINGS
) -> AppSettings:
    """Save the chosen preset, or save only the fields changed from the bar."""
    own = {
        name: stored
        for name, stored in value.preset_values.get(value.preset, {}).items()
        if name not in only
    }
    own.update({name: now for name, now in own_changes(value).items() if name in only})
    kept = {k: v for k, v in value.preset_values.items() if k != value.preset}
    if own:
        kept[value.preset] = own
    if kept == value.preset_values:
        return value
    return replace(value, preset_values=kept)


def discarded(value: AppSettings) -> AppSettings:
    """`value` with the chosen preset's changes not saved gone - "Discard
    changes" (587): the windows back to the preset as it was saved."""
    return chosen(value, value.preset)


def restorable(value: AppSettings, key: str) -> bool:
    """A built-in preset the learner has saved changes in: "Restore
    Everyday's defaults" (`reset`) takes them out (587)."""
    return key in ORDER and bool(value.preset_values.get(key))


def chosen(value: AppSettings, key: str) -> AppSettings:
    """`value` with preset `key` chosen: its values, as saved, over the
    settings, and the record of changes saying which of the settings that
    follow the app's default are named by it (a choice) and which still
    follow it. What the preset before had that wasn't saved goes - kept
    aside by whoever offers Undo (`before`; 587)."""
    if not exists(value, key):
        return value
    values, named = values_of(value, key)
    following = {
        name for name in PRESET_SETTINGS if name in FOLLOW_DEFAULT and name not in named
    }
    changed = [name for name in value.changed if name not in following]
    changed += [
        name
        for name in PRESET_SETTINGS
        if name in named and name in FOLLOW_DEFAULT and name not in changed
    ]
    return replace(value, preset=key, changed=tuple(changed), **values)  # type: ignore[arg-type]


def reset(value: AppSettings, key: str) -> AppSettings:
    """Preset `key` without its own changes - and, while it's chosen, its
    values over the settings. Everyday's reset is the app's defaults (every
    preset taking Everyday's values follows); Custom's, Everyday's."""
    kept = {k: v for k, v in value.preset_values.items() if k != key}
    value = replace(value, preset_values=kept)
    if value.preset != key:
        return value
    values, named = values_of(value, key)
    changed = tuple(
        name
        for name in value.changed
        if name not in PRESET_SETTINGS or name not in FOLLOW_DEFAULT or name in named
    )
    return replace(value, changed=changed, **values)  # type: ignore[arg-type]


def added(value: AppSettings, name: str) -> AppSettings:
    """A preset of the learner's own, made from the settings as they are now
    and chosen - "Save as new preset…" (587): the preset they were in stays
    as it was saved. Keeps its built-in parent's timing recommendation (638).
    None past OWN_MOST."""
    if not can_add(value):
        return value
    taken = set(value.own_presets)
    number = next(n for n in range(1, OWN_MOST + 2) if f"{OWN_PREFIX}{n}" not in taken)
    key = f"{OWN_PREFIX}{number}"
    names = dict(value.preset_names)
    names[key] = name
    parents = dict(value.preset_parents)
    parent = parent_of(value, value.preset)
    if parent is not None:
        parents[key] = parent
    made = replace(
        value,
        own_presets=(*value.own_presets, key),
        preset_names=names,
        preset_parents=parents,
        preset=key,
    )
    return saved_into(made)


def removed(value: AppSettings, key: str) -> AppSettings:
    """A preset of the learner's own - or Custom - deleted; Everyday chosen
    if it was."""
    if key not in value.own_presets:
        return value
    if value.preset == key:
        value = chosen(value, EVERYDAY)
    return replace(
        value,
        own_presets=tuple(k for k in value.own_presets if k != key),
        preset_values={k: v for k, v in value.preset_values.items() if k != key},
        preset_names={k: v for k, v in value.preset_names.items() if k != key},
        preset_parents={k: v for k, v in value.preset_parents.items() if k != key},
    )


def renamed(value: AppSettings, key: str, name: str) -> AppSettings:
    """Preset `key` named `name` - "" takes a built-in one or Custom back
    to its own name (an own preset keeps the one it has)."""
    name = name.strip()[:NAME_MOST]
    names = dict(value.preset_names)
    if name:
        names[key] = name
    elif not is_own(key):
        names.pop(key, None)
    return replace(value, preset_names=names)


NAME_MOST = 40
"""Characters in a preset's name."""


def follow_reading_defaults(
    value: AppSettings, stored: Mapping[str, object]
) -> AppSettings:
    """Update untouched active preset fields before from_flat infers its differences.
    Preserve choices recorded in the preset or marked changed in the flat settings.
    A legacy file without a changed record keeps its settings.
    """
    refused = refused_choices()
    preset = value.preset
    fields = {"caption_mode_chosen", "caption_path"}
    if preset == VIDEO:
        fields.add("fade_after")

    def rejected(key: str, field: str, raw: object) -> bool:
        name = choice_key(key, field)
        return (
            name is not None
            and name in refused
            and refused[name] == choice_value(field, raw)
        )

    if refused:
        # Keep unrelated preset customisations, including choices made since
        # startup. Discard only the values refused by this load.
        kept = {
            key: {
                field: raw
                for field, raw in own.items()
                if not rejected(key, field, raw)
            }
            for key, own in value.preset_values.items()
        }
        value = replace(
            value, preset_values={key: own for key, own in kept.items() if own}
        )
    declined = {name for name in fields if rejected(preset, name, getattr(value, name))}
    if stored and ("changed" not in stored or "preset" not in stored):
        fields = declined
    if not fields:
        return value
    defaults, _ = base_of(value, preset)
    own = value.preset_values.get(preset, {})
    updates = {
        name: defaults[name]
        for name in fields
        if (name in declined or name not in own and name not in value.changed)
        and defaults[name] != getattr(value, name)
    }
    if declined:
        value = replace(
            value, changed=tuple(name for name in value.changed if name not in declined)
        )
    if not updates:
        return value
    return replace(value, **updates)  # type: ignore[arg-type]


def from_flat(
    value: AppSettings, before_presets: bool = False, built_ins: int = BUILT_INS
) -> AppSettings:
    """The settings as read. A file from before presets (`before_presets`)
    with any preset setting chosen becomes Custom, chosen and saved - its
    own changes every preset setting it records as changed - and one with
    none, or a new install, Everyday. Every preset keeps what was saved in
    it (556's, saved at once, too); the flat values are the windows', so a
    chosen preset edited and not saved is still edited, and a change made
    by an older version after a rollback is kept (587). A file that follows
    an older version of the built-ins (`built_ins`) has the chosen one's
    untouched values moved to their new ones (`BUILT_IN_BEFORE`). Presets or
    values not valid are dropped."""
    if before_presets:
        setup = own_changes(replace(value, preset=EVERYDAY, preset_values={}))
        if setup:
            value = replace(value, preset=CUSTOM, own_presets=(CUSTOM,))
        else:
            value = replace(value, preset=EVERYDAY)
    if not exists(value, value.preset):
        value = replace(value, preset=EVERYDAY)
    kept: dict[str, dict[str, object]] = {}
    for key, own in value.preset_values.items():
        valid = valid_values(own)
        if valid and exists(value, key) and (key != value.preset or not before_presets):
            kept[key] = valid
    names = {
        k: v[:NAME_MOST]
        for k, v in value.preset_names.items()
        if exists(value, k) and v.strip()
    }
    parents = {
        k: v
        for k, v in value.preset_parents.items()
        if is_own(k) and exists(value, k) and v in ORDER
    }
    if built_ins < 3:
        if value.lyrics:
            for key in keys(value):
                kept.setdefault(key, {}).setdefault("lyrics", True)
        if (
            not before_presets
            and kept.get(EVERYDAY, {}).get("caption_mode_chosen") is None
        ):
            # A custom preset which followed the old global default keeps Steady.
            for key in value.own_presets:
                own = kept.setdefault(key, {})
                if own.get("caption_mode_chosen") is None:
                    own["caption_mode_chosen"] = "words"
            if value.preset in value.own_presets and value.caption_mode_chosen is None:
                value = replace(value, caption_mode_chosen="words")
    value = replace(
        value, preset_values=kept, preset_names=names, preset_parents=parents
    )
    value = _followed(value, built_ins)
    return saved_into(value) if before_presets else value


def _followed(value: AppSettings, since: int) -> AppSettings:
    """`value` with the chosen built-in preset's values that changed after
    version `since` of the built-ins moved to the new ones - where the
    windows still have the old value and the learner saved none of their
    own - and the built-ins' version now theirs."""
    saved = value.preset_values.get(value.preset, {})
    now, _ = base_of(value, value.preset)
    moves: dict[str, object] = {}
    for version, before_then in sorted(BUILT_IN_BEFORE.items()):
        if version <= since:
            continue
        for name, was in before_then.get(value.preset, {}).items():
            if version == 3:
                was = value.preset_values.get(EVERYDAY, {}).get(name, was)
            if name in now and name not in saved and getattr(value, name) == was:
                moves[name] = now[name]
    return replace(value, built_ins=BUILT_INS, **moves)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Before:
    """The presets and the windows' preset settings as they were before a
    step that loses something - picking another preset with changes not
    saved, discarding them, a reset or a delete - for Undo (`restored`;
    587). Kept in memory for a few seconds, never in the file."""

    preset: str
    values: Mapping[str, object]
    """Each preset setting as the windows had it."""
    choices: tuple[str, ...]
    """The preset settings named in the record of changes (`changed`)."""
    preset_values: Mapping[str, Mapping[str, object]]
    preset_names: Mapping[str, str]
    preset_parents: Mapping[str, str]
    own_presets: tuple[str, ...]


def before(value: AppSettings) -> Before:
    """What Undo gives back after the next step (`restored`)."""
    return Before(
        value.preset,
        {name: getattr(value, name) for name in PRESET_SETTINGS},
        tuple(name for name in value.changed if name in PRESET_SETTINGS),
        {k: dict(v) for k, v in value.preset_values.items()},
        dict(value.preset_names),
        dict(value.preset_parents),
        value.own_presets,
    )


def restored(value: AppSettings, was: Before) -> AppSettings:
    """`value` with the presets, the chosen one and its changes not saved as
    they were (`was`) - Undo (587). Everything else - the app's language,
    the languages, sound - stays as it is now."""
    changed = (
        *(name for name in value.changed if name not in PRESET_SETTINGS),
        *was.choices,
    )
    return replace(
        value,
        preset=was.preset,
        preset_values={k: dict(v) for k, v in was.preset_values.items()},
        preset_names=dict(was.preset_names),
        preset_parents=dict(was.preset_parents),
        own_presets=was.own_presets,
        changed=changed,
        **was.values,  # type: ignore[arg-type]
    )


def valid_values(own: Mapping[str, object]) -> dict[str, object]:
    """A preset's stored changes, each a preset setting and valid for it."""
    defaults = AppSettings()
    found: dict[str, Any] = {}
    names = {f.name for f in fields(AppSettings)}
    for name, stored in own.items():
        if name not in PRESET_SETTINGS or name not in names:
            continue
        valid = as_valid(name, stored, getattr(defaults, name))
        if valid is not None:
            found[name] = valid[0]
    return found


def stored_values(own: Mapping[str, object]) -> dict[str, object]:
    """A preset's changes as the settings file keeps them (lists, not
    tuples)."""
    return {k: list(v) if isinstance(v, tuple) else v for k, v in own.items()}


def differences(value: AppSettings, key: str) -> dict[str, object]:
    """What preset `key` changes, as Settings lists it: each value of its
    that differs from Everyday's - Everyday's, from the app's defaults - and
    a setting that follows the app's default where it names one and
    Everyday doesn't (Video's readings: none, not the default). As saved:
    the chosen one's changes not saved aren't in it yet (587)."""
    values, named = values_of(value, key)
    if key == EVERYDAY:
        against, against_named = _defaults(), frozenset[str]()
    else:
        against, against_named = values_of(value, EVERYDAY)
    return {
        name: values[name]
        for name in PRESET_SETTINGS
        if values[name] != against[name]
        or (name in FOLLOW_DEFAULT and name in named and name not in against_named)
    }


USAGE_COLOURS = ("original_color", "translation_color", "background_color")
"""Colours are counted as changed, never by their value (556)."""


def usage(value: AppSettings) -> dict[str, str | int | float | bool]:
    """The preset in use as the session summary's optional properties
    (polyglotic-hq 556; polyglotic-server's tracking plan,
    `listening_session_ended`): `preset` - a built-in's key, "custom", or
    "own" for one of the learner's (never its name) - and `preset_<setting>` for each
    setting in it that differs from the preset's own defaults: a fixed
    list's value, a number or a switch. Colours only as changed (True);
    the reading lines as how many are on; fade after quiet 0 for never; my
    speech "on", "off" or "each"; the caption mode "default" while it
    follows the app's. Nothing a learner typed, no caption text."""
    found: dict[str, str | int | float | bool] = {
        "preset": value.preset if value.preset in (*ORDER, CUSTOM) else "own"
    }
    for name, now in own_changes(value).items():
        if name not in BAR_SOURCE_SETTINGS:
            found[f"preset_{name}"] = _usage_value(name, now)
    return found


def _usage_value(name: str, value: object) -> str | int | float | bool:
    if name in USAGE_COLOURS:
        return True
    if name == "reading_lines":
        return len(value) if isinstance(value, tuple | list) else 0
    if name == "fade_after":
        return float(value) if isinstance(value, int | float) else 0.0
    if name == "my_speech":
        return "each" if value is None else "on" if value else "off"
    if name == "caption_mode_chosen":
        return "default" if value is None else CaptionMode(str(value)).usage_value
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | float):
        return value
    return str(value)
