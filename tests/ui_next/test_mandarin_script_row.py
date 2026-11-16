"""Settings > Speech's "Show Mandarin in", beside Spoken language
(polyglotic-hq 375): it starts as this PC reads Chinese, a choice is kept
as the setting, and it shows only where Mandarin can be heard - Detect,
or Mandarin named."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.main import languages_settings
from polyglotic_desktop.ui_next.panels import LanguagesPanel
from polyglotic_desktop.ui_next.views.panels import LanguagesView, SessionLanguages


def test_the_row_starts_as_this_pc_reads_and_keeps_a_choice(qapp: QApplication) -> None:
    view = LanguagesView(SessionLanguages(traditional_here=True))
    panel = LanguagesPanel(view)
    assert panel.mandarin_script.value() is True  # Taiwan's Windows: Traditional
    assert languages_settings(view.value)["mandarin_script"] is None  # not chosen
    panel.mandarin_script.choose(False)
    assert view.value.mandarin_script == "simplified" and not view.value.traditional
    assert languages_settings(view.value)["mandarin_script"] == "simplified"
    panel.deleteLater()


def test_the_row_shows_only_where_mandarin_can_be_heard(qapp: QApplication) -> None:
    view = LanguagesView(SessionLanguages())
    panel = LanguagesPanel(view)
    assert not panel.mandarin_row.isHidden()  # Detect
    panel.spoken.choose("ja")
    assert panel.mandarin_row.isHidden()
    panel.spoken.choose("zh")
    assert not panel.mandarin_row.isHidden()
    panel.deleteLater()
