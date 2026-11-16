"""Sound played aloud through Windows' own PlaySound (winmm): the sample
Home offers when nothing is playing (polyglotic-hq 176). From memory, on
the default device, without waiting; one sound at a time in the app."""

import ctypes
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # numpy and soundfile only once a sound plays
    from polyglotic_desktop.platform.speech_detection import Audio

SND_ASYNC = 0x0001
SND_NODEFAULT = 0x0002  # no "ding" if it can't play
SND_MEMORY = 0x0004

_winmm = ctypes.WinDLL("winmm", use_last_error=True)
_play_sound = _winmm.PlaySoundW
_play_sound.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
_play_sound.restype = ctypes.c_int


class PlayAloud:
    """Plays audio aloud; `stop` ends it. The sound's bytes are kept while
    it plays: PlaySound reads them as it goes."""

    def __init__(self) -> None:
        self._playing: ctypes.Array[ctypes.c_char] | None = None

    def play(self, audio: "Audio", rate: int) -> bool:
        """`audio` (mono float) at `rate`, from now. False if Windows can't
        play it (no output device): the sample is still captioned."""
        import soundfile as sf

        self.stop()
        wav = io.BytesIO()
        sf.write(wav, audio, rate, format="WAV", subtype="PCM_16")
        data = wav.getvalue()
        self._playing = ctypes.create_string_buffer(data, len(data))
        flags = SND_MEMORY | SND_ASYNC | SND_NODEFAULT
        return bool(_play_sound(ctypes.addressof(self._playing), None, flags))

    def stop(self) -> None:
        if self._playing is not None:
            _play_sound(None, None, 0)  # stops the sound PlaySound is playing
            self._playing = None
