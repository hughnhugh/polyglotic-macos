"""The UI lab: drives the interface through its states offscreen and
writes, for each state, a PNG and a timing JSON (decision 0031; polyglotic-hq
project 108's design, built from its `tour.py` in project 110).

    uv run python -m tools.ui_lab --out build/ui-lab            # every state
    uv run python -m tools.ui_lab --out build/ui-lab --gate     # and fail on a new part over budget
    uv run python -m tools.ui_lab approve                       # new goldens
    uv run python -m tools.ui_lab approve --only ui_next.w4_*   # only these states'
    uv run python -m tools.ui_lab prune                         # goldens whose state is gone
    uv run python -m tools.ui_lab judge                         # the judge's kit

- **The new parts** (`ui_next`, `new_parts.py`) are held to their budgets
  (`perf.budgets`): with `--gate`, a timed action whose median is over its
  budget, or any one run over the slot budget (50 ms), fails the run - CI's
  "UI lab" job.
- **The code checks** (`checks.py`) look at every window a state shows:
  clipped text, text under 12 px, a character drawn as a box, Chinese in
  a Japanese face, contrast, accessible names, keyboard reach, horizontal
  scrollbars, squashed layouts. With `--gate`, any
  finding on a new part fails the run, unless `checks.WAIVERS` accepts it
  with a reason.
- **The design detector** (`design.py`, decision 0140): Impeccable's
  design rules translated for Qt - the type scale, font families, text
  over text, target sizes, accent hues, corner radii, near-miss alignment,
  the spacing grid, line length, leading, capitals, tracking, cards in
  cards, grey on colour, cramped controls - on what each window draws and
  its pixels. With `--gate` (English, 100 %), a finding not in
  `design_baseline.json` fails the run; `design` writes `design.md` and
  `design --accept` rewrites the baseline.
- **The golden images** (`goldens.py`, `goldens/`): each new part's
  picture against the one approved for it. With `--gate`, an unapproved
  difference fails the run; `approve` makes the new pictures the goldens
  (`--only` some states; it never removes one: `prune` does, 258),
  and the pull request that commits them shows before and after. A new
  part that fails anything has its picture (and golden and diff) copied to
  `failed/`, which is all CI keeps of the pictures.
- **The judge's kit** (`judge.py`, `checklist.md`): `judge` runs the new
  parts and writes a contact sheet per surface, the findings, timings and
  goldens, and a checklist from 109's principles, for an agent to review
  the interface, fix and re-run - the loop is in `JUDGE.md`.
- **Today's interface** was recorded beside the new parts until the
  switch-over (decision 0032) removed it; a state can still be recorded
  without being gated (`State(gated=False)`).

Each state's JSON has its timed actions (median, p90, max, the budget),
the named spans recorded while it ran (`perf.spans`), the checks' findings
and notes, and the interface's own words on screen; `summary.json` and
`summary.md` hold every state. Offscreen, with Windows' fonts when there,
as the app has them on Windows (`QT_QPA_FONTDIR`, `lab.use_windows_fonts`:
Segoe UI for what names no font, the font collections, Chinese a font list
has no face for in MS UI Gothic); no GPU, no screen, no audio, nothing of the user's -
settings in memory, the made-up recorded conversation.
"""
