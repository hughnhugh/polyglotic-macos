"""Talks to the server, as polyglotic-server's docs/protocol.md describes.

Owns the WebSocket per listening session, the hello / welcome handshake,
speech frames out, caption updates in, the `learning` and `usage` messages
(usage only with the user's consent), reconnecting, and the small on-disk
buffer for events while offline. Turns protocol messages into calls on
core and back; no caption rules here. Doesn't import `ui` or `platform`.
"""
