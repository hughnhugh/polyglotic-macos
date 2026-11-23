"""Word classes shared by the caption protocol and dictionary packs."""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum


class WordClass(StrEnum):
    # Definition order is the bit order in the format-1 pack extension.
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PARTICLE = "particle"
    NUMBER = "number"


type SenseClasses = tuple[WordClass, ...] | None
"""None means pending. The empty tuple means reviewed outside the taxonomy."""


@dataclass(frozen=True)
class WordClassEvidence:
    """The union of the classes of a unit whose eligible senses are all reviewed."""

    allowed: frozenset[WordClass]
    outside: bool

    def resolve(self, server: WordClass | None) -> WordClass | None:
        if server in self.allowed:
            return server
        if not self.outside and len(self.allowed) == 1:
            return next(iter(self.allowed))
        return None


type ClassSpan = tuple[int, int]
type ClassEvidenceFor = Callable[
    [str, str, Collection[ClassSpan]], Mapping[ClassSpan, WordClassEvidence]
]
