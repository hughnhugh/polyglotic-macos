"""Offline checks for the Linux runner's APT setup."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("apt-config") is None, reason="needs Linux APT"
)
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "linux_qt_libs.sh"


@pytest.fixture
def apt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use real apt-config with test sources and record the package commands."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = {
        "apt-get": """
printf '%s\\n' "$@" >"$APT_TEST_DIR/${!#}.args"
if [[ ${!#} != update ]]; then
  touch mock.deb
  exit
fi
[[ ${APT_TEST_FAIL:-} != 1 ]] || exit 100
for option in "$@"; do
  case "$option" in
    Dir::Etc::SourceList=*) cat "${option#*=}" ;;
    Dir::Etc::SourceParts=*) cat "${option#*=}"/* ;;
  esac
done
""",
        "apt-cache": """
printf '%s\\n' "$@" >"$APT_TEST_DIR/cache.args"
echo fonts-wqy-microhei
""",
        "dpkg-query": "exit 1\n",
        "dpkg-deb": "exit 0\n",
    }
    for name, body in commands.items():
        command = bin_dir / name
        command.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8"
        )
        command.chmod(0o755)
    parts = tmp_path / "sources.list.d"
    parts.mkdir()
    config = tmp_path / "apt.conf"
    config.write_text(
        f'Dir::Etc::SourceList "{tmp_path / "sources.list"}";\n'
        f'Dir::Etc::SourceParts "{parts}";\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APT_CONFIG", str(config))
    monkeypatch.setenv("APT_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("POLYGLOTIC_APT_MIRROR", raising=False)
    monkeypatch.delenv("POLYGLOTIC_APT_TIMEOUT_SECONDS", raising=False)
    return tmp_path


def test_mirror_preserves_source_metadata_and_reaches_all_apt_commands(
    apt: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = "deb [arch=amd64] http://archive.ubuntu.com/ubuntu/ noble main\n"
    deb822 = (
        "Types: deb\n"
        "URIs: https://security.ubuntu.com/ubuntu/ http://gb.archive.ubuntu.com/ubuntu\n"
        "Suites: noble-security noble-updates\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    other = "deb https://packages.example.org/ubuntu noble main\n"
    (apt / "sources.list").write_text(legacy, encoding="utf-8")
    (apt / "sources.list.d" / "ubuntu.sources").write_text(deb822, encoding="utf-8")
    (apt / "sources.list.d" / "vendor.list").write_text(other, encoding="utf-8")
    mirror = "https://mirror.example.org/pub/ubuntu"
    monkeypatch.setenv("POLYGLOTIC_APT_MIRROR", mirror + "/")

    run = subprocess.run(
        ["bash", str(SCRIPT), str(apt / "qt-libs")],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert legacy.replace("http://archive.ubuntu.com/ubuntu/", mirror) in run.stderr
    assert (
        deb822.replace(
            "https://security.ubuntu.com/ubuntu/ http://gb.archive.ubuntu.com/ubuntu",
            f"{mirror} {mirror}",
        )
        in run.stderr
    )
    assert other in run.stderr
    assert (apt / "sources.list").read_text(encoding="utf-8") == legacy
    assert (apt / "sources.list.d" / "ubuntu.sources").read_text(
        encoding="utf-8"
    ) == deb822
    assert "QT_QPA_PLATFORM=offscreen" in run.stdout

    update_args = (apt / "update.args").read_text(encoding="utf-8").splitlines()
    source_opts = {arg for arg in update_args if arg.startswith("Dir::Etc::Source")}
    assert len(source_opts) == 2
    expected = source_opts | {
        "Acquire::http::Timeout=20",
        "Acquire::https::Timeout=20",
        "Acquire::Retries=3",
    }
    for log in ("update.args", "cache.args", "fonts-wqy-microhei.args"):
        assert expected.issubset((apt / log).read_text(encoding="utf-8").splitlines())


def test_update_failure_stops_before_download_with_the_system_sources(
    apt: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POLYGLOTIC_APT_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("APT_TEST_FAIL", "1")

    run = subprocess.run(
        ["bash", str(SCRIPT), str(apt / "qt-libs")],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert run.returncode == 100
    assert not run.stdout
    args = (apt / "update.args").read_text(encoding="utf-8").splitlines()
    assert "Acquire::http::Timeout=1" in args
    assert "Acquire::https::Timeout=1" in args
    assert "APT::Update::Error-Mode=any" in args
    assert not any(arg.startswith("Dir::Etc::Source") for arg in args)
    assert not (apt / "cache.args").exists()
