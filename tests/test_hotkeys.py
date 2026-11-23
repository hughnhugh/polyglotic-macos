"""The app's hotkeys: each one's key, the keys it can't be, and the ones two
share (core.listening.hotkeys; polyglotic-hq 567, decision 0273)."""

from datetime import datetime

from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.dictation_keys import DictationKey, Refusal
from polyglotic_desktop.core.listening.history import (
    Caption,
    copied_text,
    newest_finished,
)
from polyglotic_desktop.core.listening.hotkeys import (
    DICTATE,
    ORDER,
    Hotkey,
    Platform,
    clashes,
    defaults,
    holder,
    keys,
    refusal,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.settings import AppSettings


def key(text: str) -> DictationKey:
    found = DictationKey.parse(text)
    assert found is not None
    return found


def test_lock_pause_hide_and_back_to_live_have_keys_and_the_rest_none() -> None:
    """Ctrl+Alt+L, P and H, as since the proof of concept; Back to live
    Ctrl+Alt+J (the brief: a default that doesn't clash); the rest are a
    learner's to give - copying takes the clipboard."""
    found = {h.value: str(k) if k else None for h, k in defaults().items()}
    assert found == {
        "lock": "ctrl+alt+l",
        "pause": "ctrl+alt+p",
        "hide": "ctrl+alt+h",
        "live": "ctrl+alt+j",
        "copy": None,
        "preset": None,
        "bigger": None,
        "smaller": None,
        "bar": None,
    }
    for each in defaults().values():
        assert each is None or refusal(each) is None


def test_on_a_mac_they_re_control_command() -> None:
    """⌃⌘ and the letter (polyglotic-hq 428), kept in Qt's names."""
    assert str(defaults(Platform.MAC)[Hotkey.LIVE]) == "ctrl+win+j"
    assert str(keys({}, Platform.MAC)[Hotkey.LOCK]) == "ctrl+win+l"


def test_on_linux_they_re_ctrl_alt_shift() -> None:
    """Ctrl+Alt+L locks the screen on Cinnamon, MATE and Xfce: Linux's own
    are Ctrl+Alt+Shift and the letter (polyglotic-hq 570, decision 0293) -
    none of them a key the app refuses."""
    found = {k.value: str(v) for k, v in defaults(Platform.LINUX).items() if v}
    assert found == {
        "lock": "ctrl+alt+shift+l",
        "pause": "ctrl+alt+shift+p",
        "hide": "ctrl+alt+shift+h",
        "live": "ctrl+alt+shift+j",
    }
    for each in defaults(Platform.LINUX).values():
        assert each is None or refusal(each) is None
    assert str(keys({}, Platform.LINUX)[Hotkey.LOCK]) == "ctrl+alt+shift+l"


def test_the_learner_s_keys_cleared_ones_and_ones_read_wrong() -> None:
    found = keys({"live": "f9", "lock": "", "pause": "nonsense", "else": "f8"})
    assert found[Hotkey.LIVE] == key("f9")
    assert found[Hotkey.LOCK] is None  # cleared: does nothing
    assert found[Hotkey.PAUSE] == key("ctrl+alt+p")  # unreadable: its default
    assert found[Hotkey.COPY] is None
    assert list(found) == list(ORDER)


def test_a_hotkey_needs_a_key_and_never_one_that_types_or_windows_keeps() -> None:
    assert refusal(key("right_ctrl")) is Refusal.HELD_ALONE
    assert refusal(key("ctrl+win")) is Refusal.HELD_ALONE
    assert refusal(key("ctrl+c")) is Refusal.EVERY_PROGRAM
    assert refusal(key("a")) is Refusal.TYPES
    assert refusal(key("win+l")) is Refusal.WINDOWS
    assert refusal(key("alt+j")) is Refusal.ALT
    assert refusal(key("escape")) is Refusal.ESCAPE
    assert refusal(key("ctrl+alt+j"), [key("ctrl+alt+j")]) is Refusal.APP_HOTKEY
    assert refusal(key("f9")) is None
    assert refusal(key("ctrl+shift+f2")) is None


def test_whose_key_it_is() -> None:
    taken = {"lock": key("ctrl+alt+l"), DICTATE: key("right_ctrl"), "copy": None}
    assert holder(key("ctrl+alt+l"), taken) == "lock"
    assert holder(key("ctrl+alt+l"), taken, but="lock") is None
    assert holder(key("right_ctrl"), taken) == DICTATE
    assert holder(key("f9"), taken) is None


def test_two_sharing_a_key_the_first_keeps_it() -> None:
    """A file edited by hand, or dictation's key made a hotkey's: the first
    in order keeps it, the others are named as not working."""
    shared = clashes(
        {
            DICTATE: key("insert"),
            "lock": key("insert"),
            "pause": key("ctrl+alt+p"),
            "live": key("ctrl+alt+p"),
            "copy": None,
            "preset": None,
        }
    )
    assert shared == {"lock": DICTATE, "live": "pause"}


def test_the_settings_keep_hotkeys_and_refuse_a_file_edited_wrong() -> None:
    kept = AppSettings.from_stored({"hotkeys": {"live": "f9", "copy": ""}})
    assert kept.hotkeys == {"live": "f9", "copy": ""}
    for wrong in (
        {"live": "ctrl+c"},  # refused: every program's
        {"live": "right_ctrl"},  # a modifier alone
        {"jump": "f9"},  # no such hotkey
        {"live": 9},
        ["live", "f9"],
    ):
        assert AppSettings.from_stored({"hotkeys": wrong}).hotkeys == {}
    assert AppSettings().hotkeys == {}


def caption(n: int, original: str, live: bool = False, **translations: str) -> Caption:
    now = datetime(2026, 11, 20, 22, 0)
    clause = Clause(
        original, {Language(code): text for code, text in translations.items()}
    )
    return Caption(
        key=n,
        caption_id=CaptionId(f"c{n}"),
        source_id=SourceId("app-1"),
        by_you=False,
        live=live,
        clauses=(clause,),
        language=Language("zh"),
        languages_heard=(Language("zh"),),
        started_at=now,
        updated_at=now,
    )


def test_the_newest_finished_caption_is_copied_with_its_translation() -> None:
    """Copy the newest caption (567): a live one still being spoken isn't
    it; what was said, then the translation, a line each."""
    older = caption(1, "你好", en="Hello")
    newest = caption(2, "明天见", en="See you tomorrow")
    speaking = caption(3, "我们", live=True)
    assert newest_finished((older, newest, speaking)) == newest
    assert newest_finished((speaking,)) is None
    assert copied_text(newest) == "明天见\nSee you tomorrow"
    assert copied_text(caption(4, "好的")) == "好的"
