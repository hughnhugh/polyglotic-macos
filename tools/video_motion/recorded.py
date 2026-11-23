"""Extract a public 526 recording's first four consecutive captions.

The older server included translations in the corresponding updates. Keep
their actual arrival times, revisions and text. Omit IDs and wall clocks.
"""

import argparse
import json
from pathlib import Path


def extract(path: Path, target: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        groups.setdefault(event["id"], []).append(event)
    result: list[dict] = []
    for events in list(groups.values())[:4]:
        if any(e["replaces"] for e in events):
            raise ValueError("The reference cannot represent joined captions")
        updates, translations = [], []
        finished = None
        for e in events:
            clauses = e["clauses"]
            original = " ".join(c["original"] for c in clauses).strip()
            translated = (
                (" " if target == "en" else "")
                .join(c["translations"].get(target, "") for c in clauses)
                .strip()
            )
            tokens = original.split(" ")
            if e["kind"] == "live":
                used = 0
                words = []
                for token in tokens:
                    used += len(token)
                    words.append({"t": token, "sure": used <= e["established"]})
                    used += 1
                updates.append({"t": e["at"], "words": words})
                if translated:
                    translations.append(
                        {
                            "t": e["at"],
                            "chars": [{"t": ch, "sure": False} for ch in translated],
                        }
                    )
            elif e["kind"] == "finished" and finished is None:
                raw = e["times_raw"]
                finished = {
                    "id": len(result),
                    "s": round(raw[0] - e["mono0"], 3),
                    "e": round(raw[1] - e["mono0"], 3),
                    "en": original,
                    "zh": translated,
                    "words": tokens,
                    "finishT": e["at"],
                    "transT": e["at"],
                    "language": e["language"],
                    "target": target,
                    "updates": updates,
                    "tupdates": translations,
                }
            else:
                raise ValueError(f"Unsupported update in caption {len(result) + 1}")
        if not finished or not finished["zh"]:
            raise ValueError(f"No finished translation in caption {len(result) + 1}")
        result.append(finished)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("target")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            extract(args.corpus, args.target), ensure_ascii=False, separators=(",", ":")
        )
        + "\n",
        encoding="utf-8",
    )
