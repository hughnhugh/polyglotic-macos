"""What a caption window marks in its rows, drawn at paint time - never
laid out (decision 0031): Learning's highlights and word links, as today's
overlay shows them.

- **Saved words** in their category's colour - on live captions too -
  made readable on the panel (Paper's cream: the categories' colours are
  picked for dark panels, and showed at 1.4-2.2:1 there; polyglotic-hq
  305), with a soft tint of it behind the word where that colour can't be
  told from its row's own (Teletext's cyan translation and "Saved"'s blue).
- **Unfamiliar words** (the learner's word introductions: none, a few per
  caption or every new word - of those in their learning window, at the
  size they chose for the language: polyglotic-hq 323) and **words in the deck**, dotted
  underneath - on finished captions only (a live update keeps changing).
- These three only on rows in a language being learned (`learns`), each
  by its own language's dictionary and learning data (`Learner.of`; with
  Chinese and English both learned, both lines are marked - DECISIONS
  #110): a dictionary finds its words in other languages too - the
  English one 38 % of a Spanish line's (polyglotic-hq 174) - so a Spanish
  row showed English "unfamiliar" marks under de, el, que. A translation
  row in a learned language keeps its marks.
- **Word links** (the Look's "Word links": colours, or arrows), each
  linked word underlined in its link's colour - those the learner's
  choice for the row's language shows (`views.links`: every word, only
  words past what they know, or none; polyglotic-hq 323).
- On the provisional line (Steady's at the longest wait for text, Quick
  preview's) saved words only, as on a live caption: a word saved from
  the line being read takes its colour at once, not only once its
  finished caption comes (the user, 2026-11-14: "they don't get
  immediately highlight. Only subsequent or future ones"; polyglotic-hq
  305). Nothing else there: it keeps changing.
- **Learning load** (the Lab's viewing mode, polyglotic-hq 324, then
  489; `Panel.load`): an alternate view of the Learning marks. While it
  is on, every word of a finished caption in the language in use (the
  main tools', as the load's) is in a colour by how well the learner
  knows it (`Vocabulary.chances`, decision 0226): red (unknown) through
  the colours between (exposure, partial knowledge) to green (mastered) -
  or orange to blue (`Panel.palette`, `views.known_colours`). A row in
  another learned language beside it is drawn as with the mode off, by
  its own learning data (306). The colours run dark to light (light to dark on a light
  panel), so they read in greyscale too. Names and words the learner
  ignores keep the row's colour. New-word dots, deck dashes and saved
  words' colours aren't drawn (the colours replace them); word links are
  drawn as ever (polyglotic-hq 340), their bar below the word. Live
  captions show saved words only, as with the mode off. A line keeps the
  colours it was first drawn with, as it keeps its marks: a word heard on
  another day, or looked up, takes its new colour in the captions after;
  what the learner says about a word (Known, Add to deck...) recolours it
  at once.

A line's marks are worked out once, when it is first painted, and kept
while its rows stay the same. A Learning action on one entry (the lookup's
Add to deck, Known, Save to, Remove) forgets only the lines holding it
(`forget`), and the window repaints only those; any other Learning change
(the level, the Words page, another device) forgets them all. Exposures,
which change with every finished caption, don't: a caption keeps the
highlights it was shown with (as today).

- **The quiet view** (polyglotic-hq 477; `Panel.quiet`): in place of all
  of the above, only the chosen words in blue (`QUIET_BLUE`) - our
  curriculum's set, the learning load's words, saved words, words at your
  edge (496), as ticked
  (`Panel.quiet_words`) - on every line, live ones too (the view is
  grey throughout, so nothing else marks them): no dots, no dashes, no
  stage colours, no category colours, no link colours. Each row by its
  own language's learning data, as above.

Links "On hover" are the caption window's: the hovered word and its
counterpart, tinted. Not yet: the curves between rows for "Arrows" -
underlined in their link's colour for now. Holds caption text: never log
it.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtGui import QColor, QTextCharFormat

from polyglotic_desktop.core.learning.curriculum import DEFAULT_CHOSEN, ChosenWords
from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import LinkChoice
from polyglotic_desktop.core.learning.saved_words import SavedSpan
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.lexicon.english import inside_sentence, is_capitalised
from polyglotic_desktop.core.listening.display import LIVE_TRAIL, RowKind, WordLinks
from polyglotic_desktop.core.shared import EntryId, WordInLine
from polyglotic_desktop.ui_next.caption_layout import LINK_CONTRAST, LINK_MARK, Mark
from polyglotic_desktop.ui_next.views.caption_window import MarksIn, rows_marked
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.known_colours import (
    STEPS,
    Palette,
    known_colour,
    step,
)
from polyglotic_desktop.ui_next.views.links import RowLinks, hidden_links
from polyglotic_desktop.ui_next.views.lookup import Learner
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    ciede2000,
    colour_difference,
    readable_on,
    readable_through,
)
from polyglotic_desktop.ui_next.views.tone import caption_text_colour, vibrant
from polyglotic_desktop.ui_next.word_classes import APART_FROM_TEXT, class_colour

LINK_COLORS = (
    "#ff9f43",
    "#b388ff",
    "#4dd0e1",
    "#ff6e9c",
    "#36bf13",
    "#5c9dff",
    "#ff5252",
    "#3ddc97",
    "#e617d1",
    "#acbf60",
)
"""Pairing tints for hover. Underlines and optional text colours use
word class swatches. Hover tints are ordered so neighbours are far apart
in hue. Every two at least 13 apart in CIEDE2000 as drawn, on every preset's
panel, as lines and as words (`tests/ui_next/test_link_colours_told_apart`;
polyglotic-hq 446: the user found orange and the brown that was last, 11
apart, "not that distinguishable"). 446 changed three: the brown to an
olive, the lime to a green and the magenta a little pinker. The vibrance
slider (481) leaves them as they are: muted or made vivid, two pairs fell
under 13 (`tests/ui_next/test_tone_on_captions.py`). On a look whose text
is near one of them, it is skipped there (`link_colours`, 554)."""
UNFAMILIAR = "#ffd27a"
"""Dots under a word new to the learner."""
IN_DECK = "#7ee0a8"
"""Dashes under a word in the deck: a different shape, not only a different
colour, so the two read apart for a colour-blind learner (135, 2026-11-07)."""
KEPT = 400
"""Lines whose marks are kept: more than a caption window's 150."""
MARK_CONTRAST = 3.0
"""Dots and dashes under a word against the panel: WCAG 2.2's 1.4.11 for
what isn't text. A saved word is text: `AA_TEXT`."""
NEAR = 30.0
"""A saved word's colour this close to its row's own (`colour_difference`)
reads as the row's: it gets a tint behind it too. The categories' colours
against the presets' rows (305): Teletext's translation and "Saved" 24.7,
Ember's and the second new category 8.5, Forest's and the fifth 10.6 -
and Classic's yellow and the second's orange 29.9; the nearest left
without a tint is Ember's pale "what was said" and "Saved", 32.1, which
read apart in a caption window."""
TINT_ALPHA = 0.35
"""How strong that tint is."""
STAGE_COLOURS = ("#ff6b5e", "#ffa033", "#f5e050", "#35d6a4")
"""The learning load's four stages on a dark panel - red, orange, yellow,
green (324): a vermilion red and a bluish green, the pair that stays
apart for red-green colour blindness (Okabe and Ito's), each lighter than
the one before up to yellow. Its card on Learning and the lookup's line
show them; captions no longer do (489: every word by how well it's known,
`views.known_colours`)."""
STAGE_COLOURS_LIGHT = ("#c62828", "#a65100", "#7d6a00", "#0f7b5f")
"""And on a light panel (Paper's cream)."""
QUIET_BLUE = "#6fc3ff"
"""The quiet view's chosen words: the blue saved words had ("Saved"'s, the
first category's) - the one colour that isn't the view's grey or gold
(the user, 2026-11-18: "the blue font currently saved words as the
polarising focal points"); made readable on the panel (Paper's cream)."""
QUIET_CONTRAST = 5.5
"""The blue's contrast with the panel: 4.5 (`AA_TEXT`) and a margin - its
reading is drawn a little fainter (`reading_lines.ALPHA`), and over
Paper's panel seen through, 5.0 measured 4.1 there in the UI lab."""
MANY = 40
"""More words than this changing at once in the learning load (it filled,
its size changed): every line's marks are worked out again rather than
each word looked for."""


@dataclass(frozen=True, slots=True)
class Panel:
    """What a caption window's marks are drawn on and beside: its panel's
    colour and its rows' own ("#rrggbb", the look's)."""

    background: str = "#0a0c10"
    original: str = "#ffffff"
    translation: str = "#ffd76e"
    load: bool = False
    """Learning load's mode is on (324, 489): every word in a colour by
    how well it is known, in place of new-word dots, deck dashes and saved
    words' colours."""
    palette: Palette = Palette.RED_GREEN
    """Its colours."""
    quiet: bool = False
    """The quiet view is on (477): only the chosen words, in blue."""
    opacity: float = 1.0
    """How solid the panel is: the blue is made readable on it seen over a
    light or a black video too (`readable_through`, as links' colours)."""
    marks_in: MarksIn = MarksIn.LEARNED
    """Which line of a clause the learner's words are marked in (526)."""
    quiet_words: frozenset[ChosenWords] = DEFAULT_CHOSEN
    """Which words are chosen: our curriculum's set, the load's words,
    saved words, words at your edge (the learner's vocabulary says which a
    word is: `Vocabulary.chosen`)."""
    vibrance: int = 0
    """The vibrance slider (`views.tone.vibrant`; 481): saved words'
    categories' colours, the quiet view's blue, Learning load's colours,
    the dots and dashes at it - not word links' (`LINK_COLORS`)."""

    def own(self, kind: RowKind) -> str:
        return self.original if kind is RowKind.ORIGINAL else self.translation


def link_colours(panel: Panel) -> tuple[str, ...]:
    """The word links' colours on `panel`, in `LINK_COLORS`' order: those
    too close to its rows' own colours as a word is drawn in them
    (`APART_FROM_TEXT`) skipped, so the next takes their turn - a linked
    word mustn't read as one of its line's other words (polyglotic-hq 554).
    Both rows', as a link joins a word of each in one colour."""
    return _link_colours(
        panel.background, panel.opacity, panel.original, panel.translation
    )


def link_colour(panel: Panel, link: int) -> str:
    """Link number `link`'s colour on `panel` (`link_colours`)."""
    colours = link_colours(panel)
    return colours[link % len(colours)]


@lru_cache(maxsize=64)
def _link_colours(
    background: str, opacity: float, original: str, translation: str
) -> tuple[str, ...]:
    kept = tuple(
        colour
        for colour in LINK_COLORS
        if all(
            ciede2000(
                readable_through(colour, background, opacity, 1.0, LINK_CONTRAST),
                row,
            )
            >= APART_FROM_TEXT
            for row in (original, translation)
        )
    )
    return kept or LINK_COLORS  # text in colours like every one of them


def _said(line: Line, index: int) -> list[tuple[int, int, str]]:
    """What the line's translation says for each linked word of its row
    `index` (an original's): the word's span and the words of its link in
    the translation rows - a word written there by its sound is a name
    (polyglotic-hq 496)."""
    row = line.rows[index]
    if row.kind is not RowKind.ORIGINAL or not row.links:
        return []
    meant: dict[int, list[str]] = {}
    for other in line.rows:
        if other.kind is RowKind.TRANSLATION and other.clause == row.clause:
            for linked in other.links:
                meant.setdefault(linked.link, []).append(
                    other.text[linked.start : linked.end]
                )
    return [
        (linked.start, linked.end, " ".join(meant[linked.link]))
        for linked in row.links
        if linked.link in meant
    ]


@dataclass(frozen=True, slots=True)
class _Kept:
    """A line's marks while its rows stay the same, and what they rest on:
    the entries in it (its words, its saved words) and its text."""

    rows: object
    marks: list[list[Mark]]
    entries: frozenset[EntryId]
    text: str


class CaptionMarks:
    """A caption window's marks, by line and row: `marks(line, row)`."""

    def __init__(self, learner: Learner | None) -> None:
        self.learner = learner
        self.word_links = WordLinks.OFF
        self.introductions = WordIntroductions.A_FEW
        self.panel = Panel()
        self._kept: dict[int, _Kept] = {}
        self._formats: dict[tuple[str, str, int], QTextCharFormat] = {}

    def set_look(
        self,
        word_links: WordLinks,
        introductions: WordIntroductions,
        panel: Panel | None = None,
    ) -> None:
        panel = panel or self.panel
        if (word_links, introductions, panel) != (
            self.word_links,
            self.introductions,
            self.panel,
        ):
            if panel != self.panel:
                self._formats.clear()
            self.word_links, self.introductions = word_links, introductions
            self.panel = panel
            self._kept.clear()

    def learning_changed(self, what: str) -> bool:
        """Statuses, saved words or the level changed: True if what shows
        may have (the window repaints); not for exposures."""
        if what in (Changed.EXPOSURES.value, Changed.LOAD.value):
            return False  # the load's stages: `load_changed`
        if what == Changed.SENTENCES.value:
            return False  # a saved sentence marks nothing (459)
        self._kept.clear()
        return True

    def load_changed(self, entries: frozenset[EntryId] | None) -> set[int] | None:
        """Words of the learning load changed: the marks of the lines
        holding them are worked out again when next painted - their keys.
        None: every line's (any word may have changed, or too many did to
        look for each). Nothing unless the quiet view shows the load's
        words in blue: Learning load's colours don't follow its stages
        (489)."""
        loads = self.panel.quiet and ChosenWords.LOAD in self.panel.quiet_words
        if not loads or entries == frozenset():
            return set()
        if entries is None or len(entries) > MANY:
            self._kept.clear()
            return None
        found = {
            key
            for key, kept in self._kept.items()
            if not entries.isdisjoint(kept.entries)
        }
        for key in found:
            del self._kept[key]
        return found

    def forget(self, entry_id: EntryId, texts: Collection[str]) -> set[int]:
        """One entry changed (`texts`: its forms - a saved word is found in
        a line by them too): the marks of the lines holding it are worked
        out again when next painted. The keys of those lines."""
        found = {
            key
            for key, kept in self._kept.items()
            if entry_id in kept.entries or any(t and t in kept.text for t in texts)
        }
        for key in found:
            del self._kept[key]
        return found

    def __call__(self, line: Line, row: int) -> Sequence[Mark]:
        found = self._kept.get(line.key)
        if found is None or found.rows is not line.rows:
            if len(self._kept) > KEPT:
                self._kept.clear()
            found = self._marks(line)
            if self.learner is None or self.learner.ready:
                self._kept[line.key] = found  # else marked again once it is
        rows = found.marks
        return rows[row] if row < len(rows) else ()

    def _marks(self, line: Line) -> _Kept:
        marks: list[list[Mark]] = [[] for _ in line.rows]
        text = "\n".join(row.text for row in line.rows)
        learner = self.learner
        entries: set[EntryId] = set()
        if self.panel.quiet:  # the chosen words alone, in blue (477)
            if learner is not None and learner.ready:
                self._quiet(line, learner, marks, entries)
            return _Kept(line.rows, marks, frozenset(entries), text)
        if learner is not None and learner.ready:  # else: no Learning marks yet
            self._learning(line, learner, marks, entries)
        if self.word_links in (WordLinks.COLOURS, WordLinks.ARROWS):
            hidden = self._hidden_links(line, entries)
            background, opacity = self.panel.background, self.panel.opacity
            for index, row in enumerate(line.rows):
                if not row.links:
                    continue
                text_colour = caption_text_colour(
                    self.panel.own(row.kind), background, self.panel.vibrance
                )
                for linked in row.links:
                    if (row.clause, linked.link) in hidden:
                        continue
                    color = class_colour(linked.pos, background, opacity, text_colour)
                    marks[index].append(
                        (
                            linked.start,
                            linked.end,
                            self._format("link", color, linked.link),
                        )
                    )
        return _Kept(line.rows, marks, frozenset(entries), text)

    def _hidden_links(self, line: Line, entries: set[EntryId]) -> set[tuple[int, int]]:
        """The line's links that don't show (`views.links.hidden_links`), by
        what the learner chose for each row's language; the words judged
        join `entries`, so a change to one works the line out again."""
        learner = self.learner
        if learner is None or not any(row.links for row in line.rows):
            return set()
        says: list[RowLinks | None] = []
        for row in line.rows:
            ours = learner.of(row.language)  # its own language's tools (306)
            choices = learner.choices_of(row.language) if row.links else None
            if choices is None or choices.links is LinkChoice.EVERY:
                says.append(None if choices is None else RowLinks(every=True))
            elif choices.links is LinkChoice.OFF:
                says.append(RowLinks(off=True))
            elif learner.is_basic(row.language):  # a pack ranks its words (338)
                words = learner.words_in(
                    row.text.removesuffix(LIVE_TRAIL), row.language
                )
                # the same question as a full language's, with a line alone
                # (polyglotic-hq 373): no learning data is kept for it (0035)
                knows = learner.knowledge_of(row.language)
                says.append(
                    RowLinks(
                        known=[
                            (w.start, w.end)
                            for w in words
                            if knows is not None
                            and knows.of(w.entry, choices.links_from or None).known
                        ]
                    )
                )
            elif not ours.learns(row.language):  # no dictionary on this PC
                says.append(RowLinks(key_only=True))
            elif not learner.ready:  # can't tell yet: none, rather than all
                says.append(RowLinks(off=True))  # that then go (not kept)
            else:
                words = ours.words_in(row.text.removesuffix(LIVE_TRAIL))
                entries.update(w.entry.entry_id for w in words)
                known = ours.vocabulary.needs_no_link
                says.append(
                    RowLinks(
                        known=[
                            (w.start, w.end)
                            for w in words
                            if known(w.entry, choices.links_from)
                        ]
                    )
                )
        return hidden_links(line.rows, says)

    def _rows_marked(self, line: Line, learner: Learner) -> frozenset[int]:
        """The rows of `line` the quiet view's words are marked in
        (`views.caption_window.rows_marked`, by `Panel.marks_in`)."""
        return rows_marked(
            [
                (
                    row.clause,
                    row.kind is RowKind.ORIGINAL,
                    learner.of(row.language).learns(row.language),
                )
                for row in line.rows
            ],
            self.panel.marks_in,
        )

    def _learning(
        self,
        line: Line,
        learner: Learner,
        marks: list[list[Mark]],
        entries: set[EntryId],
    ) -> None:
        # each row by its own language's learner (`Learner.of`): with Chinese
        # and English both learned, each line in its own dictionary and its
        # own learning data's colours (DECISIONS #110)
        each = [learner.of(row.language) for row in line.rows]
        texts = [row.text.removesuffix(LIVE_TRAIL) for row in line.rows]
        texts = [
            text if ours.learns(row.language) else ""
            for text, ours, row in zip(texts, each, line.rows, strict=True)
        ]
        words = [
            ours.words_in(text, said=_said(line, n))
            for n, (ours, text) in enumerate(zip(each, texts, strict=True))
        ]
        entries.update(w.entry.entry_id for found in words for w in found)

        def saved(index: int, spans: Sequence[SavedSpan]) -> None:
            vocabulary = each[index].vocabulary
            for span in spans:
                entries.add(span.entry_id)
                found = vocabulary.saved_word(span.entry_id)
                category = vocabulary.category(found.category_id) if found else None
                if category is not None:
                    kind = line.rows[index].kind
                    marks[index].append(
                        (span.start, span.end, self._saved(category.color, kind))
                    )

        if line.live or line.provisional:  # saved words only: they keep changing
            for index, (text, found) in enumerate(zip(texts, words, strict=True)):
                saved(index, each[index].vocabulary.saved_spans(text, found))
            return
        coloured: set[int] = set()
        if self.panel.load:  # every word by how well it's known (489)
            # the load is the language in use's (the main tools'): a row in
            # another learned language open beside it is drawn as with the
            # mode off, below, by its own learning data (306, 324)
            chances = learner.vocabulary.chances
            for index, found in enumerate(words):
                if each[index] is not learner:
                    continue
                coloured.add(index)
                for word, chance in zip(
                    found, chances.each([w.entry for w in found]), strict=True
                ):
                    if chance is not None:
                        marks[index].append(
                            (word.start, word.end, self._known(chance.chance))
                        )
        learners: list[Learner] = []
        for ours in each:
            if not any(ours is seen for seen in learners):
                learners.append(ours)
        for ours in learners:  # each language's rows together, as one caption
            rows = [
                n for n, other in enumerate(each) if other is ours and n not in coloured
            ]
            if not rows:
                continue
            shown = ours.vocabulary.highlights(  # its own window (323)
                [(texts[n], words[n]) for n in rows],
                self.introductions,
                ours.choices.window_size,
            )
            for index, highlights in zip(rows, shown, strict=True):
                for word in highlights.unfamiliar:
                    marks[index].append(
                        (word.start, word.end, self._format("dotted", UNFAMILIAR))
                    )
                for word in highlights.in_deck:  # dashes: told apart without colour
                    marks[index].append(
                        (word.start, word.end, self._format("dashed", IN_DECK))
                    )
                saved(index, highlights.saved)

    def _quiet(
        self,
        line: Line,
        learner: Learner,
        marks: list[list[Mark]],
        entries: set[EntryId],
    ) -> None:
        """The quiet view's marks: each row's chosen words in blue, by its
        own language's learning data - on every line, live ones too. Words
        at your edge are told the caption's words together - its rows of
        one kind in one language - as `Vocabulary.lit` takes them (496)."""
        saved = ChosenWords.SAVED in self.panel.quiet_words
        found: dict[int, tuple[Learner, str, list[WordInLine]]] = {}
        marked = self._rows_marked(line, learner)
        for index, row in enumerate(line.rows):
            ours = learner.of(row.language)
            if index not in marked:
                continue
            text = row.text.removesuffix(LIVE_TRAIL)
            words = ours.words_in(text, said=_said(line, index))
            entries.update(w.entry.entry_id for w in words)
            found[index] = (ours, text, words)
        lit: dict[int, set[tuple[int, int]]] = {}
        groups: dict[tuple[int, RowKind], list[int]] = {}
        for index, (ours, _, _) in found.items():
            groups.setdefault((id(ours), line.rows[index].kind), []).append(index)
        for rows in groups.values():
            ours = found[rows[0]][0]
            each = [(n, w) for n in rows for w in found[n][2]]
            capitalised = {
                at
                for at, (n, w) in enumerate(each)
                if is_capitalised(found[n][1][w.start : w.end])
                and inside_sentence(found[n][1], w.start)
            }
            shown = ours.vocabulary.lit([w.entry for _, w in each], capitalised)
            for at, (n, w) in enumerate(each):
                if at in shown:
                    lit.setdefault(n, set()).add((w.start, w.end))
        for index, (ours, text, words) in found.items():
            spans = lit.get(index, set())
            if saved:
                for span in ours.vocabulary.saved_spans(text, words):
                    entries.add(span.entry_id)
                    spans.add((span.start, span.end))
            blue = self._blue()
            done = 0
            for start, end in sorted(spans):  # apart: a saved phrase over a word
                if start >= done:
                    marks[index].append((start, end, blue))
                    done = end

    def _blue(self) -> QTextCharFormat:
        key = ("quiet", QUIET_BLUE, 0)
        found = self._formats.get(key)
        if found is None:
            found = QTextCharFormat()
            panel = self.panel
            found.setForeground(
                QColor(
                    readable_through(
                        vibrant(QUIET_BLUE, panel.vibrance),
                        panel.background,
                        panel.opacity,
                        1.0,
                        QUIET_CONTRAST,
                    )
                )
            )
            self._formats[key] = found
        return found

    def _known(self, chance: float) -> QTextCharFormat:
        """A word's format in Learning load: the colour of how well it is
        known, readable on the panel (`views.known_colours`)."""
        at = step(chance)
        key = ("known", self.panel.palette.value, at)
        found = self._formats.get(key)
        if found is None:
            panel = self.panel
            found = QTextCharFormat()
            found.setForeground(
                QColor(
                    known_colour(
                        at / STEPS, panel.palette, panel.background, panel.vibrance
                    )
                )
            )
            self._formats[key] = found
        return found

    def _saved(self, color: str, row: RowKind) -> QTextCharFormat:
        """A saved word's format: in its category's colour, readable on the
        panel; with a tint of it behind, where that's too near the row's
        own colour to read as a mark (`NEAR`)."""
        key = ("saved", f"{color}/{row.value}", 0)
        found = self._formats.get(key)
        if found is None:
            readable = readable_on(
                vibrant(color, self.panel.vibrance), self.panel.background, AA_TEXT
            )
            found = QTextCharFormat()
            found.setForeground(QColor(readable))
            if colour_difference(readable, self.panel.own(row)) < NEAR:
                tint = QColor(readable)
                tint.setAlphaF(TINT_ALPHA)
                found.setBackground(tint)
            self._formats[key] = found
        return found

    def _format(self, kind: str, color: str, link: int = 0) -> QTextCharFormat:
        found = self._formats.get((kind, color, link))
        if found is not None:
            return found
        format_ = QTextCharFormat()
        if kind == "link":  # drawn by the layout, below the descenders (F14)
            format_.setProperty(LINK_MARK, link)  # its number: Arrows' ends meet
            format_.setUnderlineColor(QColor(color))
        else:
            format_.setUnderlineStyle(
                {
                    "dotted": QTextCharFormat.UnderlineStyle.DotLine,
                    "dashed": QTextCharFormat.UnderlineStyle.DashUnderline,
                }.get(kind, QTextCharFormat.UnderlineStyle.SingleUnderline)
            )
            # readable on the panel: the dots' colours are picked for dark ones
            vivid = vibrant(color, self.panel.vibrance)
            format_.setUnderlineColor(
                QColor(readable_on(vivid, self.panel.background, MARK_CONTRAST))
            )
        self._formats[(kind, color, link)] = format_
        return format_
