"""Qt's translation files (`.ts`): read, merged with the code's messages,
written back (decision 0034).

A `.ts` file is what a translator works in - Qt Linguist opens it, and
translation services (Weblate, Crowdin) read it. Each message keeps its
translation and its state:

- **unfinished** with a translation: a draft, waiting for a native
  speaker's review (Linguist shows it with a "?" until it's marked done);
- **finished** (no `type`): reviewed;
- **unfinished** and empty: not translated yet - the app shows the English.

`lrelease` puts drafts in the `.qm` too, so a draft is on screen until it's
reviewed. Written sorted by context, messages in the order the code first
uses them, with a file but no line - so a line moved elsewhere in a file
doesn't change the file.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from tools.i18n.extract import Message

DRAFT = "unfinished"


@dataclass(frozen=True)
class Translation:
    """What a `.ts` file holds for one message."""

    forms: tuple[str, ...] = ()  # one, or one per plural form
    done: bool = False  # reviewed by a native speaker

    @property
    def empty(self) -> bool:
        return not any(self.forms)


@dataclass
class TsFile:
    language: str
    translations: dict[tuple[str, str, str], Translation] = field(default_factory=dict)


def read(path: Path) -> TsFile:
    root = ET.parse(path).getroot()
    file = TsFile(root.get("language", ""))
    for context in root.iter("context"):
        name = context.findtext("name") or ""
        for message in context.iter("message"):
            translation = message.find("translation")
            if translation is None or translation.get("type") in (
                "vanished",
                "obsolete",
            ):
                continue
            forms = tuple(f.text or "" for f in translation.iter("numerusform"))
            if not forms:
                forms = (translation.text or "",)
            key = (
                name,
                message.findtext("source") or "",
                message.findtext("comment") or "",
            )
            file.translations[key] = Translation(
                forms, translation.get("type") != DRAFT
            )
    return file


def _x(text: str) -> str:
    return escape(text, {'"': "&quot;", "'": "&apos;"})


def english_forms(source: str) -> tuple[str, str]:
    """English's two forms of a count's text, from its "(s)" or "(es)":
    "%n caption(s)" -> "%n caption", "%n captions". Kept once written, so
    an irregular one ("heard once") is fixed by hand in `en.ts`."""
    one = re.sub(r"\((e?s)\)", "", source)
    other = re.sub(r"\((e?s)\)", r"\1", source)
    return one, other


def write(
    path: Path,
    language: str,
    messages: list[Message],
    old: TsFile,
    plurals_only: bool = False,
) -> str:
    """The file's text: every message in the code, with the translation
    the old file had for it. English's file (`plurals_only`) holds only
    counts - its other text is the code's."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE TS>",
        f'<TS version="2.1" language="{language}" sourcelanguage="en">',
    ]
    by_context: dict[str, list[Message]] = {}
    for message in messages:
        if plurals_only and not message.numerus:
            continue
        by_context.setdefault(message.context, []).append(message)
    for context in sorted(by_context):
        lines += ["<context>", f"    <name>{_x(context)}</name>"]
        for message in by_context[context]:
            translation = old.translations.get(message.key, Translation())
            if plurals_only and translation.empty:
                translation = Translation(english_forms(message.source), done=True)
            numerus = ' numerus="yes"' if message.numerus else ""
            lines.append(f"    <message{numerus}>")
            lines.append(f'        <location filename="../{message.file}"/>')
            lines.append(f"        <source>{_x(message.source)}</source>")
            if message.comment:
                lines.append(f"        <comment>{_x(message.comment)}</comment>")
            if message.note:
                lines.append(f"        <extracomment>{_x(message.note)}</extracomment>")
            state = (
                "" if translation.done and not translation.empty else f' type="{DRAFT}"'
            )
            if message.numerus:
                lines.append(f"        <translation{state}>")
                for form in translation.forms or ("",):
                    lines.append(f"            <numerusform>{_x(form)}</numerusform>")
                lines.append("        </translation>")
            else:
                text = translation.forms[0] if translation.forms else ""
                lines.append(f"        <translation{state}>{_x(text)}</translation>")
            lines.append("    </message>")
        lines.append("</context>")
    lines.append("</TS>")
    return "\n".join(lines) + "\n"
