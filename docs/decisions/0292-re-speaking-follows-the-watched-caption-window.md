# 0292 Re-speaking follows the watched caption window

2026-11-21. Project 636 revises the default gesture and targeting in decision 0274.

A learner can hear speech that never produces a caption. Looking through caption
history cannot tell which window they want to correct. Clicking a microphone
button also interrupts pointing or selecting. At key-down the app now chooses
the visible captured window under the pointer, then the most recently visited
eligible window, then the first eligible window. A joined column counts as its
own window. The source stays fixed through release and recognition.

F8 works with the existing global hold-key implementation across typing layouts.
Right Alt is AltGr on many layouts, and Scroll Lock can be absent on laptops.
F8 can need Fn on a laptop and is used by Word and the FiveM console. Both
Dictation and Hotkeys let the learner change it or choose the shared gesture.
Existing custom bindings and explicit shared choices survive migration.
Sources checked on 2026-11-21 include [Windows virtual keys](https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes),
[Right Alt on international layouts](https://devblogs.microsoft.com/oldnewthing/20040329-00/?p=40003),
[Scroll Lock availability](https://support.microsoft.com/en-us/excel/turn-off-scroll-lock),
[Lenovo laptop function keys](https://support.lenovo.com/ph/en/documentation/SG10010/Use_hotkeys),
[Word shortcuts](https://support.microsoft.com/en-us/accessibility/word/keyboard-shortcuts-in-word)
and the [FiveM console](https://docs.fivem.net/docs/getting-started/setup-fivem-server/).

The bar shows mic status and level. A sign next to the target names the source.
An empty recognition result can introduce the gesture once per install.
The wire format and audio processing are those of decision 0274.

If preview users report frequent conflicts, revise the default and use the
settings change record to migrate untouched bindings. Window targeting can be
changed independently of gesture recognition or capture.
