"""Run every UI lab state in Cocoa, isolating crashes and stalled native dialogs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

STATE_TIMEOUT_SEC = (
    45  # one state normally takes seconds, including interpreter startup
)


def hosted_mac() -> bool:
    return (
        sys.platform == "darwin"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    )


def fit_hosted_display(out: Path) -> None:
    """Use a larger advertised display mode for the lab's roomy-window states."""
    script = """
import CoreGraphics
let display = CGMainDisplayID()
let modes = CGDisplayCopyAllDisplayModes(display, nil) as? [CGDisplayMode] ?? []
let fit = modes.filter { $0.width >= 1440 && $0.height >= 1000 }
if let mode = fit.min(by: { $0.width * $0.height < $1.width * $1.height }) {
    var config: CGDisplayConfigRef?
    if CGBeginDisplayConfiguration(&config) == .success {
        if CGConfigureDisplayWithDisplayMode(config, display, mode, nil) == .success {
            print("mode_change", CGCompleteDisplayConfiguration(config, .forSession).rawValue)
        } else { CGCancelDisplayConfiguration(config) }
    }
}
print("screen_points", CGDisplayPixelsWide(display), CGDisplayPixelsHigh(display))
"""
    result = subprocess.run(
        ["swift", "-e", script], capture_output=True, text=True, timeout=90, check=False
    )
    (out / "display.txt").write_text(
        result.stdout or "Default display mode", encoding="utf-8"
    )


def failure_picture(out: Path, state: str) -> None:
    subprocess.run(
        ["screencapture", "-x", "-m", "-t", "jpg", str(out / (state + ".desktop.jpg"))],
        timeout=10,
        check=False,
    )


def main(language: str, state: str | None = None) -> int:
    if not hosted_mac():
        raise SystemExit("Requires a GitHub-hosted Mac")
    os.environ["QT_QPA_PLATFORM"] = "cocoa"
    from polyglotic_desktop.ui_next import languages
    from tools.ui_lab import lab
    from tools.ui_lab.__main__ import new_states

    states = new_states()
    out = Path("out") / "ui-lab" / language
    if state == "ui_next.qt_dialog":
        from tools.macos_dialog_qa import check

        return check(language, out)
    if state:
        own = languages.own_targets([language.replace("_", "-")])
        languages.own_languages = lambda: own
        selected = next(s for s in states if s.name == state)
        # These two states explicitly depict sliding. The hosted Mac has
        # Reduce Motion enabled, which correctly suppresses both animations.
        from polyglotic_desktop.ui_next import caption_window

        motion = (
            patch.object(caption_window, "reduced_motion", return_value=False)
            if state in {"ui_next.w1_arriving", "ui_next.w1j_two_apps"}
            else nullcontext()
        )
        try:
            with motion:
                (result,) = lab.run([selected], out, None, language)
        except Exception:
            app = lab.application()
            visible = [w for w in app.topLevelWidgets() if w.isVisible()]
            if visible:
                biggest = max(visible, key=lambda w: w.width() * w.height())
                biggest.grab().save(str(out / (state + ".failed.png")))
            failure_picture(out, state)
            raise
        return int(bool(result.gated and result.failed_checks()))

    out.mkdir(parents=True, exist_ok=True)
    fit_hosted_display(out)
    summary = []
    for s in states:
        with subprocess.Popen(
            [sys.executable, "-m", "tools.macos_ui_lab", language, s.name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        ) as child:
            try:
                _, error = child.communicate(
                    timeout=90 if s.name == "ui_next.qt_dialog" else STATE_TIMEOUT_SEC
                )
                code, detail = child.returncode, error[-800:]
            except subprocess.TimeoutExpired:
                try:
                    failure_picture(out, s.name)
                finally:
                    child.kill()
                    child.communicate()
                code, detail = 1, f"Exceeded {STATE_TIMEOUT_SEC} seconds"
        summary.append(
            {"state": s.name, "exit": code, "detail": detail if code else ""}
        )
        (out / "states.json").write_text(
            json.dumps(summary, indent=1), encoding="utf-8"
        )
        print(f"{s.name}: {code}", flush=True)
    return int(any(row["exit"] for row in summary))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
