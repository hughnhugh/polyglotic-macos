"""Which category a Windows app is - browser, video, call, game, music or
other - and, for well-known apps, the public name people know it by.

The known-apps list: common call, browser, video, music and game apps, by
their executable's name, each with its category and its public name
(`Discord` for Discord.exe). The public name is what the app picker and a
source's label show; it is also the only name of an app that may leave the
PC, and only in usage statistics the user agreed to share (polyglotic-hq
DECISIONS.md #30, the user, 2026-11-05). An app not on the list leaves the
PC only as its category. Games not on the list are told by where they're
installed (store and launcher folders), since there are too many to list.
A guess, kept small: add apps as testers use them - only apps used widely
enough that their name says nothing private.
"""

from pathlib import PureWindowsPath

from polyglotic_desktop.ports.capture import CommonApp, SourceCategory

_KNOWN_APPS: dict[SourceCategory, dict[str, str]] = {
    SourceCategory.BROWSER: {
        "arc.exe": "Arc",
        "brave.exe": "Brave",
        "chrome.exe": "Google Chrome",
        "chromium.exe": "Chromium",
        "firefox.exe": "Firefox",
        "iexplore.exe": "Internet Explorer",
        "librewolf.exe": "LibreWolf",
        "msedge.exe": "Microsoft Edge",
        "opera.exe": "Opera",
        "vivaldi.exe": "Vivaldi",
        "waterfox.exe": "Waterfox",
        "zen.exe": "Zen Browser",
    },
    SourceCategory.VIDEO: {
        "kodi.exe": "Kodi",
        "microsoft.media.player.exe": "Media Player",
        "mpc-be64.exe": "MPC-BE",
        "mpc-hc.exe": "MPC-HC",
        "mpc-hc64.exe": "MPC-HC",
        "mpv.exe": "mpv",
        "plex.exe": "Plex",
        "potplayermini.exe": "PotPlayer",
        "potplayermini64.exe": "PotPlayer",
        "video.ui.exe": "Movies & TV",
        "vlc.exe": "VLC",
        "wmplayer.exe": "Windows Media Player",
    },
    SourceCategory.CALL: {
        "discord.exe": "Discord",
        "kakaotalk.exe": "KakaoTalk",
        "line.exe": "LINE",
        "ms-teams.exe": "Microsoft Teams",
        "mumble.exe": "Mumble",
        "qq.exe": "QQ",
        "signal.exe": "Signal",
        "skype.exe": "Skype",
        "slack.exe": "Slack",
        "teams.exe": "Microsoft Teams",
        "telegram.exe": "Telegram",
        "ts3client_win64.exe": "TeamSpeak 3",
        "teamspeak.exe": "TeamSpeak",
        "viber.exe": "Viber",
        "webexhost.exe": "Webex",
        "wechat.exe": "WeChat",
        "weixin.exe": "WeChat",
        "whatsapp.exe": "WhatsApp",
        "zoom.exe": "Zoom",
    },
    SourceCategory.MUSIC: {
        "aimp.exe": "AIMP",
        "applemusic.exe": "Apple Music",
        "cloudmusic.exe": "NetEase Cloud Music",
        "deezer.exe": "Deezer",
        "foobar2000.exe": "foobar2000",
        "itunes.exe": "iTunes",
        "kugou.exe": "KuGou",
        "musicbee.exe": "MusicBee",
        "qqmusic.exe": "QQ Music",
        "spotify.exe": "Spotify",
        "tidal.exe": "TIDAL",
    },
    SourceCategory.GAME: {
        "cs2.exe": "Counter-Strike 2",
        "dota2.exe": "Dota 2",
        "eldenring.exe": "Elden Ring",
        "ffxiv_dx11.exe": "Final Fantasy XIV",
        "fortniteclient-win64-shipping.exe": "Fortnite",
        "genshinimpact.exe": "Genshin Impact",
        "gta5.exe": "Grand Theft Auto V",
        "league of legends.exe": "League of Legends",
        "minecraft.windows.exe": "Minecraft",
        "overwatch.exe": "Overwatch 2",
        "r5apex.exe": "Apex Legends",
        "robloxplayerbeta.exe": "Roblox",
        "rocketleague.exe": "Rocket League",
        "starrail.exe": "Honkai: Star Rail",
        "steam.exe": "Steam",
        "tslgame.exe": "PUBG: Battlegrounds",
        "valorant-win64-shipping.exe": "Valorant",
        "wow.exe": "World of Warcraft",
        "yuanshen.exe": "Genshin Impact",
    },
}
COMMON_APPS = tuple(
    CommonApp(exe, title)
    for exe, title in (
        # the browsers (the user's rehearsal feedback F12, polyglotic-hq 249)
        ("msedge.exe", "Microsoft Edge"),
        ("chrome.exe", "Google Chrome"),
        ("firefox.exe", "Firefox"),
        ("brave.exe", "Brave"),
        ("opera.exe", "Opera"),
        # the main apps
        ("discord.exe", "Discord"),
        ("zoom.exe", "Zoom"),
        ("ms-teams.exe", "Microsoft Teams"),
        ("spotify.exe", "Spotify"),
        ("vlc.exe", "VLC"),
        ("microsoft.media.player.exe", "Media Player"),
        # Netflix's and Disney+'s Windows apps: names not yet seen on a PC
        # with them (249) - a wrong one is never matched, so never listed
        # twice; check them, and add them to the known apps once seen
        ("netflix.exe", "Netflix"),
        ("disneyplus.exe", "Disney+"),
    )
)
"""Listed in a caption window's settings before they play, in this order
(`views.app_choices`). Games aren't: a game plays its own sound, not its
launcher's, and shows up once it plays."""

_KNOWN = {
    exe: (category, name)
    for category, apps in _KNOWN_APPS.items()
    for exe, name in apps.items()
}

_GAME_FOLDERS = (
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\gog games\\",
    "\\gog galaxy\\games\\",
    "\\riot games\\",
    "\\xboxgames\\",
    "\\ea games\\",
    "\\ubisoft game launcher\\games\\",
)


def _key(executable: str) -> str:
    return PureWindowsPath(executable).name.lower()


def category_of(executable: str, path: str | None = None) -> SourceCategory:
    """The category of the app run from `executable` (its file name),
    installed at `path` (its full path) if known."""
    known = _KNOWN.get(_key(executable))
    if known is not None:
        return known[0]
    if path and any(folder in path.lower() for folder in _GAME_FOLDERS):
        return SourceCategory.GAME
    return SourceCategory.OTHER


def known_name(executable: str) -> str | None:
    """The public name of the app run from `executable`, if it's on the
    known-apps list; None for any other app, whose name never leaves the
    PC."""
    known = _KNOWN.get(_key(executable))
    return known[1] if known is not None else None


def known_names() -> frozenset[str]:
    """Every public name on the known-apps list."""
    return frozenset(name for _, name in _KNOWN.values())
