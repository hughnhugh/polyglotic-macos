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
    tried = [v for v in ordered if v.language.lower() in ("zh-cn", "zh-tw", "zh-hk")]
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
