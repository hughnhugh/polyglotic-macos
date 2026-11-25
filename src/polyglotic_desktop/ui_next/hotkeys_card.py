"""Settings > Hotkeys: every key the app answers, in one place (polyglotic-hq 567, decision 0273).

The user, 2026-11-20: "Hotkey to jump to line (consider other power user
shortcuts/features) ... customiseable ... global hotkeys customisation
section". Three cards:

- **Hotkeys** (`HotkeysCard`) - pressed anywhere, over a game, a call or a
  video: each one's name, its key in a box that listens for a new one when
  clicked (`dictation_key.KeyBox`, as dictation's), Clear, and Reset all
  under them. A key pressed that can't be one says why on the hotkey's own
  line (`refusal_words`: it types, Windows keeps it, it's another
  hotkey's or dictation's...); one another program has, or one two hotkeys
  share (a file edited by hand), says so there too. A change goes out as
  `hotkey_wanted` (the hotkey's name and its key as kept, "" for none);
  `main` keeps it and takes the keys again.
- **Held while you speak** - dictation's key, named, with the way to
  change it (Settings > Dictation, where it's set: `dictation_wanted`).
- **In a window** - the keys a transcript and the lookup card answer while
  they have the keyboard: Windows' own (Ctrl+F, Ctrl+C, End, Esc), named
  here so every key is in one place, not changed (decision 0273).

No key is ever logged.
"""

from collections.abc import Collection, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QPushButton,
    QWidget,
)

from polyglotic_desktop.core.listening.dictation_keys import (
    DEFAULT_KEY,
    DictationKey,
    Refusal,
)
from polyglotic_desktop.core.listening.dictation_keys import refusal as key_refusal
from polyglotic_desktop.core.listening.hotkeys import (
    DICTATE,
    LIVE_SPACE,
    ORDER,
    RESPEAK,
    Hotkey,
    clashes,
    holder,
)
from polyglotic_desktop.core.listening.hotkeys import (
    defaults as hotkey_defaults,
)
from polyglotic_desktop.core.listening.hotkeys import (
    refusal as hotkey_refusal,
)
from polyglotic_desktop.core.listening.respeaking import DEFAULT_RESPEAK_KEY
from polyglotic_desktop.core.listening.type_theirs import TypeWhat
from polyglotic_desktop.ui_next import os_words
from polyglotic_desktop.ui_next.controls import (
    Card,
    Segmented,
    SwitchRow,
    label,
    right_row,
)
from polyglotic_desktop.ui_next.dictation_key import KeyBox, key_words
from polyglotic_desktop.ui_next.dictation_key import refusal_words as key_refusal_words


def _tr(text: str) -> str:
    return QApplication.translate("Hotkeys", text)


def _tr_settings(text: str) -> str:
    """Settings' own words for the hotkeys it named before (its App card)."""
    return QApplication.translate("Settings", text)


def hotkey_names() -> dict[str, str]:
    """What each hotkey does, by its name, as Settings lists it; dictation's
    key as "Dictate"."""
    return {
        Hotkey.LOCK.value: _tr_settings("Lock all caption windows"),
        Hotkey.PAUSE.value: _tr_settings("Pause captions"),
        Hotkey.HIDE.value: _tr_settings("Hide all caption windows"),
        #: jump every caption window and transcript to its newest line
        Hotkey.LIVE.value: _tr("Back to live"),
        Hotkey.COPY.value: _tr("Copy the newest caption"),
        Hotkey.PRESET.value: _tr("Next preset"),
        Hotkey.BIGGER.value: _tr("Caption text bigger"),
        Hotkey.SMALLER.value: _tr("Caption text smaller"),
        Hotkey.BAR.value: _tr("Open a caption window's controls"),
        DICTATE: _tr("Dictate"),
        RESPEAK: _tr("Type what they said"),
    }


def refusal_words(refusal: Refusal | None) -> str:
    """Why a key can't be a hotkey's, plainly: dictation's words where they
    fit (`dictation_key.refusal_words`), a hotkey's own where they don't."""
    if refusal is Refusal.HELD_ALONE:
        return os_words.pc_mac_or_linux(
            _tr("Hold Ctrl, Alt, Shift or Win with a key, or choose an F key."),
            _tr("Hold ⌘, ⌥, ⇧ or ⌃ with a key, or choose an F key."),
            _tr("Hold Ctrl, Alt, Shift or Super with a key, or choose an F key."),
        )
    if refusal is Refusal.ESCAPE:
        return _tr("Esc closes things in every program: choose another key.")
    if refusal is Refusal.ALT and not os_words.on_a_mac():
        return _tr("Letting go of Alt opens a program's menu: hold Ctrl with it too.")
    return key_refusal_words(refusal)


def shortcut_words(sequence: QKeySequence.StandardKey | str) -> str:
    """A window's key as this OS writes it, in the app's language
    ("Ctrl+F", "Strg+F", "⌘F")."""
    found = QKeySequence(sequence)
    return found.toString(QKeySequence.SequenceFormat.NativeText)


class HotkeyLine(QWidget):
    """One hotkey: what it does, its key (click to change), Clear, and a
    note under them when there's something to say."""

    def __init__(self, name: str, title: str) -> None:
        super().__init__()
        self.setObjectName(f"hotkeys.{name}")
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        self.title = label(title, "RowTitle", wrap=True)
        grid.addWidget(self.title, 0, 0)
        self.box = KeyBox("", f"hotkeys.{name}.key", title)
        self.box.setMinimumWidth(140)
        grid.addWidget(self.box, 0, 1)
        self.clear = QPushButton(_tr("Clear"))
        self.clear.setObjectName(f"hotkeys.{name}.clear")
        self.clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear.setToolTip(_tr("No key: the hotkey does nothing"))
        self.clear.setAccessibleName(_tr("Clear {name}'s key").format(name=title))
        grid.addWidget(self.clear, 0, 2)
        self.note = label("", "Faint", wrap=True)
        self.note.setObjectName(f"hotkeys.{name}.note")
        grid.addWidget(self.note, 1, 0, 1, 3)
        self.note.hide()  # after its parent: never a window of its own
        grid.setColumnStretch(0, 1)

    def show_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setHidden(not text)


class HotkeysCard(Card):
    """The hotkeys, each one's key changed, cleared or all reset."""

    hotkey_wanted = Signal(str, str)
    """A hotkey's name and the key the learner gave it, as kept ("" for
    none) - one nothing here refuses."""
    reset_wanted = Signal()
    """Reset all: every hotkey's key its default."""
    listening = Signal(bool)
    """A key box listens: the app's own keys must let keys through."""

    def __init__(self) -> None:
        self._normal_subtitle = os_words.pc_or_mac(
            _tr(
                "They work from any program, even a game in front. Click a key,"
                " then press the one you want."
            ),
            _tr(
                "They work from any app, even a game in front. Click a key, then"
                " press the one you want."
            ),
        )
        super().__init__(_tr_settings("Hotkeys"), self._normal_subtitle)
        self.setObjectName("settings.hotkeys_card")
        self.names = hotkey_names()
        self.lines: dict[str, HotkeyLine] = {}
        for hotkey in ORDER:
            line = HotkeyLine(hotkey.value, self.names[hotkey.value])
            line.box.pressed_key.connect(
                lambda pressed, n=hotkey.value: self._pressed(n, pressed)
            )
            line.box.listening_changed.connect(self.listening)
            line.clear.clicked.connect(
                lambda _checked=False, n=hotkey.value: self._clear(n)
            )
            self.lines[hotkey.value] = line
            self.add(line)
        self.reset = QPushButton(_tr("Reset all"))
        self.reset.setObjectName("hotkeys.reset")
        self.reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset.setToolTip(_tr("Every hotkey back to its own key"))
        self.reset.clicked.connect(self._reset)
        self.add(right_row(self.reset))
        self._keys: dict[str, DictationKey | None] = {}
        """Each hotkey's key now, and dictation's (`DICTATE`), by name."""
        self._taken: frozenset[str] = frozenset()
        self._unavailable = False
        self._command = "polyglotic"
        self._said: dict[str, str] = {}
        """A refusal said on a hotkey's line until its key next changes."""
        self.show_keys({}, ())

    @property
    def keys(self) -> Mapping[str, DictationKey | None]:
        """Each hotkey's key now, and dictation's (`DICTATE`), by name."""
        return self._keys

    def set_command(self, command: str) -> None:
        """How a desktop shortcut starts this app (`polyglotic` or the AppImage
        path): named in the unavailable notice on GNOME Wayland (647)."""
        self._command = command or "polyglotic"
        if self._unavailable:
            self._update_subtitle()

    def _update_subtitle(self) -> None:
        if self.subtitle is None:
            return
        if self._unavailable:
            self.subtitle.setText(
                _tr(
                    "This desktop doesn't allow global hotkeys. Add a custom "
                    "shortcut in your desktop's keyboard settings (GNOME: "
                    "Settings > Keyboard > Custom Shortcuts) with the command "
                    "{command} --lock, --pause or --hide instead."
                ).format(command=self._command)
            )
        else:
            self.subtitle.setText(self._normal_subtitle)

    def show_keys(
        self,
        keys: Mapping[str, str],
        taken: Collection[str],
        dictation: str | None = None,
        respeak: str | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        """Each hotkey's key now, as kept ("" none) - a hotkey not in
        `keys` has its default; `taken`: those another program has;
        `dictation`: dictation's key while it's on; `respeak`:
        re-speaking's own key, while it has one (567); `unavailable`:
        this desktop doesn't allow global hotkeys (GNOME Wayland, `NoHotkeys`)."""
        defaults = hotkey_defaults(os_words.platform())
        found: dict[str, DictationKey | None] = {
            DICTATE: DictationKey.parse(dictation) if dictation else None,
            RESPEAK: DictationKey.parse(respeak) if respeak else None,
        }
        for hotkey in ORDER:
            text = keys.get(hotkey.value)
            found[hotkey.value] = (
                defaults[hotkey]
                if text is None
                else DictationKey.parse(text)
                if text
                else None
            )
        changed = {n for n in self.lines if found.get(n) != self._keys.get(n)}
        self._said = {n: t for n, t in self._said.items() if n not in changed}
        self._keys = found
        self._taken = frozenset() if unavailable else frozenset(taken)
        self._unavailable = unavailable
        self._update_subtitle()
        shared = clashes(found)
        for name, line in self.lines.items():
            key = found[name]
            line.box.show_key(str(key) if key else "")
            can_edit = not unavailable or name == Hotkey.LIVE
            line.box.setEnabled(can_edit)
            line.clear.setEnabled(can_edit and key is not None)
            if unavailable:
                note = ""
            elif name in self._said:
                note = self._said[name]
            elif name in shared:
                note = _tr("{other} has this key too, and only it works.").format(
                    other=self.names[shared[name]]
                )
            elif name in self._taken:
                note = _tr("Another program has this key: choose another.")
            else:
                note = ""
            if not note and name == Hotkey.LIVE and key == LIVE_SPACE:
                note = _tr("Space works in caption and transcript windows.")
            line.show_note(note)
        self.reset.setEnabled(
            any(
                found[h.value] != defaults[h]
                for h in (ORDER if not unavailable else (Hotkey.LIVE,))
            )
        )

    def _pressed(self, name: str, pressed: str) -> None:
        """A key pressed in a hotkey's box: refused with why, or asked for
        (`hotkey_wanted`) - unless it's the key already."""
        key = DictationKey.parse(pressed) if pressed else None
        if key is None:
            self._say(name, refusal_words(None))
            return
        who = holder(key, self._keys, but=name)
        if who is not None:
            self._say(
                name,
                _tr("{other} has that key: clear it there, or choose another.").format(
                    other=self.names[who]
                ),
            )
            return
        refused = hotkey_refusal(key, hotkey=Hotkey(name))
        if refused is not None:
            self._say(name, refusal_words(refused))
            return
        self._say(name, "")
        if key != self._keys.get(name):
            self.hotkey_wanted.emit(name, pressed)

    def _clear(self, name: str) -> None:
        self._say(name, "")
        self.hotkey_wanted.emit(name, "")

    def _reset(self) -> None:
        self._said.clear()
        self.reset_wanted.emit()

    def _say(self, name: str, text: str) -> None:
        if text:
            self._said[name] = text
        else:
            self._said.pop(name, None)
        self.lines[name].show_note(text)


class HoldKeysCard(Card):
    """The dictation key and a link to its settings."""

    dictation_wanted = Signal()

    def __init__(self) -> None:
        super().__init__(_tr("Held while you speak"))
        self.setObjectName("settings.hold_keys")
        self.dictation = label("", "Dim", wrap=True)
        self.dictation.setObjectName("hotkeys.dictate")
        self.add(self.dictation)
        change = QPushButton(_tr("Change in Dictation"))
        change.setObjectName("hotkeys.dictate.change")
        change.setCursor(Qt.CursorShape.PointingHandCursor)
        change.clicked.connect(self.dictation_wanted)
        self.add(right_row(change))
        self.show_dictation(True, str(DEFAULT_KEY))

    def show_dictation(self, on: bool, key: str) -> None:
        self.dictation.setText(
            _tr("Dictate: hold {key} and speak.").format(key=key_words(key))
            if on
            else _tr("Dictate: off. Turn it on in Dictation.")
        )


class DictationForOthersCard(Card):
    """The speaker-to-text preferences in Settings > Dictation and Hotkeys."""

    respeak_changes = Signal(dict)
    respeak_key_wanted = Signal(str)
    listening = Signal(bool)

    def __init__(self, control_name: str = "hotkeys.respeak") -> None:
        super().__init__(_tr("Type what they said"))
        self.setObjectName("settings.dictation_for_others")
        self.respeak = SwitchRow(
            _tr("Hold a key to type it"),
            _tr(
                "Types what was said, or its translation, from the caption window "
                "you're watching. With no captions, it listens to the speakers "
                "chosen in Settings > Speech."
            ),
            control_name,
        )
        self.respeak.switch.toggled.connect(
            lambda on: self.respeak_changes.emit({"type_theirs": on})
        )
        self.add(self.respeak)
        self.type_label = label(_tr("Type"))
        self.add(self.type_label)
        self.type_what = Segmented(
            [
                (TypeWhat.ORIGINAL, _tr("What they said")),
                (TypeWhat.TRANSLATION, _tr("Its translation")),
            ]
        )
        self.type_what.setObjectName(f"{control_name}_what")
        self.type_what.setAccessibleName(_tr("Type"))
        self.type_what.changed.connect(
            lambda value: self.respeak_changes.emit({"type_what": value})
        )
        self.add(self.type_what)
        self.respeak_way = Segmented(
            [("shared", _tr("Share dictation's key")), ("own", _tr("Its own key"))]
        )
        self.respeak_way.setObjectName(f"{control_name}_way")
        self.respeak_way.changed.connect(self._way)
        self.add(self.respeak_way)
        self.respeak_how = label("", "Faint", wrap=True)
        self.respeak_how.setObjectName(f"{control_name}_how")
        self.add(self.respeak_how)
        self.respeak_box = KeyBox("", f"{control_name}.key", _tr("Type what they said"))
        self.respeak_box.pressed_key.connect(self._pressed)
        self.respeak_box.listening_changed.connect(self._box_listening)
        self.add(self.respeak_box)
        self.respeak_note = label("", "Faint", wrap=True)
        self.respeak_note.setObjectName(f"{control_name}.note")
        self.add(self.respeak_note)
        self.respeak_note.hide()  # after its parent: never a window of its own
        self._dictation_on = False
        self._dictation_key = ""
        self._respeaking = True
        self._own = DEFAULT_RESPEAK_KEY
        self._last_own: str | None = None
        """The learner's last own key, kept while one key for both is in use."""
        self.hotkeys: dict[str, DictationKey | None] = {}
        """The hotkeys' keys now, by name: an own key can't be one."""
        self.show_dictation(True, str(DEFAULT_KEY))

    def use_speaker_clipboard(self) -> None:
        self.respeak.detail.setText(
            _tr(
                "Release to copy the speech to the clipboard, then paste it where you want."
            )
        )

    def show_dictation(self, on: bool, key: str, taken: bool = False) -> None:
        self._dictation_on, self._dictation_key, self._shared_taken = on, key, taken
        self._show_respeak()

    def show_respeaking(
        self,
        on: bool,
        key: str,
        taken: bool = False,
        what: str = TypeWhat.ORIGINAL,
        last_own: str | None = None,
    ) -> None:
        """Speaker typing settings now; `taken`: another program has its own
        key."""
        if (on, key) != (self._respeaking, self._own):
            self._say("")
        self._respeaking, self._own = on, key
        if last_own:
            self._last_own = last_own
        if key:
            self._last_own = key
        self.type_what.set_value(what)
        self._show_respeak()
        if on and key and taken:
            self.show_key_conflict(key)

    def show_key_conflict(self, wanted: str) -> None:
        """Report an unavailable binding without taking keyboard focus."""
        self._say(
            _tr("Another program has {key}: choose another.").format(
                key=key_words(wanted)
            )
        )

    def not_taken(self, wanted: str) -> None:
        """The learner tried this key: invite them to press another."""
        self.show_key_conflict(wanted)
        self.respeak_box.setVisible(True)
        self.respeak_box.setChecked(True)

    def _show_respeak(self) -> None:
        self.respeak.switch.set_quietly(self._respeaking)
        self.type_label.setVisible(self._respeaking)
        self.type_what.setVisible(self._respeaking)
        own = bool(self._own) or self.respeak_box.listening
        self.respeak_way.set_value("own" if own else "shared")
        self.respeak_way.setEnabled(self._respeaking)
        self.respeak_box.setVisible(self._respeaking and own)
        self.respeak_box.show_key(self._own)
        dictation = key_words(self._dictation_key)
        if own:
            how = _tr("Hold {key} while they speak.").format(
                key=key_words(self._own) if self._own else _tr("the key you choose")
            )
        elif self._dictation_on:
            how = _tr(
                "Tap {key}, then hold it while they speak. Held without a tap, it dictates."
            ).format(key=dictation)
        else:
            how = _tr("Hold {key} while they speak.").format(key=dictation)
        self.respeak_how.setText(how)
        self.respeak_how.setHidden(not self._respeaking)
        if self.uses_dictation_key and self._shared_taken:
            self.show_key_conflict(self._dictation_key)

    def _way(self, value: object) -> None:
        if value == "shared":
            self.respeak_box.stop()
            self._say("")
            if self._own:
                self.respeak_changes.emit({"respeak_key": ""})
            self._show_respeak()
        elif not self._own:
            # Sharing is a reversible choice, not deletion of the learner's
            # accepted own key. `main` still checks that it can take it now.
            if self._last_own is not None:
                self.respeak_key_wanted.emit(self._last_own)
            else:  # no own key has been accepted yet: listen for the first one
                self.respeak_box.setVisible(True)
                self.respeak_box.setChecked(True)

    def _box_listening(self, on: bool) -> None:
        self.listening.emit(on)
        if not on:
            self._show_respeak()  # Esc with no key pressed: one key for both

    def _pressed(self, pressed: str) -> None:
        key = DictationKey.parse(pressed) if pressed else None
        if key is None:
            self._say(key_refusal_words(None))
            return
        taken = dict(self.hotkeys)
        if self._dictation_on:
            taken[DICTATE] = DictationKey.parse(self._dictation_key)
        who = holder(key, taken)
        if who is not None:
            self._say(
                _tr("{other} has that key: clear it there, or choose another.").format(
                    other=hotkey_names()[who]
                )
            )
            return
        refused = key_refusal(key)
        if refused is not None:
            self._say(key_refusal_words(refused))
            return
        self._say("")
        if pressed != self._own:
            self.respeak_key_wanted.emit(pressed)

    @property
    def uses_dictation_key(self) -> bool:
        return self._respeaking and not self._own

    @property
    def own_key(self) -> str | None:
        """Re-speaking's own key while it's on and has one, as kept."""
        return self._own if self._respeaking and self._own else None

    def _say(self, text: str) -> None:
        self.respeak_note.setText(text)
        self.respeak_note.setHidden(not text)


def window_keys() -> list[tuple[str, str]]:
    """The keys a window answers while it has the keyboard, as they're
    listed: what each does, and its key as this OS writes it."""
    find = shortcut_words(QKeySequence.StandardKey.Find)
    copy = shortcut_words(QKeySequence.StandardKey.Copy)
    home = f"{shortcut_words('Home')} / {shortcut_words('Ctrl+Home')}"
    end = f"{shortcut_words('End')} / {shortcut_words('Ctrl+End')}"
    return [
        (_tr("Search a transcript"), find),
        (_tr("Jump to the first caption"), home),
        (_tr("Back to live in a caption or transcript window"), end),
        (_tr("Copy what's selected"), copy),
        (_tr("Close the search or the lookup"), shortcut_words("Esc")),
    ]


class WindowKeysCard(Card):
    """The keys windows answer while they have the keyboard - named, not
    changed (decision 0273)."""

    def __init__(self, control_name: str = "hotkeys.respeak") -> None:
        super().__init__(
            _tr("In a window"),
            _tr(
                "While a caption window, a transcript or a word's card is the active window."
            ),
        )
        self.setObjectName("settings.window_keys")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row, (what, key) in enumerate(window_keys()):
            grid.addWidget(label(what, wrap=True), row, 0)
            grid.addWidget(label(key, "Dim"), row, 1)
        grid.setColumnStretch(0, 1)
        self.add(grid)
