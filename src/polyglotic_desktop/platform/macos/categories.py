"""Which category a Mac app is - browser, video, call, game, music or other
- and, for well-known apps, the public name people know it by: Windows'
known-apps list (`platform/windows/categories.py`) by bundle ID instead of
executable name (polyglotic-hq 411).

An app is known by its **bundle ID** (`com.hnc.Discord`), the one name of
it macOS keeps the same in every language - an app's own name is localised.
The public name is what the app picker shows and the only name of an app
that may leave the Mac, only in usage statistics the user agreed to share
(polyglotic-hq DECISIONS.md #30) - so every public name here is one Windows'
list already has, and polyglotic-server's tracking plan lists. Mac-only
apps (Safari, QuickTime Player, FaceTime, IINA, TV) have a category and a
name for the learner's eyes, but no public name until the tracking plan
names them; they leave the Mac only as their category.

Bundle IDs are from knowledge, not checked on a Mac (no Mac on 2026-11-16):
a wrong one is never matched, so the app is "other" with its own name. Add
apps as testers use them. Games not on the list are told by where they're
installed (Steam's and the launchers' folders).
"""

from polyglotic_desktop.ports.capture import CommonApp, SourceCategory

# bundle ID -> (category, the name shown, public: may leave the Mac)
_KNOWN_APPS: dict[str, tuple[SourceCategory, str, bool]] = {
    # browsers
    "com.google.chrome": (SourceCategory.BROWSER, "Google Chrome", True),
    "org.chromium.chromium": (SourceCategory.BROWSER, "Chromium", True),
    "org.mozilla.firefox": (SourceCategory.BROWSER, "Firefox", True),
    "com.microsoft.edgemac": (SourceCategory.BROWSER, "Microsoft Edge", True),
    "com.brave.browser": (SourceCategory.BROWSER, "Brave", True),
    "com.operasoftware.opera": (SourceCategory.BROWSER, "Opera", True),
    "com.vivaldi.vivaldi": (SourceCategory.BROWSER, "Vivaldi", True),
    "company.thebrowser.browser": (SourceCategory.BROWSER, "Arc", True),
    "app.zen-browser.zen": (SourceCategory.BROWSER, "Zen Browser", True),
    "org.mozilla.librewolf": (SourceCategory.BROWSER, "LibreWolf", True),
    "com.apple.safari": (SourceCategory.BROWSER, "Safari", False),
    # video
    "org.videolan.vlc": (SourceCategory.VIDEO, "VLC", True),
    "io.mpv": (SourceCategory.VIDEO, "mpv", True),
    "org.xbmc.kodi": (SourceCategory.VIDEO, "Kodi", True),
    "tv.plex.desktop": (SourceCategory.VIDEO, "Plex", True),
    "com.apple.quicktimeplayerx": (SourceCategory.VIDEO, "QuickTime Player", False),
    "com.colliderli.iina": (SourceCategory.VIDEO, "IINA", False),
    "com.apple.tv": (SourceCategory.VIDEO, "TV", False),
    # calls
    "com.hnc.discord": (SourceCategory.CALL, "Discord", True),
    "us.zoom.xos": (SourceCategory.CALL, "Zoom", True),
    "com.microsoft.teams2": (SourceCategory.CALL, "Microsoft Teams", True),
    "com.microsoft.teams": (SourceCategory.CALL, "Microsoft Teams", True),
    "com.tinyspeck.slackmacgap": (SourceCategory.CALL, "Slack", True),
    "ru.keepcoder.telegram": (SourceCategory.CALL, "Telegram", True),
    "org.telegram.desktop": (SourceCategory.CALL, "Telegram", True),
    "net.whatsapp.whatsapp": (SourceCategory.CALL, "WhatsApp", True),
    "desktop.whatsapp": (SourceCategory.CALL, "WhatsApp", True),
    "org.whispersystems.signal-desktop": (SourceCategory.CALL, "Signal", True),
    "com.skype.skype": (SourceCategory.CALL, "Skype", True),
    "com.tencent.xinwechat": (SourceCategory.CALL, "WeChat", True),
    "jp.naver.line.mac": (SourceCategory.CALL, "LINE", True),
    "com.kakao.kakaotalkmac": (SourceCategory.CALL, "KakaoTalk", True),
    "com.viber.osx": (SourceCategory.CALL, "Viber", True),
    "cisco-systems.spark": (SourceCategory.CALL, "Webex", True),
    "com.teamspeak.teamspeak3": (SourceCategory.CALL, "TeamSpeak 3", True),
    "com.apple.facetime": (SourceCategory.CALL, "FaceTime", False),
    # music
    "com.spotify.client": (SourceCategory.MUSIC, "Spotify", True),
    "com.apple.music": (SourceCategory.MUSIC, "Apple Music", True),
    "com.tidal.desktop": (SourceCategory.MUSIC, "TIDAL", True),
    "com.netease.163music": (SourceCategory.MUSIC, "NetEase Cloud Music", True),
    "com.tencent.qqmusicmac": (SourceCategory.MUSIC, "QQ Music", True),
    # games
    "com.valvesoftware.steam": (SourceCategory.GAME, "Steam", True),
    "com.blizzard.worldofwarcraft": (SourceCategory.GAME, "World of Warcraft", True),
}

ALIASES = {"com.apple.webkit.gpu": "com.apple.Safari"}
"""Processes that play an app's sound from outside its bundle, by bundle
ID: WebKit's media process plays Safari's (and Mail's, rarely) - captured
and listed as Safari, so choosing Safari captures it."""

COMMON_APPS = tuple(
    CommonApp(bundle_id, title)
    for bundle_id, title in (
        # the browsers (as Windows' list: polyglotic-hq 249, F12)
        ("com.apple.Safari", "Safari"),
        ("com.google.Chrome", "Google Chrome"),
        ("org.mozilla.firefox", "Firefox"),
        ("com.microsoft.edgemac", "Microsoft Edge"),
        ("com.brave.Browser", "Brave"),
        # the main apps
        ("com.hnc.Discord", "Discord"),
        ("us.zoom.xos", "Zoom"),
        ("com.microsoft.teams2", "Microsoft Teams"),
        ("com.spotify.client", "Spotify"),
        ("org.videolan.vlc", "VLC"),
        ("com.apple.QuickTimePlayerX", "QuickTime Player"),
    )
)
"""Listed in a caption window's settings before they play, in this order,
by the name an app has once it plays (`PlayingApp.name`: its bundle ID)."""

_GAME_FOLDERS = (
    "/steamapps/common/",
    "/epic games/",
    "/gog games/",
    "/gog galaxy/games/",
)


def _key(bundle_id: str | None) -> str:
    return (bundle_id or "").lower()


def category_of(bundle_id: str | None, path: str | None = None) -> SourceCategory:
    """The category of the app with `bundle_id`, installed at `path` (its
    executable's full path) if known."""
    known = _KNOWN_APPS.get(_key(bundle_id))
    if known is not None:
        return known[0]
    if path and any(folder in path.lower() for folder in _GAME_FOLDERS):
        return SourceCategory.GAME
    return SourceCategory.OTHER


def known_name(bundle_id: str | None) -> str | None:
    """The public name of the app with `bundle_id`, if it's on the
    known-apps list and may leave the Mac; None for any other app."""
    known = _KNOWN_APPS.get(_key(bundle_id))
    return known[1] if known is not None and known[2] else None


def shown_name(bundle_id: str | None) -> str | None:
    """The name the list gives the app with `bundle_id` for the learner's
    eyes (Safari's, though not a public one), or None if it isn't listed."""
    known = _KNOWN_APPS.get(_key(bundle_id))
    return known[1] if known is not None else None


def known_names() -> frozenset[str]:
    """Every public name on the Mac's known-apps list."""
    return frozenset(name for _, name, public in _KNOWN_APPS.values() if public)
