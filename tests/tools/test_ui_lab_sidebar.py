"""The sidebar's acceptance states stay in the UI lab gate."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tools.ui_lab import checks, sidebar
from tools.ui_lab.lab import Lab


@pytest.fixture
def qapp() -> QApplication:
    """The tools tests do not inherit the UI test directory's Qt fixture."""
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def test_sidebar_states_cover_the_required_visual_variants() -> None:
    assert {state.name for state in sidebar.STATES} == {
        "ui_next.sidebar_dark",
        "ui_next.sidebar_light",
        "ui_next.sidebar_selected_home",
        "ui_next.sidebar_selected_words",
        "ui_next.sidebar_selected_learning",
        "ui_next.sidebar_selected_account",
        "ui_next.sidebar_selected_settings",
        "ui_next.sidebar_selected_help",
        "ui_next.sidebar_largest",
        "ui_next.sidebar_windows_200",
        "ui_next.sidebar_narrow",
    }
    assert all(state.gated for state in sidebar.STATES)


@pytest.mark.parametrize("light", [False, True])
def test_floor_home_has_no_clipped_visible_text(
    qapp: QApplication, tmp_path: Path, light: bool
) -> None:
    """838: the real floor wraps a source name instead of cutting its ink."""
    lab = Lab(qapp, tmp_path)
    window = sidebar._sidebar(lab, light=light)
    window.resize(*sidebar.minimum_size())
    lab.pump()

    findings = checks.inspect(
        "ui_next.sidebar_narrow", window, lambda shown: shown.grab().toImage()
    ).findings

    assert not [finding for finding in findings if finding.check == "clipped_text"]
    window.close()


@pytest.mark.parametrize("light", [False, True])
def test_settings_preview_visible_text_meets_the_floor(
    qapp: QApplication, tmp_path: Path, light: bool
) -> None:
    """838: Settings' real preview never paints type below the 12 px floor."""
    lab = Lab(qapp, tmp_path)
    window = sidebar._sidebar(lab, "settings", light=light)

    findings = checks.inspect(
        "ui_next.sidebar_selected_settings",
        window,
        lambda shown: shown.grab().toImage(),
    ).findings

    assert not [finding for finding in findings if finding.check == "small_text"]
    window.close()
