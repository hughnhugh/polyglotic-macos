"""Dictation's key in words, and the box that listens for the one the learner wants (polyglotic-hq 289, decision 0081).

- `key_words`: a key as its keys are labelled, joined - "Right Ctrl",
  "Ctrl + Alt + D", "F9" - for Settings, the tray, the sign and Help; on a
  Mac as its menus write it, "Right ⌘", "⌃⌘D" (polyglotic-hq 429: Qt's Ctrl
  is Command there and its Meta, kept as "win", Control).
- `refusal_words`: why a key can't be dictation's, plainly.
- `KeyCapture`: what was pressed, from the keys going down and up - a
  key with the modifiers held at that moment ("ctrl+alt+d"), or, if only
  modifiers were pressed, the one modifier by its side ("right_ctrl") or
  the modifiers together ("ctrl+win"), once one comes up.
- `KeyBox`: a button showing the key; clicked, it listens for the next key
  or combination (Esc stops it) and says what was pressed (`pressed`).
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFocusEvent, QHideEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QPushButton

from polyglotic_desktop.core.listening.dictation_keys import (
    KEYS,
    DictationKey,
    Modifier,
    Refusal,
)
from polyglotic_desktop.ui_next import os_words


def _tr(text: str) -> str:
    return QApplication.translate("DictationKey", text)


MAC_SYMBOLS = {
    Modifier.WIN.value: "⌃",
    Modifier.ALT.value: "⌥",
    Modifier.SHIFT.value: "⇧",
    Modifier.CTRL.value: "⌘",
}
"""A Mac's modifiers as its keyboards and menus print them, in Apple's
order (Control, Option, Shift, Command). Qt's names: on a Mac Qt's Ctrl
is Command and its Meta ("win") is Control (polyglotic-hq 429)."""


def _mac_name(part: str) -> str | None:
    """A modifier's label on a Mac ("⌘", "Right ⌘"); None for another key."""
    if part in MAC_SYMBOLS:
        return MAC_SYMBOLS[part]
    side, _, modifier = part.partition("_")
    if modifier not in MAC_SYMBOLS:
        return None
    symbol = MAC_SYMBOLS[modifier]
    if side == "right":
        #: a modifier key on the right of a Mac's keyboard: {key} is its symbol (⌘)
        return _tr("Right {key}").format(key=symbol)
    #: a modifier key on the left of a Mac's keyboard: {key} is its symbol (⌘)
    return _tr("Left {key}").format(key=symbol)


def _name(part: str) -> str:
    """One key's label, as most keyboards print it."""
    if os_words.on_a_mac() and (mac := _mac_name(part)) is not None:
        return mac
    names = {
        "ctrl": _tr("Ctrl"),
        "alt": _tr("Alt"),
        "shift": _tr("Shift"),
        #: the Windows logo key
        "win": _tr("Win"),
        "right_ctrl": _tr("Right Ctrl"),
        "left_ctrl": _tr("Left Ctrl"),
        "right_shift": _tr("Right Shift"),
        "left_shift": _tr("Left Shift"),
        "right_alt": _tr("Right Alt"),
        "left_alt": _tr("Left Alt"),
        #: the Windows logo key on the left
        "left_win": _tr("Win"),
        #: the Windows logo key on the right
        "right_win": _tr("Right Win"),
        #: the Insert key, as written on a keyboard
        "insert": _tr("Insert"),
        "delete": _tr("Delete"),
        "home": _tr("Home"),
        "end": _tr("End"),
        "page_up": _tr("Page Up"),
        "page_down": _tr("Page Down"),
        "left": _tr("Left arrow"),
        "right": _tr("Right arrow"),
        "up": _tr("Up arrow"),
        "down": _tr("Down arrow"),
        "space": _tr("Space"),
        "enter": _tr("Enter"),
        "tab": _tr("Tab"),
        "backspace": _tr("Backspace"),
        "escape": _tr("Esc"),
        #: the Pause key, as written on a keyboard
        "pause": _tr("Pause"),
        #: the Scroll Lock key, as written on a keyboard
        "scroll_lock": _tr("Scroll Lock"),
        "print_screen": _tr("Print Screen"),
        #: the key that opens a program's right-click menu
        "menu": _tr("Menu"),
    }
    return names.get(part) or part.upper()


def key_words(key: DictationKey | str) -> str:
    """The key as its keys are labelled: "Right Ctrl", "Ctrl + Alt + D"; on
    a Mac as its menus write it: "Right ⌘", "⌃⌘D"."""
    parsed = DictationKey.parse(key) if isinstance(key, str) else key
    if parsed is None:
        return str(key)
    if os_words.on_a_mac():
        held = "".join(
            symbol
            for name, symbol in MAC_SYMBOLS.items()
            if Modifier(name) in parsed.modifiers
        )
        return held + (_name(parsed.key) if parsed.key else "")
    return " + ".join(_name(part) for part in parsed.parts)


def refusal_words(refusal: Refusal | None) -> str:
    """Why a key can't be dictation's; None: a key Polyglotic can't hold."""
    texts = {
        Refusal.TYPES: os_words.pc_or_mac(
            _tr("That key types. Hold it with Ctrl, Alt or Win, or choose another."),
            _tr("That key types. Hold it with ⌘ or ⌃, or choose another."),
        ),
        Refusal.ESCAPE: _tr("Esc cancels dictation: choose another key."),
        Refusal.WINDOWS: os_words.pc_or_mac(
            _tr("Windows keeps that one for itself: choose another."),
            _tr("macOS keeps that one for itself: choose another."),
        ),
        Refusal.EVERY_PROGRAM: os_words.pc_or_mac(
            _tr("Every program uses that one (copy, paste…): add Alt or Shift to it."),
            _tr("Every app uses that one (copy, paste…): add ⌥ or ⇧ to it."),
        ),
        Refusal.MODIFIER: os_words.pc_or_mac(
            _tr(
                "On their own, only Right Ctrl or Ctrl + Win work: hold Ctrl, Alt or"
                " Shift with a key."
            ),
            _tr("On their own, only Right ⌘ or ⌃⌘ work: hold ⌘, ⌥ or ⇧ with a key."),
        ),
        Refusal.ALT: os_words.pc_or_mac(
            _tr(
                "Letting go of Alt opens a program's menu, and your words would go"
                " there: hold Ctrl with it too."
            ),
            _tr("⌥ with a key types a character of its own: hold ⌘ with it too."),
        ),
        Refusal.APP_HOTKEY: _tr(
            "That's one of Polyglotic's own hotkeys: choose another."
        ),
    }
    if refusal is None:
        return _tr("Polyglotic can't use that key: choose another.")
    return texts[refusal]


# -- reading what was pressed --------------------------------------------------------

_MODIFIER_KEYS = {
    Qt.Key.Key_Control: Modifier.CTRL,
    Qt.Key.Key_Shift: Modifier.SHIFT,
    Qt.Key.Key_Alt: Modifier.ALT,
    Qt.Key.Key_AltGr: Modifier.ALT,
    Qt.Key.Key_Meta: Modifier.WIN,  # the Windows key, on Windows
    Qt.Key.Key_Super_L: Modifier.WIN,
    Qt.Key.Key_Super_R: Modifier.WIN,
}
_RIGHT_SCAN_CODES = {0x11D, 0x36, 0x138, 0x15C}
"""Windows' scan codes (with the extended bit) of Right Ctrl, Right Shift,
Right Alt and Right Win; the left ones differ."""
_RIGHT_VKS = {0xA3, 0xA1, 0xA5, 0x5C}
_MAC_RIGHT_KEY_CODES = {0x36, 0x3C, 0x3D, 0x3E}
"""A Mac's key codes of Right Command, Right Shift, Right Option and Right
Control (Qt's `nativeVirtualKey` there); the left ones differ."""
_QT_KEYS: dict[Qt.Key, str] = {
    **{getattr(Qt.Key, f"Key_F{n}"): f"f{n}" for n in range(1, 25)},
    **{getattr(Qt.Key, f"Key_{c}"): c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{getattr(Qt.Key, f"Key_{d}"): d for d in "0123456789"},
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page_up",
    Qt.Key.Key_PageDown: "page_down",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backtab: "tab",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Escape: "escape",
    Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_ScrollLock: "scroll_lock",
    Qt.Key.Key_Print: "print_screen",
    Qt.Key.Key_Menu: "menu",
}
_KEYPAD_NAVIGATION = {
    "insert",
    "delete",
    "home",
    "end",
    "page_up",
    "page_down",
    "left",
    "right",
    "up",
    "down",
    "enter",
}
"""Keys the number pad shares (Num Lock off) - the same key to Windows."""


def _qt_key(event: QKeyEvent) -> Qt.Key | None:
    try:
        return Qt.Key(event.key())
    except ValueError:  # a key Qt has no name for
        return None


def modifier_of(event: QKeyEvent) -> str | None:
    """The modifier the event is for, by its side ("right_ctrl"); None if
    it's another key."""
    qt_key = _qt_key(event)
    modifier = None if qt_key is None else _MODIFIER_KEYS.get(qt_key)
    if modifier is None:
        return None
    if os_words.on_a_mac():
        right = event.nativeVirtualKey() in _MAC_RIGHT_KEY_CODES
    else:
        right = (
            event.nativeScanCode() in _RIGHT_SCAN_CODES
            or event.nativeVirtualKey() in _RIGHT_VKS
            or qt_key in (Qt.Key.Key_AltGr, Qt.Key.Key_Super_R)
        )
    return f"{'right' if right else 'left'}_{modifier.value}"


def key_of(event: QKeyEvent) -> str | None:
    """The (non-modifier) key the event is for, as `dictation_keys.KEYS`
    names it; None for one dictation can't be held on (a number pad digit,
    punctuation)."""
    vk = event.nativeVirtualKey()  # Windows': the key whatever the layout or Shift
    if not os_words.on_a_mac() and (0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39):
        return chr(vk).lower()  # a Mac's codes differ (Tab is 0x30): Qt's key there
    qt_key = _qt_key(event)
    name = None if qt_key is None else _QT_KEYS.get(qt_key)
    keypad = bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier)
    if name is None or keypad and name not in _KEYPAD_NAVIGATION:
        return None
    return name if name in KEYS else None


class KeyCapture:
    """What the learner pressed, from the keys going down and up."""

    def __init__(self) -> None:
        self._held: list[str] = []
        """The modifiers down now, by their side, in the order pressed."""
        self._peak: list[str] = []
        """The most modifiers held at once since the first went down."""

    def down(self, modifier: str | None, key: str | None) -> DictationKey | None:
        """A key went down - a `modifier` by its side, or a `key` (None for
        one dictation can't use, which `unusable` then says). The key
        pressed, once it's known."""
        if modifier is not None:
            if modifier not in self._held:
                self._held.append(modifier)
            if len(self._held) > len(self._peak):
                self._peak = list(self._held)
            return None
        self.unusable = key is None
        if key is None:
            return None
        held = frozenset(Modifier(m.split("_", 1)[1]) for m in self._held)
        return DictationKey(held, key)

    def up(self, modifier: str | None) -> DictationKey | None:
        """A key came up: if only modifiers were pressed, they're the key."""
        if modifier is None or modifier not in self._held:
            return None
        self._held.remove(modifier)
        if len(self._peak) == 1:
            return DictationKey(key=self._peak[0])
        sides = {m.split("_", 1)[1] for m in self._peak}
        if len(sides) < len(self._peak):  # both Ctrls: not one combination
            return None
        return DictationKey(frozenset(Modifier(s) for s in sides))

    unusable = False
    """The last key pressed was one dictation can't be held on."""


class KeyBox(QPushButton):
    """The key, as words; clicked, it listens for the next key or
    combination."""

    pressed_key = Signal(str)
    """What was pressed, as `DictationKey` keeps it - "" for a key
    dictation can't use."""
    listening_changed = Signal(bool)
    """It listens (the dictation key itself must then let keys through)."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.setObjectName("settings.dictation_key")
        self.setAccessibleName(_tr("Dictation key"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.key = key
        self._capture = KeyCapture()
        self.toggled.connect(self._listen)
        self._show()

    @property
    def listening(self) -> bool:
        return self.isChecked()

    def show_key(self, key: str) -> None:
        """The key as it's kept now."""
        self.key = key
        self._show()

    def stop(self) -> None:
        self.setChecked(False)

    def _listen(self, on: bool) -> None:
        self._capture = KeyCapture()
        if on:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
        self._show()
        self.listening_changed.emit(on)

    def _show(self) -> None:
        listening = self.isChecked()
        if listening:
            self.setText(_tr("Press a key or combination… (Esc: stop)"))
        else:
            self.setText(key_words(self.key))
        if (self.property("kind") == "primary") != listening:
            # the accent while it listens, so it's plain it's waiting for a key
            self.setProperty("kind", "primary" if listening else None)
            self.style().unpolish(self)
            self.style().polish(self)

    def _finish(self, key: DictationKey | None) -> None:
        self.stop()
        self.pressed_key.emit("" if key is None else str(key))

    def event(self, event: QEvent) -> bool:
        """Tab and Backtab too, which would otherwise move the focus."""
        if self.isChecked() and isinstance(event, QKeyEvent):
            if event.type() is QEvent.Type.KeyPress:
                self.keyPressEvent(event)
                return True
            if event.type() is QEvent.Type.KeyRelease:
                self.keyReleaseEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.isChecked():
            super().keyPressEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        modifier = modifier_of(event)
        key = None if modifier else key_of(event)
        if key == "escape" and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.stop()
            return
        found = self._capture.down(modifier, key)
        if found is not None or self._capture.unusable:
            self._finish(found)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self.isChecked():
            super().keyReleaseEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        found = self._capture.up(modifier_of(event))
        if found is not None:
            self._finish(found)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.stop()
        super().focusOutEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        """Its page or window gone: it stops listening, so dictation's own
        key comes back."""
        self.stop()
        super().hideEvent(event)
