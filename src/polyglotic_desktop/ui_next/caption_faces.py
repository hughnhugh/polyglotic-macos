"""The captions' faces the app carries, added to Qt's fonts once
(polyglotic-hq 482; decision 0223): by the first caption layout, before it
lays anything out - so no text is ever laid out in one face and drawn
after another came (479 saw boxes then).

They're in the `ui` package's assets beside the heading faces; adding all
of them takes about 7 ms (482's measure on Windows).
"""

import logging
import sys
from collections.abc import Callable, Collection, Iterable
from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from polyglotic_desktop.ui_next import fonts

log = logging.getLogger(__name__)
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
_cjk_checked = False


def log_missing_cjk_fonts(
    installed: Collection[str] | None = None, system: str = sys.platform
) -> dict[str, tuple[str, ...]]:
    """Log missing system CJK font families once per process (polyglotic-hq
    647). Minimal Linux installs (or WSL) without `fonts-noto-cjk` show boxes
    for Japanese and Traditional Chinese; Ubuntu and Fedora desktops ship CJK
    fonts already, so nothing is logged there."""
    global _cjk_checked
    if _cjk_checked:
        return {}
    _cjk_checked = True
    families = QFontDatabase.families() if installed is None else installed
    missing = fonts.missing_cjk_families(families, system)
    if missing:
        wanted = list(
            dict.fromkeys(
                family for expected in missing.values() for family in expected
            )
        )
        hint = (
            " (install fonts-noto-cjk on Debian/Ubuntu or "
            "google-noto-sans-cjk-vf-fonts on Fedora)"
            if system.startswith("linux")
            else ""
        )
        log.warning(
            "missing system CJK font families for %s; looked for: %s%s",
            ", ".join(missing),
            ", ".join(wanted),
            hint,
        )
    return missing


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
    log_missing_cjk_fonts()
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


def weights(family: str) -> list[int]:
    """The weights of `family`'s faces in Qt's font database: the PC's own
    and the app's alike, under that name."""
    found = (QFontDatabase.weight(family, s) for s in QFontDatabase.styles(family))
    return [weight for weight in found if weight > 0]


def lightest(
    families: Iterable[str],
    medium: int = 500,
    weights_of: Callable[[str], list[int]] | None = None,
) -> int:
    """The lightest weight of their own `families` have below the one
    `medium` draws in each (Qt takes a family's nearest weight) - `medium`
    if none has a lighter face (polyglotic-hq 532: Look's Thickness offers
    no step that draws what Medium does). A family not on this PC adds
    nothing, and nor does one of the app's own (`fonts.FACES`): each is cut
    at one weight, on every OS - even where the OS has a face of its own
    under the same name, as a Linux PC's Noto Sans Devanagari Regular
    beside the app's Medium (532's Linux CI offered Regular for it, to a
    learner of any language). `weights_of`: the weights' source - this
    module's `weights`, Qt's font database."""
    found = medium
    for family in families:
        if family in fonts.FACES:
            continue
        have = (weights_of or weights)(family)
        if not have:
            continue
        drawn = min(have, key=lambda w: (abs(w - medium), w))
        lighter = [w for w in have if w < drawn]
        if lighter:
            found = min(found, min(lighter))
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
