"""The captions' faces the app carries, added to Qt's fonts once
(polyglotic-hq 482; decision 0223): by the first caption layout, before it
lays anything out - so no text is ever laid out in one face and drawn
after another came (479 saw boxes then).

They're in the `ui` package's assets beside the heading faces; adding all
of them takes about 7 ms (482's measure on Windows).
"""

from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from polyglotic_desktop.ui_next import fonts

FOLDER = Path(str(files("polyglotic_desktop.ui") / "assets" / "fonts"))

DOWNLOADED_SUFFIXES = (".ttf", ".otf")
downloaded: Path | None = None
"""Where the faces downloaded since are (`main`'s; polyglotic-hq 482's
font packs): added with the bundled ones (`load`)."""
generation = 0
"""One more each time a face is added: a caption layout made before lays
its rows out again (`CaptionLayout`), and readings are measured again -
text laid out before a face came and drawn after came out as boxes (479)."""

_loaded: dict[str, list[str]] = {}
"""Each file added: the families Qt found in it (none: it wasn't there)."""
_weights: dict[tuple[str, int], bool] = {}


def load(folder: Path = FOLDER) -> list[str]:
    """The bundled faces added to Qt's fonts, once each: the families now
    there. A file that's missing is passed over - its language's captions
    are in the OS's own face then. Needs the QGuiApplication."""
    paths = [folder / name for face in fonts.BUNDLED for name in face.files]
    if downloaded is not None and downloaded.is_dir():
        paths += sorted(
            path for path in downloaded.iterdir() if path.suffix in DOWNLOADED_SUFFIXES
        )
    add(paths)
    return sorted({family for families in _loaded.values() for family in families})


def add(paths: Iterable[Path]) -> list[str]:
    """Faces' files added to Qt's fonts, each once - a face downloaded now
    included: the families they hold. Any new one makes every caption
    layout lay its rows out again (`generation`)."""
    global generation
    found: list[str] = []
    for path in paths:
        key = str(path)
        if key not in _loaded:
            added = QFontDatabase.addApplicationFont(key)
            _loaded[key] = (
                QFontDatabase.applicationFontFamilies(added) if added >= 0 else []
            )
            if _loaded[key]:
                _weights.clear()
                generation += 1
        found += _loaded[key]
    return found


def has_weight(family: str, weight: int) -> bool:
    """Whether `family` has a face of its own at `weight` or heavier, so
    asking for that weight never has Qt make up a bold. Kept until a face
    is added."""
    key = (family, weight)
    found = _weights.get(key)
    if found is None:
        found = _weights[key] = any(
            QFontDatabase.weight(family, style) >= weight
            for style in QFontDatabase.styles(family)
        )
    return found
