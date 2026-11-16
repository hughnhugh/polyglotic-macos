"""What each surface of the new interface shows, as plain Python - no Qt
(import-linter `views-no-qt`, decision 0031).

A view holds core's state as a surface shows it (one app's captions as
lines in the chosen language, the text size, where it's scrolled to) and
takes the user's actions; a Qt widget draws it. Tested without Qt. The
rules stay in core (`core.listening.display` for what a caption's rows
say); a view only applies them.
"""
