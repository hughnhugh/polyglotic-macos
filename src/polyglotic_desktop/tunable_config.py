"""Desktop wiring shared by startup and the CLI; importing reading_rule collects its declarations."""

import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from polyglotic_desktop.adapters.tunables_file import read
from polyglotic_desktop.core.listening import (
    dictation_keys,  # noqa: F401 - register hotkey hold tunables before resolving overrides
    type_theirs,  # noqa: F401 - register speaker hold tunables on every OS
)
from polyglotic_desktop.core.listening.preset_reading import learner_choices
from polyglotic_desktop.core.shared.tunables import (
    Resolution,
    declarations,
    install,
    resolve,
)
from polyglotic_desktop.ui_next import fonts  # noqa: F401 - register script size scales before resolving overrides
from polyglotic_desktop.ui_next.views import respeaking  # noqa: F401 - register its display dimensions before resolving overrides
from polyglotic_desktop.ui_next.views.reading_rules import reading_rule


def configuration(
    cohort: Mapping[str, object],
    local: Mapping[str, object],
    learner: Mapping[str, object],
) -> Resolution:
    return resolve(
        (("cohort", cohort), ("local", local), ("learner", learner)), (reading_rule,)
    )


def changed_settings(stored: Mapping[str, object]) -> dict[str, object]:
    """Only registered settings the learner changed. Pre-0.1.8 files kept no change record."""
    changed = stored.get("changed", list(stored))
    if not isinstance(changed, (list, tuple)):
        return {}
    known = declarations()
    return {
        f"settings.{key}": stored[key]
        for key in changed
        if isinstance(key, str) and key in stored and f"settings.{key}" in known
    }


def load(
    data: Path,
    override: Path | None,
    stored: Mapping[str, object],
    *,
    cohort: Mapping[str, object] | None = None,
) -> Resolution:
    log = logging.getLogger(__name__)
    file_warnings: tuple[str, ...] = ()
    try:
        local = read(override or data / "tunables.toml", optional=override is None)
    except (OSError, ValueError, RecursionError) as error:
        # Parser messages can contain file contents; report the category only.
        file_warnings = (f"local file refused ({type(error).__name__})",)
        local = {}
    result = configuration(
        cohort or {}, local, changed_settings(stored) | learner_choices(stored)
    )
    if file_warnings:
        result = replace(result, warnings=file_warnings + result.warnings)
    for warning in result.warnings:
        log.warning("tunables: %s", warning)
    install(result)
    return result
