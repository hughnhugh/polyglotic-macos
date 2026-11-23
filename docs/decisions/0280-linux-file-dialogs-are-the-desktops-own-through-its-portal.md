# 0280 Linux's file dialogs are the desktop's own, through its portal

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, in polyglotic-hq project 574 (Linux's slice 7),
  from 571's finding; the port itself is the user's (polyglotic-hq
  DECISIONS #243, 2026-11-20)

## Situation

Save transcript and the two exports for Anki ask Qt for a save dialog
(`QFileDialog.getSaveFileName`). Qt draws the OS's own where its platform
theme offers one: Windows' and the Mac's always do. On Linux the theme
comes from a plugin chosen by the desktop (`XDG_CURRENT_DESKTOP`): GTK 3's
on GNOME, Xfce and the like, with GTK's dialog; on KDE Qt's built-in KDE
theme, which has no dialog of its own - KDE's own dialogs come from
plasma-integration's plugin, built against the system's Qt.

571 found `polyglotic.spec` dropping every platform theme plugin
(`platformthemes`) from the package. So the packed app drew Qt's own
widget dialog everywhere - a different, plainer dialog from every other
program's, without the desktop's bookmarks or recent places. Keeping GTK
3's plugin isn't the answer for an AppImage: it loads the system's GTK
into the app beside the app's own copy of GLib (bundled for Qt), and
plasma-integration's can't load into another Qt at all.

## Decision

- **The package keeps Qt's portal theme, and no other:**
  `platformthemes/libqxdgdesktopportal.so` (`polyglotic.spec`'s
  `PLATFORM_THEMES`, Linux only; `tools/package/build.py`'s Linux parts
  require it, so a build without it fails).
- **The app asks for it** before the application is made, on X11
  (`main.use_file_dialogs`, `platform/linux/file_dialogs.py`):
  `QT_QPA_PLATFORMTHEME=xdgdesktopportal`, unless the session already
  names a theme - then as asked.
- The portal theme keeps the desktop's own theme beneath it (Qt's GNOME or
  KDE theme) for everything else, and asks the desktop portal's file
  chooser (`org.freedesktop.portal.FileChooser`) for each dialog: GNOME's
  dialog on GNOME (xdg-desktop-portal-gnome or -gtk), KDE's on KDE
  (xdg-desktop-portal-kde), drawn by the portal's own process. Where no
  portal answers, Qt draws its own dialog, as before.
- **Checked on GitHub's runners** with the packed AppImage on Ubuntu
  24.04's GNOME, Ubuntu's GNOME Shell, Fedora 45's GNOME and KDE Plasma 6
  (`linux-release.yml`, decision 0281): Save transcript's and the Anki
  export's buttons pressed over AT-SPI, each dialog is asked of the portal
  (`SaveFile` on the session bus, with its title), and no Qt dialog opens
  in the app.

## Why

- It's the route Flatpak and Snap apps take, and it works the same on every
  desktop the plan supports - GNOME, KDE, Xfce with its portal - with one
  plugin of Qt's own and nothing of the system's loaded into the app.
- The exports and the transcript share Qt's one call, so one change covers
  all three; nothing in the interface changes.

## What would make us reverse it

- A desktop where the portal's dialog misbehaves (a path the app can't
  write to - the portal hands back the path chosen, and the app writes it
  itself, so a sandboxed document portal path would be one), or where no
  portal runs and learners miss GTK's dialog.
- Qt dropping or renaming its portal theme.

## How we'd reverse it

- Delete `use_file_dialogs` and its call; Qt then picks as before.
- Drop `PLATFORM_THEMES`'s Linux case in the spec and the part in
  `build.py`: the package is as it was.
