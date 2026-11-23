"""The outputs and microphones plugged in now, from the sound server
(`pulse.py`; polyglotic-hq 372, 550): for Home's and Settings' choice of
them, and how many outputs play, for the caption log's mic-bleed line.

A device's id is the server's name for it (`alsa_output.pci-0000_00_1f.3.
analog-stereo`), which stays the same across restarts and replugging, as
Windows' device ids and Core Audio's UIDs do. An output's monitor is never
listed as a microphone. Each answer is one short connection of its own,
made on the asking thread; nothing at all if there's no sound server.
"""

from collections.abc import Callable

from polyglotic_desktop.platform.linux import pulse
from polyglotic_desktop.platform.linux.capture import Server, connect
from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices


def listed(
    outputs: list[pulse.Device], inputs: list[pulse.Device], defaults: pulse.Defaults
) -> SoundDevices:
    """The speakers and mics, by description, and the defaults - a default
    input that is an output's monitor isn't a microphone (547)."""
    mics = [source for source in inputs if source.monitor_of is None]
    mic_names = {source.name for source in mics}
    speaker_names = {sink.name for sink in outputs}
    return SoundDevices(
        tuple(
            SoundDevice(d.name, d.description)
            for d in sorted(outputs, key=lambda d: d.description.lower())
        ),
        tuple(
            SoundDevice(d.name, d.description)
            for d in sorted(mics, key=lambda d: d.description.lower())
        ),
        defaults.output if defaults.output in speaker_names else None,
        defaults.input if defaults.input in mic_names else None,
    )


def _asked(server: Callable[[], Server] = connect) -> Server | None:
    try:
        return server()
    except OSError:
        return None


def sound_devices(server: Callable[[], Server] = connect) -> SoundDevices:
    """Every speaker and mic plugged in, and the server's defaults; nothing
    if the sound server can't say."""
    found = _asked(server)
    if found is None:
        return SoundDevices()
    try:
        return listed(found.sinks(), found.sources(), found.server_info())
    except OSError:
        return SoundDevices()
    finally:
        found.close()


def outputs_playing(server: Callable[[], Server] = connect) -> int | None:
    """How many outputs are playing now (the server's own state for each);
    None if it can't say."""
    found = _asked(server)
    if found is None:
        return None
    try:
        return sum(1 for sink in found.sinks() if sink.running)
    except OSError:
        return None
    finally:
        found.close()
