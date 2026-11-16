"""The review sheet (tools/i18n/review.py): a native reviewer's spreadsheet
out of a translation file and back - corrections in and reviewed, "ok"
marks reviewed, a broken placeholder refused (polyglotic-hq 156)."""

import csv
import shutil
from pathlib import Path

from tools.i18n import __main__ as i18n
from tools.i18n import review, ts


def _rows(sheet: Path) -> list[dict[str, str]]:
    with sheet.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _fill(sheet: Path, rows: list[dict[str, str]]) -> None:
    with sheet.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, review.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_a_sheet_goes_out_and_its_corrections_come_back(tmp_path: Path) -> None:
    language_file = tmp_path / "polyglotic_zh_CN.ts"
    shutil.copy(i18n.ts_path("zh_CN"), language_file)
    sheet = tmp_path / "review.csv"
    count = review.write_sheet(language_file, sheet)
    rows = _rows(sheet)
    assert len(rows) == count == len(ts.read(language_file).translations)
    assert sheet.read_bytes().startswith(b"\xef\xbb\xbf")  # Excel reads it as UTF-8
    row = {(r["context"], r["english"]): r for r in rows}
    assert row["LookupCard", "'+%Ln more reading(s)"]["translation"].startswith(
        "'+"
    )  # no formula

    row["CaptionWindow", "Original only"]["correction"] = "只看原文"
    row["TranscriptWindow", "Copy"]["ok"] = "x"
    row["CaptionWindow", "{app}'s captions appear here"]["correction"] = (
        "字幕会显示在这里"  # lost {app}
    )
    row["LookupCard", "'+%Ln more reading(s)"]["correction"] = "'+%Ln 个读音"
    _fill(sheet, rows)

    file = ts.read(language_file)
    reviewed, refused = review.read_sheet(sheet, file)
    original_only = ("CaptionWindow", "Original only", "")
    assert reviewed[original_only] == ts.Translation(("只看原文",), done=True)
    assert reviewed[("TranscriptWindow", "Copy", "")].done
    assert reviewed[("LookupCard", "+%Ln more reading(s)", "")].forms == (
        "+%Ln 个读音",
    )
    assert ("CaptionWindow", "{app}'s captions appear here", "") not in reviewed
    assert len(refused) == 1 and "{app}" in refused[0]
    assert len(reviewed) == 3
