"""The app's log, as a report attaches it: the newest part, the user's folder hidden.

The log (`logs/polyglotic.log` in the data folder, rotated as
`polyglotic.log.1`, `.2`...) records what the app did - never captions,
audio or settings. A report may attach its newest `LIMIT` characters,
reading back into the previous file when the current one is short. Before
the user sees it, their home folder (`C:\\Users\\<name>`) is replaced by
`%USERPROFILE%`: a traceback names files by their full path, and the
path holds the user's name. What `read_log` returns is exactly what's
shown and sent.
"""

from pathlib import Path

LIMIT = 256 * 1024  # characters: half the protocol's 512 KiB, so a request stays small
LOG_NAME = "polyglotic.log"


def read_log(folder: Path, home: Path | None = None, limit: int = LIMIT) -> str | None:
    """The newest `limit` characters of the log in `folder`, starting at a
    whole line, with `home` hidden; None if there's no log (run from
    source, the app logs to its console)."""
    parts: list[str] = []
    size = 0
    for index in range(10):
        path = folder / (LOG_NAME if index == 0 else f"{LOG_NAME}.{index}")
        try:
            text = path.read_text("utf-8", errors="replace")
        except OSError:
            break
        parts.insert(0, text)
        size += len(text)
        if size >= limit:
            break
    if not parts:
        return None
    joined = "".join(parts)
    if len(joined) > limit:
        joined = joined[-limit:]
        newline = joined.find("\n")
        joined = joined[newline + 1 :] if newline >= 0 else joined
    return hide_home(joined, home if home is not None else Path.home())


def hide_home(text: str, home: Path) -> str:
    """`text` with the user's home folder written as `%USERPROFILE%`, in
    either slash, any case (Windows paths ignore case), and escaped with
    each backslash doubled, as Velopack's own lines write a path at every
    update check ("Reading releases from file: ...", polyglotic-hq 336)."""
    escaped = str(home).replace("\\", "\\\\")
    for form in (escaped, str(home), home.as_posix()):  # the escaped one first
        if len(form) <= 3:  # a drive or nothing: no name to hide
            continue
        lowered, needle = text.lower(), form.lower()
        found = lowered.find(needle)
        while found >= 0:
            text = text[:found] + "%USERPROFILE%" + text[found + len(form) :]
            lowered = text.lower()
            found = lowered.find(needle, found + len("%USERPROFILE%"))
    return text
