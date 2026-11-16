# The judge's loop

How an agent (Claude, or Fable for a deep review) reviews the new
interface (`ui_next`) through the UI lab, fixes what it finds and checks
the fix, without a screen. This is the self-evaluating loop the user asked
for on 2026-11-06 ("look at my screen, run tests and evaluate each UI and
the UX ... and self-iterate"). Project 108 designed it (section 5);
project 119 built the kit. The user's eye stays in two places (below).

## What the lab gives you

`uv run python -m tools.ui_lab judge` runs every state of the new
interface offscreen and writes `build/ui-lab/judge/`:

| File | What it is |
|---|---|
| `judge.md` | Start here. Each surface's states and verdicts, the states 109 draws that the lab lacks, the interface's own words on screen (with any the glossary avoids), the checks' notes (Tab order, exemptions, elided text), and the checklist. |
| `sheets/<surface>.png` | The contact sheet: every state of a surface on one image, labelled with its verdict, scaled down. |
| `<state>.png` | Each state full size. Open one when a detail matters: a sheet halves the text. |
| `annotated/<state>.png` | A state's picture with its findings drawn on it: a numbered box around each one that has a place (the design detector's), and every finding listed under the picture by its number. Only for states with findings. Read it beside `design.md`: the box shows at once whether a finding is the thing you think it is. |
| `findings.md` | The code checks' findings: clipped and small text, contrast, accessible names, keyboard reach, horizontal scrollbars, squashed layouts. |
| `design.md` | The design detector's findings (Impeccable's rules for Qt, `design.py`), by rule; **new** marks one not in the baseline, which fails the gate. The rest are the backlog to work down: fix one, then `design --accept` in the same pull request. |
| `timings.md` | Every timed action against its budget. |
| `goldens.md` | Each picture against its approved golden. |

The code checks, budgets and goldens are already gates in CI. **The judge
looks for what they can't see:**
- 109's principles;
- consistency of spacing and alignment, and hierarchy;
- the glossary's words;
- the states that are missing.

## The loop

1. **Set up.**
   - Work in your own worktree of `polyglotic-desktop` from `origin/main`, then `uv sync`.
   - Offscreen only: no GPU, never the user's screen or audio.
   - Read `polyglotic-hq/projects/109-client-structure-wireframes/PRINCIPLES.md`, its `STRUCTURE.md` for the surfaces you review, and the glossary in `polyglotic-hq/DOMAIN.md`.
2. **Run the kit:** `uv run python -m tools.ui_lab judge`.
3. **Read.**
   - `judge.md` first, then each surface's sheet (the Read tool shows a PNG).
   - Then the state PNGs where the sheet is too small to judge: text, spacing, alignment.
   - Compare states with each other: idle with hovered (does anything move?), default with narrow or minimum, dark with light.
4. **File findings** in your project folder (`polyglotic-hq/projects/NNN-.../findings.md`), one line each:
   - **Line format:** `surface · state(s) · rule · what is wrong · how bad · the fix you propose`.
   - **Rule:** a line of `checklist.md`, such as "109 rule 3" or "hierarchy".
   - **How bad:**
     - **blocker:** breaks a principle the user agreed, such as captions covered or a modal;
     - **should:** an inconsistency a user would notice;
     - **nice:** polish.
   - Quote the state's file name so the finding can be checked.
   - Never quote caption text. The lab's captions are made up, but the habit matters.
5. **Fix,** blockers first, then shoulds:
   - one concern per pull request, in `ui_next` only (`ui`'s dialogs and tray are out of scope);
   - start from ENGINEERING.md's checklist, with a test where the fix is behaviour (a size, a colour, a name) and not only looks.
6. **Re-run.**
   - Run `uv run python -m tools.ui_lab --gate`: the budgets and the checks must pass.
   - Then `uv run python -m tools.ui_lab approve --only <state>...` for the pictures you changed on purpose (names, or patterns such as `ui_next.w4_words_*`; plain `approve` runs every state). Approving never removes a golden; `uv run python -m tools.ui_lab prune` removes those whose state is gone.
   - **Look at every golden you approve** (the state's PNG against `git show HEAD:tools/ui_lab/goldens/<state>.png`). Never approve a picture you haven't looked at.
   - Commit the goldens with the fix. The pull request shows before and after.
7. **Repeat** from step 2 until a full pass files no blocker or should, or you reach your brief's limit (3 passes, or its time). Then report:
   - what you found, fixed, and left;
   - the pull requests;
   - what needs the user.

## What the judge never does

- **Change what the user decides:** the budgets (`perf/budgets.py`), the principles, the glossary, the scope ("Nothing new", DECISIONS.md #50), or a window's structure in STRUCTURE.md. Write it up as a decision for the user, with your recommendation.
- **Weaken a check to pass:**
  - no new waiver in `checks.WAIVERS` without a reason that would convince a reviewer;
  - no tolerance raised in `goldens.ALLOWED` except for a state that animates.
- **Approve goldens on another machine.** They are made on the user's PC, where CI runs; elsewhere every picture differs, and the run says so.
- **Run real windows, the GPU, audio or the screen.** The lab is offscreen. A real-window check, if a fix needs one, is a short run on Windows' platform, closed by itself, with no capture (as projects 112 and 113 did), and only when the brief allows it.
- **Log or write caption text, words looked up, or anything of the user's.**

## What only the user can see

- **The goldens:** a pull request that changes pictures shows them before and after in "Files changed". The user (or Claude, reviewing) looks at that, not at a description of it.
- **One walk with real windows and sound per milestone:**
  - the feel of a drag;
  - fonts on the real monitor at its scaling;
  - a caption window over a real game or video.

  The lab can't see these. Bring the walk's findings back as findings for the next pass.

## Limits of the lab (so you don't over-trust it)

- **Not photographed offscreen:**
  - window opacity and fading;
  - the hidden state;
  - real DPI above 100 %.
- **Contrast** is measured against one stand-in video colour (#4a5a6a). Over a bright video the caption window's panel lightens; judge that by eye.
- **Tab order** is read as Qt's chain walks it. Whether that order makes sense (top to bottom, left to right) is yours to judge, from the checks' notes.
- **Painted controls** (the lookup card's actions) have no accessible names to check. They never take the keyboard, by design.
