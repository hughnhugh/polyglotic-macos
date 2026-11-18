"""Listening time is counted by the category of the source a finished
caption came from (polyglotic-hq project 163): `Sources` knows each
source's category - an app's, the whole system's - never its name."""

from tests.ui.test_main_wiring import CHAT, ChangingAppList, FakePipeline, sources_with

from polyglotic_desktop.core.listening.sources import EVERYTHING_ELSE, MIC
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ui.settings import AppSettings


def test_each_captured_source_has_its_category() -> None:
    sources = sources_with(FakePipeline(), ChangingAppList(CHAT))
    sources.follow(
        AppSettings(whole_system=False, apps=("Chat App",), everything_else=True)
    )
    assert sources.category_of_source(sources.app_id("Chat App")) is SourceCategory.CALL
    assert sources.category_of_source(EVERYTHING_ELSE) is SourceCategory.SYSTEM
    assert sources.category_of_source(MIC) is SourceCategory.OTHER  # not captured
