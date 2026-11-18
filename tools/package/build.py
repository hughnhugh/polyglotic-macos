"""Build the app testers install: PyInstaller, one folder (decision 0016).

    uv sync --locked --group package
    uv run --no-sync python -m tools.dictionaries.build      # once: the dictionaries
    uv run --no-sync python -m tools.package.build v0.1.0    # -> dist/Polyglotic/

From the locked environment, in order:
1. the release stamp from the tag (`stamp.py`, decision 0015), and Windows'
   file properties and an icon for `Polyglotic.exe`;
2. PyInstaller with `polyglotic.spec`: the app's code from `src/` (never
   `tests/`), the speech-detection model, the icon masters, heading
   faces and the interface's translations, compiled first (`ui/assets`;
   `tools.i18n`, decision 0034), the stamp, and the libraries the code imports,
   trimmed of what it never loads;
3. beside `Polyglotic.exe`, as separate, unlocked files: the dictionaries
   and their `CREDITS.md` (decision 0009), `THIRD_PARTY_NOTICES.md`,
   `RELEASE-NOTES.md` (what's new after an update, polyglotic-hq 345) and
   `licenses/` - every bundled package's licence files, Python's and the
   heading faces' OFL texts;
4. checks: no tests, `.env` files or device tokens anywhere in the folder
   or its code archive; the parts the app needs are there;
5. `--check-install` run on the packed app (it opens no window, captures
   nothing, connects nowhere), timed: its whole run (`wall_seconds`), the
   main window's first paint from the process's launch (`launch_seconds`,
   Python's start and the imports included - over
   `perf.budgets.START_PACKED` is a problem) and from the check's start
   (`window_seconds`);
6. a summary: size on disk, files, a zip's size (the download), start
   time - printed, and written to `build/package/summary.json`.

Velopack packs the folder afterwards (the release workflow).

On macOS (decision 0186; the macOS job, .github/workflows/macos.yml) the
same steps make `dist/Polyglotic.app`, an app bundle for Apple silicon: its
icon an .icns and its Info.plist from `info_plist` (the permission prompts'
wording); the build's files (3.) in `Contents/Resources` (`Layout`); signed
ad hoc once they're in (`sign`), or with the certificate
POLYGLOTIC_CODESIGN_IDENTITY names (the release's self-signed one: decision
0196); zipped by `ditto` for its size (`MACOS_ZIP`). Velopack packs it
afterwards, as on Windows (`pack.sh`; polyglotic-hq 430, decision 0202):
the zip a tester downloads is Velopack's portable one, which can update
itself.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.requirements import Requirement

from tools.i18n import __main__ as i18n
from tools.package import stamp

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

REPO = Path(__file__).resolve().parents[2]
SPEC = Path(__file__).with_name("polyglotic.spec")
WORK = REPO / "build" / "package"
NAME = "Polyglotic"
DICTIONARY_FILES = (
    "cedict.sqlite",
    "ecdict.sqlite",
    "ecdict-en.sqlite",  # English in English (decision 0211)
    "CREDITS.md",
)
ASSETS = REPO / "src" / "polyglotic_desktop" / "ui" / "assets"


@dataclass(frozen=True)
class Layout:
    """Where the packed app's parts are, on the OS it's packed on: one
    folder on Windows; an app bundle on macOS (polyglotic-hq 410), where
    PyInstaller keeps its code in `Contents/Frameworks` and the build's own
    files go in `Contents/Resources` (`main.beside_the_app`), which the
    bundle's signature seals - `Contents/MacOS` is for code alone."""

    folder: str
    """The packed app, inside `--out`."""
    executable: str
    """The program inside `folder`."""
    code: str
    """PyInstaller's own folder inside `folder` (`sys._MEIPASS`)."""
    beside: str
    """Where the build puts the dictionaries, notices, release notes and
    licences, inside `folder` ("" for beside the executable)."""
    qt: str
    """PySide6's Qt folder inside `code`: its plugins and translations."""
    parts: tuple[str, ...]
    """The OS's own parts the app can't start without, inside `code`: Qt's
    windowing plugin, Qt's SVG (the icons are drawn from SVG masters),
    libsndfile and, on macOS, capture's native libraries."""


WINDOWS = Layout(
    folder=NAME,
    executable=f"{NAME}.exe",
    code="_internal",
    beside="",
    qt="PySide6",
    parts=(
        "PySide6/plugins/platforms/qwindows.dll",
        "PySide6/Qt6Svg.dll",
        "_soundfile_data/libsndfile_x64.dll",
    ),
)
MACOS = Layout(
    folder=f"{NAME}.app",
    executable=f"Contents/MacOS/{NAME}",
    code="Contents/Frameworks",
    beside="Contents/Resources",
    qt="PySide6/Qt",
    parts=(
        "PySide6/Qt/plugins/platforms/libqcocoa.dylib",
        "PySide6/Qt/lib/QtSvg.framework",
        "_soundfile_data/libsndfile_arm64.dylib",
        # capture (polyglotic-hq 411, 412): catap's Core Audio taps and
        # PortAudio's mic, each loaded from beside its package's code
        "catap/native/libcatap_coreaudio.dylib",
        "_sounddevice_data/portaudio-binaries/libportaudio.dylib",
    ),
)
LAYOUT = MACOS if sys.platform == "darwin" else WINDOWS
"""This OS's (the app is packed on Windows and macOS only)."""
QT_TRANSLATIONS = i18n.LRELEASE.parent / (
    "translations" if sys.platform == "win32" else "Qt/translations"
)
QT_LANGUAGES = tuple(
    language
    for language in i18n.LANGUAGES
    if (QT_TRANSLATIONS / f"qtbase_{language}.qm").exists() and language != "en"
)
"""The interface languages Qt has its own words for (OK, Cancel, Copy -
not Thai, Vietnamese, Indonesian, Malay, Hindi or Filipino): their
`qtbase_<language>.qm` is kept in the packed app (decision 0034; the spec's
DROP, told by POLYGLOTIC_QT_LANGUAGES)."""


def needed(layout: Layout) -> tuple[str, ...]:
    """Inside the packed app: what it can't start without."""
    code = f"{layout.code}/"
    beside = f"{layout.beside}/" if layout.beside else ""
    return (
        layout.executable,
        f"{code}polyglotic_desktop/release.json",
        f"{code}polyglotic_desktop/platform/data/silero_vad_16k_op15.onnx",
        f"{code}polyglotic_desktop/platform/data/samples/zh.flac",
        f"{code}polyglotic_desktop/platform/data/samples/en.flac",
        f"{code}polyglotic_desktop/platform/data/samples/CREDITS.md",
        f"{code}polyglotic_desktop/adapters/data/zh_traditional.txt.gz",
        f"{code}polyglotic_desktop/adapters/data/OpenCC-LICENSE.txt",
        *(f"{code}{part}" for part in layout.parts),
        # Qt's own words (OK, Cancel, Copy) in each interface language (0034)
        *(f"{code}{layout.qt}/translations/qtbase_{q}.qm" for q in QT_LANGUAGES),
        *(
            f"{code}polyglotic_desktop/ui/assets/{p.relative_to(ASSETS).as_posix()}"
            for p in sorted(ASSETS.rglob("*"))
            if p.is_file() and p.suffix != ".qm"
        ),
        # the interface's translations, compiled by the build (not committed: 0034)
        *(
            f"{code}polyglotic_desktop/ui/assets/translations/{i18n.qm_path(language).name}"
            for language in i18n.LANGUAGES
        ),
        f"{beside}THIRD_PARTY_NOTICES.md",
        f"{beside}RELEASE-NOTES.md",  # what's new after an update (polyglotic-hq 345)
        *(f"{beside}dictionaries/{file}" for file in DICTIONARY_FILES),
    )


NEEDED = needed(WINDOWS)
"""Windows' (`needed(LAYOUT)` is what a build checks)."""
TOKEN = re.compile(rb"pgd_[A-Za-z0-9_-]{43}")  # a device token (protocol.md)
LICENSE_NAME = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
OUR_LICENCE_TEXTS = Path(__file__).with_name("licenses")
QT = ("LGPL-3.0.txt", "GPL-3.0.txt")
"""Qt and PySide6 are used under the LGPL-3.0, which comes with the GPL-3.0;
their wheels carry neither text, so we do (from gnu.org, 2026-11-05)."""
PORTAUDIO = "PortAudio-LICENSE.txt"
"""PortAudio's licence (v19.7.0's LICENSE.txt, from github.com/PortAudio/
portaudio, 2026-11-16): sounddevice's macOS wheel bundles the library
without it (polyglotic-hq 412)."""
IN_PACKAGE = {  # licence files kept in a package's folder, not its dist-info
    "onnxruntime": ("LICENSE", "ThirdPartyNotices.txt"),
    "_soundfile_data": ("COPYING",),  # libsndfile's LGPL-2.1
}


# -- 1. the stamp, file properties and icon ---------------------------------------


def version_info(version: str) -> str:
    """PyInstaller's version resource: Windows shows it in the file's
    properties."""
    numbers = tuple(int(n) for n in version.split(".")) + (0,)
    strings = {
        "FileDescription": NAME,
        "FileVersion": version,
        "InternalName": NAME,
        "OriginalFilename": f"{NAME}.exe",
        "ProductName": NAME,
        "ProductVersion": version,
    }
    table = ", ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    return (
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers},"
        " mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,"
        " date=(0, 0)),\n"
        f"  kids=[StringFileInfo([StringTable('040904B0', [{table}])]),\n"
        "        VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n"
        ")\n"
    )


def write_icon(path: Path) -> None:
    """The app's icon (`ui.icons`, from its SVG masters) as a Windows .ico
    at 16, 20, 24, 32, 48 and 256 pixels, for the exe and the installer
    (Velopack's `--icon`)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from polyglotic_desktop.ui.icons import ICO_SIZES, app_image

    _app = QGuiApplication.instance() or QGuiApplication([])
    path.write_bytes(ico([app_image(size) for size in ICO_SIZES]))


def ico(images: Sequence[QImage]) -> bytes:
    """Square images as one .ico file: 256 px as PNG, the rest as 32-bit
    bitmaps with their mask - what every Windows reader takes."""
    entries = [_ico_png(image) if image.width() >= 256 else _ico_bitmap(image)
               for image in images]  # fmt: skip
    data = struct.pack("<HHH", 0, 1, len(images))  # reserved, icon, count
    offset = len(data) + 16 * len(images)
    for image, entry in zip(images, entries, strict=True):
        side = image.width() % 256  # 0 means 256
        data += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(entry), offset)
        offset += len(entry)
    return data + b"".join(entries)


def _ico_png(image: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImageWriter

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not QImageWriter(buffer, b"png").write(image):
        raise RuntimeError("couldn't write the icon's PNG")
    return bytes(buffer.data().data())


ICNS_TYPES = {32: b"ic11", 64: b"ic12", 128: b"ic07", 256: b"ic08", 512: b"ic09",
              1024: b"ic10"}  # fmt: skip
"""Apple's icon types that hold a PNG, by its side in pixels (Finder and
the Dock take the size they need)."""


def write_icns(path: Path) -> None:
    """The app's icon (`ui.icons`, from its SVG masters) as a macOS .icns
    for the app bundle (polyglotic-hq 410)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from polyglotic_desktop.ui.icons import app_image

    _app = QGuiApplication.instance() or QGuiApplication([])
    path.write_bytes(icns({kind: _ico_png(app_image(side))
                           for side, kind in ICNS_TYPES.items()}))  # fmt: skip


def icns(pngs: dict[bytes, bytes]) -> bytes:
    """PNG images as one .icns file: `icns` and the file's length, then each
    image's type, its length (with these 8 bytes) and the PNG."""
    entries = b"".join(kind + struct.pack(">I", 8 + len(png)) + png
                       for kind, png in pngs.items())  # fmt: skip
    return b"icns" + struct.pack(">I", 8 + len(entries)) + entries


BUNDLE_ID = "io.polyglotic.desktop"
"""The macOS app's identifier (decision 0186): fixed once a tester has
given it a permission - macOS keeps the microphone's and the system
audio's answers under it."""
MACOS_MINIMUM = "14.2"
"""Core Audio's process taps, which capture one app or everything else,
came in macOS 14.2 (polyglotic-hq 408)."""
MIC_USE = (
    "Polyglotic listens to your microphone while a caption window shows your"
    " speech - your first one does until you turn it off - or while you hold"
    " the dictation key, to caption, translate or type what you say."
)
"""macOS's question's line saying why (polyglotic-hq 478: the first caption
window shows the learner's speech, and dictation is on, for a new
learner)."""
AUDIO_USE = (
    "Polyglotic listens to the apps you choose to caption, to show live"
    " captions and translations of what you hear."
)
"""macOS shows these in its permission prompts (a draft for the user to
approve: polyglotic-hq 410). Without them, macOS ends the app when it
touches the microphone or a tap."""


def info_plist(version: str) -> dict[str, object]:
    """The app bundle's Info.plist entries (PyInstaller adds the rest)."""
    return {
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": MACOS_MINIMUM,
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": MIC_USE,
        "NSAudioCaptureUsageDescription": AUDIO_USE,
        # an accessory from the start: no Dock icon, and the caption windows
        # allowed over full-screen apps (polyglotic-hq 429, decision 0201)
        "LSUIElement": True,
    }


def sign(app: Path) -> dict[str, object]:
    """The app bundle signed again once the build's files are in its
    Resources (PyInstaller signed it before): ad hoc (`-`) unless
    POLYGLOTIC_CODESIGN_IDENTITY names a certificate in the keychain. Then
    verified, with its designated requirement - what macOS keeps a
    permission under: an ad-hoc build's is its hash, so each new build asks
    again (polyglotic-hq 408, 410). With a certificate the requirement is
    its identifier and the certificate, the same for every build signed
    with it, so a learner's permissions carry over (decision 0196); its
    `authority` is the certificate's name, which an ad-hoc build hasn't."""
    identity = os.environ.get("POLYGLOTIC_CODESIGN_IDENTITY") or "-"
    command = ["codesign", "--force", "--deep", "--sign", identity]
    if identity != "-":
        # Apple's timestamp service is for its own certificates; a
        # self-signed one asks it in vain and the signing fails.
        command.append("--timestamp=none")
    signed = subprocess.run(
        [*command, str(app)], capture_output=True, text=True, check=False
    )
    verified = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    requirement = subprocess.run(
        ["codesign", "--display", "--requirements", "-", str(app)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    shown = subprocess.run(
        ["codesign", "--display", "--verbose=2", str(app)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return {
        "ad_hoc": identity == "-",
        "signed": signed.returncode == 0,
        "verified": verified.returncode == 0,
        "said": (signed.stderr + verified.stderr).strip()[-2000:],
        "designated_requirement": requirement.stdout.strip()[-500:],
        "authority": [
            line.partition("=")[2]
            for line in shown.stderr.splitlines()
            if line.startswith("Authority=")
        ],
    }


def signature_problems(signature: Mapping[str, object]) -> list[str]:
    """What's wrong with `sign`'s result. A failed signing is one even when
    the bundle still verifies: PyInstaller's ad-hoc signature is there
    underneath, so a certificate that didn't take would ship ad hoc unseen
    (polyglotic-hq 422)."""
    found = []
    if not signature["signed"]:
        found.append(f"codesign couldn't sign the app bundle: {signature['said']}")
    if not signature["verified"]:
        found.append(f"the app bundle's signature doesn't verify: {signature['said']}")
    if not signature["ad_hoc"] and not signature.get("authority"):
        found.append(
            "signed ad hoc although POLYGLOTIC_CODESIGN_IDENTITY names a certificate"
        )
    return found


def _ico_bitmap(image: QImage) -> bytes:
    """A 32-bit BGRA bitmap, bottom row first, at twice its height (the
    colours, then the 1-bit mask: set where the pixel is clear)."""
    from PySide6.QtGui import QImage

    image = image.convertToFormat(QImage.Format.Format_ARGB32)  # BGRA in memory
    side = image.width()
    pixels, line = bytes(image.constBits()), image.bytesPerLine()
    rows = [pixels[y * line : y * line + side * 4] for y in range(side)]
    mask_row = (side + 31) // 32 * 4
    mask = b""
    for row in rows:
        bits = bytearray(mask_row)
        for x in range(side):
            if row[x * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask = bytes(bits) + mask  # bottom row first, as the colours
    colours = b"".join(reversed(rows))
    header = struct.pack("<IiiHHIIiiII", 40, side, side * 2, 1, 32, 0,
                         len(colours) + len(mask), 0, 0, 0, 0)  # fmt: skip
    return header + colours + mask


# -- 3. notices and licences --------------------------------------------------------


def runtime_distributions(
    root: str = "polyglotic-desktop",
) -> list[metadata.Distribution]:
    """The app's runtime dependencies, all the way down, for this platform
    (no dev or package groups: those are never bundled)."""
    seen: dict[str, metadata.Distribution] = {}
    queue = [root]
    while queue:
        name = queue.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            continue
        dist = metadata.distribution(name)
        seen[key] = dist
        for line in dist.requires or []:
            requirement = Requirement(line)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                queue.append(requirement.name)
    seen.pop(re.sub(r"[-_.]+", "-", root).lower())
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def licence_files(dist: metadata.Distribution) -> Iterator[tuple[Path, Path]]:
    """Each licence file in the package's dist-info, with its path there
    (numpy keeps one per vendored library, several with the same name), and
    any software bill of materials (velopack lists the Rust crates it
    links)."""
    for file in dist.files or []:
        parts = file.parts
        in_dist_info = parts and parts[0].endswith(".dist-info")
        listed = "licenses" in parts or "sboms" in parts
        if in_dist_info and (LICENSE_NAME.search(file.name) or listed):
            yield Path(str(dist.locate_file(file))), Path(*parts[1:])


def top_level_names(dist: metadata.Distribution) -> set[str]:
    """The importable names a distribution installs (`numpy`,
    `_soundfile_data`, `typing_extensions`...)."""
    names = set()
    for file in dist.files or []:
        first = file.parts[0]
        if first.endswith((".dist-info", ".data")) or first in ("..", "__pycache__"):
            continue
        names.add(first.split(".")[0])
    return names


def is_bundled(
    dist: metadata.Distribution,
    folder: Path,
    modules: set[str],
    layout: Layout = WINDOWS,
) -> bool:
    """Whether PyInstaller put any of the distribution in the packed app:
    in its code archive, or as files in its own folder (`_internal`)."""
    internal = folder / layout.code
    return any(
        name in modules
        or (internal / name).exists()
        or any(internal.glob(f"{name}.*"))  # an extension: _cffi_backend.cp312-...pyd
        for name in top_level_names(dist)
    )


def copy_licences(folder: Path, layout: Layout = WINDOWS) -> list[dict[str, object]]:
    """Every bundled package's licence files, and Python's, under
    `licenses/`; returns what was copied, for the summary."""
    out = folder / layout.beside / "licenses"
    copied: list[dict[str, object]] = []
    modules = {m.split(".")[0] for m in archive_modules(folder / layout.executable)}
    for dist in runtime_distributions():
        if not is_bundled(dist, folder, modules, layout):
            continue  # a dependency the app's code never imports
        name, version = dist.metadata["Name"], dist.version
        target = out / f"{name}-{version}"
        files = list(licence_files(dist))
        for file, relative in files:
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target / relative)
        licence = dist.metadata.get("License-Expression") or dist.metadata.get(
            "License"
        )
        copied.append(
            {
                "name": name,
                "version": version,
                "licence": (licence or "").splitlines()[0][:80] if licence else None,
                "files": len(files),
            }
        )
    qt = out / "Qt-and-PySide6"
    qt.mkdir(parents=True, exist_ok=True)
    for text in QT:
        shutil.copy2(OUR_LICENCE_TEXTS / text, qt / text)
    # velopack's wheel names MIT but carries no text (its SBOM lists the
    # Rust crates it links); the installer's Setup.exe and Update.exe are
    # Velopack's too
    (out / "Velopack").mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUR_LICENCE_TEXTS / "Velopack-MIT.txt", out / "Velopack" / "LICENSE")
    # PortAudio, in sounddevice's wheel (a Mac's only): the wheel names its
    # licence but carries no text, so we do - v19.7.0's, the version the
    # wheel's library is built from (polyglotic-hq 412)
    if (folder / layout.code / "_sounddevice_data").is_dir():
        (out / "PortAudio").mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUR_LICENCE_TEXTS / PORTAUDIO, out / "PortAudio" / "LICENSE.txt")
        copied.append({"name": "PortAudio", "version": "19.7.0", "licence": "MIT",
                       "files": 1})  # fmt: skip
    for package, names in IN_PACKAGE.items():
        spec = importlib.util.find_spec(package)
        if spec is None or not spec.submodule_search_locations:
            continue
        where = Path(spec.submodule_search_locations[0])
        for name in names:
            if (where / name).is_file():
                (out / package).mkdir(parents=True, exist_ok=True)
                shutil.copy2(where / name, out / package / name)
    # the heading faces' SIL Open Font Licence texts (they ship beside the
    # fonts too, in _internal/polyglotic_desktop/ui/assets/fonts)
    (out / "Fonts").mkdir(parents=True, exist_ok=True)
    for ofl in sorted((ASSETS / "fonts").glob("*-OFL.txt")):
        shutil.copy2(ofl, out / "Fonts" / ofl.name)
    python = Path(sys.base_prefix) / "LICENSE.txt"
    if python.is_file():
        (out / "Python").mkdir(parents=True, exist_ok=True)
        shutil.copy2(python, out / "Python" / "LICENSE.txt")
    copied.append({"name": "Python", "version": sys.version.split()[0],
                   "licence": "PSF-2.0", "files": int(python.is_file())})  # fmt: skip
    return copied


# -- 4. checks ----------------------------------------------------------------------


def archive_modules(exe: Path) -> list[str]:
    """The module names in the packed app's code archive (PYZ): in the
    program itself, or beside it in a `.pkg` of its name, as PyInstaller
    may keep it in a macOS app bundle."""
    from PyInstaller.archive.readers import CArchiveReader

    try:
        archive = CArchiveReader(str(exe))
    except Exception:
        found = sorted(exe.parents[1].rglob(f"{exe.name}.pkg"))
        if not found:
            raise
        archive = CArchiveReader(str(found[0]))
    pyz = next(name for name, entry in archive.toc.items() if entry[-1] == "z")
    return sorted(archive.open_embedded_archive(pyz).toc)


def problems(folder: Path, layout: Layout = WINDOWS) -> list[str]:
    """What mustn't be in the packed app, or must be and isn't (a macOS
    framework is a folder)."""
    found = [
        f"missing: {need}" for need in needed(layout) if not (folder / need).exists()
    ]
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder).as_posix()
        if path.name.startswith(".env") or path.suffix == ".env":
            found.append(f"an environment file: {relative}")
        if TOKEN.search(path.read_bytes()):
            found.append(f"something shaped like a device token: {relative}")
    for module in archive_modules(folder / layout.executable):
        top = module.split(".")[0]
        if top in ("tests", "tools", "conftest") or (
            top == "polyglotic_desktop" and "test" in module
        ):
            found.append(f"a test or tool in the code: {module}")
    return found


# -- 5., 6. the self-check and the summary ------------------------------------------


def check_install(folder: Path, layout: Layout = WINDOWS) -> dict[str, object]:
    """`Polyglotic.exe --check-install`, timed from start to exit, with a
    data folder of its own, emptied first - never the account's own
    (`%APPDATA%\\Polyglotic`). The check opens the learning stores in its
    data folder, and the build runs on the user's PC as the user (the
    self-hosted runner, decision 0025): their own learning data is no
    build's business, and a build mustn't pass or fail by what's in it
    (polyglotic-hq 242)."""
    report = WORK / "check-install.json"
    report.unlink(missing_ok=True)
    data = WORK / "check-install-data"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    started = time.perf_counter()
    result = subprocess.run(
        [
            str(folder / layout.executable),
            "--check-install",
            str(report),
            "--data",
            str(data),
        ],
        timeout=120,
        check=False,
    )
    seconds = round(time.perf_counter() - started, 3)
    found = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    found.update(exit_code=result.returncode, wall_seconds=seconds)
    return found


FIRST_LAUNCH = ("exit_code", "launch_seconds", "window_seconds", "wall_seconds")
"""What is kept of a Mac's first launch (`settled_check_install`)."""


def settled_check_install(folder: Path, layout: Layout = WINDOWS) -> dict[str, object]:
    """`check_install`, judged on a start a learner has every day. On a Mac
    the first launch of a newly signed app carries macOS' own first look
    at it (Gatekeeper and its code-signature checks, once per build on each
    Mac: polyglotic-hq 419's run 1, 1.775 s), so that launch settles the app
    and is kept as `first_launch`, and the second is judged. On Windows,
    one launch, as before."""
    if layout is not MACOS:
        return check_install(folder, layout)
    first = check_install(folder, layout)
    check = check_install(folder, layout)
    check["first_launch"] = {k: first.get(k) for k in FIRST_LAUNCH}
    return check


def first_launch_failed(check: dict[str, object]) -> list[str]:
    """A Mac's settling launch must work too: only its time isn't judged."""
    first = check.get("first_launch")
    if isinstance(first, dict) and first.get("exit_code") != 0:
        return [f"the first launch failed: {first}"]
    return []


GITHUB_MAC_CEILING_MS = 2500.0
"""The packed start's limit on GitHub's own Mac runner only (decision 0193,
polyglotic-hq 420): there the settled launch took 1.051 s and 1.627 s on
the same code (419's runs 2 and 3), the VM's noise more than half the 1000
ms budget. The ceiling still catches a doubling; the budget itself
(`START_PACKED`, DECISIONS.md #53) is a person's Mac's to measure."""


def start_limit_ms(layout: Layout, environ: Mapping[str, str] = os.environ) -> float:
    """What the packed app's start is judged against: `START_PACKED`, or on
    GitHub's own Mac runner `GITHUB_MAC_CEILING_MS`. GitHub names its own
    runners `RUNNER_ENVIRONMENT=github-hosted`."""
    from polyglotic_desktop.perf.budgets import START_PACKED

    if layout is MACOS and environ.get("RUNNER_ENVIRONMENT") == "github-hosted":
        return GITHUB_MAC_CEILING_MS
    return START_PACKED.ms


def over_start_budget(
    check: dict[str, object], limit_ms: float | None = None
) -> list[str]:
    """The packed app's main window later than its budget (or not timed);
    `limit_ms` in its place on GitHub's Mac (`start_limit_ms`).

    Judged on `launch_seconds` - from the process's launch, Python's start
    and the imports included, which is the wait a person has (polyglotic-hq
    243; 136 added the field) - falling back to `window_seconds` (from the
    check's start) when a build couldn't read its process time."""
    from polyglotic_desktop.perf.budgets import START_PACKED

    limit = START_PACKED.ms if limit_ms is None else limit_ms
    seconds = check.get("launch_seconds")
    measured = "from launch"
    if not isinstance(seconds, int | float):
        seconds = check.get("window_seconds")
        measured = "from the check's start (launch time unread)"
    if not isinstance(seconds, int | float):
        return ["--check-install didn't time the main window"]
    if seconds > limit / 1000:
        return [f"the main window took {seconds} s {measured}, over {limit:.0f} ms"]
    return []


def packs_as_decided(check: dict[str, object]) -> list[str]:
    """A downloaded dictionary pack opens and is looked up in, in the packed
    app (`--check-install`'s `dictionary_pack`), without simplemma: decision
    0123 keeps it out (Russian loses 0.2 points of running words; its data
    would need its own licence reading). Problems, if not."""
    pack = check.get("dictionary_pack")
    if not isinstance(pack, dict):
        return ["--check-install didn't try a dictionary pack"]
    if pack.get("simplemma"):
        return ["simplemma is in the build: decision 0123 keeps it out"]
    return []


def zipped_size(folder: Path) -> int:
    """The folder as a zip (Velopack's packages are zips): about the
    download."""
    path = WORK / f"{NAME}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                z.write(file, file.relative_to(folder))
    size = path.stat().st_size
    path.unlink()
    return size


MACOS_ZIP = "Polyglotic-macos-arm64.zip"
"""The app bundle as a tester would download it, kept in the build's work
folder (the macOS job uploads it only when asked: polyglotic-hq 410)."""


def ditto_zip(app: Path) -> int:
    """The app bundle zipped by macOS's own `ditto`, which keeps its
    symbolic links and signature (Python's zipfile keeps neither); its
    size."""
    path = WORK / MACOS_ZIP
    path.unlink(missing_ok=True)
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    str(app), str(path)], check=True)  # fmt: skip
    return path.stat().st_size


def biggest(folder: Path, n: int = 12) -> list[tuple[str, float]]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    return [(p.relative_to(folder).as_posix(), mb(p.stat().st_size)) for p in files[:n]]


def mb(size: int) -> float:
    return round(size / 1_000_000, 1)


# -- the build ----------------------------------------------------------------------


IN_THE_INSTALLER = "packs"
"""Where `--packs` puts dictionary packs in the app's folder, beside
`dictionaries/cedict.sqlite`: the app reads them before any download
(decision 0124)."""


def bundle_packs(
    languages: Sequence[str], built: Path, folder: Path, version: str
) -> list[Path]:
    """`languages`' packs (both meanings files each, as `tools.dictionaries.
    packs` builds them in `built`) copied into `folder`, each stamped with
    `version` - the fallback for testers who can't download one (decision
    0124). Their credits go beside them."""
    from polyglotic_desktop.adapters.sqlite_dictionary import add_info
    from tools.dictionaries.packs import PACKS

    folder.mkdir(parents=True, exist_ok=True)
    copied = []
    for language in languages:
        name = PACKS[language].name
        for file in (f"{name}.sqlite", f"{name}-zh.sqlite", f"{name}.CREDITS.md"):
            source = built / file
            if not source.is_file():
                raise FileNotFoundError(f"{source.name}: build the packs first")
            shutil.copy2(source, folder / file)
            if file.endswith(".sqlite"):
                add_info(folder / file, {"pack_version": version})
                copied.append(folder / file)
    return copied


def build(
    tag: str,
    channel: str,
    dictionaries: Path,
    out: Path,
    packs: Sequence[str] = (),
    packs_from: Path | None = None,
) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    release = stamp.stamp(stamp.version_from_tag(tag), channel, stamp.built_now())
    version = json.loads(release)["version"]
    (WORK / "release.json").write_text(release, encoding="utf-8")
    layout = LAYOUT
    macos = layout is MACOS
    if macos:
        icon = WORK / f"{NAME}.icns"
        write_icns(icon)
        (WORK / "info.json").write_text(
            json.dumps(info_plist(version)), encoding="utf-8"
        )
    else:
        icon = WORK / f"{NAME}.ico"
        (WORK / "version_info.txt").write_text(version_info(version), encoding="utf-8")
        write_icon(icon)
    i18n.build()  # the interface's .qm files, packed with the other assets
    missing = [f for f in DICTIONARY_FILES if not (dictionaries / f).is_file()]
    if missing:
        print(f"No dictionaries in {dictionaries}: run tools.dictionaries.build first")
        return 1

    env = dict(
        os.environ,
        POLYGLOTIC_STAMP=str(WORK / "release.json"),
        POLYGLOTIC_ICON=str(icon),
        POLYGLOTIC_QT_LANGUAGES=" ".join(QT_LANGUAGES),
    )
    if macos:  # the app bundle's Info.plist (the spec's BUNDLE)
        env["POLYGLOTIC_INFO_PLIST"] = str(WORK / "info.json")
    else:  # Windows' file properties
        env["POLYGLOTIC_VERSION_FILE"] = str(WORK / "version_info.txt")
    pyinstaller = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm",
                   "--clean", "--log-level", "WARN", "--distpath", str(out),
                   "--workpath", str(WORK / "work")]  # fmt: skip
    started = time.perf_counter()
    subprocess.run(pyinstaller, env=env, check=True, cwd=REPO)
    build_seconds = round(time.perf_counter() - started, 1)

    folder = out / layout.folder
    beside = folder / layout.beside
    shutil.copytree(dictionaries, beside / "dictionaries", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*-wal", "*-shm", "*.tmp", "packs"))  # fmt: skip
    if packs:  # off by default: packs are downloaded (decision 0124)
        bundled = bundle_packs(
            packs,
            packs_from or dictionaries / "packs",
            beside / "dictionaries" / IN_THE_INSTALLER,
            version,
        )
        print(f"Packs in the installer: {', '.join(p.name for p in bundled)}")
    shutil.copy2(REPO / "THIRD_PARTY_NOTICES.md", beside / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(REPO / "RELEASE-NOTES.md", beside / "RELEASE-NOTES.md")
    licences = copy_licences(folder, layout)
    signature = sign(folder) if macos else None

    found = problems(folder, layout)
    if signature is not None:
        found += signature_problems(signature)
    check = settled_check_install(folder, layout)
    if check.get("exit_code") != 0 or check.get("version") != version:
        found.append(f"--check-install failed: {check}")
    found += first_launch_failed(check)
    start_limit = start_limit_ms(layout)
    found += over_start_budget(check, start_limit)
    found += packs_as_decided(check)
    files = [p for p in folder.rglob("*") if p.is_file()]
    if macos:
        zipped = ditto_zip(folder)
    summary = {
        "version": version,
        "channel": channel,
        "build_seconds": build_seconds,
        "files": len(files),
        "size_mb": mb(sum(p.stat().st_size for p in files)),
        "zipped_mb": mb(zipped if macos else zipped_size(folder)),
        "check_install": check,
        "start_judged_against_ms": start_limit,
        "signature": signature,
        "biggest_mb": biggest(folder),
        "licences": licences,
        "problems": found,
    }
    (WORK / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "licences"}, indent=2))
    if found:
        print("\nThe packed app isn't right:\n- " + "\n- ".join(found))
        return 1
    print(f"\nPacked {NAME} {version} ({channel}) in {folder}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.build")
    parser.add_argument("tag", help="the release's git tag, e.g. v0.1.0")
    parser.add_argument("--channel", default="win-x64-alpha")
    parser.add_argument(
        "--dictionaries", type=Path, default=REPO / "build" / "dictionaries"
    )
    parser.add_argument("--out", type=Path, default=REPO / "dist")
    parser.add_argument(
        "--packs",
        nargs="+",
        default=[],
        metavar="LANGUAGE",
        help="put these languages' dictionary packs in the installer (ru es):"
        " off by default, they're downloaded (decision 0124)",
    )
    parser.add_argument(
        "--packs-from",
        type=Path,
        help="where the packs are built (default DICTIONARIES/packs)",
    )
    args = parser.parse_args(argv)
    try:
        return build(
            args.tag,
            args.channel,
            args.dictionaries,
            args.out,
            args.packs,
            args.packs_from,
        )
    except ValueError as e:
        print(f"Not a release: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
