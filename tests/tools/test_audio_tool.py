"""The audio tool (`tools.dictionaries.audio`; polyglotic-hq 405, 418,
424): the voice for each language that passed the listening check, the
credit French's voice needs, Chinese's model pinned and its watermark said,
and a long run that picks up where it was stopped."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from tools.dictionaries import audio

from polyglotic_desktop.adapters.audio_file import SqliteAudio
from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.ports.dictionary import EntryRecord

RATE = 24000
WORDS = ("casa", "perro", "gato", "agua", "sol", "luna", "mar")


def tone(word: str) -> tuple[Any, int]:
    """A "voice": a quarter second of tone, its pitch the word's length."""
    import numpy

    t = numpy.arange(RATE // 4) / RATE
    sound = (0.4 * numpy.sin(2 * math.pi * 100 * len(word) * t)).astype("float32")
    return sound, RATE


def pack(folder: Path) -> Path:
    """A pack whose words are ranked, commonest first."""
    folder.mkdir(parents=True, exist_ok=True)
    records = [
        EntryRecord(f"wiktes:{n}", word, "", "", ("x",), n, ())
        for n, word in enumerate(WORDS, start=1)
    ]
    path = folder / "wiktes.sqlite"
    write_dictionary(
        path,
        {"dictionary": "wiktes", "language": "es", "meanings_language": "en"},
        records,
        {r.headword: [r.entry_id] for r in records},
    )
    return path


class Stopped(Exception):
    """The run stopped part way (the PC paused, a reboot)."""


def test_each_language_that_passed_has_its_voice_and_licence() -> None:
    """405's voices: the four that passed (Spanish, Italian, Portuguese,
    English), French for the user's ear, Japanese through misaki for
    comparison; Chinese is Chatterbox's (424)."""
    voices = {code: (s.voice, s.tag, s.g2p) for code, s in audio.VOICES.items()}
    assert voices == {
        "en": ("af_heart", "en-US", "espeak-ng"),
        "es": ("ef_dora", "es-ES", "espeak-ng"),
        "it": ("if_sara", "it-IT", "espeak-ng"),
        "pt": ("pf_dora", "pt-BR", "espeak-ng"),
        "fr": ("ff_siwis", "fr-FR", "espeak-ng"),
        "ja": ("jf_alpha", "ja-JP", "misaki-ja"),
        "zh": ("built-in voice", "zh-CN", ""),
    }
    for spoken in audio.VOICES.values():
        licence = "MIT" if spoken.model == audio.CHATTERBOX else "Apache-2.0"
        assert licence in spoken.licence_text and spoken.voice in spoken.said_by
    # CC BY 4.0: the authors, the licence, and that it trained the voice
    french = audio.VOICES["fr"].licence_text
    assert "SIWIS" in french and "Yamagishi" in french and "CC BY 4.0" in french
    assert audio.VOICES["ja"].said_by.endswith("(misaki G2P)")
    for no_longer in ("espeak-ng", "misaki-zh"):
        with pytest.raises(ValueError):
            audio.misaki(no_longer)


def test_chinese_is_said_by_the_pinned_chatterbox_pack_and_says_so() -> None:
    """417: Chatterbox's zh-cmn pack (MIT), archived since August 2026 - its
    code and weights pinned; each word followed by "。" as 417 ran it; the
    watermark it adds named in the file. Kokoro's files say as before."""
    chinese = audio.VOICES["zh"]
    assert chinese.model == audio.CHATTERBOX and chinese.stop == "。"
    assert chinese.said_by == "Chatterbox Multilingual zh-cmn, built-in voice"
    licence = chinese.licence_text
    assert (
        audio.CHATTERBOX_CODE[:8] in licence and audio.CHATTERBOX_ZH[1][:8] in licence
    )
    assert "synthetic" in licence and "nobody's cloned" in licence
    said = audio.info("cedict", "zh", chinese)
    assert said["said_as"] == "each word followed by 。"
    assert "Perth watermark" in said["watermark"]
    assert set(audio.info("wiktes", "es", audio.VOICES["es"])) == {
        "dictionary",
        "language",
        "voice_language",
        "voice",
        "licence",
        "made",
    }
    assert audio.CHATTERBOX_FIXED == ("tokenizer._mel_filters", "tokenizer.window")


def test_a_built_in_dictionarys_words_are_said_though_it_names_no_language(
    tmp_path: Path,
) -> None:
    """CC-CEDICT's file (built into the app, not a pack) names no language:
    the voice's says it (424: the first Chinese run stopped on it)."""
    tmp_path.mkdir(exist_ok=True)
    records = [
        EntryRecord(f"cedict:{n}", word, "", "", ("x",), n, ())
        for n, word in enumerate(("的", "我们", "中国"), start=1)
    ]
    built_in = tmp_path / "cedict.sqlite"
    write_dictionary(
        built_in,
        {"dictionary": "cedict"},
        records,
        {r.headword: [r.entry_id] for r in records},
    )
    stats = audio.build(built_in, tone, audio.VOICES["zh"], 100, tmp_path / "out")
    made = SqliteAudio(tmp_path / "out" / "cedict.audio")
    assert stats["words"] == 3 and made.info["language"] == "zh"
    assert made.info["voice_language"] == "zh-CN" and made.clip("我们") is not None
    made.close()


def test_a_run_stopped_part_way_picks_up_where_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """405: a pause lost an Italian run at 9,000 of 10,000 words. Each
    `SAVE_EVERY` words are kept; the next run says only the rest, and the
    file is the same as one run's."""
    monkeypatch.setattr(audio, "SAVE_EVERY", 2)
    source = pack(tmp_path / "packs")
    spoken = audio.VOICES["es"]
    said: list[str] = []

    def stops_after_five(word: str) -> tuple[Any, int]:
        if len(said) == 5:
            raise Stopped
        said.append(word)
        return tone(word)

    out = tmp_path / "out"
    with pytest.raises(Stopped):
        audio.build(source, stops_after_five, spoken, 100, out)
    partial = out / "wiktes.audio.partial"
    assert partial.is_file() and not (out / "wiktes.audio").exists()

    again: list[str] = []

    def rest(word: str) -> tuple[Any, int]:
        again.append(word)
        return tone(word)

    stats = audio.build(source, rest, spoken, 100, out)
    assert again == list(WORDS[4:])  # four were saved; the fifth wasn't
    assert stats["words"] == len(WORDS) and not partial.exists()
    resumed = SqliteAudio(out / "wiktes.audio")
    whole = tmp_path / "whole"
    audio.build(source, tone, spoken, 100, whole)
    once = SqliteAudio(whole / "wiktes.audio")
    assert resumed.info == once.info
    assert resumed.info["voice"] == "Kokoro-82M v1.0, ef_dora (espeak-ng G2P)"
    for word in WORDS:
        assert resumed.clip(word) == once.clip(word) is not None
    resumed.close()
    once.close()


def test_a_saved_run_by_another_voice_is_never_mixed_in(tmp_path: Path) -> None:
    source = pack(tmp_path / "packs")
    out = tmp_path / "out"
    out.mkdir()
    audio.Partial(out / "wiktes.audio.partial", "someone else").close()
    with pytest.raises(SystemExit, match="someone else"):
        audio.build(source, tone, audio.VOICES["es"], 100, out)
