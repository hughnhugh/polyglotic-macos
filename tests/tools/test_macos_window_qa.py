"""Independent expectations used to judge the hosted Mac's Quartz gestures."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from tools.macos_quartz import Evidence, Pointer, motion

from tools import macos_quartz


@pytest.mark.parametrize(
    ("side", "shift", "expected"),
    [
        ("right", (120, 0), (200, 100, 670, 168)),
        ("left", (-120, 0), (80, 100, 670, 168)),
        ("top", (0, -32), (200, 68, 550, 200)),
        ("bottom", (0, 32), (200, 100, 550, 200)),
        ("top-left", (-120, -32), (80, 68, 670, 200)),
        ("top-right", (120, -32), (200, 68, 670, 200)),
        ("bottom-left", (-120, 32), (80, 100, 670, 200)),
        ("bottom-right", (120, 32), (200, 100, 670, 200)),
        ("move", (35, 20), (235, 120, 550, 168)),
    ],
)
def test_frame_expected_for_each_handle(
    side: str, shift: tuple[int, int], expected: tuple[int, int, int, int]
) -> None:
    frame = QRect(200, 100, 550, 168)
    point, delta, target = motion(frame, side, False)
    assert frame.contains(point)
    assert delta == QPoint(*shift)
    assert target == QRect(*expected)


def test_desktop_recording_and_input_require_the_hosted_mac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(macos_quartz, "hosted_mac", lambda: False)
    with pytest.raises(RuntimeError, match="GitHub-hosted Mac"):
        Pointer()
    with pytest.raises(RuntimeError, match="GitHub-hosted Mac"):
        Evidence(tmp_path / "pictures")
    assert not (tmp_path / "pictures").exists()
