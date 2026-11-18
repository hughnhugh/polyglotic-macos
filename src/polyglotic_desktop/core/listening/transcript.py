"""The transcript: the caption history written out as text, SRT or CSV.

What the user saves with "Save transcript as" (MVP.md: save and export the
caption history as text, SRT and CSV; projects 009, 015). Only finished
captions - a live update is still changing. Nothing is written anywhere
unless the user asks: these return the text, and the interface writes it
to the file they chose.

- **Text:** a caption per paragraph: its time, the name of its source as
  the transcript shows it ("You" for the user's own mic), what was said,
  then each translation on its own line.
- **SRT** (SubRip): numbered cues timed from the start of the listening
  session - when each caption first appeared until it finished (at least
  `MIN_CUE_SEC`, and never into the next) - what was said, and its
  translation into one language under it.
- **CSV:** a row per caption - its time, whether it was you, its
  source's name, its language, what was said, and a column per
  translation.
- **A caption's translation alone** (`translation_text`): for copying a
  line's translation without the rest (polyglotic-hq 333).

Each translation goes under the language it is written in: a caption
already in a target is translated into the target's second language, which
the server keeps under the target (`captions.line_language`: the server's
word for each line, else worked out from the caption's language with
`seconds`, each target's second language) - so an English caption's
Chinese line, in a window into English with Chinese its second, is saved
as Chinese, not as English (polyglotic-hq 432), and so is an English
clause's Chinese line in a Mandarin caption (497).

The interface passes its own time zone and source names, so what's saved
reads as the screen did (polyglotic-hq project 062).

Holds caption text: the user's own data, saved only where they say.
"""

import csv
import io
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, tzinfo

from polyglotic_desktop.core.listening.captions import Language, line_language
from polyglotic_desktop.core.listening.history import Caption, join_text
from polyglotic_desktop.core.listening.sources import SourceId

MIN_CUE_SEC = 1.5
"""The shortest an SRT cue lasts, so a quick caption can still be read."""


def finished(captions: Sequence[Caption]) -> list[Caption]:
    return [c for c in captions if not c.live]


Seconds = Mapping[Language, Language]
"""Each target's second language (protocol.md's `second_languages`)."""


def _translations(
    caption: Caption, languages: Sequence[Language], seconds: Seconds | None = None
) -> list[str]:
    """The caption's translation into each language, clause by clause - a
    clause with none in it gives its original; "" where no clause was
    translated into it (it was already in that language). A line is in the
    language it is written in (`line_language`), whatever its key."""
    seconds = seconds or {}
    written = [
        {
            line_language(clause, key, caption.language, seconds.get(key)): text
            for key, text in clause.translations.items()
        }
        for clause in caption.clauses
    ]
    found = []
    for language in languages:
        translated = any(language in w for w in written)
        found.append(
            join_text(
                w.get(language, c.original)
                for w, c in zip(written, caption.clauses, strict=True)
            )
            if translated
            else ""
        )
    return found


def translation_text(
    caption: Caption, languages: Sequence[Language], seconds: Seconds | None = None
) -> str:
    """The caption's translations alone - into each of `languages` it was
    translated into, one a line, as `as_text` writes them without their
    language's name; "" for none (the transcript's "Copy the
    translation", polyglotic-hq 333)."""
    found = _translations(caption, languages, seconds)
    return "\n".join(text for text in found if text)


def as_text(
    captions: Sequence[Caption],
    languages: Sequence[Language],
    names: dict[str, str] | None = None,
    you: str = "You",
    zone: tzinfo | None = None,
    sources: Mapping[SourceId, str] | None = None,
    seconds: Seconds | None = None,
) -> str:
    """The finished captions as plain text. `names` names the languages
    for the translation lines (default: their codes); `sources` names the
    sources (default: none), and `you` labels the user's own captions when
    `sources` doesn't name theirs; times are shown in `zone` (default: as
    stored, UTC)."""
    names = names or {}
    paragraphs = []
    for caption in finished(captions):
        time = caption.started_at.astimezone(zone) if zone else caption.started_at
        head = f"[{time:%H:%M:%S}]"
        who = _source_name(caption, sources, you)
        if who:
            head += f" {who}:"
        lines = [f"{head} {caption.original}"]
        for language, text in zip(
            languages, _translations(caption, languages, seconds), strict=True
        ):
            if text:
                lines.append(f"    {names.get(language, language)}: {text}")
        paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs) + ("\n" if paragraphs else "")


def _source_name(
    caption: Caption, sources: Mapping[SourceId, str] | None, you: str
) -> str:
    """The caption's source as named, "you" for the user's own if not."""
    name = (sources or {}).get(caption.source_id, "")
    return name or (you if caption.by_you else "")


def as_srt(
    captions: Sequence[Caption],
    languages: Sequence[Language],
    started_at: datetime,
    seconds: Seconds | None = None,
) -> str:
    """The finished captions as SubRip cues, timed from `started_at` (the
    listening session's start), each with its translations into
    `languages` under what was said (`translation_text`: the window's
    language, or for a caption already in it, its second's)."""
    shown = finished(captions)
    cues = []
    for n, caption in enumerate(shown):
        start = caption.started_at - started_at
        end = max(
            caption.updated_at - started_at, start + timedelta(seconds=MIN_CUE_SEC)
        )
        if n + 1 < len(shown):
            following = shown[n + 1].started_at - started_at
            if following > start:
                end = min(end, following)
        lines = [caption.original]
        translation = translation_text(caption, languages, seconds)
        if translation:
            lines.append(translation)
        cues.append(
            f"{n + 1}\n{_srt_time(start)} --> {_srt_time(end)}\n" + "\n".join(lines)
        )
    return "\n\n".join(cues) + ("\n" if cues else "")


def _srt_time(offset: timedelta) -> str:
    ms = max(0, round(offset.total_seconds() * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def as_csv(
    captions: Sequence[Caption],
    languages: Sequence[Language],
    zone: tzinfo | None = None,
    sources: Mapping[SourceId, str] | None = None,
    seconds: Seconds | None = None,
) -> str:
    """The finished captions as CSV, a row each: time (ISO 8601, in
    `zone`), you (yes/no), its source's name (from `sources`; "" if not
    named), language, original, then a column per translation language."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["time", "you", "source", "language", "original", *languages])
    for caption in finished(captions):
        time = caption.started_at.astimezone(zone) if zone else caption.started_at
        writer.writerow(
            [
                time.isoformat(timespec="seconds"),
                "yes" if caption.by_you else "no",
                (sources or {}).get(caption.source_id, ""),
                caption.language or "",
                caption.original,
                *_translations(caption, languages, seconds),
            ]
        )
    return out.getvalue()
