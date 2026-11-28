"""Settings inventory from Polyglotic HQ project 844's AUDIT.md.

One row represents a learner-facing choice or group of controls. Dotted keys
identify independent choices within a stored mapping, and `window.*` keys are
saved by the caption-window store. Object-name globs cover repeated controls
such as the app rows and language pickers.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SettingEntry:
    id: str
    setting_keys: tuple[str, ...]
    object_names: tuple[str, ...]
    place_today: str
    proposed_place: str
    shortcut: bool = False


SETTINGS_MAP: tuple[SettingEntry, ...] = (
    SettingEntry("P1", ("preset",), ("presets.use.*",), "settings:presets", "everyday"),
    SettingEntry("P2", (), ("presets.new",), "settings:presets", "more:presets"),
    SettingEntry(
        "P3", ("preset_names",), ("presets.name",), "settings:presets", "more:presets"
    ),
    SettingEntry("P4", (), ("presets.changes",), "settings:presets", "more:presets"),
    SettingEntry(
        "P5",
        ("preset", "preset_values", "preset_names", "preset_parents", "own_presets"),
        ("presets.delete", "presets.reset"),
        "settings:presets",
        "more:presets",
        shortcut=True,
    ),
    SettingEntry(
        "P6",
        ("preset", "preset_values", "preset_names", "preset_parents", "own_presets"),
        (
            "settings.preset_line",
            "presets.new_name",
            "presets.line.save",
            "presets.line.save_as",
            "presets.line.discard",
            "presets.line.undo",
            "presets.line.named",
            "presets.line.cancel",
        ),
        "settings:preset-line",
        "everyday",
        shortcut=True,
    ),
    SettingEntry("L1", (), ("look.preview",), "settings:look", "more:look"),
    SettingEntry(
        "L2",
        (
            "original_color",
            "translation_color",
            "background_color",
            "opacity",
            "caption_contrast",
            "caption_vibrance",
            "caption_weight",
            "caption_edge",
            "caption_faces",
            "reading_size",
            "reading_colour",
        ),
        ("look.recommended.*",),
        "settings:look/recommended",
        "everyday",
    ),
    SettingEntry(
        "L3",
        ("original_color", "translation_color", "background_color", "opacity"),
        ("look.preset.*",),
        "settings:look/colours",
        "more:look",
    ),
    SettingEntry(
        "L4",
        ("caption_contrast", "caption_vibrance", "caption_weight", "caption_edge"),
        ("look.contrast", "look.vibrance", "look.thickness", "look.edge"),
        "settings:look",
        "more:look",
    ),
    SettingEntry(
        "L5",
        ("original_color",),
        ("look.original_colour", "look.original_colour.*"),
        "settings:look",
        "more:look",
    ),
    SettingEntry(
        "L6",
        ("translation_color",),
        ("look.translation_colour", "look.translation_colour.*"),
        "settings:look",
        "more:look",
    ),
    SettingEntry(
        "L7",
        ("background_color",),
        ("look.background_colour", "look.background_colour.*"),
        "settings:look",
        "more:look",
    ),
    SettingEntry("L8", ("opacity",), ("look.background",), "settings:look", "cog"),
    SettingEntry(
        "L9", ("show_original",), ("look.show_original",), "settings:look", "more:look"
    ),
    SettingEntry(
        "L10", ("show_language",), ("look.show_language",), "settings:look", "more:look"
    ),
    SettingEntry(
        "L11", ("show_source",), ("look.show_source",), "settings:look", "more:look"
    ),
    SettingEntry(
        "L12",
        ("window.text_size", "window.translation_size", "window.language_sizes"),
        (
            "settings.caption_size",
            "settings.caption_size_smaller",
            "settings.caption_size_bigger",
            "settings.translation_same",
            "settings.translation_size",
            "settings.translation_size_smaller",
            "settings.translation_size_bigger",
        ),
        "settings:look",
        "cog",
    ),
    SettingEntry(
        "L13", ("caption_faces",), ("look.face_*",), "settings:look", "more:look"
    ),
    SettingEntry(
        "L14",
        (
            "original_color",
            "translation_color",
            "background_color",
            "opacity",
            "caption_font",
            "caption_faces",
            "show_original",
            "show_language",
            "show_source",
            "caption_contrast",
            "caption_vibrance",
            "caption_weight",
            "caption_edge",
            "fade_after",
            "caption_arrival",
            "word_links",
            "link_detail",
            "link_line",
            "link_gap",
            "reading_lines",
            "reading_size",
            "reading_past",
            "respelling_past",
            "reading_system",
            "reading_colour",
            "reading_custom_color",
            "colour_links_by_word_class",
            "said_in_link_colours",
            "translation_in_link_colours",
            "quiet_view",
            "marks_in",
        ),
        ("look.reset",),
        "settings:look",
        "more:look",
        shortcut=True,
    ),
    SettingEntry(
        "W1",
        ("word_links", "quiet_view"),
        ("look.word_links",),
        "settings:links",
        "everyday",
    ),
    SettingEntry(
        "W2",
        ("link_line", "caption_lab.link_px"),
        ("look.link_line",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W3",
        ("link_gap",),
        ("look.link_gap",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W4",
        ("link_detail",),
        ("look.link_detail",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W5",
        ("colour_links_by_word_class",),
        ("look.colour_links_by_word_class",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W6",
        ("said_in_link_colours",),
        ("look.said_in_link_colours",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W7",
        ("translation_in_link_colours",),
        ("look.translation_in_link_colours",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W8",
        (),
        ("look.to_learning",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W9",
        ("quiet_view", "word_links", "reading_lines"),
        ("look.quiet",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W10",
        ("quiet_words",),
        (
            "look.quiet_curriculum",
            "look.quiet_edge",
            "look.quiet_load",
            "look.quiet_saved",
        ),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W11",
        ("curriculum_size",),
        ("look.curriculum_size",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "W12",
        ("marks_in",),
        ("look.marks_in",),
        "settings:links",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R1",
        ("reading_lines.zh",),
        ("look.reading_zh",),
        "settings:readings",
        "everyday",
    ),
    SettingEntry(
        "R2",
        ("reading_system",),
        ("look.reading_system",),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R3",
        ("reading_lines.yue",),
        ("look.reading_yue",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R4",
        ("japanese_reading",),
        ("look.japanese_reading",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R5",
        ("reading_lines.ru",),
        ("look.reading_ru",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R6",
        ("reading_lines.ko",),
        ("look.reading_ko",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R7",
        ("reading_lines.hi",),
        ("look.reading_hi",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R8",
        ("reading_past",),
        ("look.reading_past",),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R9",
        ("reading_lines.en",),
        ("look.reading_en",),
        "settings:readings",
        "everyday/more:word-links-and-readings",
    ),
    SettingEntry(
        "R10",
        ("respelling_past",),
        ("look.respelling_past",),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R11",
        ("reading_size",),
        ("look.reading_size",),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R12",
        ("reading_colour",),
        ("look.reading_colour",),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "R13",
        ("reading_custom_color", "reading_colour"),
        ("look.reading_custom", "look.reading_custom.*"),
        "settings:readings",
        "more:word-links-and-readings",
    ),
    SettingEntry(
        "T1", ("caption_mode_chosen",), ("timing.mode",), "settings:timing", "everyday"
    ),
    SettingEntry(
        "T2",
        ("steady_newest_word",),
        ("timing.newest_word",),
        "settings:timing",
        "more:timing",
    ),
    SettingEntry("T3", ("steady_cards",), ("timing.cards",), "settings:timing", "lab"),
    SettingEntry(
        "T4", ("steady_two_zones",), ("timing.two_zones",), "settings:timing", "lab"
    ),
    SettingEntry(
        "T5", ("caption_path",), ("timing.path",), "settings:timing", "more:timing"
    ),
    SettingEntry(
        "T6",
        ("translation_after",),
        ("timing.translation_after",),
        "settings:timing",
        "more:timing",
    ),
    SettingEntry(
        "T7",
        ("steady_words_ahead",),
        ("timing.words_ahead",),
        "settings:timing",
        "more:timing",
    ),
    SettingEntry(
        "T8",
        ("live_update_interval",),
        ("timing.live_interval",),
        "settings:timing",
        "lab",
    ),
    SettingEntry(
        "T9", ("max_wait_for_text",), ("timing.max_wait",), "settings:timing", "lab"
    ),
    SettingEntry(
        "T10",
        ("text_settles_after",),
        ("timing.settle_after",),
        "settings:timing",
        "lab",
    ),
    SettingEntry(
        "B1", ("caption_arrival",), ("look.arrival",), "settings:timing", "more:timing"
    ),
    SettingEntry(
        "B2", ("fade_after",), ("look.fade_after",), "settings:timing", "more:timing"
    ),
    SettingEntry(
        "B3",
        ("pause_hidden_after",),
        ("look.pause_hidden_after",),
        "settings:timing",
        "more:listening",
    ),
    SettingEntry(
        "B4",
        ("show_hidden_on_speech",),
        ("look.show_on_speech",),
        "settings:timing",
        "more:listening",
    ),
    SettingEntry(
        "S1",
        ("speaker_device",),
        ("sound.speakers",),
        "settings:speech/sound",
        "more:listening",
    ),
    SettingEntry(
        "S2",
        ("my_speech", "window.show_mic"),
        ("sound.my_speech",),
        "settings:speech/sound",
        "home",
    ),
    SettingEntry(
        "S3",
        ("mic_device",),
        ("sound.mics", "sound.level"),
        "settings:speech/sound",
        "more:listening",
    ),
    SettingEntry(
        "S4",
        ("spoken_language", "window.spoken_language"),
        ("languages.spoken_button",),
        "settings:speech",
        "everyday",
    ),
    SettingEntry("S5", ("lyrics",), ("languages.lyrics",), "settings:speech", "bar"),
    SettingEntry(
        "S6",
        ("mandarin_script",),
        ("languages.mandarin_script",),
        "settings:speech",
        "more:listening",
    ),
    SettingEntry(
        "S7",
        ("second_languages", "no_second_language", "preset_second_languages"),
        ("languages.second.*",),
        "settings:speech",
        "bar",
    ),
    SettingEntry(
        "S8",
        ("spelling_hints",),
        ("languages.spelling_hints",),
        "settings:speech",
        "more:listening",
    ),
    SettingEntry(
        "D1",
        ("type_theirs",),
        ("hotkeys.respeak",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D2",
        ("type_what",),
        ("hotkeys.respeak_what",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D3",
        ("respeak_key",),
        ("hotkeys.respeak_way",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D4",
        ("respeak_key",),
        ("hotkeys.respeak.key",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D5",
        ("dictation",),
        ("settings.dictation",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D6",
        ("dictation_key",),
        ("settings.dictation_key", "settings.dictation_key_reset"),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D7",
        ("dictation_language",),
        ("settings.dictation_language",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D8",
        ("dictation_australian",),
        ("settings.dictation_australian",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "D9",
        (),
        ("settings.typing_settings",),
        "settings:dictation",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H1",
        ("hotkeys.lock", "hotkey_scopes.lock"),
        (
            "hotkeys.lock.key",
            "hotkeys.lock.clear",
            "hotkeys.lock.scope",
            "hotkeys.lock.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H2",
        ("hotkeys.pause", "hotkey_scopes.pause"),
        (
            "hotkeys.pause.key",
            "hotkeys.pause.clear",
            "hotkeys.pause.scope",
            "hotkeys.pause.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H3",
        ("hotkeys.hide", "hotkey_scopes.hide"),
        (
            "hotkeys.hide.key",
            "hotkeys.hide.clear",
            "hotkeys.hide.scope",
            "hotkeys.hide.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H4",
        ("hotkeys.live", "hotkey_scopes.live"),
        (
            "hotkeys.live.key",
            "hotkeys.live.clear",
            "hotkeys.live.scope",
            "hotkeys.live.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H5",
        ("hotkeys.copy", "hotkey_scopes.copy"),
        (
            "hotkeys.copy.key",
            "hotkeys.copy.clear",
            "hotkeys.copy.scope",
            "hotkeys.copy.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H6",
        ("hotkeys.preset", "hotkey_scopes.preset"),
        (
            "hotkeys.preset.key",
            "hotkeys.preset.clear",
            "hotkeys.preset.scope",
            "hotkeys.preset.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H7",
        ("hotkeys.bigger", "hotkey_scopes.bigger"),
        (
            "hotkeys.bigger.key",
            "hotkeys.bigger.clear",
            "hotkeys.bigger.scope",
            "hotkeys.bigger.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H8",
        ("hotkeys.smaller", "hotkey_scopes.smaller"),
        (
            "hotkeys.smaller.key",
            "hotkeys.smaller.clear",
            "hotkeys.smaller.scope",
            "hotkeys.smaller.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H9",
        ("hotkeys.bar", "hotkey_scopes.bar"),
        (
            "hotkeys.bar.key",
            "hotkeys.bar.clear",
            "hotkeys.bar.scope",
            "hotkeys.bar.alt_*",
        ),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H10",
        ("hotkeys", "hotkey_scopes"),
        ("hotkeys.reset",),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "H11",
        (),
        ("hotkeys.dictate", "hotkeys.dictate.change"),
        "settings:hotkeys",
        "gone",
    ),
    SettingEntry(
        "H12",
        ("type_theirs", "type_what", "respeak_key"),
        (
            "settings.hotkeys.respeak",
            "settings.hotkeys.respeak_what",
            "settings.hotkeys.respeak_way",
            "settings.hotkeys.respeak.key",
        ),
        "settings:hotkeys",
        "gone",
    ),
    SettingEntry(
        "H13",
        (),
        ("settings.window_keys",),
        "settings:hotkeys",
        "more:keys-and-dictation",
    ),
    SettingEntry(
        "A0",
        ("interface_language",),
        (
            "settings.language_picker",
            "settings.language_restart",
            "settings.language_defer",
            "settings.language_wrong",
        ),
        "settings:header",
        "everyday",
    ),
    SettingEntry(
        "A1",
        ("interface_text_size",),
        ("settings.text_size",),
        "settings:app",
        "everyday",
    ),
    SettingEntry("A2", ("theme",), ("settings.theme",), "settings:app", "more:app"),
    SettingEntry(
        "A3", ("window_theme",), ("settings.window_theme",), "settings:app", "everyday"
    ),
    SettingEntry(
        "A4",
        ("transcript_length",),
        ("settings.transcript_length",),
        "settings:app",
        "more:app",
    ),
    SettingEntry(
        "A5",
        ("transcript_ask_at_quit",),
        ("settings.transcript_ask",),
        "settings:app",
        "more:app",
    ),
    SettingEntry(
        "A6",
        (),
        (
            "settings.check_updates",
            "settings.restart_update",
            "settings.open_app_folder",
        ),
        "settings:app",
        "more:app",
    ),
    SettingEntry(
        "A7",
        ("start_at_sign_in",),
        ("settings.start_at_sign_in",),
        "settings:app",
        "more:app",
    ),
    SettingEntry(
        "A8", (), ("settings.notices", "settings.tell_us"), "settings:app", "more:app"
    ),
    SettingEntry(
        "X1", ("caption_lab.new_for",), ("lab.new_for",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X2", ("caption_lab.new_fade",), ("lab.new_fade",), "settings:lab", "lab"
    ),
    SettingEntry("X3", ("caption_lab.older",), ("lab.older",), "settings:lab", "lab"),
    SettingEntry(
        "X4", ("caption_lab.older_steps",), ("lab.older_steps",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X5", ("caption_lab.unfinished",), ("lab.unfinished",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X6", ("caption_lab.loading",), ("lab.loading",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X7", ("caption_lab.link_px",), ("lab.link_px",), "settings:lab", "tunable"
    ),
    SettingEntry(
        "X8", ("caption_lab.row_gap",), ("lab.row_gap",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X9", ("caption_lab.caption_gap",), ("lab.caption_gap",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X10", ("caption_lab.arrival_gap",), ("lab.arrival_gap",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X11", ("caption_lab.line_gap",), ("lab.line_gap",), "settings:lab", "lab"
    ),
    SettingEntry("X12", ("caption_lab",), ("lab.reset",), "settings:lab", "lab"),
    SettingEntry(
        "X13", ("caption_lab.own_right",), ("lab.own_right",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X14", ("caption_lab.own_tint",), ("lab.own_tint",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X15", ("caption_lab.own_bar",), ("lab.own_bar",), "settings:lab", "lab"
    ),
    SettingEntry(
        "X16", ("caption_lab.own_label",), ("lab.own_label",), "settings:lab", "lab"
    ),
    SettingEntry("X17", ("caption_lab.fill",), ("lab.fill",), "settings:lab", "lab"),
    SettingEntry(
        "X18",
        ("caption_lab.join", "caption_lab.fill"),
        ("lab.join",),
        "settings:lab",
        "lab",
    ),
    SettingEntry("X19", ("caption_lab.flow",), ("lab.flow",), "settings:lab", "lab"),
    SettingEntry(
        "X20",
        ("caption_lab.run_on", "caption_lab.flow", "caption_lab.fill"),
        ("lab.run_on",),
        "settings:lab",
        "lab",
    ),
    SettingEntry(
        "X21",
        ("caption_lab.aligned", "caption_lab.flow"),
        ("lab.aligned",),
        "settings:lab",
        "lab",
    ),
    SettingEntry(
        "X22",
        ("caption_lab.placing", "caption_lab.flow"),
        ("lab.placing",),
        "settings:lab",
        "lab",
    ),
    SettingEntry(
        "X23",
        ("caption_lab.load",),
        ("lab.load", "lab.to_learning"),
        "settings:lab",
        "lab",
    ),
    SettingEntry(
        "X24",
        ("caption_lab.load_colours",),
        ("lab.load_colours",),
        "settings:lab",
        "lab",
    ),
    SettingEntry(
        "C1",
        ("source_colors", "source_names"),
        ("picker.colour.[0-9]*", "picker.name.[0-9]*", "picker.rename.[0-9]*"),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C2",
        ("window.translate_into", "preset_languages"),
        ("picker.language.[0-9]*",),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C3", ("window.show_mic",), ("picker.mic.[0-9]*",), "home/captions", "home"
    ),
    SettingEntry(
        "C4",
        ("apps", "whole_system", "everything_else"),
        ("picker.captions.[0-9]*", "picker.transcript.[0-9]*", "picker.stop.[0-9]*"),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C5",
        ("apps", "whole_system", "everything_else"),
        ("picker.everything_else",),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C6",
        ("apps", "whole_system", "everything_else"),
        ("picker.refresh", "picker.add.*", "picker.start", "picker.apps_again"),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C7",
        ("whole_system",),
        ("home.pick_apps", "home.all_audio"),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C8",
        (),
        ("picker.sample_button", "picker.sample_next"),
        "home/captions",
        "home",
    ),
    SettingEntry(
        "C9",
        ("source_colors", "source_names"),
        ("picker.colour.you", "picker.name.you", "picker.rename.you"),
        "home/captions",
        "home",
    ),
    SettingEntry("C10", (), ("picker.my_speech",), "home/captions", "gone"),
    SettingEntry(
        "C11",
        ("speaker_device", "my_speech", "window.show_mic", "mic_device"),
        ("sound.speakers", "sound.my_speech", "sound.mics", "sound.level"),
        "home/sound",
        "home/more:listening",
    ),
    SettingEntry(
        "C12",
        ("locked", "window.geometry", "window.joined"),
        ("home.lock_all", "home.hide_all", "home.join", "home.reset_positions"),
        "home/windows",
        "home",
    ),
    SettingEntry(
        "home:level-prompt",
        ("level_line_dismissed",),
        ("home.level.not_now",),
        "home/windows",
        "home",
    ),
    SettingEntry(
        "G1",
        ("window.text_size", "window.language_sizes"),
        (
            "settings_popover.text_size_slider",
            "settings_popover.caption_window.smaller",
            "settings_popover.caption_window.bigger",
        ),
        "cog",
        "cog",
    ),
    SettingEntry(
        "G2",
        ("window.translation_size", "window.language_sizes"),
        (
            "settings_popover.translation_size_slider",
            "settings_popover.caption_window.translation_smaller",
            "settings_popover.caption_window.translation_bigger",
            "settings_popover.caption_window.translation_same",
        ),
        "cog",
        "cog",
    ),
    SettingEntry(
        "G3", ("window.opacity",), ("settings_popover.opacity_slider",), "cog", "cog"
    ),
    SettingEntry(
        "G4",
        ("apps", "whole_system", "everything_else", "window.joined"),
        (
            "settings_popover.transcript",
            "settings_popover.join",
            "settings_popover.stop",
            "settings_popover.all_settings",
        ),
        "cog",
        "cog",
        shortcut=True,
    ),
    SettingEntry(
        "G5",
        ("apps", "whole_system", "everything_else"),
        (
            "settings_popover.app",
            "settings_popover.app_button",
            "settings_popover.apps",
            "settings_popover.bar_timing",
            "settings_popover.bar_languages",
            "settings_popover.bar_presets",
        ),
        "cog",
        "bar",
        shortcut=True,
    ),
    SettingEntry(
        "G6",
        ("window.show_pace",),
        ("settings_popover.show_pace",),
        "cog",
        "cog",
    ),
    SettingEntry(
        "G7",
        ("long_lines",),
        ("settings_popover.long_lines_button", "settings_popover.long_lines_choices"),
        "cog",
        "cog",
    ),
    SettingEntry(
        "G8",
        ("window.show_caption_info",),
        ("settings_popover.show_caption_info",),
        "cog",
        "cog",
    ),
    # The bar's in-context controls, listed together after the audit tables.
    SettingEntry(
        "bar:preset",
        ("preset",),
        ("presets.preset.*",),
        "bar:preset",
        "bar",
        shortcut=True,
    ),
    SettingEntry(
        "bar:timing",
        ("caption_mode_chosen", "caption_path"),
        ("timings.timing.*",),
        "bar:timing",
        "bar",
        shortcut=True,
    ),
    SettingEntry(
        "bar:language",
        ("window.spoken_language", "window.translate_into", "preset_languages"),
        (
            "settings_popover.language_button",
            "settings_popover.languages",
            "settings_popover.spoken_button",
            "settings_popover.spoken_choices",
            "settings_popover.spoken_fallback",
        ),
        "bar:language",
        "bar",
        shortcut=True,
    ),
    SettingEntry(
        "bar:lyrics",
        ("lyrics",),
        ("settings_popover.lyrics", "settings_popover.caption_window.lyrics"),
        "bar:language",
        "bar",
    ),
    SettingEntry(
        "bar:second",
        ("second_languages", "no_second_language", "preset_second_languages"),
        ("settings_popover.second_button", "settings_popover.second_choices"),
        "bar:language",
        "bar",
    ),
    SettingEntry(
        "bar:window-defaults",
        ("window.start_like_this", "window.last", "window.set_up"),
        ("settings_popover.start_like_this", "settings_popover.ask_set_up"),
        "bar:language",
        "bar",
    ),
    SettingEntry(
        "bar:show",
        ("show_original", "show_translation"),
        ("presets.show.*",),
        "bar:preset",
        "bar",
    ),
    SettingEntry(
        "bar:mic", ("window.show_mic",), ("caption_window.band.mic",), "bar:mic", "bar"
    ),
    # The audit lists an Add: My speech menu item; this branch has a separate mic button.
    SettingEntry("bar:add-mic", (), (), "unavailable", "bar"),
)


@dataclass(frozen=True)
class KnownDuplicate:
    unit: str
    rows: tuple[str, ...]
    writes: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()


# AUDIT.md's eleven findings include repeated UI as well as repeated writes.
# Keep the exact expected keys and locations independent of the inventory.
KNOWN_DUPLICATES = {
    1: KnownDuplicate(
        "U4",
        ("S2", "C3", "C10", "C11", "bar:mic", "bar:add-mic"),
        (
            (("my_speech",), ("home/sound", "settings:speech/sound")),
            (
                ("window.show_mic",),
                (
                    "bar:mic",
                    "home/captions",
                    "home/sound",
                    "settings:speech/sound",
                ),
            ),
        ),
    ),
    2: KnownDuplicate(
        "U4",
        ("S1", "S3", "C11"),
        ((("speaker_device", "mic_device"), ("home/sound", "settings:speech/sound")),),
    ),
    # The key editors H7/H8 change bindings. The actions change the window.
    3: KnownDuplicate(
        "U3",
        ("L12", "G1", "G2", "H7", "H8"),
        (
            (
                (
                    "window.text_size",
                    "window.translation_size",
                    "window.language_sizes",
                ),
                ("cog", "settings:look"),
            ),
        ),
    ),
    # The cog changes one window's opacity; Look changes the app default.
    4: KnownDuplicate("U3", ("L8", "G3")),
    # H11 displays the dictation key and opens Dictation to change it.
    5: KnownDuplicate(
        "U3",
        ("D1", "D2", "D3", "D4", "D6", "H11", "H12"),
        (
            (
                ("type_theirs", "type_what", "respeak_key"),
                ("settings:dictation", "settings:hotkeys"),
            ),
        ),
    ),
    6: KnownDuplicate(
        "U3",
        ("S5", "S7", "bar:lyrics", "bar:second"),
        (
            (
                (
                    "lyrics",
                    "second_languages",
                    "no_second_language",
                    "preset_second_languages",
                ),
                ("bar:language", "settings:speech"),
            ),
        ),
    ),
    7: KnownDuplicate(
        "U3",
        ("W2", "X7"),
        ((("caption_lab.link_px",), ("settings:lab", "settings:links")),),
    ),
    # Two settings share similar labels on one page.
    8: KnownDuplicate("U3", ("R8", "R10")),
    # Applying a look or colour set changes values also available individually.
    9: KnownDuplicate(
        "U3",
        ("P1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L13", "R11", "R12"),
        (
            (
                ("original_color", "translation_color", "background_color", "opacity"),
                ("settings:look", "settings:look/colours", "settings:look/recommended"),
            ),
            (
                (
                    "caption_contrast",
                    "caption_vibrance",
                    "caption_weight",
                    "caption_edge",
                    "caption_faces",
                ),
                ("settings:look", "settings:look/recommended"),
            ),
            (
                ("reading_size", "reading_colour"),
                ("settings:look/recommended", "settings:readings"),
            ),
        ),
    ),
    # The ten sections share one header widget.
    10: KnownDuplicate("U2", ("A0",)),
    11: KnownDuplicate(
        "U3",
        ("L9", "bar:show"),
        ((("show_original",), ("bar:preset", "settings:look")),),
    ),
}


def expected_duplicates() -> dict[str, frozenset[str]]:
    return {
        key: frozenset(places)
        for duplicate in KNOWN_DUPLICATES.values()
        for keys, places in duplicate.writes
        for key in keys
    }


def duplicates(
    entries: Iterable[SettingEntry] = SETTINGS_MAP,
) -> dict[str, frozenset[str]]:
    """Find keys with more than one home, omitting in-context shortcuts."""
    places: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        if not entry.shortcut:
            for key in entry.setting_keys:
                places[key].add(entry.place_today)
    return {key: frozenset(found) for key, found in places.items() if len(found) > 1}


def summary(entries: Iterable[SettingEntry] = SETTINGS_MAP) -> str:
    """Count Settings rows separately from their Home, cog and bar counterparts."""
    entries = tuple(entries)
    current = Counter(entry.place_today for entry in entries)
    settings = tuple(
        entry for entry in entries if entry.place_today.startswith("settings:")
    )
    proposed = Counter(entry.proposed_place for entry in settings)
    everyday = sum(
        row.proposed_place == "everyday" and row.id != "P6" for row in settings
    )
    more = sum(count for place, count in proposed.items() if "more:" in place)
    leaving = sum(
        proposed[place] for place in ("cog", "bar", "home", "gone", "tunable")
    )
    today = ", ".join(f"{place} {count}" for place, count in sorted(current.items()))
    plan = ", ".join(f"{place} {count}" for place, count in sorted(proposed.items()))
    return (
        f"{len(settings)} Settings rows today; {everyday} Everyday choices, "
        f"{more} More, {proposed['lab']} Lab, {leaving} leaving.\n"
        f"Today: {today}\nProposed Settings rows: {plan}"
    )
