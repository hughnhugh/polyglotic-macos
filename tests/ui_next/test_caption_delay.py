"""Each caption's delay shown on request (polyglotic-hq 271): the words,
the tray's switch, the setting and the look the caption windows follow."""

import re

from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.core.listening.delays import CaptionDelay
from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_delay import delay_text


def test_the_delay_says_from_the_start_from_the_end_and_the_servers_share(
    qapp: QApplication,
) -> None:
    said = delay_text(CaptionDelay(from_start=3.64, from_end=1.26, server=0.412))
    assert said == "3.6 s from start · 1.3 s from end · server 0.41 s"
    assert delay_text(CaptionDelay(3.64, 1.26, None)) == (
        "3.6 s from start · 1.3 s from end"
    )


def test_it_is_off_until_the_learner_turns_it_on_in_the_tray(
    qapp: QApplication,
) -> None:
    assert AppSettings().show_delay is False
    assert caption_look(AppSettings()).show_delay is False
    store = MemorySettingsStore({"targets": ["en"]})
    app = make_app(store)
    assert not app.show_delay.isChecked()
    app.show_delay.setChecked(True)
    assert store.values["show_delay"] is True
    assert caption_look(app.settings.value).show_delay is True
    app.settings.update(show_delay=False)  # changed elsewhere: the switch follows
    assert not app.show_delay.isChecked()
    app.close()


def test_a_caption_window_shows_it_above_the_caption_when_its_look_says_so(
    qapp: QApplication,
) -> None:
    import dataclasses
    import time

    from tests.ui_next.made_up import finished_updates
    from tests.ui_next.test_caption_window import window_of

    from polyglotic_desktop.core.listening.captions import SpeechTimes
    from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

    now = time.perf_counter()
    timed = dataclasses.replace(
        finished_updates(3)[2],
        times=SpeechTimes(now - 4.0, now - 1.0, now - 0.6, now - 0.1),
        processing_ms=400,
    )
    window = window_of(qapp, captions=2)
    try:
        window.receive(timed)
        assert "from start" not in window.view.lines[-1].label  # off by default
        window.set_look(CaptionLook(show_delay=True))
        label = window.view.lines[-1].label
        said = r"4\.\d s from start · 1\.\d s from end · server 0\.40 s$"
        assert re.search(said, label)
        assert "from start" not in window.view.lines[0].label  # no times: no delay
    finally:
        window.close()
        window.deleteLater()
