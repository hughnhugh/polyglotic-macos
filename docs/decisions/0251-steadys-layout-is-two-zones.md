# 0251 Steady's layout is two zones: the live lines below, the settled transcript above

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude asked for it to be built on polyglotic-hq
  DECISIONS #230's recommendations (items 3 and 4), reversibly, before the
  user's formal answer (526's brief, Phase 2). The user tries a preview
  build before any release.

## Situation

Steady ([0246](0246-steady-is-word-by-word-and-the-default-quick-preview-retires.md))
shows words one at a time. In the window's one list of captions, each
caption is the unit: it arrives as a block with its translation under each
clause, pushes the others up, and "Mandarin" is printed over every one. A
word-by-word caption there keeps changing height, and the line being read
moves. 526's videos (`zones-*`) showed the alternative the user was asked
about: a few flowing lines being read at the foot of the window, and above
them the transcript, each caption set once.

## Decision

In a paced mode (`CaptionMode.paced`), unless the learner turns it off
(Settings > Timing, `steady_two_zones`), a caption window shows:

- **The live zone** (`ui_next.caption_window.ZoneCanvas`) at its foot: the
  captions that haven't settled, run on as one paragraph in the one
  layout (decision 0132) - line by line, each line's translation under it,
  a space between clauses (`zone_look`). Its last lines only: three while
  one speaker talks, two when two have spoken within a minute
  (`views.zones`). Full ink. A new speaker starts a line.
- **The settled transcript** above (the window's canvas): each caption
  that has left the live zone, laid out again whole with its translation
  below it (`settled_look`: the one layout's "Translation below", unless
  the Lab's New layout is on), dimming over three captions.
- **The handoff is by line:** a caption settles when its last line has
  rolled out of the live zone, never while part of it is still there; or
  after 5 s with nothing new, when the zone empties and the next caption
  starts a paragraph.
- **One view, two canvases.** Both draw the same `CaptionLines`; which
  captions each shows is `Zones.settled`. So keys, marks, the lookup card,
  selection, Say it and copying work in both: the window finds a word
  through `CaptionWindow.placed()`, which is both canvases' captions.
- **The window's rules that come with it** (526's DESIGN.md section 5):
  the language is named when it changes, not over every caption
  (`Labels.language_once`); Chinese, Japanese and Korean are never slanted
  (`fonts.UPRIGHT_SCRIPTS` - in every mode: a computer's slant of them is
  harder to read); karaoke's waiting words are drawn faint (`AHEAD_ALPHA`);
  no slide: the zone steps by the line.

The other modes, and Steady with two zones off, show the one list as
before.

## Why

The line being read stays in one place, at one size; the transcript above
is clean and doesn't change. One view keeps every per-caption feature
working in both zones without a second copy of the window's state.

Not taken: a separate widget with its own view for the live zone (two key
spaces: lookup, selection and marks would each need routing); drawing the
live zone in the same canvas as a region (the canvas's caches and its
scroll are per list; the change would reach every paint path of the
default modes).

## Not done here

- The roll is a step, not an eased slide.
- The transcript's place after a handoff isn't animated.
- A line-length cap for wide windows, and the short-window rules beyond
  "fewer live lines" (DESIGN.md 5.3, Sizes).
- The UI lab has no states for the two zones yet.

## What would make us reverse it

The user preferring the one list after trying the preview build, or real
windows showing the handoff distracts.

## How we'd reverse it

`steady_two_zones`' default to False (one line in `ui.settings`): the
code path is the one the other modes use.
