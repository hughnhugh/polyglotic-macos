# PyInstaller's recipe for the app testers install: one folder, no console.
# Run through `python -m tools.package.build` (decision 0016), which sets
# POLYGLOTIC_STAMP (the release stamp, decision 0015) and checks the result.
#
# What goes in: the app's code (from src/, so never tests/), the
# speech-detection model, the release stamp, and what PyInstaller's hooks
# find the code imports - Python, Qt (Core, Gui, Widgets), ONNX Runtime,
# numpy, libsndfile, pydantic, websockets. What's left out, and why, is in
# EXCLUDES and DROP below. The dictionaries, notices and licences are put
# beside Polyglotic.exe by the build afterwards, as separate files.
#
# On macOS (polyglotic-hq 410) the folder becomes an app bundle,
# Polyglotic.app, for Apple silicon (onnxruntime has no Intel-Mac wheel),
# with its Info.plist from the build (POLYGLOTIC_INFO_PLIST: the permission
# prompts' wording, the identifier) and Qt's cocoa platform plugin; the
# build's own files go in its Contents/Resources (build.py's Layout).

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parents[1]  # noqa: F821 - SPECPATH is PyInstaller's
SRC = ROOT / "src"
APP = SRC / "polyglotic_desktop"
STAMP = Path(os.environ["POLYGLOTIC_STAMP"])
VERSION_FILE = os.environ.get("POLYGLOTIC_VERSION_FILE")  # Windows'
ICON = os.environ.get("POLYGLOTIC_ICON")  # .ico on Windows, .icns on macOS
INFO_PLIST = os.environ.get("POLYGLOTIC_INFO_PLIST")  # macOS's, as JSON
MACOS = sys.platform == "darwin"
# the interface languages Qt has its own words for (build.py's QT_LANGUAGES)
QT_LANGUAGES = os.environ.get("POLYGLOTIC_QT_LANGUAGES", "zh_CN zh_TW").split()

# Modules nothing in the app uses, which PyInstaller would otherwise follow
# from libraries' optional imports.
EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "lib2to3",
    "pytest",
    # onnxruntime's tools for building and converting models
    "onnxruntime.tools",
    "onnxruntime.transformers",
    "onnxruntime.quantization",
    "sympy",
    "mpmath",
    # numpy's testing and build helpers
    "numpy.testing",
    "numpy.f2py",
    "numpy.distutils",
    # pydantic's mypy plugin, and what it would pull in from a dev
    # environment (the release builds without the dev tools anyway; tomli
    # can't be excluded - setuptools' hook aliases its vendored copy)
    "pydantic.mypy",
    "mypy",
    # not "yaml": genanki (the Anki deck file, decision 0028) imports it at
    # start-up, so the packed app needs it (project 098 found the crash)
    # not PySide6.QtNetwork: a second start reaches the copy that runs on
    # Qt's local socket (polyglotic-hq 310, decision 0101)
]

# Files the hooks collect that the app never loads (project 005's trimmed
# build, measured 2026-11-04): Qt's software OpenGL renderer, Qt's own
# translations (the app's interface text has its own) - but for its
# standard buttons and menus in each interface language offered (decision
# 0034) - and plugins for networking, TLS and image formats the app
# doesn't use. Matched against the path inside the bundle: Qt's files are
# under PySide6/ on Windows and PySide6/Qt/ on macOS, whose windowing
# plugin is cocoa (libqcocoa) and whose widget style (styles/) stays.
DROP = [
    r"(^|[\\/])opengl32sw\.dll$",
    r"PySide6[\\/](Qt[\\/])?translations[\\/](?!qtbase_("
    + "|".join(re.escape(q) for q in QT_LANGUAGES)
    + r")\.qm$)",
    r"PySide6[\\/](Qt[\\/])?plugins[\\/](tls|networkinformation|generic"
    r"|imageformats|iconengines|platforminputcontexts|platformthemes)[\\/]",
    r"PySide6[\\/](Qt[\\/])?plugins[\\/]platforms[\\/]"
    r"(?!qwindows|qoffscreen|libqcocoa|libqoffscreen)",
    # (not Qt6Svg: the icons are drawn from their SVG masters, ui.icons)
    r"PySide6[\\/]Qt6(Pdf|Qml|Quick|OpenGL|VirtualKeyboard)\w*\.dll$",
    # sounddevice's wheel for macOS carries PortAudio for Windows too, which
    # its hook collects beside the Mac's libportaudio.dylib (polyglotic-hq 412)
    r"_sounddevice_data[\\/]portaudio-binaries[\\/][^\\/]+\.dll$",
]

# Mac capture's native libraries (polyglotic-hq 411, 412): catap loads its
# Core Audio library from beside its own code (catap/native/), which no
# hook collects; sounddevice's hook collects PortAudio's
# (_sounddevice_data/portaudio-binaries/libportaudio.dylib). build.py's
# MACOS layout checks both are in the bundle.
NATIVE = []
if MACOS:
    from PyInstaller.utils.hooks import collect_dynamic_libs

    NATIVE = collect_dynamic_libs("catap")


def keep(entry) -> bool:
    return not any(re.search(pattern, entry[0]) for pattern in DROP)


a = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "package" / "entry.py")],
    pathex=[str(SRC)],
    binaries=NATIVE,
    datas=[
        (str(APP / "platform" / "data" / "silero_vad_16k_op15.onnx"),
         "polyglotic_desktop/platform/data"),
        # Home's samples, FLEURS (CC BY 4.0), with their credits (176)
        (str(APP / "platform" / "data" / "samples"),
         "polyglotic_desktop/platform/data/samples"),
        # Mandarin in Traditional: OpenCC's table (Apache-2.0) and its
        # licence (polyglotic-hq 375)
        (str(APP / "adapters" / "data"), "polyglotic_desktop/adapters/data"),
        (str(STAMP), "polyglotic_desktop"),
        # the icons' SVG masters, and the themes' heading faces with their
        # OFL texts (project 098)
        (str(APP / "ui" / "assets"), "polyglotic_desktop/ui/assets"),
    ],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if keep(entry)]
a.datas = [entry for entry in a.datas if keep(entry)]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Polyglotic",
    console=False,  # a windowed app: logs go to a file (main.start_logging)
    upx=False,  # packers make antivirus false alarms likelier (project 005)
    version=VERSION_FILE,  # Windows' file properties: name and version
    # the app's own icon, from its SVG masters (ui.icons); macOS's is the bundle's
    icon=None if MACOS else ICON,
    target_arch="arm64" if MACOS else None,  # Apple silicon only
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="Polyglotic",
)

if MACOS:
    INFO = json.loads(Path(INFO_PLIST).read_text(encoding="utf-8"))  # build.info_plist
    app = BUNDLE(  # noqa: F821
        coll,
        name="Polyglotic.app",
        icon=ICON,
        bundle_identifier=INFO["CFBundleIdentifier"],
        version=INFO["CFBundleShortVersionString"],
        info_plist=INFO,
    )
