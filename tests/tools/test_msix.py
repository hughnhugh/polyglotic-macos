"""The Microsoft Store's package (decision 0056): its manifest, its
version, its logos, the pinned build tools, and the check that it holds the
build's files - against folders and packages made here. Package packs the
real build with MakeAppx on every run (.github/actions/build-and-pack)."""

import hashlib
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Self
from xml.etree import ElementTree

import pytest
from tools.package import msix
from tools.package.msix import REHEARSAL, STORE, Identity, NotTrusted

NS = {
    "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "uap5": "http://schemas.microsoft.com/appx/manifest/uap/windows10/5",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
}


def parsed(identity: Identity = STORE, version: str = "0.1.0") -> ElementTree.Element:
    return ElementTree.fromstring(msix.manifest(identity, version).encode("utf-8"))


@pytest.mark.parametrize(
    ("version", "package"),
    [("0.1.0", "1.1.0.0"), ("0.1.12", "1.1.12.0"), ("1.0.0", "2.0.0.0")],
)
def test_the_package_version_has_a_first_part_above_0_and_a_last_part_of_0(
    version: str, package: str
) -> None:
    assert msix.store_version(version) == package


def test_a_newer_app_is_always_a_newer_package() -> None:
    order = ["0.1.0", "0.1.1", "0.2.0", "0.10.0", "1.0.0", "1.0.1", "2.0.0"]
    packages = [tuple(map(int, msix.store_version(v).split("."))) for v in order]
    assert packages == sorted(packages)


@pytest.mark.parametrize("version", ["0.1", "v0.1.0", "0.1.0.0", "0.1.x", "0.70000.0"])
def test_a_version_the_package_cant_carry_is_refused(version: str) -> None:
    with pytest.raises(ValueError):
        msix.store_version(version)


def test_the_manifest_names_the_store_identity_and_the_version() -> None:
    root = parsed(version="0.3.2")
    identity = root.find("m:Identity", NS)
    assert identity is not None
    assert identity.get("Name") == STORE.name
    assert identity.get("Publisher") == STORE.publisher
    assert identity.get("Version") == "1.3.2.0"
    assert identity.get("ProcessorArchitecture") == "x64"
    assert root.findtext("m:Properties/m:DisplayName", namespaces=NS) == "Polyglotic"


def test_the_store_identity_is_a_placeholder_until_partner_center_gives_it() -> None:
    # replaced by Partner Center's values in the pull request that fills them
    assert STORE.placeholder
    assert STORE.publisher.startswith("CN=")


def test_the_app_is_a_desktop_app_started_as_polyglotic_exe() -> None:
    app = parsed().find("m:Applications/m:Application", NS)
    assert app is not None
    assert app.get("Id") == msix.APP_ID
    assert app.get("Executable") == "Polyglotic.exe"
    assert app.get("EntryPoint") == "Windows.FullTrustApplication"


def test_it_declares_full_trust_and_the_microphone_and_nothing_else() -> None:
    capabilities = parsed().find("m:Capabilities", NS)
    assert capabilities is not None
    declared = [(c.tag.split("}")[1], c.get("Name")) for c in capabilities]
    assert declared == [
        ("Capability", "runFullTrust"),
        ("DeviceCapability", "microphone"),
    ]
    assert capabilities[0].tag == f"{{{NS['rescap']}}}Capability"


def test_the_store_copy_is_in_start_and_has_no_command() -> None:
    visual = parsed().find("m:Applications/m:Application/uap:VisualElements", NS)
    assert visual is not None
    assert visual.get("AppListEntry") is None
    assert parsed().find(".//uap5:ExecutionAlias", NS) is None


def test_a_rehearsal_is_another_app_with_no_start_entry_and_a_command() -> None:
    root = parsed(REHEARSAL)
    identity = root.find("m:Identity", NS)
    assert identity is not None
    assert identity.get("Name") != STORE.name
    assert "Rehearsal" in identity.get("Name", "")
    visual = root.find("m:Applications/m:Application/uap:VisualElements", NS)
    assert visual is not None
    assert visual.get("AppListEntry") == "none"
    alias = root.find(".//uap5:ExecutionAlias", NS)
    assert alias is not None
    assert alias.get("Alias") == msix.REHEARSAL_COMMAND


def test_names_with_markup_characters_stay_text() -> None:
    odd = Identity("A.B", 'CN="x" & <y>', "Me & Co", "P<o>")
    root = parsed(odd)
    assert (
        root.findtext("m:Properties/m:PublisherDisplayName", namespaces=NS) == "Me & Co"
    )
    identity = root.find("m:Identity", NS)
    assert identity is not None
    assert identity.get("Publisher") == 'CN="x" & <y>'


def test_every_logo_the_manifest_names_is_drawn_at_each_scale() -> None:
    files = msix.logo_files()
    for logo in ("Square44x44Logo", "Square150x150Logo", "StoreLogo"):
        assert f"Assets\\{logo}.png" in msix.manifest(STORE, "0.1.0")
        for scale in msix.SCALES:
            assert f"{logo}.scale-{scale}.png" in files
    assert files["Square44x44Logo.scale-200.png"][:2] == (88, 88)
    assert files["Square150x150Logo.scale-400.png"][:2] == (600, 600)
    for size in (16, 24, 32, 48, 256):  # the taskbar's, unplated
        assert files[f"Square44x44Logo.targetsize-{size}_altform-unplated.png"][:2] == (
            size,
            size,
        )


def test_the_logos_are_pngs_of_their_size(tmp_path: Path) -> None:
    """Drawn under the widgets' application, as the icon's test is
    (test_package_build): the tool makes a bare QGuiApplication when there's
    none, and one left behind failed every test after it that needs a
    QApplication - 227 of tests/ui's in a run of tests/tools then tests/ui
    (polyglotic-hq 565, the whole suite split across machines)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    written = msix.write_logos(tmp_path)
    assert isinstance(QGuiApplication.instance(), QApplication)
    assert {p.name for p in written} == set(msix.logo_files())
    image = QImage(str(tmp_path / "Square150x150Logo.scale-100.png"))
    assert (image.width(), image.height()) == (150, 150)
    assert image.pixelColor(0, 0).alpha() == 0  # inset on a clear tile
    assert image.pixelColor(75, 75).alpha() == 255


def app_folder(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    (app / "_internal" / "polyglotic_desktop").mkdir(parents=True)
    (app / "Polyglotic.exe").write_bytes(b"the app")
    (app / "_internal" / "polyglotic_desktop" / "release.json").write_text("{}")
    (app / "_internal" / "a file [x].txt").write_bytes(b"spaces and brackets")
    return app


def test_the_mapping_puts_each_file_at_its_own_path(tmp_path: Path) -> None:
    app = app_folder(tmp_path)
    own = tmp_path / "own"
    (own / "Assets").mkdir(parents=True)
    (own / "AppxManifest.xml").write_text("<Package/>")
    (own / "Assets" / "StoreLogo.scale-100.png").write_bytes(b"png")
    lines = msix.mapping(app, own).splitlines()
    assert lines[0] == "[Files]"
    targets = {re.fullmatch(r'"([^"]+)" "([^"]+)"', line)[2] for line in lines[1:]}  # type: ignore[index]
    assert targets == {
        "AppxManifest.xml",
        "Assets\\StoreLogo.scale-100.png",
        "Polyglotic.exe",
        "_internal\\polyglotic_desktop\\release.json",
        "_internal\\a file [x].txt",
    }
    assert f'"{(app / "Polyglotic.exe").resolve()}" "Polyglotic.exe"' in lines


def test_an_app_file_where_the_package_keeps_its_own_is_refused(tmp_path: Path) -> None:
    app = app_folder(tmp_path)
    (app / "resources.pri").write_bytes(b"the app's")
    with pytest.raises(ValueError, match="resources.pri"):
        msix.mapping(app, tmp_path / "own")


def msix_like(path: Path, files: dict[str, bytes]) -> Path:
    """A package as MakeAppx lays it out: names percent-encoded."""
    own = {
        "AppxManifest.xml": b"<Package/>",
        "AppxBlockMap.xml": b"<BlockMap/>",
        "[Content_Types].xml": b"<Types/>",
        "resources.pri": b"pri",
        "Assets/StoreLogo.scale-100.png": b"png",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, data in {**own, **files}.items():
            z.writestr(name.replace(" ", "%20").replace("[", "%5B").replace("]", "%5D")
                       if name not in own else name, data)  # fmt: skip
    return path


def test_a_package_of_the_builds_files_compares_clean(tmp_path: Path) -> None:
    app = app_folder(tmp_path)
    files = {
        p.relative_to(app).as_posix(): p.read_bytes()
        for p in app.rglob("*")
        if p.is_file()
    }
    assert msix.compare(msix_like(tmp_path / "p.msix", files), app) == []


def test_a_changed_missing_or_extra_file_isnt_the_build(tmp_path: Path) -> None:
    app = app_folder(tmp_path)
    files = {
        p.relative_to(app).as_posix(): p.read_bytes()
        for p in app.rglob("*")
        if p.is_file()
    }
    files["Polyglotic.exe"] = b"another app"
    del files["_internal/a file [x].txt"]
    files["Update.exe"] = b"velopack"
    problems = msix.compare(msix_like(tmp_path / "p.msix", files), app)
    assert problems == [
        "_internal/a file [x].txt: only in the build",
        "Update.exe: not in the build",
        "Polyglotic.exe: not the build's bytes",
    ]


def nupkg(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


def test_the_build_tools_are_unpacked_once_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = nupkg(
        {
            msix.SDK_BIN + "makeappx.exe": b"makeappx",
            msix.SDK_BIN + "makepri.exe": b"makepri",
            msix.SDK_BIN + "arm64/other.exe": b"not ours",
            "bin/10.0.28000.0/x86/makeappx.exe": b"32-bit",
        }
    )
    monkeypatch.setattr(msix, "SDK_SHA256", hashlib.sha256(data).hexdigest())
    (tmp_path / f"buildtools-{msix.SDK_VERSION}.nupkg").write_bytes(data)
    tools = msix.build_tools(tmp_path)
    assert sorted(p.name for p in tools.iterdir()) == ["makeappx.exe", "makepri.exe"]
    assert (tools / "makeappx.exe").read_bytes() == b"makeappx"
    assert msix.build_tools(tmp_path) == tools  # the second time, as it is


def test_build_tools_that_arent_the_pinned_package_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = nupkg({msix.SDK_BIN + "makeappx.exe": b"someone else's"})

    class Response(io.BytesIO):
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(msix.urllib.request, "urlopen", lambda *a, **k: Response(data))
    with pytest.raises(NotTrusted):
        msix.build_tools(tmp_path)
    assert not list(tmp_path.glob("*.nupkg"))  # not kept
    assert not (tmp_path / msix.SDK_VERSION / "x64").exists()


def test_signing_is_for_a_rehearsal_only(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        msix.main(["pack", "0.1.0", str(tmp_path), str(tmp_path / "o.msix"),
                   "--sign", str(tmp_path / "t.pfx")])  # fmt: skip


def test_a_folder_without_the_app_isnt_packed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        msix.pack("0.1.0", tmp_path, tmp_path / "o.msix", tools=tmp_path)
