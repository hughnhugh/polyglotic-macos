"""The whole learning view in one click: a caption window's word links
button turns on word links with their lines, linked words in their link's
colour on both sides, pinyin in its word link's colour - and, for a
Chinese window, pinyin itself; off again, back exactly (the user,
2026-11-17, polyglotic-hq 446: "the word linkage caption window nav bar
option should default switch on with arrows ... also showing pinyin
colour, translation text colour matching and caption colour matching ...
essentially this should be the one click default")."""

from dataclasses import replace

from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.display import ReadingColour, WordLinks
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView, learning_view

PLAIN = CaptionLook(
    said_in_link_colours=False,
    translation_in_link_colours=False,
    reading_colour=ReadingColour.SAME,
)
"""A learner who turned each of them off before."""


def _whole(look: CaptionLook) -> tuple[object, ...]:
    return (
        look.word_links,
        look.said_in_link_colours,
        look.translation_in_link_colours,
        look.reading_colour,
        look.reading_lines,
    )


def test_one_click_turns_on_the_whole_learning_view() -> None:
    view = LookView(PLAIN)
    view.set_links_shown(True, ("zh",))
    assert _whole(view.value) == (
        WordLinks.ARROWS, True, True, ReadingColour.LINK, ("zh",),
    )  # fmt: skip


def test_off_again_is_back_exactly() -> None:
    view = LookView(replace(PLAIN, reading_lines=("ja",)))
    view.set_links_shown(True, ("zh",))
    view.set_links_shown(False)
    assert view.value == replace(PLAIN, reading_lines=("ja",))


def test_a_window_without_chinese_adds_no_pinyin() -> None:
    view = LookView(PLAIN)
    view.set_links_shown(True, ())
    assert view.value.reading_lines == ()
    pinyin = LookView(replace(PLAIN, reading_lines=("zh",)))
    pinyin.set_links_shown(True, ())
    pinyin.set_links_shown(False)
    assert pinyin.value.reading_lines == ("zh",)  # the learner's, kept


def test_a_pinyin_colour_the_learner_picked_stays_theirs() -> None:
    picked = replace(PLAIN, reading_colour=ReadingColour.CUSTOM)
    on = learning_view(picked, True, WordLinks.ARROWS)
    assert on.reading_colour is ReadingColour.CUSTOM


def test_the_way_last_chosen_in_look_is_kept() -> None:
    view = LookView(PLAIN)
    view.set_word_links(WordLinks.COLOURS)  # chosen in Settings: no lines
    view.set_links_shown(False)
    view.set_links_shown(True)
    assert view.value.word_links is WordLinks.COLOURS
    assert view.value.said_in_link_colours  # and the rest of the view


def test_a_saved_underline_from_the_old_button_gets_the_lines() -> None:
    """Before 446 the button itself saved Underline (Colours): after an
    update, a tester's next click shows the lines; a way chosen in this
    run, or a saved On hover, is kept."""
    view = LookView(replace(PLAIN, word_links=WordLinks.COLOURS))
    view.set_links_shown(False)
    view.set_links_shown(True)
    assert view.value.word_links is WordLinks.ARROWS
    hover = LookView(replace(PLAIN, word_links=WordLinks.HOVER))
    hover.set_links_shown(False)
    hover.set_links_shown(True)
    assert hover.value.word_links is WordLinks.HOVER


def test_turned_on_in_settings_off_turns_only_the_links_off() -> None:
    """Not turned on by the button (or before a restart): nothing to go
    back to, so the rest stays as it is."""
    on = replace(PLAIN, word_links=WordLinks.ARROWS, said_in_link_colours=True)
    view = LookView(on)
    view.set_links_shown(False)
    assert view.value == replace(on, word_links=WordLinks.OFF)


def test_a_chinese_window_asks_for_pinyin(qapp: QApplication) -> None:
    asked: list[tuple[bool, tuple[str, ...]]] = []
    # furigana comes on by its own switch only, not with the links (511)
    for spoken, readings in (("zh", ("zh",)), ("ja", ())):
        window = window_of(qapp, captions=0, spoken_language=spoken)
        try:
            window.links_wanted.connect(lambda on, found: asked.append((on, found)))
            window.controls["links"].trigger()  # the dropdown's (556)
            assert asked[-1] == (True, readings)
        finally:
            window.close()


def test_a_window_hearing_chinese_with_detect_asks_for_pinyin(
    qapp: QApplication,
) -> None:
    """The recorded conversation is Chinese, heard by Detect."""
    window = window_of(qapp, translate_into="en")
    try:
        assert window.choices.spoken_language is None
        assert window.readings() == ("zh",)
    finally:
        window.close()


def test_a_new_install_shows_it_all_once_links_are_on() -> None:
    look = CaptionLook()
    assert look.word_links is WordLinks.OFF  # off until the learner clicks
    assert look.said_in_link_colours and look.translation_in_link_colours
    assert look.reading_colour is ReadingColour.GREY  # links' colours where linked
    view = LookView(look)
    view.set_links_shown(True, ("zh",))
    assert view.value.reading_colour is ReadingColour.GREY  # kept (532)
