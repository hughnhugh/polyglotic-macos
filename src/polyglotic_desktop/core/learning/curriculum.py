"""Our curriculum, 0.1.8's version (polyglotic-hq 473's option A, DECISIONS
#201; desktop decision 0219): a small active set of words being learned,
which the quiet view shows in blue.

- **The set** holds `size` words (50 until the learner says): words past
  the learner's known line - new or in the deck, never a name - those the
  learner's own audio has said first (heard in `theme.HEARD_IN` or more
  captions from what the PC played, inside the learning window, never
  everyday talk: the most heard first), then the next by the learning
  load's order (`levels.place`: a word's frequency rank, or its level's
  size).
- **Sittings.** A sitting ends after `SITTING_GAP` with no finished
  caption (as the load's "once a session"), and when the app closes. The
  set fills between sittings - at the start, and when the first caption of
  a new sitting comes.
- **The conversation's words** (polyglotic-hq 491, desktop decision 0227;
  `theme`) - the one way in mid-sitting (the user, 2026-11-18): at each
  update of a source's window (every `theme.EVERY` of its talk), its
  stretch words and then its theme words enter while the captions'
  expected blue words stay under `TARGET_RATE` a caption, at most
  `MOST_NEW` an update; a look-alike of a lit word waits. A word that has
  to make room takes the place of the newest word never met (one that
  came by the load's order first); never a met one. A conversation word
  that hasn't been said for `theme.WINDOW` **rests** at the next update:
  it gives its place back, keeps its days met, and comes back in when it
  is said again.
- **A meeting** is the word heard in a finished caption from what the PC
  played (never the learner's own mic). A word **retires**, and doesn't
  come back - its place goes to the next word at the next sitting:
  - a conversation's word (theme, stretch) when met while the learner
    knows it: 489's chance says green (`known`; polyglotic-hq 496,
    DECISIONS #215) - a series' core words (业主, 物业) keep lighting
    episode after episode until then;
  - a word that came by being heard or by the load's order once it has
    been met on `RETIRE_DAYS` separate days (the learner's own days, the
    PC's), as before (#859).
- **A word not met for a whole sitting** gives up its place and waits: it
  may come in again later, when heard.
- **Statuses.** A word set known or ignored leaves; a retired word stays
  retired.

Kept on this PC with the rest of the learning data (`ports.learning`'s
`StoredCurriculumWord`) and deleted with it. Nothing of it leaves the PC.

Plain rules here; `Curriculum` is the set itself, which `Vocabulary` holds
and tells of finished captions, statuses and the line.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum

from polyglotic_desktop.core.learning.theme import (
    HEARD_IN,
    Chosen,
    ConversationThemes,
    Said,
    everyday,
    known_by_speech,
    look_alike,
    offered,
    theme_name,
)
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ports.learning import StoredCurriculumWord

DEFAULT_SIZE = 50
"""The set's size until the learner says (473: 50 words put a blue word in
about 1 caption in 4 for a Chinese learner who knows 1,000 words)."""

SIZES = (20, 50, 100)
"""The sizes offered."""

MIN_SIZE, MAX_SIZE = 1, 500

RETIRE_DAYS = 3
"""Separate days a word that came by being heard or by the load's order is
met on before it retires (473). A conversation's word retires when known
instead (496)."""

SITTING_GAP = timedelta(minutes=30)
"""No finished caption for this long ends a sitting."""


class ChosenWords(StrEnum):
    """Which words the quiet view shows in blue (a multiselect: the union
    of what's ticked; DECISIONS #201)."""

    CURRICULUM = "curriculum"
    """Our curriculum: the active set (this module)."""
    LOAD = "load"
    """The learning load's words (`core.learning.load`)."""
    SAVED = "saved"
    """Saved words, whatever their category."""
    EDGE = "edge"
    """Words at your edge: any word in the learner's learning window as it
    is said - never a name, a number, everyday talk or a filler
    (`Vocabulary.at_edge`; polyglotic-hq 496, DECISIONS #215: a Mandarin
    talk repeats too few words for the set alone to reach the user's "2-10
    words on each screen")."""


EDGE_PER_CAPTION = 2
"""Words at your edge light while a caption shows fewer blue words than
this, the commonest first (`Vocabulary.lit`): the user's "a couple per
sentence" (2026-11-18). On 491's live captions for a learner of 1,000 words
it kept Mandarin's screens with 2-10 blue words at 61 % and took English's
from 82 % to 93 % (English's over 10 from 18 % to 7 %); 3 a caption left
English at 83 % (polyglotic-hq 496)."""


DEFAULT_CHOSEN = frozenset({ChosenWords.CURRICULUM, ChosenWords.EDGE})
"""What the quiet view shows in blue until the learner says: our curriculum
(473's assumption, the user's: "I would assume our curriculum would be the
default option") and words at your edge (496: the user's "2-10 words on
each screen" and "go with safe defaults")."""


def chosen_from(stored: Iterable[object]) -> frozenset[ChosenWords]:
    """The choices as kept (their values), read leniently: one this app
    doesn't know is left out. Nothing readable: nothing chosen."""
    known = {each.value: each for each in ChosenWords}
    return frozenset(known[s] for s in stored if isinstance(s, str) and s in known)


class Standing(StrEnum):
    IN = "in"
    RETIRED = "retired"
    RESTING = "resting"
    """A conversation's word no longer said: out of the set, its days met
    kept for when it comes back (491)."""


class Came(StrEnum):
    """Why a word came into the set."""

    HEARD = "heard"
    """The learner's own audio had said it."""
    ORDER = "order"
    """It was next by the load's order."""
    THEME = "theme"
    """The conversation was about it: in the learning window (491)."""
    STRETCH = "stretch"
    """The conversation's own core word, past the learning window (491)."""


CONVERSATION = frozenset({Came.THEME, Came.STRETCH})
"""The ways in that follow the conversation: such a word rests when it
stops being said."""

TARGET_RATE = 1.0
"""The blue words a caption shows on average, as the set's words are said
in a source's window, that the conversation's words fill it up to (the
user, 2026-11-18: "2-10 words on each screen ... maybe a 0.2 - couple per
sentence"; a screen holds about 5 captions). The supply of words said
twice binds first nearly always (491: 0.6, 1.0 and 1.5 gave 0.38-0.43
blue words a caption in Mandarin meetings)."""

MOST_NEW = 10
"""Conversation words entering at one update, at most: the top of the
user's 2-10 a screen."""


@dataclass(frozen=True)
class ActiveWord:
    """A word the set keeps: in it, or retired. `days_met`: the separate
    days it has been met on since it entered, the last on `last_day`;
    `sittings`: the sittings begun while it was in."""

    entry_id: EntryId
    standing: Standing
    came: Came
    entered_at: datetime
    days_met: int = 0
    last_day: date | None = None
    sittings: int = 0
    retired_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.standing is Standing.IN


class CurriculumStore:
    """What `Curriculum` needs kept: two calls of `LearningStore`."""

    def __init__(
        self,
        save: Callable[[Sequence[StoredCurriculumWord]], None],
        delete: Callable[[Sequence[str]], None],
    ) -> None:
        self.save = save
        self.delete = delete


class Curriculum:
    """The active set of one language. Off (`size` None) it keeps what it
    has and counts nothing.

    `facts` gives a word's facts (None if the dictionary hasn't got it);
    `eligible` says whether a word may be in the set now (past the line:
    new or in the deck, not a name); `heard` gives the words heard from
    what the PC played, each with how many captions; `placed(after,
    limit)` the dictionary's words placed past `after`, earliest first;
    `line_place` the place the known line stands at; `day_of` the
    learner's day for a time; `reaches` whether a word is no rarer than
    the learning window's end; `known_words` about how many words the
    learner knows; `known` whether the learner knows a word now (489's
    chance, green), which retires a conversation's word. The methods that
    change the set return whether its words changed - a word in or out (a
    meeting counted changes none)."""

    def __init__(
        self,
        stored: Iterable[StoredCurriculumWord],
        store: CurriculumStore,
        facts: Callable[[EntryId], EntryFacts | None],
        eligible: Callable[[EntryFacts], bool],
        heard: Callable[[], Iterable[tuple[EntryId, int]]],
        placed: Callable[[int, int], Sequence[tuple[int, EntryFacts]]],
        line_place: Callable[[], int],
        day_of: Callable[[datetime], date],
        reaches: Callable[[EntryFacts], bool] = lambda _: True,
        known_words: Callable[[], int] = lambda: 0,
        known: Callable[[EntryFacts], bool] = lambda _: False,
    ) -> None:
        self._store = store
        self._known = known
        self._reaches = reaches
        self._known_words = known_words
        self.themes = ConversationThemes()
        """What each source is talking about now (in memory only)."""
        self._facts = facts
        self._eligible = eligible
        self._heard = heard
        self._placed = placed
        self._line_place = line_place
        self._day_of = day_of
        self._words: dict[EntryId, ActiveWord] = {}
        for row in stored:
            try:
                word = _from_stored(row)
            except ValueError:
                continue  # a newer app's value: left as it is in the store
            self._words[word.entry_id] = word
        self.size: int | None = None
        self._moved = False
        """A word came in or left since `_took_moved` last asked."""
        self._last_caption: datetime | None = None
        """When the sitting under way last had a finished caption; None:
        none since the app started - the next caption starts a sitting."""

    # -- reading ---------------------------------------------------------------

    @property
    def on(self) -> bool:
        return self.size is not None

    def active(self, entry_id: EntryId) -> bool:
        """Whether the word is in the set now (never while it's off)."""
        if self.size is None:
            return False
        word = self._words.get(entry_id)
        return word is not None and word.active

    def word(self, entry_id: EntryId) -> ActiveWord | None:
        return self._words.get(entry_id)

    def members(self) -> list[ActiveWord]:
        """The words in the set, the earliest in first."""
        return sorted(
            (w for w in self._words.values() if w.active),
            key=lambda w: (w.entered_at, w.entry_id),
        )

    def retired(self) -> list[ActiveWord]:
        return [w for w in self._words.values() if w.standing is Standing.RETIRED]

    # -- the learner's choices -----------------------------------------------------

    def set_size(self, size: int | None, now: datetime, fill: bool = True) -> bool:
        """Turns the set on, changes its size, or (None) turns it off. A
        change comes in between sittings: at once if none is under way,
        else at the next - but a set still empty fills at once. With
        `fill` False (the app's start), the set fills when `fill` is called,
        or at the first sitting's first caption: filling looks through every
        word heard (polyglotic-hq 509)."""
        if size is not None:
            size = min(MAX_SIZE, max(MIN_SIZE, size))
        if size == self.size:
            return False
        self.size = size
        if size is None:
            return True
        if fill:
            self.fill(now)
        self._took_moved()
        return True

    def fill(self, now: datetime) -> bool:
        """The set brought up to its size now, unless a sitting is under
        way and the set has words (then the next sitting fills it); True if
        a word came in."""
        if self.size is None:
            return False
        if not self._in_sitting(now) or not any(w.active for w in self._words.values()):
            self._refill(now)
        return self._took_moved()

    # -- what happens ------------------------------------------------------------

    def caption_finished(
        self,
        words: Sequence[WordInLine],
        now: datetime,
        caption_id: str = "",
        source: str = "",
        forms: Sequence[str] = (),
    ) -> bool:
        """A finished caption from what the PC played (never the learner's
        own mic): a new sitting first, if one is beginning - words that sat
        a whole sitting unmet leave, the set fills - then the caption into
        its source's window (`forms`: each word as said), and the
        conversation's words at that source's update; then each word of the
        set in it is met today, and retires if it now may (`_retires`)."""
        if self.size is None:
            return False
        changed: dict[EntryId, ActiveWord] = {}
        if not self._in_sitting(now):
            self._sitting_begins(changed)
            self._fill(now, changed)
        self._last_caption = now
        said = [
            (w.entry, forms[n] if n < len(forms) else "") for n, w in enumerate(words)
        ]
        if self.themes.heard(caption_id, source, said, now):
            self._conversation_update(source, now, changed)
        day = self._day_of(now)
        for entry_id in {w.entry.entry_id for w in words if not w.entry.is_name}:
            word = self._words.get(entry_id)
            if word is None or not word.active or word.last_day == day:
                continue
            word = replace(word, days_met=word.days_met + 1, last_day=day)
            if self._retires(word):
                word = replace(word, standing=Standing.RETIRED, retired_at=now)
                self._moved = True
            self._words[entry_id] = changed[entry_id] = word
        self._save(changed)
        return self._took_moved()

    def caption_withdrawn(self, caption_id: str) -> None:
        """A caption withdrawn, or joined into another: out of its window."""
        self.themes.withdrawn(caption_id)

    def theme_name(self, source: str) -> list[Said]:
        """What the source is talking about now, as its few keyest words
        (`theme.theme_name`); none until it has said enough."""
        window = self.themes.window(source)
        return theme_name(window) if window is not None else []

    def status_set(self, entry_id: EntryId, known_or_ignored: bool) -> bool:
        """A word's status was set: known or ignored, it leaves the set (a
        retired word stays retired). Its place is filled at the next
        sitting."""
        word = self._words.get(entry_id)
        if word is None or not word.active or not known_or_ignored:
            return False
        self._drop(entry_id)
        return self._took_moved()

    def line_moved(self, now: datetime) -> bool:
        """The known line moved: words it now covers leave. Their places
        are filled at the next sitting - at once if none is under way."""
        gone = [
            w.entry_id
            for w in self._words.values()
            if w.active
            and (facts := self._facts(w.entry_id)) is not None
            and not self._eligible(facts)
        ]
        for entry_id in gone:
            self._drop(entry_id)
        if self.size is not None and not self._in_sitting(now):
            self._refill(now)
        return self._took_moved()

    def moved(self, old_id: EntryId, new_id: EntryId) -> None:
        """A dictionary update merged an entry into another: what the set
        kept under the old ID is the new one's, unless it has its own."""
        word = self._words.get(old_id)
        if word is None:
            return
        self._drop(old_id)
        if new_id not in self._words:
            self._words[new_id] = replace(word, entry_id=new_id)
            self._store.save([_stored(self._words[new_id])])
        self._took_moved()

    def clear(self, now: datetime) -> None:
        """The learner deleted their learning data: the store's rows went
        with it; a set that is on fills again."""
        self._words.clear()
        self._last_caption = None
        self.themes.clear()
        if self.size is not None:
            self._refill(now)
        self._took_moved()

    # -- inside ------------------------------------------------------------------------

    def _retires(self, word: ActiveWord) -> bool:
        """Whether a word just met leaves the set for good: a
        conversation's word once the learner knows it (`known`), any other
        on its `RETIRE_DAYS`th day met."""
        if word.came in CONVERSATION:
            facts = self._facts(word.entry_id)
            return facts is not None and self._known(facts)
        return word.days_met >= RETIRE_DAYS

    def _in_sitting(self, now: datetime) -> bool:
        last = self._last_caption
        return last is not None and now - last <= SITTING_GAP

    def _refill(self, now: datetime) -> None:
        changed: dict[EntryId, ActiveWord] = {}
        self._fill(now, changed)
        self._save(changed)

    def _took_moved(self) -> bool:
        moved, self._moved = self._moved, False
        return moved

    def _sitting_begins(self, changed: dict[EntryId, ActiveWord]) -> None:
        """A sitting begins: a word that sat the whole of the one before
        unmet gives up its place; the rest count one more sitting."""
        for word in [w for w in self._words.values() if w.active]:
            if word.sittings >= 1 and word.days_met == 0:
                self._drop(word.entry_id)
                changed.pop(word.entry_id, None)
            else:
                moved = replace(word, sittings=word.sittings + 1)
                self._words[word.entry_id] = changed[word.entry_id] = moved

    def _fill(self, now: datetime, changed: dict[EntryId, ActiveWord]) -> None:
        """Brings the set up to its size: the words heard most first - in
        `HEARD_IN` captions or more, inside the learning window, never
        everyday talk (polyglotic-hq 485: as built it took 嗯 and "um", and
        words heard once) - then the next by the load's order."""
        size = self.size
        if size is None:
            return
        need = size - sum(1 for w in self._words.values() if w.active)
        if need <= 0:
            return
        heard = sorted(
            (
                (count, entry_id)
                for entry_id, count in self._heard()
                if count >= HEARD_IN
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        known = self._known_words()
        for _, entry_id in heard:
            if need == 0:
                return
            facts = self._facts(entry_id)
            if (
                facts is not None
                and self._can_enter(facts)
                and self._reaches(facts)
                and not facts.is_number
                and not everyday(facts)
                and not known_by_speech(facts, known)
            ):
                self._enter(facts, Came.HEARD, now, changed)
                need -= 1
        after = self._line_place()
        batch = max(200, 2 * need)
        while need > 0:
            found = self._placed(after, batch)
            if not found:
                return
            after = max(after + 1, max(at for at, _ in found))
            for _, facts in found:
                if need == 0:
                    return
                if self._can_enter(facts):
                    self._enter(facts, Came.ORDER, now, changed)
                    need -= 1
            batch *= 2  # a line kept as a level: many known words to pass

    def _conversation_update(
        self, source: str, now: datetime, changed: dict[EntryId, ActiveWord]
    ) -> None:
        """A source's update: its words no longer said rest; then its
        stretch and theme words come in, in that order, while the set's
        words make fewer than `TARGET_RATE` blue words a caption of its
        window, `MOST_NEW` at most; a look-alike of a lit word waits."""
        window = self.themes.window(source)
        if window is None:
            return
        for word in [w for w in self._words.values() if w.active]:
            if word.came in CONVERSATION and not self.themes.said_lately(
                word.entry_id, now
            ):
                rested = replace(word, standing=Standing.RESTING)
                self._words[word.entry_id] = changed[word.entry_id] = rested
                self._moved = True
        lit = [w.entry_id for w in self._words.values() if w.active]
        rate = sum(window.rate(e) for e in lit)
        forms = [f for e in lit if (f := self.themes.form(e))]
        came = 0
        for offer in offered(
            window, self._eligible, self._reaches, self._known_words()
        ):
            if rate >= TARGET_RATE or came >= MOST_NEW:
                return
            facts = offer.said.entry
            kept = self._words.get(facts.entry_id)
            if kept is not None and kept.standing is not Standing.RESTING:
                continue  # in the set, or retired
            if any(look_alike(offer.said.form, f) for f in forms):
                continue
            if not self._make_room(changed):
                return
            how = Came.STRETCH if offer.chosen is Chosen.STRETCH else Came.THEME
            if kept is None:
                self._enter(facts, how, now, changed)
            else:  # back from resting, its days met kept
                back = replace(
                    kept, standing=Standing.IN, came=how, entered_at=now, sittings=0
                )
                self._words[facts.entry_id] = changed[facts.entry_id] = back
                self._moved = True
            rate += offer.rate
            forms.append(offer.said.form)
            came += 1

    def _make_room(self, changed: dict[EntryId, ActiveWord]) -> bool:
        """A place for a conversation's word: a free one, else the newest
        word never met that came by the load's order (then by being heard)
        gives up its place. False: every word in the set has been met."""
        size = self.size
        active = [w for w in self._words.values() if w.active]
        if size is not None and len(active) < size:
            return True
        unmet = [w for w in active if w.days_met == 0 and w.came not in CONVERSATION]
        if not unmet:
            return False
        last = max(
            unmet,
            key=lambda w: (w.came is Came.ORDER, w.entered_at, w.entry_id),
        )
        self._drop(last.entry_id)
        changed.pop(last.entry_id, None)
        return True

    def _can_enter(self, facts: EntryFacts) -> bool:
        return facts.entry_id not in self._words and self._eligible(facts)

    def _enter(
        self,
        facts: EntryFacts,
        came: Came,
        now: datetime,
        changed: dict[EntryId, ActiveWord],
    ) -> None:
        word = ActiveWord(facts.entry_id, Standing.IN, came, now)
        self._words[facts.entry_id] = changed[facts.entry_id] = word
        self._moved = True

    def _drop(self, entry_id: EntryId) -> None:
        word = self._words.pop(entry_id, None)
        if word is not None:
            self._moved = self._moved or word.active
            self._store.delete([entry_id])

    def _save(self, changed: dict[EntryId, ActiveWord]) -> None:
        if changed:
            self._store.save([_stored(w) for w in changed.values()])


def _stored(word: ActiveWord) -> StoredCurriculumWord:
    return StoredCurriculumWord(
        word.entry_id,
        word.standing.value,
        word.came.value,
        word.entered_at,
        word.days_met,
        word.last_day,
        word.sittings,
        word.retired_at,
    )


def _from_stored(row: StoredCurriculumWord) -> ActiveWord:
    return ActiveWord(
        EntryId(row.entry_id),
        Standing(row.standing),
        Came(row.came),
        row.entered_at,
        max(0, row.days_met),
        row.last_day,
        max(0, row.sittings),
        row.retired_at,
    )
