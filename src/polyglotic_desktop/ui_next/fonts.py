"""The fonts each OS has for the interface, after Windows' in every font
list (polyglotic-hq 179).

The lists name Windows' fonts first - Segoe UI, Microsoft YaHei and
JhengHei, Yu Gothic - as the app always has. On macOS and Linux none of
those exist, and Qt fell back to whatever it found (DejaVu, in 171's
Linux probe), so each list ends with that OS's own (`also`). On Windows
`also` adds nothing: the lists, and so the interface, are as they were.
"""

import sys

OTHER_OS: dict[str, dict[str, tuple[str, ...]]] = {
    "darwin": {
        "latin": ("Helvetica Neue",),
        "zh": ("PingFang SC",),
        "zh-hant": ("PingFang TC",),
        "yue": ("PingFang HK",),
        "ja": ("Hiragino Sans",),
    },
    "linux": {
        "latin": ("Noto Sans", "Cantarell", "DejaVu Sans"),
        "zh": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"),
        "zh-hant": ("Noto Sans CJK TC", "Source Han Sans TC"),
        "yue": ("Noto Sans CJK HK", "Source Han Sans HC"),
        "ja": ("Noto Sans CJK JP", "Source Han Sans"),
    },
}
"""Each OS's families by script: Latin text, Simplified Chinese ("zh"),
Traditional ("zh-hant"), Hong Kong's ("yue") and Japanese ("ja")."""


def also(script: str, system: str = sys.platform) -> tuple[str, ...]:
    """This OS's fonts for `script`, to follow Windows' in a font list -
    none on Windows."""
    return OTHER_OS.get(system, {}).get(script, ())
