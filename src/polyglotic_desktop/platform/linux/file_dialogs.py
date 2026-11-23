"""The desktop's own file dialogs on Linux (polyglotic-hq 574; decision
0280): Save transcript and the export for Anki open GNOME's dialog on GNOME
and KDE's on KDE, through the desktop portal's file chooser
(`org.freedesktop.portal.FileChooser`), which the portal's own process
draws.

The packed app can't load a desktop's own Qt theme: KDE's
(plasma-integration) is built against the system's Qt, and Qt's GTK 3
theme would load the system's GTK into the app beside the app's own GLib.
So it carries one of Qt's platform themes, the portal's
(`platformthemes/libqxdgdesktopportal.so`, kept by `polyglotic.spec`), and
asks for it before the application is made:
- **a theme already asked for** (`QT_QPA_PLATFORMTHEME`) is the learner's
  or the desktop's: left alone;
- **otherwise the portal's.** It keeps the desktop's own theme beneath it
  (Qt's GNOME or KDE theme, by `XDG_CURRENT_DESKTOP`) for everything but the
  dialogs; where no portal answers, Qt draws its own dialog, as before.

Without it, Qt picked GTK 3's theme on GNOME (dropped from the package: so
Qt's own dialog) and its KDE theme on KDE, which has no dialogs of its own.
"""

import os
from collections.abc import Mapping, MutableMapping

PORTAL = "xdgdesktopportal"
"""Qt's name for the portal's platform theme."""


def theme_to_use(environ: Mapping[str, str]) -> dict[str, str]:
    """What to add to the environment before Qt starts (nothing: as asked)."""
    if environ.get("QT_QPA_PLATFORMTHEME", "").strip():
        return {}
    return {"QT_QPA_PLATFORMTHEME": PORTAL}


def use_portal_dialogs(
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """`theme_to_use`, put in the environment (the process's unless one is
    given); what was added, for the log."""
    env = os.environ if environ is None else environ
    found = theme_to_use(env)
    env.update(found)
    return found
