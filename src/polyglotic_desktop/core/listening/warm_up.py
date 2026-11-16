"""The server's warm-up notices, and when what they say is over.

protocol.md, `notice`: `models_warming_up` - the speech model (or the
translator with it) is starting, so the first captions may be slow;
`translator_warming_up` - only the translator is, so captions come first
and translations a little later. Home keeps a server notice on its banner
for a while; a warm-up's comes off once the captions show it's over
(polyglotic-hq 145: Home still said "The speech model is starting" after
captions were back).
"""

from polyglotic_desktop.core.listening.captions import CaptionKind, CaptionUpdate

MODELS_WARMING_UP = "models_warming_up"
TRANSLATOR_WARMING_UP = "translator_warming_up"
SERVER_RESTARTING = "server_restarting"
"""The server is restarting: over once the session listens again (Home kept
it two minutes after captions were back - polyglotic-hq 203)."""


def warm_up_over(code: str, update: CaptionUpdate) -> bool:
    """Whether `update` shows the warm-up that `code` announced is over: a
    caption with words, for the speech model; a caption with a translation,
    for the translator. False for any other notice, and for a withdrawal."""
    if update.kind is CaptionKind.WITHDRAWN or not update.clauses:
        return False
    if code == MODELS_WARMING_UP:
        return True
    if code == TRANSLATOR_WARMING_UP:
        return any(clause.translations for clause in update.clauses)
    return False
