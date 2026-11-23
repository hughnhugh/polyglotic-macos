# 0290 Caption bar choices save as they are made

- **Status:** proposed for preview 3b (Polyglotic HQ project 626)
- **Date:** 2026-11-21

The caption bar is for quick changes while listening. Timing and translation
presentation, the window's spoken and translation languages, and Lyrics apply
immediately and are remembered. Save, Save as new preset, and Discard belong
in Settings > Presets. The preset chip shows its name while Settings has
pending edits. Undo remains available after switching away from a draft.
This revises the caption bar portion of decision 0283.

Bar changes to preset fields save only those fields. A draft in Settings is
kept separately from the preset's saved values. Window language choices are
scoped to the source within the preset, with existing window choices as the
fallback. The second language is mapped by first translation language within
the preset, as it was previously app-wide.

Instant is the starting timing in each built-in preset. Explicitly chosen
timings and existing custom presets keep their values. Video keeps its
separate subtitle offers and its existing fallback for a saved Steady choice.

Dictation for others appears beside dictation in Settings > Dictation and is
on by default. The window's mic button holds for that window's eligible source.
The global key holds for the eligible source that spoke last. Its label and
tip follow the configured key and whether a tap is needed.

We would revisit autosave if quick changes frequently overwrite settings a
learner meant to try only once. The bar's signals and the partial save in
`use_presets` keep that policy reversible without changing the Settings draft.
