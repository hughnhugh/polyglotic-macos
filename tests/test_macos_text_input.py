"""Dictation's words typed on a Mac (polyglotic-hq 429): the characters as
Unicode key events, with a stand-in for macOS's call - no test types for
real - and the record's wiring. Typing into TextEdit is proven on GitHub's
Mac (`tools.macos_full_screen_checks`)."""

from collections.abc import Sequence

import pytest

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.macos import text_input
from polyglotic_desktop.platform.macos.text_input import Piece, pieces, type_text


def test_each_character_is_its_own_utf16_units() -> None:
    assert pieces("hé") == [(0x68,), (0xE9,)]
    assert pieces("你好") == [(0x4F60,), (0x597D,)]
    assert pieces("😀") == [(0xD83D, 0xDE00)]  # one character, two units together


def test_a_line_break_or_tab_types_a_space() -> None:
    assert pieces("a\nb\tc\r") == pieces("a b c ")


def test_the_words_are_typed_in_order() -> None:
    sent: list[Piece] = []

    def post(typed: Sequence[Piece]) -> int:
        sent.extend(typed)
        return len(typed)

    assert type_text("你好 world", post)
    assert sent == pieces("你好 world")


def test_some_left_untyped_says_so() -> None:
    assert not type_text("hello", lambda typed: len(typed) - 1)
    assert not type_text("hello", lambda typed: 0)  # the permission not given


def test_nothing_to_type_needs_no_call() -> None:
    def post(_typed: Sequence[Piece]) -> int:
        raise AssertionError("nothing to send")

    assert type_text("", post)


def test_a_test_run_never_types_for_real(monkeypatch: pytest.MonkeyPatch) -> None:
    def real(_typed: Sequence[Piece]) -> int:
        raise AssertionError("typed into the machine's front app")

    monkeypatch.setattr(text_input, "_post", real)
    monkeypatch.setattr(text_input, "allowed", lambda ask=True: True)
    assert not type_text("hello")


def test_the_macs_record_types_and_reads_the_front_window() -> None:
    mac = os_adapters("darwin")
    assert mac.type_text is text_input.type_text
    assert mac.keyboard_window is text_input.keyboard_window


@pytest.mark.macos_only
def test_the_permission_and_the_front_window_are_read() -> None:
    """Asked without macOS's box (a test never shows it)."""
    assert isinstance(text_input.allowed(ask=False), bool)
    assert text_input.keyboard_window() >= 0


def test_the_macs_record_says_whether_it_may_type_and_where_to_allow_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """polyglotic-hq 438: the Accessibility permission read without asking,
    and System Settings opened at Privacy & Security > Accessibility."""
    assert isinstance(os_adapters("darwin").typing_permission, text_input.Permission)
    asked: list[bool] = []

    def allowed(ask: bool = True) -> bool:
        asked.append(ask)
        return True

    monkeypatch.setattr(text_input, "allowed", allowed)
    ran: list[list[str]] = []
    permission = text_input.Permission(ran.append)
    assert permission.allowed() is True and asked == [False]
    permission.open_settings()
    assert ran == [["/usr/bin/open", text_input.ACCESSIBILITY_SETTINGS]]
    assert "Privacy_Accessibility" in text_input.ACCESSIBILITY_SETTINGS
