"""The caption window as fresh captions arrive during mic and F8 holds."""

from functools import partial

from tests.ui.test_dictating import StandInMic

from polyglotic_desktop.core.listening.caption_hold import CaptionResults
from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM
from polyglotic_desktop.core.listening.type_theirs import shown_text
from polyglotic_desktop.ui.dictation import Dictating, HeldCaptions
from polyglotic_desktop.ui.recorded_captions import APP, ZH, clause, finished
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.dictation_sign import DictationSign
from tools.ui_lab.caption_window import window
from tools.ui_lab.lab import Lab, State

METER_LEVEL = 0.64
"""Fraction of the meter lit in the held, speaking fixture."""


def _during_hold(lab: Lab, speakers: bool) -> CaptionWindow:
    source = WHOLE_SYSTEM if speakers else APP
    shown = window(lab, captions=0, source=source, show_mic=not speakers)
    sign = DictationSign()
    sign.setParent(shown, sign.windowFlags())
    share = HeldCaptions(
        CaptionResults(source if speakers else MIC),
        lambda _end: None,
        lambda: None,
        lambda: METER_LEVEL,
        lambda lines: shown_text(lines, None),
    )
    recorder = StandInMic()
    typing = Dictating(
        Settings(None, parent=shown),
        recorder,
        lambda _request, _audio: None,
        lambda _text: True,
        lambda: 1,
        lambda _key: False,
        lambda _wanted: True,
        parent=shown,
        from_speakers=speakers,
        share_captions=lambda _start: share,
    )
    typing.sign_changed.connect(
        lambda state, level: sign.show_state(
            state, level, speakers=speakers, window=shown if speakers else None
        )
    )
    lab.closing.append(typing.stop)
    typing.key_down()
    assert sign.listening and recorder.hold == 0

    answers = [
        finished(
            "first-line",
            clause("下一站就是市中心。", "The next stop is the city centre."),
            source=source,
        ),
        finished(
            "last-line",
            clause(
                "请从左边的车门下车。", "Please exit through the doors on the left."
            ),
            source=source,
        ),
    ]
    if not speakers:
        answers.append(
            finished(
                "own-speech",
                clause("我在下一站下车。", "I’m getting off at the next stop."),
                source=MIC,
                language=ZH,
            )
        )
    for update in answers:
        typing.caption_received(update)
        shown.view.apply(update)
        typing.caption_applied(update)
    shown.apply_changed(new_caption=True)
    lab.pump()
    assert sign.grab().save(str(lab.out / f"{lab.result.state}.sign.png"))
    return shown


STATES = [
    State(
        "ui_next.w1_mic_dictation_hold",
        partial(_during_hold, speakers=False),
        gated=True,
        scene=True,
    ),
    State(
        "ui_next.w1_speaker_typing_hold",
        partial(_during_hold, speakers=True),
        gated=True,
        scene=True,
    ),
]
