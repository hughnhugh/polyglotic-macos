"""515: what the Mac says for public Chinese test words (polyglotic-hq 515) -
every Chinese voice macOS lists, with its quality, the one the card would
use first, and each word made by the app's own `MacVoices` at the card's
pace (1.0) and slower (0.7), trimmed as the speaker trims it - as WAV
files and their facts (rate, the buffers' formats, length, level).
Nothing is played.

    uv run --no-sync python -m tools.macos_audio515 OUT
"""

from __future__ import annotations

import json
import sys
import wave
from array import array
from pathlib import Path

WORDS = ["你好", "谢谢", "朋友", "学习", "今天天气很好", "我们一起去公园散步吧。"]


def level(pcm: bytes) -> dict[str, float]:
    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        return {"peak": 0.0, "rms": 0.0}
    peak = max(abs(s) for s in samples) / 32768
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768
    return {"peak": round(peak, 3), "rms": round(rms, 4)}


def main() -> int:
    """The words are made on a thread of their own while the main thread runs
    Qt's event loop, as the app's speaker thread does beside the interface:
    macOS hands a word's buffers over through the main thread's run loop
    (run 2 made them on the main thread and every word timed out)."""
    import threading
    import time

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(["audio515"])
    done: list[int] = []

    def work() -> None:
        try:
            done.append(made())
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            done.append(1)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    end = time.monotonic() + 600
    while worker.is_alive() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    return done[0] if done else 1


TRIED = ("Tingting", "Meijia", "Eddy")
"""Mandarin's own voice on this Mac, Taiwan's, and one of the Eloquence
voices the card may also list."""


def made() -> int:
    from polyglotic_desktop.platform.macos import objc, voices
    from polyglotic_desktop.platform.speaking import trimmed

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    mac = voices.MacVoices()
    with objc.pool():
        objc.load("AVFoundation")
        kind = objc.cls("AVSpeechSynthesisVoice")
        listed = [
            voices._listed(v) for v in objc.items(objc.send(kind, "speechVoices"))
        ]
    chinese = [v for v in listed if v.voice.language.lower().startswith("zh")]
    ordered = [v for v in mac.found() if v.language.lower().startswith("zh")]
    facts: dict[str, object] = {
        "chinese_voices": [
            {
                "name": v.voice.name,
                "id": v.voice.id,
                "language": v.voice.language,
                "quality": v.quality,
                "traits": v.traits,
            }
            for v in chinese
        ],
        "card_order": [f"{v.name} ({v.language})" for v in ordered],
        "all_voices": len(listed),
        "clips": [],
    }
    tried = [
        v for v in ordered
        if v.name in TRIED and v.language.lower() in ("zh-cn", "zh-tw")
    ][:4]  # fmt: skip
    for v in tried:
        for i, word in enumerate(WORDS):
            for rate in (1.0, 0.7):
                try:
                    clip = trimmed(mac.synthesize(word, v, rate))
                except OSError as error:
                    facts["clips"].append(
                        {"voice": v.name, "word": i, "error": str(error)}
                    )  # type: ignore[union-attr]
                    continue
                name = f"{v.name.replace(' ', '_')}-{v.language}-{i}-{rate}.wav"
                with wave.open(str(out / name), "wb") as w:
                    w.setnchannels(clip.channels)
                    w.setsampwidth(2)
                    w.setframerate(clip.rate)
                    w.writeframes(clip.pcm)
                facts["clips"].append(  # type: ignore[union-attr]
                    {
                        "file": name,
                        "voice": v.name,
                        "language": v.language,
                        "word": i,
                        "rate": rate,
                        "hz": clip.rate,
                        "seconds": round(clip.seconds, 3),
                        **level(clip.pcm),
                    }
                )
    # how much slower each pace is on a Mac (Windows' 0.7 takes 1.4 times as long)
    paces: dict[str, dict[str, float]] = {}
    found = mac.found()
    for name, language, text in (
        ("Tingting", "zh-CN", WORDS[5]),
        ("Samantha", "en-US", "The weather is nice today; let's go for a walk."),
    ):
        voice = next(
            (v for v in found if v.name == name and v.language == language), None
        )
        if voice is None:
            continue
        lengths: dict[str, float] = {}
        for pace in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
            try:
                lengths[str(pace)] = round(
                    trimmed(mac.synthesize(text, voice, pace)).seconds, 3
                )
            except OSError as error:
                lengths[str(pace)] = -1.0
                print(name, pace, error)
        paces[name] = lengths
    facts["paces"] = paces
    facts["formats"] = sorted(mac.formats)
    (out / "facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in facts.items() if k != "clips"},
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
