"""Listening: speech turned into captions - the product's heart.

Owns, on the PC: sources (an app, the whole system, the mic), caption
display state (live updates replaced in place, finished captions,
withdrawn captions, joined captions), caption history, and - in protocol
version 1 - the live-update timing rules: live updates every N seconds in
6s live sections, the finished pass at a 0.8s pause, 20s long-speech
splits, 2s joins. The timing rules are a pure state machine with no I/O,
so they can move to the server in version 2 (decision 0003 in
polyglotic-server).

Also summarises per-caption detail once per listening session (caption
delay, rewrite rate, dropped captions); that detail never leaves the app.
"""
