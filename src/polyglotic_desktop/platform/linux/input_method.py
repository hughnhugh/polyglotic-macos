"""Which of Qt's input method plugins the app asks for on Linux, so Chinese,
Japanese and Korean can be typed into its own boxes (polyglotic-hq 571;
decision 0279).

The app carries Qt's IBus plugin and compose's, not Fcitx's: Fcitx5's own
Qt plugin is built against Qt's private API and loads only into the Qt it
was built with. Fcitx5 answers IBus's clients too, through its IBus
frontend - on IBus's own bus where IBus is installed, and as the portal's
IBus (`org.freedesktop.portal.IBus`) where it isn't. Qt 6.7 and later take
a list of plugins to try in turn (`QT_IM_MODULES`). So, set before the
application is made:
- **a list already set** is the learner's or the desktop's: left alone;
- **Fcitx asked for** (`QT_IM_MODULE=fcitx`, as Kubuntu sets it): Fcitx's,
  then IBus's - through the portal where IBus isn't installed, since Qt's
  IBus plugin otherwise gives up when there's no `ibus-daemon` to start;
- **nothing asked for** (a session that names no input method): IBus's
  where IBus is installed - GNOME runs it - then compose's, Qt's own
  default. Without this the app had compose alone, and pinyin typed
  "nihao" (571's runs);
- **anything else** (`ibus`, `xim`, `none`): as asked.
"""

import os
import shutil
from collections.abc import Callable, Mapping, MutableMapping

FCITX = frozenset({"fcitx", "fcitx5"})


def plugins_to_try(environ: Mapping[str, str], ibus_installed: bool) -> dict[str, str]:
    """What to add to the environment before Qt starts (nothing: as asked)."""
    if environ.get("QT_IM_MODULES", "").strip():
        return {}
    asked = environ.get("QT_IM_MODULE", "").strip()
    if asked.lower() in FCITX:
        found = {"QT_IM_MODULES": f"{asked};ibus"}
        if not ibus_installed:
            found["IBUS_USE_PORTAL"] = "1"
        return found
    if not asked and ibus_installed:
        return {"QT_IM_MODULES": "ibus;compose"}
    return {}


def use_carried_plugins(
    environ: MutableMapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, str]:
    """`plugins_to_try`, put in the environment (the process's unless one is
    given); what was added, for the log."""
    env = os.environ if environ is None else environ
    found = plugins_to_try(env, which("ibus-daemon") is not None)
    env.update(found)
    return found
