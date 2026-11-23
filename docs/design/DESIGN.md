---
name: Polyglotic desktop
description: The main window, the transcript and the lookup card in 091's Margin; caption windows neutral over anything.
colors:
  bg: "#11151d"
  sidebar: "#141922"
  surface: "#181d27"
  surface-2: "#1f2532"
  surface-3: "#232b3a"
  border: "#2a3140"
  text: "#e9ecf1"
  text-dim: "#a3abb9"
  text-faint: "#8c95a5"
  accent: "#e9ecf1"
  accent-hover: "#ffffff"
  accent-text: "#11151d"
  success: "#6fcf97"
  warning: "#f2c14e"
  danger: "#ff8a80"
  focus: "#ff8fbe"
  marker: "#5c2440"
  light-bg: "#f5f6f7"
  light-sidebar: "#eceef2"
  light-surface: "#ffffff"
  light-surface-2: "#eef0f4"
  light-surface-3: "#e1e5ee"
  light-border: "#d8dce3"
  light-text: "#172033"
  light-text-dim: "#4b5568"
  light-text-faint: "#5d6678"
  light-accent: "#172033"
  light-accent-hover: "#2b3753"
  light-accent-text: "#f5f6f7"
  light-success: "#1d6b45"
  light-warning: "#8a5a00"
  light-danger: "#b42318"
  light-focus: "#b0185a"
  light-marker: "#ffa8cc"
typography:
  page-title:
    fontFamily: "Literata, Segoe UI Variable Text, Segoe UI"
    fontSize: "24px"
    fontWeight: 600
  state-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "20px"
    fontWeight: 600
  section:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "17px"
    fontWeight: 600
  brand:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "15px"
    fontWeight: 600
  card-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "14px"
    fontWeight: 600
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI"
    fontSize: "13px"
    fontWeight: 400
  faint:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "12px"
    fontWeight: 400
  section-label:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.6px"
  stat:
    fontFamily: "Segoe UI Variable Text, Segoe UI"
    fontSize: "28px"
    fontWeight: 600
  transcript:
    fontFamily: "Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI"
    fontSize: "16px"
  card-word:
    fontFamily: "Microsoft YaHei UI, Segoe UI Variable Display"
    fontSize: "26px"
rounded:
  hairline: "2px"
  chip-inner: "3px"
  small: "6px"
  control: "8px"
  segmented: "9px"
  chip: "10px"
  card: "12px"
spacing:
  inset: "3px"
  gap: "8px"
  row: "12px"
  page: "16px"
  content-max: "720px"
components:
  button:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-dim}"
    rounded: "{rounded.control}"
    padding: "5px 9px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
  field:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.chip}"
    padding: "3px 8px"
---

# Design System: Polyglotic desktop

The new interface's visual system as built (`ui_next`), in the shape of
Impeccable's `document` (polyglotic-hq 347, 2026-11-15). **The code is the
source:** colours are `ui/theme.py`'s Margin palettes (dark, the default,
and light), sizes and radii are `ui_next/style.py`'s stylesheet at a text
size factor of 1.0 (Windows' 100 % and the app's Smaller; the default,
Normal, is 1.3 since desktop decision 0244). This file names them for people and agents; the UI lab's design
detector holds the code to the type scale and radii (`TYPE_SCALE`,
`RADII` in `tools/ui_lab/design.py`). What the app is for:
[PRODUCT.md](PRODUCT.md); the rules every window follows: 109's
PRINCIPLES.md (polyglotic-hq).

## Overview

Two worlds. **The main window, the transcript and the lookup card** are
091's Margin: ink and paper, quiet greys, one pink (the marker, focus) and
Literata for page titles; a calm notebook a learner visits between
sessions. **The caption windows are neutral** in every theme: white or the
learner's colours on a translucent panel over whatever plays, never the
brand (098). Both are Operate surfaces in Impeccable's terms: scanability,
consistency and the real scene (over a game) outrank expression.

## Colors

Tokens by role (`Palette`): `BG` the window, `SIDEBAR` the rail, `SURFACE`
cards, `SURFACE_2` controls, `SURFACE_3` hover and selection, `BORDER`
hairlines; `TEXT`, `TEXT_DIM` (secondary), `TEXT_FAINT` (notes, counts);
`ACCENT` the primary action (paper in dark, ink in light: buttons are the
text colour); `SUCCESS`, `WARNING`, `DANGER` states, always with words;
`FOCUS` and `MARKER` the pink. Glaze and Signal swap the palette.

### Named Rules
- **One accent per window.** The accent is for the primary action, the
  current choice and state; the lab flags more than three saturated hues.
- **Captions are the learner's.** Their colours are presets the learner
  picks; the brand never tints them.

## Typography

Segoe UI Variable Text for the interface (Windows' own; Chinese in
Microsoft YaHei UI or JhengHei UI by the interface's language), Literata
only for page titles. The scale at a factor of 1.0: 12 (notes, section labels), 13
(body), 14 (card titles), 15 (the brand), 16 (the transcript), 17 (section
buttons), 18 and 26 (the lookup card's word), 20 (state titles), 24 (page
titles), 28 (stats). Every size is multiplied by the text size
(`style.px`) and never drawn under 12 px.

### Named Rules
- **Section labels** are 12 px, semibold, letter-spaced 0.6 px, faint.
- **Wrapped notes** should keep to about 80 characters (the lab's
  `line_length`; today's 720 px content column runs longer: a known gap).

## Layout

The main window: a rail on the left, pages on the right, content at most
720 px wide, a 760 x 520 minimum with no horizontal scrolling (109 rule 9).
Spacing: insets up to 6 px for optical fit, 8 px between related items,
12-16 px between groups and around cards; even values only above 6 px.

## Elevation & Depth

Flat. Cards are `SURFACE` with a 1 px `BORDER`; no shadows in the main
window. The lookup card and the caption windows' popovers float over other
apps with Windows' own shadow.

## Shapes

Radii from the stylesheet: 2 (slider grooves), 3 (scroll handles), 6
(small buttons, list items, segmented buttons), 8 (buttons, fields,
menus, banners), 9 (the segmented frame), 10 (chips, the transcript's
text panel), 12 (cards). Circles and pills by shape (a switch, a slider's
handle).

## Components

### Buttons
Default: `SURFACE_2`, 1 px border, 8 px radius, 6 x 12 padding. Primary
(`kind="primary"`): the accent filled, semibold; at most one per view.
Ghost: no frame, dim text. Small and name kinds for rows.

### Cards
`#Card`: `SURFACE`, 1 px border, 12 px radius. Never a card inside a card.

### Fields
`SURFACE_2`, 1 px border turning `FOCUS` on focus, 8 px radius; a visible
label above or beside each.

### Navigation
The rail's `#NavButton`s: dim text, the current page `SURFACE_3` and
semibold.

### The lookup card
The word large (26 px) in its script's face, pinyin, meanings, then the
actions; never takes the keyboard.

## Do's and Don'ts

### Do:
- Use the palette's roles and the stylesheet's sizes; add to the scale in
  `style.py` (and the detector's `TYPE_SCALE`) before using a new size.
- Keep every target 24 px or spaced from its neighbours.
- Say a state in one line where the learner is looking.

### Don't:
- Colour a caption window with the brand.
- Put a card in a card, or a coloured stripe on one side as decoration.
- Open a modal where an inline line would do.
- Use a font the interface doesn't name (the lab's `font_family`).
