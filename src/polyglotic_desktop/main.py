"""The one place that wires everything together.

`main` builds the interface (`ui.app.DesktopApp`) on the learner's data
and dictionary, the speech pipeline and its sources from the user's
settings, and the connection to the server (`connection.client.Connection`:
the listening session, and sync sessions for what waits in the outbox),
then connects them:
- **the session's listener calls arrive on the session's own thread**
  (decision 0012): `QtListener` hands caption updates to the caption feed,
  which queues them to the Qt thread, and the session's state to Home
  through a queued signal; the pace hint goes to the pipeline, which is
  thread-safe;
- **the settings**, as they change: the listening settings to the session;
  the source choice (the apps picked, by name, or everything the PC
  plays; the mic) starts and stops the sources that changed; the
  live-update interval and Pause to the timing rules;
- **learning data** (project 028): Learning's events go to the
  `DataExchange` (kept in the outbox until the server has them); statuses
  and saved words from the server - of the learner's dictionary only, for
  an account learning both languages - come back on a session's thread
  and are applied on the Qt thread without being sent back (`QtExchange`);
  finished days' exposure counts are handed over at start and hourly -
  kept only with their consent;
- **hotkeys**: Ctrl+Alt+L, P and H (lock, pause, hide) registered with
  Windows on a thread of their own; each press goes to the interface's
  thread;
- **feedback** (project 053): "Report a problem" and "Suggest something"
  open the form - and, if the app hit an error nothing caught last time
  (`CrashLog` leaves `crashed.json` in the data folder), Home offers once
  to send a report with the log; a report is kept in the data folder's
  `feedback` folder
  first, then sent on a thread of its own (`FeedbackSender`) - again at
  start, after signing in and every 10 minutes while any waits; signing
  out forgets them. What became of it shows on Home.
- **first run** (`first_run`, decisions 0054 and 0085): one run of screens
  before anything is built on their answers, each after the first with
  Back (polyglotic-hq 250) - no language (293: the learner's dictionary
  and learning data are the language learned's, chosen on Learning, or a
  guess from Windows' languages until then; a change applies at the next
  start) and no level (estimated at a middle one until set: Home's line
  asks), the consent screen with its yes to the
  tester agreement; without it the app quits, and new words of the
  agreement ask again at start (polyglotic-hq 185) - then signing in
  with an invite code (later starts signed out ask it over the window);
  the Account page signs in and out, changes what's shared, and deletes
  learning data (here too only if ticked).

- **the interface** (decisions 0031 and 0032): the new main window
  (`Hub`: Home, Words, Account, Settings, Help), a caption window per app
  captioned (at most 3) or one joined window, a transcript per app, and
  today's tray and dialogs. Each window's language - or Original only -
  goes to the server as its source's own (`listening_settings`); the mic
  is captured only while a window shows my speech; only the first 3 apps
  picked are captured. A window's settings popover never has the focus,
  so Esc or a click elsewhere reaches it through Windows' key state
  (`ports.system.KeyState`), read, not taken.

- **the OS** (decision 0038): its adapters - audio, the app list, the
  device token's store, hotkeys, key state, staying on top, the taskbar's
  look, the OS's version, the data folder - picked in one place,
  `os_adapters`, and imported only there; nothing else imports
  `platform.windows` (import-linter's `os-in-one-place`).

- **updates** (decision 0017): the installer's start-up hooks before
  anything else; then a look for an update on a thread of its own, before
  the interface is built, and every few hours; what each look found goes
  to Home, the tray and Settings (`UpdateShown`: a downloaded update
  offered, with Restart now - polyglotic-hq 299); downloaded updates apply at
  the next start; the channel `welcome` names is followed; the server's
  "update required" goes straight to the updater.

    uv run python -m polyglotic_desktop.main --server http://127.0.0.1:8217

It logs to `logs/polyglotic.log` in the data folder (from source, to the
console as well; installed, it has none) - an exception nothing caught
too, by its type and place (`CrashLog`), with a plain box if it stops the
app starting. `--check-install REPORT` builds everything without
showing, capturing or connecting, and writes what it found (the release
build runs it on the packed app). Logs states only - never caption text,
audio or settings.

What the window doesn't need is imported after its first paint (project
108's fix f; polyglotic-hq project 136): the connection (pydantic,
websockets), speech detection (numpy, onnxruntime) and the signed feed's
libraries took about 0.3 s of the 0.55 s of imports from source. Their
names are typed under `TYPE_CHECKING` and imported where first used;
`tests/test_start_imports.py` keeps them out of `import main`.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import importlib.util
import json
import logging
import logging.handlers
import sys
import tempfile
import threading
import time
import traceback
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import urlsplit

import shiboken6
from PySide6.QtCore import (
    QEvent,
    QLocale,
    QObject,
    Qt,
    QTimer,
    QTranslator,
    Signal,
    Slot,
    qVersion,
)
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from polyglotic_desktop.adapters.anki_package import GenankiDeckWriter
from polyglotic_desktop.adapters.app_log import read_log
from polyglotic_desktop.adapters.background_learning import BackgroundLearningStore
from polyglotic_desktop.adapters.background_outbox import BackgroundOutbox
from polyglotic_desktop.adapters.feedback_files import FeedbackFolder
from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.adapters.json_settings import (
    JsonSettingsStore,
    ReadOnlySettings,
)
from polyglotic_desktop.adapters.problem_report_files import ProblemReportFolder
from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.adapters.sqlite_dictionary import FORMAT as DICTIONARY_FORMAT
from polyglotic_desktop.adapters.sqlite_dictionary import (
    DictionaryDamaged,
    DictionaryFormatError,
    GuardedDictionary,
    SqliteDictionary,
)
from polyglotic_desktop.adapters.sqlite_learning import (
    LearningStoreFormatError,
    SqliteLearningStore,
    delete_learning_data_at,
    open_learning_store,
    read_level_file,
    set_aside_in,
    unreadable_in,
)
from polyglotic_desktop.adapters.sqlite_outbox import open_outbox
from polyglotic_desktop.adapters.velopack_updates import (
    VelopackUpdater,
    run_installer_hooks,
)
from polyglotic_desktop.connection.app import AppInfo, this_release
from polyglotic_desktop.core.learning.first_known import (
    Before,
    QuickMarks,
    marks_more,
)
from polyglotic_desktop.core.learning.languages import (
    LearningLanguages,
    Tier,
    learned_code,
    open_beside,
    packs_beside,
    starting_language,
    tier_of,
)
from polyglotic_desktop.core.learning.levels import (
    UNKNOWN_LEVEL_LINKS_FROM,
    KnownLine,
)
from polyglotic_desktop.core.learning.load import LoadRules
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    EntryText,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.basic import absent as absent_dictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
    SCHEMES,
)
from polyglotic_desktop.core.lexicon.meanings import short_meaning
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem
from polyglotic_desktop.core.lexicon.pack_download import Step as PackStep
from polyglotic_desktop.core.lexicon.packs import (
    InstalledPack,
    PackOffer,
    Reader,
    best_offer,
    needs_newer_app,
    update_for,
)
from polyglotic_desktop.core.lexicon.vietnamese import VietnameseSplit
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
    mandarin_written,
)
from polyglotic_desktop.core.listening.delays import CAPTION_LOG
from polyglotic_desktop.core.listening.display import (
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.listening.maintenance import (
    SOON,
    Maintenance,
    soon,
)
from polyglotic_desktop.core.listening.maintenance import (
    from_stored as maintenance_from_stored,
)
from polyglotic_desktop.core.listening.maintenance import (
    stored as maintenance_stored,
)
from polyglotic_desktop.core.listening.problem_report import (
    SpeechPart,
    captions_as_shown,
    speech_by_source,
)
from polyglotic_desktop.core.listening.recheck import (
    RecheckResult,
)
from polyglotic_desktop.core.listening.settings import (
    ListeningSettings,
    agreed_language,
)
from polyglotic_desktop.core.listening.sources import (
    DICTATION,
    EVERYTHING_ELSE,
    MIC,
    SAMPLE,
    WHOLE_SYSTEM,
    Capture,
    Source,
    SourceId,
    capture_of,
    known_app_id,
)
from polyglotic_desktop.core.listening.summary import SessionAction
from polyglotic_desktop.core.listening.timing import (
    VAD_SAMPLE_RATE,
    CaptionMode,
    CaptionTiming,
    Decision,
    TranscriptionRequest,
)
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.releases.notes import (
    plain,
    sections,
    seen_at_start,
    unseen,
    version_order,
)
from polyglotic_desktop.core.releases.updates import (
    CHECK_EVERY_HOURS,
    Found,
    RestartOffer,
    UpdateNow,
    Updates,
    whats_new,
)
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    WordStatus,
)
from polyglotic_desktop.perf import start_parts
from polyglotic_desktop.perf.watchdog import Watchdog
from polyglotic_desktop.platform.sample import SampleCapture, SoundOut, sample_file
from polyglotic_desktop.ports.capture import (
    AppCaptureSupport,
    AppCaptureTrial,
    AppList,
    AudioCapture,
    CommonApp,
    PlayingApp,
    SoundDevices,
    SourceCategory,
    TrialOutcome,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.credentials import CredentialStore
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.feedback import Report, ReportKind, WaitingReports
from polyglotic_desktop.ports.one_copy import CopyLock, LetToFront
from polyglotic_desktop.ports.problem_reports import ProblemReport, ReportedSpeech
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ports.startup import IN_TRAY, StartWithWindows
from polyglotic_desktop.ports.system import (
    DataFolder,
    ErrorBox,
    ForegroundWatch,
    HoldKey,
    Hotkeys,
    KeyboardWindow,
    KeyState,
    LaunchClock,
    LightTaskbar,
    OnTop,
    OsVersion,
    StorePackage,
    TaskbarIdentity,
    Translocation,
    TypeText,
)
from polyglotic_desktop.ports.updates import Update
from polyglotic_desktop.ports.word_split import WordSplit
from polyglotic_desktop.ui import (
    icons,
    interface_language,
    move_to_applications,
    one_copy,
    theme,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.apps_with_sound import AppsWithSound
from polyglotic_desktop.ui.consent import ConsentDialog, agreement_needed
from polyglotic_desktop.ui.delete_learning import DeleteLearningDialog
from polyglotic_desktop.ui.feedback import FeedbackDialog
from polyglotic_desktop.ui.first_run import BACK, Answer, Step, asked
from polyglotic_desktop.ui.first_run import run as run_first_run
from polyglotic_desktop.ui.learning import LearningTools, PlacedAhead
from polyglotic_desktop.ui.level_picker import LevelPicker
from polyglotic_desktop.ui.problem_report import (
    OneReportWindow,
    Part,
    ProblemReportDialog,
    captions_detail,
    captions_look,
    mic_name,
    part_labels,
    speech_detail,
    speech_label,
    speech_look,
)
from polyglotic_desktop.ui.settings import (
    MAX_SOURCE_NAME,
    SOURCE_KEY_EVERYTHING_ELSE,
    SOURCE_KEY_MIC,
    SOURCE_KEY_SAMPLE,
    SOURCE_KEY_SYSTEM,
    AppSettings,
    Settings,
    added_language_changes,
    introductions_changes,
    language_choices_changes,
    learning_changes,
    load_rules_changes,
    reset_point_changes,
)
from polyglotic_desktop.ui.sign_in import (
    Redeem,
    SignInDialog,
    SignInFailed,
    SignInProblem,
    confirm_sign_out,
)
from polyglotic_desktop.ui.widgets import TextDialog
from polyglotic_desktop.ui_next import maintenance as maintenance_words
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.account_page import AccountPage as NextAccountPage
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.first_window import made_ahead
from polyglotic_desktop.ui_next.fonts_ahead import FontsAhead
from polyglotic_desktop.ui_next.help_page import HelpPage as NextHelpPage
from polyglotic_desktop.ui_next.home import WHATS_NEW_ON_HOME, HomePage, hotkey_works
from polyglotic_desktop.ui_next.languages import (
    learned_name,
    own_targets,
    taken_off_note,
)
from polyglotic_desktop.ui_next.learning_page import LearningPage, reset_question
from polyglotic_desktop.ui_next.main_window import MainWindow as NextMainWindow
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.pack_row import (
    failed_notice,
    ready_notice,
    remove_question,
)
from polyglotic_desktop.ui_next.plan import plan_text
from polyglotic_desktop.ui_next.save_folder import SaveFolder
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views import known_words
from polyglotic_desktop.ui_next.views.app_choices import AppChoice, app_choices
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import (
    LIMIT,
    CaptionLook,
    Notice,
    WindowChoices,
    minutes_used_up,
    slowed_now,
)
from polyglotic_desktop.ui_next.views.home import (
    AppRow,
    AppStatus,
    HomeState,
    ListeningState,
    Picker,
    PickerView,
    addable,
    every_window_paused,
    offer_start_with_windows,
    sample_state,
)
from polyglotic_desktop.ui_next.views.lab import CaptionLab
from polyglotic_desktop.ui_next.views.learning import (
    InstalledPackLine,
    PackLine,
)
from polyglotic_desktop.ui_next.views.learning import cards as learning_cards
from polyglotic_desktop.ui_next.views.load import load_view
from polyglotic_desktop.ui_next.views.lookup import WordAt
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.plan import PlanLine, PlanShown, plan_line
from polyglotic_desktop.ui_next.views.sound import Sound, SoundView
from polyglotic_desktop.ui_next.views.transcript import TranscriptLength
from polyglotic_desktop.ui_next.views.words import level_line
from polyglotic_desktop.ui_next.word_speech import WordSpeech
from polyglotic_desktop.ui_next.words_page import OpenLanguages, WordsPage

if TYPE_CHECKING:  # imported where first used, after the window's first paint
    from polyglotic_desktop.adapters.pack_downloads import PackDeliveries
    from polyglotic_desktop.connection import protocol
    from polyglotic_desktop.connection.client import Connection
    from polyglotic_desktop.connection.exchange import DataExchange
    from polyglotic_desktop.connection.feedback import Outcome
    from polyglotic_desktop.connection.protocol import Os
    from polyglotic_desktop.connection.session import Status
    from polyglotic_desktop.connection.sign_in import RedeemResult
    from polyglotic_desktop.core.lexicon.traditional import TraditionalChinese
    from polyglotic_desktop.platform.audio_buffer import AudioBuffer
    from polyglotic_desktop.platform.speaking import SpeakerThread
    from polyglotic_desktop.platform.speech_detection import Audio
    from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline

log = logging.getLogger(__name__)

APP_CHECK_MS = 5000  # how often to look for a chosen app that isn't open
HEARING_MS = 100  # how often the listening mark asks whose speech is under way
EXPOSURE_DAYS_MS = 3_600_000  # how often to hand over finished days' exposures
VOICES_AFTER_START_MS = 2000  # Windows' voices looked for after the start (286)

LOG_BYTES, LOG_FILES = 1_000_000, 3  # installed: the log file, rotated
CAPTION_LOG_FILE = "captions.log"
CAPTION_LOG_BYTES, CAPTION_LOG_FILES = 2_000_000, 4
"""The caption log: 10 MB at most - about 100,000 lines, some hours of
busy listening (ids, sizes and times; never caption text)."""

CRASH_NOTE = "crashed.json"  # an error nothing caught, for the next start


def moved_to_applications(
    place: Translocation | None,
    settings: Settings,
    offer: Callable[[Translocation], Path | None] = move_to_applications.offer,
) -> bool:
    """On a Mac run from macOS's temporary copy (App Translocation), where
    Velopack can't update it: "Move Polyglotic to Applications?", asked once
    whatever the answer (decision 0205). True when it moved and opens again
    from there once this copy ends - `main` ends it."""
    if place is None or settings.value.applications_offered or not place.translocated():
        return False
    log.info("run from macOS's temporary copy: offering to move to Applications")
    settings.update(applications_offered=True)
    moved = offer(place)
    if moved is None:
        return False
    place.reopen(moved)
    log.info("moved to Applications: opening it there")
    return True


def installed() -> bool:
    """Running as the packed app (PyInstaller), not from source."""
    return bool(getattr(sys, "frozen", False))


def beside_the_app(executable: str | Path | None = None) -> Path:
    """Where the build puts its own files - the dictionaries, the notices,
    the release notes, the licences (tools/package/build.py): beside the
    packed app's `Polyglotic.exe` on Windows; inside a macOS app's
    `Contents/Resources`, since `Contents/MacOS` holds only code and its
    signature seals Resources (polyglotic-hq 410). `executable`: the packed
    app's (`sys.executable` unless given)."""
    path = Path(executable if executable is not None else sys.executable)
    folder = path.parent
    if folder.name == "MacOS" and folder.parent.name == "Contents":
        return folder.parent / "Resources"
    return folder


def third_party_notices() -> str | None:
    """THIRD_PARTY_NOTICES.md, beside the packed app's `Polyglotic.exe`
    (tools/package/build.py puts it there); None from source or if it's
    missing."""
    if not installed():
        return None
    try:
        return (beside_the_app() / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    except OSError:
        return None


def release_notes() -> str:
    """RELEASE-NOTES.md, beside the packed app's `Polyglotic.exe`
    (tools/package/build.py puts it there) or, from source, the repo's;
    "" if it's missing (polyglotic-hq 345)."""
    folder = beside_the_app() if installed() else Path(__file__).parents[2]
    try:
        return (folder / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def show_whats_new(
    hub: Hub, settings: Settings, version: str, fresh: bool, english: bool
) -> None:
    """What's new after an update (polyglotic-hq 345, decision 0137): the
    notes of each version since the last whose notes were seen, on Home
    until Close - the newest in a few lines, the others named and in
    Help - and every version's in Help. A fresh install's first run shows
    none (`fresh`); `english`: the interface is, else Home and Help say
    the notes are in English."""
    seen = seen_at_start(settings.value.whats_new_seen, version, fresh)
    if seen != settings.value.whats_new_seen:
        settings.update(whats_new_seen=seen)
    notes = sections(release_notes())
    now = version_order(version)
    hub.help.show_whats_new(
        [
            (each.version, plain(each.markdown))
            for each in notes
            if now is None or (version_order(each.version) or now) <= now
        ],
        in_english=not english,
    )
    hub.home.whats_new_closed.connect(lambda: settings.update(whats_new_seen=version))
    hub.home.whats_new_wanted.connect(lambda: hub.window.go_to("help"))
    hub.home.whats_new_wanted.connect(hub.help.open_whats_new)
    shown = unseen(seen, version, notes)
    if not shown:
        return
    log.info("what's new: %s on Home", ", ".join(n.version for n in shown))
    hub.home.show_whats_new(
        shown[0].version,
        whats_new(shown[0].markdown, lines=WHATS_NEW_ON_HOME),
        [each.version for each in shown[1:]],
        in_english=not english,
    )


def dictionaries_folder() -> Path:
    """The dictionary files: beside the packed app's `Polyglotic.exe`, as
    separate, unlocked files (decision 0009); from source, where
    `tools.dictionaries.build` writes them."""
    if installed():
        return beside_the_app() / "dictionaries"
    return Path("build/dictionaries")


TASKBAR_ID = "Polyglotic.Desktop"
"""The ID Windows' taskbar knows the app by from source (its AppUserModelID:
windows grouped, pinned and drawn under it), not `python.exe`'s. Installed,
the installer's stands (decision 0051). Fixed once testers pin the app: a
changed ID leaves their pins behind."""


SERVER = "https://api.polyglotic.io"
"""The live server, built into every installed copy (the domain since
2026-11-09; the tunnel's address since 2026-11-11, polyglotic-hq DECISIONS
#108). Changed only by a pull request, never by the build (decision
0015); `--server` overrides it for development, and for the PC the server
runs on."""

CREDENTIALS_ELSEWHERE = "Polyglotic/device@{server}"
"""The Credential Manager entry for a server other than `SERVER` (a test
server, from source): one per server, so signing in to one never replaces
another's sign-in (polyglotic-hq 288: on 2026-11-11 the from-source copy's
test-server token sat in the installed copy's entry, which the live server
refused, and the installed copy asked for a code). `SERVER`'s is the
adapter's own, `Polyglotic/device`, as every installed copy has it."""


def credentials_entry(server: str, named: str | None) -> str | None:
    """The device token's entry: `named` (`--credentials`) if given; None -
    the app's own - for `SERVER`; else `CREDENTIALS_ELSEWHERE` for this
    server's host and port."""
    if named:
        return named
    if server.rstrip("/") == SERVER:
        return None
    return CREDENTIALS_ELSEWHERE.format(server=urlsplit(server).netloc or server)


UPDATES = "https://updates.polyglotic.io/"
"""The update feed, built into every installed copy (decision 0015). Not
served yet on 2026-11-11: the first friends' builds find no feed and stay
as installed. `--updates` overrides it to try updates from a folder on
this PC."""
UPDATES_AT_EXIT_SEC = 5.0  # at quit, how long to wait for the updater
RFC8032_TEST_1 = (  # key, signature of the empty message (RFC 8032, 7.1)
    "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
    (
        b"5VZDAMNgrHKQhuLMgG6CioSHfx645dl02HPgZSJJAVVfuIIVkKM7rMYeOXAc+bRr0lv18Fl"
        b"bviRlUUFDjnoQCw=="
    ),
)

FEED_KEYS: tuple[str, ...] = ("T9JEreM5nPkehQOMIfPbjUz1+UoZ73pUJ7rslb72xBs=",)
"""The public keys (Ed25519, base64) the update feed must be signed with
(decision 0019) - on since 0.1.1, with the key the user made on 2026-11-11
(polyglotic-hq DECISIONS.md #97). Every feed and package is checked first,
and an unsigned or tampered one is refused. Empty would turn it off:
Velopack reads the feed as it is (0.1.0 did). Up to two keys while one replaces
the other. Changed only by a pull request, like the addresses."""


def updater(feed: str) -> VelopackUpdater:
    """The installer's updates from `feed`, checked against `FEED_KEYS` when
    it's the built-in feed and they're set. Checked packages are kept beside
    `current` in the install folder (Velopack's place for files that may go
    with an uninstall) - on a Mac, outside the app (`verified_feed_folder`)."""
    release = this_release()
    signed = feed == UPDATES and bool(FEED_KEYS)
    return VelopackUpdater(
        feed,
        FEED_KEYS if signed else (),
        release.channel,
        release.version,
        verified_feed_folder(),
        open_url=_open_url,
    )


def verified_feed_folder(
    executable: str | Path | None = None, home: Path | None = None
) -> Path:
    """Where the signed feed and its checked package wait for Velopack
    (decision 0019): beside `current` in Velopack's install folder on
    Windows (`%LOCALAPPDATA%/Polyglotic/verified-feed`); on a Mac, in
    `~/Library/Caches/Polyglotic/verified-feed` - never inside the app
    bundle, whose signature seals everything in it, so a file written there
    would break the signature macOS keeps the learner's permissions under
    (polyglotic-hq 430, decision 0196). `executable`: the packed app's
    (`sys.executable` unless given)."""
    path = Path(executable if executable is not None else sys.executable)
    if path.parent.name == "MacOS" and path.parent.parent.name == "Contents":
        return (
            (home or Path.home())
            / "Library"
            / "Caches"
            / "Polyglotic"
            / "verified-feed"
        )
    return path.parent.parent / "verified-feed"


def pack_storage(
    packs_from: str, packs_keys: Sequence[str], packed: bool
) -> tuple[str, tuple[str, ...]]:
    """Where the dictionary packs come from, and the keys their list may be
    signed with (decision 0122): `PACKS` and `FEED_KEYS` - and from source,
    a developer's stand-in (`--packs-from`) and keys (`--packs-key`) too. An
    installed copy (`packed`) ignores both switches and says so: a shortcut
    can't send it to another host or make it trust another key."""
    if packed:
        if packs_from != PACKS or packs_keys:
            log.warning("--packs-from and --packs-key are ignored in an installed copy")
        return PACKS, FEED_KEYS
    return packs_from, (*FEED_KEYS, *packs_keys)


def _open_pack_url(request: Any, timeout: float) -> Any:
    """A dictionary pack's files over connection.tls (decision 0104), held to
    the storage's own host: a redirect to another, or off `https`, is
    refused before it's followed (decision 0122)."""
    from polyglotic_desktop.connection import tls

    return tls.urlopen(request, timeout, same_host=True)


def _open_url(request: Any, timeout: float) -> Any:
    """The update feed's files over connection.tls (decision 0104), imported
    only when the feed is read: the updater is built before the window (136)."""
    from polyglotic_desktop.connection import tls

    return tls.urlopen(request, timeout)


class NoOsAdapters(RuntimeError):
    """This OS has no adapters yet: what's missing is in the message."""


@dataclass(frozen=True)
class OsAdapters:
    """The OS's own pieces, as `main` wires them - each a port's
    implementation (`ports/capture.py`, `ports/credentials.py`,
    `ports/system.py`), picked by `os_adapters` (decision 0038)."""

    app_list: Callable[[], AppList]
    app_capture_support: Callable[[], AppCaptureSupport]
    """Whether this Windows captures one app alone: yes, try, or no
    (decision 0076)."""
    app_capture_trial: Callable[[], AppCaptureTrial]
    app_capture: Callable[[int, str, AppCaptureTrial | None], AudioCapture]
    everything_else_capture: Callable[[int, AppCaptureTrial | None], AudioCapture]
    windows_build: Callable[[], str]
    """Windows' build and update (`19045.5131`), for the log's line on
    capturing apps one by one (decision 0076)."""
    system_capture: Callable[[str | None], AudioCapture]
    mic_capture: Callable[[str | None], AudioCapture]
    """Everything an output plays, and a mic: the device chosen by its id
    (None: Windows' default, also while the one chosen is unplugged)."""
    outputs_playing: Callable[[], int | None]
    """How many outputs play sound now (None: Windows can't say), for the
    caption log's line on each mic-bleed check (polyglotic-hq 290)."""
    credentials: Callable[[str | None], CredentialStore]
    """The device token's store: a named one (`credentials_entry`), else the
    app's."""
    hotkeys: Callable[[Mapping[str, Callable[[], None]]], Hotkeys]
    sound_out: Callable[[], SoundOut]
    """Plays the sample aloud (176)."""
    speaker: Callable[[], SpeakerThread] | None
    """Says a looked-up word aloud in one of the OS's own voices (polyglotic-hq
    286, decision 0077): the `Speaker` port on a thread of its own. None
    where the OS has none yet (macOS, 409): the word card offers no voice."""
    start_at_sign_in: Callable[[str], StartWithWindows] | None
    """The app, at this executable, starting when the learner signs in (176).
    None where the OS has none yet (macOS, 409): Home never offers it."""
    copy_lock: Callable[[str], CopyLock]
    """The lock the one copy for this name holds (polyglotic-hq 310)."""
    let_to_front: LetToFront
    keys: KeyState
    on_top: Callable[[], OnTop]
    foreground_watch: Callable[[Callable[[], None]], ForegroundWatch]
    light_taskbar: LightTaskbar
    taskbar_identity: TaskbarIdentity
    """The app's ID on the taskbar (decision 0051)."""
    store_package: StorePackage
    """The Microsoft Store's package this copy runs from, if it does
    (decision 0056)."""
    os_name: Callable[[], Os]
    os_version: OsVersion
    data_folder: DataFolder
    show_error: ErrorBox
    seconds_since_launch: LaunchClock
    read_fonts: Callable[[], bool]
    """Has Qt read the OS's fonts now, on the calling thread, without
    holding Python's interpreter (`ui_next.fonts_ahead`, decision 0112)."""
    make_native_window: Callable[[int], bool]
    """Gives the QWidget at an address its window of the OS's, on the
    calling thread, without holding the interpreter
    (`ui_next.first_window`, decision 0113)."""
    hold_key: Callable[
        [str, Callable[[], None], Callable[[], None], Callable[[], None]], HoldKey
    ]
    """Dictation's key, held (polyglotic-hq 283, 289): the key as kept, and
    what to call when it goes down, comes up, and is part of a shortcut."""
    type_text: TypeText
    keyboard_window: KeyboardWindow
    common_apps: tuple[CommonApp, ...] = ()
    """Browsers and the main apps a caption window lists before they play."""
    sound_devices: Callable[[], SoundDevices] = SoundDevices
    """The speakers and mics plugged in, for Home's Sound (polyglotic-hq 372)."""
    metered: Callable[[], bool] = lambda: False
    """Whether the OS calls the connection metered: a dictionary pack's
    download asks first on one (decision 0122), and an update found waits
    for the learner (polyglotic-hq 345)."""
    translocation: Callable[[], Translocation] | None = None
    """Whether macOS runs the app from a temporary copy it can't update
    itself in, and the move to Applications (polyglotic-hq 433). None where
    an OS has no such thing (Windows)."""


def os_adapters(system: str = sys.platform) -> OsAdapters:
    """The adapters of the OS this runs on (`system`: `sys.platform`'s
    name) - the one place that picks them, imported only now, so the rest
    of the app (and its tests) load on any OS. Raises `NoOsAdapters` naming
    what's missing where there are none yet (polyglotic-hq 171: macOS and
    Linux; macOS's since 409, capturing nothing until 411's)."""
    if system == "darwin":
        return macos_adapters()
    if system != "win32":
        raise NoOsAdapters(
            f"Polyglotic has no adapters for this OS ({system}) yet:"
            " platform/linux would provide ports/capture.py's,"
            " ports/credentials.py's and ports/system.py's (decision 0038)"
        )
    from polyglotic_desktop.adapters import windows_credentials
    from polyglotic_desktop.platform.windows import (
        apps,
        capture,
        categories,
        devices,
        error_box,
        hotkeys,
        keys,
        on_top,
        package,
        process,
        qt_calls,
        sound,
        startup,
        taskbar,
        text_input,
    )
    from polyglotic_desktop.platform.windows import one_copy as copies
    from polyglotic_desktop.platform.windows import system as windows

    def speaker() -> SpeakerThread:
        """Windows' voices, imported only now: never on the start's path."""
        from polyglotic_desktop.platform.speaking import SpeakerThread
        from polyglotic_desktop.platform.windows import voices

        return SpeakerThread(voices.WindowsVoices(), voices.WaveOut)

    def credentials(target: str | None) -> CredentialStore:
        store = windows_credentials.WindowsCredentialStore
        return store(target) if target else store()

    def metered() -> bool:
        """Imported when first asked - a pack's download, or an update found
        (on the updates' thread): never on the interface thread at the start."""
        from polyglotic_desktop.platform.windows import network_cost

        return network_cost.metered()

    return OsAdapters(
        app_list=apps.WindowsAppList,
        app_capture_support=capture.app_capture_support,
        app_capture_trial=capture.Trial,
        app_capture=capture.AppCapture,
        everything_else_capture=capture.EverythingElseCapture,
        windows_build=windows.windows_build,
        system_capture=capture.SystemCapture,
        mic_capture=capture.MicCapture,
        outputs_playing=devices.outputs_playing,
        credentials=credentials,
        hotkeys=hotkeys.GlobalHotkeys,
        sound_out=sound.PlayAloud,
        speaker=speaker,
        start_at_sign_in=startup.RunAtSignIn,
        copy_lock=copies.NamedMutex,
        let_to_front=copies.let_to_front,
        keys=keys.held,
        on_top=on_top.WindowsOnTop,
        foreground_watch=on_top.ForegroundWatch,
        light_taskbar=taskbar.light_taskbar,
        taskbar_identity=taskbar.app_identity,
        store_package=package.store_package,
        os_name=windows.os_name,
        os_version=windows.os_version,
        data_folder=windows.data_folder,
        show_error=error_box.show_error,
        seconds_since_launch=process.seconds_since_launch,
        read_fonts=qt_calls.read_fonts,
        make_native_window=qt_calls.make_native_window,
        hold_key=hotkeys.HoldKey,
        type_text=text_input.type_text,
        keyboard_window=text_input.keyboard_window,
        common_apps=categories.COMMON_APPS,
        sound_devices=devices.sound_devices,
        metered=metered,
    )


def macos_adapters() -> OsAdapters:
    """The Mac's (polyglotic-hq 409, 411): its own system, Keychain and one
    copy; its capture - Core Audio taps and the mic - with the apps playing,
    the sound devices and the known apps; and what the first Mac build
    doesn't have yet saying so through its port (`platform/macos/not_yet`)."""
    from polyglotic_desktop.platform.macos import (
        apps,
        capture,
        categories,
        devices,
        keychain,
        not_yet,
        one_copy,
        translocation,
    )
    from polyglotic_desktop.platform.macos import system as mac

    def credentials(service: str | None) -> CredentialStore:
        return keychain.KeychainStore(service) if service else keychain.KeychainStore()

    return OsAdapters(
        app_list=apps.MacAppList,
        app_capture_support=capture.app_capture_support,
        app_capture_trial=capture.Trial,
        app_capture=capture.AppCapture,
        everything_else_capture=capture.EverythingElseCapture,
        windows_build=capture.no_windows_build,
        system_capture=capture.SystemCapture,
        mic_capture=capture.MicCapture,
        outputs_playing=devices.outputs_playing,
        credentials=credentials,
        hotkeys=not_yet.NoHotkeys,
        sound_out=not_yet.NoSound,
        speaker=None,
        start_at_sign_in=None,
        copy_lock=one_copy.FileLock,
        let_to_front=one_copy.let_to_front,
        keys=not_yet.held,
        on_top=not_yet.QtOnTop,
        foreground_watch=not_yet.NoForegroundWatch,
        light_taskbar=mac.light_menu_bar,
        taskbar_identity=not_yet.same_name,
        store_package=not_yet.none_found,
        os_name=mac.os_name,
        os_version=mac.os_version,
        data_folder=mac.data_folder,
        show_error=mac.show_error,
        seconds_since_launch=mac.seconds_since_launch,
        read_fonts=not_yet.not_done,
        make_native_window=not_yet.not_made,
        hold_key=not_yet.NoHoldKey,
        type_text=not_yet.type_text,
        keyboard_window=not_yet.keyboard_window,
        metered=not_yet.not_metered,
        common_apps=categories.COMMON_APPS,
        sound_devices=devices.sound_devices,
        translocation=translocation.MacTranslocation,
    )


def listening_settings(
    value: AppSettings,
    own: Mapping[SourceId, tuple[Language, ...]] | None = None,
    spoken: Mapping[SourceId, Language | None] | None = None,
) -> ListeningSettings:
    """What the server needs from the user's settings. `own`: each source's
    languages from the new interface's caption windows (the developer
    switch; none: Original only). The session's targets are then all of
    theirs together - or, if every window is Original only, today's as
    before, which an older server translates into and the windows don't
    show. `spoken`: each source's spoken language from its window (None:
    Detect); the session's is then the one they all name, or Detect
    (`agreed_language`: what a server before 2026-11-09 hears every
    source as) - without windows, today's setting as before. Dictation,
    when it's on, is a source of its own: never translated, heard in its
    own language (decision 0073) - left out of the session's own."""
    targets = tuple(Language(t) for t in value.targets)
    if own:
        together = tuple(dict.fromkeys(t for langs in own.values() for t in langs))
        targets = together or targets
    heard = Language(value.spoken_language) if value.spoken_language else None
    if spoken:
        heard = agreed_language(spoken.values())
    source_targets, source_spoken = dict(own or {}), dict(spoken or {})
    if value.dictation:  # never translated; heard as chosen, or detected (0073)
        source_targets[DICTATION] = ()
        chosen = value.dictation_language
        source_spoken[DICTATION] = Language(chosen) if chosen else None
    return ListeningSettings(
        spoken_language=heard,
        targets=targets,
        source_targets=source_targets,
        source_spoken=source_spoken,
        second_languages={
            Language(t): Language(s) for t, s in value.second_languages.items()
        },
        spelling_hints=value.spelling_hints,
        # Quick preview's lines are always translated (polyglotic-hq 268,
        # DECISIONS.md #101: +65 ms for the learner in 243's phase 2; the
        # server's give-way drops overtaken ones at the peak), and so are
        # Steady's - the longest wait for text's only (277); Live updates'
        # as the learner's "Translate live captions" says
        translate_live=value.caption_mode.provisional_lines
        or (value.translate_live and value.caption_mode is CaptionMode.LIVE),
    )


SETTLE_MS = 300
"""How long a change waits for the next before the session is handed the
listening settings: a control dragged hands over its last value once it
stops, never each mouse move (polyglotic-hq 273)."""


class TakesSettings(Protocol):
    """What the settings are handed to: the listening session."""

    def change_settings(self, settings: ListeningSettings) -> None: ...


class SettingsHandoff(QObject):
    """The listening settings handed to the session once a change has
    settled - `SETTLE_MS` after the last - and only when what the server
    needs differs from what the session last had (polyglotic-hq 273: a
    drag of the panel's slider sent the server a settings message on every
    mouse move; it answered `rate_limited` six times, dropping what came
    with them, and each hand-over held the interface up to 410 ms). A drag
    of a control the server doesn't need - the look - hands over nothing.
    `session`: the listening session now, if any; `chosen`: the listening
    settings now."""

    def __init__(
        self,
        session: Callable[[], TakesSettings | None],
        chosen: Callable[[], ListeningSettings],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session, self._chosen = session, chosen
        self._last: tuple[TakesSettings, ListeningSettings] | None = None
        self._settle = QTimer(self, singleShot=True, interval=SETTLE_MS)
        self._settle.timeout.connect(self.hand_over)

    @property
    def waiting(self) -> bool:
        """A change waits to settle."""
        return self._settle.isActive()

    def changed(self) -> None:
        """Something the listening settings come from changed: handed over
        once nothing else has for `SETTLE_MS`."""
        self._settle.start()

    def started(self, session: TakesSettings, settings: ListeningSettings) -> None:
        """A session started with `settings`: they aren't handed it again."""
        self._last = (session, settings)

    def hand_over(self) -> None:
        """The settings now, to the session - unless it has them already."""
        self._settle.stop()
        session = self._session()
        if session is None:
            return
        now = self._chosen()
        last = self._last
        if last is not None and last[0] is session and last[1] == now:
            return
        self._last = (session, now)
        session.change_settings(now)


def captioned_apps(
    value: AppSettings, per_app: bool, app_id: Callable[[str], SourceId]
) -> list[tuple[str, SourceId]]:
    """The caption windows' sources, in order, each with its key: the
    first LIMIT apps picked (by name), then everything else the PC plays
    beside the one app, if it's on; or everything the PC plays, one window
    ("system") - also for apps picked where Windows can't capture one app
    alone (Windows 10)."""
    if not value.source_chosen:
        return []
    if value.whole_system or not per_app:
        return [(SOURCE_KEY_SYSTEM, WHOLE_SYSTEM)]
    picked = [(name, app_id(name)) for name in value.apps[:LIMIT]]
    if value.captions_everything_else:
        picked.append((SOURCE_KEY_EVERYTHING_ELSE, EVERYTHING_ELSE))
    return picked


def chosen_capture(value: AppSettings) -> Capture:
    """What the learner chose to caption, for `source_selected`: the mode,
    how many apps are picked (at most LIMIT), and their own speech."""
    return capture_of(
        value.source_chosen,
        value.whole_system,
        0 if value.whole_system else len(value.apps[:LIMIT]),
        value.caption_mic,
        value.captions_everything_else,
    )


def captured(value: AppSettings) -> AppSettings:
    """What capture follows with the new interface's caption windows: the
    first LIMIT apps picked only. Home's picker adds no 4th (`adding_app`);
    this keeps one picked in today's interface from being captured with no
    window."""
    return replace(value, apps=value.apps[:LIMIT])


def caption_look(value: AppSettings) -> CaptionLook:
    """How every caption window looks: today's Captions page's settings."""
    return CaptionLook(
        opacity=value.opacity,
        background=value.background_color,
        original=value.original_color,
        translation=value.translation_color,
        font=value.caption_font,
        show_original=value.show_original,
        show_language=value.show_language,
        show_source=value.show_source,
        show_delay=value.show_delay,
        fade_after=value.fade_after,
        arrival=Arrival(value.caption_arrival),
        pause_hidden_after=value.pause_hidden_after,
        show_on_speech=value.show_hidden_on_speech,
        word_links=WordLinks(value.word_links),
        link_detail=LinkDetail(value.link_detail),
        link_line=LinkLine(value.link_line),
        link_gap=LinkGap(value.link_gap),
        introductions=value.word_introductions,
        preview=value.caption_mode.provisional_lines,
        lab=CaptionLab.from_stored(value.caption_lab),
        reading_lines=value.reading_lines,
        reading_size=ReadingSize(value.reading_size),
        reading_past=value.reading_past,
        reading_system=ReadingSystem(value.reading_system),
        reading_colour=ReadingColour(value.reading_colour),
        reading_custom=value.reading_custom_color,
        link_words=value.link_words_coloured,
    )


def second_language_chosen(
    value: AppSettings, target: str, second: str
) -> dict[str, object]:
    """The settings change a window's "Lines already in ..." asks for: lines
    already in `target` shown in `second` - "" (or `target` itself): left as
    they are. Kept by language, so every window with `target` follows
    (263)."""
    seconds = dict(value.second_languages)
    if second and second != target:
        seconds[target] = second
    else:
        seconds.pop(target, None)
    return {"second_languages": seconds}


def stop_captioning(value: AppSettings, key: str) -> dict[str, object]:
    """The settings change a caption window's close (or Home's x) asks for:
    its app unticked - with everything else beside it, which goes with its
    one app; for everything else, that alone; for everything the PC plays,
    nothing captioned."""
    if key == SOURCE_KEY_EVERYTHING_ELSE:
        return {"everything_else": False}
    off = {"everything_else": False} if value.everything_else else {}
    if key == SOURCE_KEY_SYSTEM:
        return {"whole_system": False, "apps": (), **off}
    return {"apps": tuple(app for app in value.apps if app != key), **off}


def switching_app(value: AppSettings, old: str, new: str) -> dict[str, object] | None:
    """The settings change a window's Captioning list asks for (F12, 249):
    app `new` captioned in `old`'s place - in its order, with its colour -
    or None if `new` is captioned already, or `old` isn't."""
    if new == old or new in value.apps or old not in value.apps:
        return None
    colours = dict(value.source_colors)
    colours[new] = colours.get(old) or value.source_colors_for([old])[old]
    return {
        "apps": tuple(new if app == old else app for app in value.apps),
        "source_colors": colours,
    }


WINDOW_NOTICES = {
    ConnectionState.WAITING: Notice.RECONNECTING,
    ConnectionState.SERVER_BUSY: Notice.SERVER_BUSY,
    ConnectionState.SIGN_IN_NEEDED: Notice.NOT_SIGNED_IN,
    ConnectionState.UPDATE_NEEDED: Notice.UPDATE_NEEDED,
    ConnectionState.PLUS_ENDED: Notice.PLUS_ENDED,
    ConnectionState.STOPPED: Notice.STOPPED,
}
"""The session's states a caption window says on its notice line."""

UNREACHABLE_NOTICES = {
    Unreachable.OFFLINE: Notice.OFFLINE,
    Unreachable.NO_ANSWER: Notice.CANT_REACH,
    # a refused connection: can't reach it - "restarting" only when the
    # server said so (polyglotic-hq 368)
    Unreachable.DOWN: Notice.CANT_REACH,
    Unreachable.RESTARTING: Notice.SERVER_RESTARTING,
    Unreachable.SERVER_ERROR: Notice.SERVER_PROBLEM,
    Unreachable.BLOCKED: Notice.BLOCKED,
    Unreachable.NOT_SECURE: Notice.NOT_SECURE,
    Unreachable.CLOCK: Notice.CLOCK,
    Unreachable.OUT_OF_DATE: Notice.NOT_SECURE,  # "see Home": Home says which (313)
    Unreachable.TOO_MANY_SESSIONS: Notice.TOO_MANY_SESSIONS,
    Unreachable.TOO_MANY_TRIES: Notice.TOO_MANY_TRIES,
    Unreachable.MAINTENANCE: Notice.MAINTENANCE,
}
"""Waiting to try again: what a caption window says, by why the server
can't be reached (polyglotic-hq 251) - in place of "Reconnecting"."""


def window_notice(
    state: ConnectionState, unreachable: Unreachable | None
) -> Notice | None:
    """What a caption window (or a transcript) says of the session's state."""
    if state is ConnectionState.WAITING and unreachable is not None:
        return UNREACHABLE_NOTICES[unreachable]
    return WINDOW_NOTICES.get(state)


def in_maintenance(status: Status) -> bool:
    """Whether the session waits out a planned maintenance window: the
    speech pipeline keeps nothing to send after it (polyglotic-hq 319)."""
    from polyglotic_desktop.connection.session import SessionState

    return (
        status.state is SessionState.WAITING
        and status.unreachable is Unreachable.MAINTENANCE
    )


class MaintenanceSoon(QObject):
    """The caption windows' one line about a planned maintenance window,
    once, `SOON` before its start (polyglotic-hq 319): over a game or a
    call, Home isn't in view."""

    def __init__(
        self,
        show: Callable[[str], None],
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__()
        self._show = show
        self._wall_clock = wall_clock
        self._window: Maintenance | None = None
        self._said: set[datetime] = set()  # the starts said
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.say)

    def follow(self, window: Maintenance | None) -> None:
        """The window held now: its line is due at its start less `SOON`."""
        self._window = window
        self._timer.stop()
        if window is None or window.starts_at in self._said:
            return
        now = self._wall_clock()
        due = (window.starts_at - SOON - window.server_now(now)).total_seconds()
        if due <= 0:
            self.say()
        elif due < SOON_TIMER_MAX_SEC:  # a later `welcome` sets one further off
            self._timer.start(int(due * 1000))

    def say(self) -> None:
        window = self._window
        if window is None or window.starts_at in self._said:
            return
        if soon(window, self._wall_clock()):
            self._said.add(window.starts_at)
            self._show(maintenance_words.soon_line(window))


SOON_TIMER_MAX_SEC = 2 * 24 * 3600
"""The line's timer is set at most this far ahead (a Qt timer's limit is
about 24 days)."""


def wire_maintenance(
    connection: Connection,
    listener: QtListener,
    desktop: DesktopApp,
    hub: Hub,
    windows: CaptionWindows,
) -> MaintenanceSoon:
    """A planned maintenance window: the one kept from before (if it isn't
    over) goes to the connection, which hands it to each session; each
    change is kept, and said on Home and, once, on the caption windows
    (polyglotic-hq 319)."""
    held = maintenance_from_stored(
        desktop.settings.value.maintenance, datetime.now(UTC)
    )
    connection.maintenance = held
    soon_line = MaintenanceSoon(windows.show_notice)
    soon_line.setParent(desktop)

    def seen(window: Maintenance | None) -> None:
        desktop.settings.update(maintenance=maintenance_stored(window))
        hub.set_maintenance(window)
        soon_line.follow(window)

    listener.maintenance_seen.connect(seen)
    hub.set_maintenance(held)
    soon_line.follow(held)
    return soon_line


def wire_caption_windows(
    windows: CaptionWindows, desktop: DesktopApp, send_settings: Callable[[], None]
) -> None:
    """The caption windows in step with the app: captions, notices,
    pause, today's free minutes used (the server's count) and the listening
    mark reach them - and signed out, they go until the learner signs in
    (`CaptionWindows`); lock and hide every window are the app's commands
    (tray, Home, hotkeys), which the windows' own buttons check; "Caption
    my own speech" is on while any window shows my speech, and turns it on
    or off in every window; Learning's changes redraw the highlights; a
    window's close unticks its app; its timing chip sets the session's;
    each window's label follows its app's source as it's found;
    All caption settings... opens Settings > Captions (`Hub`) and Open transcript its
    transcript window (`wire_transcripts`)."""
    windows.languages_changed.connect(send_settings)
    windows.mic_wanted.connect(desktop.caption_mic.setChecked)
    desktop.caption_mic.toggled.connect(
        lambda on: (
            windows.set_show_mic_everywhere(on)
            if on != windows.show_mic_anywhere
            else None
        )
    )
    windows.lock_wanted.connect(lambda: desktop.lock_windows.setChecked(True))
    windows.unlock_wanted.connect(lambda: desktop.lock_windows.setChecked(False))
    windows.hide_wanted.connect(lambda: desktop.hide_windows.setChecked(True))
    # speech started in a hidden window, and the learner asked for it (335)
    windows.show_wanted.connect(lambda: desktop.hide_windows.setChecked(False))
    # what a locked window says unlocks it: the hotkey as it is now - none if
    # it doesn't work here (`hotkeys_not_working`) - set before the windows lock
    lock = desktop.lock_windows
    windows.set_unlock_keys(shortcut_text(lock))
    lock.changed.connect(lambda: windows.set_unlock_keys(shortcut_text(lock)))
    desktop.lock_windows.toggled.connect(windows.set_locked)
    desktop.hide_windows.toggled.connect(windows.set_hidden)
    windows.set_locked(desktop.lock_windows.isChecked())
    windows.set_hidden(desktop.hide_windows.isChecked())
    windows.stop_wanted.connect(
        lambda key: desktop.settings.update(
            **stop_captioning(desktop.settings.value, key)
        )
    )
    windows.timing_wanted.connect(
        lambda mode: desktop.settings.update(caption_mode_chosen=mode)
    )
    windows.second_language_wanted.connect(
        lambda target, second: desktop.settings.update(
            **second_language_chosen(desktop.settings.value, target, second)
        )
    )

    def relabel() -> None:
        labels = desktop.source_labels()
        windows.set_labels(labels, labels[MIC].name)

    # an app's source found after its window opened (every start: the windows
    # open before capture starts): the window takes the app's name, not its file's
    desktop.labels_changed.connect(relabel)
    desktop.feed.applied.connect(windows.apply)
    desktop.feed.dictionary_ready.connect(windows.dictionary_ready)
    desktop.feed.checked.connect(windows.use_checked)
    desktop.feed.captioned.connect(windows.captioned)
    desktop.caption_notice.connect(windows.show_notice)
    desktop.connection_changed.connect(
        lambda state, retry_in: windows.set_connection(
            window_notice(state, desktop.unreachable), retry_in
        )
    )
    desktop.pause.toggled.connect(windows.set_paused)
    windows.set_paused(desktop.pause.isChecked())
    desktop.minutes_changed.connect(
        lambda _used, left: windows.set_minutes_used(minutes_used_up(left))
    )
    desktop.captions_failing.connect(windows.set_failing)
    desktop.connection_unstable.connect(windows.set_unstable)
    if desktop.tools is not None:  # highlights drawn again on a Learning change
        desktop.tools.changed.connect(windows.learning_changed)
        desktop.tools.load_changed.connect(windows.load_changed)  # stages (324)


def wire_transcripts(transcripts: Transcripts, desktop: DesktopApp) -> None:
    """The transcript windows in step with the app: opened from a caption
    window's Open transcript and the tray's Transcript menu; captions, the
    best model's versions, pause and the connection's state reach them;
    their timing sets the session's; Learning's changes recolour saved
    words; Settings > App says how far
    back their lists go."""
    transcripts.windows.transcript_wanted.connect(transcripts.show)
    transcripts.timing_wanted.connect(
        lambda mode: desktop.settings.update(caption_mode_chosen=mode)
    )
    desktop.feed.applied.connect(transcripts.apply)
    desktop.feed.dictionary_ready.connect(transcripts.dictionary_ready)
    desktop.feed.checked.connect(transcripts.use_checked)
    desktop.pause.toggled.connect(transcripts.set_paused)
    transcripts.set_paused(desktop.pause.isChecked())
    # an app's source found after its window opened (every start): the tray's
    # Transcript menu and an open transcript take the name its caption window
    # just took, not its file's (after `wire_caption_windows`' relabel)
    desktop.labels_changed.connect(transcripts.follow)
    desktop.connection_changed.connect(
        lambda state, _retry_in: transcripts.set_connection(
            window_notice(state, desktop.unreachable)
        )
    )
    if desktop.tools is not None:
        desktop.tools.changed.connect(transcripts.learning_changed)

    def follow_length() -> None:  # Settings > App's Transcripts (334)
        value = desktop.settings.value
        transcripts.set_length(TranscriptLength.from_stored(value.transcript_length))
        transcripts.ask_at_quit = value.transcript_ask_at_quit

    follow_length()
    desktop.settings.changed.connect(follow_length)
    # Quit asks first about a long transcript not saved; "Don't ask again" kept
    desktop.quit_check = transcripts.may_quit
    transcripts.asking_changed.connect(
        lambda on: desktop.settings.update(transcript_ask_at_quit=on)
    )
    menu = desktop.tray_menu  # Transcript >, after the caption windows' commands
    actions = menu.actions()
    if desktop.report_problem in actions:
        menu.insertMenu(
            actions[actions.index(desktop.report_problem) - 1], transcripts.menu
        )
    follow_transcripts(transcripts)


def follow_transcripts(transcripts: Transcripts) -> None:
    """The transcripts follow the settings: the window theme, and their
    caption windows' languages, labels and timing."""
    transcripts.set_theme(window_theme())
    transcripts.follow()


def follow_settings(
    windows: CaptionWindows, desktop: DesktopApp, sources: Sources
) -> None:
    """The caption windows follow the settings: the look, the timing,
    second languages, labels, and which apps are captioned."""
    value = desktop.settings.value
    windows.set_look(caption_look(value))
    windows.set_timing(value.caption_mode)
    windows.set_longest_wait(value.max_wait_for_text)
    windows.set_settle_after(value.text_settles_after)
    desktop.feed.history.set_settle_after(value.text_settles_after)
    windows.set_second_languages(
        {Language(t): Language(s) for t, s in value.second_languages.items()}
    )
    captioned = captioned_apps(value, sources.per_app, sources.app_id)
    if sources.sample_shown and not value.source_chosen:  # an app chosen ends it
        captioned.append((SOURCE_KEY_SAMPLE, SAMPLE))
    desktop.set_app_sources(sources.shown())
    labels = desktop.source_labels()
    windows.set_labels(labels, labels[MIC].name)
    windows.set_captioned(captioned)


def traditional_here() -> bool:
    """Whether this PC reads Chinese in Traditional characters: what "Show
    Mandarin in" starts at (`interface_language.reads_traditional`; 375)."""
    app = QApplication.instance()
    running = interface_language.in_use(app) if app else interface_language.ENGLISH
    return interface_language.reads_traditional(
        running, interface_language.windows_languages()
    )


def shows_traditional(value: AppSettings) -> bool:
    """Mandarin's captions are shown in Traditional characters: as chosen,
    else as this PC reads Chinese (polyglotic-hq 375)."""
    if value.mandarin_script is None:
        return traditional_here()
    return value.mandarin_script == "traditional"


class MandarinScript:
    """ "Show Mandarin in: Traditional" (polyglotic-hq 375; decision 0164):
    each caption's Mandarin converted on this PC as it arrives, before the
    caption windows, the transcript or a lookup see it - so what's shown,
    copied, looked up and kept is one text. The converter's table (1 MB)
    is read the first time a caption needs it, on the session's thread;
    then the Chinese dictionary is told the forms it writes
    (`ChineseDictionary.read_traditional`), so a converted line splits and
    counts its words as before. `chinese`: the Chinese dictionary open now,
    if any (one can open later: a language learned beside)."""

    def __init__(self, chinese: Callable[[], ChineseDictionary | None]) -> None:
        self._chinese = chinese
        self.traditional = False
        """Wanted now: set on the interface thread, read on the session's."""
        self._converter: TraditionalChinese | None = None
        self._told: ChineseDictionary | None = None
        self._loading = threading.Lock()

    def caption(self, update: CaptionUpdate) -> CaptionUpdate:
        """`update` as the learner reads Mandarin."""
        if not self.traditional:
            return update
        converter = self._converter
        if converter is None:
            with self._loading:
                if self._converter is None:
                    # imported here: never before the first paint (400)
                    from polyglotic_desktop.adapters.traditional_table import (
                        read_table,
                    )
                    from polyglotic_desktop.core.lexicon.traditional import (
                        TraditionalChinese,
                    )

                    self._converter = TraditionalChinese(read_table())
                converter = self._converter
        dictionary = self._chinese()
        if dictionary is not None and dictionary is not self._told:
            dictionary.read_traditional(converter.simplified_of())
            self._told = dictionary
        return mandarin_written(update, converter.convert)


def session_languages(
    value: AppSettings, in_use: Sequence[str], recent: Sequence[str] = ()
) -> SessionLanguages:
    """The Languages panel's value: today's settings, the caption windows'
    languages (a second-language row each) and the spoken languages named
    last (`recent`: first in its list, polyglotic-hq 317)."""
    return SessionLanguages(
        spoken=value.spoken_language,
        second_languages=dict(value.second_languages),
        translate_live=value.translate_live,
        spelling_hints=value.spelling_hints,
        in_use=tuple(in_use),
        live_updates=value.caption_mode is CaptionMode.LIVE,
        recent_spoken=tuple(recent),
        mandarin_script=value.mandarin_script,
        traditional_here=traditional_here(),
    )


def languages_settings(languages: SessionLanguages) -> dict[str, object]:
    """The settings a change in the Languages panel makes."""
    return {
        "spoken_language": languages.spoken,
        "second_languages": dict(languages.second_languages),
        "translate_live": languages.translate_live,
        "spelling_hints": languages.spelling_hints,
        "mandarin_script": languages.mandarin_script,
    }


def not_working(
    hotkeys: Iterable[str], bound: Iterable[str], taken: Iterable[str]
) -> list[str]:
    """The app's hotkeys that do nothing here: those another app has
    (`taken`), and those never handed to Windows (not `bound` - a preview
    build registers none, so the installed copy keeps them: polyglotic-hq
    398). Nothing then names them - a locked window says where else to
    unlock it."""
    working = set(bound) - set(taken)
    return [key for key in hotkeys if key not in working]


def shortcut_text(action: QAction) -> str:
    """`action`'s hotkey as the OS writes it ("Ctrl+Alt+L"; on a Mac, where
    Qt's Ctrl is Command, "⌥⌘L"); "" for none."""
    return action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)


def look_settings(look: CaptionLook) -> dict[str, object]:
    """The settings a change in the Look panel makes (Quick preview's line
    is the timing's, not the look's)."""
    return {
        "opacity": look.opacity,
        "background_color": look.background,
        "original_color": look.original,
        "translation_color": look.translation,
        "caption_font": look.font,
        "show_original": look.show_original,
        "show_language": look.show_language,
        "show_source": look.show_source,
        "fade_after": look.fade_after,
        "caption_arrival": look.arrival.value,
        "pause_hidden_after": look.pause_hidden_after,
        "show_hidden_on_speech": look.show_on_speech,
        "word_links": look.word_links.value,
        "link_detail": look.link_detail.value,
        "link_line": look.link_line.value,
        "link_gap": look.link_gap.value,
        "caption_lab": look.lab.to_stored(),
        "reading_lines": look.reading_lines,
        "reading_size": look.reading_size.value,
        "reading_past": look.reading_past,
        "reading_system": look.reading_system.value,
        "reading_colour": look.reading_colour.value,
        "reading_custom_color": look.reading_custom,
        "link_words_coloured": look.link_words,
    }


def window_theme() -> style.Theme:
    """The window theme now - today's theme module's - for the new
    interface's own windows (each dressed by a stylesheet of its own)."""
    return style.Theme(
        asdict(theme.palette(theme.current, theme.current_theme)),
        theme.HEADING_FAMILY,
        dark=theme.current == "dark",
    )


def timing_of(value: AppSettings) -> Timing:
    """The Timing panel's value from the settings: the caption mode, the
    Live updates interval and the longest wait for text (277)."""
    return Timing(
        value.caption_mode,
        value.live_update_interval,
        value.max_wait_for_text,
        value.text_settles_after,
    )


class Panels:
    """The shared panels' views, in step with the settings: every panel
    showing them - Settings > Captions and the transcripts' rails - binds
    to these (109's 1.1: one owner, one value). A change in a panel is
    saved with the settings, and the caption windows follow it from
    there - but the look's: the caption windows show it at once, and it's
    saved once it settles (`SETTLE_MS` after the last change), so a drag
    of its slider saves once, not on every mouse move (polyglotic-hq 273:
    each save ran everything that follows the settings, file reads
    included, and held the interface up to 410 ms). The look's reset is
    the look's only: the windows' places are Home's "Reset positions"
    (248's section 2.2)."""

    def __init__(self, settings: Settings, windows: CaptionWindows) -> None:
        self.settings, self.windows = settings, windows
        value = settings.value
        self.languages = LanguagesView(
            session_languages(value, self.in_use(), windows.recent_spoken()),
            self._languages_chosen,
        )
        self.timing = TimingView(
            timing_of(value),
            lambda t: settings.update(
                caption_mode_chosen=t.mode.value,
                live_update_interval=t.live_interval,
                max_wait_for_text=t.max_wait,
                text_settles_after=t.settle_after,
            ),
        )
        self.look = LookView(caption_look(value), self._look_changed)
        self.look_waiting = False
        """A look change waits to be saved."""
        self._look_settles = QTimer(singleShot=True, interval=SETTLE_MS)
        self._look_settles.timeout.connect(self.save_look)
        style.use(window_theme())
        settings.changed.connect(self.follow)
        windows.languages_changed.connect(self.follow)

    def _look_changed(self, look: CaptionLook) -> None:
        """The learner changed the look: the caption windows show it now;
        it's saved once it settles."""
        self.windows.set_look(look)
        self.look_waiting = True
        self._look_settles.start()

    def save_look(self) -> None:
        """The look as the panels have it, saved now if a change waits -
        once it settles, and at quit (`Interface.close`)."""
        self._look_settles.stop()
        if self.look_waiting:
            self.look_waiting = False
            self.settings.update(**look_settings(self.look.value))

    def _languages_chosen(self, languages: SessionLanguages) -> None:
        """A change in the Languages panel (Settings > Captions > Speech),
        saved. Its Spoken language is for every window: each window's own
        is set to it (263) - a window's settings then change its own."""
        if languages.spoken != self.settings.value.spoken_language:
            self.windows.set_spoken_everywhere(languages.spoken)
        self.settings.update(**languages_settings(languages))

    def in_use(self, leaving_out: str | None = None) -> list[str]:
        """The caption windows' languages, in order - but the window of
        `leaving_out` (a source key)'s."""
        found = (
            t
            for source, langs in self.windows.targets().items()
            if source != leaving_out
            for t in langs
        )
        return [str(t) for t in dict.fromkeys(found)]

    def follow(self) -> None:
        value = self.settings.value
        style.use(window_theme())
        self.languages.follow(
            session_languages(value, self.in_use(), self.windows.recent_spoken())
        )
        self.timing.follow(timing_of(value))
        look = caption_look(value)
        if self.look_waiting:  # the panels' is newer: only the timing's line
            look = replace(self.look.value, preview=look.preview)
        self.look.follow(look)


def _tr_app(text: str) -> str:
    """A source's own name, as today's interface translates it."""
    return QApplication.translate("DesktopApp", text)


def picker_of(
    value: AppSettings,
    found: Sequence[PlayingApp],
    per_app: bool,
    windows: CaptionWindows,
    hidden: bool,
    sample: tuple[bool, bool] = (False, False),
    sample_ended: bool = False,
    fell_back: bool = False,
) -> Picker:
    """Home's app picker: a row per captioned app - the first LIMIT picked,
    and everything else beside one, or everything the PC plays - with its
    label, its colour, whether it's playing, and its window's language and
    my-speech mark; the apps with sound that could be added; and the
    sample (`sample`: whether there's one in the language learned, and
    whether it's on - polyglotic-hq 176; `sample_ended`: it played to its
    end, its window kept - 208). `fell_back`: capturing apps one by one
    was tried here and failed (decision 0076)."""
    colours = value.source_colors_for()
    rows = []
    for key, _ in captioned_apps(value, per_app, lambda name: SourceId(name)):
        if key == SOURCE_KEY_SYSTEM:
            status, own = (
                AppStatus.EVERYTHING,
                pc_or_mac(_tr_app("This PC"), _tr_app("This Mac")),
            )
        elif key == SOURCE_KEY_EVERYTHING_ELSE:
            status, own = AppStatus.EVERYTHING_ELSE, _tr_app("Everything else")
        else:
            same = [a for a in found if a.name == key]
            own = same[0].title if same else key
            status = (
                AppStatus.PLAYING
                if any(a.playing for a in same)
                else AppStatus.QUIET
                if same
                else AppStatus.NOT_OPEN
            )
        window = windows.windows.get(key)
        choices = (
            window.choices
            if window is not None
            else windows.stored.by_key.get(key, WindowChoices())
        )
        sight, paused_after = windows.sight(key)
        rows.append(
            AppRow(
                key,
                value.source_names.get(key) or own,
                colours.get(key) or value.source_colors_for([key])[key],
                status,
                choices.translate_into,
                choices.show_mic,
                sight,
                paused_after,
            )
        )
    you = AppRow(
        SOURCE_KEY_MIC,
        value.source_names.get(SOURCE_KEY_MIC) or _tr_app("You"),
        colours[SOURCE_KEY_MIC],
        AppStatus.QUIET,
    )
    available = addable(
        [(a.name, a.title, a.playing) for a in found], tuple(value.apps)
    )
    return Picker(
        you=you,
        captioned=tuple(rows),
        available=available,
        whole_system=value.whole_system,
        per_app=per_app,
        fell_back=fell_back and not per_app,
        hidden=hidden,
        everything_else=per_app and value.captions_everything_else,
        sample=sample_state(*sample, value.source_chosen, available, sample_ended),
    )


def hidden_line(rows: Sequence[AppRow]) -> tuple[list[str], int | None]:
    """What the tray says of hidden caption windows (polyglotic-hq 335):
    the apps they caption still, unseen, and - any paused - the longest
    time one was hidden before its listening paused (minutes)."""
    captioning = [row.label for row in rows if row.sight is Sight.CAPTIONING]
    paused = [
        row.paused_after
        for row in rows
        if row.sight is Sight.PAUSED and row.paused_after is not None
    ]
    return captioning, max(paused) if paused else None


def adding_app(value: AppSettings, name: str) -> dict[str, object] | None:
    """The settings change Home's + asks for: `name` captioned, with its
    colour fixed now (unticking another later won't change it) - or None
    at the limit (DECISIONS.md #53: 3 apps), or while everything else is
    captioned beside one app (it can be beside one only, #59)."""
    if name in value.apps or len(value.apps) >= LIMIT or value.captions_everything_else:
        return None
    colours = dict(value.source_colors)
    colours.setdefault(name, value.source_colors_for([name])[name])
    changes: dict[str, object] = {
        "apps": (*value.apps, name),
        "whole_system": False,
        "source_colors": colours,
    }
    if value.everything_else:  # kept while it didn't apply: not with this app
        changes["everything_else"] = False
    return changes


def everything_else_change(value: AppSettings, on: bool) -> dict[str, object] | None:
    """The settings change Home's "Also caption everything else" asks for:
    on with one app picked only (None otherwise), with its colour fixed now,
    as an app's is when it's added; or off."""
    if not on:
        return {"everything_else": False}
    if value.whole_system or len(value.apps) != 1:
        return None
    key = SOURCE_KEY_EVERYTHING_ELSE
    colours = dict(value.source_colors)
    on_now = replace(value, everything_else=True)
    colours.setdefault(key, on_now.source_colors_for()[key])
    return {"everything_else": True, "source_colors": colours}


def renaming(value: AppSettings, key: str, text: str, own: str) -> dict[str, object]:
    """The learner's name for a source; empty, or its own: none."""
    names = dict(value.source_names)
    name = text.strip()[:MAX_SOURCE_NAME]
    if name and name != own:
        names[key] = name
    else:
        names.pop(key, None)
    return {"source_names": names}


class Hub:
    """The main window (109's section 7): Home - the state, the app picker,
    the Languages and Timing panels, the caption windows' commands - and
    Words, Account, Settings and Help (109's step 6), wired to the app's
    commands and today's dialogs. It follows the settings, the apps with
    sound, the caption windows and the session's state (`DesktopApp`'s),
    and says the state in the tray's tooltip; the tray and the first run
    bring it forward (`show`); the picker's commands go to
    the settings and the caption windows."""

    def __init__(
        self,
        desktop: DesktopApp,
        windows: CaptionWindows,
        panels: Panels,
        apps: AppsWithSound,
        per_app: bool,
        save_folder: SaveFolder | None = None,
        opened: OpenLanguages | None = None,
    ) -> None:
        """`save_folder`: where Words' exports open their save dialogs -
        the transcripts' too (`new_interface`). `opened`: which of Words'
        language sections were left open."""
        self.desktop, self.windows, self.apps = desktop, windows, apps
        self.panels, self.per_app = panels, per_app
        self.fell_back = False
        """Capturing apps one by one was tried here and failed (`main`'s
        `AppsOneByOne`, decision 0076): Home says so, with "Try apps again"."""
        self.apps_again: Callable[[], None] | None = None
        """Tries capturing apps one by one again (`main`)."""
        self.busy = False  # the server's pace hint slows live updates
        self.sample: Callable[[bool], None] | None = None
        """Turns the sample on or off (`main`, once listening is wired)."""
        self._samples: dict[str | None, bool] = {}
        """Whether there's a sample, by language learned (`_has_sample`)."""
        self.sample_on = False
        self.sample_ended = False  # played to its end, its window kept (208)
        self.update_found: UpdateNow | None = None
        """What the updater found after the server refused this version."""
        self._shown = False
        self._retry_at: float | None = None
        """When the session tries to reconnect next (`time.monotonic`)."""
        self.picker = PickerView(self._picker(), self)
        self.list_devices: Callable[[], SoundDevices] = SoundDevices
        """The speakers and mics plugged in (`main`: the OS's; 372)."""
        self.read_mic_peak: Callable[[], float | None] = lambda: None
        """The mic's level while it's captioned (`main`: the sources')."""
        self.sound = SoundView(self._sound(), self)
        self.home = HomePage(
            self.picker,
            desktop.pause,
            desktop.lock_windows,
            desktop.hide_windows,
            theme.SOURCE_COLORS,
            sound=self.sound,
        )
        self.home.add_feedback(desktop.report_problem, desktop.suggest)
        self.startup: StartWithWindows | None = None
        """Starting with Windows - the installed app only (`main`)."""
        self._captions = 0  # finished captions shown in this run
        desktop.feed.captioned.connect(self._captioned)
        self.home.start_with_windows_answered.connect(self._start_with_windows)
        self.home.reset_positions_wanted.connect(windows.reset_places)
        self.home.level_wanted.connect(self._level_wanted)
        self.home.level_dismissed.connect(
            lambda: desktop.settings.update(level_line_dismissed=True)
        )
        self.home.join_wanted.connect(
            lambda: windows.separate() if windows.joined_window else windows.join()
        )
        windows.joined_changed.connect(lambda _: self.follow())
        self.window = NextMainWindow(desktop.quit)
        tr = QApplication.translate
        self.window.add_page("home", tr("MainWindow", "Home"), self.home)
        start_parts.done("page_home")  # with the main window itself
        self.words: WordsPage | None = None
        tools = desktop.tools
        if tools is not None:  # a section per full language open (306)
            self.words = WordsPage(list(tools.every), windows.card, save_folder, opened)
            tools.changed.connect(self.words.learning_changed)  # every language's
            for each in tools.every:  # opened early
                each.read_ahead_done.connect(self.words.learning_changed)
            self.words.change_level_wanted.connect(self.change_level)
            self.window.add_page("words", tr("MainWindow", "Words"), self.words)
        start_parts.done("page_words")
        self.account = NextAccountPage()
        self.home.sign_in_wanted.connect(self.account.sign_in.trigger)
        self.home.get_plus_wanted.connect(self.account.get_plus.click)
        self.account.add_feedback(desktop.report_problem, desktop.suggest)
        # Learning, between Words and Account (polyglotic-hq 262, 248's Q2 A)
        self.level_of: Callable[[str], KnownLine | None] | None = None
        """Another full dictionary's level, as it was kept (`main`)."""
        self.learning = LearningPage(self.account.delete_learning)
        self.learning.change_level_wanted.connect(self.change_level)
        self.learning.languages_wanted.connect(self._languages_wanted)
        self.packs: PackDelivery | None = None
        """The dictionary packs (`use_packs`, decision 0122)."""
        self.learning.introductions_chosen.connect(
            lambda choice: desktop.settings.update(**introductions_changes(choice))
        )
        self.learning.choices_chosen.connect(
            lambda code, chosen: desktop.settings.update(
                **language_choices_changes(desktop.settings.value, code, chosen)
            )
        )
        self.learning.words_wanted.connect(lambda: self.window.go_to("words"))
        self._undo_known: dict[str, tuple[Before, int]] = {}
        """Each language's Undo after a quick mark, this session only: the
        line before it, and how many words it marked (polyglotic-hq 342)."""
        self.ask_reset: Callable[[str, str], bool] = self._ask_reset
        """Reset's question (its title and what it changes): True to reset."""
        self.learning.first_known_wanted.connect(self.mark_first_known)
        self.learning.undo_known_wanted.connect(self.undo_known)
        self.learning.reset_known_wanted.connect(self.reset_known)
        self._wire_load_card()
        self.window.add_page("learning", tr("MainWindow", "Learning"), self.learning)
        self.window.add_page("account", tr("MainWindow", "Account"), self.account)
        start_parts.done("page_learning_and_account")
        self.settings = SettingsPage(
            [(key, look.name) for key, look in theme.THEMES.items()],
            desktop.hotkeys,
            desktop.work_with_us,
            interface_language.picker(),
            look=panels.look,
            timing=panels.timing,
            speech=panels.languages,
            sound=self.sound,
        )
        app = QApplication.instance()
        running = interface_language.in_use(app) if app else interface_language.ENGLISH
        self.settings.show_draft(interface_language.is_draft(running))
        self.settings.translation_feedback_wanted.connect(
            lambda: desktop.feedback_wanted.emit("suggestion")
        )
        self.settings.learning_wanted.connect(lambda: self.window.go_to("learning"))
        self.settings.lab.load_wanted.connect(self.open_load)
        self.learning.load.lab_wanted.connect(self.open_lab_load)
        windows.all_settings_wanted.connect(self.open_caption_settings)
        self.settings.interface_language_chosen.connect(
            lambda code: desktop.settings.update(interface_language=code or None)
        )
        self.settings.theme_chosen.connect(
            lambda key: desktop.settings.update(theme=key)
        )
        self.settings.window_theme_chosen.connect(
            lambda mode: desktop.settings.update(window_theme=mode)
        )
        self.settings.text_size_chosen.connect(
            lambda size: desktop.settings.update(app_text_size=size)
        )
        self.settings.transcript_length_chosen.connect(
            lambda length: desktop.settings.update(transcript_length=length)
        )
        self.settings.transcript_ask_chosen.connect(
            lambda on: desktop.settings.update(transcript_ask_at_quit=on)
        )
        self._show_theme()
        desktop.settings.changed.connect(self._show_theme)
        # the app's text size: `main` applied it at start; a change, at once
        self._text_size = desktop.settings.value.app_text_size
        desktop.settings.changed.connect(self._follow_text_size)
        self.window.add_page(
            "settings", tr("MainWindow", "Settings"), self.settings, "foot"
        )
        start_parts.done("page_settings")
        self.help = NextHelpPage(
            desktop.caption_facts,
            lambda: tools.dictionary_problem if tools is not None else None,
            tools.is_chinese if tools is not None else True,
            lambda: tools.learning_set_aside if tools is not None else None,
            lambda: tools.learning_unsaved if tools is not None else False,
        )
        self.help.report_wanted.connect(desktop.check_report_wanted)
        self.window.add_page("help", tr("MainWindow", "Help"), self.help, "foot")
        start_parts.done("page_help")
        self.window.go_to("home")
        self.retheme()
        desktop.window_wanted.connect(self.show)
        self.window.hidden_to_tray.connect(desktop.note_in_tray)  # once: still running
        desktop.themed.connect(self.retheme)
        self.window.text_size_changed.connect(self.retheme)  # the logo at it
        desktop.minutes_changed.connect(self.home.state.set_minutes)
        desktop.home_notice.connect(self.home.state.set_notice)
        desktop.banner_in_view = self.banner_in_view  # else the tray says it too
        desktop.captions_failing.connect(self.home.state.set_failing)
        desktop.connection_unstable.connect(self.home.state.set_unstable)
        for each in tools.every if tools is not None else ():
            self._follow_problems(each)
        if tools is not None:  # and its learning data set aside at the start
            self._dictionary_out()
            self._learning_data_changed()
        self._learning_shown: tuple[object, ...] | None = None
        self._ask_level: set[str] = set()
        """Full languages just added on Learning that open in a moment
        (`main`'s `open_added`): asked about their level once they do."""
        """The settings Learning's page shows, as it last showed them."""
        self.show_learning()
        desktop.settings.changed.connect(self._learning_settings_changed)
        if tools is not None:  # a level picked or changed
            tools.changed.connect(self._learning_changed)
        desktop.connection_changed.connect(self._connection_changed)
        desktop.pause.toggled.connect(self.follow)
        desktop.hide_windows.toggled.connect(self.follow)
        desktop.settings.changed.connect(self.follow)
        windows.languages_changed.connect(self.follow)
        windows.mic_wanted.connect(self.follow)
        windows.sight_changed.connect(self.follow)
        apps.found.connect(self.follow)
        self.follow()

    def _follow_problems(self, each: LearningTools) -> None:
        """An open language's dictionary going out (at the start, or when a
        query fails: 199), its learning data found damaged later (206) or
        deleted on this PC with the files set aside (213): Home's banner."""
        each.dictionary_out.connect(
            self._dictionary_out, Qt.ConnectionType.QueuedConnection
        )
        each.learning_damaged.connect(
            self._learning_data_changed, Qt.ConnectionType.QueuedConnection
        )
        each.learning_deleted.connect(
            self._learning_data_changed, Qt.ConnectionType.QueuedConnection
        )
        each.learning_not_deleted.connect(
            partial(self._not_deleted, each.language),
            Qt.ConnectionType.QueuedConnection,
        )

    def _not_deleted(self, code: str) -> None:
        """A deletion on this PC left some of `code`'s learning data (306):
        Home says which language, and how to finish it; the other languages'
        are deleted all the same."""
        self.desktop.home_notice.emit(not_deleted_notice(code))

    def language_opened(self, other: LearningTools) -> None:
        """A full language opened during the run, beside the main one (306):
        its Words section, Home's banner if its dictionary or learning data
        is out, and Learning's cards with its level. One just added on
        Learning, with no level yet, is asked how many words the learner
        knows (323), as the main language is."""
        if self.words is not None:
            self.words.add_learner(other)
            other.read_ahead_done.connect(self.words.learning_changed)
        self._follow_problems(other)
        self._dictionary_out()
        self._learning_data_changed()
        self.show_learning()
        if other.language in self._ask_level:  # just added on Learning (323)
            self._ask_level.discard(other.language)
            if other.vocabulary.line is None:
                self.change_level(other.language)

    def _dictionary_out(self) -> None:
        """A learner's dictionary is out (polyglotic-hq 199): Home's
        banner says which - the main language's first, else another open
        one's, the rest working on (306) - and Help's check (it asks when
        it runs)."""
        tools = self.desktop.tools
        if tools is not None:
            out = next((t for t in tools.every if t.dictionary_problem), tools)
            self.home.state.set_dictionary_out(out.dictionary_problem, out.is_chinese)

    def _learning_data_changed(self) -> None:
        """A language's learning data was set aside at the start, or found
        damaged since: Home's banner says nothing more is saved until a
        restart (polyglotic-hq 206) - the main language's first, else
        another open one's (306). Or the learner deleted it on this PC: the
        banner no longer names a file set aside that went with it (213).
        Help's check asks when it runs."""
        tools = self.desktop.tools
        if tools is not None:
            found = next(
                (t for t in tools.every if t.learning_unsaved or t.learning_set_aside),
                tools,
            )
            self.home.state.set_learning_set_aside(
                found.learning_set_aside, unsaved=found.learning_unsaved
            )

    def _follow_text_size(self) -> None:
        """The app's text size changed (Settings > App): every window at it
        now - the main window restyles and says so (`text_size_changed`:
        `interface` restyles the others). Only a change: what the settings
        had at start, `main` applied before the first window."""
        size = self.desktop.settings.value.app_text_size
        if size != self._text_size:
            self._text_size = size
            self.window.set_app_text_size(size)

    def _show_theme(self) -> None:
        value = self.desktop.settings.value
        self.settings.show_theme(value.theme, value.window_theme)
        self.settings.show_text_size(value.app_text_size)
        self.settings.show_interface_language(value.interface_language or "")
        self.settings.show_transcript_length(
            value.transcript_length, value.transcript_ask_at_quit
        )

    def show_plan(self, line: PlanLine) -> None:
        """The account's plan, on Home and Account (polyglotic-hq 185)."""
        self.home.state.set_plan(plan_text(line))
        self.account.show_plan(line)

    def show_learning(self) -> None:
        """Learning's page: the languages being learned, each with what its
        dictionary gives and its level, and the word introductions chosen."""
        value = self.desktop.settings.value
        tools = self.desktop.tools
        running = tools.language if tools is not None else None
        open_now = {t.language: t for t in tools.every} if tools is not None else {}

        def level_of(code: str) -> KnownLine | None:
            if code in open_now:  # open: live
                return open_now[code].vocabulary.line
            return self.level_of(code) if self.level_of is not None else None

        languages = value.learning_languages
        self._learning_shown = _learning_settings(value)
        packs = tuple(tools.basic) if tools is not None else ()
        delivery = self.packs
        # what "Learn another language" may say of a basic language (330)
        self.learning.pack_line = (
            delivery.line if delivery is not None else lambda _: None
        )
        self.learning.show_learning(
            languages,
            learning_cards(
                languages,
                tuple(open_now),
                level_of,
                packs,
                value.choices_for,
                delivery.line if delivery is not None else lambda _: None,
                self._quick_marks_of,
            ),
            value.word_introductions,
            running,
            chinese=tools.is_chinese if tools is not None else True,
        )
        if delivery is not None:
            self.learning.show_installed(delivery.installed_lines())
            delivery.wanted_list(languages.all)
        if self.words is not None and running is not None:  # whose words (299)
            self.words.show_in_use(tuple(open_now), value.learning)
        self._show_level_line()  # the languages learned decide it too

    def use_packs(self, packs: PackDelivery) -> None:
        """The dictionary packs (decision 0122): Learning's rows follow them,
        its buttons ask them, and Home says once when one is in or failed if
        the learner is elsewhere."""
        self.packs = packs
        packs.on_learning = lambda: (
            self.window.isVisible() and self.window.current == "learning"
        )
        packs.changed.connect(self.show_learning)
        packs.line_changed.connect(
            lambda code: self.learning.show_pack(code, packs.line(code))
        )
        self.learning.pack_wanted.connect(packs.asked)

    def _learning_settings_changed(self) -> None:
        """A setting changed: Learning's page again only if what it shows
        from the settings did - each showing reads another language's
        level from its file (polyglotic-hq 273: on every move of a drag)."""
        if _learning_settings(self.desktop.settings.value) != self._learning_shown:
            self.show_learning()

    def _learning_changed(self, what: str) -> None:
        if what == Changed.LEVEL.value:
            self.show_learning()
        elif what == Changed.LOAD.value:
            self._load_soon.start()

    def _wire_load_card(self) -> None:
        """Learning's card for the learning load (polyglotic-hq 324): what
        the learner asks there is done by the learner's tools, and the
        rules they choose are kept in the settings, which the load follows
        (`DesktopApp._follow_load_rules`)."""
        card = self.learning.load
        self._load_soon = QTimer(self.window)
        # a caption a second counts meetings: the card follows a few times a
        # second, and only while its page is in view
        self._load_soon.setSingleShot(True)
        self._load_soon.setInterval(250)
        self._load_soon.timeout.connect(self.show_load)
        self.learning.shown.connect(self.show_load)
        card.listed_chosen.connect(self.show_load)
        card.rules_chosen.connect(self._load_rules_chosen)

        def with_tools(act: Callable[[LearningTools], object]) -> None:
            if self.desktop.tools is not None:
                act(self.desktop.tools)

        card.checked.connect(
            lambda entry, knows: with_tools(
                lambda t: t.vocabulary.check_word(EntryId(entry), knows)
            )
        )
        card.known.connect(
            lambda entry: with_tools(
                lambda t: t.vocabulary.set_status(EntryId(entry), WordStatus.KNOWN)
            )
        )
        card.not_now.connect(
            lambda entry: with_tools(
                lambda t: t.vocabulary.set_aside_from_load(EntryId(entry))
            )
        )
        card.add_wanted.connect(
            lambda entry: with_tools(lambda t: t.add_to_load(EntryId(entry)))
        )
        card.add_next_wanted.connect(
            lambda count: with_tools(lambda t: t.add_next_to_load(count))
        )
        card.many_wanted.connect(
            lambda what, entries: with_tools(
                lambda t: for_picked_in_load(t, what, [EntryId(e) for e in entries])
            )
        )

    def show_load(self) -> None:
        """The learning load on Learning, as it is now - read only while
        the page is in view (it shows again when it comes into view)."""
        tools = self.desktop.tools
        card = self.learning.load
        if tools is None or not tools.vocabulary.load.on:
            card.show_load(None)
        elif self.learning.isVisible():
            card.show_load(
                load_view(
                    tools.vocabulary.load,
                    tools.describe,
                    datetime.now(UTC),
                    card.listed,
                    card.rows,
                ),
                tools.is_chinese,
            )

    def _load_rules_chosen(self, rules: object) -> None:
        tools = self.desktop.tools
        if tools is not None and isinstance(rules, LoadRules):
            settings = self.desktop.settings
            settings.update(**load_rules_changes(settings.value, tools.language, rules))

    def _show_level_line(self) -> None:
        """Home's line asking for the level, until the learner sets one or
        says Not now - the first run doesn't ask (polyglotic-hq 293). Only
        while there's a level to set: the language learned is the one in
        use, or none is chosen yet - not for a learner of languages with no
        levels (a basic dictionary, or none yet)."""
        tools = self.desktop.tools
        value = self.desktop.settings.value
        self.home.show_level_line(
            tools is not None
            and tools.vocabulary.line is None
            and not value.level_line_dismissed
            and (
                value.learning == tools.language
                or (value.learning is None and not value.also_learning)
            )
        )

    def _level_wanted(self) -> None:
        """The level line's Set your level: the level picker for the
        language learned, in use now; else Learning, where a language is
        chosen first - its card then has Change your level."""
        tools = self.desktop.tools
        if tools is not None and self.desktop.settings.value.learning == tools.language:
            self.change_level()
        else:
            self.window.go_to("learning")

    def _languages_wanted(self, languages: LearningLanguages) -> None:
        """Learning's page changed the languages being learned. One added
        whose learning data is open - the main language's, or any other full
        language's open beside it (306) - with no level set yet, is asked
        about how many words the learner knows - once, here, and skippable
        (polyglotic-hq 323); one that opens a moment later is asked as it
        opens (`language_opened`); Home's line still offers it after a
        skip. One stopped whose dictionary pack is on this PC asks whether
        to remove it too (decision 0122); a basic language added has its
        pack offered on its card."""
        settings = self.desktop.settings
        before = settings.value.learning_languages
        settings.update(**added_language_changes(settings.value, languages))
        tools = self.desktop.tools
        if tools is not None:
            for code in languages.all:
                # a full language; a pack language whose pack is here, so its
                # learning data opens in a moment too (decision 0175) - one
                # whose pack is still to download isn't asked out of the blue
                asked = tier_of(code) is Tier.FULL or code in tools.basic
                if before.learns(code) or not asked:
                    continue
                ours = tools.of(code)
                if ours.language != code:  # opens in a moment (`open_added`):
                    self._ask_level.add(code)  # asked then (`language_opened`)
                elif ours.vocabulary.line is None:
                    self.change_level(code)
                    break  # one question at a time
        packs = self.packs
        for code in before.all:
            removable = packs is not None and code in {
                p.code
                for p in packs.installed_lines()  # not the installer's own
            }
            if packs is None or languages.learns(code) or not removable:
                continue
            title, said, remove, keep = remove_question(code, packs.here[code][0].size)
            box = QMessageBox(
                QMessageBox.Icon.Question, title, said, parent=self.window
            )
            yes = box.addButton(remove, QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(keep, QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is yes:
                packs.remove(code)

    def _quick_marks(self, code: str) -> QuickMarks:
        """A language's Undo and Reset after quick marks (342)."""
        undo = self._undo_known.get(code)
        reset_to = self.desktop.settings.value.reset_point(code)
        return QuickMarks(reset_to, undo[0] if undo is not None else None)

    def _quick_marks_of(self, code: str) -> tuple[QuickMarks, int]:
        undo = self._undo_known.get(code)
        return self._quick_marks(code), undo[1] if undo is not None else 0

    def _set_quick_marks(self, code: str, marks: QuickMarks, marked: int = 0) -> None:
        """Keeps `marks`: Undo for this session, Reset in the settings."""
        if marks.undo_to is not None:
            self._undo_known[code] = (marks.undo_to, marked)
        else:
            self._undo_known.pop(code, None)
        settings = self.desktop.settings
        if settings.value.reset_point(code) != marks.reset_to:
            settings.update(**reset_point_changes(settings.value, code, marks.reset_to))

    def mark_first_known(self, code: str, first: int) -> None:
        """Learning's "Mark known" for the open language `code`: its known
        line moves to the first `first` words; Undo and Reset are offered
        (polyglotic-hq 342). Only forward: a number the line holds already
        marks nothing."""
        tools = self.desktop.tools
        if tools is None:
            return
        vocabulary = tools.of(code or None).vocabulary
        known = known_words.words_known(vocabulary.estimating)
        if not marks_more(known, first):
            return
        marks = self._quick_marks(code).marked(vocabulary.line)
        self._set_quick_marks(code, marks, first - (known or 0))
        vocabulary.set_known_words(first)  # Learning shown again, with Undo

    def undo_known(self, code: str) -> None:
        """Undo, right after a quick mark: the line as it was before it."""
        tools = self.desktop.tools
        undone = self._quick_marks(code).undone()
        if tools is None or undone is None:
            return
        before, marks = undone
        self._set_quick_marks(code, marks)
        tools.of(code or None).vocabulary.restore_line(before.line)

    def reset_known(self, code: str) -> None:
        """Reset, asked first with how many words it changes: the line as it
        was before the first quick mark. Words marked by hand stay."""
        tools = self.desktop.tools
        reset = self._quick_marks(code).reset()
        if tools is None or reset is None:
            return
        before, marks = reset
        vocabulary = tools.of(code or None).vocabulary
        back = before.line or KnownLine.starting(vocabulary.scheme)
        now, then = (
            known_words.words_known(vocabulary.estimating),
            known_words.words_known(back),
        )
        title, said = reset_question(
            learned_name(code),
            level_line(before.line),
            max(0, (now or 0) - (then or 0)),
        )
        if self.ask_reset(title, said):
            self._set_quick_marks(code, marks)
            vocabulary.restore_line(before.line)

    def _ask_reset(self, title: str, said: str) -> bool:
        """Reset's question over the main window: Reset, or Cancel (the
        default)."""
        box = QMessageBox(QMessageBox.Icon.Question, title, said, parent=self.window)
        yes = box.addButton(
            QApplication.translate("Learning", "Reset"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        answer = box.clickedButton() is yes
        box.deleteLater()
        return answer

    def change_level(self, code: str = "") -> None:
        """Words' and Learning's Change your level, Home's Set your level,
        and a language just added: about how many words do you know? - over
        the main window, for the open language `code` (a section of Words, a
        card on Learning; "": the main language; 306). The picker opens on
        the choice nearest the level now; OK makes it a line in words
        (polyglotic-hq 323)."""
        tools = self.desktop.tools
        if tools is None:
            return
        tools = tools.of(code or None)
        offered = known_words.choices(tools.language)
        picker = LevelPicker(
            learned_name(tools.language),
            offered,
            known_words.not_sure(tools.language),
            known_words.opens_on(offered, tools.vocabulary.line),
            self.window,
        )
        if picker.exec():
            # said another way: quick marks' Undo and Reset go (342)
            self._set_quick_marks(tools.language, QuickMarks())
            tools.vocabulary.set_known_words(picker.known())
        picker.deleteLater()

    def open_load(self) -> None:
        """Settings > Lab's "Open it on Learning": Learning, at the learning
        load's card - the language in use's (polyglotic-hq 342)."""
        self.window.go_to("learning")
        self.learning.scroll_to_load()

    def open_lab_load(self) -> None:
        """The learning load card's "Settings > Lab": Settings' Lab, at the
        switch that turns the load on and off (polyglotic-hq 342)."""
        self.window.go_to("settings")
        self.settings.show_section("lab")
        lab = self.settings.lab
        QTimer.singleShot(0, lambda: self.settings.ensureWidgetVisible(lab.load, 0, 80))

    def open_caption_settings(self) -> None:
        """A caption window's "All caption settings...": the main window in
        front, on Settings > Look, the first of the caption windows'
        sections (polyglotic-hq 304)."""
        self.window.go_to("settings")
        self.settings.show_section("look")
        self.show(picker=False)

    def open_dictation_settings(self) -> None:
        """The tray's "More languages…" for dictation: the main window in
        front, on Settings > Dictation (polyglotic-hq 283, 304)."""
        self.window.go_to("settings")
        self.settings.show_section("dictation")
        self.show(picker=False)

    def show(self, picker: bool = True) -> None:
        """The main window in front - on Home, where the learner picks
        what to caption, while nothing is chosen (with `picker`)."""
        if picker and not self.desktop.settings.value.source_chosen:
            self.window.go_to("home")
        if not self._shown:  # its first time: sized to the screen it opens on
            self._shown = True
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self.window.fit_to(screen.availableGeometry())
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def banner_in_view(self) -> bool:
        """Whether Home's banner is in front of the learner: the main window
        shown on Home, and it - or a dialog over it, such as the report
        just sent from - is the window in front (polyglotic-hq 279)."""
        window = self.window
        if not window.isVisible() or window.isMinimized() or window.current != "home":
            return False
        active = QApplication.activeWindow()
        while active is not None and active is not window:
            active = active.parentWidget()
        return active is window

    def _captioned(self, _source_id: str) -> None:
        """A finished caption shown: after a good session, "Start with
        Windows?" on Home - once ever (polyglotic-hq 176)."""
        self._captions += 1
        startup = self.startup
        value = self.desktop.settings.value
        if offer_start_with_windows(
            self._captions,
            value.start_with_windows_asked,
            startup is not None and startup.enabled(),
            startup is not None,
        ):
            self.desktop.settings.update(start_with_windows_asked=True)
            self.home.offer_start_with_windows()

    def _start_with_windows(self, yes: bool) -> None:
        if yes and self.startup is not None:
            self.startup.set_enabled(True)

    def close(self) -> None:
        """The window closes for good (the app is quitting)."""
        self.window.keep_in_tray = False
        self.window.close()

    def retheme(self) -> None:
        ratio = self.window.devicePixelRatioF()
        logo = icons.logo(round(style.px(28) * ratio), theme.current == "dark")
        logo.setDevicePixelRatio(ratio)
        self.window.set_theme(window_theme(), logo)

    def set_busy(self, busy: bool) -> None:
        """The server's pace hint: "Busy time" on Home's banner when it
        begins slowing the live updates the learner's timing shows - as the
        caption windows say it."""
        mode = self.desktop.settings.value.caption_mode
        if slowed_now(self.busy, busy, mode):
            self.home.state.set_notice(notice_text(Notice.BUSY, None))
        self.busy = busy

    def set_maintenance(self, window: Maintenance | None) -> None:
        """The planned maintenance window the app holds: Home's banner and
        state line say it (polyglotic-hq 319)."""
        self.home.state.set_maintenance(window)
        self.follow()

    def set_update_found(self, found: UpdateNow) -> None:
        """What the updater found after "update required": Home says what
        to do while the server refuses this version."""
        self.update_found = found
        self.follow()

    def _picker(self) -> Picker:
        return picker_of(
            self.desktop.settings.value,
            self.apps.playing_apps(),
            self.per_app,
            self.windows,
            self.desktop.hide_windows.isChecked(),
            (
                self.sample is not None
                and self._has_sample(
                    sample_language(self.desktop.settings.value, self.desktop.tools)
                ),
                self.sample_on,
            ),
            self.sample_ended,
            self.fell_back,
        )

    def _has_sample(self, learning: str | None) -> bool:
        """Whether there's a sample in `learning`: looked for once per
        language, not on every setting changed (polyglotic-hq 273) - the
        samples come with the app."""
        found = self._samples.get(learning)
        if found is None:
            found = self._samples[learning] = sample_file(learning) is not None
        return found

    def _connection_changed(self, _state: object, retry_in: float | None) -> None:
        """The session's state changed: Home's countdown runs to the next
        try from now, not from whenever Home is next drawn."""
        now = time.monotonic()
        self._retry_at = now + retry_in if retry_in is not None else None
        if self.desktop.connection is ConnectionState.SIGN_IN_NEEDED:
            self.home.state.set_plan(None)  # the plan was the account's
        self.follow()

    # -- Sound (polyglotic-hq 372): `SoundCommands` ----------------------------------

    def _sound(self) -> Sound:
        """Home's Sound as the settings and the windows are now - the
        devices and the level as last found."""
        value = self.desktop.settings.value
        kept = getattr(self, "sound", None)
        return Sound(
            kept.value.devices if kept is not None else SoundDevices(),
            value.speaker_device,
            value.mic_device,
            value.whole_system,
            self.windows.show_mic_anywhere,
            kept.value.level if kept is not None else None,
        )

    def set_speaker_device(self, device: str | None) -> None:
        self.desktop.settings.update(speaker_device=device)

    def set_mic_device(self, device: str | None) -> None:
        self.desktop.settings.update(mic_device=device)

    def set_my_speech(self, on: bool) -> None:
        """In every window, as the tray's "Caption my own speech"."""
        self.desktop.caption_mic.setChecked(on)

    def sound_devices(self) -> SoundDevices:
        return self.list_devices()

    def mic_peak(self) -> float | None:
        return self.read_mic_peak()

    def follow(self) -> None:
        value = self.desktop.settings.value
        state = self.desktop.connection
        picker = self._picker()
        self.picker.follow(picker)
        self.sound.follow(self._sound())
        self.home.show_joined(
            self.windows.joined_window is not None, len(self.windows.windows)
        )
        # the sample's window, kept for lookups once it has ended, captions
        # nothing: no language in use, nor a window (208's finding; 213)
        kept = SOURCE_KEY_SAMPLE if self.sample_ended and not self.sample_on else None
        self.home.show_state(
            HomeState(
                connection=ListeningState(state.value),
                retry_at=self._retry_at,
                paused=self.desktop.pause.isChecked(),
                # the sample playing is captioning: Home follows its session
                chosen=value.source_chosen or self.sample_on,
                languages=tuple(self.panels.in_use(leaving_out=kept)),
                windows=sum(key != kept for key in self.windows.windows),
                speech_shown=self.windows.show_mic_anywhere,
                update_found=self.update_found,
                unreachable=self.desktop.unreachable,
                windows_paused_after=every_window_paused(picker.captioned),
            )
        )
        self.desktop.show_state_title(self.home.state.title_label.text())
        self.desktop.show_hidden(*hidden_line(picker.captioned))

    # -- the picker's commands ----------------------------------------------------------

    def add(self, name: str) -> None:
        changes = adding_app(self.desktop.settings.value, name)
        if changes is not None:
            self.desktop.settings.update(**changes)

    def remove(self, key: str) -> None:
        value = self.desktop.settings.value
        self.desktop.settings.update(**stop_captioning(value, key))

    def rename(self, key: str, text: str) -> None:
        own = next(
            (a.title for a in self.apps.playing_apps() if a.name == key),
            {
                SOURCE_KEY_SYSTEM: pc_or_mac(_tr_app("This PC"), _tr_app("This Mac")),
                SOURCE_KEY_EVERYTHING_ELSE: _tr_app("Everything else"),
                SOURCE_KEY_MIC: _tr_app("You"),
            }.get(key, key),
        )
        value = self.desktop.settings.value
        self.desktop.settings.update(**renaming(value, key, text, own))

    def recolour(self, key: str, colour: str) -> None:
        colours = dict(self.desktop.settings.value.source_colors)
        colours[key] = colour
        self.desktop.settings.update(source_colors=colours)

    def show_window(self, key: str) -> None:
        """Home's Captions: its window - hidden, every window shown again,
        as Ctrl+Alt+H would (polyglotic-hq 335: "show it to carry on")."""
        if self.desktop.hide_windows.isChecked():
            self.desktop.hide_windows.setChecked(False)
        else:
            self.windows.show_window(key)

    def open_transcript(self, key: str) -> None:
        self.windows.transcript_wanted.emit(key)

    def set_whole_system(self, on: bool) -> None:
        self.desktop.settings.update(whole_system=on)

    def set_everything_else(self, on: bool) -> None:
        changes = everything_else_change(self.desktop.settings.value, on)
        if changes is not None:
            self.desktop.settings.update(**changes)

    def set_show_mic(self, key: str, on: bool) -> None:
        self.windows.set_show_mic(key, on)
        self.follow()

    def set_translate_into(self, key: str, code: str) -> None:
        self.windows.set_language(key, code)
        self.follow()

    def refresh(self) -> None:
        self.apps.look()

    def try_sample(self, on: bool) -> None:
        if self.sample is not None:
            self.sample(on)

    def try_apps_again(self) -> None:
        if self.apps_again is not None:
            self.apps_again()


@dataclass
class Interface:
    """The new interface's parts as `main` builds them: the caption windows,
    the transcripts, the shared panels and the main window."""

    windows: CaptionWindows
    transcripts: Transcripts
    panels: Panels
    hub: Hub

    def close(self) -> None:
        """Every window closed, their choices saved (the app is quitting) -
        and a look change still settling."""
        self.panels.save_look()
        self.transcripts.close()
        self.windows.close()
        self.hub.close()


class LearningOffer:
    """The lookup card's "Learn it too?" (`views.lookup.LanguagesOffer`): the
    languages being learned, as the settings keep them for Learning's page
    (DECISIONS.md #65, polyglotic-hq 262)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.packs: PackDelivery | None = None
        """The dictionary packs (`main`, after the start): a language added
        here says its pack's size (decision 0122)."""

    def asks_about(self, caption_language: str | None) -> str | None:
        return self.settings.value.learning_languages.asks_about(caption_language)

    def learn_too(self, code: str) -> None:
        languages = self.settings.value.learning_languages
        value = self.settings.value
        self.settings.update(**added_language_changes(value, languages.added(code)))

    def not_now(self, code: str) -> None:
        languages = self.settings.value.learning_languages
        self.settings.update(**learning_changes(languages.declined(code)))

    def pack_size(self, code: str) -> int:
        if self.packs is None or code in self.packs.here:
            return 0
        return self.packs.line(code).size


PACKS = UPDATES
"""Where the dictionary packs' signed list and files are (decision 0122):
the update storage, under `packs/`. `--packs-from` overrides it to try a
stand-in on this PC, checked against `--packs-key` as well as `FEED_KEYS`."""
PACKS_AFTER_START_MS = 1500  # the packs are opened after the first paint (322)
PAGES_STYLED_AFTER_START_MS = 1000
"""The main window's pages not on show get its stylesheet this long after
the first paint, one a turn (`MainWindow.style_ahead`, decision 0158)."""
PACK_UPDATES_AFTER_START_MS = 120_000
PACK_UPDATES_EVERY_MS = 24 * 3600 * 1000
"""A newer version of a pack on this PC: looked for two minutes after the
start, then once a day (decision 0122's bandwidth rule)."""
_READ_OR_NONE = (None, Problem.NOT_OFFERED)
"""A refresh's outcomes that say whether a pack can be had: the list read,
or none published."""
LIST_AGAIN_SEC = 600.0
"""Learning asks for the list again at most this often once it has one (a
download asks for it every time)."""
PACK_OLD_CLOSED_AFTER_MS = 2000
"""A replaced pack's file is closed this long after the new one is in: a
lookup under way on another thread finishes on it first."""


def pack_meanings(interface: str) -> str:
    """The meanings language a pack is downloaded in: Chinese for a Chinese
    interface, else English (every pack has English; polyglotic-hq 326
    looks at more)."""
    return "zh" if interface.lower().startswith("zh") else "en"


def pack_reader(version: str) -> Reader:
    """What this app reads: its dictionary format, the word splits it has -
    letters always (simplemma's guesses only where it's installed: decision
    0123), Vietnamese's always (plain Python over the pack's own words:
    decision 0121), French's elided words always (polyglotic-hq 341), a
    word's combining marks and Arabic's, Indonesian's and Hindi's
    clitics and endings always (polyglotic-hq 380), Turkish's suffixes always
    (polyglotic-hq 388), Persian's words kept whole at their zero-width
    non-joiner (`joiners`) and Filipino's, Czech's and Greek's affixes
    guessed (`affixes`) always (polyglotic-hq 387), Thai's always (plain
    Python over the pack's own words: decision 0173), Sudachi only with its
    dictionary - and its version."""
    splits = {
        *("spaced", "elided", "marks", "clitics", "turkish", "vietnamese"),
        *("joiners", "affixes", "thai"),
    }
    if all(
        importlib.util.find_spec(m) is not None
        for m in ("sudachipy", "sudachidict_small")
    ):
        splits.add("japanese")
    return Reader(frozenset({DICTIONARY_FORMAT}), frozenset(splits), version)


def open_pack(path: Path, language: str) -> tuple[BasicDictionary, SqliteDictionary]:
    """A pack file as its language's basic dictionary, with its word split -
    and its file, for closing."""
    file = SqliteDictionary(path)
    # imported here: a pack opens after the first paint (400)
    from polyglotic_desktop.core.lexicon.thai import ThaiSplit

    split: WordSplit = (
        JapaneseSplit()
        if language == "ja"
        else VietnameseSplit(file)
        if language == "vi"
        else ThaiSplit(file)
        if language == "th"
        else SpacedSplit(language)
    )
    return BasicDictionary(file, split, language), file


class PackDelivery(QObject):
    """Dictionary packs onto this PC and into the lookups (decision 0122):
    the downloads' steps moved from their thread to this one, Learning's
    rows kept current, each pack opened as it arrives - no restart - and
    the one it replaces closed, then deleted.

    `basic` is the lookups' own: every learner's tools read it (`LearningTools.basic`),
    so a pack put in it is looked up from the next hover."""

    _progress = Signal(object)  # a PackProgress, from the downloads' thread
    _installed = Signal(object, object)  # a PackOffer and its path, from there
    _listed = Signal(object, object)  # the offers (or None) and why, from there
    changed = Signal()
    """Learning's cards change: a pack in or out, or the list arrived."""
    line_changed = Signal(str)
    """A language's pack line changed: its row only (`line`)."""
    notice = Signal(str)
    """Home's notice, once (the learner isn't on Learning)."""

    def __init__(
        self,
        folder: Path,
        basic: dict[str, BasicDictionary],
        meanings: str,
        reader: Reader,
        address: str = PACKS,
        keys: Sequence[str] = FEED_KEYS,
        metered: Callable[[], bool] = lambda: False,
        also: Sequence[Path] = (),
        open_url: Any = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.folder_path = folder
        self.also = tuple(also)
        self.basic = basic
        self.meanings = meanings
        self.reader = reader
        self._address = address
        self._keys = tuple(keys)
        self._metered = metered
        self._open_url = open_url
        self.deliveries: PackDeliveries | None = None
        self.progress: dict[str, PackProgress] = {}
        self.here: dict[str, tuple[InstalledPack, Path]] = {}
        """The packs open for lookups, by language."""
        self._files: dict[str, SqliteDictionary] = {}  # each one's file, to close
        self.offers: tuple[PackOffer, ...] | None = None
        self.list_problem: Problem | None = None
        """Why the last refresh couldn't read the list (None: it did, or none
        was tried): `NOT_OFFERED`, none published (a 404) - no dictionary is
        ready, whatever list is kept; anything else, it couldn't be checked
        (polyglotic-hq 330)."""
        self._list_asked = -LIST_AGAIN_SEC  # when Learning last asked for the list
        self.on_learning: Callable[[], bool] = lambda: False
        """Whether the learner is looking at Learning (`main`): no notice then."""
        self._asked: set[str] = set()  # downloads the learner asked for, this run
        self._progress.connect(self._step)
        self._installed.connect(self._in)
        self._listed.connect(self._list)

    # -- the start --------------------------------------------------------------

    def start(self) -> None:
        """After the first paint: the packs on this PC opened for lookups,
        older versions left by an update deleted, and the downloads' thread
        started (the list fetched if a learned language needs it)."""
        from polyglotic_desktop.adapters.pack_downloads import (
            PackDeliveries,
            PackFolder,
        )
        from polyglotic_desktop.adapters.pack_list import PackList
        from polyglotic_desktop.adapters.signed_feed import fetch, public_keys

        folder = PackFolder(self.folder_path, self.also)
        for (language, meanings), (pack, path) in sorted(folder.installed().items()):
            held = self.here.get(language)
            if held is not None and held[0].meanings == self.meanings:
                continue  # the learner's meanings first, else English
            if meanings != self.meanings and meanings != "en":
                continue
            self._open(pack, path)
        removed = folder.remove(folder.outdated())
        if removed:
            log.info("dictionary packs: %d bytes of older versions deleted", removed)
        packs = PackList(
            self._address,
            public_keys(self._keys),
            self.folder_path / "list",
            get=lambda url: fetch(url, self._open_url),
        )
        self.deliveries = PackDeliveries(
            packs,
            folder,
            self.reader,
            self._progress.emit,
            self._installed.emit,
            self._listed.emit,
            metered=self._metered,
            open_url=self._open_url,
        )
        self.offers = self.deliveries.offers
        log.info(
            "dictionary packs: %s open; list %s",
            ", ".join(
                f"{l}/{p.meanings} {p.version}"
                for l, (p, _) in sorted(self.here.items())
            )
            or "none",
            "kept" if self.offers is not None else "not fetched yet",
        )

    def wanted_list(self, codes: Sequence[str]) -> None:
        """Learning shows `codes`' cards: fetch the list if one of them is a
        basic language without its pack (its size is said)."""
        if self.deliveries is None:
            return
        missing = [c for c in codes if tier_of(c) is Tier.BASIC and c not in self.here]
        now = time.monotonic()
        recent = self.offers is not None and now - self._list_asked < LIST_AGAIN_SEC
        if missing and not recent:  # Learning shows often; the list changes rarely
            self._list_asked = now
            self.deliveries.refresh()

    def check_updates(self) -> None:
        """A newer version of each pack on this PC, fetched quietly - only on
        a connection Windows doesn't call metered; on one, Learning offers
        Get it now (decision 0122)."""
        if self.deliveries is None or not self.here:
            return
        for language, (pack, _) in sorted(self.here.items()):
            self.deliveries.want(language, pack.meanings, update=True)

    # -- what Learning shows ------------------------------------------------------

    def line(self, code: str) -> PackLine:
        here = self.here.get(code)
        none_published = self.list_problem is Problem.NOT_OFFERED  # a 404 (330)
        offers = None if none_published else self.offers  # what can be had now
        offer = (
            best_offer(offers, code, self.meanings, self.reader)
            if offers is not None
            else None
        )
        update = (
            update_for(here[0], offers, self.reader)
            if here is not None and offers is not None
            else None
        )
        progress = self.progress.get(code)
        if progress is not None and progress.update and progress.problem is None:
            progress = None  # quiet, until it's in
        newer_app = (
            offers is not None
            and here is None
            and needs_newer_app(offers, code, self.meanings, self.reader)
        )
        return PackLine(
            size=offer.gz_size if offer is not None else 0,  # what comes down
            installed_version=here[0].version if here is not None else "",
            installed_size=here[0].size if here is not None else 0,
            progress=progress,
            newer_app=newer_app,
            update_size=(
                update.gz_size if update is not None and self._metered() else 0
            ),
            credits=offer.credits if offer is not None else "",
            # no list held, and the last try couldn't read one: unknown
            unlisted=self.offers is None and self.list_problem not in _READ_OR_NONE,
            # the list held has nothing for it, or none is published: no
            # dictionary yet (330)
            not_offered=(
                (offers is not None or none_published)
                and here is None
                and offer is None
                and not newer_app
            ),
        )

    def installed_lines(self) -> list[InstalledPackLine]:
        return [
            InstalledPackLine(code, pack.version, pack.size)
            for code, (pack, path) in sorted(self.here.items())
            if path.parent == self.folder_path  # the installer's own can't go
        ]

    # -- what's asked ---------------------------------------------------------------

    def asked(self, code: str, action: str) -> None:
        """Learning's buttons: `download`, `retry`, `anyway`, `update`,
        `cancel`, `remove`."""
        if self.deliveries is None:
            return
        log.info("dictionary pack %s: %s asked", code, action)
        if action == "cancel":
            self.deliveries.cancel(code)
        elif action == "remove":
            self.remove(code)
        else:
            self._asked.add(code)
            self.deliveries.want(
                code, self.meanings, metered_ok=action in ("anyway", "update")
            )

    def remove(self, code: str) -> None:
        """Its pack out of the lookups, closed, and deleted from this PC - one
        the learner downloaded; the installer's own stays (decision 0124)."""
        if code in self.here and self.here[code][1].parent != self.folder_path:
            return
        held = self.here.pop(code, None)
        self.basic.pop(code, None)
        file = self._files.pop(code, None)
        if file is not None:
            file.close()
        if held is not None and self.deliveries is not None:
            freed = self.deliveries.folder.remove([held[1]])
            log.info("dictionary pack %s: removed, %d bytes freed", code, freed)
        self.progress.pop(code, None)
        self.changed.emit()

    # -- from the downloads' thread, on this one --------------------------------

    @Slot(object)
    def _step(self, progress: PackProgress) -> None:
        code = progress.language
        if progress.step is PackStep.CANCELLED:
            self.progress.pop(code, None)
        else:
            self.progress[code] = progress
        self.line_changed.emit(code)
        if progress.stopped and not progress.update:
            self._tell(code, failed_notice(code))

    @Slot(object, object)
    def _in(self, offer: PackOffer, path: Path) -> None:
        """A pack in: opened, put in the lookups in place of any older one
        (closed a little later, then deleted)."""
        from polyglotic_desktop.adapters.pack_downloads import PackFolder

        old = self.here.get(offer.language)
        try:
            pack = InstalledPack(
                offer.language,
                offer.meanings,
                offer.dictionary,
                offer.version,
                path.name,
                offer.size,
            )
            self._open(pack, path)
        except (DictionaryFormatError, DictionaryDamaged, OSError) as e:
            log.warning(
                "dictionary pack %s: not opened: %s", offer.language, type(e).__name__
            )
            return
        self.progress.pop(offer.language, None)
        if old is not None and old[1] != path:
            replaced = old[1]
            log.info(
                "dictionary pack %s: %s replaces %s",
                offer.language,
                offer.version,
                old[0].version,
            )

            def delete() -> None:
                PackFolder(self.folder_path).remove([replaced])

            QTimer.singleShot(PACK_OLD_CLOSED_AFTER_MS + 500, delete)
        self.changed.emit()
        if offer.language in self._asked:
            self._asked.discard(offer.language)
            self._tell(offer.language, ready_notice(offer.language))

    @Slot(object, object)
    def _list(
        self, offers: tuple[PackOffer, ...] | None, problem: Problem | None
    ) -> None:
        """The list as the downloads' thread found it (the one kept if it
        couldn't be read, None if none is), and why it couldn't: Learning
        then says so rather than "checking" for good - and none published
        (a 404) as no dictionary to download yet (330)."""
        if offers != self.offers or problem != self.list_problem:
            self.offers, self.list_problem = offers or self.offers, problem
            self.changed.emit()

    def _open(self, pack: InstalledPack, path: Path) -> None:
        dictionary, file = open_pack(path, pack.language)
        old = self._files.get(pack.language)
        self.basic[pack.language] = dictionary
        self._files[pack.language] = file
        self.here[pack.language] = (pack, path)
        if old is not None:  # a lookup on another thread finishes on it first
            QTimer.singleShot(PACK_OLD_CLOSED_AFTER_MS, old.close)
        threading.Thread(  # its word split reads its data, off this thread
            target=dictionary.words, args=("a",), name="pack warm", daemon=True
        ).start()

    def _tell(self, code: str, text: str) -> None:
        if not self.on_learning():
            self.notice.emit(text)

    def close(self) -> None:
        """At the end: the downloads' thread stops after its step; the packs'
        files are closed."""
        if self.deliveries is not None:
            self.deliveries.close()
        for file in self._files.values():
            file.close()


def new_interface(
    desktop: DesktopApp,
    store: SettingsStore,
    tools: LearningTools | None,
    per_app: bool,
    keys: KeyState | None = None,
    on_top: OnTop | None = None,
    common_apps: Sequence[CommonApp] = (),
) -> Interface:
    """The interface on the app (decisions 0031 and 0032): a caption window
    per app captioned, a transcript per app, the panels they share and the
    main window - for `main` and for `check_install` alike. `keys`: Windows'
    key state (`platform.windows.keys.held`), for the settings popovers;
    `on_top`: Windows' always-on-top band (`platform.windows.on_top`), to
    keep the caption windows above a game that is itself always on top;
    `common_apps`: browsers and the main apps a window's Captioning list
    shows before they play (F12, 249)."""
    windows = CaptionWindows(
        store, MIC, parent=desktop, keys=keys, learner=tools, on_top=on_top
    )
    found_apps = desktop.apps
    assert found_apps is not None  # the app is always given an app list

    def choices_for(key: str) -> list[AppChoice]:
        value = desktop.settings.value
        # the hub's: everything the PC plays from when trying apps fails (0076)
        if not hub.per_app or value.whole_system or key not in value.apps:
            return []  # everything the PC plays, the mic, the sample: no apps
        found = [(a.name, a.title, a.playing) for a in found_apps.playing_apps()]
        common = [(a.name, a.title) for a in common_apps]
        return app_choices(found, common, key, value.apps)

    def switch(key: str, name: str) -> None:
        changes = switching_app(desktop.settings.value, key, name)
        if changes is not None:
            windows.carry(key, name)  # the new app opens where the old one was
            desktop.settings.update(**changes)

    windows.app_choices = choices_for
    windows.app_wanted.connect(switch)
    if windows.card is not None:  # "Learn Japanese too?" (polyglotic-hq 262)
        windows.card.model.offer = LearningOffer(desktop.settings)
    # every save dialog opens where the last save went, or in Documents -
    # never the install folder an update replaces (polyglotic-hq 244)
    save_folder = SaveFolder(store)
    transcripts = Transcripts(
        windows, store, learner=tools, parent=desktop, save_folder=save_folder
    )
    panels = Panels(desktop.settings, windows)
    windows.links_wanted.connect(panels.look.set_links_shown)  # a window's button
    windows.fill_wanted.connect(panels.look.set_filled)  # and its filled lines (372)
    windows.aligned_wanted.connect(panels.look.set_lined_up)  # and parts lined up
    transcripts.panels = panels  # their rails show the same panels
    start_parts.done("caption_windows")  # with the transcripts and panels
    hub = Hub(
        desktop,
        windows,
        panels,
        found_apps,
        per_app,
        save_folder,
        OpenLanguages(store),
    )
    start_parts.done("hub")  # the main window's wiring, after its pages
    # the text size changed - Windows' or the app's own (Settings > App)
    hub.window.text_size_changed.connect(transcripts.restyle)
    hub.window.text_size_changed.connect(windows.restyle)  # their chrome
    hub.window.text_size_changed.connect(hub.retheme)  # the logo, at its size
    menu = desktop.tray_menu  # and Qt's other own parts (`style.size_qt_parts`)
    hub.window.text_size_changed.connect(lambda: style.size_qt_parts(menu))
    menu.aboutToShow.connect(lambda: style.size_qt_parts(menu))  # later submenus
    style.size_qt_parts(menu)
    return Interface(windows, transcripts, panels, hub)


def connection_state(
    status: Status, shown: ConnectionState | None = None
) -> tuple[ConnectionState, float | None]:
    """The session's state as Home shows it - and the caption windows and
    transcripts. `shown`: the state shown now. While reconnecting, each try
    is still "Reconnecting" (no countdown while it tries), not "Connecting":
    the windows' notice would go blank for each try (polyglotic-hq 133).
    Likewise "Update needed" stays while the session asks the server again
    whether it takes this version (polyglotic-hq 137), and "Plus has ended"
    while it asks whether the account has Plus again (polyglotic-hq 203)."""
    from polyglotic_desktop.connection.reconnect import StopReason
    from polyglotic_desktop.connection.session import SessionState

    if status.state is SessionState.CONNECTING and shown in (
        ConnectionState.WAITING,
        ConnectionState.SERVER_BUSY,
        ConnectionState.UPDATE_NEEDED,
        ConnectionState.PLUS_ENDED,
    ):
        return shown, None
    if status.state is SessionState.STOPPED:
        return {
            StopReason.SIGN_IN_NEEDED: ConnectionState.SIGN_IN_NEEDED,
            StopReason.UPDATE_REQUIRED: ConnectionState.UPDATE_NEEDED,
            StopReason.LISTENING_MOVED: ConnectionState.MOVED,
            StopReason.LIMIT_REACHED: ConnectionState.PLUS_ENDED,  # 4009 (185)
        }.get(status.stopped or StopReason.CLOSED, ConnectionState.STOPPED), None
    if status.state is SessionState.WAITING and status.server_busy:
        return ConnectionState.SERVER_BUSY, status.retry_in  # not the learner's (208)
    return {
        SessionState.CONNECTING: ConnectionState.CONNECTING,
        SessionState.LISTENING: ConnectionState.LISTENING,
        SessionState.WAITING: ConnectionState.WAITING,
    }[status.state], status.retry_in


def unreachable_shown(
    status: Status,
    shown: ConnectionState | None = None,
    said: Unreachable | None = None,
) -> Unreachable | None:
    """Why the server can't be reached, as Home and the caption windows say
    it: the session's while it waits to try again - and through each try,
    as "Reconnecting" stays (`connection_state`), so the reason doesn't
    blank for each try. `said`: the reason said now (polyglotic-hq 251)."""
    from polyglotic_desktop.connection.session import SessionState

    if status.state is SessionState.WAITING and not status.server_busy:
        return status.unreachable
    if status.state is SessionState.CONNECTING and shown is ConnectionState.WAITING:
        return said
    return None


Listener = Callable[[Found, Update | None, Update | None], None]
"""What a look found, what's downloaded and what's held (`BackgroundUpdates`)."""


class BackgroundUpdates:
    """Core's update rules on a thread of their own, one call at a time, so
    the network never holds up start-up or the interface (decision 0017).
    A failure - no network, no feed yet - is logged, never raised. What
    each look found goes to `tell`'s listener, on this thread - the last
    one at once to a listener that comes later: the first look runs before
    the interface is built (polyglotic-hq 299)."""

    def __init__(self, updates: Updates) -> None:
        self.updates = updates
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="updates")
        self._lock = threading.Lock()
        self._listener: Listener | None = None
        self._last: tuple[Found, Update | None, Update | None] | None = None

    def check(self) -> None:
        self._worker.submit(self._run, "check", self._look)

    def download_anyway(self) -> None:
        """The learner's Download anyway, on a metered connection (345):
        what was held is downloaded, and the listener told."""
        self._worker.submit(
            self._run,
            "download anyway",
            lambda: self._tell(self.updates.download_anyway()),
        )

    def tell(self, listener: Listener) -> None:
        """`listener(found, downloaded, held)` after each look, from this
        thread: `held`, an update found on a metered connection and not
        downloaded."""
        with self._lock:
            self._listener, last = listener, self._last
        if last is not None:
            listener(*last)

    def _look(self) -> None:
        self._tell(self.updates.look())

    def _tell(self, found: Found) -> None:
        if found not in (Found.UP_TO_DATE, Found.READY):
            log.info("updates: %s", found.value)
        with self._lock:
            self._last = (found, self.updates.downloaded, self.updates.held)
            listener, last = self._listener, self._last
        if listener is not None:
            listener(*last)

    def follow(self, channel: str | None) -> None:
        def follow_then_check() -> None:
            if self.updates.follow(channel):
                log.info("following the server's update channel")
                self._look()

        self._worker.submit(self._run, "follow", follow_then_check)

    def restart_when_quitting(self) -> None:
        """The learner's Restart now: what's downloaded applies as the app
        quits, then the new version starts - before `at_exit`, on this
        thread (polyglotic-hq 299)."""
        self._worker.submit(
            self._run, "restart now", self.updates.restart_when_quitting
        )

    def update_now(self, found: Callable[[UpdateNow], None]) -> None:
        """Straight to the updater; `found` is told what it found, on the
        updates' thread - after a failure, whether a downloaded update
        installs at the next start."""

        def update_now_then_say() -> None:
            try:
                outcome = self.updates.update_now()
            except Exception:
                downloaded = self.updates.downloaded is not None
                found(UpdateNow.DOWNLOADED if downloaded else UpdateNow.NONE_YET)
                raise
            found(outcome)

        self._worker.submit(self._run, "update now", update_now_then_say)

    def at_exit(self) -> None:
        """At quit: what must apply as the app exits, then stop."""
        done = self._worker.submit(self._run, "at exit", self.updates.at_exit)
        try:
            done.result(timeout=UPDATES_AT_EXIT_SEC)
        except TimeoutError:
            log.warning("updates: still busy at quit")
        self._worker.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _run(name: str, call: Callable[[], object]) -> None:
        try:
            call()
        except Exception as e:  # noqa: BLE001 - the app runs on without updates
            log.warning("updates: %s failed (%s)", name, _update_failure(e))


def _update_failure(problem: Exception) -> str:
    """A failed update step as the log says it (`signed_feed.failure_named`)."""
    from polyglotic_desktop.adapters.signed_feed import failure_named

    return failure_named(problem)


class UpdateShown(QObject):
    """What the updates found, on the interface thread (polyglotic-hq
    299): a downloaded update offered on Home - "Version X is ready", what's
    new in two lines, Restart now and Later - and in the tray's menu;
    Settings says what the last look found. Never a window of its own over
    a game or a call, and nothing restarts by itself: Restart now quits as
    Quit does, then the installer applies it and starts the new version.
    On a metered connection, an update found isn't downloaded: Home's card
    says how big it is, with Download anyway (polyglotic-hq 345)."""

    _found = Signal(object, object, object)

    def __init__(
        self,
        home: HomePage,
        desktop: DesktopApp,
        settings: SettingsPage | None,
        restart: Callable[[], None],
        download_anyway: Callable[[], None] = lambda: None,
    ) -> None:
        """`settings`: Settings' Updates card (None for the Microsoft
        Store's copy, which the Store updates). `restart`: Restart now;
        `download_anyway`: Download anyway, on a metered connection."""
        super().__init__(desktop)
        self.offer = RestartOffer()
        self.home, self.desktop, self.settings = home, desktop, settings
        self._found.connect(self._show, Qt.ConnectionType.QueuedConnection)
        home.restart_wanted.connect(restart)
        home.update_later.connect(self._later)
        home.download_anyway_wanted.connect(download_anyway)
        desktop.install_update.triggered.connect(restart)
        if settings is not None:
            settings.restart_wanted.connect(restart)

    def found(
        self, found: Found, downloaded: Update | None, held: Update | None = None
    ) -> None:
        """A look's outcome, from the updates' thread: `held`, an update
        found on a metered connection and not downloaded."""
        self._found.emit(found, downloaded, held)

    @Slot(object, object, object)
    def _show(
        self, found: Found, downloaded: Update | None, held: Update | None
    ) -> None:
        if self.offer.found(downloaded, held):
            asking = self.offer.asking or self.offer.asking_to_download
            if asking is not None:
                log.info(
                    "update %s offered on Home%s",
                    asking.version,
                    "" if self.offer.asking else " to download (metered)",
                )
        # each time: a Download anyway that failed shows its button again
        if (asking := self.offer.asking) is not None:
            self.home.show_update(asking.version, whats_new(asking.notes))
        elif (waiting := self.offer.asking_to_download) is not None:
            self.home.show_update(
                waiting.version, whats_new(waiting.notes), metered_size=waiting.size
            )
        else:
            self.home.show_update(None)
        version = downloaded.version if downloaded else None
        self.desktop.show_update_ready(version)
        if self.settings is not None:  # ready, whatever this look found
            self.settings.show_update(
                Found.READY.value if version else found.value,
                version or (held.version if held else None),
            )

    def _later(self) -> None:
        log.info("update: Later - asked again at the next start")
        self.offer.later()
        self.home.show_update(None)


def plan_shown(plan: protocol.PlanState) -> PlanShown:
    """The server's plan as the plan line reads it. A date that can't be
    read is left out: the line then names no date rather than a wrong one."""
    from polyglotic_desktop.connection.protocol import parse_at

    until = None
    if plan.until is not None:
        with contextlib.suppress(ValueError):
            until = parse_at(plan.until)
    code = plan.message.code if plan.message is not None else None
    return PlanShown(plan.tier, plan.source, plan.status, until, code)


class DictationKeyHeld:
    """Dictation's key, taken from the OS as the settings say
    (polyglotic-hq 283, 289): let go while Settings' key box listens for a
    new one; a key pressed there tried before it's kept - one another
    program has leaves the key before."""

    def __init__(self, hold_key: Callable[[str], HoldKey]) -> None:
        """`hold_key`: the OS's key, as kept ("right_ctrl"), not started."""
        self._hold_key = hold_key
        self._key: HoldKey | None = None
        self.held_as: str | None = None
        """The key held now, as kept; None: none."""
        self.taken = False
        """Another program had the key when it was last taken."""
        self.box_listening = False

    def follow(self, on: bool, key: str) -> bool:
        """Dictation on or off, and its key: taken, or let go. True if
        that changed anything."""
        wanted = key if on and not self.box_listening else None
        if wanted == self.held_as:
            return False
        self.stop()
        self.taken = False
        if wanted is not None:
            self._key = self._hold_key(wanted)
            self.taken = not self._key.start()
            self.held_as = wanted
        return True

    def try_key(self, wanted: str, on: bool) -> bool:
        """A key pressed in Settings: False if another program has it
        (`follow` then takes the one before again); else True - and held
        now, if dictation is `on`."""
        self.stop()  # the key before may share keys with it
        trial = self._hold_key(wanted)
        if not trial.start():
            trial.stop()
            return False
        if on and not self.box_listening:
            self._key, self.held_as = trial, wanted
        else:
            trial.stop()
        return True

    def stop(self) -> None:
        if self._key is not None:
            self._key.stop()
        self._key, self.held_as = None, None


class QtListener(QObject):
    """The session's listener: its calls come on the session's thread and
    go to the interface on the Qt thread. The channel the server names, and
    its "update required", go to the updates."""

    _status = Signal(object)
    _minutes = Signal(float, object)
    _notice = Signal(str)
    _failed = Signal()
    _stalled = Signal(bool)
    _pace = Signal(object)
    _plan = Signal(object)
    plan_shown = Signal(object)
    """The account's plan as its line (`PlanLine`), on the interface thread."""
    busy_changed = Signal(bool)
    """The server's pace hint began (True) or stopped slowing live updates
    - a busy time - on the interface thread."""
    spoken_per_source = Signal(bool)
    """A listening session opened: whether its server uses each caption
    window's spoken language (`welcome.source_fields`; 263), on the
    interface thread."""
    update_found = Signal(object)
    """What the updater found after "update required" (`UpdateNow`), on the
    interface thread: what Home tells the learner to do."""
    cohort_seen = Signal(str)
    """A session opened: the account's test group (`welcome.cohort`), on the
    interface thread (polyglotic-hq 275)."""
    clock_doubted = Signal(bool)
    """A session opened: whether its certificate was let through with this
    PC's time outside its dates - the clock looks wrong (connection.tls,
    polyglotic-hq 313) - on the interface thread."""
    _maintenance = Signal(object)
    maintenance_seen = Signal(object)
    """The planned maintenance window the app holds changed (`Maintenance`,
    or None), on the interface thread (polyglotic-hq 319)."""

    def __init__(
        self,
        desktop: DesktopApp,
        pipeline: SpeechPipeline | None,
        updates: BackgroundUpdates | None = None,
        account: NextAccountPage | None = None,
    ) -> None:
        """`account`: the Account page the session's sign-in state goes to."""
        super().__init__(desktop)
        self.desktop = desktop
        self.pipeline = pipeline
        self.updates = updates
        self.account = account
        self.session_id: str | None = None
        """The last listening session's id, for feedback to name."""
        self.dictated: Callable[[CaptionUpdate], None] | None = None
        """Where dictation's answers go, from the session's thread - never
        the caption feed (`ui.dictation.Dictating.answered`; 0073)."""
        self.mandarin: MandarinScript | None = None
        """Mandarin's captions in the script the learner reads (375)."""
        self._status.connect(self._show_status, Qt.ConnectionType.QueuedConnection)
        self._minutes.connect(desktop.set_minutes, Qt.ConnectionType.QueuedConnection)
        self._notice.connect(desktop.show_notice, Qt.ConnectionType.QueuedConnection)
        self._failed.connect(desktop.caption_failed, Qt.ConnectionType.QueuedConnection)
        self._stalled.connect(
            desktop.connection_stalled, Qt.ConnectionType.QueuedConnection
        )
        self._busy = False
        self._pace.connect(self._show_pace, Qt.ConnectionType.QueuedConnection)
        self._plan.connect(self._show_plan, Qt.ConnectionType.QueuedConnection)
        self._maintenance.connect(
            self._show_maintenance, Qt.ConnectionType.QueuedConnection
        )
        self._held: str | None = None
        """The tier the open listening session holds until it ends (its
        `welcome`'s), on the interface thread; None when none is open."""
        self._last_plan: PlanShown | None = None

    def status_changed(self, status: Status) -> None:
        log.info("session %s", status.state.value)
        if self.pipeline is not None:  # nothing kept through a planned window (319)
            self.pipeline.hold_speech(not in_maintenance(status))
        if status.session_id is not None:
            self.session_id = status.session_id
        if status.channel is not None and self.updates is not None:
            self.updates.follow(status.channel)
        self._status.emit(status)

    def caption_updated(self, update: CaptionUpdate) -> None:
        if update.source_id == DICTATION:  # typed, never a caption (0073)
            if self.dictated is not None:
                self.dictated(update)
            return
        if self.mandarin is not None:  # in the script the learner reads (375)
            update = self.mandarin.caption(update)
        self.desktop.feed.receive(update)  # queued to the Qt thread

    def pace_changed(self, live_interval_min: float | None) -> None:
        if self.pipeline is not None:
            self.pipeline.set_pace_hint(live_interval_min)
        self._pace.emit(live_interval_min)

    def minutes_changed(self, used: float, left: float | None) -> None:
        self._minutes.emit(used, left)

    def notice(self, code: str) -> None:
        log.info("notice %s", code)
        self._notice.emit(code)

    def caption_failed(self) -> None:
        self._failed.emit()  # queued after the captions before it

    def connection_stalled(self, stalled: bool) -> None:
        self._stalled.emit(stalled)

    def rechecked(self, result: RecheckResult) -> None:
        # nothing asks since "Looks wrong?" left the interface (polyglotic-hq 339)
        log.info("recheck %s", result.outcome.value)  # never the line

    def plan_changed(self, plan: protocol.PlanState) -> None:
        log.info("plan %s (%s, %s)", plan.tier, plan.source, plan.status)
        self._plan.emit(plan)

    def maintenance_changed(self, window: Maintenance | None) -> None:
        self._maintenance.emit(window)  # on the session's thread

    @Slot(object)
    def _show_maintenance(self, window: Maintenance | None) -> None:
        self.maintenance_seen.emit(window)  # on the interface thread

    @Slot(object)
    def _show_plan(self, plan: protocol.PlanState) -> None:
        """The plan as its line. A `plan` message that lowers the tier while
        a listening session holding Plus is open says Plus ends with the
        session: the session keeps its tier until it ends (protocol.md,
        `plan`). `welcome`'s plan is the session's own, and `limit_reached`'s
        comes as it ends, so they're said as they are (polyglotic-hq 237)."""
        from polyglotic_desktop.connection.protocol import Plan

        self._last_plan = plan_shown(plan)
        held = self._held if isinstance(plan, Plan) else None
        self.plan_shown.emit(plan_line(self._last_plan, held))

    @Slot(object)
    def _show_pace(self, live_interval_min: float | None) -> None:
        busy = live_interval_min is not None
        if busy != self._busy:
            self._busy = busy
            self.busy_changed.emit(busy)

    @Slot(object)
    def _show_status(self, status: Status) -> None:
        from polyglotic_desktop.connection.reconnect import StopReason
        from polyglotic_desktop.connection.session import SessionState

        shown = self.desktop.connection
        state, retry_in = connection_state(status, shown)
        why = unreachable_shown(status, shown, self.desktop.unreachable)
        self.desktop.set_connection(state, retry_in, why)
        self._follow_held(status)
        if status.source_fields is not None:  # a listening session's `welcome`
            self.spoken_per_source.emit("spoken_language" in status.source_fields)
        if status.cohort is not None:  # any session's `welcome`
            self.cohort_seen.emit(status.cohort)
        if status.state is SessionState.LISTENING:  # any session's `welcome`
            self.clock_doubted.emit(status.clock_looks_wrong)
        if self.account is not None and state is ConnectionState.SIGN_IN_NEEDED:
            self.account.set_signed_in(False)
        if self.account is not None and status.account_id is not None:
            self.account.show_account(status.account_id)
        if status.stopped is StopReason.UPDATE_REQUIRED and self.updates is not None:
            self.updates.update_now(self.update_found.emit)  # straight to the updater

    def _follow_held(self, status: Status) -> None:
        """The listening session's tier, from its `welcome`, until it ends;
        when it ends, the last plan's own line - unless the account signed
        out, whose plan isn't shown any more."""
        from polyglotic_desktop.connection.reconnect import StopReason
        from polyglotic_desktop.connection.session import SessionState

        if status.stopped is StopReason.SIGN_IN_NEEDED:
            self._held = self._last_plan = None
            return
        if status.state is SessionState.LISTENING:
            self._held = status.tier
            return
        ended, self._held = self._held is not None, None
        if ended and self._last_plan is not None:
            self.plan_shown.emit(plan_line(self._last_plan))


def not_deleted_notice(code: str) -> str:
    """Home's line when deleting the learning data on this PC left some of
    language `code`'s there (polyglotic-hq 306)."""
    return pc_or_mac(
        _tr_app(
            "Some of your {language} learning data couldn't be deleted from this "
            "PC. Restart Polyglotic, then delete it again on Account."
        ),
        _tr_app(
            "Some of your {language} learning data couldn't be deleted from this Mac. "
            "Restart Polyglotic, then delete it again on Account."
        ),
    ).format(language=learned_name(code))


def start_notice(set_aside: Path | None, taken_off: Sequence[str]) -> str:
    """What Home's banner says once as the app starts, if anything: a
    settings file that wasn't settings, set aside (polyglotic-hq 133), and
    saved languages taken off the list (DECISIONS.md #40; project 144)."""
    said = []
    if set_aside is not None:
        said.append(
            _tr_app(
                "Your settings couldn't be read, so they've been reset."
                " The old file is kept beside them as {name}."
            ).format(name=set_aside.name)
        )
    if taken_off:
        said.append(taken_off_note(taken_off))
    return " ".join(said)


def once_running(call: Callable[[], None]) -> None:
    """`call` as soon as the app's event loop runs - for a dialog the tray's
    Quit must be able to end: Qt ignores a quit before the loop runs, so the
    first run's sign-in, asked before it, stayed up and the app carried on
    without its tray (polyglotic-hq 133)."""
    QTimer.singleShot(0, call)


def captioning(value: AppSettings) -> bool:
    """Something is chosen to caption: apps, everything the PC plays, or
    the mic. A listening session is open only then - until the learner
    picks (the first run starts paused, polyglotic-hq DECISIONS.md #25) it
    would hold one of the account's places on the server for nothing
    (project 051's note; 061). Learning syncs in sync sessions meanwhile."""
    return value.source_chosen or value.caption_mic


def listen_then_sync(
    connection: Connection,
    listen: Callable[[], None],
    value: AppSettings,
    sample: bool = False,
) -> bool:
    """Listening first - if something is chosen to caption and it isn't
    already - then `start`, which, with a listening session open, opens no
    sync session: the listening session sends what waits and syncs
    learning itself. The other way round, the start-up sync's `hello`
    could already be out when listening began, and with another PC of the
    account listening the server would count three sessions - one refused
    `too_many_sessions` (polyglotic-hq project 042, Low 9). `start` still
    runs: it clears a stop left by signing out, and with nothing chosen it
    syncs. The sample (`sample`) is something to caption too. Whether a
    listening session is open."""
    if (captioning(value) or sample) and connection.listening is None:
        listen()
    connection.start()
    return connection.listening is not None


NO_SESSION = (ConnectionState.STOPPED, ConnectionState.NOT_CONNECTED)
"""The states the app's own stop leaves: nothing was chosen to caption."""


def follow_choice(
    connection: Connection,
    value: AppSettings,
    listen: Callable[[], None],
    desktop: DesktopApp | None = None,
    sample: bool = False,
    dictating: bool = False,
) -> None:
    """A setting changed: listening once something is chosen to caption -
    or while the sample is on (`sample`, polyglotic-hq 176), or while
    dictation needs a session (`dictating`: a hold under way, or one
    answered in the last minute - decision 0073) - and not once nothing
    is - what waits then goes in a sync session. A session just
    opened says Connecting at once (`desktop`): Home said "Stopped" - the
    last session's end - until the new one's first word (polyglotic-hq
    145)."""
    wanted = captioning(value) or sample or dictating
    if wanted and connection.listening is None:
        opened = listen_then_sync(connection, listen, value, sample or dictating)
        if opened and desktop is not None and desktop.connection in NO_SESSION:
            desktop.set_connection(ConnectionState.CONNECTING)
    elif not wanted and connection.listening is not None:
        connection.stop_listening()


def plus_is_back(connection: ConnectionState | None, line: PlanLine) -> bool:
    """Stopped because Plus ended (4009), and a plan with Plus arrives - a
    code redeemed, or Plus bought: listening starts again by itself
    (polyglotic-hq 185)."""
    return connection is ConnectionState.PLUS_ENDED and line.has_plus


class NotAgreed(Exception):
    """The first screen closed without the yes: under 16, or no to the
    tester agreement."""


@dataclass(frozen=True)
class FirstChoice:
    """What the first screen chose: what's shared, and the yes."""

    choices: tuple[bool, bool, bool]
    agreement: Agreement | None


@dataclass(frozen=True)
class FirstRun:
    """What the first run's screens leave (`first_run`): the learner's
    tools for the language chosen, with their learning store (to close at
    the end); Your data's answer, if it was asked; and whether the code was
    asked - then it isn't again, over the window; and whether nothing was
    saved before it (`new`): this PC's first start, a fresh install's."""

    tools: LearningTools
    learning_store: BackgroundLearningStore
    first: FirstChoice | None
    code_asked: bool
    new: bool = False


def first_run(
    store: SettingsStore,
    learner: Callable[[bool], tuple[LearningTools, BackgroundLearningStore]],
    consent: ConsentChoice | None,
    code: Redeem | None,
    code_again: bool = False,
    windows_languages: Sequence[str] = (),
    kept: Callable[[str], bool] = lambda _: False,
) -> FirstRun:
    """At start, the first run's screens, one after another, each after the
    first with Back (polyglotic-hq 250, the user's F4; `ui.first_run`):

    1. Your data and the yes - the first run, or the tester agreement's new
       words (`agreement_needed`), with `consent`, the choices so far;
    2. the code, after that, when this PC isn't signed in (`code` given):
       the first run ends signed in, or signed out if it's closed. A later
       start signed out asks it over the window instead. `code_again`: this
       PC has signed in before, so its code works again (polyglotic-hq 288).

    No language and no level are asked (polyglotic-hq 293, decision 0085):
    the app opens for anyone, every language is chosen in Settings and on
    Learning, and words are estimated at a middle level until the learner
    sets theirs (Home's line asks, `HomePage.show_level_line`).
    `learner` builds the tools (English: True) for the language being
    learned, or until one is chosen a guess from Windows' display languages
    (`windows_languages`, in the user's order) and the learning data `kept`
    on this PC (`starting_language`). New settings translate into the first
    of Windows' languages that captions are translated into, else English
    (`own_targets`); saved ones are kept as they are.

    Each answer is kept on its own screen's Next, never on Back. Closing a
    screen goes on without its answer - except Your data's, which raises
    `NotAgreed` (polyglotic-hq 185, DECISIONS.md #88)."""
    new = not store.load()  # nothing saved yet: this PC's first start
    settings = Settings(store)
    own = own_targets(windows_languages)
    if new and own and (own[0],) != settings.value.targets:
        settings.update(targets=(own[0],))
    chosen = starting_language(
        settings.value.learning,
        learned_code(windows_languages[0]) if windows_languages else None,
        kept,
    )
    learning, learning_store = learner(chosen == "en")
    # the learner's theme, as the window will have it (`DesktopApp`): no
    # window yet to share its stylesheet
    theme.apply(settings.value.window_theme, settings.value.theme)
    sheet = style.stylesheet(window_theme())
    first: FirstChoice | None = None
    screens: dict[str, TextDialog] = {}
    answered = False
    """A screen before the code was asked."""
    code_asked = False

    def screen(key: str, make: Callable[[], TextDialog]) -> TextDialog:
        """The screen for `key`, made once: shown again, it has what was
        entered on it."""
        if key not in screens:
            screens[key] = make()
            screens[key].setStyleSheet(sheet)
        return screens[key]

    def ask_consent(back: bool) -> Answer:
        nonlocal first, answered
        answered = True
        tester = None if settings.value.cohort is None else is_tester(settings.value)
        shown = screen("consent", lambda: ConsentDialog(consent, tester=tester))
        assert isinstance(shown, ConsentDialog)
        result = asked(shown, shown.back, back)
        if result == BACK:
            return Answer.BACK
        if not result:  # closed, or Quit: no yes, no further
            return Answer.QUIT
        first = FirstChoice(shown.choices(), shown.agreement())
        return Answer.NEXT

    def ask_code(back: bool) -> Answer:
        nonlocal code_asked
        code_asked = True
        assert code is not None
        shown = screen("code", lambda: SignInDialog(code, again=code_again))
        assert isinstance(shown, SignInDialog)
        result = asked(shown, shown.back, back)
        return Answer.BACK if result == BACK else Answer.NEXT  # in, or signed out

    agreed = run_first_run(
        [
            Step("consent", lambda: agreement_needed(consent), ask_consent),
            Step("code", lambda: code is not None and answered, ask_code),
        ]
    )
    for shown in screens.values():
        shown.deleteLater()
    if not agreed:
        learning_store.close()  # no further
        raise NotAgreed
    return FirstRun(learning, learning_store, first, code_asked, new)


def sign_in_problem(result: RedeemResult) -> SignInFailed | None:
    """The connection's answer to an invite code, as the sign-in dialog
    shows it; None once signed in."""
    from polyglotic_desktop.connection.sign_in import (
        InviteNotValid,
        NotACode,
        PlusAlready,
        SignedIn,
        SignInAgain,
        SignOutFirst,
        SubscriptionEnded,
        TooManyAttempts,
    )

    if isinstance(result, SignedIn):
        return None
    if isinstance(result, NotACode):
        return SignInFailed(SignInProblem.NOT_A_CODE)
    if isinstance(result, InviteNotValid):
        return SignInFailed(SignInProblem.NOT_VALID)
    if isinstance(result, SubscriptionEnded):
        return SignInFailed(SignInProblem.SUBSCRIPTION_ENDED)
    if isinstance(result, TooManyAttempts):
        return SignInFailed(SignInProblem.TOO_MANY_ATTEMPTS, result.retry_after)
    if isinstance(result, PlusAlready):
        return SignInFailed(SignInProblem.PLUS_ALREADY)
    if isinstance(result, SignInAgain):
        return SignInFailed(SignInProblem.SIGN_IN_AGAIN)
    if isinstance(result, SignOutFirst):
        return SignInFailed(SignInProblem.SIGN_OUT_FIRST)
    return SignInFailed(SignInProblem.UNREACHABLE, unreachable=result.unreachable)


class SignedInCohort:
    """The cohort a code signed in with - the redeem answer's - handed from
    the sign-in thread to the interface's: the account's test group is known
    from the first minute, so an alpha tester's "Report a problem" and
    diagnostics don't wait for the first session's `welcome` (polyglotic-hq
    279). `answered` runs on the sign-in thread; the dialog's own answer
    reaches the interface's thread after it, and `take` is read there."""

    def __init__(self) -> None:
        self._cohort: str | None = None

    def answered(self, result: RedeemResult) -> SignInFailed | None:
        """`result` as the sign-in dialog shows it (`sign_in_problem`), its
        cohort kept when it signed in."""
        from polyglotic_desktop.connection.sign_in import SignedIn

        if isinstance(result, SignedIn):
            self._cohort = result.cohort
        return sign_in_problem(result)

    def take(self) -> str | None:
        """The cohort the last code signed in with, once: None if no code
        has signed in since the last take."""
        cohort, self._cohort = self._cohort, None
        return cohort


def entry_text(tools: LearningTools, entry_id: EntryId) -> EntryText | None:
    """What a word saved on another PC keeps here, from this PC's dictionary."""
    entry = tools.entry(entry_id)
    if entry is None:
        return None
    meaning = short_meaning([entry])
    return EntryText(entry.headword, entry.traditional, entry.reading, meaning)


class QtExchange(QObject):
    """The exchange's listener: statuses and saved words from the server,
    and the server's "deleted", arrive on a session's thread and are
    applied to the learner's vocabulary on the Qt thread (it's single-
    threaded), without being sent back."""

    _arrived = Signal(object)
    _deleted = Signal()

    def __init__(
        self,
        tools: LearningTools,
        parent: QObject | None = None,
        data: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools
        self.data = data
        """The data folder: where the learning data of languages not open
        is kept (`delete_closed_learning_data`)."""
        self.delete_here = False
        """Set when the user also asked to delete the data on this PC."""
        self._arrived.connect(self._apply, Qt.ConnectionType.QueuedConnection)
        self._deleted.connect(self._delete, Qt.ConnectionType.QueuedConnection)

    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        self._arrived.emit(list(events))

    def learning_deleted(self) -> None:
        self._deleted.emit()

    @Slot(object)
    def _apply(self, events: list[LearningEvent]) -> None:
        changed = self.tools.vocabulary.apply_from_server(
            events, lambda entry_id: entry_text(self.tools, entry_id)
        )
        log.info("learning from the server: %d change(s) applied", changed)

    @Slot()
    def _delete(self) -> None:
        """The server deleted the learning data - every language's. Asked to
        delete it here too: every open language's on this PC, each its own
        file and the copies set aside from it (DECISIONS #135, polyglotic-hq
        306) - one opened during the run included. A store that can't be
        emptied says so for its own language (`learning_not_deleted`); the
        others are deleted all the same. Then every language's that isn't
        open - one no longer learned, or a pack language whose pack was
        removed (decision 0175): the server's copy of those is gone too."""
        log.info("learning data deleted on the server")
        if self.delete_here:
            self.delete_here = False
            every = self.tools.every
            for each in every:
                each.vocabulary.delete_learning_data()
            log.info("learning data deleted on this PC: %d language(s)", len(every))
            if self.data is not None:
                delete_closed_learning_data(
                    self.data, [each.language for each in every]
                )


class QtFeedback(QObject):
    """The feedback sender's outcomes: they come on its thread and show on
    Home on the Qt thread. `just_sent`: the report the user sent this time."""

    _outcome = Signal(str, str)

    def __init__(self, desktop: DesktopApp) -> None:
        super().__init__(desktop)
        self.desktop = desktop
        self.just_sent: str | None = None
        self._outcome.connect(self._show, Qt.ConnectionType.QueuedConnection)

    def outcome(self, report: Report, outcome: Outcome) -> None:
        self._outcome.emit(report.id, outcome.value)

    def outcome_of(self, report_id: str, outcome: Outcome) -> None:
        """A problem report's outcome (polyglotic-hq 275), from its sender's thread."""
        self._outcome.emit(report_id, outcome.value)

    @Slot(str, str)
    def _show(self, report_id: str, outcome: str) -> None:
        self.desktop.show_feedback(outcome, report_id == self.just_sent)


def new_report(
    kind: ReportKind,
    text: str,
    reply_to: str | None,
    attached: str | None,
    app: AppInfo,
    session_id: str | None,
) -> Report:
    """A report as the user sent it now, with what goes with every one."""
    from polyglotic_desktop.connection import protocol

    return Report(
        id=str(uuid.uuid4()),
        at=protocol.at(datetime.now(UTC)),
        kind=kind,
        text=text,
        reply_to=reply_to,
        log=attached,
        app_version=app.app_version,
        os=app.os,
        os_version=app.os_version,
        session_id=session_id,
    )


def feedback_versions(app: AppInfo) -> str:
    """This copy's versions, as the feedback form says they're sent - in
    the interface language's punctuation (polyglotic-hq 235: 223 saw an
    ASCII comma among the Chinese form's own)."""
    #: The feedback form's "Also sent: ...": the app's version, Windows' name
    #: (windows-11) and its version number (10.0.26200) - keep them as they are
    return _tr_app("Polyglotic {version}, {os} ({os_version})").format(
        version=app.app_version, os=app.os, os_version=app.os_version
    )


TESTER_COHORTS = frozenset({"alpha"})
"""Cohorts whose testers get "Report a problem" with everything attached,
and diagnostics always on (polyglotic-hq 275; decision 0067). The server
refuses captions and audio from anyone else (its decision 0055)."""


def is_tester(settings: AppSettings) -> bool:
    """Whether the account signed in is an alpha tester's, as last said."""
    return settings.cohort in TESTER_COHORTS


def diagnostics_on_for_testers(exchange: DataExchange) -> bool:
    """An alpha tester's crash reports and usage statistics, on (the user,
    2026-11-11: content-free diagnostics always on for alpha testers; the
    consent screen says so). Word counts stay as chosen. Nothing before the
    first run's choice. True if it changed anything."""
    current = exchange.consent
    if current is None or (current.usage and current.crashes):
        return False
    exchange.choose_consent(True, True, current.exposures)
    log.info("an alpha tester: crash reports and usage statistics on")
    return True


def cohort_known(
    cohort: str,
    settings: Settings,
    exchange: DataExchange,
    reporting: Callable[[bool], None],
) -> None:
    """The account's test group, from a code's redeem answer or a session's
    `welcome`: kept for the next start (the menu's "Report a problem" works
    before a session opens), the caption windows' "Report a problem" shown
    to a tester (`reporting`), and an alpha tester's diagnostics on
    (polyglotic-hq 275, 279)."""
    if settings.value.cohort != cohort:
        settings.update(cohort=cohort)
    tester = is_tester(settings.value)
    reporting(tester)
    if tester:
        diagnostics_on_for_testers(exchange)


def report_facts(
    app: AppInfo,
    channel: str,
    speech: Sequence[SpeechPart],
    apps_one_by_one: str | None = None,
) -> dict[str, object]:
    """The app, Windows and the audio devices, for a problem report: no
    caption text, no app's name - each source by its id and category.
    `apps_one_by_one`: the log's line on capturing apps one by one - the
    build, whether it was tried, how it went (decision 0076)."""
    screens = [
        {
            "scale": screen.devicePixelRatio(),
            "width": screen.geometry().width(),
            "height": screen.geometry().height(),
        }
        for screen in QGuiApplication.screens()
    ]
    facts: dict[str, object] = {
        "app": {
            "version": app.app_version,
            "channel": channel,
            "installed": installed(),
            "interface_language": QLocale().name(),
            "qt": qVersion(),
        },
        "windows": {
            "os": app.os,
            "version": app.os_version,
            "screens": screens,
            **({"apps_one_by_one": apps_one_by_one} if apps_one_by_one else {}),
        },
        "sources": [
            {"id": part.source_id, "category": part.category.value} for part in speech
        ],
    }
    try:
        from polyglotic_desktop.platform.windows.devices import (
            Flow,
            active_devices,
            default_device,
        )

        facts["audio_devices"] = {
            flow.name.lower(): {
                "default": getattr(default_device(flow), "name", None),
                "active": [d.name for d in active_devices(flow)],
            }
            for flow in Flow
        }
    except (ImportError, OSError) as problem:  # no Core Audio here
        facts["audio_devices"] = {"unavailable": type(problem).__name__}
    return facts


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def problem_report_parts(
    log_text: str | None,
    settings: dict[str, object],
    facts: dict[str, object],
    captions: list[dict[str, object]],
    speech: Sequence[SpeechPart],
    names: dict[str, str],
    check_result: str | None,
) -> list[Part]:
    """What "Report a problem" offers, each part with its size and what
    Look shows: exactly what goes. A part with nothing in it isn't offered."""
    labels = part_labels()
    parts = []
    if check_result:
        parts.append(
            Part("check", labels["check"], len(check_result), lambda: check_result)
        )
    if log_text is not None:
        parts.append(
            Part("log", labels["log"], len(log_text.encode("utf-8")), lambda: log_text)
        )
    pretty = partial(json.dumps, ensure_ascii=False, indent=2)
    parts.append(
        Part(
            "settings",
            labels["settings"],
            _json_size(settings),
            lambda: pretty(settings),
        )
    )
    parts.append(
        Part("facts", labels["facts"], _json_size(facts), lambda: pretty(facts))
    )
    if captions:
        parts.append(
            Part(
                "captions",
                labels["captions"],
                _json_size(captions),
                lambda: captions_look(captions),
                captions_detail(len(captions)),
            )
        )
    said = {str(c["caption_id"]): str(c["original"]) for c in captions}
    for part in speech:
        clips = [(str(c.caption_id), c.end - c.start) for c in part.clips]
        parts.append(
            Part(
                f"speech:{part.source_id}",
                speech_label(names.get(part.source_id, part.category.value)),
                part.size,
                partial(speech_look, clips, said),
                speech_detail(part.seconds),
                others_voices=part.others_voices,
            )
        )
    return parts


def ask_for_feedback(
    kind: ReportKind,
    logs: Path,
    app: AppInfo,
    session_id: str | None,
    waiting: WaitingReports,
    parent: QWidget | None = None,
    check_result: str | None = None,
) -> Report | None:
    """The feedback form; the report kept to send if the user sent it.
    `check_result` is Help's "no captions?" check, added to the text."""
    dialog = FeedbackDialog(
        kind,
        lambda: read_log(logs),
        feedback_versions(app),
        session_id is not None,
        parent,
        check_result,
    )
    if not dialog.exec():
        return None
    report = new_report(*dialog.report(), app, session_id)
    waiting.add(report)
    log.info("a %s report kept to send", report.kind)
    return report


def share_finished_days(vocabulary: Vocabulary, exchange: DataExchange) -> None:
    """Finished UTC days' exposure counts, handed over once: kept to send
    only with the learner's opt-in, dropped otherwise."""
    days = vocabulary.take_finished_exposure_days(datetime.now(UTC).date())
    if days:
        exchange.exposures(days)


@dataclass(frozen=True)
class SourcePlan:
    """What to capture: the apps picked that are open (each by process id -
    its name stays on this PC), everything the PC plays (`whole_system`),
    or neither (nothing picked yet, or no app picked is open); everything
    else the PC plays beside the one app picked (`everything_else`): that
    app left out while it's open, else the whole system's audio; and the
    mic."""

    apps: tuple[tuple[int, str, SourceCategory], ...]
    whole_system: bool
    mic: bool
    everything_else: bool = False


def plan_sources(
    value: AppSettings, apps: list[PlayingApp], per_app: bool
) -> SourcePlan:
    """The sources the settings ask for. Nothing until the learner picks
    what to caption (the first run starts paused: polyglotic-hq
    DECISIONS.md #25). Everything the PC plays when they chose it, or
    picked apps Windows can't capture on their own (Windows 10); otherwise
    each app picked that's open - one that isn't joins when it opens -
    and everything else beside the one app, if it's on. The mic follows
    its own switch.

    Of several processes of one app, the same one each time, whatever
    order Windows lists them in: one playing before one that isn't, then
    the lowest process id - a different one would restart the source."""
    if not value.source_chosen:
        return SourcePlan((), False, value.caption_mic)
    if value.whole_system or not per_app:
        return SourcePlan((), True, value.caption_mic)
    found = []
    for name in value.apps:
        app = min(
            (a for a in apps if a.name == name),
            key=lambda a: (not a.playing, a.process_id),
            default=None,
        )
        if app is not None:
            found.append((app.process_id, app.name, app.category))
    return SourcePlan(
        tuple(found), False, value.caption_mic, value.captions_everything_else
    )


TRIAL_CHECK_MS = 1000
"""How often a trial of capturing apps one by one is asked how it went."""


def apps_one_by_one(
    support: AppCaptureSupport, fell_back: Mapping[str, str], here: Mapping[str, str]
) -> bool:
    """Whether apps are captioned one by one on this PC (decision 0076):
    where Windows promises it; where it may (Windows 10 version 2004 and
    later) unless it failed here before (`fell_back`: the Windows build and
    the app's version it failed with, and why) and both are as they were
    (`here`) - a Windows update or an app update tries again; never where
    it can't (everything the PC plays)."""
    if support is AppCaptureSupport.YES:
        return True
    if support is AppCaptureSupport.NO:
        return False
    return not fell_back or any(fell_back.get(k) != v for k, v in here.items())


def app_capture_line(
    support: AppCaptureSupport,
    build: str,
    on: bool,
    outcome: TrialOutcome | None = None,
    fell_back: Mapping[str, str] | None = None,
) -> str:
    """The log's line on capturing apps one by one (decision 0076):
    Windows' build, whether it was tried, and whether it worked or why not
    - Windows' code, never an app's name. Content-free: it says what the
    first Windows 10 tester's PC did."""
    start = f"capturing apps one by one: Windows build {build}, "
    if support is AppCaptureSupport.YES:
        return start + "promised"
    if support is AppCaptureSupport.NO:
        return start + "not tried (Windows before version 2004)"
    if outcome is not None:
        if outcome.worked:
            return start + "tried: it worked"
        return start + f"tried: it failed ({outcome.why}), everything the PC plays now"
    if on:
        return start + "trying"
    why = (fell_back or {}).get("why", "")
    return start + f"not tried: it failed here before ({why})"


class AppsOneByOne(QObject):
    """Whether apps are captioned one by one on this PC (`on`) - and,
    where Windows doesn't promise it (Windows 10 version 2004 to 22H2:
    decision 0076), trying it: the captures tell `trial` what they find.
    If it fails, it's everything the PC plays from then on, remembered in
    the settings for this Windows update and this version of the app (an
    update of either tries again, as does `try_again`); `changed` says so.
    `line` is the log's line on it, the latest."""

    changed = Signal()

    def __init__(
        self,
        support: AppCaptureSupport,
        settings: Settings,
        build: str,
        app_version: str,
        new_trial: Callable[[], AppCaptureTrial],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.support, self._settings, self._new_trial = support, settings, new_trial
        self._build = build
        self._here = {"windows": build, "app": app_version}
        fell_back = settings.value.app_capture_fell_back
        self.on = apps_one_by_one(support, fell_back, self._here)
        self.trial: AppCaptureTrial | None = None
        self._watch = QTimer(self, interval=TRIAL_CHECK_MS)
        self._watch.timeout.connect(self.check)
        if self.on and support is AppCaptureSupport.TRY:
            self._start_trial()
        self._say(app_capture_line(support, build, self.on, None, fell_back))

    @property
    def fell_back(self) -> bool:
        """Tried here, and Windows couldn't capture one app alone."""
        return self.support is AppCaptureSupport.TRY and not self.on

    def _start_trial(self) -> None:
        self.trial = self._new_trial()
        self._watch.start()

    def _say(self, line: str) -> None:
        self.line = line
        log.info("%s", line)

    def check(self) -> None:
        """How the trial went, once a capture has shown: it worked (said
        in the log), or everything the PC plays from now on."""
        outcome = self.trial.outcome if self.trial is not None else None
        if outcome is None:
            return
        self._watch.stop()
        self._say(app_capture_line(self.support, self._build, True, outcome))
        if outcome.worked:
            return
        self.on, self.trial = False, None
        self.changed.emit()
        self._settings.update(app_capture_fell_back={**self._here, "why": outcome.why})

    def try_again(self) -> None:
        """Apps one by one again, after it failed here: tried afresh."""
        if not self.fell_back:
            return
        self.on = True
        self._start_trial()
        self._say(app_capture_line(self.support, self._build, True))
        self.changed.emit()
        self._settings.update(app_capture_fell_back={})


def fell_back_text() -> str:
    """What the learner is told, once, when capturing apps one by one
    failed on this PC (decision 0076)."""
    return pc_or_mac(
        _tr_app(
            "Windows on this PC couldn't caption one app alone, so Polyglotic"
            " captions everything the PC plays. You can try apps again on Home."
        ),
        _tr_app(
            "This Mac couldn't caption one app alone, so Polyglotic captions "
            "everything the Mac plays. You can try apps again on Home."
        ),
    )


class Sources:
    """The pipeline's sources, following the settings: each app picked
    (with everything else the PC plays beside one), or everything the PC
    plays, and the mic - each a source of its own, with its own speech
    detection and timing.

    A change starts and stops only what changed: an app picked closing, or
    opening again, leaves the other sources as they were (speech in
    progress included). Each app keeps one source id while the app runs -
    `app-1`, `app-2`, ... in the order they were first captured, never its
    name (protocol.md, `source.id`); `ids` maps the app's name to it, on
    this PC only. `on_change` is told, after each change, each app's
    source id, name and what it's called on screen (its public name if
    it's a known app) - for its captions' labels; `on_capture`, what is
    captured now - the mode, how many apps, the mic - for the listening
    session's usage statistics (polyglotic-hq project 134).

    **Everything else** (polyglotic-hq DECISIONS.md #59) is captured
    leaving its one app out (`everything_else_capture`, by the app's
    process id), so nothing is heard twice; while that app isn't open, it
    is everything the PC plays - and it restarts, leaving the app out,
    when the app opens (or closes again).

    **The app's own sound** (a looked-up word said aloud, polyglotic-hq
    286): everything the PC plays, everything else and the mic can hear it,
    so they're added as hearing the app (`hears_the_app`) and are silent
    while it plays (`SpeechPipeline.hush`); an app on its own never hears
    it, nor does the sample.

    **Nothing is captured while signed out** (`signed_in`): audio is taken
    only to serve the learner, and a signed-out app serves nothing - it
    starts on signing in (polyglotic-hq 137; before, an app added on a
    first run left at "Not signed in" was captured and run through speech
    detection, 133).

    **The sample** (polyglotic-hq 176): while it's on (`play_sample`) -
    and nothing else is chosen - the recording `sample_capture` makes is a
    source of its own (SAMPLE), started again each time it's turned on.
    Played to its end (`sample_done`), `end_sample` turns it off and keeps
    its window for lookups (`sample_kept`) until an app is chosen, or it's
    tried again or closed (polyglotic-hq 208)."""

    def __init__(
        self,
        pipeline: SpeechPipeline,
        apps: AppList,
        per_app: bool,
        app_capture: Callable[[int, str], AudioCapture],
        system_capture: Callable[[], AudioCapture],
        mic_capture: Callable[[], AudioCapture],
        on_change: Callable[[dict[SourceId, tuple[str, str]]], None] | None = None,
        on_capture: Callable[[Capture], None] | None = None,
        signed_in: bool = True,
        *,
        everything_else_capture: Callable[[int], AudioCapture],
        sample_capture: Callable[[], AudioCapture | None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.signed_in = signed_in
        self._value: AppSettings | None = None  # the settings last followed
        self.on_change = on_change
        self.on_capture = on_capture
        self.apps = apps
        self.per_app = per_app
        self._app_capture = app_capture
        self._system_capture = system_capture
        self._mic_capture = mic_capture
        self._everything_else_capture = everything_else_capture
        self._sample_capture = sample_capture
        self.sample_on = False
        self.sample_kept = False  # ended, its window kept for lookups (208)
        self._sample: AudioCapture | None = None  # the one playing, if any
        self._samples = 0  # times turned on: each is a capture of its own
        self.plan: SourcePlan | None = None
        self.ids: dict[str, SourceId] = {}
        self._titles: dict[str, str] = {}  # an app's name -> on screen
        self._known: dict[str, str | None] = {}  # -> its public name, if known
        self._running: dict[SourceId, tuple[object, ...]] = {}
        self._categories: dict[SourceId, SourceCategory] = {}
        self._buffers: dict[SourceId, AudioBuffer] = {}
        self._reference: AudioBuffer | None = None  # what the PC played, for the mic
        self._devices: tuple[str | None, str | None] = (None, None)
        """The speakers and mic chosen when last followed (372)."""

    def mic_peak(self) -> float | None:
        """The mic's loudest sample over the last tenth of a second, while
        it's captured (Home's level meter, polyglotic-hq 372); else None."""
        buffer = self._buffers.get(MIC)
        return buffer.peak() if buffer is not None else None

    def category_of(self, name: str) -> SourceCategory | None:
        """The category of the app called `name`, if it is captured now."""
        apps = self.plan.apps if self.plan is not None else ()
        return next((c for _, n, c in apps if n == name), None)

    def category_of_source(self, source_id: SourceId) -> SourceCategory:
        """The category of the source captured as `source_id` (the last it
        was captured as), else `other`."""
        return self._categories.get(source_id, SourceCategory.OTHER)

    def app_id(self, name: str) -> SourceId:
        """The source id of the app called `name`: the same each time it's
        captured while Polyglotic runs."""
        if name not in self.ids:
            self.ids[name] = SourceId(f"app-{len(self.ids) + 1}")
        return self.ids[name]

    def shown(self) -> dict[SourceId, tuple[str, str]]:
        """Each app captured since Polyglotic started: its source id ->
        (its name, what it's called on screen)."""
        return {
            source_id: (name, self._titles.get(name, name))
            for name, source_id in self.ids.items()
        }

    @property
    def sample_shown(self) -> bool:
        """The sample's window shows: while it plays, and after its end."""
        return self.sample_on or self.sample_kept

    @property
    def sample_done(self) -> bool:
        """The sample has played to its end and the speech detector has
        nothing of it under way: its last sentence is finished (each sample
        ends in silence - tests/test_sample.py). Time to end it."""
        capture = self._sample
        return (
            self.sample_on
            and capture is not None
            and capture.capturing is None
            and SAMPLE not in self.pipeline.hearing()
        )

    def play_sample(self, on: bool) -> None:
        """The sample on - from its start - or off (its window too)."""
        changed = self.sample_kept or on != self.sample_on
        self.sample_kept = False
        if not changed:
            return
        self.sample_on = on
        self._samples += on
        if self._value is not None:
            self.follow(self._value, again=True)

    def end_sample(self) -> None:
        """The sample has played to its end: off, its window kept for
        lookups (polyglotic-hq 208, 203's option B)."""
        if self.sample_on:
            self.play_sample(False)
            self.sample_kept = True

    def set_signed_in(self, signed_in: bool) -> None:
        """Signed in (capture follows the settings) or out (nothing is
        captured). Signed out, the sample stops and its window goes, as an
        app's does: it isn't in the plan, so an unchanged plan left it
        playing aloud, captioned by nothing (polyglotic-hq 223)."""
        if signed_in != self.signed_in:
            self.signed_in = signed_in
            gone = not signed_in and self.sample_shown
            if gone:
                self.sample_on = self.sample_kept = False
            if self._value is not None:
                self.follow(self._value, again=gone)

    def follow(self, value: AppSettings, again: bool = False) -> None:
        """Capture as `value` says - `again`: even if its plan is the same
        (the sample turned on or off)."""
        self._value = value
        if value.source_chosen and self.sample_shown:
            self.sample_on = False  # an app (or the PC) chosen: the sample's done
            self.sample_kept = False
            again = True
        wants_apps = self.per_app and not value.whole_system and value.apps
        apps = self.apps.playing_apps() if wants_apps and self.signed_in else []
        plan = (
            plan_sources(value, apps, self.per_app)
            if self.signed_in
            else SourcePlan((), False, False)
        )
        for app in apps:
            self._titles[app.name] = app.title
            self._known[app.name] = app.known_name
        # another speaker or mic chosen (372): the same plan, captured anew
        devices = (value.speaker_device, value.mic_device)
        if plan == self.plan and devices == self._devices and not again:
            return
        self.plan, self._devices = plan, devices
        if self.on_capture is not None:
            self.on_capture(
                capture_of(
                    value.source_chosen,
                    plan.whole_system,
                    len(plan.apps),
                    plan.mic,
                    plan.everything_else,
                )
            )
        # what each source captures: a change of it restarts the source
        wanted: dict[SourceId, tuple[object, ...]] = {}
        apps_wanted: dict[SourceId, tuple[int, str, SourceCategory]] = {}
        for process_id, name, category in plan.apps:
            source_id = self.app_id(name)
            wanted[source_id] = ("app", process_id, name)
            apps_wanted[source_id] = (process_id, name, category)
        # a device chosen (polyglotic-hq 372) is part of what a source
        # captures: choosing another restarts it on that one
        if plan.whole_system:
            wanted[WHOLE_SYSTEM] = ("system", value.speaker_device)
        # everything else leaves its one app out while it's open (by process id)
        left_out = plan.apps[0][0] if plan.everything_else and plan.apps else None
        if plan.everything_else:
            wanted[EVERYTHING_ELSE] = ("everything_else", left_out)
        if self.sample_on and self.signed_in and self._sample_capture is not None:
            wanted[SAMPLE] = ("sample", self._samples)
        if plan.mic:
            # the mic is checked for bleed against what the PC played
            # (decision 0004): the whole system's own audio, or a reference
            wanted[MIC] = (
                "mic",
                plan.whole_system,
                value.mic_device,
                value.speaker_device,
            )
        for source_id in [
            s for s in self._running if wanted.get(s) != self._running[s]
        ]:
            self.pipeline.remove_source(source_id)
            del self._running[source_id]
            self._buffers.pop(source_id, None)
            if source_id == SAMPLE:
                self._sample = None
        if MIC not in self._running and self._reference is not None:
            self.pipeline.remove_reference(self._reference)
            self._reference = None
        for source_id, what in wanted.items():
            if source_id in self._running:
                continue
            if source_id in apps_wanted:
                process_id, name, category = apps_wanted[source_id]
                # its public name, if it's a known app: for the session's
                # usage statistics only, with consent (DECISIONS.md #30)
                known = self._known.get(name)
                source = Source(
                    source_id, category, known_app_id(known) if known else None
                )
                capture = self._app_capture(process_id, name)
                self._buffers[source_id] = self.pipeline.add_source(source, capture)
                self._categories[source_id] = category
            elif source_id == SAMPLE:
                assert self._sample_capture is not None
                sample = self._sample_capture()
                if sample is None:  # none in the language learned
                    continue
                self._sample = sample
                source = Source(SAMPLE, SourceCategory.OTHER)
                self._categories[SAMPLE] = SourceCategory.OTHER
                self._buffers[SAMPLE] = self.pipeline.add_source(source, sample)
            elif source_id == WHOLE_SYSTEM:
                source = Source(WHOLE_SYSTEM, SourceCategory.SYSTEM)
                self._categories[WHOLE_SYSTEM] = SourceCategory.SYSTEM
                capture = self._system_capture()
                self._buffers[WHOLE_SYSTEM] = self.pipeline.add_source(
                    source, capture, hears_the_app=True
                )
            elif source_id == EVERYTHING_ELSE:
                source = Source(EVERYTHING_ELSE, SourceCategory.SYSTEM)
                self._categories[EVERYTHING_ELSE] = SourceCategory.SYSTEM
                capture = (
                    self._system_capture()
                    if left_out is None
                    else self._everything_else_capture(left_out)
                )
                self._buffers[EVERYTHING_ELSE] = self.pipeline.add_source(
                    source, capture, hears_the_app=True
                )
            else:
                reference = self._buffers.get(WHOLE_SYSTEM)
                if reference is None:
                    self._reference = self.pipeline.add_reference(
                        self._system_capture()
                    )
                    reference = self._reference
                mic = Source(MIC, SourceCategory.MIC)
                self._buffers[MIC] = self.pipeline.add_source(
                    mic, self._mic_capture(), reference, hears_the_app=True
                )
            self._running[source_id] = what
        if self.on_change is not None:
            self.on_change(self.shown())
        log.info(
            "capturing %s%s%s",
            f"{len(plan.apps)} app(s)" if not plan.whole_system else "everything",
            " and everything else" if plan.everything_else else "",
            " and the mic" if plan.mic else "",
        )


def start_interface_language(
    app: QApplication, store: SettingsStore, fonts_listed: bool = True
) -> list[QTranslator]:
    """The interface's language - the setting, else Windows', else English -
    installed before the first window or question (decision 0034): its
    translations, children of `app` for as long as it runs. And its fonts
    (`style.use_interface_language`) - with `fonts_listed=False`, behind the
    fonts the interface names only: `main`'s, while Windows' fonts are
    still being read (`fonts_then_language`)."""
    language = interface_language.pick(
        Settings(store).value.interface_language, interface_language.windows_languages()
    )
    translators = interface_language.install(app, language)
    app.setProperty("interface_language", language)  # interface_language.in_use
    style.use_interface_language(language, fonts_listed)  # its script's first
    log.info("interface: %s (%d translation files)", language, len(translators))
    return translators


def fonts_then_language(fonts: FontsAhead, app: QApplication) -> None:
    """Windows' fonts waited for (`FontsAhead`), then the interface's
    Chinese behind every font Qt lists, now that listing them asks nothing
    more of Windows: before the first text of any window is measured or
    drawn, the first run's screens included (polyglotic-hq 322)."""
    fonts.wait()
    style.use_interface_language(interface_language.in_use(app))


def sample_language(value: AppSettings, tools: LearningTools | None) -> str | None:
    """The language Home's sample is in: the one being learned - or, until
    one is chosen (the first run asks none: polyglotic-hq 293), the one
    whose dictionary runs."""
    if value.learning is not None or tools is None:
        return value.learning
    return tools.language


def for_picked_in_load(tools: LearningTools, what: str, entries: list[EntryId]) -> None:
    """The learning load card's action for several words picked at once
    (polyglotic-hq 342), as its button for one word does it for each:
    `check_known` and `not_yet` answer the check, `known` marks them known
    (in one go), `not_now` sets them aside, `add` adds them by hand."""
    vocabulary = tools.vocabulary
    if what == "known":
        vocabulary.set_statuses(entries, WordStatus.KNOWN)
    for entry_id in entries:
        if what in ("check_known", "not_yet"):
            vocabulary.check_word(entry_id, what == "check_known")
        elif what == "not_now":
            vocabulary.set_aside_from_load(entry_id)
        elif what == "add":
            tools.add_to_load(entry_id)


def _learning_settings(value: AppSettings) -> tuple[object, ...]:
    """What Learning's page shows from the settings."""
    choices = tuple(sorted((k, repr(v)) for k, v in value.language_choices.items()))
    reset = tuple(sorted((k, repr(v)) for k, v in value.known_reset.items()))
    return (value.learning_languages, value.word_introductions, choices, reset)


def learning_file(data: Path, code: str) -> Path:
    """Where a language's learning data is kept: each its own file, so
    switching back finds it as it was - `learning.sqlite` for Chinese (the
    first there was), `learning-<code>.sqlite` for every other: English's,
    and each pack language's (`learning-ru.sqlite`; decision 0175)."""
    return data / ("learning.sqlite" if code == "zh" else f"learning-{code}.sqlite")


def delete_closed_learning_data(data: Path, open_languages: Iterable[str]) -> int:
    """Empties the learning data of every language that isn't open - one
    learned before and stopped, a pack language whose pack was removed
    (decision 0175) - and deletes the copies set aside from each, as an
    open language's own deletion does (`Vocabulary.delete_learning_data`):
    the level and the categories stay. The learner asked for all of it to
    go from this PC, and the server's copy of these is gone. One that can't
    be opened or emptied (from a newer app, in use) is logged and left; the
    others still go. Returns how many were emptied."""
    in_use = {learning_file(data, code) for code in open_languages}
    emptied = 0
    for path in sorted(data.glob("learning*.sqlite")):
        if path in in_use:
            continue
        if delete_learning_data_at(path):
            emptied += 1
    if emptied:
        log.info("learning data deleted on this PC: %d language(s) not open", emptied)
    return emptied


def kept_level(data: Path, code: str) -> KnownLine | None:
    """A language's level as it was kept beside its learning data
    (decision 0048) - read, never opened: Learning shows the level of a
    language not in use (polyglotic-hq 262). None when there's none, and
    for a language with no dictionary at all."""
    if tier_of(code) is Tier.NONE:
        return None
    stored = read_level_file(learning_file(data, code))
    return KnownLine.stored(stored.scheme, stored.midpoint) if stored else None


def learner_dictionary(english: bool) -> str:
    """The learner's dictionary - its file's name, and the start of every
    entry ID in their learning data: CC-CEDICT for a Chinese learner,
    ECDICT for an English one."""
    return "ecdict" if english else "cedict"


def installer_packs(dictionaries: Path) -> Path:
    """Where a build made with `--packs` keeps the packs it carries
    (decision 0124): `dictionaries/packs` in the app's folder, read before
    any download and never written; from source, nowhere."""
    return dictionaries / "packs" if installed() else dictionaries / "no-packs"


def packs_folder(dictionaries: Path, data: Path) -> Path:
    """Where the dictionary packs are kept (decision 0089): an installed
    copy's with the learner's data (`data`), never in the install folder -
    an update replaces that whole folder, and the Microsoft Store's can't
    be written - so a pack stays through every update; from source, in
    `dictionaries` (`build/dictionaries`), where `tools.dictionaries.packs`
    writes them."""
    if installed():
        return data / "dictionaries"
    return dictionaries / "packs"


def learner_tools(
    dictionaries: Path,
    english: bool,
    data: Path,
    basic: dict[str, BasicDictionary] | None = None,
) -> tuple[LearningTools, BackgroundLearningStore]:
    """The learner's vocabulary and dictionary: CC-CEDICT for a Chinese
    learner, ECDICT for an English one. Each language keeps its own
    learning data, so switching back finds it as it was. With it, the
    learning store, for closing at the end.

    A dictionary file that's missing or can't be read doesn't stop the
    start (polyglotic-hq 199): it's left out, said in the log, and the
    tools' `dictionary_problem` says why - captions run, and lookups say
    what's wrong. One that fails a query later (damaged in the middle)
    goes out then, and the tools' `dictionary_out` says so. The learner's
    data is kept as it is.

    A learning data file that can't be read doesn't stop the start either
    (polyglotic-hq 206): it's set aside, kept, and a new one started
    (`open_learning_store`). One from a newer app still does. One found
    damaged later - a save failing - is set aside then, nothing more is
    saved this session, and the tools' `learning_damaged` says so."""
    file = GuardedDictionary(dictionaries / f"{learner_dictionary(english)}.sqlite")
    dictionary: ChineseDictionary | EnglishDictionary = (
        EnglishDictionary(file) if english else ChineseDictionary(file)
    )
    scheme = ENGLISH_FREQUENCY if english else DEFAULT_CHINESE_SCHEME
    tools, store = _learner(
        lambda: dictionary,
        learning_file(data, "en" if english else "zh"),
        scheme.id,
        basic,
        dictionary_problem=lambda: file.problem,
    )
    file.on_problem = lambda _: tools.dictionary_out.emit()  # a query failed
    return tools, store


def pack_learner_tools(
    code: str, data: Path, basic: dict[str, BasicDictionary]
) -> tuple[LearningTools, BackgroundLearningStore]:
    """A pack language's learner (decision 0175; polyglotic-hq 391): its
    vocabulary over its own learning data file (`learning_file`), its
    dictionary the language's pack as `basic` holds it now - one that
    arrives or is replaced during the run answers from then on, and one
    removed leaves a dictionary that finds nothing. A pack has no levels:
    the line is a number of words, estimated at `UNKNOWN_LEVEL_LINKS_FROM`
    until the learner says (as its links were before it kept anything),
    and its bands are frequency cut-offs (`ENGLISH_FREQUENCY`'s: plain
    ranks, whatever the language). The learning data is treated as
    Chinese's and English's are: set aside when it can't be read, refused
    from a newer app (`LearningStoreFormatError`)."""
    nothing = absent_dictionary(code)
    return _learner(
        lambda: basic.get(code, nothing),
        learning_file(data, code),
        ENGLISH_FREQUENCY.id,
        basic,
        pack=code,
        starting=KnownLine.words(UNKNOWN_LEVEL_LINKS_FROM),
    )


def _learner(
    dictionary_now: Callable[
        [], ChineseDictionary | EnglishDictionary | BasicDictionary
    ],
    path: Path,
    scheme_id: str,
    basic: dict[str, BasicDictionary] | None,
    dictionary_problem: Callable[[], DictionaryProblem | None] | None = None,
    pack: str | None = None,
    starting: KnownLine | None = None,
) -> tuple[LearningTools, BackgroundLearningStore]:
    """A language's vocabulary over its learning data at `path`, and its
    tools (`learner_tools`, `pack_learner_tools`). `dictionary_now`: the
    language's dictionary, asked each time - a pack's can change during
    the run."""

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return dictionary_now().facts(entry_id, scheme)

    def words_past(
        after: int, limit: int, scheme: str
    ) -> Sequence[tuple[int, EntryFacts]]:
        return dictionary_now().words_past(after, limit, scheme)

    def level_words(scheme: str, level: int) -> int | None:
        # a level's words: how a line kept as a level places word links (338)
        found = SCHEMES.get(scheme)
        return found.words_at(level) if found else None

    path.parent.mkdir(parents=True, exist_ok=True)
    opened: list[SqliteLearningStore] = []

    def open_store() -> SqliteLearningStore:
        opened.append(open_learning_store(path))
        return opened[-1]

    # Learning's saves on a thread of their own: never waited for here
    store = BackgroundLearningStore(open_store)
    # the dictionary's words in frequency order: the learning load's (324)
    load_words = PlacedAhead(words_past)  # read off this thread

    def vocabulary_over(store: BackgroundLearningStore) -> Vocabulary:
        return Vocabulary(
            store,
            facts,
            scheme_id,
            placed=load_words,
            level_words=level_words,
            starting=starting,
        )

    vocabulary = vocabulary_over(store)
    if store.out:  # its first read found damage SQLite's check missed: set
        store.close()  # aside as at the start, and a new one (206)
        store = BackgroundLearningStore(open_store)
        vocabulary = vocabulary_over(store)
    # after a dictionary update (decision 0007): one query, not one a word met
    vocabulary.follow_merged_entries(dictionary_now().merged_ids())
    tools = LearningTools(
        vocabulary,
        dictionary_now(),
        deck_writer=GenankiDeckWriter(),
        basic=basic,
        dictionary_problem=dictionary_problem,
        learning_data_new=opened[-1].created,
        learning_set_aside=next((o.set_aside for o in opened if o.set_aside), None),
        load_words=load_words,
        pack=pack,
    )
    store.on_damaged = tools.learning_damaged.emit  # later: a save failed (206)
    store.on_deleted = tools.learning_deleted.emit  # its files set aside too (213)
    store.on_not_deleted = tools.learning_not_deleted.emit  # some left (306)
    return tools, store


def tools_beside(
    tools: LearningTools,
    dictionaries: Path,
    data: Path,
    languages: LearningLanguages,
    own: str | None = None,
) -> list[tuple[LearningTools, BackgroundLearningStore]]:
    """Every other full language learned (`open_beside`; until one is, every
    other full one but the learner's `own`) and every pack language learned
    whose pack is open (`packs_beside`; decision 0175) not open yet,
    opened beside `tools` - at the start, and as one is added during the
    run - each as `learner_tools` opens the main one: its own dictionary
    and its own learning data file (DECISIONS #110, decision 0095). A
    Chinese line is then looked up, counted and saved in Chinese's, an
    English one in English's. One dictionary missing or damaged, or one
    learning data file set aside, leaves the other working: each says so
    for itself. One whose learning data is from a newer app - which stops
    a start for the main language - stays closed, said in the log, and its
    lines are looked up as before. Each one opened, with its learning
    store, to close at the end."""
    opened = []
    for code in (
        *open_beside(languages, tools.language, own),
        *packs_beside(languages, tools.basic),
    ):
        if code in tools.also:
            continue
        try:
            # the same basic packs as the main tools' (327): one dict for all
            if tier_of(code) is Tier.FULL:
                other, store = learner_tools(
                    dictionaries, code == "en", data, tools.basic
                )
            else:
                other, store = pack_learner_tools(code, data, tools.basic)
        except LearningStoreFormatError as e:  # its type only: content-free
            log.warning("%s's learning data left closed: %s", code, type(e).__name__)
            continue
        tools.learn_beside(other)
        opened.append((other, store))
    if opened:  # language codes only
        log.info("learning data open: %s", ", ".join(t.language for t in tools.every))
    return opened


def start_logging(data: Path) -> None:
    """To a rotating file in the data folder - the log the feedback form
    shows and attaches, where an exception is written as its type and
    place only (`ContentFreeLog`) - and, from source, to the console as
    well (installed, the app has none: sys.stderr is None). From source
    too, so a report sent while trying the app carries its log
    (polyglotic-hq project 062)."""
    form = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    folder = data / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    file = logging.handlers.RotatingFileHandler(
        folder / "polyglotic.log",
        maxBytes=LOG_BYTES,
        backupCount=LOG_FILES,
        encoding="utf-8",
    )
    file.setFormatter(ContentFreeLog(form))
    handlers: list[logging.Handler] = [file]
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(form))
        handlers.append(console)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in handlers:
        root.addHandler(handler)
    # The caption log (core.listening.delays; polyglotic-hq 271): a line per
    # caption event, several a second while someone talks - in a file of
    # its own, so it never pushes the app's own lines out of theirs.
    captions = logging.handlers.RotatingFileHandler(
        folder / CAPTION_LOG_FILE,
        maxBytes=CAPTION_LOG_BYTES,
        backupCount=CAPTION_LOG_FILES,
        encoding="utf-8",
    )
    captions.setFormatter(ContentFreeLog("%(asctime)s %(message)s"))
    caption_log = logging.getLogger(CAPTION_LOG)
    caption_log.addHandler(captions)
    caption_log.propagate = False


class ContentFreeLog(logging.Formatter):
    """The log file's lines, with an exception (`log.exception`, ours or a
    library's) as its type and where it was raised, as the crash hook
    writes it - never its traceback, whose file paths hold the user's
    Windows name, nor its message, which may hold a caption, a path or a
    token (polyglotic-hq project 053; 061)."""

    def format(self, record: logging.LogRecord) -> str:
        cached, record.exc_text = record.exc_text, None  # another handler's
        try:
            return super().format(record)
        finally:
            record.exc_text = cached

    def formatException(
        self,
        ei: tuple[type[BaseException], BaseException, TracebackType | None]
        | tuple[None, None, None],
    ) -> str:
        kind, _, tb = ei
        if kind is None:
            return ""
        return f"{type_name(kind)} at {where(tb)}"


def where(tb: TracebackType | None) -> str:
    """Where an exception was raised, as `file.py:line in function` - the
    innermost frame, and the innermost of the app's own when that's
    another. File names only: a full path holds the user's name."""
    frames = traceback.extract_tb(tb)
    if not frames:
        return "an unknown place"

    def place(frame: traceback.FrameSummary) -> str:
        return f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"

    ours = [f for f in frames if "polyglotic_desktop" in Path(f.filename).parts]
    if ours and ours[-1] is not frames[-1]:
        return f"{place(frames[-1])}, from {place(ours[-1])}"
    return place(frames[-1])


def type_name(kind: type[BaseException]) -> str:
    module = kind.__module__
    return (
        kind.__qualname__ if module == "builtins" else f"{module}.{kind.__qualname__}"
    )


class CrashLog:
    """Exceptions nothing caught, logged by their type and where they were
    raised - never their message, which may hold a caption, a path or a
    token. Installed, the app has no console, so without this a failure at
    start ends it without a trace (polyglotic-hq project 042, Medium 4).

    Before the interface runs (`running` False) such an exception ends the
    app: `show_failure`, when given (installed), tells the user first. While
    it runs, Qt hands an exception from a slot here and carries on, and a
    thread's ends only that thread: both are logged, nothing shown.

    Each is also noted in `marker` (when given) - when, its type and place,
    whether at start, and the listening session then (`session`) - so the
    next start can offer to send a report with the log (project 053)."""

    def __init__(
        self,
        show_failure: Callable[[], None] | None = None,
        marker: Path | None = None,
    ) -> None:
        self.show_failure = show_failure
        self.marker = marker
        self.session: Callable[[], str | None] = lambda: None
        self.running = False

    def install(self) -> None:
        sys.excepthook = self.uncaught
        threading.excepthook = self.uncaught_in_thread

    def uncaught(
        self,
        kind: type[BaseException],
        value: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(kind, KeyboardInterrupt):
            return
        stage = "while running" if self.running else "at start"
        log.error("uncaught %s %s, at %s", type_name(kind), stage, where(tb))
        self._note(type_name(kind), where(tb), at_start=not self.running)
        if not self.running and self.show_failure is not None:
            self.show_failure()

    def uncaught_in_thread(self, args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        log.error(
            "uncaught %s on thread %s, at %s",
            type_name(args.exc_type),
            args.thread.name if args.thread is not None else "?",
            where(args.exc_traceback),
        )
        self._note(type_name(args.exc_type), where(args.exc_traceback), False)

    def _note(self, what: str, place: str, at_start: bool) -> None:
        """The latest such error, for the next start (`last_crash`)."""
        if self.marker is None:
            return
        noted = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "what": what,
            "where": place,
            "at_start": at_start,
            "session_id": self.session(),
        }
        try:
            self.marker.parent.mkdir(parents=True, exist_ok=True)
            self.marker.write_text(json.dumps(noted), encoding="utf-8")
        except OSError:
            pass  # the log has it; only the offer is lost


@dataclass(frozen=True)
class LastCrash:
    """An error nothing caught, the last time the app ran."""

    at_start: bool  # it stopped the app starting
    session_id: str | None


def last_crash(marker: Path) -> LastCrash | None:
    """What `CrashLog` noted last time, read once: the note is deleted, so
    Home offers a report for it only once."""
    try:
        noted = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    finally:
        marker.unlink(missing_ok=True)
    if not isinstance(noted, dict):
        return None
    session = noted.get("session_id")
    return LastCrash(
        bool(noted.get("at_start")), session if isinstance(session, str) else None
    )


def show_start_failure(data: Path, show_error: ErrorBox) -> None:
    """The box an installed app shows when it can't start."""
    show_error(
        "Polyglotic",
        "Polyglotic couldn't start, and has closed.\n\n"
        "What went wrong is in its log, which never holds anything you heard,"
        f" said or saw:\n{data / 'logs' / 'polyglotic.log'}\n\n"
        "Try starting it again. If it still won't start, please send us that file.",
    )


class NoApps:
    """The apps with sound, for the install check: none - it looks at
    nothing on the PC."""

    def playing_apps(self) -> list[PlayingApp]:
        return []


def try_the_windows(interface: Interface, desktop: DesktopApp) -> list[str]:
    """Each of the new interface's windows built and shown once (offscreen,
    for the install check), wired as `main` wires them: a caption window,
    the joined window, a transcript and the lookup card, on two made-up
    sources. Returns the windows built, in that order."""
    app = QApplication.instance()
    windows, transcripts = interface.windows, interface.transcripts
    wire_caption_windows(windows, desktop, lambda: None)
    wire_transcripts(transcripts, desktop)
    first, second = SourceId("check-1"), SourceId("check-2")
    built: list[str] = []
    windows.set_captioned([("check-1", first)])
    transcripts.follow()
    if windows.windows["check-1"].isVisible():
        built.append("caption_window")
    windows.set_captioned([("check-1", first), ("check-2", second)])
    windows.join()
    joined = windows.joined_window
    if joined is not None and joined.isVisible():
        built.append("joined_window")
    windows.separate()
    transcripts.follow()
    transcripts.show("check-1")
    shown = transcripts.shown.get("check-1")
    if shown is not None and shown.isVisible():
        built.append("transcript")
    card = windows.card
    if card is not None:
        area = Rect(0, 0, 1280, 720)
        word = WordAt(
            "你好",
            LookupContext("你好"),
            (0, 2),
            Rect(100, 600, 40, 24),
            Rect(80, 590, 600, 44),
            area,
            (0, 0, 0, 2),
        )
        card.pin(word)
        if card.isVisible():
            built.append("lookup_card")
        card.close_card()
    if app is not None:
        app.processEvents()
    return built


def check_install(
    report: Path,
    dictionaries: Path,
    feed: str | None = None,
    learners: Path | None = None,
) -> int:
    """Everything the app needs, built and tried once - Qt (offscreen, so no
    window appears), both dictionaries and the learner's data (in a
    temporary folder), the interface as `main` builds it (`new_interface`)
    and each of its windows (`try_the_windows`), the speech-detection model
    on a second of silence, the Opus encoder - with nothing shown,
    captured, sent or written outside that folder. Writes what it found to
    `report` as JSON; 0 if all of it worked. The release build runs it on
    the packed app to prove the bundle is whole, and to time a start:
    `window_seconds`, from the check's start (after Python's imports) to
    the main window's first paint, and `launch_seconds`, the same from the
    process's launch (the interpreter and the imports included); before
    the paint, one learner's dictionary and data, as a start opens (the
    English learner's are checked after it: polyglotic-hq 400) - the
    budget is `perf.budgets`' START_FROM_SOURCE from source and
    START_PACKED packed. A dictionary that's missing or can't be read is
    named in `dictionaries_out` with why, and fails the check - after
    everything else is built without it, as the app starts without it
    (polyglotic-hq 199). `learning_set_aside` names the learning data
    files set aside in the learner's data folder (`learners`, else the app's),
    each because it couldn't be read (polyglotic-hq 206) - only listed,
    never opened; the app starts with a new one, so the check passes.
    `learning_unreadable` gives, per learning store there, how many rows
    the start leaves out because they can't be read - counts only, read
    without writing (polyglotic-hq 207); the check passes, as the app
    starts without them, unless a store has too many and the app would
    refuse it (`learning_refused`, the store and its table).

    With `feed` (`--updates`), an installed copy also looks there for an
    update and downloads it - never applies it: CI installs a build on its
    runner and proves the updater reads a feed it packed."""
    started = time.perf_counter()
    found: dict[str, object] = {"frozen": installed()}
    try:
        release = this_release()
        found.update(version=release.version, channel=release.channel)
        existing = QApplication.instance()
        app = (
            existing
            if isinstance(existing, QApplication)
            else QApplication(["polyglotic", "-platform", "offscreen"])
        )
        found["qt"] = qVersion()
        # the learning stores are closed before the folder is removed, even
        # when a step fails (Windows can't delete an open SQLite file);
        # anything still open is left to Windows' temporary-files clean-up
        # rather than failing the check
        with (
            tempfile.TemporaryDirectory(
                prefix="polyglotic-check-", ignore_cleanup_errors=True
            ) as folder,
            contextlib.ExitStack() as closing,
        ):
            data = Path(folder)
            # one learner before the window, as a start opens one (`main`:
            # another language learned opens after the first paint); the
            # English learner's dictionary is checked after the timing, not
            # in it - it was timed as part of a wait no one has (400)
            tools, chinese = learner_tools(dictionaries, False, data / "chinese")
            closing.callback(chinese.close)
            # what's missing is named before the window, so a step that fails
            # without its dictionaries still says why (the English learner's
            # is added after the timing, below)
            found["dictionaries"] = [
                file.name for file in sorted(dictionaries.glob("*.sqlite"))
            ]
            out: dict[str, str] = {}
            if (problem := tools.dictionary_problem) is not None:
                out[f"{learner_dictionary(False)}.sqlite"] = problem.value
            found["dictionaries_out"] = out
            store = JsonSettingsStore(data / "settings.json")
            desktop = DesktopApp(store, tools, NoApps())
            closing.callback(desktop.close)
            interface = new_interface(desktop, store, tools, per_app=True)
            closing.callback(interface.close)
            interface.hub.window.show()  # offscreen: a first paint, seen by no one
            app.processEvents()
            painted = time.perf_counter()
            found["window_seconds"] = round(painted - started, 3)
            english_tools, english = learner_tools(dictionaries, True, data / "english")
            closing.callback(english.close)
            if (problem := english_tools.dictionary_problem) is not None:
                out[f"{learner_dictionary(True)}.sqlite"] = problem.value
            # from the launch to the paint: the clock read now, less the time
            # since the paint (the English learner's opening isn't in it)
            since_paint = time.perf_counter() - painted
            found["launch_seconds"] = round(
                os_adapters().seconds_since_launch() - since_paint, 3
            )
            # the Microsoft Store's package it runs from, if any (decision 0056)
            found["store_package"] = os_adapters().store_package()
            learner_data = learners or os_adapters().data_folder()
            found["learning_set_aside"] = set_aside_in(learner_data)
            unreadable = unreadable_in(learner_data)
            found["learning_unreadable"] = {
                name: rows for name, (rows, _) in unreadable.items()
            }
            refused = {name: table for name, (_, table) in unreadable.items() if table}
            found["learning_refused"] = refused
            # imported after the window, as main() has it
            import numpy as np

            from polyglotic_desktop.adapters.signed_feed import (
                FeedNotTrusted,
                public_keys,
                verify,
            )
            from polyglotic_desktop.platform.opus import encode_ogg_opus
            from polyglotic_desktop.platform.speech_detection import (
                SpeechDetector,
                load_model,
            )

            silence = np.zeros(16_000, dtype=np.float32)
            frames = SpeechDetector(load_model()).feed(0.0, silence)
            found["speech_frames"] = sum(frame.speech for frame in frames)
            found["opus_bytes"] = len(encode_ogg_opus(silence))
            found["ready_seconds"] = round(time.perf_counter() - started, 3)
            found["windows"] = try_the_windows(interface, desktop)
            key, signature = RFC8032_TEST_1  # the signed feed's check works here
            verify(b"", signature, public_keys([key]))
            try:
                verify(b"x", signature, public_keys([key]))
            except FeedNotTrusted:
                found["feed_signature_check"] = True
            found["dictionary_pack"] = try_a_pack(learner_data)
            found["installer_packs"] = try_the_installers_packs(
                installer_packs(dictionaries)
            )
            installer = updater(feed or UPDATES)
            found["installed"] = installer.installed()
            if feed is not None and found["installed"]:
                update = installer.find(None, False)
                found["update_found"] = update.version if update else None
                if update is not None:
                    installer.download(update)
                    found["update_downloaded"] = True
        pack = found.get("dictionary_pack", {})
        pack_ok = isinstance(pack, dict) and all(
            pack.get(k) == v for k, v in PACK_CHECKED.items()
        )
        found["ok"] = not out and not refused and pack_ok
        if not pack_ok:
            found["error"] = "a dictionary pack can't be opened and looked up in"
        if out:
            found["error"] = "dictionaries out: " + ", ".join(sorted(out))
        elif refused:
            found["error"] = "learning data refused: " + ", ".join(sorted(refused))
    except Exception as e:  # noqa: BLE001 - reported: a windowless app has no console
        found.update(ok=False, error=f"{type(e).__name__}: {e}")
    report.write_text(json.dumps(found, indent=2), encoding="utf-8")
    return 0 if found["ok"] else 1


CHECK_CAPTURE_SEC = 5.0
"""How long `check_capture` listens to each source."""


class _Heard:
    """What a capture delivered to `check_capture`: counts and the loudest
    sample, never the audio (an `AudioCallback`)."""

    def __init__(self) -> None:
        self.pieces = 0
        self.samples = 0
        self.peak = 0.0

    def __call__(self, start: float, samples: bytes) -> None:
        import numpy as np  # as check_install has it: after the start's imports

        audio = np.frombuffer(samples, dtype="<f4")
        self.pieces += 1
        self.samples += len(audio)
        if len(audio):
            self.peak = max(self.peak, float(np.max(np.abs(audio))))


def check_capture(
    report: Path,
    os_name: str,
    sources: Mapping[str, Callable[[], AudioCapture]],
    seconds: float = CHECK_CAPTURE_SEC,
) -> int:
    """The packed app's capture, tried once on GitHub's Mac (polyglotic-hq
    412): each of `sources` (everything the Mac plays, the default mic)
    started for `seconds` while the job plays a FLEURS clip, so a run
    proves the capture's native libraries (catap's, PortAudio's) load
    inside the app bundle and hear sound. Writes, per source, how much
    audio came, its loudest sample, the capture's name and error - never
    the audio - to `report` as JSON; 0 if every source heard sound.
    Refused on Windows (`os_name` "windows-..."): there it would hear the
    PC it runs on, and the self-hosted runners are the user's own."""
    found: dict[str, object] = {"os": os_name, "seconds": seconds}
    heard_all = False
    if os_name.startswith("windows"):
        found["error"] = "refused on Windows: it would hear this PC"
    else:
        heard_all = True
        for name, make in sources.items():
            heard = _Heard()
            each: dict[str, object] = {}
            try:
                capture = make()
                capture.start(heard)
                time.sleep(seconds / 2)
                each["capturing"] = capture.capturing
                time.sleep(seconds / 2)
                each["error"] = capture.error
                capture.stop()
            except Exception as e:  # noqa: BLE001 - reported by type: it's the point
                each["error"] = type(e).__name__
            each.update(
                pieces=heard.pieces,
                seconds=round(heard.samples / VAD_SAMPLE_RATE, 2),
                peak=round(heard.peak, 4),
                heard=heard.peak > 0,
            )
            heard_all = heard_all and heard.peak > 0
            found[name] = each
    found["ok"] = heard_all
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(found, indent=2), encoding="utf-8")
    return 0 if heard_all else 1


PACK_CHECKED = {
    "unpacked": True,
    "opened": True,
    "found": "рука",
    "vietnamese": ["Học sinh", "đi"],
}
"""What `try_a_pack` finds when a downloaded pack works in this build -
with or without simplemma (the installed app is without: decision 0123,
which the release build's own check holds it to) - and Vietnamese's own
split, plain Python, joining a line's syllables into its pack's words."""


def try_a_pack(folder: Path) -> dict[str, object]:
    """A dictionary pack as a download leaves it, tried in this build
    (decisions 0122, 0123): a small Russian pack written, gzipped, unpacked
    as a download is, opened, and an inflected word looked up through its
    own table; then a small Vietnamese pack's line split into its words -
    so a release can't leave out what packs need (298 found the word
    splits left out)."""
    from polyglotic_desktop.adapters.pack_downloads import _unpack
    from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
    from polyglotic_desktop.ports.dictionary import EntryRecord

    found: dict[str, object] = {}
    folder.mkdir(parents=True, exist_ok=True)
    built = folder / "check-pack.sqlite"
    record = EntryRecord("wiktru:1", "рука", "", "рука́", ("hand",), 1, ())
    write_dictionary(
        built,
        {
            "dictionary": "wiktru",
            "language": "ru",
            "tier": "basic",
            "meanings_language": "en",
            "pack_version": "1",
        },
        [record],
        {"рука": ["wiktru:1"]},
        lemmas={"руку": "рука"},
    )
    packed = folder / "check-pack.sqlite.gz"
    packed.write_bytes(gzip.compress(built.read_bytes()))
    unpacked = folder / "check-pack-unpacked.sqlite"
    _unpack(packed, unpacked, built.stat().st_size, lambda _: None)
    found["unpacked"] = unpacked.read_bytes() == built.read_bytes()
    dictionary, file = open_pack(unpacked, "ru")
    try:
        found["opened"] = True
        entries = dictionary.lookup("Руку")
        found["found"] = entries[0].headword if entries else None
    finally:
        file.close()
    found["simplemma"] = importlib.util.find_spec("simplemma") is not None
    vietnamese = folder / "check-pack-vi.sqlite"
    write_dictionary(
        vietnamese,
        {"dictionary": "wiktvi", "language": "vi", "tier": "basic"},
        [
            EntryRecord("wiktvi:1", "học sinh", "", "", ("pupil",), 2, ()),
            EntryRecord("wiktvi:2", "đi", "", "", ("to go",), 1, ()),
        ],
        {"học sinh": ["wiktvi:1"], "đi": ["wiktvi:2"]},
    )
    dictionary, file = open_pack(vietnamese, "vi")
    try:  # its syllables joined into the pack's words (decision 0121)
        line = "Học sinh đi"
        found["vietnamese"] = [line[a:b] for a, b in dictionary.words(line)]
    finally:
        file.close()
    for path in (built, packed, unpacked, vietnamese):
        path.unlink(missing_ok=True)
    return found


INSTALLER_PACK_WORDS = {"ru": "руку", "es": "casas", "ja": "食べ"}
"""A word each pack finds through its own table (an inflected form)."""


def try_the_installers_packs(folder: Path) -> dict[str, str]:
    """The packs a `--packs` build carries (decision 0124), each opened and
    a word of its language looked up: language/meanings -> its version and
    the entry found (`?` if none) - empty for a build without."""
    from polyglotic_desktop.adapters.pack_downloads import PackFolder

    found = {}
    for (language, meanings), (pack, path) in sorted(
        PackFolder(folder).installed().items()
    ):
        dictionary, file = open_pack(path, language)
        try:
            word = INSTALLER_PACK_WORDS.get(language, "")
            entries = dictionary.lookup(word) if word else []
            headword = entries[0].headword if entries else "?"
        finally:
            file.close()
        found[f"{language}/{meanings}"] = f"{pack.version}: {word} -> {headword}"
    return found


def import_the_rest() -> None:
    """The libraries the window doesn't need - pydantic, websockets, numpy,
    onnxruntime - imported on a thread of their own at start: about 0.3 s
    that would otherwise hold the interface thread right after the first
    paint (136). Each module is imported once whichever thread asks first."""
    import polyglotic_desktop.connection.client
    import polyglotic_desktop.connection.exchange
    import polyglotic_desktop.connection.feedback
    import polyglotic_desktop.connection.milestones
    import polyglotic_desktop.connection.sign_in
    import polyglotic_desktop.platform.speech_detection
    import polyglotic_desktop.platform.speech_pipeline  # noqa: F401


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line's options."""
    parser = argparse.ArgumentParser(prog="python -m polyglotic_desktop.main")
    parser.add_argument(
        "--server",
        default=SERVER,
        help=f"the server (default {SERVER}); e.g. http://127.0.0.1:8217",
    )
    parser.add_argument("--dictionaries", type=Path, default=dictionaries_folder())
    parser.add_argument(
        "--data", type=Path, default=None, help="where settings and learning data live"
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="the Credential Manager entry (default: the app's for its own server;"
        " Polyglotic/device@HOST:PORT for any other --server)",
    )
    parser.add_argument(
        "--updates",
        default=UPDATES,
        help=f"the update feed (default {UPDATES}), or a folder on this PC",
    )
    # the developer switch (decision 0031), now the default: accepted and
    # ignored until the first release after it (decision 0032)
    parser.add_argument("--next-interface", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        IN_TRAY,
        action="store_true",
        help="start in the tray, without the main window (as Windows starts it)",
    )
    parser.add_argument(
        "--basic-dictionaries",
        nargs="?",
        const="en",
        choices=["en", "zh"],
        default=None,
        help="developers: the dictionary packs' meanings in English or Chinese,"
        " whatever the interface's language",
    )
    parser.add_argument(
        "--packs-from",
        default=PACKS,
        help=f"developers, from source: the dictionary packs' storage (default"
        f" {PACKS}) - a stand-in to try downloads against, https or this PC's"
        " loopback; an installed copy ignores it",
    )
    parser.add_argument(
        "--packs-key",
        action="append",
        default=[],
        help="developers, from source: a public key (base64) a stand-in's packs"
        " list may be signed with, as well as FEED_KEYS; an installed copy ignores it",
    )
    parser.add_argument(
        "--check-install",
        type=Path,
        metavar="REPORT",
        help="build everything without showing, capturing or connecting;"
        " write what was found to REPORT (JSON) and quit",
    )
    # GitHub's Mac only (polyglotic-hq 412): refused on Windows
    parser.add_argument("--check-capture", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def store_copy_here() -> str | None:
    """The Microsoft Store's package this copy runs from, if it does
    (decision 0056) - asked before anything else, Velopack's start-up
    included. None too where this OS has no adapters yet, so that
    `--check-install` still runs and reports what's missing."""
    try:
        return os_adapters().store_package()  # imports only
    except NoOsAdapters:
        return None


VELOPACK_HOOK = "--veloapp-"
"""How the installer's hooks start the app (`--veloapp-install 1.2.3`):
each exits in `run_installer_hooks`, and none waits for one copy."""


@dataclass(frozen=True)
class FirstCopy:
    """This copy runs: it holds `lock` until the process ends, and answers
    second starts under `name` (polyglotic-hq 310, decision 0101)."""

    name: str
    lock: CopyLock


def this_copy(argv: list[str] | None = None) -> FirstCopy | None:
    """The one copy for this user and data folder (polyglotic-hq 310,
    decision 0101): this one, or the process ends here - after the copy
    that runs brought its window forward (0), at once when started in the
    tray (0), or, when it doesn't answer, after saying so (1). Before
    Velopack's start, whose update ends every copy running from the install
    folder, and before anything is opened. None, with nothing held, for an
    installer's hook, `--check-install` (a folder of its own) and an OS
    with no adapters yet."""
    given = sys.argv[1:] if argv is None else argv
    if any(a.startswith(VELOPACK_HOOK) for a in [*given, *sys.argv[1:]]):
        return None
    args = arguments(argv)
    if args.check_install or args.check_capture:
        return None
    try:
        system = os_adapters()
    except NoOsAdapters:
        return None
    data = args.data or system.data_folder()
    name = one_copy.copy_name(data, one_copy.user())
    lock = system.copy_lock(name)
    asked = partial(one_copy.ask_to_show, name, system.let_to_front)
    started = one_copy.start(lock.take, asked, show=not args.in_tray)
    if started is one_copy.Start.RUNS:
        return FirstCopy(name, lock)
    if started is not one_copy.Start.NO_ANSWER:
        sys.exit(0)
    app = QApplication(sys.argv[:1])  # the learner's language, from the file as it is
    start_interface_language(app, ReadOnlySettings(data / "settings.json"))
    system.show_error("Polyglotic", one_copy.not_answering())
    sys.exit(1)


def windows_deleted() -> None:
    """Every window deleted now, once the event loop has ended - the main
    window with its pages and their panels, the caption windows, the
    transcripts, the lookup card - while Qt and Python are both still up.
    Left to Python's exit, they are torn down in no set order while panels
    are still bound to their views: the crash 261's tests hit at exit (code
    134 on Linux). The windows Quit closed are deleted first (their
    `deleteLater`), then each window left, one at a time, asking Qt again
    after each: deleting one deletes the windows it owns."""
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for _ in range(1000):  # a bound, never reached: each pass deletes one
        alive = QApplication.topLevelWidgets()
        if not alive:
            break
        shiboken6.delete(alive[0])
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main(argv: list[str] | None = None) -> None:
    # the start's parts, by name, from here to the first paint: each
    # `done` ends one (`perf.start_parts`, polyglotic-hq 314)
    start_parts.begin()
    store_copy = store_copy_here()  # whose copy this is comes first
    start_parts.done("arguments")  # (with the rest of them, below)
    # one copy per user and data folder: a second start brings the first's
    # window forward and ends here, before Velopack and anything opened (310)
    copy = this_copy(argv)
    start_parts.done("one_copy")
    if store_copy is None:  # the Store's copy has no Velopack (decision 0056)
        run_installer_hooks()  # the installer's hooks exit here (Velopack)
    args = arguments(argv)
    if args.check_install:
        feed = args.updates if args.updates != UPDATES else None
        sys.exit(check_install(args.check_install, args.dictionaries, feed, args.data))
    system = os_adapters()
    if args.check_capture:
        to_capture = {
            "system": lambda: system.system_capture(None),
            "mic": lambda: system.mic_capture(None),
        }
        sys.exit(check_capture(args.check_capture, system.os_name(), to_capture))
    start_parts.done("arguments")
    taskbar_id = system.taskbar_identity(TASKBAR_ID)  # before any window
    data = args.data or system.data_folder()
    start_logging(data)
    crashes = CrashLog(
        partial(show_start_failure, data, system.show_error) if installed() else None,
        data / CRASH_NOTE,
    )
    crashed = last_crash(data / CRASH_NOTE)  # before this run can note one
    crashes.install()
    release = this_release()
    log.info(
        "Polyglotic %s (%s), taskbar ID %s%s",
        release.version,
        release.channel,
        taskbar_id,
        ", the Microsoft Store's package" if store_copy else "",
    )
    # the Store's copy: the Store updates it, nothing here (decision 0056)
    updater_or_store = None if store_copy else updater(args.updates)
    # on a metered connection, an update waits for the learner (345)
    updates = BackgroundUpdates(
        Updates(updater_or_store, release.channel, system.metered)
    )
    updates.check()  # before anything else is built: a broken start can still update

    # the connection's and speech libraries load on a thread while the window
    # is built, so neither the window nor the interface thread waits on them
    # (they're imported where used, after the first paint - 136)
    threading.Thread(target=import_the_rest, name="imports", daemon=True).start()
    start_parts.done("logging_and_updates")
    app = QApplication(sys.argv[:1])
    # Windows' fonts, read on a thread of their own from now - beside the
    # learner's data, not at Home's first label (about 0.3 s; polyglotic-hq
    # 322, decision 0112)
    fonts = FontsAhead(system.read_fonts)
    fonts.begin()
    # Windows' Text size, from the system font Qt read (135's proposal A)
    style.use_text_scale(style.text_scale_of(app.font()))
    app.setApplicationName("Polyglotic")
    # every window's: its title bar, the taskbar's button and Alt-Tab - else
    # Windows' plain application icon, which Qt's window classes carry
    # (polyglotic-hq 245)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)  # the tray keeps it running
    start_parts.done("application")  # (with the rest of it, below)
    # second starts answered from now on, until Quit (polyglotic-hq 310): a
    # local server, no thread - the first run's questions answer them too
    second_starts = one_copy.SecondStarts(copy.name, app) if copy else None
    start_parts.done("one_copy")
    watchdog = Watchdog(parent=app)  # logs a stretch over 50 ms: names, durations
    watchdog.start()
    start_parts.done("application")
    store = JsonSettingsStore(data / "settings.json")
    # its translators are the app's children; its fonts once they're read
    start_interface_language(app, store, fonts_listed=False)
    # the app's own text size (Settings > App), on Windows': every window from
    # the first run's on is built at it (polyglotic-hq 292, decision 0084)
    style.use_app_text_size(Settings(store).value.app_text_size)
    # on a Mac run from macOS's temporary copy, where it can't update itself:
    # asked once to move to Applications, and opened again from there (433)
    place = system.translocation() if system.translocation else None
    if moved_to_applications(place, Settings(store)):
        store.close()
        watchdog.stop()
        return
    # the dictionary packs (decision 0122): opened after the first paint, into
    # the lookups' own dict every learner's tools read - so a pack downloaded
    # later is looked up at once
    basic: dict[str, BasicDictionary] = {}
    # an unreadable one is set aside; written on a thread of its own, in
    # order - the consent choice and every event (polyglotic-hq 136, 144)
    outbox = BackgroundOutbox(lambda: open_outbox(data / "outbox.sqlite"))
    credentials = system.credentials(credentials_entry(args.server, args.credentials))
    app_info = AppInfo.this_app(system.os_name(), system.os_version())
    # the cohort each code signs in with: applied once the dialog closes -
    # the first run's once the rest is built (polyglotic-hq 279)
    signed_in_cohort = SignedInCohort()

    def redeem_code(typed: str, signed_in: bool = False) -> SignInFailed | None:
        # the connection's, imported here: the first run's code comes before
        # the rest is imported (after the window's first paint)
        from polyglotic_desktop.connection.sign_in import redeem

        try:
            return signed_in_cohort.answered(
                redeem(args.server, typed, credentials, app_info, signed_in=signed_in)
            )
        except ValueError:  # the server's address isn't one the token may go to
            return SignInFailed(SignInProblem.UNREACHABLE)

    # the first run's screens, or new words of the tester agreement: the
    # level, what's shared and the yes (kept once the exchange exists), the
    # code - each after the first with Back (polyglotic-hq 250); no language
    # (293): the tools are the language learned's, or a guess from Windows'
    start_parts.done("settings")

    def tools_then_fonts(
        english: bool,
    ) -> tuple[LearningTools, BackgroundLearningStore]:
        """The learner's tools, made while Windows' fonts are read; then the
        fonts, before the first run's first screen or the window."""
        made = learner_tools(args.dictionaries, english, data, basic)
        start_parts.done("learner")  # the dictionary opened, the data read
        # Windows' first-time work for a first window, in what would be a
        # wait for the fonts (polyglotic-hq 322, decision 0113)
        made_ahead(system.make_native_window)
        start_parts.done("first_window")
        fonts_then_language(fonts, app)
        start_parts.done("fonts")  # what was left of their read, waited for
        return made

    windows_languages = interface_language.windows_languages()
    # the learner's own language, as the guess has it (`starting_language`):
    # it never opens beside the guess until one is learned (`open_beside`)
    own = learned_code(windows_languages[0]) if windows_languages else None
    try:
        started = first_run(
            store,
            tools_then_fonts,
            outbox.consent(),
            redeem_code if credentials.load() is None else None,
            code_again=credentials.install_id() is not None,
            windows_languages=windows_languages,
            kept=lambda code: learning_file(data, code).exists(),
        )
    except NotAgreed:  # closed without the yes: no further (polyglotic-hq 185)
        log.info("the tester agreement wasn't accepted: quitting")
        outbox.close()
        store.close()
        watchdog.stop()
        return
    tools, learning_store, first = started.tools, started.learning_store, started.first
    start_parts.done("learner")  # and the first run's screens, if any
    english = not tools.is_chinese
    # every other full language learned opens beside it once the window has
    # shown (`open_added`): each line looked up and saved in its own
    # (DECISIONS #110, decision 0095), its learning data read, and its word
    # split and read-ahead begun, after the first paint, not before it (306:
    # about 60 ms at 10,000 words met; 314's threads beside the window)
    beside: list[BackgroundLearningStore] = []
    desktop = DesktopApp(
        store,
        tools,
        system.app_list(),
        your_sources=(MIC,),
        light_taskbar=system.light_taskbar,
    )
    # apps one by one: promised, tried (Windows 10 2004 to 22H2), or not
    # (decision 0076) - the log's line says which, and how it went
    per_app = AppsOneByOne(
        system.app_capture_support(),
        desktop.settings,
        system.windows_build(),
        app_info.app_version,
        system.app_capture_trial,
        desktop,
    )
    start_parts.done("app")
    interface = new_interface(
        desktop,
        store,
        tools,
        per_app.on,
        system.keys,
        system.on_top(),
        system.common_apps,
    )
    windows, transcripts, hub = interface.windows, interface.transcripts, interface.hub
    if per_app.fell_back:  # here before: Home offers "Try apps again" (0076)
        hub.fell_back = True
        hub.follow()
    over: QWidget = hub.window  # what today's dialogs open over
    hub.level_of = partial(kept_level, data)  # another language's, on Learning
    hub.show_learning()

    def chosen() -> ListeningSettings:
        """The listening settings now - each window's languages its source's."""
        return listening_settings(
            desktop.settings.value, windows.targets(), windows.spoken_languages()
        )

    # the window first; then the rest - speech detection, the connection
    desktop.show_tray()
    hub.window.keep_in_tray = desktop.tray is not None  # closing it hides it
    hub.window.follows_text_size = True  # a change Qt reports restyles it
    if second_starts is not None:  # a second start: the window, as the tray's Open
        second_starts.show_with(desktop.show_window)
    if notice := start_notice(store.set_aside, windows.taken_off):
        desktop.home_notice.emit(notice)
    # the installed app can start with Windows (176) - not the Store's copy
    # yet: its Run value would be the package's private copy (decision 0056)
    if installed() and store_copy is None and system.start_at_sign_in is not None:
        hub.startup = system.start_at_sign_in(sys.executable)
    start_parts.done("tray")  # and the last wiring before the window shows
    if not (args.in_tray and desktop.tray is not None):
        desktop.show_window()  # started by Windows: in the tray (176)
    start_parts.done("window_shown")
    app.processEvents()  # its first paint
    start_parts.done("first_paint")
    start_parts.end()
    show_whats_new(  # after an update: once per version (polyglotic-hq 345)
        hub,
        desktop.settings,
        release.version,
        started.new,
        interface_language.in_use(app) == interface_language.ENGLISH,
    )
    if desktop.apps is not None:  # the apps with sound: first looked for now (291)
        desktop.apps.look()

    # imported only now - pydantic, websockets, numpy and onnxruntime take
    # about 0.3 s - so the window is up first (108's fix f, project 136)
    from polyglotic_desktop.connection import listening
    from polyglotic_desktop.connection.client import Connection
    from polyglotic_desktop.connection.exchange import DataExchange
    from polyglotic_desktop.connection.feedback import RETRY_EVERY_SEC, FeedbackSender
    from polyglotic_desktop.connection.milestones import Milestones
    from polyglotic_desktop.connection.problem_reports import ProblemReportSender
    from polyglotic_desktop.platform.speech_detection import (
        MIC_GAIN_MAX,
        SpeechDetector,
        load_model,
    )
    from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline

    # the word split's data, off this thread (0.2 s): a caption before it's
    # read shows at once, counted and marked when it is (136); then what Words
    # reads for every word met (polyglotic-hq 212). Begun only now, with the
    # window shown and the libraries in: begun before the window, its thread
    # took the interpreter from the window's build by turns - the window came
    # about 50 ms later at 30,000 words met, and nothing reads a caption or
    # Words before this (polyglotic-hq 314)
    tools.prepare()
    exchanged = QtExchange(tools, desktop, data)
    # an account learning both languages: only the main one's entries come in
    # (the exchange keeps one dictionary's sync); every open language's
    # changes go out - each entry ID names its dictionary
    exchange = DataExchange(
        outbox,
        outbox,
        exchanged,
        learner_dictionary(english),
        whole_state=tools.vocabulary.learning_state,  # after a restore (166)
    )
    # words saved elsewhere while the dictionary is out arrive once it's whole
    if tools.dictionary_problem is None:
        exchange.dictionary_whole()
    else:
        exchange.dictionary_out()
    tools.dictionary_out.connect(exchange.dictionary_out)  # from any thread: locked
    if tools.learning_data_new:  # new, or set aside: what the server keeps comes back
        exchange.learning_data_new()  # (polyglotic-hq 206)

    def to_server(event: LearningEvent | VocabularyChanged) -> None:
        if not isinstance(event, VocabularyChanged):
            exchange.learning(event)

    for each in tools.every:
        each.vocabulary.subscribe(to_server)

    value = desktop.settings.value
    connection: Connection | None = None

    def speech_ready() -> None:
        session = connection.listening if connection is not None else None
        if session is not None:
            session.speech_ready()

    timing = CaptionTiming(
        value.live_interval,
        rules=value.caption_mode.rules,
        max_wait=value.max_wait_for_text,
    )
    # the speech-detection model (onnxruntime; 0.1-0.2 s) loads on a thread
    # of its own; each source's detector is made from it on that source's
    # capture thread, at its first audio - never here (polyglotic-hq 136)
    loader = ThreadPoolExecutor(1, thread_name_prefix="speech-model")
    model = loader.submit(load_model)
    loader.shutdown(wait=False)
    pipeline = SpeechPipeline(
        lambda: SpeechDetector(model.result()),
        timing,
        on_ready=speech_ready,
        outputs_playing=system.outputs_playing,
        new_mic_detector=lambda: SpeechDetector(model.result(), MIC_GAIN_MAX),
    )
    # the install's milestones (usage statistics, with consent): a PC that
    # has never connected is a new install (polyglotic-hq project 134)
    milestones = Milestones(outbox, exchange, app_info)
    # the outbox's reads here first (the exchange's and the milestones'
    # notes): a read waits for the writes queued before it, and the
    # consent choice's are the first (polyglotic-hq project 144)
    if first is not None:
        exchange.choose_consent(*first.choices, agreement=first.agreement)
    # noted in the outbox and sent if due, once a read says whether this PC
    # has connected (it waits for the consent choice's writes): off this
    # thread, as everything else of its is (polyglotic-hq project 136)
    threading.Thread(
        target=lambda: milestones.started(fresh=not exchange.has_connected()),
        name="milestones",
        daemon=True,
    ).start()
    listener = QtListener(desktop, pipeline, updates, hub.account)

    def chinese() -> ChineseDictionary | None:
        """The Chinese dictionary open now, the learner's or one beside."""
        dictionary = tools.of("zh").dictionary
        return dictionary if isinstance(dictionary, ChineseDictionary) else None

    listener.mandarin = mandarin = MandarinScript(chinese)

    def follow_script() -> None:
        mandarin.traditional = shows_traditional(desktop.settings.value)

    follow_script()
    desktop.settings.changed.connect(follow_script)
    listener.plan_shown.connect(hub.show_plan)
    # a busy time, said where the learner looks
    listener.busy_changed.connect(windows.set_busy)
    listener.spoken_per_source.connect(windows.set_spoken_per_source)
    listener.busy_changed.connect(hub.set_busy)
    listener.update_found.connect(hub.set_update_found)
    listener.clock_doubted.connect(hub.home.state.set_clock_looks_wrong)
    connection = Connection(
        args.server, credentials, app_info, exchange, listener, milestones=milestones
    )
    wire_maintenance(connection, listener, desktop, hub, windows)
    account = hub.account
    reports = FeedbackFolder(data / "feedback")
    feedback = QtFeedback(desktop)
    sender = FeedbackSender(args.server, credentials, reports, feedback.outcome)

    problem_reports = ProblemReportFolder(data / "problem-reports")
    problem_sender = ProblemReportSender(
        args.server, credentials, problem_reports, feedback.outcome_of
    )

    crashes.session = lambda: listener.session_id

    def cohort_seen(cohort: str | None) -> None:
        """The account's test group, from a session's `welcome` or the
        redeem answer of a code just signed in with (`cohort_known`)."""
        if cohort is not None:
            cohort_known(cohort, desktop.settings, exchange, windows.set_reporting)

    listener.cohort_seen.connect(cohort_seen)
    # the caption windows' strips too (a tester's, as last known)
    windows.set_reporting(is_tester(desktop.settings.value))
    cohort_seen(signed_in_cohort.take())  # the first run's code, if it signed in
    windows.report_wanted.connect(lambda: open_feedback("problem"))
    report_window = OneReportWindow()

    def open_problem_report(
        session_id: str | None, check_result: str | None = None
    ) -> None:
        """An alpha tester's "Report a problem": the dialog over the window,
        not modal; what's left ticked is kept and sent off this thread. One
        at a time: asked again, the open one comes to the front (278)."""
        from polyglotic_desktop.connection import protocol

        if report_window.front():
            return
        captions = captions_as_shown(desktop.feed.history.captions, datetime.now(UTC))
        speech = speech_by_source(pipeline.held_speech())
        names = {str(sid): title for sid, (_, title) in sources.shown().items()}
        for part in speech:
            if desktop.feed.history.is_yours(part.source_id):
                names[str(part.source_id)] = mic_name()
        log_text = read_log(data / "logs")
        values = desktop.settings.value.to_stored()
        facts = report_facts(app_info, release.channel, speech, per_app.line)
        dialog = ProblemReportDialog(
            problem_report_parts(
                log_text, values, facts, captions, speech, names, check_result
            ),
            feedback_versions(app_info),
            over,
        )

        def send() -> None:
            text, ticked = dialog.chosen()
            if check_result and "check" in ticked:
                text = f"{text}\n\n--- no-captions check ---\n{check_result}".strip()
            report = ProblemReport(
                id=str(uuid.uuid4()),
                at=protocol.at(datetime.now(UTC)),
                text=text[:5000],
                app_version=app_info.app_version,
                os=app_info.os,
                os_version=app_info.os_version,
                session_id=session_id,
                log=log_text if "log" in ticked else None,
                settings=values if "settings" in ticked else None,
                facts=facts if "facts" in ticked else None,
                captions=captions if "captions" in ticked else None,
                speech=tuple(
                    ReportedSpeech(
                        str(clip.caption_id),
                        str(clip.source_id),
                        clip.category.value,
                        clip.start,
                        clip.end,
                        clip.audio,
                    )
                    for part in speech
                    if f"speech:{part.source_id}" in ticked
                    for clip in part.clips
                ),
            )
            feedback.just_sent = report.id
            if credentials.load() is None:
                desktop.show_feedback("sign_in", True)
            problem_sender.keep_and_send(report)

        dialog.sent.connect(send)
        report_window.opened(dialog)
        dialog.show()
        dialog.raise_()

    def open_feedback(
        kind: str, session_id: str | None = None, check_result: str | None = None
    ) -> None:
        if kind == "problem" and is_tester(desktop.settings.value):
            open_problem_report(session_id or listener.session_id, check_result)
            return
        report = ask_for_feedback(
            cast(ReportKind, kind),
            data / "logs",
            app_info,
            session_id or listener.session_id,
            reports,
            over,
            check_result,
        )
        if report is None:
            return
        feedback.just_sent = report.id
        if credentials.load() is None:
            desktop.show_feedback("sign_in", True)
        sender.send_waiting()

    desktop.feedback_wanted.connect(open_feedback)
    desktop.check_report_wanted.connect(
        lambda result: open_feedback("problem", check_result=result)
    )
    desktop.set_activity(pipeline.activity)
    settings_page = hub.settings
    settings_page.check_for_updates.connect(updates.check)

    def restart_into_update() -> None:
        """Restart now (polyglotic-hq 299): the app quits as Quit does -
        everything saved - and the installer applies the update and starts
        the new version."""
        if not desktop.may_quit():  # a transcript not saved: Cancel (334)
            return
        log.info("restart now: the update applies as the app quits")
        updates.restart_when_quitting()
        desktop.quit.trigger()

    update_shown = UpdateShown(
        hub.home,
        desktop,
        None if store_copy is not None else settings_page,
        restart_into_update,
        updates.download_anyway,
    )
    updates.tell(update_shown.found)
    settings_page.set_notices(third_party_notices())

    if crashed is not None:  # offered once, quietly, on Home
        hub.home.offer_crash_report(crashed.at_start)
        hub.home.crash_report_wanted.connect(
            lambda: open_feedback("problem", crashed.session_id)
        )
    settings_page.set_version(
        release.version, release.channel, store=store_copy is not None
    )

    def counted(event: LearningEvent | VocabularyChanged) -> None:
        if not isinstance(event, VocabularyChanged):
            connection.learned(event)  # lookups and saves, in the session's summary

    for each in tools.every:
        each.vocabulary.subscribe(counted)
    # the listening settings reach the session once a change settles (273)
    handoff = SettingsHandoff(lambda: connection.listening, chosen, desktop)

    # dictation's pieces (polyglotic-hq 283, decision 0073) wait here and go
    # out on the listening session before the captions' speech: the learner
    # is waiting for them
    from polyglotic_desktop.core.listening.pending import PendingSpeech

    dictation_waiting: PendingSpeech[bytes | None] = PendingSpeech()
    dictation_lock = threading.Lock()

    def dictation_send(request: TranscriptionRequest, speech: bytes) -> None:
        with dictation_lock:
            dictation_waiting.put(request, speech)
        speech_ready()

    def dictation_forget() -> None:
        """Dictation gave its pieces up: none still waiting is sent
        (polyglotic-hq 299)."""
        with dictation_lock:
            dictation_waiting.clear()

    def speech_to_send() -> tuple[Decision, bytes | None] | None:
        """What the listening session sends next: a dictation's piece first,
        then the captions' speech (the pipeline's)."""
        with dictation_lock:
            ready = dictation_waiting.take()
        return ready if ready is not None else pipeline.take()

    def listen() -> None:
        current, settings = desktop.settings.value, chosen()
        session = connection.start_listening(
            settings,
            speech_to_send,
            current.live_interval,
            current.caption_mode,
        )
        handoff.started(session, settings)

    def not_listening() -> None:
        """Home's state while nothing is chosen to caption (no session)."""
        signed_in = credentials.load() is not None
        desktop.set_connection(
            ConnectionState.NOT_CONNECTED
            if signed_in
            else ConnectionState.SIGN_IN_NEEDED
        )

    def sign_in() -> None:
        again = credentials.install_id() is not None  # signed in here before (288)
        if SignInDialog(redeem_code, over, again=again).exec():
            account.set_signed_in(True)
            cohort_seen(signed_in_cohort.take())  # before the reports go
            sender.send_waiting()  # reports kept until now
            problem_sender.send_waiting()
            connection.stop_listening()  # the one that stopped for want of a token
            if not listen_then_sync(connection, listen, desktop.settings.value):
                not_listening()

    def listen_here() -> None:
        """Home's "Listen here" after listening moved to another device: the
        stopped session goes, and a new one takes listening back (the other
        device is then the one told)."""
        connection.stop_listening()
        if not listen_then_sync(connection, listen, desktop.settings.value):
            not_listening()

    hub.home.listen_here_wanted.connect(listen_here)

    def have_code() -> None:
        """Account's "I have a code", signed in: the code from a Plus email,
        onto this account (polyglotic-hq 185); then a new session, whose
        `welcome.plan` says the Plus it brought."""
        if SignInDialog(partial(redeem_code, signed_in=True), over).exec():
            cohort_seen(signed_in_cohort.take())  # the account's, as it was
            listen_here()

    account.have_code.triggered.connect(have_code)

    def plus_again(line: PlanLine) -> None:
        if plus_is_back(desktop.connection, line):
            listen_here()

    listener.plan_shown.connect(plus_again)

    def sign_out() -> None:
        if confirm_sign_out(over, unsent=exchange.has_waiting()):
            account.set_signed_in(False)
            dropped = reports.clear()  # nothing from this account reaches the next
            dropped += problem_reports.clear()
            desktop.settings.update(cohort=None)  # the next account says its own
            windows.set_reporting(False)
            if dropped:
                log.info("signed out: %d waiting report(s) dropped", dropped)
            desktop.set_connection(ConnectionState.SIGN_IN_NEEDED)
            threading.Thread(target=connection.sign_out, daemon=True).start()

    def choose_what_to_share() -> None:
        dialog = ConsentDialog(
            exchange.consent, over, tester=is_tester(desktop.settings.value)
        )
        if dialog.exec():  # the yes given at start goes with it
            exchange.choose_consent(*dialog.choices(), agreement=dialog.agreement())

    def delete_learning() -> None:
        # every open language's copies set aside: deleted with them (306)
        set_aside = sum(s.set_aside_copies() for s in (learning_store, *beside))
        dialog = DeleteLearningDialog(over, set_aside)
        if dialog.exec():
            pipeline.forget_recent()
            problem_reports.clear()  # a waiting report's captions and audio too
            exchanged.delete_here = dialog.delete_on_this_pc()
            exchange.delete_learning()

    account.sign_in.triggered.connect(sign_in)
    account.sign_out.triggered.connect(sign_out)
    account.your_data.triggered.connect(choose_what_to_share)
    account.delete_learning.triggered.connect(delete_learning)
    signed_in = credentials.load() is not None
    account.set_signed_in(signed_in)
    if signed_in and exchange.account is not None:  # before any session (223)
        account.show_account(exchange.account)
    apps = desktop.apps
    assert apps is not None  # main always gives DesktopApp the app list
    aloud = system.sound_out()
    # a looked-up word said aloud in one of the PC's voices - and left out of
    # the captions: the sources that hear it are hushed while it plays
    # (polyglotic-hq 286, decision 0077). Nothing is sent anywhere.
    speaker = system.speaker() if system.speaker is not None else None
    if windows.card is not None and speaker is not None:
        windows.card.use_speech(WordSpeech(speaker, hush=pipeline.hush, parent=desktop))
    if speaker is not None:  # the voices listed once the app has started
        QTimer.singleShot(VOICES_AFTER_START_MS, speaker.look_for_voices)
    # the pages not on show in the window's stylesheet once the start is
    # done, so a first click on one doesn't wait for it (decision 0158)
    QTimer.singleShot(PAGES_STYLED_AFTER_START_MS, hub.window.style_ahead)
    # dictionary packs (decision 0122): opened, and their downloads' thread
    # started, after the first paint; a newer version looked for later
    packs = PackDelivery(
        packs_folder(args.dictionaries, data),
        basic,
        args.basic_dictionaries or pack_meanings(interface_language.in_use(app)),
        pack_reader(app_info.app_version),
        *pack_storage(args.packs_from, args.packs_key, installed()),
        metered=system.metered,
        also=(installer_packs(args.dictionaries),),
        open_url=_open_pack_url,
        parent=desktop,
    )
    hub.use_packs(packs)
    packs.notice.connect(desktop.home_notice)
    if windows.card is not None and isinstance(windows.card.model.offer, LearningOffer):
        windows.card.model.offer.packs = packs  # "Learn it too" says its size

    after_packs: list[Callable[[], None]] = []  # once the packs are opened

    def start_packs() -> None:
        packs.start()
        for act in after_packs:
            act()
        hub.show_learning()

    QTimer.singleShot(PACKS_AFTER_START_MS, start_packs)
    pack_updates = QTimer(desktop, interval=PACK_UPDATES_EVERY_MS)
    pack_updates.timeout.connect(packs.check_updates)

    def first_pack_updates() -> None:
        packs.check_updates()
        pack_updates.start()

    QTimer.singleShot(PACK_UPDATES_AFTER_START_MS, first_pack_updates)

    def sample_capture() -> SampleCapture | None:
        """The sample in the language learned, played aloud as it starts."""
        found = sample_file(sample_language(desktop.settings.value, desktop.tools))
        if found is None:
            return None

        def play(audio: Audio, rate: int) -> Callable[[], None]:
            aloud.play(audio, rate)
            return aloud.stop

        return SampleCapture(found, play)

    sources = Sources(
        pipeline,
        apps,
        per_app.on,
        # each tells the trial, if apps one by one is being tried (0076)
        lambda process_id, name: system.app_capture(process_id, name, per_app.trial),
        # the speakers and mic chosen (polyglotic-hq 372): as the settings
        # are when a source starts - choosing another restarts it
        lambda: system.system_capture(desktop.settings.value.speaker_device),
        lambda: system.mic_capture(desktop.settings.value.mic_device),
        desktop.set_app_sources,
        connection.captured,  # per app vs whole system, in the session's summary
        signed_in,  # nothing captured while signed out
        everything_else_capture=lambda left_out: system.everything_else_capture(
            left_out, per_app.trial
        ),
        sample_capture=sample_capture,
    )

    def signed_in_or_out(state: ConnectionState, _retry_in: object) -> None:
        shown = sources.sample_shown
        sources.set_signed_in(state is not ConnectionState.SIGN_IN_NEEDED)
        if shown and not sources.sample_shown:  # signed out: the sample went (223)
            hub.sample_on = hub.sample_ended = False
            follow_settings(windows, desktop, sources)
            hub.follow()

    desktop.connection_changed.connect(signed_in_or_out)

    # dictation (polyglotic-hq 283, decision 0073): off until turned on;
    # then its key, held, opens the mic, and what was said is typed (imported
    # only now, after the window's first paint, like the connection)
    from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
    from polyglotic_desktop.platform.dictation_mic import DictationMic
    from polyglotic_desktop.ui.dictation import Dictating
    from polyglotic_desktop.ui_next.dictation_key import key_words
    from polyglotic_desktop.ui_next.dictation_sign import DictationSign
    from polyglotic_desktop.ui_next.languages import dictation_choices

    def dictation_session(wanted: bool) -> bool:
        """Dictation needs a listening session (`wanted`) - one opens if
        none is; False when signed out - or no longer does: it closes if
        nothing else needs it."""
        if wanted and credentials.load() is None:
            return False
        value = desktop.settings.value
        follow_choice(connection, value, listen, desktop, sources.sample_on, wanted)
        return True

    def dictation_has_mic(held: bool, tail: float) -> None:
        """While dictation has the mic, the mic's captions hear silence: what's
        dictated is never also a "You" line (polyglotic-hq 299)."""
        now = time.perf_counter()  # the captures' clock
        if held:
            pipeline.dictation_holds(now)
        else:
            pipeline.dictation_lets_go(now + tail)

    dictation_mic = DictationMic(  # the mic chosen, each hold (372)
        lambda: system.mic_capture(desktop.settings.value.mic_device)
    )
    dictating = Dictating(
        desktop.settings,
        dictation_mic,
        dictation_send,
        system.type_text,
        system.keyboard_window,
        system.keys,
        dictation_session,
        parent=desktop,
        mic_held=dictation_has_mic,
        forget_unsent=dictation_forget,
    )
    # a session that can't be answered says so at once, not after 10 s (299)
    desktop.connection_changed.connect(
        lambda state, _retry_in: dictating.connection_changed(state)
    )
    dictating.connection_changed(desktop.connection)
    listener.dictated = dictating.answered
    dictation_sign = DictationSign()
    dictating.sign_changed.connect(dictation_sign.show_state)
    dictation_key = DictationKeyHeld(
        lambda key: system.hold_key(
            key, dictating.key_down, dictating.key_up, dictating.key_other
        )
    )
    dictation_was_on = desktop.settings.value.dictation

    def follow_dictation() -> None:
        """Dictation's key taken (or let go) as the settings say - let go
        while Settings' key box listens - and shown in words where it's
        named: Settings, the tray, the sign, Help (polyglotic-hq 289)."""
        nonlocal dictation_was_on
        value = desktop.settings.value
        changed = dictation_key.follow(value.dictation, value.dictation_key)
        if changed and not value.dictation:
            dictating.stop()
        words = key_words(value.dictation_key)
        desktop.show_dictation_key(words)
        hub.help.show_dictation_key(words)
        dictation_sign.key = words
        if value.dictation and not dictation_was_on:
            dictation_sign.show_hint()  # which key to hold, as it's turned on
        dictation_was_on = value.dictation
        settings_page.show_dictation(
            value.dictation,
            value.dictation_key,
            value.dictation_language,
            value.dictation_australian,
            dictation_key.taken,
        )

    def dictation_key_box(listening: bool) -> None:
        dictation_key.box_listening = listening
        follow_dictation()

    def dictation_key_wanted(wanted: str) -> None:
        """A key pressed in Settings: kept if another program doesn't have
        it - else the one before is, and Settings says so."""
        if dictation_key.try_key(wanted, desktop.settings.value.dictation):
            desktop.settings.update(dictation_key=wanted)
        else:
            settings_page.dictation_key_not_taken(wanted)
            follow_dictation()  # the key before, again

    settings_page.dictation_changes.connect(
        lambda changes: desktop.settings.update(**changes)
    )
    settings_page.dictation_key_listening.connect(dictation_key_box)
    settings_page.dictation_key_wanted.connect(dictation_key_wanted)
    # its language as modes at the tray: Detect, English, Mandarin, Cantonese
    desktop.set_dictation_languages(dictation_choices(DICTATION_LANGUAGES))
    desktop.dictation_settings_wanted.connect(hub.open_dictation_settings)
    follow_dictation()

    def listened(update: CaptionUpdate) -> None:
        """Listening time, from finished captions of what the PC played in
        a language being learned, in that language's learning data
        (polyglotic-hq projects 163, 174, 306) - by the source's category,
        never its name; on this PC only."""
        ours = tools.of(update.language)
        if (
            update.kind is CaptionKind.FINISHED
            and ours.learns(update.language)
            and not desktop.feed.history.is_yours(update.source_id)
        ):
            category = sources.category_of_source(update.source_id)
            if category is not SourceCategory.MIC:
                ours.vocabulary.listened(category.value)

    desktop.feed.applied.connect(listened)

    send_settings = handoff.changed

    chosen_sources = [chosen_capture(desktop.settings.value)]

    def sources_chosen(changed: AppSettings) -> None:
        """`source_selected` when the learner changed what to caption (with
        consent): the mode, how many apps, the mic, and an added app's
        category - never its name."""
        now, picked = chosen_capture(changed), list(changed.apps[:LIMIT])
        if now == chosen_sources[0] and set(picked) == set(before_apps[0]):
            return
        added = next((a for a in picked if a not in before_apps[0]), None)
        before_apps[0] = picked
        chosen_sources[0] = now
        category = sources.category_of(added) if added else None
        exchange.usage(
            listening.SOURCE_SELECTED,
            listening.source_selected(now, category),
            datetime.now(UTC),
        )

    before_apps = [list(desktop.settings.value.apps[:LIMIT])]

    def settings_changed() -> None:
        changed = desktop.settings.value
        follow_settings(windows, desktop, sources)
        follow_transcripts(transcripts)
        send_settings()
        pipeline.set_timing(
            changed.caption_mode.rules,
            changed.live_interval,
            changed.max_wait_for_text,
        )
        sources.follow(captured(changed))  # an app chosen ends the sample
        hub.sample_on, hub.sample_ended = sources.sample_on, sources.sample_kept
        sources_chosen(changed)  # after: an app just added has its category
        follow_dictation()
        follow_choice(
            connection,
            changed,
            listen,
            desktop,
            sources.sample_on,
            dictating.session_wanted,
        )

    def try_sample(on: bool) -> None:
        """Home's sample on or off (polyglotic-hq 176): its source, its
        caption window, and listening while it's on."""
        sources.play_sample(on)
        hub.sample_on, hub.sample_ended = sources.sample_on, False
        follow_settings(windows, desktop, sources)
        send_settings()  # its window's languages
        value = desktop.settings.value
        follow_choice(
            connection,
            value,
            listen,
            desktop,
            sources.sample_on,
            dictating.session_wanted,
        )
        hub.follow()

    hub.sample = try_sample
    hub.list_devices = system.sound_devices  # Home's Sound (372)
    hub.read_mic_peak = sources.mic_peak

    def sample_ended() -> None:
        """The sample played to its end (polyglotic-hq 208, 203's option B):
        its window stays for lookups, listening stops once its last caption
        is in (the session sends what waits, then closes), and Home offers
        it again with the next step - an app of the learner's own."""
        sources.end_sample()
        hub.sample_on, hub.sample_ended = False, sources.sample_kept
        follow_settings(windows, desktop, sources)
        value = desktop.settings.value
        follow_choice(
            connection, value, listen, desktop, False, dictating.session_wanted
        )
        hub.follow()

    def sample_window_closed(key: str) -> None:
        if key == SOURCE_KEY_SAMPLE and sources.sample_shown:  # its x: it goes
            try_sample(False)

    windows.stop_wanted.connect(sample_window_closed)

    def apps_changed() -> None:
        """Capturing apps one by one failed here (everything the PC plays
        from now - said once, on Home and the caption windows), or is tried
        again (decision 0076)."""
        sources.per_app = hub.per_app = per_app.on
        hub.fell_back = per_app.fell_back
        settings_changed()  # the sources and windows, now
        hub.follow()
        if per_app.fell_back:
            desktop.home_notice.emit(fell_back_text())
            desktop.caption_notice.emit(fell_back_text())

    per_app.changed.connect(apps_changed)
    hub.apps_again = per_app.try_again

    wire_caption_windows(windows, desktop, send_settings)
    follow_settings(windows, desktop, sources)
    # the mic is captured only while a window shows my speech
    desktop.caption_mic.setChecked(windows.show_mic_anywhere)
    wire_transcripts(transcripts, desktop)
    # what the learner does, in the listening session's summary (project 134)
    transcripts.opened.connect(lambda: connection.did(SessionAction.TRANSCRIPT_OPENED))
    windows.joined_changed.connect(connection.joined)
    connection.joined(windows.joined_window is not None)
    desktop.settings.changed.connect(settings_changed)
    desktop.pause.toggled.connect(pipeline.set_paused)
    # a caption window hidden past the learner's limit: its app's listening
    # pauses until it's shown (polyglotic-hq 335)
    windows.paused_changed.connect(
        lambda: pipeline.set_paused_sources(windows.paused_sources())
    )
    pipeline.set_paused_sources(windows.paused_sources())
    # a hidden window whose transcript is open is being read: not paused
    windows.reading = transcripts.is_open
    # a chosen app opened later: looked for off the interface thread
    apps.found.connect(lambda: sources.follow(captured(desktop.settings.value)))
    looking = QTimer(desktop, interval=APP_CHECK_MS)
    looking.timeout.connect(apps.look)
    looking.start()
    hearing = QTimer(desktop, interval=HEARING_MS)  # for the listening mark

    def heard() -> None:
        windows.heard(pipeline.hearing())
        if sources.sample_done:
            sample_ended()

    hearing.timeout.connect(heard)
    hearing.start()
    # each open language's days: each count names its entry's dictionary
    for each in tools.every:
        share_finished_days(each.vocabulary, exchange)
    sharing = QTimer(desktop, interval=EXPOSURE_DAYS_MS)
    for each in tools.every:
        sharing.timeout.connect(partial(share_finished_days, each.vocabulary, exchange))
    sharing.start()

    tried = set(tools.also)  # the full languages opened, or tried, this run

    def open_added() -> None:
        """Every full language learned beside the main one opens - those
        learned already as the app's loop starts, after the window's first
        paint; one learned during the run (Learning's "Learn it", a lookup's
        "Learn it too") as it's added (306): its dictionary, its learning
        data and its read-ahead; its changes and exposure days going out
        like the others'; its Words section and Learning card; its lines
        marked from the next paint. One that can't open (a learning data
        file from a newer app, which stops a start) stays closed, said in
        the log, and its lines are looked up as before."""
        languages = desktop.settings.value.learning_languages
        wanted = [
            c
            for c in (
                *open_beside(languages, tools.language, own),
                # a pack language learned, once its pack is open (0175): one
                # whose pack comes later is opened then (`packs.changed`)
                *packs_beside(languages, basic),
            )
            if c not in tried
        ]
        if not wanted:  # the usual case: any other setting changed
            return
        tried.update(wanted)  # once each: one left closed isn't tried again
        for other, store in tools_beside(
            tools, args.dictionaries, data, languages, own
        ):
            beside.append(store)
            other.prepare()
            other.vocabulary.subscribe(to_server)
            other.vocabulary.subscribe(counted)
            share_finished_days(other.vocabulary, exchange)
            sharing.timeout.connect(
                partial(share_finished_days, other.vocabulary, exchange)
            )
            hub.language_opened(other)
            other.changed.emit("")  # every window's marks worked out again

    # after the click's own change is drawn: opening reads its learning data
    desktop.settings.changed.connect(lambda: QTimer.singleShot(0, open_added))
    QTimer.singleShot(0, open_added)  # those learned already: after the window
    # a pack language's, once the packs are opened and as one arrives (0175)
    packs.changed.connect(lambda: QTimer.singleShot(0, open_added))
    after_packs.append(open_added)
    checking = QTimer(desktop, interval=CHECK_EVERY_HOURS * 3_600_000)
    checking.timeout.connect(updates.check)
    checking.start()
    sender.send_waiting()  # reports kept from last time
    problem_sender.send_waiting()
    resending = QTimer(desktop, interval=RETRY_EVERY_SEC * 1000)
    resending.timeout.connect(sender.send_waiting)
    resending.timeout.connect(problem_sender.send_waiting)
    resending.start()

    bound = {key: partial(desktop.hotkey_pressed.emit, key) for key in desktop.hotkeys}
    hotkeys = system.hotkeys(bound)
    # another app may have some; a build may register none (398)
    desktop.hotkeys_not_working(not_working(desktop.hotkeys, bound, hotkeys.start()))
    # Home reads its actions; Help names only those that work (400)
    hub.help.show_hotkeys(
        [key for key, action in desktop.hotkeys.items() if hotkey_works(action)]
    )
    # a game that is itself always on top comes to the front: the caption
    # windows go back above it (on the interface's thread)
    in_front = system.foreground_watch(windows.front_changed.emit)

    in_front.start()

    if not signed_in and not started.code_asked:  # the token refused before
        once_running(sign_in)  # (the first run asked for the code before the window)
    # learning syncs, and whatever waited since last time goes out, on it -
    # or, with nothing chosen to caption yet, in a sync session
    if not listen_then_sync(connection, listen, desktop.settings.value):
        not_listening()
    sources.follow(captured(desktop.settings.value))

    def stop() -> None:
        resending.stop()
        sender.close()
        problem_sender.close()
        hotkeys.stop()
        dictation_key.stop()
        dictating.stop()
        dictation_mic.stop()
        in_front.stop()
        looking.stop()
        hearing.stop()
        sharing.stop()
        checking.stop()
        if speaker is not None:
            speaker.close()  # a word being said stops
        pipeline.stop()
        connection.close()  # the last finished speech goes first; the summary is kept
        interface.close()  # the windows' choices saved
        desktop.close()
        store.close()  # after the last save: written before the app ends
        updates.at_exit()
        watchdog.stop()
        outbox.close()  # after the connection's last: what waits is written
        learning_store.close()  # last: after every write queued, the file closed now
        for other in beside:  # each other open language's, the same way
            other.close()

    app.aboutToQuit.connect(stop)
    app.aboutToQuit.connect(packs.close)
    crashes.running = True
    code = app.exec()
    windows_deleted()
    sys.exit(code)


if __name__ == "__main__":
    main()
