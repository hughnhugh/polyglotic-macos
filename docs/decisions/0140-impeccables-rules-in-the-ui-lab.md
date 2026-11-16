# 0140 Impeccable's design rules, translated for Qt, in the UI lab

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** the founder asked for Impeccable on the website and "this
  framework to the same level ... for the desktop app" (polyglotic-hq
  DECISIONS #163, 2026-11-15); built in polyglotic-hq project 347.

## Situation

Impeccable (pbakaus/impeccable, Apache-2.0) is a design skill for coding
agents with a deterministic detector of 62 rules run on a rendered web page:
contrast, line length, the type scale, corner radii, cramped padding, text
over text, generated-UI tells. It reads HTML and CSS only; Qt widgets have
no DOM and no DevTools port, so its detector can't see our windows. The UI
lab already draws every state offscreen and runs code checks on what each
window draws (`checks.py`: clipped and small text, contrast from the
pixels, names, keyboard reach, scrollbars, squashed layouts).

## Decision

`tools/ui_lab/design.py` asks Impeccable's questions of each window a state
shows, from what it draws (each run of text with its place, size, font and
colour; each rounded shape and its radius) and from its pixels: the type
scale, font families, text over text, targets under 24 px (with WCAG's
spacing exception), more than three accent hues, corner radii off the scale
or too many in one window, near-miss left edges, odd margins above 6 px,
lines over 80 characters, tight leading, capitals, wide tracking, cards in
cards, grey text on colour, cramped controls. Every lab run records its
findings in each state's JSON and `design.md`; the judge's kit includes
them.

**The gate fails on new findings only:** those not in
`tools/ui_lab/design_baseline.json` (state, rule, widget - not the detail,
whose numbers move; digits in a widget's name are ignored), checked in the
English run at 100 % text size where the goldens are. The baseline holds
what the detector found when it came, to be worked down; `python -m
tools.ui_lab design --accept` rewrites it, in a pull request that says why.

No Impeccable code, skill text, hook or `.impeccable/` is in this repo: the
rules are rewritten for Qt here, and the skill's text lives in
polyglotic-hq.

## Why

- The same level as the website: a deterministic pass that catches drift
  before a person looks, so the judge spends its time on what only an eye
  can see (109's principles, hierarchy, the glossary).
- New findings only, as 0136 judges budgets beside main's record: a gate
  that failed on every old finding would be waived wholesale on day one.
- Alternatives not taken: running Impeccable's detector on a rendered
  screenshot (it needs a DOM); a separate CI step (it would draw every
  state twice).

## What would make us reverse it

- The gate fails on findings that aren't problems (a rule too noisy to
  keep), or a rule stops finding anything for months.
- Its time in the lab run grows past what the CI runner can carry.

## How we'd reverse it

Per rule: delete its function and its line in `RULES`, then `design
--accept`. All of it: remove `design.py`, its call in `lab._run_states`,
`design_gate` in `__main__`, the baseline and the test file; nothing else
depends on it.
