"""Prepare the disposable build checkout for an isolated Mac tester preview."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.macos_ui_lab import hosted_mac


def replace_once(path: str, changes: dict[str, str]) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    for old, new in changes.items():
        if text.count(old) != 1:
            raise ValueError(f"Preview identity patch has drifted in {path}")
        text = text.replace(old, new, 1)
    target.write_text(text, encoding="utf-8")


def prepare(out: Path) -> None:
    if not hosted_mac():
        raise RuntimeError("Prepare only the disposable hosted Mac checkout")
    folder = "Polyglotic-Preview"
    service = "Polyglotic/preview"
    identifier = "io.polyglotic.desktop.preview"
    name = "Polyglotic Preview"
    replace_once(
        "tools/package/build.py",
        {
            'BUNDLE_ID = "io.polyglotic.desktop"': f'BUNDLE_ID = "{identifier}"',
            '"CFBundleDisplayName": NAME': f'"CFBundleDisplayName": "{name}"',
            '"CFBundleName": NAME': f'"CFBundleName": "{name}"',
        },
    )
    replace_once(
        "src/polyglotic_desktop/platform/macos/system.py",
        {'APP_FOLDER = "Polyglotic"': f'APP_FOLDER = "{folder}"'},
    )
    replace_once(
        "src/polyglotic_desktop/platform/macos/keychain.py",
        {'SERVICE = "Polyglotic/device"': f'SERVICE = "{service}"'},
    )
    replace_once(
        "src/polyglotic_desktop/main.py",
        {
            'UPDATES = "https://updates.polyglotic.io/"': "UPDATES = str(Path(sys.executable).resolve().parent)",
            "PACKS = UPDATES": 'PACKS = "https://updates.polyglotic.io/"',
            # The installer self-check constructs a manager independently of the
            # disabled application updater. Only the production HTTPS origin is signed.
            "signed = feed == UPDATES and bool(FEED_KEYS)": "signed = feed == PACKS and bool(FEED_KEYS)",
            'CREDENTIALS_ELSEWHERE = "Polyglotic/device@{server}"': 'CREDENTIALS_ELSEWHERE = "Polyglotic/preview@{server}"',
            "updater_or_store = None if store_copy else updater(args.updates)": "updater_or_store = None  # isolated tester preview has no application updates",
            '/ "Caches"\n            / "Polyglotic"': f'/ "Caches"\n            / "{folder}"',
        },
    )
    from polyglotic_desktop import main
    from polyglotic_desktop.platform.macos import keychain, system
    from polyglotic_desktop.platform.macos.one_copy import locks_folder
    from tools.package.build import info_plist

    plist = info_plist("0.1.10")
    assert (
        plist["CFBundleIdentifier"] == identifier
        and plist["CFBundleDisplayName"] == name
    )
    assert system.data_folder().name == folder and service == keychain.SERVICE
    assert locks_folder().parent == system.data_folder()
    assert (
        main.verified_feed_folder("/tmp/P.app/Contents/MacOS/Polyglotic").parent.name
        == folder
    )
    assert Path(main.UPDATES).is_dir() and not list(
        Path(main.UPDATES).glob("releases.*.json")
    )
    assert main.PACKS.startswith("https://") and main.pack_storage("", (), True)[1]
    out.mkdir(parents=True, exist_ok=True)
    (out / "identity.json").write_text(
        json.dumps(
            {
                "bundle": identifier,
                "name": name,
                "data_folder": folder,
                "keychain": service,
                "locks_in_preview_data": True,
                "update_feed": "application updater disabled; local empty program directory",
                "signed_dictionary_feed": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
