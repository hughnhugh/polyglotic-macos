"""Languages for the settings file: the languages not offered as targets.
Names and the languages to pick are the new interface's
(`ui_next.languages`).

No line says which spoken languages are captioned less accurately
(DECISIONS.md #23's note): the user asked it gone, 2026-11-13 ("Remove the
line ... in the detect-language section and anywhere else").
"""

# polyglotic-hq DECISIONS.md #40 (2026-11-06; projects 082, 084): the
# translator writes these in a script most of their speakers don't read -
# Mongolian in the traditional script, Kazakh in Arabic script - so they
# aren't offered, and the server refuses them. Back among `ui_next.languages`'
# names when a model passes.
NOT_OFFERED = ("mn", "kk")
