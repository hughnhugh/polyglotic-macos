"""Colours as a colour-blind learner sees them (polyglotic-hq 489): the
Machado, Oliveira and Fernandes (2009) simulation of protanopia and
deuteranopia at full severity - each a 3x3 matrix applied in linear sRGB
- and greyscale (relative luminance). For the tests of Learning load's
colours and the UI lab's pictures of them.

The matrices are the paper's Table (severity 1.0), as published with it:
https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html
"""

from enum import StrEnum

from PySide6.QtGui import QColor, QImage


class Sight(StrEnum):
    PROTANOPIA = "protanopia"
    DEUTERANOPIA = "deuteranopia"
    GREYSCALE = "greyscale"


MATRICES = {
    Sight.PROTANOPIA: (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    Sight.DEUTERANOPIA: (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
}


def _linear(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _encoded(value: float) -> int:
    c = max(0.0, min(1.0, value))
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return round(c * 255)


_LINEAR = [_linear(v) for v in range(256)]


def seen(colour: str, sight: Sight) -> str:
    """`colour` ("#rrggbb") as seen with `sight`."""
    digits = colour.lstrip("#")
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    out = _seen_rgb(r, g, b, sight)
    return "#" + "".join(f"{c:02x}" for c in out)


def _seen_rgb(r: int, g: int, b: int, sight: Sight) -> tuple[int, int, int]:
    rgb = (_LINEAR[r], _LINEAR[g], _LINEAR[b])
    if sight is Sight.GREYSCALE:
        y = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        grey = _encoded(y)
        return grey, grey, grey
    m = MATRICES[sight]
    out = (sum(m[i][j] * rgb[j] for j in range(3)) for i in range(3))
    red, green, blue = (_encoded(v) for v in out)
    return red, green, blue


def seen_image(image: QImage, sight: Sight) -> QImage:
    """A copy of `image` as seen with `sight` (each colour once: a
    picture of captions has few)."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32)
    cache: dict[int, int] = {}
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            found = cache.get(pixel)
            if found is None:
                c = QColor.fromRgba(pixel)
                r, g, b = _seen_rgb(c.red(), c.green(), c.blue(), sight)
                found = cache[pixel] = QColor(r, g, b, c.alpha()).rgba()
            out.setPixel(x, y, found)
    return out
