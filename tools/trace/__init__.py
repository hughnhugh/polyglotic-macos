"""The caption timelines' viewer: a local page from the app's trace (polyglotic-hq 543, decision 0255).

    uv run python -m tools.trace %APPDATA%\\Polyglotic\\logs
    uv run python -m tools.trace trace.jsonl --out page.html --pictures DIR
    uv run python -m tools.trace %APPDATA%\\Polyglotic\\logs --summary

Reads the app's caption timelines (`perf.trace`): the rolling trace file
(`trace.jsonl*`, on a PC that asked for the detail), the timelines a
problem report's log carries, or - for an app before the trace - the
caption log (`captions.log*`: sent, answered and shown only). Writes one
HTML page: what the stretch says (`perf.trace_summary`: each segment's
percentiles, the hangs and their causes, bursts, drops, and the stretches
of sound without speech - polyglotic-hq 549), an overview, and
a close-up of each of the worst hangs - every update a bar from the sound
to the screen, coloured by segment, and the moments the screen changed.
`--pictures` also writes those close-ups as PNGs (Qt's SVG renderer,
offscreen: the page's own drawing, never the screen). `--summary` prints
one line and the numbers as JSON, for a daily summary.

Times, counts and fixed words only: the trace holds nothing else.
"""
