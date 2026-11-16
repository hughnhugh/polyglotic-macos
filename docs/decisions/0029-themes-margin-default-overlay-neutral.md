# 0029 Three themes, Margin by default, the overlays neutral

- **Status:** accepted
- **Date:** 2026-11-06
- **Decided by:** the user, 2026-11-06 19:54 ("keep margin as the default
  for now, perhaps the app will have themes they can change it to
  anyway"), in polyglotic-hq project 098's brief; the directions are
  project 091's (its brand page and report).

## Situation

Project 091 drew three visual directions for Polyglotic - **Margin** (ink
on paper, a pink marker; the logo is the dotted "new word" mark),
**Glaze** (celadon and cobalt) and **Signal** (graphite and amber) - and
recommended Margin. The window had one blue palette, dark or light (054),
and a drawn speech-bubble icon. The user picked Margin as the default and
kept the other two as themes the learner can choose.

## Decision

- `ui/theme.py` holds three `Theme`s - Margin, Glaze, Signal - each a light
  and a dark `Palette` mapped onto the fields the stylesheet already used,
  plus `FOCUS` (the focus ring on text inputs) and `MARKER` (a highlighter's
  fill: text selections). ok / warn / bad stay `SUCCESS`, `WARNING`,
  `DANGER`. **Margin is the default** (`AppSettings.theme = "margin"`); the
  learner's light / dark / like-Windows choice (`window_theme`, still dark
  by default) applies within whichever theme.
- Margin's rule: buttons are ink, pink only ever marks.
- Settings has an **Appearance** card: Theme (Margin, Glaze, Signal) and
  Light or dark. The light/dark row moved there from Captions' "This
  window" card, so Captions' "Reset to defaults" no longer resets it.
- Each theme's Latin heading face - Literata, Source Serif 4, Overpass -
  is bundled as one static SemiBold cut to Latin (72-90 KB each), with its
  OFL text, in `ui/assets/fonts`, and used only for page titles
  (`#PageTitle`), falling back to Windows' fonts for anything else.
  Interface text stays on Segoe UI and Microsoft YaHei UI; Chinese never
  uses a bundled face.
- **The overlays don't change:** they read `theme.OVERLAY` - the app's
  first dark palette, unchanged - whatever the theme. The overlay is
  near-black glass with white text over someone's call or game (049, 087).
- **One icon set, from Margin's symbol, whatever the theme:** SVG masters
  in `ui/assets/icons` (a 16-pixel-grid master for 16-32 px, a 64-unit one
  above), drawn at run time with QtSvg (`ui/icons.py`; Qt6Svg is no longer
  dropped from the package). The tray has listening / idle / paused, each
  for a light and a dark taskbar, picked from Windows' own taskbar setting
  (`platform/windows/taskbar.py`). The build writes the .ico (16, 20, 24,
  32, 48, 256) for the exe and Velopack's installer from the same masters.
- Enforced by tests: every text pair at least 4.5:1 and the focus ring at
  least 3:1 in all six palettes, the overlay palette unchanged, the 16 px
  icons on the pixel grid, the tray following the app's state, the .ico's
  six sizes, and the packed app needing the masters, faces and Qt6Svg.

## Why

- Margin brands the learning (the mark under a word), not the captioning;
  091's recommendation, and the user's.
- Keeping all three as themes costs a few palettes and two small fonts, and
  lets the learner choose; the brand stays Margin's (the icon, installer,
  website).
- Mapping onto the existing `Palette` fields left every page's code as it
  was: only the values and a few stylesheet rules changed.
- SVG masters drawn at run time keep one source for the window, tray, exe
  and installer icons; a designer's polish replaces the SVG files and
  nothing else. The alternative - committing rendered PNGs and an .ico -
  needs a check that they stay in step with the masters.
- Static, subset faces rather than variable fonts: 239 KB for all three
  instead of 2.5 MB.

## What would make us reverse it

- The trade-mark search (091's next step) forces a new name or mark: the
  masters and the theme names change, not the structure.
- Learners ignore the theme choice, or a theme confuses support: drop it
  to Margin alone (remove two `Theme`s and the Settings row).
- The overlay needs the brand after all (a test with players says so) -
  that would be a new decision, replacing this one.

## How we'd reverse it

- A palette or face: edit `ui/theme.py` and `ui/assets/fonts`; the
  contrast tests say whether it still reads.
- The icon: replace the SVG masters; the tests check the 16 px grid and
  the tray's colours.
- Removing the theme choice: delete `GLAZE` and `SIGNAL`, the Settings row
  and the `theme` setting (stored values fall back to the default). An
  hour's work.
