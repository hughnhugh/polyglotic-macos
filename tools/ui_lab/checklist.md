# The checklist

For each surface: look at its sheet, then at any state's own PNG where a
detail matters, and answer each line. The code checks have already
looked for clipped and small text, contrast, names, keyboard reach,
horizontal scrollbars and squashed layouts (findings.md): don't redo
them; look for what they can't see.

The rules are project 109's (polyglotic-hq
`projects/109-client-structure-wireframes/PRINCIPLES.md` and
`STRUCTURE.md`) and the glossary (polyglotic-hq `DOMAIN.md`).

## What the client is for (109, in order)

1. **The captions are readable and never in the way.** Can the newest
   caption be read at a glance, over the stand-in video? Does anything
   cover it - a strip, a notice, a pill, the card?
2. **Every action is instant.** Is anything over its budget (timings.md)?
   Does any state show a spinner or a "loading" where 109 has none?
3. **One obvious place for everything.** Does each setting show once,
   with one wording? Does a shortcut open the same control rather than a
   copy?
4. **Honest and quiet.** Is a state (paused, reconnecting, the limit) one
   line where the learner is looking - never a modal, never over a game?
5. **Nothing new.** Is anything shown that today's app doesn't do
   (DECISIONS.md #50: rebuild what exists, add nothing)?

## The rules every window follows (109's cleanness rules)

1. **Resize:** at the minimum size (a `narrow` or `minimum` state), does
   everything still fit and read in order?
2. **Text size:** does the window keep its size and the newest caption
   stay where the eye is?
3. **Nothing moves on hover:** comparing idle with hovered, does anything
   shift? Controls drawn over the content, in a reserved band?
4. **One place for each setting** (the owner table in STRUCTURE.md 1.1).
5. **Per-window things on the window; session things on Home and the
   rail** - is anything in the wrong place?
6. **Plain words from the glossary** - see "The interface's words here"
   and "Words the glossary avoids" for each surface.
7. **Positions are presets or "where I put it"**; "Reset position" one
   click away.
8. **A limit is shown plainly, before it is hit** ("3 of 3 apps").
9. **The main window:** 760 x 520 minimum with no horizontal scrolling;
   content at most 720 px wide; nothing in a card at a fixed width.
10. **Reachable by keyboard and named** (the checks' Tab order notes:
    does the order read top to bottom, left to right?).
11. **Caption windows stay neutral in every theme**; Margin, Glaze and
    Signal colour the main window, the transcripts and the lookup.

## Impeccable's lenses (polyglotic-hq 347)

The design detector (`design.md`) has measured the type scale, fonts, radii,
targets, alignment, line length and colour count: read its findings, don't
redo them. Then judge what it can't, in Impeccable's words:

- **audit:** accessibility (contrast, names, keyboard, targets), the text
  sizes and window sizes, theming (dark and light where themed), and
  implementation integrity - is this window built from the interface's own
  parts and tokens, or one-offs?
- **critique:** hierarchy, clarity, cognitive load (more than four choices
  at one decision point?), emotional fit (reassurance where a learner
  worries: data, paying, deleting), and Nielsen's ten heuristics, 0-4 each.
- **polish:** states (hover, disabled, loading, error, empty), consistent
  affordances (the same button looks the same everywhere), alignment and
  spacing rhythm (tight groups, generous separation, more space above a
  heading than below it).
- **quieter / distill:** one accent per window; colour only for the primary
  action, the current choice and state; no decoration that carries no
  state; nothing a learner must read twice.
- **clarify:** controls name their action; notices name the problem and
  the way out, in the glossary's words.
- **Bans (Impeccable's, kept here):** a card inside a card; a coloured side
  stripe as decoration; a small capitals label above a heading inside
  content; a modal where an inline line would do; an emoji standing in for an
  icon (the icons are Segoe Fluent Icons).

## Consistency of spacing and alignment

- Do the same things have the same padding, gaps and corner radii across
  states and across surfaces (rows, chips, buttons, cards)?
- Do left edges line up: titles, notes, buttons, ticked choices?
- Are icons and text on a row centred on the same line?
- Is the space between groups larger than the space inside them?

## Hierarchy

- Is the most important thing in each state the most prominent (the
  newest caption; the word on a card; the state line on Home)?
- At most one primary (accent-filled) action per view?
- Are secondary things (notes, counts, hints) dimmer and smaller, but
  still readable?

## The glossary's words

- Every word on screen is the glossary's: caption, original,
  translation, finished caption, live update, Steady, lookup, deck, saved
  word, category, known, source, "You", "Everything the PC plays",
  locked, Back to live, caption window (not "overlay"), app, Original
  only, Show my speech here, lookup card, transcript.
- Sentence case, no jargon (no "segment", "final", "VAD", "token"), no
  blame ("error", "failed") where plain words do.

## States covered

- Does each surface have the states 109 draws ("States 109 draws" under
  each surface)? Which missing ones matter, and could the lab draw them
  offscreen? (Fading and hidden can't be photographed offscreen: say so,
  don't count them.)
- Are the edge cases there: empty, 1,000 lines, the minimum size, a long
  app name, Original only, light and dark (where themed)?
