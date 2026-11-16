"""What the new interface (`ui_next`) stands on that isn't one window's
(decision 0032): the app behind the windows (`app.DesktopApp`: the
commands, the session's state, the tray, the caption feed, "Looks
wrong?"), the settings file's shape, the window theme, the icons,
Learning's tools, the apps with sound, and today's dialogs - first-run
language, level, consent, sign in and out, deleting learning data,
feedback, the comparison card.

Shows what core decides and passes the user's actions to core. No domain
rules here. Doesn't import `platform`, `connection` or `ui_next` (`main`
wires them). Moves into `ui_next` - renamed `ui` - once the UI judge's
fixes have landed (decision 0032).
"""
