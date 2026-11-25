# 0304 The caption-window cog owns that window's look

**Decision.** A caption window (a source, or a source column while windows are
joined) owns the settings edited in its cog: the text size for each language
and **Panel: how solid**. It also owns its position and size, which are edited
directly by dragging and resizing rather than by a cog row. The joined shell's
opacity control deliberately changes every visible column; after separation,
each source still keeps the value written to it.

The cog also contains navigation and activity controls: app, timing, language,
preset, transcript, join/separate, stop, and **All caption settings...**. Those
are actions or activity choices, not window-look settings. Always-on-top is an
invariant of caption windows, not a preference. Click-through is the session's
Lock command and remains shared so one invisible interactive window cannot be
left behind.

Window look values are stored under `caption_windows.windows[<source key>]`.
Preset selection never reads or writes them. On upgrade, the effective global
opacity and legacy language sizes are copied into each existing window before
the global forms stop applying, so the first upgraded frame looks unchanged.
