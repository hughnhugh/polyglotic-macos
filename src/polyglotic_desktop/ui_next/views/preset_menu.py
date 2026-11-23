"""What the caption windows' preset dropdown and Settings > Presets show -
plain Python, no Qt (polyglotic-hq 556, desktop decision 0264).

`main` makes a `PresetMenu` from the settings (`ui.use_presets`, which the
new interface can't import) every time they change, and hands it to every
caption window and to Settings; the learner's clicks go back as signals,
and `main` makes the change. Holds no caption text.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from polyglotic_desktop.core.listening.preset_reading import VIDEO_LINES
from polyglotic_desktop.ui_next.views.panels import Shared


class Show(StrEnum):
    """What every caption shows: the dropdown's one choice of lines."""

    BOTH = "both"
    ORIGINAL = "original"
    """What was said only: no translation, in any window."""
    TRANSLATION = "translation"
    """The translation only: what was said hidden."""


@dataclass(frozen=True, slots=True)
class PresetItem:
    """A preset as listed: its key ("video", "own1"), its name - the
    learner's, where they renamed it - whether it's the learner's
    rather than built in (Custom, or one they made: these can be deleted),
    and the built-in `parent` an own preset was saved from (638)."""

    key: str
    name: str
    own: bool = False
    parent: str | None = None


class Undo(StrEnum):
    """A step that lost something, offered back for a few seconds (587)."""

    SWITCHED = "switched"
    """Another preset picked: the one before's changes not saved went."""
    DISCARDED = "discarded"
    RESTORED = "restored"
    """A built-in's saved changes taken out: its defaults back."""
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class PresetMenu:
    """The presets, the chosen one, and what's on in it: its Show, and the
    options added on top - word links, quiet view and readings.
    `changes`: what the chosen one changes from
    what it would have, as saved, as Settings lists them (the setting's name
    and its value, in words); `can_add`: another preset of the learner's own
    can be made. `edited`: how many of the chosen one's settings the
    windows have changed and it hasn't saved (587); `restorable`: a
    built-in the learner saved changes in; `undo`: a step that lost
    something, and the preset it was in, while Undo is offered."""

    items: tuple[PresetItem, ...] = ()
    chosen: str = "everyday"
    show: Show = Show.BOTH
    links: bool = False
    quiet: bool = False
    readings: bool = False
    changes: tuple[tuple[str, str], ...] = ()
    can_add: bool = True
    edited: int = 0
    restorable: bool = False
    undo: tuple[Undo, str] | None = None
    video_lines_shown: int = field(default_factory=lambda: VIDEO_LINES.value)

    @property
    def name(self) -> str:
        """The chosen preset's name ("" before any is known)."""
        return next((i.name for i in self.items if i.key == self.chosen), "")

    @property
    def chosen_own(self) -> bool:
        return any(i.own for i in self.items if i.key == self.chosen)

    @property
    def chosen_parent(self) -> str | None:
        """The built-in parent the chosen own preset was saved from, or None (638)."""
        return next((i.parent for i in self.items if i.key == self.chosen), None)

    @property
    def new_name(self) -> str:
        """The name "Save as new preset…" suggests: the chosen one's with
        the first number free - "Learning 2", then "Learning 3"."""
        taken = {i.name.casefold() for i in self.items}
        number = 2
        while f"{self.name} {number}".casefold() in taken:
            number += 1
        return f"{self.name} {number}"


class PresetsView(Shared[PresetMenu]):
    """The presets as Settings > Presets shows them: `follow`ed from the
    settings, and the learner's steps handed to `main` through the
    callables it sets - pick, rename, reset, add, delete (556); save,
    discard and undo (587). `naming`: "Save as new preset…" asks for a name
    on the Settings line, a window's dropdown sending the learner there
    (it never takes the keyboard)."""

    def __init__(self, menu: PresetMenu | None = None) -> None:
        super().__init__(menu or PresetMenu())
        self.chose: Callable[[str], None] = lambda key: None
        self.rename: Callable[[str, str], None] = lambda key, name: None
        self.reset: Callable[[str], None] = lambda key: None
        self.add: Callable[[str], None] = lambda name: None
        self.delete: Callable[[str], None] = lambda key: None
        self.save: Callable[[], None] = lambda: None
        self.discard: Callable[[], None] = lambda: None
        self.undo: Callable[[], None] = lambda: None
        self.naming = Shared(False)
