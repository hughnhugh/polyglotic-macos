"""Home's sample in the script Mandarin is shown in (polyglotic-hq 400,
after 375): the sample (176) is a recording captioned like any app, so its
captions come through the session and are converted as every other
source's are. Settings' preview, which writes its own captions, follows
the choice in `ui_next.caption_preview`."""

import shiboken6
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import make_app

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.sources import SAMPLE
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import MandarinScript, QtListener

ZH = Language("zh")


def test_homes_sample_is_shown_in_the_script_chosen(qapp: QApplication) -> None:
    desktop = make_app()
    try:
        listener = QtListener(desktop, None)
        listener.mandarin = script = MandarinScript(lambda: None)
        script.traditional = True
        listener.caption_updated(
            CaptionUpdate(
                CaptionId("s1"),
                SAMPLE,
                CaptionKind.FINISHED,
                (Clause("我的头发", translations={Language("en"): "my hair"}),),
                ZH,
                (ZH,),
            )
        )
        qapp.processEvents()
        shown = desktop.feed.history.captions
        assert [c.clauses[0].original for c in shown] == ["我的頭髮"]
    finally:
        desktop.close()
        shiboken6.delete(desktop)
