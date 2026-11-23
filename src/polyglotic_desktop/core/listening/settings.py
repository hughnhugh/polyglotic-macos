"""The user's listening settings: what the server needs to caption their speech.

Sent to the server when a listening session opens and whenever they change
(protocol.md, `settings`). Choosing them is the interface's job (D1).

**Each source can have its own target languages** (polyglotic-hq
DECISIONS.md #53, the user, 2026-11-07: each caption window picks its
translation language, or "Original only"): `source_targets`. A source
without its own is translated into `targets` - so today's interface, which
sets `targets` only, sets every source the same, and settings from before
there were per-source languages carry over as they were.

**Each source can have its own spoken language** too (polyglotic-hq
project 248's Q6 A, the user, 2026-11-09: the spoken language moves to each
caption window; the server's decision 0051): `source_spoken`. A source
without its own is heard as `spoken_language`. A server from before
2026-11-09 takes one spoken language for every source, so the session's is
the one language every window names, or Detect when they differ
(`agreed_language`) - the honest fallback, which the window says.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import TYPED_SOURCES, SourceId


@dataclass(frozen=True, slots=True)
class ListeningSettings:
    """`spoken_language`: the language spoken, or None to detect it.
    `targets`: the target languages to translate into (at most two) - every
    source's, unless it has its own. `second_languages`: for a target, the
    language shown for lines already in it (a source's own targets
    included). `spelling_hints`: names and slang the speech model should
    spell the user's way - for recognition only, never logged or stored by
    the server. `translate_live`: translate live updates too, not only
    finished captions. `source_targets`: a source's own target languages,
    by its id; none (an empty tuple) is "Original only" - captioned, not
    translated. `source_spoken`: a source's own spoken language, by its
    id; None is Detect."""

    spoken_language: Language | None = None
    targets: tuple[Language, ...] = ()
    second_languages: Mapping[Language, Language] = field(default_factory=dict)
    spelling_hints: tuple[str, ...] = field(default=(), repr=False)
    translate_live: bool = True
    source_targets: Mapping[SourceId, tuple[Language, ...]] = field(
        default_factory=dict
    )
    source_spoken: Mapping[SourceId, Language | None] = field(default_factory=dict)

    live_translation: bool = False
    """Request separately delivered provisional translations on the listening hello."""

    @property
    def original_only(self) -> bool:
        """A source is captioned without a translation ("Original only"):
        its own languages are none - or no language is chosen at all.
        Dictation's none don't count: it is never translated, nor a
        caption (decision 0073)."""
        own = {s: t for s, t in self.source_targets.items() if s not in TYPED_SOURCES}
        if not self.targets and not own:
            return True
        return any(not languages for languages in own.values())

    def targets_of(self, source: SourceId) -> tuple[Language, ...]:
        """The languages `source`'s speech is translated into: its own, or
        `targets`. Empty: none."""
        return self.source_targets.get(source, self.targets)

    @property
    def all_targets(self) -> tuple[Language, ...]:
        """Every language a source may be translated into, once each:
        `targets`, then each source's own, in that order."""
        own = (t for languages in self.source_targets.values() for t in languages)
        return tuple(dict.fromkeys((*self.targets, *own)))

    def spoken_language_of(self, source: SourceId) -> Language | None:
        """The language `source`'s speech is in: its own, or
        `spoken_language`. None: detect it."""
        if source in self.source_spoken:
            return self.source_spoken[source]
        return self.spoken_language


def agreed_language(spoken: Iterable[Language | None]) -> Language | None:
    """The one spoken language all of `spoken` name; None - Detect - when
    they differ, or there are none. What a server that takes one spoken
    language for every source is sent (the honest fallback)."""
    found = set(spoken)
    return found.pop() if len(found) == 1 else None
