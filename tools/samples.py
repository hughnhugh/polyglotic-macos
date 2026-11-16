"""The samples Home offers when nothing is playing (polyglotic-hq 176): a
few FLEURS sentences in each language a learner can learn, joined with
short gaps, evened in volume, as 16 kHz mono FLAC in
`platform/data/samples/` - with their credits in that folder's
CREDITS.md and THIRD_PARTY_NOTICES.md.

FLEURS (Conneau et al., 2022; google/fleurs on Hugging Face) is CC BY 4.0.
The clips are its test split, as polyglotic-hq project 086 downloaded them
(`data/audio/<config>/manifest.json` beside each WAV).

    uv run python -m tools.samples DIR   # DIR: 086's data/audio
"""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from polyglotic_desktop.platform.replay import read_clip

OUT = (
    Path(__file__).resolve().parents[1] / "src/polyglotic_desktop/platform/data/samples"
)
CHOSEN = {  # language learned -> (FLEURS config, sentence ids in order)
    "zh": ("cmn_hans_cn", ("2005", "1760", "1965", "1871")),
    "en": ("en_us", ("1972", "1750", "1720", "1674")),
}
LEAD_IN_SEC, GAP_SEC, TRAILING_SEC = 0.3, 0.9, 1.0
PEAK = 0.5  # -6 dBFS
RATE = 16000


def build(audio_dir: Path) -> None:
    for language, (config, ids) in CHOSEN.items():
        manifest = json.loads((audio_dir / config / "manifest.json").read_text("utf-8"))
        by_id: dict[str, dict[str, str]] = {}
        for entry in manifest:
            by_id.setdefault(entry["id"], entry)  # FLEURS has several readings
        pieces = [np.zeros(round(LEAD_IN_SEC * RATE), np.float32)]
        for n, sentence in enumerate(ids):
            clip = read_clip(audio_dir / config / by_id[sentence]["file"])
            pieces.append(clip * (PEAK / max(1e-6, float(np.abs(clip).max()))))
            gap = TRAILING_SEC if n == len(ids) - 1 else GAP_SEC
            pieces.append(np.zeros(round(gap * RATE), np.float32))
        joined = np.concatenate(pieces)
        sf.write(OUT / f"{language}.flac", joined, RATE, subtype="PCM_16")
        print(language, f"{len(joined) / RATE:.1f} s", [by_id[s]["raw"] for s in ids])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m tools.samples")
    parser.add_argument("audio_dir", type=Path)
    build(parser.parse_args().audio_dir)
