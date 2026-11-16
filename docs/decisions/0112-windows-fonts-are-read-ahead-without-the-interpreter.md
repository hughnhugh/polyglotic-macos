# 0112 Windows' fonts are read ahead of the first window, by a call into Qt that doesn't hold Python's interpreter

- **Status:** accepted (reversible)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 322 (brief: "the font database: don't list every family at start; a warm-up off the interface thread where it truly overlaps; the fallback query ... without changing how any text looks"). Claude reviews it with the pull request.

## Situation

With real windows the start took 0.74-0.91 s at every release since
2026-11-08, and about 0.3 s of it was Qt reading Windows' fonts on the
interface thread (322's measurements, this PC, 340 font families):

- **The list of families, about 0.1 s,** at the first use of the font database. That was `style.use_chinese_behind_every_font`, which lists every family to put the interface's Chinese faces behind each.
- **Every family's faces, about 0.2 s,** the first time a font list needs a fallback. Qt's `QPlatformFontDatabase::fallbacksForFamily` goes through every family and has each one read, whatever the script. The interface's own list (Segoe UI first) asks at Home's first label. 314 took this for the cost of "the first Chinese text"; it is paid once, by the first font list of more than one family, in any script.

Neither can be made smaller from outside Qt: the read is Qt's, of Windows'
fonts, and the answer is kept for the run. They can only be done somewhere
else. But:

- **PySide6 holds the interpreter (the GIL) for the whole of the call.** A Python thread calling `QFontDatabase.families()` left the interface thread about a tenth of its turns (measured: 0.9 thousand loop turns a millisecond against 6.8 thousand beside a sleeping thread). So a warm-up thread through PySide moves nothing.
- **The same holds on the interface thread:** during those 0.3 s the thread importing the connection's libraries got nothing either, which is most of why the window couldn't be clicked for 0.23 s after its paint.

## Decision

- **`platform/windows/qt_calls.py`** calls `QFontDatabase::writingSystems()` straight in Qt's library (the `Qt6Gui.dll` PySide6 has loaded, found by `GetModuleHandle`, never loaded again) through ctypes, by the name MSVC gives it. ctypes lets the interpreter go for the call's length. That one function does both reads and nothing else, and `QFontDatabase` is documented thread-safe.
- **`ui_next/fonts_ahead.py`'s `FontsAhead`** runs it on a thread of its own (`fonts-ahead`, not a daemon) from the moment the QApplication exists, on Qt's `windows` platform only.
- **`main` waits for it** (`fonts_then_language`) once the learner's tools are made, before the first run's first screen or the window: a `join`, which also lets the interpreter go, so the imports' thread uses what is left of the wait.
- **The families are listed after that wait,** when listing them asks nothing more of Windows. Until then the interface's Chinese is behind the fonts the interface names only (`use_interface_language(language, listed=False)`), which needs no look at Windows' fonts. Nothing is measured or drawn in between, so **every text looks as it did**: the same substitutions are in place before the first font is used.
- **Where the call can't be made** (another OS, a Qt without that name, a 32-bit build) nothing is read ahead and Qt reads its fonts when first asked, as before.
- **A test finds the name in the Qt the app is built with** (`tests/ui_next/test_windows_qt_calls.py`), so an update that loses it fails CI instead of quietly giving the 0.3 s back.

Measured, 10 starts each in turn with real windows, the PC about 42 % busy:
the window 753 ms before and 670 ms after; a click answered 232 ms after
the paint before and 64 ms after. Offscreen, where nothing is read ahead:
296 and 286 ms.

## Why

- **A mangled name is fragile-looking, but it is Qt's public ABI:** Qt keeps binary compatibility for the whole of Qt 6, PySide6's version is pinned in `uv.lock`, and the test names the day it breaks.
- **`writingSystems()` and not `families()`:** it has every family read (the 0.2 s), where `families()` only lists them. It takes no arguments and returns a short list of numbers.
- **The list it returns is never freed:** about 150 bytes, once a run. Freeing it would need a second private name (`QArrayData::deallocate`).
- **Not a daemon thread:** it runs inside Qt, which must not be taken down under it. An app that quits within 0.3 s of starting waits for it.
- **Alternatives not taken:**
  - **The Chinese face first in the interface's font list:** it changes how mixed Chinese and Latin text looks, and it doesn't remove the read: any list of two families asks for fallbacks.
  - **Qt's own fallback setting** (`QFontDatabase::setApplicationFallbackFontFamilies`): PySide6 6.12 doesn't offer it, and in Qt's source it adds fallbacks before the platform's without skipping the read.
  - **No font merging** (`QFont.NoFontMerging`): no read, but any character the first face lacks would draw as a box.
  - **A thread through PySide:** measured above; it holds the interpreter.
  - **Listing the families after the first paint:** a family used in between would keep the fallbacks Qt first found for it.

## What would make us reverse it

- A crash or a hang inside the read on some PC (a broken font, a font manager).
- PySide6 letting the interpreter go in such calls by itself, or Qt no longer reading every family for a fallback.

## How we'd reverse it

Pass `None` to `FontsAhead` in `main` (one line): the fonts are then read
when first asked, on the interface thread, and everything else is as it is.
To remove it: `fonts_ahead.py`, `qt_calls.read_fonts`, the adapter's field
and `fonts_then_language`'s wait (an hour).
