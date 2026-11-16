"""Drafting a language's interface text: every string with no translation,
handed to a drafter and its answers checked back in (polyglotic-hq 294,
decision 0087).

python -m tools.i18n draft de                          # the work, for the drafter
python -m tools.i18n draft de --answers answers.tsv    # its answers in, checked

**The work** (`build/i18n/draft-<language>.tsv`): a line per string the
language has no translation for - new in the code, or changed (its English
changed, so its old translation went: `update`). Each line: its id, where
it's used (Qt's context), how many forms it takes (a count's, in this
language: `keep.PLURAL_FORMS`), the English, and the note for the
translator. Drafted and reviewed strings aren't in it, so a run after the
first touches only what's new or changed.

**The drafter** reads the work, the language's glossary
(`translations/GLOSSARY-<language>.md`: the product's terms - caption,
lookup, "Translate into" - said one way every time) and writes **answers**:
a TSV, each line an id, a tab, the translation (a count's forms split by
" | "). Today the drafter is Claude, in a Claude Code session (polyglotic-hq
294): no outside service gets the strings without the user's say.

**The answers come in** checked by machine (`keep.broken`: the `{names}`,
the count, HTML tags, the number of forms); each good one goes into the
`.ts` as a draft ("?" in Qt Linguist, until a native reader reviews it),
each refused one is listed and stays empty - the next run hands it out
again. A glossary term the English uses and the translation doesn't is
listed too (a hint, not a refusal: a word's form changes with its place in
a sentence).
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tools.i18n import extract, keep, ts

WORK = extract.REPO / "build" / "i18n"
FORMS = " | "


def message_id(key: tuple[str, str, str]) -> str:
    """A string's id in the work and the answers: short, and the same on
    every run (a hash of its context, English and disambiguation)."""
    return hashlib.sha1("\0".join(key).encode("utf-8")).hexdigest()[:10]


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def _uncell(text: str) -> str:
    return re.sub(r"\\([\\tn])", lambda m: {"t": "\t", "n": "\n"}.get(m[1], "\\"), text)


def to_draft(messages: list[extract.Message], file: ts.TsFile) -> list[extract.Message]:
    """The messages `file` has no translation for, in the code's order."""
    return [m for m in messages if file.translations.get(m.key, ts.Translation()).empty]


def write_work(language: str, messages: list[extract.Message], out: Path) -> int:
    """The drafter's work for `language`: a line per message; how many."""
    lines = ["id\tcontext\tforms\tenglish\tnote"]
    for message in messages:
        forms = keep.PLURAL_FORMS[language] if message.numerus else 1
        note = message.note
        if message.comment:
            note = f"({message.comment}) {note}".strip()
        lines.append(
            "\t".join(
                [
                    message_id(message.key),
                    message.context,
                    str(forms),
                    _cell(message.source),
                    _cell(note),
                ]
            )
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return len(messages)


@dataclass
class Answers:
    drafted: dict[tuple[str, str, str], ts.Translation]
    refused: list[str]
    unknown: list[str]  # ids not in the work any more


def read_answers(
    answers: Path, language: str, messages: list[extract.Message]
) -> Answers:
    """The drafter's answers, checked: each good one a draft."""
    by_id = {message_id(m.key): m for m in messages}
    found = Answers({}, [], [])
    for number, line in enumerate(answers.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith(("id\t", "#")):
            continue
        ident, _, text = line.partition("\t")
        message = by_id.get(ident.strip())
        if message is None:
            found.unknown.append(f"line {number}: {ident!r}")
            continue
        forms = tuple(_uncell(f.strip()) for f in text.split(FORMS.strip()))
        if not message.numerus:  # as written: a list's ", " keeps its space
            forms = (_uncell(text.rstrip("\r\n")),)
        wrong = keep.broken(message.source, forms, language)
        if wrong:
            found.refused.append(f"{message.source!r}: {wrong}")
            continue
        found.drafted[message.key] = ts.Translation(forms, done=False)
    return found


_ROW = re.compile(r"^\|(.+)\|(.+)\|")


def glossary(language: str) -> list[tuple[str, str]]:
    """The glossary's terms, (English, the language's), from its table:
    only rows with one term on each side ("caption | Untertitel")."""
    path = extract.REPO / "translations" / f"GLOSSARY-{language}.md"
    if not path.exists():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not _ROW.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        english, theirs = cells[0], cells[1]
        if (
            english
            and theirs
            and not set(english) <= set("-: ")
            and "/" not in english + theirs
            and "(" not in english
            and english.lower() != "english"
        ):
            terms.append((english, theirs))
    return terms


def unglossed(
    language: str, drafted: dict[tuple[str, str, str], ts.Translation]
) -> list[str]:
    """Drafts whose English uses a glossary term their translation doesn't
    (its first five letters, so most of a word's endings still match)."""
    found = []
    for english, theirs in glossary(language):
        term = re.compile(rf"\b{re.escape(english)}s?\b", re.IGNORECASE)
        stem = theirs.split(",")[0].strip().lower()[:5]
        for (_context, source, _comment), translation in drafted.items():
            if term.search(source) and not any(
                stem in form.lower() for form in translation.forms
            ):
                found.append(f"{english!r} -> {theirs!r}: {source!r}")
    return found
