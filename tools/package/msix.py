"""The Microsoft Store's package: the build Velopack packs, packed again as
an MSIX (decision 0056).

    python -m tools.package.msix pack VERSION APP OUT.msix [--rehearsal]
        [--sign PFX --password-file FILE]
    python -m tools.package.msix compare OUT.msix APP

- `pack` packs the PyInstaller folder APP (`dist/Polyglotic`, or a
  promotion's unpacked app) as it is - one build, packed twice (decision
  0044) - with the package's own files beside it: its manifest (the Store's
  identity, the capabilities the app needs), the app's icon at Windows'
  sizes and the `resources.pri` that finds them. MakeAppx and MakePri come
  from the Windows SDK's build tools, pinned and checked by SHA-256
  (`build_tools`). The package is unsigned: the Store signs what it
  publishes ("The Microsoft Store will automatically re-sign your MSIX/AppX
  packages", Microsoft Learn, "App package requirements for MSIX app",
  updated 2026-08-24).
- `--rehearsal` packs it as another app, for an install on this PC
  (polyglotic-hq projects/README.md): its own identity and name, no Start
  menu entry, and a command (`polyglotic-rehearsal`) that starts it with
  arguments - `--data` and `--credentials` of its own. `--sign` signs it
  with a test certificate, for sideloading only.
- `compare` checks the package holds APP's files byte for byte, and nothing
  else but the package's own.

The identity's three values are Partner Center's, once the name is
reserved (Product identity: Package/Identity/Name, Package/Identity/
Publisher, Package/Properties/PublisherDisplayName). Until then `STORE` is a
placeholder the Store would refuse, so nothing packed before can be
submitted by mistake. Changed only by a pull request, like main.SERVER.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from xml.sax.saxutils import escape, quoteattr

# -- what's in the package --------------------------------------------------------


@dataclass(frozen=True)
class Identity:
    """Who the package says it is. For the Store, Partner Center's values,
    which the manifest must match exactly."""

    name: str
    """Package/Identity/Name: the reserved name's package name."""
    publisher: str
    """Package/Identity/Publisher: `CN=` and Partner Center's publisher ID -
    or, for a sideloaded rehearsal, the test certificate's subject."""
    publisher_display_name: str
    display_name: str
    placeholder: bool = False
    """Not Partner Center's yet: the Store would refuse it."""
    rehearsal: bool = False
    """An install on this PC: no Start menu entry, and a command to start it."""


STORE = Identity(
    name="Polyglotic.Placeholder",
    publisher="CN=00000000-0000-0000-0000-000000000000",
    publisher_display_name="Polyglotic",
    display_name="Polyglotic",
    placeholder=True,
)
"""The Store's package. A placeholder until the user reserves the name in
Partner Center (polyglotic-hq projects/264's STORE.md): then its name,
publisher and publisher display name, exactly as Partner Center shows them."""

REHEARSAL = Identity(
    name="PolygloticRehearsal",
    publisher="CN=Polyglotic Rehearsal Test",
    publisher_display_name="Polyglotic Rehearsal",
    display_name="Polyglotic Rehearsal",
    rehearsal=True,
)
"""An install on this PC, as another app: never the Store's identity."""

APP_ID = "Polyglotic"
"""The application's ID in the package: Windows knows the Store's copy by
`<package family name>!Polyglotic` on the taskbar (decision 0051)."""
EXE = "Polyglotic.exe"
REHEARSAL_COMMAND = "polyglotic-rehearsal.exe"
MIN_WINDOWS = "10.0.19041.0"  # Windows 10 2004: uap10, and what the Store lists
TESTED_WINDOWS = "10.0.26200.0"  # Windows 11 25H2, where it was installed

CAPABILITIES = ("runFullTrust", "microphone")
"""What the package declares. `runFullTrust`: a desktop app, not in an app
container - restricted, so the Store asks why at submission. `microphone`:
the mic as a source, with its own switch in Windows' privacy settings.
Capturing an app's or the system's sound (WASAPI loopback) has no
capability to declare."""

# The package's own files, beside the app's (`compare` allows only these)
OWN_FILES = re.compile(
    r"^(AppxManifest\.xml|AppxBlockMap\.xml|\[Content_Types\]\.xml"
    r"|AppxSignature\.p7x|AppxMetadata/.*|resources\.pri|Assets/[^/]+\.png)$"
)

# -- the icons ----------------------------------------------------------------------

SCALES = (100, 125, 150, 200, 400)
TARGET_SIZES = (16, 20, 24, 32, 48, 256)  # the .ico's: the taskbar, Start, Explorer


@dataclass(frozen=True)
class Logo:
    """One of the manifest's images: its name, its size at 100%, and how
    much of it the icon fills."""

    name: str
    width: int
    height: int
    fill: float = 1.0


LOGOS = (
    Logo("Square44x44Logo", 44, 44),  # the app list, the taskbar, Start's pins
    Logo("Square150x150Logo", 150, 150, fill=0.66),  # a tile: the icon inset
    Logo("StoreLogo", 50, 50),  # the package's logo (installers, Settings)
)


def logo_files() -> dict[str, tuple[int, int, float]]:
    """Each image file in `Assets/` -> its width, height and fill: every
    logo at each scale, and the small logo at each target size, plated and
    unplated (on the taskbar)."""
    files = {}
    for logo in LOGOS:
        for scale in SCALES:
            width = round(logo.width * scale / 100)
            height = round(logo.height * scale / 100)
            files[f"{logo.name}.scale-{scale}.png"] = (width, height, logo.fill)
    for size in TARGET_SIZES:
        files[f"Square44x44Logo.targetsize-{size}.png"] = (size, size, 1.0)
        files[f"Square44x44Logo.targetsize-{size}_altform-unplated.png"] = (
            size,
            size,
            1.0,
        )
    return files


def write_logos(assets: Path) -> list[Path]:
    """The app's icon (`ui.icons`, from its SVG masters, as the .ico) drawn
    for each of `logo_files()`, transparent around it."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    from polyglotic_desktop.ui.icons import app_image

    _app = QGuiApplication.instance() or QGuiApplication([])
    assets.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (width, height, fill) in logo_files().items():
        side = max(1, round(min(width, height) * fill))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.drawImage((width - side) // 2, (height - side) // 2, app_image(side))
        painter.end()
        path = assets / name
        if not image.save(str(path)):  # PNG, from the name
            raise RuntimeError(f"couldn't write {name}")
        written.append(path)
    return written


# -- the manifest -------------------------------------------------------------------


def store_version(version: str) -> str:
    """The package's version for the app's `MAJOR.MINOR.PATCH`: the Store's
    four parts, the first never 0 and the last always 0 ("reserved for Store
    use"), so `(MAJOR+1).MINOR.PATCH.0` - 0.1.0 is 1.1.0.0. It only ever
    rises with the app's, so the Store always sees a newer package as newer.
    Fixed once the first package is submitted (decision 0056)."""
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not MAJOR.MINOR.PATCH: {version!r}")
    major, minor, patch = (int(p) for p in parts)
    numbers = (major + 1, minor, patch, 0)
    if any(n > 65535 for n in numbers):
        raise ValueError(f"too big for a package version: {version!r}")
    return ".".join(str(n) for n in numbers)


def manifest(identity: Identity, version: str) -> str:
    """AppxManifest.xml for the app at `version` (MAJOR.MINOR.PATCH)."""
    description = "Live captions and translations of what you hear, for learners."
    visual = (
        f"<uap:VisualElements DisplayName={quoteattr(identity.display_name)}"
        f' Description={quoteattr(description)} BackgroundColor="transparent"'
        ' Square150x150Logo="Assets\\Square150x150Logo.png"'
        ' Square44x44Logo="Assets\\Square44x44Logo.png"'
        + (' AppListEntry="none"' if identity.rehearsal else "")
        + " />"
    )
    extensions = ""
    if identity.rehearsal:  # started with arguments of its own (`--data` ...)
        extensions = f"""
      <Extensions>
        <uap5:Extension Category="windows.appExecutionAlias" Executable="{EXE}" EntryPoint="Windows.FullTrustApplication">
          <uap5:AppExecutionAlias>
            <uap5:ExecutionAlias Alias="{REHEARSAL_COMMAND}" />
          </uap5:AppExecutionAlias>
        </uap5:Extension>
      </Extensions>"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap5="http://schemas.microsoft.com/appx/manifest/uap/windows10/5"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap5 rescap">
  <Identity Name={quoteattr(identity.name)} Publisher={quoteattr(identity.publisher)} Version="{store_version(version)}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{escape(identity.display_name)}</DisplayName>
    <PublisherDisplayName>{escape(identity.publisher_display_name)}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="{MIN_WINDOWS}" MaxVersionTested="{TESTED_WINDOWS}" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Applications>
    <Application Id="{APP_ID}" Executable="{EXE}" EntryPoint="Windows.FullTrustApplication">
      {visual}{extensions}
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
    <DeviceCapability Name="microphone" />
  </Capabilities>
</Package>
"""


# -- the Windows SDK's tools ------------------------------------------------------

SDK_VERSION = "10.0.28000.2705"  # NuGet, 2026-08-26
SDK_SHA256 = "8bfdfb6ca2633f531cf80b5fa22512ba61a394d7988f0970db83baadc67929ed"
"""Microsoft.Windows.SDK.BuildTools' package (MakeAppx, MakePri, SignTool),
checked against NuGet's own SHA-512 when pinned (2026-11-09)."""
SDK_URL = (
    "https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.buildtools/"
    f"{SDK_VERSION}/microsoft.windows.sdk.buildtools.{SDK_VERSION}.nupkg"
)
SDK_BIN = "bin/10.0.28000.0/x64/"
SDK_CACHE = Path("build/windows-sdk")


class NotTrusted(Exception):
    """A download that isn't the pinned file, or a package that isn't the
    build: the reason."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while piece := f.read(1 << 20):
            digest.update(piece)
    return digest.hexdigest()


def build_tools(cache: Path = SDK_CACHE) -> Path:
    """The folder with MakeAppx, MakePri and SignTool: the Windows SDK's
    build tools from NuGet, fetched once into `cache` and checked against
    the pinned SHA-256 - no Windows SDK to install (it needs an
    administrator), nothing from the PATH."""
    tools = cache / SDK_VERSION / "x64"
    if (tools / "makeappx.exe").is_file():
        return tools
    cache.mkdir(parents=True, exist_ok=True)
    package = cache / f"buildtools-{SDK_VERSION}.nupkg"
    if not package.is_file() or sha256(package) != SDK_SHA256:
        with urllib.request.urlopen(SDK_URL, timeout=120) as response:
            package.write_bytes(response.read())
    found = sha256(package)
    if found != SDK_SHA256:
        package.unlink()
        raise NotTrusted(f"the build tools' package is {found}, pinned {SDK_SHA256}")
    unpacked = tools.with_name("x64.partial")
    shutil.rmtree(unpacked, ignore_errors=True)
    with zipfile.ZipFile(package) as z:
        for info in z.infolist():
            if info.filename.startswith(SDK_BIN) and not info.is_dir():
                name = PurePosixPath(info.filename.removeprefix(SDK_BIN))
                if len(name.parts) != 1:  # the tools only, no subfolders
                    continue
                (unpacked / name.name).parent.mkdir(parents=True, exist_ok=True)
                (unpacked / name.name).write_bytes(z.read(info))
    unpacked.rename(tools)
    return tools


def _run(command: list[str]) -> None:
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        print(done.stdout[-4000:], done.stderr[-4000:], sep="\n", file=sys.stderr)
        raise RuntimeError(f"{Path(command[0]).name} failed ({done.returncode})")


# -- packing ------------------------------------------------------------------------

PRICONFIG = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<resources targetOsVersion="10.0.0" majorVersion="1">
  <index root="\\" startIndexAt="\\">
    <default>
      <qualifier name="Language" value="en-US"/>
      <qualifier name="Contrast" value="standard"/>
      <qualifier name="Scale" value="100"/>
      <qualifier name="HomeRegion" value="001"/>
      <qualifier name="TargetSize" value="256"/>
      <qualifier name="LayoutDirection" value="LTR"/>
      <qualifier name="Theme" value="dark"/>
      <qualifier name="AlternateForm" value=""/>
      <qualifier name="DXFeatureLevel" value="DX9"/>
      <qualifier name="Configuration" value=""/>
      <qualifier name="DeviceFamily" value="Universal"/>
      <qualifier name="Custom" value=""/>
    </default>
    <indexer-config type="folder" foldernameAsQualifier="true" filenameAsQualifier="true" qualifierDelimiter="."/>
  </index>
</resources>
"""
"""MakePri's configuration (`makepri createconfig`'s for Windows 10, en-US)
without its `<packaging>`: one resources.pri for one package, not one per
scale for a bundle's resource packages."""


def mapping(app: Path, own: Path) -> str:
    """MakeAppx's mapping file: each of the app's files at its own path in
    the package, and the package's own files from `own` - nothing copied.
    ValueError if the app has a file where the package keeps its own."""
    lines = ["[Files]"]
    for folder in (own, app):
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            inside = path.relative_to(folder).as_posix()
            if folder == app and OWN_FILES.match(inside):
                raise ValueError(f"{inside}: the package's own file, not the app's")
            lines.append(f'"{path.resolve()}" "{inside.replace("/", chr(92))}"')
    return "\n".join(lines) + "\n"


def pack(
    version: str,
    app: Path,
    out: Path,
    identity: Identity = STORE,
    tools: Path | None = None,
) -> Path:
    """The MSIX of `app` at `out`: the app's files unchanged, the manifest,
    the logos and resources.pri. Returns `out`."""
    if not (app / EXE).is_file():
        raise FileNotFoundError(f"{app / EXE}: not a PyInstaller folder")
    tools = tools or build_tools()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="msix-") as work:
        own, config = Path(work) / "package", Path(work) / "config"
        own.mkdir()
        config.mkdir()
        (own / "AppxManifest.xml").write_text(
            manifest(identity, version), encoding="utf-8", newline="\r\n"
        )
        write_logos(own / "Assets")
        priconfig = config / "priconfig.xml"
        priconfig.write_text(PRICONFIG, encoding="utf-8")
        _run(
            [str(tools / "makepri.exe"), "new", "/pr", str(own), "/cf", str(priconfig),
             "/mn", str(own / "AppxManifest.xml"), "/of", str(own / "resources.pri"),
             "/o"]
        )  # fmt: skip
        files = config / "mapping.txt"
        files.write_text(mapping(app, own), encoding="utf-8")
        _run(
            [str(tools / "makeappx.exe"), "pack", "/o", "/h", "SHA256",
             "/f", str(files), "/p", str(out)]
        )  # fmt: skip
    return out


def sign(package: Path, pfx: Path, password: str, tools: Path | None = None) -> None:
    """Signs `package` with a test certificate, for sideloading on this PC
    only. Never a real signing identity: the Store signs its own."""
    tools = tools or build_tools()
    _run(
        [str(tools / "signtool.exe"), "sign", "/fd", "SHA256", "/f", str(pfx),
         "/p", password, str(package)]
    )  # fmt: skip


def compare(package: Path, app: Path) -> list[str]:
    """What isn't the build: one line per problem, none if the package holds
    `app`'s files byte for byte and nothing else but its own."""
    expected = {
        path.relative_to(app).as_posix(): sha256(path)
        for path in app.rglob("*")
        if path.is_file()
    }
    found = {}
    with zipfile.ZipFile(package) as z:
        for info in z.infolist():
            name = unquote(info.filename)
            if not info.is_dir() and not OWN_FILES.match(name):
                found[name] = hashlib.sha256(z.read(info)).hexdigest()
    problems = [
        f"{n}: only in the build" for n in sorted(expected.keys() - found.keys())
    ]
    problems += [
        f"{n}: not in the build" for n in sorted(found.keys() - expected.keys())
    ]
    problems += [
        f"{n}: not the build's bytes"
        for n in sorted(expected.keys() & found.keys())
        if expected[n] != found[n]
    ]
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.msix")
    commands = parser.add_subparsers(dest="command", required=True)
    packing = commands.add_parser("pack", help="the build as the Store's MSIX")
    packing.add_argument("version", help="MAJOR.MINOR.PATCH")
    packing.add_argument("app", type=Path, help="the PyInstaller folder")
    packing.add_argument("out", type=Path, help="the .msix to write")
    packing.add_argument(
        "--rehearsal", action="store_true", help="another app, for this PC"
    )
    packing.add_argument("--sign", type=Path, metavar="PFX", help="a test certificate")
    packing.add_argument(
        "--password-file", type=Path, help="the certificate's password"
    )
    comparing = commands.add_parser("compare", help="the package holds the build")
    comparing.add_argument("package", type=Path)
    comparing.add_argument("app", type=Path)
    args = parser.parse_args(argv)
    if args.command == "pack":
        identity = REHEARSAL if args.rehearsal else STORE
        if args.sign and not args.rehearsal:
            parser.error("--sign is for a rehearsal: the Store signs its own")
        out = pack(args.version, args.app, args.out, identity)
        if args.sign:
            password = args.password_file.read_text(encoding="utf-8").strip()
            sign(out, args.sign, password)
        note = (
            " (placeholder identity: not for the Store)" if identity.placeholder else ""
        )
        print(f"{out}: {store_version(args.version)}, {identity.name}{note}")
        print(f"{sha256(out)}  {out.name}")
        return 0
    problems = compare(args.package, args.app)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"{args.package.name}: the build's files, byte for byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
