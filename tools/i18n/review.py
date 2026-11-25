"""A spreadsheet for a native reviewer who'd rather not install Qt
Linguist (decision 0034; translations/README.md).

python -m tools.i18n sheet zh_CN review.csv   # every string, to review
python -m tools.i18n sheet de review.csv --most-seen 60   # the 60 seen most
python -m tools.i18n apply zh_CN review.csv   # the corrections back in

`--most-seen 60` is the sheet a friend who speaks the language reads in
ten minutes (polyglotic-hq 294): the 60 strings the interface shows most,
most first, each once - the order `python -m tools.ui_lab seen` found
(`build/ui-lab/seen.tsv`; run it first).

The sheet has a row per string: where it's used, the English, Qt's
disambiguation and the note for the translator, the translation now,
whether it's reviewed - and two columns for the reviewer: "ok" (anything
there: the translation is right as it is) and "correction" (the right
translation). `apply` puts each correction in, and marks it and each "ok"
reviewed; a correction that loses or renames a `{placeholder}` or the
count is refused, and said. A count with several forms has them split by
" | ". Saved as UTF-8 with a byte-order mark, so Excel opens Chinese
right; a cell starting like a formula (=, +, -, @) starts with an
apostrophe, taken off again on the way back.
"""

import csv
from pathlib import Path

from tools.i18n import extract, keep, ts

SEEN = extract.REPO / "build" / "ui-lab" / "seen.tsv"
WHERE = {
    "Account": "Account",
    "CaptionDelay": "Settings > Captions > Timing",
    "CaptionPreview": "Settings > Captions > Look",
    "CaptionWindow": "a caption window",
    "ColourControls": "Settings > Captions > Look > colours",
    "ConsentDialog": "the question about what to share",
    "DeleteLearningDialog": "deleting your learning data",
    "DesktopApp": "the tray menu and the app's messages",
    "DictationKey": "Settings > App > Dictation",
    "DictationSign": "the sign shown while dictating",
    "FeedbackDialog": "Report a problem / Ask a question / Help build Polyglotic",
    "FirstRun": "the first start",
    "Help": "Help",
    "Home": "Home",
    "JoinedWindow": "joined caption windows",
    "Lab": "Settings > Captions > Lab",
    "LanguagePicker": "the first start: choosing the app's language",
    "Learning": "Learning",
    "LearningLanguage": "Learning",
    "Languages": "language names and notes",
    "LevelPicker": "Learning > your level",
    "LookupCard": "a word's card (a lookup)",
    "MainWindow": "the main window's side bar",
    "Pages": "the main window",
    "Panels": "caption settings (Settings > Captions, a transcript's side panel)",
    "Plan": "Account > your plan",
    "ProblemReport": "Report a problem / Make a suggestion",
    "Settings": "Settings",
    "SettingsPopover": "a caption window's settings",
    "SignInDialog": "signing in",
    "TranscriptWindow": "a transcript",
    "Transcripts": "a transcript",
    "Words": "Words",
}
"""Where each context's strings are, in a reviewer's words."""

COLUMNS = (
    "where",
    "context",
    "english",
    "disambiguation",
    "note",
    "translation",
    "reviewed",
    "ok",
    "correction",
)
FORMS = " | "
_FORMULA = ("=", "+", "-", "@")


def _cell(text: str) -> str:
    return "'" + text if text.startswith(_FORMULA) else text


def _uncell(text: str) -> str:
    return text[1:] if text.startswith("'") and text[1:].startswith(_FORMULA) else text


def most_seen(
    file: ts.TsFile, count: int, seen: Path = SEEN
) -> list[tuple[tuple[str, str, str], int]]:
    """The `count` strings of `file` the interface shows most (`seen`,
    written by `python -m tools.ui_lab seen`), each English once, and how
    many of the lab's screens show it."""
    if not seen.exists():
        raise SystemExit(f"{seen} isn't there: run `python -m tools.ui_lab seen` first")
    found: list[tuple[tuple[str, str, str], int]] = []
    english: set[str] = set()
    for line in seen.read_text(encoding="utf-8").splitlines()[1:]:
        states, context, source, comment, _where = line.split("\t")
        key = (context, source, comment)
        if key in file.translations and source not in english:
            english.add(source)
            found.append((key, int(states)))
        if len(found) == count:
            break
    return found


def write_sheet(
    language_file: Path, sheet: Path, most: int | None = None, seen: Path = SEEN
) -> int:
    """The sheet for `language_file` - every string, or the `most` seen
    most (`most_seen`), most first; how many rows."""
    file = ts.read(language_file)
    notes = {m.key: m.note for m in extract.read().messages}
    if most is None:
        rows = [(key, 0) for key in file.translations]
    else:
        rows = most_seen(file, most, seen)
    with sheet.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        for (context, source, comment), screens in rows:
            translation = file.translations[(context, source, comment)]
            where = WHERE.get(context, context)
            if screens:
                where += f" (on {screens} of the UI lab's screens)"
            writer.writerow(
                [
                    where,
                    context,
                    _cell(source),
                    comment,
                    notes.get((context, source, comment), ""),
                    _cell(FORMS.join(translation.forms)),
                    "yes" if translation.done else "",
                    "",
                    "",
                ]
            )
    return len(rows)


def read_sheet(
    sheet: Path, file: ts.TsFile
) -> tuple[dict[tuple[str, str, str], ts.Translation], list[str]]:
    """The reviewed translations a filled-in sheet gives, by message, and
    the corrections refused."""
    reviewed: dict[tuple[str, str, str], ts.Translation] = {}
    refused = []
    with sheet.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            key = (row["context"], _uncell(row["english"]), row["disambiguation"])
            now = file.translations.get(key)
            if now is None:
                refused.append(f"{key[1]!r}: not in the translation file any more")
                continue
            correction = _uncell(row["correction"].strip())
            if correction:
                forms = tuple(f.strip() for f in correction.split(FORMS.strip()))
                wrong = keep.broken(key[1], forms, file.language)
                if wrong:
                    refused.append(f"{key[1]!r}: {wrong}")
                    continue
                reviewed[key] = ts.Translation(forms, done=True)
            elif row["ok"].strip() and not now.empty:
                reviewed[key] = ts.Translation(now.forms, done=True)
    return reviewed, refused
