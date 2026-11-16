"""A Mac's audio devices as they are right now, from Core Audio (through
catap): the defaults and every output and mic, by UID and name ("AirPods
Pro") - for Home's and Settings' choice of them (polyglotic-hq 372, 411).

A device's id is its Core Audio UID, which stays the same across restarts
and replugging, as Windows' device ids do. The mic is opened through
PortAudio (sounddevice), which knows devices by name: `portaudio_index`
finds a UID's device there.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """A device plugged in now: its UID and name, whether it plays and
    records, and whether it's macOS' default output or input."""

    uid: str
    name: str
    outputs: bool
    inputs: bool
    default_output: bool = False
    default_input: bool = False


def listed(devices: Iterable[AudioDevice]) -> SoundDevices:
    """The speakers and mics among `devices`, by name, and the defaults."""
    found = sorted(devices, key=lambda d: d.name.lower())
    return SoundDevices(
        tuple(SoundDevice(d.uid, d.name) for d in found if d.outputs),
        tuple(SoundDevice(d.uid, d.name) for d in found if d.inputs),
        next((d.uid for d in found if d.outputs and d.default_output), None),
        next((d.uid for d in found if d.inputs and d.default_input), None),
    )


def portaudio_index(
    uid: str | None,
    devices: Sequence[AudioDevice],
    portaudio: Sequence[tuple[str, int]],
) -> int | None:
    """PortAudio's index of the mic with `uid` - by name, among its devices
    that record (`portaudio`: (name, input channels) in its order) - or None
    for PortAudio's default: no `uid`, or no one device of that name."""
    if uid is None:
        return None
    name = next((d.name for d in devices if d.uid == uid), None)
    matches = [
        i for i, (each, channels) in enumerate(portaudio) if each == name and channels
    ]
    return matches[0] if len(matches) == 1 else None


# -- Core Audio, through catap: only on a Mac --------------------------------


def audio_devices() -> list[AudioDevice]:
    """Every device plugged in now (catap's `list_audio_devices`); raises
    OSError if Core Audio can't say."""
    try:
        import catap  # macOS 14.2+ only: imported when first asked

        return [
            AudioDevice(
                str(d.uid),
                str(d.name),
                bool(d.output_streams),
                bool(d.input_streams),
                bool(d.is_default_output),
                bool(d.is_default_input),
            )
            for d in catap.list_audio_devices()
        ]
    except (ImportError, RuntimeError) as e:
        problem = type(e).__name__
        raise OSError(f"Couldn't reach the Mac's audio devices: {problem}") from None


def sound_devices() -> SoundDevices:
    """Every speaker and mic plugged in, by name, and macOS' defaults.
    Nothing, if Core Audio can't say."""
    try:
        return listed(audio_devices())
    except OSError:
        return SoundDevices()


def outputs_playing() -> int | None:
    """How many outputs play sound now: not read on macOS yet (None, as
    the port allows), so the caption log's mic-bleed line leaves it out.
    Core Audio's `kAudioDevicePropertyDeviceIsRunningSomewhere` would say."""
    return None
