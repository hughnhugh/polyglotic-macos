"""Sound: which speakers and which mic, and whether what I say is
captioned - one state, shown on Home and in Settings > Speech alike
(polyglotic-hq 372; the user, 2026-11-15, DECISIONS #175: "Home should
have an area to choose speaker / microphone settings").

- **What you hear**: the apps added on Home are captioned whichever
  speakers play them (each app's own sound, decision 0076); everything the
  PC plays is heard from one output - Windows' default, or one the learner
  picks (`AppSettings.speaker_device`). The mic's check for the PC's own
  sound (decision 0004) listens to the same output.
- **What you say**: captioned or not - in every caption window, the tray's
  "Caption my own speech" (`caption_mic`; a window's "Show my speech here"
  turns it on there alone) - and which mic: Windows' default, or one picked
  (`AppSettings.mic_device`, dictation's too). The mic's level shows while
  it's captioned: the mic is never opened just to show a level.

A device chosen and then unplugged isn't forgotten: Windows' default is
used meanwhile, and it comes back when plugged in again (the capture's own
`wanted_device`). Devices' ids and names stay on this PC.

Plain Python, no Qt: `SoundCommands` (`main`) carries out the choices,
and `follow` brings back what they changed.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices
from polyglotic_desktop.ui_next.views.panels import Shared

LEVEL_FLOOR_DB = -60.0
"""The level meter's empty end: quieter than a quiet room at a mic."""


@dataclass(frozen=True, slots=True)
class Sound:
    """What the Sound card shows. `speaker` and `mic`: the ids chosen (None:
    Windows' default). `whole_system`: everything the PC plays is captioned
    now - where the speakers matter. `my_speech`: what I say is captioned in
    a window. `level`: the mic's level now, 0.0 to 1.0 (None: not captured)."""

    devices: SoundDevices = field(default_factory=SoundDevices)
    speaker: str | None = None
    mic: str | None = None
    whole_system: bool = False
    my_speech: bool = False
    level: float | None = None

    def speakers(self) -> list[tuple[str | None, SoundDevice | None]]:
        """The speakers' choices in order: Windows' default (with the
        device it is now, if known), then each plugged in."""
        return _choices(self.devices.speakers, self.devices.default_speaker)

    def mics(self) -> list[tuple[str | None, SoundDevice | None]]:
        return _choices(self.devices.mics, self.devices.default_mic)

    @property
    def speaker_missing(self) -> bool:
        """The speakers chosen aren't plugged in: Windows' default is used."""
        return _missing(self.speaker, self.devices.speakers)

    @property
    def mic_missing(self) -> bool:
        return _missing(self.mic, self.devices.mics)


def _choices(
    plugged: tuple[SoundDevice, ...], default: str | None
) -> list[tuple[str | None, SoundDevice | None]]:
    now = next((d for d in plugged if d.id == default), None)
    return [(None, now), *((d.id, d) for d in plugged)]


def _missing(chosen: str | None, plugged: tuple[SoundDevice, ...]) -> bool:
    return chosen is not None and all(d.id != chosen for d in plugged)


def level_of(peak: float | None) -> float | None:
    """A mic's peak (0.0 to 1.0 of full scale) as the meter's fill: on a
    decibel scale from LEVEL_FLOOR_DB to 0 dB, as a level meter reads -
    so speech at a normal distance fills about half of it."""
    if peak is None:
        return None
    if peak <= 0.0:
        return 0.0
    db = 20.0 * math.log10(min(1.0, peak))
    return max(0.0, min(1.0, 1.0 - db / LEVEL_FLOOR_DB))


class SoundCommands(Protocol):
    """What `main` does with the learner's choices."""

    def set_speaker_device(self, device: str | None) -> None: ...

    def set_mic_device(self, device: str | None) -> None: ...

    def set_my_speech(self, on: bool) -> None: ...

    def look_for_devices(self, found: Callable[[SoundDevices], None]) -> None:
        """The devices plugged in now, handed to `found` - at once, or once
        they're listed: a Mac took 1.9 s to list them, and the interface
        waited (polyglotic-hq 523, 563)."""
        ...

    def mic_peak(self) -> float | None:
        """The mic's loudest sample over the last tenth of a second, 0.0 to
        1.0 of full scale - None while it isn't captured."""
        ...


class SoundView(Shared[Sound]):
    """The Sound card's view: one value, however many cards show it."""

    def __init__(self, value: Sound, commands: SoundCommands) -> None:
        super().__init__(value)
        self.commands = commands

    def look_again(self) -> None:
        """The devices plugged in, looked at again (a card shown, a list
        opened): a device plugged in since shows - when they're listed."""
        self.commands.look_for_devices(self._found)

    def _found(self, devices: SoundDevices) -> None:
        if devices != self.value.devices:
            self.follow(_with(self.value, devices=devices))

    def set_speaker(self, device: str | None) -> None:
        if device != self.value.speaker:
            self.commands.set_speaker_device(device)

    def set_mic(self, device: str | None) -> None:
        if device != self.value.mic:
            self.commands.set_mic_device(device)

    def set_my_speech(self, on: bool) -> None:
        if on != self.value.my_speech:
            self.commands.set_my_speech(on)

    def read_level(self) -> None:
        """The mic's level now (`level_of`), while it's captioned - the
        card asks, every tenth of a second while it shows."""
        level = level_of(self.commands.mic_peak()) if self.value.my_speech else None
        if level != self.value.level:
            self.follow(_with(self.value, level=level))


def _with(value: Sound, **changes: object) -> Sound:
    return replace(value, **changes)  # type: ignore[arg-type]
