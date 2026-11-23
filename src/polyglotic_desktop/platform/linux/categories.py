"""Which category a Linux app is - browser, video, call, game, music or other
- and, for well-known apps, the public name people know it by: Windows'
known-apps list (`platform/windows/categories.py`) by the executable's name
on Linux instead (polyglotic-hq 546, 561).

An app is known by its **executable's name** as the sound server reports it
(`application.process.binary`, `PlayingApp.name`): `firefox`, `chrome`,
`Discord`, the same in every language. The public name is what the app
picker shows and the only name of an app that may leave the PC, only in
usage statistics the user agreed to share (polyglotic-hq DECISIONS.md #30) -
so every public name here is one Windows' list already has, which
polyglotic-server's tracking plan lists. Linux-only apps (GNOME's Videos,
Celluloid, Rhythmbox) have a category and a name for the learner's eyes,
but no public name until the tracking plan names them; they leave the PC
only as their category.

The executables' names are from knowledge, not each checked on a desktop
(2026-11-20): a wrong one is never matched, so the app is "other" with its
own name. Add apps as testers use them. Games not on the list are told by
where they're installed (Steam's library, Proton and the launchers'
folders), from the process's own executable.
"""

from polyglotic_desktop.ports.capture import CommonApp, SourceCategory

# executable (lower case) -> (category, the name shown, public: may leave the PC)
_KNOWN_APPS: dict[str, tuple[SourceCategory, str, bool]] = {
    # browsers
    "firefox": (SourceCategory.BROWSER, "Firefox", True),
    "firefox-bin": (SourceCategory.BROWSER, "Firefox", True),
    "firefox-esr": (SourceCategory.BROWSER, "Firefox", True),
    "chrome": (SourceCategory.BROWSER, "Google Chrome", True),
    "google-chrome": (SourceCategory.BROWSER, "Google Chrome", True),
    "chromium": (SourceCategory.BROWSER, "Chromium", True),
    "chromium-browser": (SourceCategory.BROWSER, "Chromium", True),
    "msedge": (SourceCategory.BROWSER, "Microsoft Edge", True),
    "brave": (SourceCategory.BROWSER, "Brave", True),
    "opera": (SourceCategory.BROWSER, "Opera", True),
    "vivaldi-bin": (SourceCategory.BROWSER, "Vivaldi", True),
    "librewolf": (SourceCategory.BROWSER, "LibreWolf", True),
    "waterfox": (SourceCategory.BROWSER, "Waterfox", True),
    "zen": (SourceCategory.BROWSER, "Zen Browser", True),
    "zen-bin": (SourceCategory.BROWSER, "Zen Browser", True),
    "epiphany": (SourceCategory.BROWSER, "GNOME Web", False),
    "falkon": (SourceCategory.BROWSER, "Falkon", False),
    # video
    "vlc": (SourceCategory.VIDEO, "VLC", True),
    "mpv": (SourceCategory.VIDEO, "mpv", True),
    "kodi": (SourceCategory.VIDEO, "Kodi", True),
    "kodi.bin": (SourceCategory.VIDEO, "Kodi", True),
    "plex": (SourceCategory.VIDEO, "Plex", True),
    "totem": (SourceCategory.VIDEO, "Videos", False),
    "celluloid": (SourceCategory.VIDEO, "Celluloid", False),
    "haruna": (SourceCategory.VIDEO, "Haruna", False),
    "smplayer": (SourceCategory.VIDEO, "SMPlayer", False),
    "showtime": (SourceCategory.VIDEO, "Showtime", False),
    # calls
    "discord": (SourceCategory.CALL, "Discord", True),
    "zoom": (SourceCategory.CALL, "Zoom", True),
    "slack": (SourceCategory.CALL, "Slack", True),
    "telegram-desktop": (SourceCategory.CALL, "Telegram", True),
    "telegram": (SourceCategory.CALL, "Telegram", True),
    "signal-desktop": (SourceCategory.CALL, "Signal", True),
    "skypeforlinux": (SourceCategory.CALL, "Skype", True),
    "wechat": (SourceCategory.CALL, "WeChat", True),
    "viber": (SourceCategory.CALL, "Viber", True),
    "mumble": (SourceCategory.CALL, "Mumble", True),
    "ts3client_linux_amd64": (SourceCategory.CALL, "TeamSpeak 3", True),
    "teamspeak": (SourceCategory.CALL, "TeamSpeak", True),
    # music
    "spotify": (SourceCategory.MUSIC, "Spotify", True),
    "netease-cloud-music": (SourceCategory.MUSIC, "NetEase Cloud Music", True),
    "qqmusic": (SourceCategory.MUSIC, "QQ Music", True),
    "rhythmbox": (SourceCategory.MUSIC, "Rhythmbox", False),
    "elisa": (SourceCategory.MUSIC, "Elisa", False),
    "strawberry": (SourceCategory.MUSIC, "Strawberry", False),
    "amberol": (SourceCategory.MUSIC, "Amberol", False),
    # games
    "steam": (SourceCategory.GAME, "Steam", True),
    "steamwebhelper": (SourceCategory.GAME, "Steam", True),
}

COMMON_APPS = tuple(
    CommonApp(executable, title)
    for executable, title in (
        # the browsers (as Windows' list: polyglotic-hq 249, F12)
        ("firefox", "Firefox"),
        ("chrome", "Google Chrome"),
        ("chromium", "Chromium"),
        ("brave", "Brave"),
        # the main apps
        ("Discord", "Discord"),
        ("zoom", "Zoom"),
        ("spotify", "Spotify"),
        ("vlc", "VLC"),
        ("mpv", "mpv"),
    )
)
"""Listed in a caption window's settings before they play, in this order,
by the name an app has once it plays (`PlayingApp.name`: its executable's,
as the sound server reports it - Discord's has a capital)."""

_GAME_FOLDERS = (
    "/steamapps/common/",
    "/steam/compatibilitytools.d/",
    "/games/heroic/",
    "/heroic/",
    "/lutris/",
    "/games/",
)


def _key(executable: str | None) -> str:
    return (executable or "").lower()


def category_of(executable: str | None, path: str | None = None) -> SourceCategory:
    """The category of the app whose executable is `executable`, at `path`
    (its full path, from the process) if known."""
    known = _KNOWN_APPS.get(_key(executable))
    if known is not None:
        return known[0]
    if path and any(folder in path.lower() for folder in _GAME_FOLDERS):
        return SourceCategory.GAME
    return SourceCategory.OTHER


def known_name(executable: str | None) -> str | None:
    """The public name of the app whose executable is `executable`, if it's
    on the known-apps list and may leave the PC; None for any other app."""
    known = _KNOWN_APPS.get(_key(executable))
    return known[1] if known is not None and known[2] else None


def shown_name(executable: str | None) -> str | None:
    """The name the list gives the app for the learner's eyes (GNOME's
    Videos, though not a public one), or None if it isn't listed."""
    known = _KNOWN_APPS.get(_key(executable))
    return known[1] if known is not None else None


def known_names() -> frozenset[str]:
    """Every public name on Linux's known-apps list."""
    return frozenset(name for _, name, public in _KNOWN_APPS.values() if public)
