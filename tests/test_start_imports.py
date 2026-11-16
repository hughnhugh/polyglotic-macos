"""What `import polyglotic_desktop.main` brings in: not the libraries the
window doesn't need (polyglotic-hq project 136; 108's fix f). They took
about 0.3 s of the 0.55 s of imports from source, before the window."""

import subprocess
import sys

NOT_BEFORE_THE_WINDOW = (
    "numpy",
    "onnxruntime",
    "pydantic",
    "websockets",
    "nacl",
    "genanki",
    "urllib.request",
    "polyglotic_desktop.connection.protocol",
    "polyglotic_desktop.platform.speech_pipeline",
    # Mandarin in Traditional (375): read when a caption first needs it;
    # Thai's split: when a Thai pack opens (400)
    "polyglotic_desktop.adapters.traditional_table",
    "polyglotic_desktop.core.lexicon.traditional",
    "polyglotic_desktop.core.lexicon.thai",
)
"""Imported after the window's first paint (or never, from source)."""

LISTED = f"""
import sys
import polyglotic_desktop.main
print(" ".join(m for m in {NOT_BEFORE_THE_WINDOW!r} if m in sys.modules))
"""


def test_importing_main_leaves_the_connection_and_speech_libraries_for_later() -> None:
    done = subprocess.run(
        [sys.executable, "-c", LISTED],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    assert done.stdout.split() == [], f"imported with main: {done.stdout.strip()}"
