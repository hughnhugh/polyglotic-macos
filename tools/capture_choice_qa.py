"""Measure capture plans and session identity while the real app handles source changes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.ui.test_check_install import sample_dictionaries

from polyglotic_desktop import main as app
from polyglotic_desktop.connection.client import Connection
from polyglotic_desktop.ports.capture import PlayingApp, SourceCategory
from polyglotic_desktop.ui.settings import AppSettings
from tools import app_tour as kit
from tools.macos_settings_sweep import first_run, run_app


def main(out: Path) -> int:
    if os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("Requires a disposable hosted desktop")
    os.environ["QT_QPA_PLATFORM"] = "cocoa" if sys.platform == "darwin" else "offscreen"
    out.mkdir(parents=True, exist_ok=True)
    sources: list[app.Sources] = []
    plans: list[dict[str, Any]] = []
    starts: list[int] = []
    original = Connection.start_listening

    def start(connection: Any, *args: Any, **kwargs: Any) -> Any:
        session = original(connection, *args, **kwargs)
        starts.append(id(session))
        return session

    class Measured(app.Sources):
        def follow(self, value: AppSettings, again: bool = False) -> None:
            if not sources:
                sources.append(self)
            super().follow(value, again)
            if self.plan and "desktop" in kit.STATE:
                selected = kit.STATE["desktop"].settings.value
                plans.append(
                    {
                        "selected_all": selected.whole_system,
                        "selected_mic": selected.caption_mic,
                        "signed_in": self.signed_in,
                        "system": self.plan.whole_system,
                        "mic": self.plan.mic,
                        "apps": len(self.plan.apps),
                    }
                )

    def steps() -> kit.Step:
        yield from first_run()
        desktop = kit.STATE["desktop"]
        windows = kit.STATE["interface"].windows
        settings = desktop.settings
        settings.update(whole_system=True, apps=(), caption_mic=False, targets=("en",))
        yield kit.pause(1.5)
        plans.clear()
        first = len(starts)
        warnings: list[bool] = []
        desktop.connection_unstable.connect(warnings.append)
        # An app scan is asynchronous. These are the successive lists a learner
        # with Safari, Discord and Logi G Hub open could see.
        listed = [
            PlayingApp(i, name, True, SourceCategory.OTHER)
            for i, name in enumerate(("Safari", "Discord", "Logi G Hub"), 10)
        ]
        for apps in (listed, [], listed[::-1]):
            desktop.apps._take(apps)
            yield kit.pause(0.15)
        # Caption-window reconciliation can itself emit a new choice. Deliver
        # Everything from inside that notification, before the older one returns.
        for _ in range(3):

            def select_everything() -> None:
                windows.languages_changed.disconnect(select_everything)
                settings.update(whole_system=True, apps=(), caption_mic=False)

            windows.languages_changed.connect(select_everything)
            settings.update(whole_system=False, apps=())
            yield kit.pause(0.25)
        desktop.apps._take(kit.PlayerListed().playing_apps())
        transitions = []
        for system, microphone, apps_selected in (
            (True, True, ()),
            (False, True, (kit.PLAYER,)),
            (False, False, (kit.PLAYER,)),
            (True, False, ()),
        ):
            # The new caption window restores its own "Show my speech here"
            # preference. Toggle the mic after selecting the source, as on Home.
            settings.update(whole_system=system, apps=apps_selected)
            yield kit.pause(0.2)
            desktop.caption_mic.setChecked(microphone)
            yield kit.pause(0.4)
            plan = sources[0].plan
            transitions.append(
                bool(
                    plan
                    and plan.whole_system == system
                    and plan.mic == microphone
                    and len(plan.apps) == len(apps_selected)
                )
            )
        yield kit.pause(1)
        stale = [
            p for p in plans if p["signed_in"] and p["selected_all"] and not p["system"]
        ]
        expected = [p for p in plans if p["signed_in"] and p["selected_all"]]
        facts = {
            "plans": plans,
            "intentional_source_transitions": transitions,
            "unstable_warnings": warnings.count(True),
            "extra_listening_sessions": len(starts) - first,
            "signed_in_system_checks": len(expected),
            "stale_plans": len(stale),
            "final_system": bool(
                sources and sources[0].plan and sources[0].plan.whole_system
            ),
        }
        kit.check(
            "whole-system selection survives app list and nested source changes",
            bool(expected) and not stale and facts["final_system"],
            str(facts),
        )
        kit.check(
            "four deliberate changes apply without an unstable-connection notice",
            all(transitions) and not any(warnings),
            str(facts),
        )
        kit.check(
            "source changes retain the listening session",
            first > 0 and len(starts) == first,
            str(facts),
        )
        kit.hub().window.grab().save(str(out / "home.png"))
        (out / "capture-choice.json").write_text(
            json.dumps(facts, indent=1), encoding="utf-8"
        )

    driver = kit.Driver(120)
    driver.steps = steps()
    with (
        tempfile.TemporaryDirectory(
            prefix="capture-choice-", ignore_cleanup_errors=True
        ) as folder,
        patch.object(app, "Sources", Measured),
        patch.object(Connection, "start_listening", start),
    ):
        work = Path(folder)
        run_app(
            work,
            str(sample_dictionaries(work / "dicts")),
            driver,
            replay_mic_permission=True,
        )
        (out / "checks.json").write_bytes((work / "checks.json").read_bytes())
    return int(
        not (out / "capture-choice.json").exists()
        or any(not c["ok"] for c in kit.RESULTS["checks"])
    )


if __name__ == "__main__":
    code = main(Path(sys.argv[1]))
    sys.stdout.flush()
    os._exit(code)
