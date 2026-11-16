"""Audio capture and speech detection, one package per operating system.

`windows/` now; `macos/` and `linux/` later. Turns one app's audio, the
whole system's or the mic into speech segments for core, and nothing more:
no caption rules, no network. May use Windows APIs, audio libraries and the
speech-detection model; doesn't import `ui` or `connection` (`main` wires
them).
"""
