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
- **The learning load** (the Lab's viewing mode, polyglotic-hq 324;
  `Panel.load`): an alternate view of the Learning marks. While it is on, a
  finished caption's words that are in the load are in their stage's
  colour, each with a line under it that fills in as the word is learned,
  so the stage never rests on the colour alone: red over dots, orange
  over dashes, yellow over a dash-dot line, green over a solid line, and a
  word ready to check in green over a wavy line. A known word is plain
  text (a graduated one too: "consolidated"). New-word dots and deck
  dashes aren't drawn (the load replaces them). Word links are drawn as
  ever (polyglotic-hq 340; the user, 2026-11-15: "Word links stop working
  with learning load"): a link's bar is below the font's descent, under
  the stage's line, so a word of the load that is linked shows both - its
  stage in its colour and the line under it, its link in the bar below
  that. Saved words keep their category's colour
  unless they are in the load, on live captions too. Words outside the
  load that aren't known yet are as usual, or dimmed (`Panel.dim_rare`).
  A word that changes stage is drawn again wherever it shows
  (`load_changed`); a meeting that moves no word redraws nothing.

A line's marks are worked out once, when it is first painted, and kept
while its rows stay the same. A Learning action on one entry (the lookup's
Add to deck, Known, Save to, Remove) forgets only the lines holding it
(`forget`), and the window repaints only those; any other Learning change
(the level, the Words page, another device) forgets them all. Exposures,
which change with every finished caption, don't: a caption keeps the
highlights it was shown with (as today).

Links "On hover" are the caption window's: the hovered word and its
counterpart, tinted. Not yet: the curves between rows for "Arrows" -
underlined in their link's colour for now. Holds caption text: never log
it.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from PySide6.QtGui import QColor, QTextCharFormat

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import LinkChoice
from polyglotic_desktop.core.learning.load import Stage
from polyglotic_desktop.core.learning.saved_words import SavedSpan
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.listening.display import LIVE_TRAIL, RowKind, WordLinks
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK, Mark
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.links import RowLinks, hidden_links
from polyglotic_desktop.ui_next.views.lookup import Learner
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    colour_difference,
    luminance,
    readable_on,
)

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
"""A colour per link, not a text colour (white, yellow and saved words'
colours already mean something), ordered so neighbours are far apart in
hue. Every two at least 13 apart in CIEDE2000 as drawn, on every preset's
panel, as lines and as words (`tests/ui_next/test_link_colours_told_apart`;
polyglotic-hq 446: the user found orange and the brown that was last, 11
apart, "not that distinguishable"). 446 changed three: the brown to an
olive, the lime to a green and the magenta a little pinker."""
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
the one before up to yellow. 5.9:1 or more on every dark preset's panel,
and at least 39 apart from each other (`colour_difference`)."""
STAGE_COLOURS_LIGHT = ("#c62828", "#a65100", "#7d6a00", "#0f7b5f")
"""And on a light panel (Paper's cream), where those four made readable
turn to three browns: 4.6:1 or more there, at least 32 apart."""
LIGHT_PANEL = 0.4
"""A panel at least this light (`luminance`) takes the light ramp."""
STAGE_LINES = (
    QTextCharFormat.UnderlineStyle.DotLine,
    QTextCharFormat.UnderlineStyle.DashUnderline,
    QTextCharFormat.UnderlineStyle.DashDotLine,
    QTextCharFormat.UnderlineStyle.SingleUnderline,
    QTextCharFormat.UnderlineStyle.WaveUnderline,
)
"""The line under a word of the load, by stage (ready to check last): it
fills in as the word is learned - dots, dashes, dash-dot, solid - and
waves when the word is ready to check. A shape for each, so a colour-blind
learner tells them apart."""
RARE_ALPHA = 0.55
"""A word outside the load, dimmed: this much of its row's ink - still
3:1 as large text on every preset's panel."""
MANY = 40
"""More words than this changing stage at once (the load filled, its
size changed): every line's marks are worked out again rather than each
word looked for."""


@dataclass(frozen=True, slots=True)
class Panel:
    """What a caption window's marks are drawn on and beside: its panel's
    colour and its rows' own ("#rrggbb", the look's)."""

    background: str = "#0a0c10"
    original: str = "#ffffff"
    translation: str = "#ffd76e"
    load: bool = False
    """The Lab's learning load mode is on (324): words in the load in
    their stage's colour, in place of new-word dots, deck dashes and word
    links' colours."""
    dim_rare: bool = False
    """And the words outside it that aren't known yet are dimmed."""

    def own(self, kind: RowKind) -> str:
        return self.original if kind is RowKind.ORIGINAL else self.translation


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
        self._kept.clear()
        return True

    def load_changed(self, entries: frozenset[EntryId] | None) -> set[int] | None:
        """Words of the learning load changed stage: the marks of the
        lines holding them are worked out again when next painted - their
        keys. None: every line's (any word may have changed, or too many
        did to look for each). Nothing while the mode is off."""
        if not self.panel.load or entries == frozenset():
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
        if learner is not None and learner.ready:  # else: no Learning marks yet
            self._learning(line, learner, marks, entries)
        if self.word_links in (WordLinks.COLOURS, WordLinks.ARROWS):
            hidden = self._hidden_links(line, entries)
            for index, row in enumerate(line.rows):
                for linked in row.links:
                    if (row.clause, linked.link) in hidden:
                        continue
                    color = LINK_COLORS[linked.link % len(LINK_COLORS)]
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
        words = [ours.words_in(text) for ours, text in zip(each, texts, strict=True)]
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
        in_load: set[int] = set()
        if self.panel.load:  # the learning load's view, instead (324)
            # the load is the language in use's (the main tools'): a row in
            # another language open beside it is drawn as with the mode off,
            # below, by its own learning data (306)
            vocabulary = learner.vocabulary
            stage_of = vocabulary.load.stage
            for index, (text, found) in enumerate(zip(texts, words, strict=True)):
                if each[index] is not learner:
                    continue
                in_load.add(index)
                kind = line.rows[index].kind
                staged = set()
                for word in found:
                    stage = stage_of(word.entry.entry_id)
                    if stage is not None:
                        staged.add(word.entry.entry_id)
                        marks[index].extend(
                            (word.start, word.end, format_)
                            for format_ in self._stage(stage, kind)
                        )
                    elif self.panel.dim_rare and vocabulary.could_be_in_load(
                        word.entry
                    ):
                        marks[index].append((word.start, word.end, self._rare(kind)))
                saved(
                    index,
                    [
                        span
                        for span in vocabulary.saved_spans(text, found)
                        if span.entry_id not in staged
                    ],
                )
        learners: list[Learner] = []
        for ours in each:
            if not any(ours is seen for seen in learners):
                learners.append(ours)
        for ours in learners:  # each language's rows together, as one caption
            rows = [
                n for n, other in enumerate(each) if other is ours and n not in in_load
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

    def _stage(self, stage: Stage, row: RowKind) -> list[QTextCharFormat]:
        """A word of the load's formats: its stage's colour, readable on
        the panel (with a tint behind where that is too near its row's own:
        Classic's yellow translation and the yellow stage), and its
        stage's line under it. The dots and the dashes are a format of
        their own: the layout draws those below where an underline goes."""
        key = ("stage", row.value, int(stage))
        found = self._formats.get(key)
        if found is None:
            light = luminance(self.panel.background) >= LIGHT_PANEL
            ramp = STAGE_COLOURS_LIGHT if light else STAGE_COLOURS
            colour = readable_on(
                ramp[min(stage, Stage.GREEN)], self.panel.background, AA_TEXT
            )
            found = QTextCharFormat()
            found.setForeground(QColor(colour))
            if colour_difference(colour, self.panel.own(row)) < NEAR:
                tint = QColor(colour)
                tint.setAlphaF(TINT_ALPHA)
                found.setBackground(tint)
            line = STAGE_LINES[stage]
            if stage >= Stage.YELLOW:  # Qt's own underline, with the text
                found.setUnderlineStyle(line)
                found.setUnderlineColor(QColor(colour))
            else:
                under = QTextCharFormat()
                under.setUnderlineStyle(line)
                under.setUnderlineColor(QColor(colour))
                self._formats[("stage line", row.value, int(stage))] = under
            self._formats[key] = found
        under_key = ("stage line", row.value, int(stage))
        if under_key in self._formats:
            return [found, self._formats[under_key]]
        return [found]

    def _rare(self, row: RowKind) -> QTextCharFormat:
        """A word outside the load that isn't known yet, dimmed: its row's
        own colour at `RARE_ALPHA`."""
        key = ("rare", row.value, 0)
        found = self._formats.get(key)
        if found is None:
            colour = QColor(self.panel.own(row))
            colour.setAlphaF(RARE_ALPHA)
            found = QTextCharFormat()
            found.setForeground(colour)
            self._formats[key] = found
        return found

    def _saved(self, color: str, row: RowKind) -> QTextCharFormat:
        """A saved word's format: in its category's colour, readable on the
        panel; with a tint of it behind, where that's too near the row's
        own colour to read as a mark (`NEAR`)."""
        key = ("saved", f"{color}/{row.value}", 0)
        found = self._formats.get(key)
        if found is None:
            readable = readable_on(color, self.panel.background, AA_TEXT)
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
            format_.setUnderlineColor(
                QColor(readable_on(color, self.panel.background, MARK_CONTRAST))
            )
        self._formats[(kind, color, link)] = format_
        return format_
