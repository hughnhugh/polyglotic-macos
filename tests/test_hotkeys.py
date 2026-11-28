"""The app's hotkeys: every key valid with a scope, defaults, clashes, and
conflict-free alternatives (core.listening.hotkeys; polyglotic-hq 567, 966;
decision 0273)."""

from datetime import datetime

import pytest

from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.dictation_keys import (
    KEYS,
    MEDIA_KEYS,
    PUNCTUATION,
    DictationKey,
    Refusal,
)
from polyglotic_desktop.core.listening.history import (
    Caption,
    copied_text,
    newest_finished,
)
from polyglotic_desktop.core.listening.hotkeys import (
    ALTERNATIVE_COUNT,
    DICTATE,
    ORDER,
    Hotkey,
    HotkeyScope,
    Platform,
    candidate_alternatives,
    clashes,
    default_scope,
    defaults,
    find_free_alternatives,
    holder,
    is_typing_key,
    keys,
    refusal,
    scopes,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.settings import AppSettings


def key(text: str) -> DictationKey:
    found = DictationKey.parse(text)
    assert found is not None
    return found


def test_lock_pause_hide_and_back_to_live_have_keys_and_the_rest_none() -> None:
    """Ctrl+Alt+L, P and H default to Everywhere; Space defaults to In
    Polyglotic's windows for Back to live; the learner can bind any key to any."""
    found = {h.value: str(k) if k else None for h, k in defaults().items()}
    assert found == {
        "lock": "ctrl+alt+l",
        "pause": "ctrl+alt+p",
        "hide": "ctrl+alt+h",
        "live": "space",
        "copy": None,
        "preset": None,
        "bigger": None,
        "smaller": None,
        "bar": None,
    }
    for hotkey, each in defaults().items():
        assert each is None or refusal(each, hotkey=hotkey) is None
    assert refusal(key("space"), hotkey=Hotkey.HIDE) is None
    resolved_scopes = scopes(defaults())
    assert resolved_scopes[Hotkey.LOCK] is HotkeyScope.EVERYWHERE
    assert resolved_scopes[Hotkey.PAUSE] is HotkeyScope.EVERYWHERE
    assert resolved_scopes[Hotkey.HIDE] is HotkeyScope.EVERYWHERE
    assert resolved_scopes[Hotkey.LIVE] is HotkeyScope.APP


def test_on_a_mac_they_re_control_command() -> None:
    """⌃⌘ and the letter (polyglotic-hq 428), kept in Qt's names."""
    assert str(defaults(Platform.MAC)[Hotkey.LIVE]) == "space"
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
        "live": "space",
    }
    for hotkey, each in defaults(Platform.LINUX).items():
        assert each is None or refusal(each, hotkey=hotkey) is None
    assert str(keys({}, Platform.LINUX)[Hotkey.LOCK]) == "ctrl+alt+shift+l"


def test_the_learner_s_keys_cleared_ones_and_ones_read_wrong() -> None:
    found = keys({"live": "f9", "lock": "", "pause": "nonsense", "else": "f8"})
    assert found[Hotkey.LIVE] == key("f9")
    assert found[Hotkey.LOCK] is None  # cleared: does nothing
    assert found[Hotkey.PAUSE] == key("ctrl+alt+p")  # unreadable: its default
    assert found[Hotkey.COPY] is None
    assert list(found) == list(ORDER)


@pytest.mark.parametrize(
    "kept",
    [
        "a",
        "z",
        "0",
        "9",
        "space",
        "enter",
        "tab",
        "backspace",
        "delete",
        "left",
        "right",
        "up",
        "down",
        "home",
        "end",
        "page_up",
        "page_down",
        "f1",
        "f9",
        "f12",
        "f24",
        "pause",
        "insert",
        "scroll_lock",
        "print_screen",
        "menu",
        "escape",
        "ctrl+c",
        "alt+j",
        "shift+a",
        "ctrl+shift+f2",
        *PUNCTUATION,
        *MEDIA_KEYS,
    ],
)
def test_every_non_modifier_key_is_valid(kept: str) -> None:
    """966: every key alone or with modifiers is accepted as a hotkey."""
    parsed = key(kept)
    assert refusal(parsed) is None
    assert str(parsed) == kept


def test_every_key_in_keys_parses_and_only_modifiers_alone_or_dupes_are_refused() -> (
    None
):
    for name in KEYS:
        assert refusal(key(name)) is None
    assert refusal(key("right_ctrl")) is Refusal.HELD_ALONE
    assert refusal(key("ctrl+win")) is Refusal.HELD_ALONE
    assert refusal(key("ctrl+alt+j"), [key("ctrl+alt+j")]) is Refusal.APP_HOTKEY


def test_typing_keys_default_to_app_and_combinations_or_non_typing_to_everywhere() -> (
    None
):
    for typing in (
        "a",
        "7",
        "space",
        "enter",
        "tab",
        "backspace",
        "left",
        "comma",
        "slash",
        "shift+a",
    ):
        parsed = key(typing)
        assert is_typing_key(parsed), typing
        assert default_scope(parsed) is HotkeyScope.APP, typing
    for global_key in (
        "f9",
        "f12",
        "pause",
        "insert",
        "media_play",
        "volume_up",
        "ctrl+c",
        "ctrl+alt+l",
        "alt+j",
        "shift+f9",
    ):
        parsed = key(global_key)
        assert not is_typing_key(parsed), global_key
        assert default_scope(parsed) is HotkeyScope.EVERYWHERE, global_key


def test_scopes_respect_saved_choice_and_fall_back_to_default() -> None:
    chosen = keys({"copy": "space", "bigger": "f9", "hide": ""})
    resolved = scopes(
        chosen, {"copy": "everywhere", "bigger": "app", "lock": "invalid"}
    )
    assert resolved[Hotkey.COPY] is HotkeyScope.EVERYWHERE
    assert resolved[Hotkey.BIGGER] is HotkeyScope.APP
    assert resolved[Hotkey.LOCK] is HotkeyScope.EVERYWHERE  # invalid -> default
    assert resolved[Hotkey.LIVE] is HotkeyScope.APP  # Space default
    assert resolved[Hotkey.HIDE] is HotkeyScope.EVERYWHERE  # unset


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


def test_candidate_and_find_free_alternatives_skip_busy_and_app_keys() -> None:
    current = key("ctrl+alt+p")
    used = {key("ctrl+alt+l"), key("ctrl+alt+h"), key("ctrl+alt+shift+p")}
    candidates = candidate_alternatives(Hotkey.PAUSE, current, used, Platform.WINDOWS)
    assert current not in candidates
    assert all(c not in used for c in candidates)
    assert all(not is_typing_key(c) for c in candidates)
    busy = {str(candidates[0])}
    tested: list[str] = []

    def can_take(text: str) -> bool:
        tested.append(text)
        return text not in busy

    found = find_free_alternatives(candidates, can_take)
    assert len(found) == ALTERNATIVE_COUNT.value == 2
    assert found == [candidates[1], candidates[2]]
    assert tested == [str(candidates[0]), str(candidates[1]), str(candidates[2])]


def test_the_settings_keep_hotkeys_and_scopes_and_refuse_a_file_edited_wrong() -> None:
    kept = AppSettings.from_stored(
        {
            "hotkeys": {"live": "f9", "copy": "space", "hide": ""},
            "hotkey_scopes": {"copy": "everywhere", "live": "app"},
        }
    )
    assert kept.hotkeys == {"live": "f9", "copy": "space", "hide": ""}
    assert kept.hotkey_scopes == {"copy": "everywhere", "live": "app"}
    for wrong in (
        {"live": "right_ctrl"},  # a modifier alone
        {"jump": "f9"},  # no such hotkey
        {"live": "not_a_key"},
        {"live": 9},
        ["live", "f9"],
    ):
        assert AppSettings.from_stored({"hotkeys": wrong}).hotkeys == {}
    for wrong_scope in (
        {"live": "global"},
        {"jump": "app"},
        {"live": 1},
        ["app"],
    ):
        assert (
            AppSettings.from_stored({"hotkey_scopes": wrong_scope}).hotkey_scopes == {}
        )
    assert AppSettings().hotkeys == {}
    assert AppSettings().hotkey_scopes == {}
    # 977: `to_stored` keeps only 0.1.12-valid entries in `hotkeys` and puts
    # newer bindings in `hotkeys_v2`; malformed `hotkeys_v2` leaves valid
    # `hotkeys` intact.
    stored = kept.to_stored()
    assert stored["hotkeys"] == {"live": "f9", "hide": ""}
    assert stored["hotkeys_v2"] == {"copy": "space"}
    assert AppSettings.from_stored(stored) == kept
    assert AppSettings.from_stored(
        {"hotkeys": {"live": "f9"}, "hotkeys_v2": {"copy": "right_ctrl"}}
    ).hotkeys == {"live": "f9"}


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
