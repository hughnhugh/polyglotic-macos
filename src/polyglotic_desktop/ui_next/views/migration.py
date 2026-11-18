"""Today's caption settings moved to each caption window's own - once
(polyglotic-hq project 109's structure, sections 1.1 and 9; build step 6).
Plain Python, no Qt.

Today's interface keeps one set for every overlay: the target languages
(an overlay each), "Caption my own speech", the text size, and where the
overlays were put - by target language. The new interface keeps them per
caption window, by source (`views.caption_window`, one setting:
`caption_windows`). The first time it runs - while no window has stored
settings of its own - each of today's sources (the apps picked, in
order; or everything the PC plays, "system") gets:
- **translate into** today's first target language (`targets[0]`);
- **show my speech** as "Caption my own speech" was (`caption_mic`) -
  in every window;
- **text size** today's (`text_scale`);
- **spoken language** today's one for every window (`spoken_language`;
  none is Detect) - and a window stored before windows had their own
  takes it too (a value missing from its own; polyglotic-hq 263);
- **its place**: today's position preset (`overlay_position`); "Where I
  put it" is where the first target language's overlay was put
  (`overlay_geometry`, by language), for the first source - the others
  at their preset's default slots, so no two open on top of each other.

The rules:
- **It runs once.** What it gives the windows is saved at once
  (`CaptionWindows`), and from then on each window's own are read - a
  change made later in today's interface doesn't move them again.
- **A window with settings of its own is never changed by it;** a value
  missing from them takes today's.
- **Today's keys stay** as they were, so today's interface - it still
  runs until the switch-over (109's step 9) - reads what it did, and
  whichever interface runs next loses nothing: the windows' setting is
  one key beside today's, kept by `ui.settings` (which keeps keys it
  doesn't know and reads them again before each save) and written by the
  caption windows the same way (only their own key, every other key as
  the file holds it then).
- A window opened later, for a source today's settings didn't name,
  copies the last window's language, text size and mode (109's section
  2) - except while nothing has been saved yet: then it takes today's
  values too.
- Not carried: today's Width slider (`overlay_width`) - a window starts
  at its default width and is resized by its edges (109's section 9).
"""

from collections.abc import Mapping
from dataclasses import replace

from polyglotic_desktop.ui_next.views.caption_window import (
    SPOKEN_LANGUAGES,
    STORED_KEY,
    StoredWindows,
    WindowChoices,
    rect_from,
    text_size,
)
from polyglotic_desktop.ui_next.views.placement import Preset

SYSTEM = "system"
"""Everything the PC plays: its window's key (today's
`ui.settings.SOURCE_KEY_SYSTEM`)."""


def stored_windows(stored: Mapping[str, object]) -> StoredWindows:
    """The caption windows' choices, from the whole settings file: their
    own setting if there is one - anything missing from it taken from
    today's values - or else today's values moved over (`moved_over`)."""
    own = stored.get(STORED_KEY)
    if isinstance(own, Mapping):
        return StoredWindows.from_stored(own, todays_values(stored))
    return moved_over(stored)


def moved_over(stored: Mapping[str, object]) -> StoredWindows:
    """Today's values as each of today's sources' own choices, the first
    at today's place, the others at their default slots. `first_use` is
    set: nothing is saved yet."""
    today = todays_values(stored)
    by_key = {}
    for index, key in enumerate(todays_sources(stored)):
        by_key[key] = today if index == 0 else at_default_slot(today)
    # today's apps had windows: the first window's set-up isn't for them (465)
    return StoredWindows(by_key, today, first_use=True, set_up=bool(by_key))


def todays_values(stored: Mapping[str, object]) -> WindowChoices:
    """One window's choices from today's settings: the first target
    language, the text size, "Caption my own speech" and the overlays'
    position - a preset as it was; "custom" as where the first target
    language's overlay was put (or Bottom centre, if that wasn't kept).
    Anything missing or not valid: the defaults."""
    base = WindowChoices()
    targets = stored.get("targets")
    if isinstance(targets, list) and targets and isinstance(targets[0], str):
        base = replace(base, translate_into=targets[0])
    size = text_size(stored.get("text_scale"))
    if size is not None:
        base = replace(base, text_size=size)
    if isinstance(stored.get("caption_mic"), bool):
        base = replace(base, show_mic=bool(stored["caption_mic"]))
    if stored.get("spoken_language") in SPOKEN_LANGUAGES:  # None: Detect
        base = replace(base, spoken_language=str(stored["spoken_language"]))
    position = stored.get("overlay_position")
    if position in {p.value for p in Preset}:
        base = replace(base, preset=Preset(str(position)))
    if base.preset is Preset.CUSTOM:
        places = stored.get("overlay_geometry")
        place = None
        if isinstance(places, Mapping) and base.translate_into:
            place = rect_from(places.get(base.translate_into))
        base = (
            replace(base, geometry=place)
            if place
            else replace(base, preset=Preset.BOTTOM_CENTRE)
        )
    return base


def todays_sources(stored: Mapping[str, object]) -> list[str]:
    """What today's settings caption, as the windows' keys: everything the
    PC plays, or the apps picked in order (each once). Everything the PC
    plays only where it was chosen: from 0.1.8 the file names what was
    changed (`changed`), and a new learner's file holds it on as the default
    before any window has opened (polyglotic-hq 484) - that learner had no
    window of today's, and their first window is set up as a first."""
    changed = stored.get("changed")
    chosen = not isinstance(changed, list) or "whole_system" in changed
    if stored.get("whole_system") is True and chosen:
        return [SYSTEM]
    apps = stored.get("apps")
    if not isinstance(apps, list):
        return []
    return list(dict.fromkeys(a for a in apps if isinstance(a, str) and a))


def at_default_slot(choices: WindowChoices) -> WindowChoices:
    """`choices` at their preset's default slot - "Where I put it" at
    Bottom centre's."""
    preset = Preset.BOTTOM_CENTRE if choices.preset is Preset.CUSTOM else choices.preset
    return replace(choices, preset=preset, geometry=None)
