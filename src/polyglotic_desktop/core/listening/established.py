"""Established text: the start of a live caption the server says is final
(desktop decision 0228; polyglotic-server decision 0095, polyglotic-hq 494).

A live `caption_update` may say how much of the caption's start two live
updates in a row agreed on (`established`, protocol.md): on live's speech
model the finished caption changes 2.6 % of such text, against 13-18 % of
a live update's last word (polyglotic-hq 487). So the app shows it as final
before the caption is finished:

- **Drawn as final:** the established part of a live caption is drawn as a
  finished caption is - full ink, where the rest of the line is drawn as
  text still being spoken (Live updates' a little dim; Steady's and Quick
  preview's provisional line dim and italic). A clause established to its
  end has its translation drawn as final too.
- **A quiet correction:** when an update - the finished caption, or a live
  update the speech model heard differently - changes words that were
  shown as established, the words that took their place are recoloured for
  a moment (`CORRECTION_SEC`), then drawn as usual. The newer hearing wins,
  as for any update: established text is not held against it (when a
  later live update disagreed with established text, the finished caption
  sided with it 53 times in 64 on 487's conversation trace - polyglotic-hq
  494). Words the learner's settled text keeps (`settling`) never change,
  so they are never corrected.
- **Counting:** characters (code points) of the clauses' originals counted
  in order, as if joined with nothing between them - the protocol's count,
  whatever this app puts between clauses when it shows them.

Holds caption text: never log it.
"""

from collections.abc import Sequence
from difflib import SequenceMatcher

from polyglotic_desktop.core.listening.captions import Clause

CORRECTION_SEC = 1.5
"""How long a quiet correction's words keep their colour: long enough to
catch from the corner of an eye, short enough not to call for reading
again (487's mock-up faded it over 1.2 s)."""

Span = tuple[int, int]
"""Characters `[start, end)` of the clauses' originals counted in order."""


def said(clauses: Sequence[Clause]) -> str:
    """The clauses' originals end to end, nothing between: what the counts
    here count."""
    return "".join(clause.original for clause in clauses)


def _word_char(char: str) -> bool:
    """A character inside a spaced word: letters and digits of a writing
    that spaces its words (a Chinese or Japanese character is a word of
    its own)."""
    return char.isalnum() and not ("⺀" <= char <= "鿿" or "가" <= char <= "힯")


def _words_of(text: str) -> str:
    """`text`'s letters and digits in lower case: what a correction compares
    (the server's agreement sets punctuation and letter case aside too)."""
    return "".join(char.lower() for char in text if char.isalnum())


def _not_inside_a_word(text: str, end: int) -> int:
    """`end`, moved back to the start of the word it falls inside, if any."""
    while 0 < end < len(text) and _word_char(text[end - 1]) and _word_char(text[end]):
        end -= 1
    return end


def kept_established(
    update: Sequence[Clause], established: int, shown: Sequence[Clause]
) -> int:
    """How much of `shown` - the update's clauses as the caption now shows
    them, its settled text kept - is established, given the update's
    `established` count: all of it where the two start alike, else as far
    as they do, never ending inside a word."""
    heard, now = said(update), said(shown)
    count = max(0, min(established, len(heard), len(now)))
    if now[:count] == heard[:count]:
        return count
    same = 0
    while same < count and now[same] == heard[same]:
        same += 1
    return _not_inside_a_word(now, same)


def corrected(
    before: Sequence[Clause], established: int, after: Sequence[Clause]
) -> tuple[Span, ...]:
    """Where `after` changed the words `before` showed as established (its
    first `established` characters): the words that took their place, whole
    words, in `after`'s count. None when it kept them all."""
    old, new = said(before)[: max(0, established)], said(after)
    if not old or new.startswith(old):
        return ()
    spans: list[Span] = []
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    for kind, i1, i2, j1, j2 in matcher.get_opcodes():
        if kind == "equal" or i1 >= len(old) or j1 == j2:
            continue  # kept, past what was established, or words only dropped
        if _words_of(old[i1:i2]) == _words_of(new[j1:j2]):
            continue  # punctuation, spacing or letter case only: the same words
        start, end = j1, j2
        while start > 0 and _word_char(new[start - 1]) and _word_char(new[start]):
            start -= 1
        while end < len(new) and _word_char(new[end - 1]) and _word_char(new[end]):
            end += 1
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((start, end))
    return tuple(spans)


def per_clause(clauses: Sequence[Clause], count: int) -> tuple[int, ...]:
    """How many characters at the start of each clause's original lie in
    the first `count` of the clauses' text."""
    out = []
    start = 0
    for clause in clauses:
        length = len(clause.original)
        out.append(max(0, min(length, count - start)))
        start += length
    return tuple(out)


def spans_per_clause(
    clauses: Sequence[Clause], spans: Sequence[Span]
) -> tuple[tuple[Span, ...], ...]:
    """`spans` of the clauses' text, clause by clause, each in its own
    original's count."""
    out = []
    start = 0
    for clause in clauses:
        end = start + len(clause.original)
        out.append(
            tuple(
                (max(a, start) - start, min(b, end) - start)
                for a, b in spans
                if a < end and b > start
            )
        )
        start = end
    return tuple(out)
