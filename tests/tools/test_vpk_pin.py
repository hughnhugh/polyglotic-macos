"""The packing tool and the app's updater are the same Velopack release:
`vpk` in `.config/dotnet-tools.json` and `velopack` in `uv.lock`
(Velopack versions its CLI and libraries together). Dependabot updates
them separately; this fails until both move."""

import json
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_vpk_and_the_velopack_library_are_the_same_version() -> None:
    tools = json.loads((REPO / ".config" / "dotnet-tools.json").read_text())
    vpk = tools["tools"]["vpk"]["version"]
    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    (velopack,) = [p["version"] for p in lock["package"] if p["name"] == "velopack"]
    assert vpk == velopack
    assert tools["tools"]["vpk"]["rollForward"] is False
