"""The app's own sound on Linux, through the sound server (polyglotic-hq
546's slice 5, 591; `pulse.Playback`): libpulse, as capture uses it, on the
default output as it is when each sound starts.

- `PulseOutput` - the speaker's `speaking.Output`, a recorded word's clip;
- `PlayAloud` - `sample.SoundOut`: Home's sample played aloud while it's
  captioned (polyglotic-hq 176).

Each sound is a connection, a stream and a thread of its own, closed when
it ends: nothing held between words. The thread runs the connection's
loop, so the server's asks for more sound are answered at once - asked
only as often as the speaker looks (every 20 ms), PipeWire's pulse server
(a 0.25 s buffer) ran dry between asks and a 0.8 s word played over 2.3 s
with gaps (591's probe, GitHub's Ubuntu 24.04 runner). Never logs what is
played.
"""

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from polyglotic_desktop.platform.linux.pulse import PulseServer
from polyglotic_desktop.platform.speaking import Clip

if TYPE_CHECKING:  # numpy only once a sample plays
    from polyglotic_desktop.platform.speech_detection import Audio

log = logging.getLogger(__name__)

STARTED_SEC = 3.0
"""A sound waits this long at most to hear the sound server started it
(about 20 ms on GitHub's Ubuntu runner)."""
RUN_SEC = 0.02
"""The connection's loop runs this long between looks for a stop."""


class PulseOutput:
    """`speaking.Output`: one clip on the default output, on a thread of its
    own that makes the connection, plays the clip to its end (the server
    says so: `Playback.done`) or until stopped, and closes it."""

    def __init__(self, server: Callable[[], PulseServer] = PulseServer) -> None:
        self._connect = server
        self._thread: threading.Thread | None = None
        self._over = threading.Event()
        self._stopping = threading.Event()

    def start(self, clip: Clip) -> bool:
        """Returns once the server has started it; False if it couldn't (no
        sound server, no output)."""
        started = threading.Event()
        playing: list[bool] = []

        def run() -> None:
            try:
                server = self._connect()
            except OSError as error:
                log.warning("couldn't play a sound: %s", error)
                started.set()
                self._over.set()
                return
            try:
                playback = server.play(clip.pcm, clip.rate, clip.channels)
                playing.append(True)
                started.set()
                while not (playback.done or playback.failed or self._stopping.is_set()):
                    server.run(RUN_SEC)
                playback.close()
            except OSError as error:
                log.warning("couldn't play a sound: %s", error)
            finally:
                server.close()
                started.set()
                self._over.set()

        self._thread = threading.Thread(target=run, name="sound-out", daemon=True)
        self._thread.start()
        started.wait(STARTED_SEC)
        return bool(playing)

    def playing(self) -> bool:
        return self._thread is not None and not self._over.is_set()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(STARTED_SEC)


def pcm16(audio: "Audio") -> bytes:
    """Mono float audio (-1 to 1) as 16-bit little-endian PCM, clipped."""
    import numpy as np

    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


class PlayAloud:
    """`SoundOut`: Home's sample on the default output; `stop` ends it.
    `play` returns once the sound server has started it - False if it
    couldn't (no sound server, no output): the sample is still captioned."""

    def __init__(self, output: Callable[[], PulseOutput] = PulseOutput) -> None:
        self._new_output = output
        self._playing: PulseOutput | None = None

    def play(self, audio: "Audio", rate: int) -> bool:
        self.stop()
        output = self._new_output()
        started = output.start(Clip(pcm16(audio), rate))
        self._playing = output
        return started

    def stop(self) -> None:
        if self._playing is not None:
            self._playing.stop()
            self._playing = None
