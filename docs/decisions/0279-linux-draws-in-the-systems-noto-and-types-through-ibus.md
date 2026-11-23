# 0279 Linux draws the interface in the system's Noto faces, and takes typing through IBus

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, in polyglotic-hq project 571 (Linux's slice 4),
  from 546's plan; the port itself is the user's (polyglotic-hq DECISIONS
  #243, 2026-11-20)

## Situation

The interface's font lists name Windows' faces first and each other OS's
after them (`ui_next/fonts.py`'s `also`, polyglotic-hq 179). On Linux two
questions were open (546's plan, 1.7 and the port table):
- **Carry the fonts, or use the system's?** Chinese, Japanese and Korean
  need Noto Sans CJK (or Source Han Sans): 19.5 MB a weight as Ubuntu
  installs it (`NotoSansCJK-Regular.ttc`), about 12.2 MB a weight
  compressed as the AppImage compresses (zstd -19). The AppImage is
  136.3 MB (571's build, 2026-11-20); Regular and Bold would add about
  25 MB (18 %).
- **How Chinese and Japanese are typed into the app's own boxes:** Qt reads
  the desktop's input method through a plugin. PySide6's wheel carries
  IBus's (and compose); Fcitx5, which Kubuntu uses, has a Qt plugin of its
  own that the wheel doesn't carry - built against Qt's private API, it
  only loads into the Qt it was built with.

What 571 found on GitHub's runners (`.github/workflows/linux-typing.yml`,
`tools/linux_fonts_check.py` - every string of all 21 interface languages
laid out in the interface's fonts, the UI lab's own checks asked of each):
- **Ubuntu 24.04's desktop** installs Noto Sans, Noto Sans CJK, DejaVu,
  Liberation and Ubuntu (`ubuntu-desktop-minimal`'s font packages);
  **Fedora 45** (its `fonts` group, in Workstation and the KDE edition)
  Noto Sans, Noto Sans CJK (the variable cut) and the other Noto scripts.
  In both, no language drew a box, Chinese was never in a Japanese face,
  nor a Japanese sentence's kanji in a Chinese one.
- **Before this record** a Japanese interface on Linux drew its kanji in
  Noto Sans CJK SC (China's shapes), the first Chinese face its list
  named: the language's own script's faces were Windows' names only.
- **With DejaVu alone** (a minimal install), every Chinese, Japanese,
  Korean, Thai and Hindi string drew boxes.
- **Typing** (`tools/linux_typing_check.py`: "nihao" and Space pressed
  into Words' search box through the X server, Ubuntu 24.04's IBus 1.5.29
  with libpinyin, and Fcitx5 5.1.7 with its pinyin): 你好 with
  `QT_IM_MODULE=ibus`, through IBus or Fcitx5; and "nihongo", Space and
  Enter with Mozc 2.28, through either: 日本語. But Kubuntu's own
  `QT_IM_MODULE=fcitx`, and a session that names no input method, left
  Qt with compose alone: "nihao ". Naming IBus's plugin after Fcitx's
  (`QT_IM_MODULES="fcitx;ibus"`, Qt 6.7's list) typed 你好 - only while
  `ibus-daemon` was installed: Qt's IBus plugin gives up without it,
  unless asked to use the portal's IBus (`IBUS_USE_PORTAL=1`), which
  Fcitx5 also answers.

## Decision

- **The system's fonts, none carried for the interface.** Linux's lists
  name Noto's families as the distributions do (`fonts.OTHER_OS["linux"]`):
  Noto Sans for Latin and Cyrillic; Noto Sans CJK SC, TC, HK, JP and KR;
  Noto Sans Thai and Devanagari.
- **An interface language's own script's faces on every OS**
  (`style.script_faces`): Windows' names, then this OS's (`fonts.also`) -
  a Japanese interface's kanji in Noto Sans CJK JP (Hiragino Sans on a
  Mac), before the Chinese faces. **The OS's Latin face before them**, as
  Segoe UI is on Windows, so a Japanese or Hindi interface's Latin letters
  aren't in its CJK or Devanagari face's. Windows' lists are unchanged.
- **IBus's input method plugin, compose's and QtDBus are carried and
  checked:** `tools/package/build.py`'s Linux parts, so a build without
  them fails; `tools/package/linux_input_methods.sh` starts the packed app
  with IBus and Qt says it loaded the plugin.
- **Fcitx5 through its IBus frontend:** the app carries no Fcitx plugin.
  Before Qt starts on X11 (`main.use_input_methods`,
  `platform/linux/input_method.py`): Fcitx asked for, IBus's plugin is
  named after it - through the portal where IBus isn't installed; nothing
  asked for, IBus's then compose's where IBus is installed; a list
  already set, or anything else, as asked. With it, Kubuntu's setting and
  no `ibus-daemon` typed 你好 on the runner.

## Why

- The desktops checked install Noto Sans CJK with the desktop (Ubuntu
  24.04's, Fedora 45's; Ubuntu 26.04's and Kubuntu's are assumed from
  their seeds, not checked), so carried faces would be 25 MB more in every
  download and every full update, for nobody on a supported desktop.
- Asking each language for its own script's faces is what Windows already
  does (polyglotic-hq 294); on Linux and the Mac the list simply lacked
  their names.
- Building Fcitx5's Qt plugin against PySide6's exact Qt needs Qt's
  private headers for that version, which the wheel doesn't ship - a
  build of its own to keep in step with every PySide6 update.

## What would make us reverse it

- Learners on a desktop without CJK fonts (a minimal Arch or Debian), or
  testers reporting boxes: carry Noto Sans CJK's Regular, or the app's own
  Noto Sans SC (already carried for captions) behind the interface.
- Fcitx5's IBus frontend failing on a real Kubuntu (checked only on
  Ubuntu's Fcitx5 5.1.7 on a runner), or an `IBUS_USE_PORTAL` session
  where IBus itself runs: carry a Fcitx5 plugin built for PySide6's Qt.
- A session where `ibus-daemon` is installed but not running and the
  learner types with dead keys: IBus's plugin named before compose's would
  take them (not seen; GNOME runs IBus).

## How we'd reverse it

- Carrying a face: its file in `ui/assets/fonts` or a pack, added at start
  as `caption_faces` adds the caption faces, and its family at the end of
  `fonts.OTHER_OS["linux"]`'s lists. A few lines and a bigger AppImage.
- Asking as the session asks: delete `use_input_methods` and its call.
- A Fcitx5 plugin: built in `linux_build.sh` against the wheel's Qt (with
  Qt's private headers for that version, from Qt's own archive), put in
  `platforminputcontexts`, and named in `build.py`'s Linux parts.
