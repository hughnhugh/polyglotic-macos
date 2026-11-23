"""First-run language selection, immediate relaunch, resume at step 2,
default translate-into, Settings Restart now / Later, and lock hand-off
(polyglotic-hq 658)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore
from tests.ui.first_run_script import (
    Built,
    agree,
    back,
    closed,
    nothing_asked,
    scripted,
)

from polyglotic_desktop.adapters import relaunch
from polyglotic_desktop.core.shared import papers
from polyglotic_desktop.main import (
    NotAgreed,
    RestartForLanguage,
    apply_interface_language_choice,
    first_run,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.one_copy import CopyLock
from polyglotic_desktop.ui import interface_language, one_copy
from polyglotic_desktop.ui.language_picker import LanguagePicker
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    CaptionLook,
)
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)

AT = datetime(2026, 11, 22, 12, tzinfo=UTC)
AGREED = ConsentChoice(
    "a", AT, False, False, False, Agreement(papers.TESTER_AGREEMENT_VERSION, AT)
)


def pick_language(code: str):
    """Select `code` on `LanguagePicker` and press Continue."""

    def press(dialog: LanguagePicker) -> int:
        dialog.choose(code)
        dialog.accept()
        return 1

    return press


def never_code(typed: str) -> None:
    raise AssertionError("the code was sent")


# -- Step 1 widget: languages, keyboard, screen reader, translation note ----------


def test_language_picker_lists_all_languages_by_own_name_and_updates_note(
    qapp: QApplication,
) -> None:
    picker = LanguagePicker(interface_language.picker(), "de")
    try:
        items = [
            (
                picker.languages.item(i).data(Qt.ItemDataRole.UserRole),
                picker.languages.item(i).text(),
            )
            for i in range(picker.languages.count())
        ]
        assert items == interface_language.picker()
        assert dict(items) == interface_language.OFFERED
        assert picker.chosen() == "de"
        assert picker.windowTitle() == "Your language"
        assert picker.intro.text() == "Polyglotic will restart in this language."
        assert (
            picker.translation_note.text()
            == "Translations into Deutsch - change any time in Settings"
        )
        assert picker.languages.accessibleName() == "Your language"
        assert (
            picker.languages.accessibleDescription()
            == "Polyglotic will restart in this language."
        )
        picker.choose("ja")
        assert picker.chosen() == "ja"
        assert (
            picker.translation_note.text()
            == "Translations into 日本語 - change any time in Settings"
        )
    finally:
        picker.close()
        picker.deleteLater()


def test_language_picker_works_by_keyboard(qapp: QApplication) -> None:
    picker = LanguagePicker(interface_language.picker(), "de")
    picker.show()
    qapp.processEvents()
    try:
        before_row = picker.languages.currentRow()
        QTest.keyClick(picker.languages, Qt.Key.Key_Down)
        qapp.processEvents()
        assert picker.languages.currentRow() == before_row + 1
        expected_code, expected_name = interface_language.picker()[before_row + 1]
        assert picker.chosen() == expected_code
        assert expected_name in picker.translation_note.text()

        accepted: list[bool] = []
        picker.accepted.connect(lambda: accepted.append(True))
        QTest.keyClick(picker.languages, Qt.Key.Key_Return)
        qapp.processEvents()
        assert accepted == [True]
    finally:
        picker.close()
        picker.deleteLater()


# -- Step order, no restart when unchanged, relaunch & resume at step 2 -----------


def test_step_order_and_no_restart_when_keeping_running_language(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 1 is LanguagePicker, preselected from OS language; keeping the
    language already showing continues straight to step 2 with no restart."""
    store = MemorySettingsStore()
    built = Built()
    chosen_initially: list[str] = []

    def inspect_and_continue(dialog: LanguagePicker) -> int:
        chosen_initially.append(dialog.chosen())
        dialog.accept()
        return 1

    script = [
        ("LanguagePicker", inspect_and_continue),
        ("ConsentDialog", agree()),
        ("SignInDialog", closed),
    ]
    seen = scripted(monkeypatch, script)
    started = first_run(
        store,
        built,
        None,
        never_code,
        windows_languages=["de-DE", "en-US"],
        running_language="de",
    )
    assert chosen_initially == ["de"]
    assert seen == [
        ("LanguagePicker", False),
        ("ConsentDialog", True),
        ("SignInDialog", True),
    ]
    assert started.new
    assert store.values["interface_language"] == "de"
    assert store.values["targets"] == ["de"]
    assert store.values["first_run_step"] == "done"
    assert "targets" not in Settings(store).value.changed


def test_closing_step_1_quits_without_saving(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemorySettingsStore()
    built = Built()
    scripted(monkeypatch, [("LanguagePicker", closed)])
    with pytest.raises(NotAgreed):
        first_run(
            store,
            built,
            None,
            never_code,
            windows_languages=["en-AU"],
            running_language="en",
        )
    assert store.values == {}
    assert built.closed == [False]


def test_choosing_another_language_saves_progress_and_resumes_at_step_2(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing a different language saves it + default translate-into +
    step-2 progress and raises RestartForLanguage; the relaunched run resumes
    directly at step 2 (ConsentDialog) and finishes set-up with nothing lost."""
    store = MemorySettingsStore()
    first_built = Built()
    scripted(monkeypatch, [("LanguagePicker", pick_language("de"))])
    with pytest.raises(RestartForLanguage):
        first_run(
            store,
            first_built,
            None,
            never_code,
            windows_languages=["en-AU"],
            running_language="en",
        )
    assert first_built.closed == [False]  # learning store closed before relaunch
    assert store.values["interface_language"] == "de"
    assert store.values["targets"] == ["de"]
    assert store.values["first_run_step"] == "consent"
    # Fresh install's first window still sets itself up with translate_into="de"
    migrated = stored_windows(store.values)
    assert migrated.by_key == {} and not migrated.set_up
    assert migrated.last.translate_into == "de"

    # Relaunched process starts in German and resumes at step 2 (ConsentDialog)
    second_built = Built()
    seen = scripted(
        monkeypatch,
        [
            ("ConsentDialog", agree()),
            ("SignInDialog", closed),
        ],
    )
    started = first_run(
        store,
        second_built,
        None,
        never_code,
        windows_languages=["en-AU"],
        running_language="de",
    )
    assert seen == [("ConsentDialog", True), ("SignInDialog", True)]
    assert started.new  # still a fresh install (What's new stays quiet)
    assert started.first is not None and started.first.agreement is not None
    assert started.code_asked
    assert store.values["first_run_step"] == "done"

    # Third launch: returning learner, nothing asked
    nothing_asked(monkeypatch)
    again = first_run(
        store,
        Built(),
        AGREED,
        never_code,
        windows_languages=["en-AU"],
        running_language="de",
    )
    assert not again.new and again.first is None and not again.code_asked


def test_back_from_step_2_after_relaunch_can_change_language_again(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the learner picked the wrong language in step 1, Back from step 2
    returns to step 1 and updates both interface_language and the default
    translate-into language."""
    store = MemorySettingsStore(
        {
            "interface_language": "de",
            "first_run_step": "consent",
            "targets": ["de"],
            "changed": ["interface_language", "first_run_step"],
        }
    )
    seen = scripted(
        monkeypatch,
        [
            ("ConsentDialog", back),
            ("LanguagePicker", pick_language("ja")),
        ],
    )
    with pytest.raises(RestartForLanguage):
        first_run(
            store,
            Built(),
            None,
            never_code,
            windows_languages=["en-AU"],
            running_language="de",
        )
    assert seen == [("ConsentDialog", True), ("LanguagePicker", False)]
    assert store.values["interface_language"] == "ja"
    assert store.values["targets"] == ["ja"]
    assert store.values["first_run_step"] == "consent"


# -- Default translate-into language mapping & preservation -----------------------


@pytest.mark.parametrize(
    ("interface_code", "expected_target"),
    [
        ("de", "de"),
        ("ja", "ja"),
        ("zh_CN", "zh"),
        ("zh_TW", "zh-hant"),
        ("pt_BR", "pt"),
        ("fil", "tl"),
        ("en", "en"),
    ],
)
def test_default_translate_into_maps_interface_language(
    interface_code: str, expected_target: str
) -> None:
    store = MemorySettingsStore()
    settings = Settings(store)
    apply_interface_language_choice(settings, store.load(), interface_code)
    assert settings.value.targets == (expected_target,)
    assert "targets" not in settings.value.changed


def test_explicit_translate_into_choice_is_never_overwritten() -> None:
    # Case 1: learner explicitly changed `targets`
    store1 = MemorySettingsStore()
    s1 = Settings(store1)
    s1.update(targets=("fr",))
    assert "targets" in s1.value.changed
    apply_interface_language_choice(s1, store1.load(), "de")
    assert s1.value.targets == ("fr",)

    # Case 2: learner already has saved caption windows
    store2 = MemorySettingsStore(
        {
            STORED_KEY: {"last": {"translate_into": "es"}, "by_key": {}},
            "targets": ["es"],
        }
    )
    s2 = Settings(store2)
    apply_interface_language_choice(s2, store2.load(), "de")
    assert s2.value.targets == ("es",)


# -- Platform relaunch command building -------------------------------------------


def test_relaunch_command_per_platform() -> None:
    # Windows installed (Velopack current/Polyglotic.exe)
    win_exe = r"C:\Users\learner\AppData\Local\Polyglotic\current\Polyglotic.exe"
    assert relaunch.relaunch_command(
        ["--data", r"C:\tmp\d", "--in-tray"],
        frozen=True,
        executable=win_exe,
        system="win32",
        environ={},
    ) == [win_exe, "--data", r"C:\tmp\d"]

    # Windows from source
    py_exe = r"C:\repo\.venv\Scripts\python.exe"
    assert relaunch.relaunch_command(
        ["--server", "http://127.0.0.1:8217", "--lock"],
        frozen=False,
        executable=py_exe,
        system="win32",
        environ={},
    ) == [py_exe, "-m", "polyglotic_desktop.main", "--server", "http://127.0.0.1:8217"]

    # Linux AppImage
    assert relaunch.relaunch_command(
        ["--data", "/tmp/d", "--in-tray"],
        frozen=True,
        executable="/tmp/.mount_Poly/usr/bin/Polyglotic",
        system="linux",
        environ={"APPIMAGE": "/home/learner/Applications/Polyglotic.AppImage"},
    ) == ["/home/learner/Applications/Polyglotic.AppImage", "--data", "/tmp/d"]

    # Linux from source (no $APPIMAGE)
    assert relaunch.relaunch_command(
        ["--data", "/tmp/d"],
        frozen=False,
        executable="/usr/bin/python3",
        system="linux",
        environ={},
    ) == ["/usr/bin/python3", "-m", "polyglotic_desktop.main", "--data", "/tmp/d"]

    # macOS app bundle
    assert relaunch.relaunch_command(
        ["--data", "/tmp/d"],
        frozen=True,
        executable="/Applications/Polyglotic.app/Contents/MacOS/Polyglotic",
        system="darwin",
        environ={},
    ) == [
        "/usr/bin/open",
        "-n",
        "/Applications/Polyglotic.app",
        "--args",
        "--data",
        "/tmp/d",
    ]
    assert relaunch.relaunch_command(
        [],
        frozen=True,
        executable="/Applications/Polyglotic.app/Contents/MacOS/Polyglotic",
        system="darwin",
        environ={},
    ) == ["/usr/bin/open", "-n", "/Applications/Polyglotic.app"]

    # Velopack hook flags are stripped cleanly
    assert relaunch.passthrough_args(
        ["--veloapp-updated", "0.1.10", "--data", "x", "--pause"]
    ) == ["--data", "x"]


def test_relaunch_invokes_popen_and_handles_oserror() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> None:
        calls.append((cmd, kwargs))

    ok = relaunch.relaunch(
        ["--data", "/tmp/d"],
        frozen=True,
        executable="/app/Polyglotic",
        system="linux",
        environ={"APPIMAGE": "/home/u/Polyglotic.AppImage"},
        popen=fake_popen,
    )
    assert ok
    assert calls[0][0] == ["/home/u/Polyglotic.AppImage", "--data", "/tmp/d"]
    assert calls[0][1]["start_new_session"] is True
    assert calls[0][1]["close_fds"] is True

    def broken_popen(cmd: list[str], **kwargs: object) -> None:
        raise OSError("missing binary")

    assert not relaunch.relaunch(
        frozen=True,
        executable="/missing",
        system="linux",
        environ={},
        popen=broken_popen,
    )


# -- Settings page: Restart now and Later -----------------------------------------


def test_settings_language_picker_offers_restart_now_and_later(
    qapp: QApplication,
) -> None:
    tell_us = QAction("Tell us")
    page = SettingsPage(
        [("margin", "Margin")],
        tell_us,
        [("de", "Deutsch"), ("en", "English"), ("ja", "日本語")],
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )
    try:
        page.show_running_language("en", "en")
        page.show_interface_language("")
        page.resize(1200, 700)
        page.show()
        qapp.processEvents()

        assert not page.language_restart.isVisible()
        assert not page.language_defer.isVisible()
        assert not page.language_later.isVisible()

        # Picking the same effective language ("en" while running "en") needs no restart
        page.language_picker.setCurrentIndex(page.language_picker.findData("en"))
        qapp.processEvents()
        assert not page.language_restart.isVisible()
        assert not page.language_defer.isVisible()

        # Picking a different language shows Restart now and Later
        page.language_picker.setCurrentIndex(page.language_picker.findData("de"))
        qapp.processEvents()
        assert page.language_restart.isVisible()
        assert page.language_defer.isVisible()
        assert page.language_later.isVisible()

        # Clicking Later hides the buttons and leaves "From the next start"
        page.language_defer.click()
        qapp.processEvents()
        assert not page.language_restart.isVisible()
        assert not page.language_defer.isVisible()
        assert page.language_later.isVisible()

        # Picking another different language offers Restart now again
        restarted: list[bool] = []
        page.language_restart_wanted.connect(lambda: restarted.append(True))
        page.language_picker.setCurrentIndex(page.language_picker.findData("ja"))
        qapp.processEvents()
        assert page.language_restart.isVisible()
        page.language_restart.click()
        assert restarted == [True]

        # Switching back to "Like this PC" (which resolves to running "en") hides all
        page.language_picker.setCurrentIndex(0)
        qapp.processEvents()
        assert not page.language_restart.isVisible()
        assert not page.language_defer.isVisible()
        assert not page.language_later.isVisible()
    finally:
        page.close()
        page.deleteLater()


# -- Single-instance lock hand-off ------------------------------------------------


def test_lock_handoff_lets_relaunched_instance_start(qapp: QApplication) -> None:
    """When the old copy closes SecondStarts and releases its CopyLock (even
    slightly after the new copy begins), the new copy acquires the lock and
    starts rather than exiting."""
    name = f"Polyglotic-test-658-{uuid.uuid4().hex}"
    old_lock: CopyLock
    new_lock: CopyLock
    if sys.platform == "win32":
        from polyglotic_desktop.platform.windows.one_copy import (
            NamedMutex,
            let_to_front,
        )

        old_lock = NamedMutex(name)
        new_lock = NamedMutex(name)
    elif sys.platform == "darwin":
        from polyglotic_desktop.platform.macos.one_copy import FileLock, let_to_front

        old_lock = FileLock(name)
        new_lock = FileLock(name)
    else:
        from polyglotic_desktop.platform.linux.one_copy import FileLock, let_to_front

        old_lock = FileLock(name)
        new_lock = FileLock(name)

    assert old_lock.take()
    server = one_copy.SecondStarts(name, qapp)
    assert server.listening
    # Step 1 of relaunch: stop answering second starts before releasing lock
    server.close()

    def release_shortly() -> None:
        time.sleep(0.35)
        old_lock.release()

    releaser = threading.Thread(target=release_shortly, daemon=True)
    releaser.start()
    try:
        outcome = one_copy.start(
            new_lock.take,
            lambda left: one_copy.ask_to_show(name, let_to_front, left),
            show=True,
            wait_sec=5.0,
        )
        assert outcome is one_copy.Start.RUNS
    finally:
        releaser.join(timeout=5.0)
        new_lock.release()
        old_lock.release()
        server.deleteLater()


@pytest.mark.windows_only
def test_lock_handoff_across_real_subprocesses(tmp_path: Path) -> None:
    """A child process started right as the parent releases its Windows
    NamedMutex acquires the lock and exits 0."""
    name = f"Polyglotic-test-658-proc-{uuid.uuid4().hex}"
    from polyglotic_desktop.platform.windows.one_copy import NamedMutex

    parent_lock = NamedMutex(name)
    assert parent_lock.take()
    child_script = (
        "import sys\n"
        "from polyglotic_desktop.platform.windows.one_copy import NamedMutex, let_to_front\n"
        "from polyglotic_desktop.ui import one_copy\n"
        "name = sys.argv[1]\n"
        "lock = NamedMutex(name)\n"
        "started = one_copy.start(\n"
        "    lock.take,\n"
        "    lambda left: one_copy.ask_to_show(name, let_to_front, left),\n"
        "    show=True,\n"
        "    wait_sec=5.0,\n"
        ")\n"
        "lock.release()\n"
        "assert started is one_copy.Start.RUNS, started\n"
        "print('ACQUIRED')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", child_script, name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    try:
        time.sleep(0.3)
        parent_lock.release()
        out, _ = proc.communicate(timeout=30)
        assert proc.returncode == 0, out
        assert "ACQUIRED" in out
    finally:
        parent_lock.release()
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
