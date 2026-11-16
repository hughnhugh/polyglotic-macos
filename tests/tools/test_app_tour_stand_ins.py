"""The app tour's stand-ins take what the app hands its OS adapters
(polyglotic-hq 443: the Mac tour failed at the start when `main` began
handing the speaker its recordings, decision 0133)."""

import dataclasses
import inspect
from collections.abc import Callable
from typing import Any

import numpy as np

from polyglotic_desktop import main
from tools import app_tour


def _stand_ins() -> Any:
    real = dataclasses.make_dataclass(
        "Real", [(f.name, Any, None) for f in dataclasses.fields(main.OsAdapters)]
    )
    os_adapters: Callable[..., Any] = app_tour.adapters(
        lambda _system: real(), np.zeros(16, dtype=np.float32)
    )
    return os_adapters()


def test_the_tours_speaker_takes_the_recordings_main_hands_it() -> None:
    from polyglotic_desktop.platform.recorded_voices import Recordings

    speaker = _stand_ins().speaker
    inspect.signature(speaker).bind(Recordings())  # as main calls it
