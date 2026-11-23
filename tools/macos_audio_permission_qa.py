"""Drive native system audio through the running app with the runner's own TCC state."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from polyglotic_desktop.core.listening.sources import WHOLE_SYSTEM
from tools import app_tour as kit
from tools.macos_capture_checks import Run, playing
from tools.macos_quartz import Evidence, Pointer, centre
from tools.macos_settings_sweep import activate, first_run, run_app
from tools.macos_ui_lab import hosted_mac


def main(out: Path) -> int:
    if not hosted_mac():
        raise SystemExit("Requires a disposable hosted Mac")
    from tests.ui.test_check_install import sample_dictionaries

    os.environ["QT_QPA_PLATFORM"] = "cocoa"
    evidence = Evidence(out)
    pointer = Pointer()
    driver = kit.Driver(240)

    def steps() -> kit.Step:
        yield from first_run()
        desktop = kit.STATE["desktop"]
        home = kit.hub().window
        home.go_to("home")
        desktop.settings.update(whole_system=True, apps=(), caption_mic=False)
        desktop.hide_windows.setChecked(True)
        activate()

        def denied() -> bool:
            current = desktop.caption_facts().activity.get(WHOLE_SYSTEM)
            return bool(current and current.not_allowed)

        yield kit.wait(
            denied, 30, "real system tap reports NOT_ALLOWED while afplay plays"
        )
        state = kit.hub().home.state
        if not hasattr(state, "capture_settings"):
            evidence.record(
                "native-system-audio-denied",
                home,
                home.frameGeometry(),
                "Home has a recovery action when the tap is denied",
                False,
            )
            return
        yield kit.wait(
            state.capture_settings.isVisible,
            8,
            "Home shows the audio permission action",
        )
        before = home.frameGeometry()
        evidence.record(
            "native-system-audio-denied",
            home,
            before,
            "real tap denied and recovery visible on Home",
            denied()
            and state.capture_problem.isVisible()
            and state.capture_settings.isVisible(),
        )
        if state.capture_settings.isVisible():
            # Only dismiss an actual denial button. The hosted OS can put its
            # permission prompt directly over the app's recovery control.
            shot = out / "native-system-audio-denied-desktop.jpg"
            locate = """
import AppKit
import Vision
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
try VNImageRequestHandler(url: url).perform([request])
for observation in request.results ?? [] {
    let word = observation.topCandidates(1).first?.string.lowercased() ?? ""
    if word.filter({$0.isLetter}) == "dontallow" {
        print(observation.boundingBox.midX, 1 - observation.boundingBox.midY)
        break
    }
}
"""
            import threading

            from PySide6.QtCore import QPoint

            answer: list[str] = []

            def locate_denial() -> None:
                result = subprocess.run(
                    ["swift", "-e", locate, str(shot)],
                    capture_output=True,
                    text=True,
                    timeout=75,
                    check=False,
                )
                answer.extend(result.stdout.split())

            worker = threading.Thread(target=locate_denial, daemon=True)
            worker.start()
            yield kit.wait(
                lambda: not worker.is_alive(),
                85,
                "read the denial button on the hosted desktop",
            )
            if len(answer) == 2:
                screen = home.screen().geometry()
                yield from pointer.click(
                    QPoint(
                        round(float(answer[0]) * screen.width()),
                        round(float(answer[1]) * screen.height()),
                    )
                )
            yield from pointer.click(centre(state.capture_settings))
            cocoa = importlib.import_module("AppKit")

            def settings_open() -> bool:
                front = cocoa.NSWorkspace.sharedWorkspace().frontmostApplication()
                return bool(
                    front and front.bundleIdentifier() == "com.apple.systempreferences"
                )

            yield kit.wait(
                settings_open, 12, "macOS System Settings comes to the front"
            )
            evidence.record(
                "privacy-settings-open",
                home,
                before,
                "System Settings handles the ScreenCapture pane URL",
                settings_open(),
                url=state.capture_settings.property("url"),
            )
            yield kit.wait(
                lambda: any(
                    "frames=" in line and "playing=" in line for line in diagnostics()
                ),
                80,
                "native capture records its first one-minute frame and playback counters",
            )

    driver.steps = steps()
    with tempfile.TemporaryDirectory(prefix="native-denial-") as scratch:
        work = Path(scratch)

        def diagnostics() -> list[str]:
            return [
                line.split("platform.macos.capture: ", 1)[-1]
                for path in work.rglob("polyglotic.log")
                for line in path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if "platform.macos.capture: " in line and " capture" in line
            ]

        bench = Run(work / "capture.json", None, 0)
        bench.blackhole()
        if not bench.blackhole_uid:
            return 1
        with playing("afplay", bench.long_wav):
            run_app(
                work,
                str(sample_dictionaries(work / "dictionaries")),
                driver,
                native_system_audio=True,
            )
        (out / "checks.json").write_bytes((work / "checks.json").read_bytes())
        records = diagnostics()
        (out / "diagnostic.json").write_text(
            json.dumps(records, indent=1), encoding="utf-8"
        )
    return int(
        not evidence.steps
        or not any("frames=" in line and "playing=" in line for line in records)
        or any(not r["ok"] for r in kit.RESULTS["checks"])
    )


if __name__ == "__main__":
    code = main(Path(sys.argv[1]))
    sys.stdout.flush()
    os._exit(code)
