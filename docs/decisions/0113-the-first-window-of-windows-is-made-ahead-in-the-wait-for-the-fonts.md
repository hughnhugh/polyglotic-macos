# 0113 Windows' first-time work for a first window is done ahead, in the wait for the fonts

- **Status:** accepted (reversible)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 322 (brief: "the first native window ... anything else the profile shows", "nothing new before the first paint" that isn't the start's own). Claude reviews it with the pull request.

## Situation

With real windows the main window's first show took about 125 ms, where a
second show takes about 15 (322's measurements, this PC):

- **It is Windows' first-time work for a window that takes drops.** Qt registers every top-level window for drag and drop (`RegisterDragDrop`); the first time in a process, Windows loads its data-exchange and certificate libraries (dataexchange, twinapi.appcore, cryptnet and others). A tool-tip kind of window, which Qt doesn't register, costs 12 ms.
- **It is paid once a process, by any top-level widget,** shown or not, kept or not: after a hidden widget was given its window and deleted, the main window's show took 25 ms.
- **PySide6 holds the interpreter through it,** like the fonts' read (decision 0112).
- **Since 0112 the interface thread waits** about 170 ms for the fonts' read once the learner's tools are made, doing nothing.

## Decision

- **`platform/windows/qt_calls.py`'s `make_native_window`** calls `QWidget::winId()` straight in `Qt6Widgets.dll` through ctypes, as 0112 calls the fonts' read: on the interface thread, where a widget belongs, but without the interpreter.
- **`ui_next/first_window.py`'s `made_ahead`** makes a plain widget nobody sees, has it given its window that way, and deletes it at once. On Qt's `windows` platform only.
- **`main` does it once the learner's tools are made, before it waits for the fonts** (`tools_then_fonts`): the 0.1 s is spent in what was a wait, and the imports' thread runs through it.
- **Nothing is shown,** and nothing new comes before the first paint: the same work, moved out of the main window's show.
- **A test finds the name in the Qt the app is built with,** as for 0112.

Measured, 10 starts each in turn with real windows, the PC about 40 % busy:

| | Window | Then until a click is answered | Together |
|---|---|---|---|
| main | 785 ms | 237 ms | 1025 ms |
| 0112 alone | 646 ms | 84 ms | 727 ms |
| with this | 553 ms | 61 ms | 618 ms |

The parts: `window_shown` 127 ms to 25; the wait for the fonts 168 ms to 69,
with 122 ms of `first_window` before it. Offscreen, where neither is done:
296, 296 and 290 ms.

## Why

- **Through ctypes and not `widget.winId()`:** measured in the prototype, the PySide call brought the window as early but left a click unanswered 174 ms after the paint (against 66): the imports' thread got nothing meanwhile.
- **A widget made and deleted, not the main window's own:** the main window isn't built yet at that point - its pages need the fonts. And a window made early for the main window itself would have to be made before its size and place are known.
- **Not on another thread:** widgets are the interface thread's. Registering for drops on a plain Windows thread to load the libraries was not tried (proposed as a project; it would overlap with the learner's data instead of the fonts' wait).
- **`showNormal` through ctypes as well** was tried in the prototype: once the first window is made ahead the show is about 25 ms, and letting the interpreter go for it gained nothing clear.

## What would make us reverse it

- The fonts' read no longer waited for (a faster read, or 0112 reversed): the 0.1 s would be the interface thread's own again, and only the interpreter let go would remain as a gain.
- A flash, a taskbar button or a focus change seen on any PC from the hidden widget (none on a private desktop here; Qt doesn't show a widget for `winId`).

## How we'd reverse it

Remove the `made_ahead(...)` line in `main`'s `tools_then_fonts` (one
line): the main window's show does the work again. To remove it all:
`first_window.py`, `qt_calls.make_native_window`, the adapter's field and
the `first_window` part (half an hour).
