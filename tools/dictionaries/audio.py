"""Audio files: a pack's commonest words spoken ahead of time by an open
speech model we run ourselves (decision 0133; polyglotic-hq 341, 405, 418).

    uv run --with kokoro-onnx==0.6.1 python -m tools.dictionaries.audio es \\
        --model kokoro-v1.0.onnx --voices voices-v1.0.bin --limit 10000

    # Japanese and Chinese: misaki's pronunciation step too
    uv run --with kokoro-onnx==0.6.1 --with "misaki[ja,zh]==0.9.4" \\
        python -m tools.dictionaries.audio ja --pack .../jmdict.sqlite ...

Writes `<dictionary>.audio` (`adapters.audio_file`; `--out`, by default
beside the pack): each of the pack's commonest headwords, said alone, as
Ogg Opus. Nothing is sent anywhere and no account is needed: the model
runs on this PC's CPU (Kokoro-82M says a word in about 0.15 s on 4
threads), so the live server's GPU is never asked for it. A language of
10,000 words takes about 25 minutes, so a run is gentle with the PC the
live server shares: `--threads` (4) and, on Windows, below-normal priority.
It saves as it goes (`SAVE_EVERY` words, in `<dictionary>.audio.partial`):
a run stopped part way picks up where it was.

The model and voice per language are in `VOICES`: only models and voices
whose licences allow commercial use and redistribution of what they say
(each named in the file's `info`, which the pack list's credits take). The
speech model is not a dependency of the app or of its build: `--with`
brings it for this run alone. Its text-to-phoneme step is espeak-ng
(GPL-3.0; it runs here and is not shipped - the audio is ours to ship),
or for Japanese and Chinese misaki's (Apache-2.0), as Kokoro's own
pipeline does.

A clip is the model's sound with the silence around it cut, encoded by
libsndfile's Opus at `LEVEL`. Every clip's Ogg stream starts with the same
two header pages (about 870 bytes, a third of a short word's file); they are
kept once in the file (`split_ogg`).
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import struct
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from polyglotic_desktop.adapters.audio_file import SUFFIX, write_audio
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from tools.dictionaries import packs

LEVEL = 0.9
"""libsndfile's compression level for Opus (0 best, 1 smallest): about
33 kbit/s for speech at 24 kHz - a word of 0.6 s is about 2.5 kB."""
SERIAL = 0x341
"""Every clip's Ogg stream serial number, so their header pages are the
same bytes (libsndfile picks one at random)."""
QUIET = 0.01
LEAD_SEC = 0.02
TAIL_SEC = 0.08
SAVE_EVERY = 500
"""Words made between saves of a run's partial file (405: a pause lost an
Italian run at 9,000 of 10,000 words)."""
PARTIAL = ".partial"

Synth = Callable[[str], tuple[Any, int]]
"""Says a word: its samples (floats, one channel) and their rate."""

KOKORO = "Kokoro-82M v1.0"
KOKORO_ONLY = (
    "Kokoro-82M: Apache-2.0 (hexgrad); voice {voice}: no third-party data "
    "licence named for it"
)
SIWIS = (
    "Kokoro-82M: Apache-2.0 (hexgrad); its voice ff_siwis was trained on the "
    "SIWIS French Speech Synthesis Database (Yamagishi, Honnet, Garner, "
    "Lazaridis; University of Edinburgh, 2017, doi:10.7488/ds/1705), CC BY 4.0"
)
"""CC BY 4.0 asks for the authors, the licence, and that it was used: said
in the file's `info` and, through the pack list, on Learning."""


@dataclass(frozen=True)
class Spoken:
    """Who says a language's words: the model, its voice, how a word becomes
    the model's phonemes, and the licences that let us ship what they say."""

    tag: str  # the voice's BCP 47 tag: "fr-FR"
    voice: str
    lang: str  # as espeak-ng names the language; "" when `g2p` is misaki's
    g2p: str = "espeak-ng"  # or "misaki-ja", "misaki-zh"
    licence: str = ""
    model: str = KOKORO

    @property
    def licence_text(self) -> str:
        return self.licence or KOKORO_ONLY.format(voice=self.voice)

    @property
    def said_by(self) -> str:
        """The file's `voice`: the model, the voice, and the phoneme step."""
        step = "misaki" if self.g2p.startswith("misaki") else self.g2p
        return f"{self.model}, {self.voice} ({step} G2P)"


VOICES = {
    # 405's listening check (Whisper large-v3, 100 random words; the bar 84):
    # English 94, Spanish 93, Italian 87, Portuguese 86 passed; French 85 is
    # held for the user's ear; Japanese 66 and Chinese 40 are here for 417's
    # comparison, not to publish.
    "en": Spoken("en-US", "af_heart", "en-us"),
    "es": Spoken("es-ES", "ef_dora", "es"),
    "it": Spoken("it-IT", "if_sara", "it"),
    "pt": Spoken("pt-BR", "pf_dora", "pt-br"),
    "fr": Spoken("fr-FR", "ff_siwis", "fr-fr", licence=SIWIS),
    "ja": Spoken("ja-JP", "jf_alpha", "", g2p="misaki-ja"),
    "zh": Spoken("zh-CN", "zf_xiaobei", "", g2p="misaki-zh"),
}


# -- Ogg ---------------------------------------------------------------------------


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        r = n << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
        table.append(r & 0xFFFFFFFF)
    return table


_CRC = _crc_table()


def _crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC[((crc >> 24) & 0xFF) ^ byte]
    return crc


def ogg_pages(data: bytes) -> list[bytes]:
    """An Ogg stream's pages, each with its serial number set to `SERIAL`
    and its checksum made again. ValueError if it isn't Ogg."""
    pages, at = [], 0
    while at < len(data):
        if data[at : at + 4] != b"OggS" or at + 27 > len(data):
            raise ValueError("not an Ogg stream")
        segments = data[at + 26]
        size = 27 + segments + sum(data[at + 27 : at + 27 + segments])
        page = bytearray(data[at : at + size])
        page[14:18] = struct.pack("<I", SERIAL)
        page[22:26] = b"\0\0\0\0"
        page[22:26] = struct.pack("<I", _crc(bytes(page)))
        pages.append(bytes(page))
        at += size
    return pages


def split_ogg(data: bytes) -> tuple[bytes, bytes]:
    """An Ogg Opus file as (its two header pages, the rest): the first is
    the same for every clip one encoder makes."""
    pages = ogg_pages(data)
    if len(pages) < 3:
        raise ValueError("an Ogg Opus stream with no sound")
    return b"".join(pages[:2]), b"".join(pages[2:])


# -- clips -------------------------------------------------------------------------


def trimmed(samples: Any, rate: int) -> Any:
    """The samples without the silence around the word (a little kept);
    none at all if there is no sound in them."""
    import numpy

    loud = numpy.flatnonzero(numpy.abs(samples) > QUIET)
    if not len(loud):
        return samples[:0]  # silence: nothing was said
    first = max(0, int(loud[0]) - int(LEAD_SEC * rate))
    return samples[first : int(loud[-1]) + int(TAIL_SEC * rate)]


def encoded(samples: Any, rate: int) -> bytes:
    import soundfile

    out = io.BytesIO()
    soundfile.write(
        out, samples, rate, format="OGG", subtype="OPUS", compression_level=LEVEL
    )
    return out.getvalue()


def words_to_say(pack_file: Path, limit: int) -> list[str]:
    """The pack's commonest headwords, at most `limit`: words with a letter,
    each once, commonest first."""
    file = SqliteDictionary(pack_file)
    try:
        ranked = file.headwords_ranked(0, limit)
    finally:
        file.close()
    return list(dict.fromkeys(w for w, _ in ranked if any(c.isalpha() for c in w)))


def record_each(
    words: Iterable[str], synth: Synth
) -> tuple[bytes, list[tuple[str, bytes, float]]]:
    """Each word said, cut and encoded: the clips' shared start, and each
    word's own part with its seconds of sound. A word the model gives no
    sound for is left out."""
    head = b""
    clips: list[tuple[str, bytes, float]] = []
    for word in words:
        samples, rate = synth(word)
        samples = trimmed(samples, rate)
        if len(samples) < rate // 50:  # under 20 ms: nothing was said
            continue
        start, rest = split_ogg(encoded(samples, rate))
        if head and start != head:
            raise ValueError(f"{word!r}: its Ogg headers differ from the others'")
        head = start
        clips.append((word, rest, len(samples) / rate))
    return head, clips


def record(
    words: Iterable[str], synth: Synth
) -> tuple[bytes, list[tuple[str, bytes]], float]:
    """`record_each`: the shared start, each word's part, the seconds in all."""
    head, clips = record_each(words, synth)
    return head, [(w, clip) for w, clip, _ in clips], sum(s for _, _, s in clips)


class Partial:
    """A run's work so far, saved as it goes (`<file>.partial`, SQLite): the
    clips' shared start, each word's clip and seconds - and who said them, so
    a run with another voice or model never mixes into it."""

    def __init__(self, path: Path, said_by: str) -> None:
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.executescript(
            "CREATE TABLE IF NOT EXISTS said_by (value TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS head (data BLOB NOT NULL);"
            "CREATE TABLE IF NOT EXISTS clips (word TEXT PRIMARY KEY, "
            "sound BLOB NOT NULL, seconds REAL NOT NULL);"
        )
        row = self._db.execute("SELECT value FROM said_by").fetchone()
        if row is None:
            self._db.execute("INSERT INTO said_by VALUES (?)", (said_by,))
            self._db.commit()
        elif row[0] != said_by:
            self._db.close()
            raise SystemExit(
                f"{path.name} was said by {row[0]}, not {said_by}: delete it to "
                "start again"
            )
        found = self._db.execute("SELECT data FROM head").fetchone()
        self.head: bytes = bytes(found[0]) if found else b""

    def done(self) -> set[str]:
        return {word for (word,) in self._db.execute("SELECT word FROM clips")}

    def save(self, head: bytes, clips: Sequence[tuple[str, bytes, float]]) -> None:
        if head and self.head and head != self.head:
            raise ValueError("this run's Ogg headers differ from the saved ones")
        if head and not self.head:
            self.head = head
            self._db.execute("INSERT INTO head VALUES (?)", (head,))
        self._db.executemany("INSERT OR REPLACE INTO clips VALUES (?, ?, ?)", clips)
        self._db.commit()

    def clips(self, words: Iterable[str]) -> tuple[list[tuple[str, bytes]], float]:
        """The saved clips of `words` (any others left out), and their seconds."""
        wanted = set(words)
        kept, seconds = [], 0.0
        for word, sound, length in self._db.execute("SELECT * FROM clips"):
            if word in wanted:
                kept.append((word, bytes(sound)))
                seconds += length
        return kept, seconds

    def close(self) -> None:
        self._db.close()


def record_saving(
    words: Sequence[str],
    synth: Synth,
    partial: Partial,
    every: int = SAVE_EVERY,
    told: Callable[[int, int], None] = lambda _done, _of: None,
) -> tuple[bytes, list[tuple[str, bytes]], float]:
    """`record`, saved to `partial` each `every` words: the words saved by
    an earlier run aren't said again. The shared start, the clips of
    `words` (in no order), their seconds."""
    have = partial.done()
    todo = [word for word in words if word not in have]
    for at in range(0, len(todo), every):
        chunk = todo[at : at + every]
        partial.save(*record_each(chunk, synth))
        told(len(words) - len(todo) + at + len(chunk), len(words))
    clips, seconds_in_all = partial.clips(words)
    return partial.head, clips, seconds_in_all


def kokoro(model: Path, voices: Path, spoken: Spoken, threads: int = 4) -> Synth:
    """Kokoro-82M on this PC's CPU (onnxruntime, `threads` of it), through
    kokoro-onnx; Japanese and Chinese through misaki's phonemes."""
    import onnxruntime
    from kokoro_onnx import Kokoro  # type: ignore[import-not-found]

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = onnxruntime.InferenceSession(
        str(model), options, providers=["CPUExecutionProvider"]
    )
    engine = Kokoro.from_session(session, str(voices))
    phonemes = misaki(spoken.g2p) if spoken.g2p.startswith("misaki") else None

    def say(word: str) -> tuple[Any, int]:
        if phonemes is not None:
            samples, rate = engine.create(
                phonemes(word),
                voice=spoken.voice,
                speed=1.0,
                lang="en-us",
                is_phonemes=True,
            )
        else:
            samples, rate = engine.create(
                word, voice=spoken.voice, speed=1.0, lang=spoken.lang
            )
        return samples, int(rate)

    return say


def misaki(g2p: str) -> Callable[[str], str]:
    """misaki's text to Kokoro's phonemes for Japanese or Chinese."""
    import importlib

    classes = {"misaki-ja": ("ja", "JAG2P"), "misaki-zh": ("zh", "ZHG2P")}
    if g2p not in classes:
        raise ValueError(g2p)
    module, name = classes[g2p]
    convert = getattr(importlib.import_module(f"misaki.{module}"), name)()
    return lambda text: str(convert(text)[0])


def info(dictionary: str, language: str, spoken: Spoken) -> dict[str, str]:
    return {
        "dictionary": dictionary,
        "language": language,
        "voice_language": spoken.tag,
        "voice": spoken.said_by,
        "licence": spoken.licence_text,
        "made": "ahead of time, on Polyglotic's own PC; nobody has checked each word",
    }


def build(
    pack_file: Path,
    synth: Synth,
    spoken: Spoken,
    limit: int,
    out: Path,
    told: Callable[[int, int], None] = lambda _done, _of: None,
) -> dict[str, object]:
    """`pack_file`'s words said into `<dictionary>.audio` in `out`, saved
    as they're made (`Partial`, deleted once the file is written)."""
    pack = SqliteDictionary(pack_file)
    try:
        dictionary, language = pack.info["dictionary"], pack.info["language"]
    finally:
        pack.close()
    words = words_to_say(pack_file, limit)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{dictionary}{SUFFIX}"
    partial = Partial(path.with_name(path.name + PARTIAL), spoken.said_by)
    started = time.perf_counter()
    try:
        head, clips, seconds = record_saving(
            words, synth, partial, every=SAVE_EVERY, told=told
        )
    finally:
        partial.close()
    took = time.perf_counter() - started
    write_audio(path, info(dictionary, language, spoken), head, clips)
    partial.path.unlink()
    sound = sum(len(clip) for _, clip in clips)
    return {
        "file": path.name,
        "words": len(clips),
        "of the words asked": len(words),
        "seconds of sound": round(seconds),
        "seconds to make (this run)": round(took),
        "bytes a word": round(sound / max(1, len(clips))),
        "size": f"{path.stat().st_size / 1e6:.1f} MB",
    }


def _below_normal() -> None:
    """This process at below-normal priority on Windows: the live server's
    word-link aligner shares the CPU (polyglotic-hq projects/README.md)."""
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("language", choices=sorted(VOICES))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument(
        "--pack",
        type=Path,
        help="the pack whose words are said (default: the built pack's "
        "<name>.sqlite in build/dictionaries/packs)",
    )
    parser.add_argument("--out", type=Path, help="(default: beside the pack)")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    pack_file = args.pack or (
        packs.REPO
        / "build"
        / "dictionaries"
        / "packs"
        / f"{packs.PACKS[args.language].name}.sqlite"
    )
    _below_normal()
    spoken = VOICES[args.language]
    synth = kokoro(args.model, args.voices, spoken, args.threads)
    started = time.perf_counter()

    def told(done: int, of: int) -> None:
        took = time.perf_counter() - started
        print(f"  {done:,} of {of:,} words ({took:.0f} s)", flush=True)

    stats = build(
        pack_file, synth, spoken, args.limit, args.out or pack_file.parent, told
    )
    print(f"{stats['file']}: words spoken by {spoken.said_by}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
