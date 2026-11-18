"""The Lab: experimental caption settings for the user and the testers to
tune by feel (polyglotic-hq 284; the user's live testing, 270's
FEEDBACK.md: "Configurability of settings and modes are particularly
good especially for my own testing and alpha / beta testers ... If there
are things that are obviously bad, we can remove them later").

One value, `CaptionLab`, kept in the look every caption window shares
(`CaptionLook.lab`) and saved as one setting, `caption_lab` - so "Reset
the lab" is one step, and taking a control out later is one field. Every
control applies at once to the running caption windows and the preview.
Its defaults are the app as it is without the lab.

Each slider's ends were found by trying them (284's report says how):
- **New for** (`new_for`): how long a caption stays at full ink after it
  arrives, beside the newest - which always is (`newness`). 0 s is
  today's step (DECISIONS.md #104). Up to `NEW_FOR_RANGE`'s end: past it,
  every caption a default window shows at a typical pace is still "new"
  and the step says nothing.
- **Then** (`new_fade`): it steps back at once, or fades back over
  `FADE_BACK_SEC`.
- **Gap between new captions** (`arrival_gap`): captions arriving
  together are let into a window at least this far apart, in order,
  nothing dropped (`views.pacing`); 0 s is today's.
- **Gap between new lines** (`line_gap`): a new caption's lines are
  shown one at a time, this far apart, oldest first - poured lines
  and clause rows alike (`views.reveal`; 309); 0 s is today's.
- **Text still being spoken** (`unfinished`): as now, like finished
  text, dimmer, italic, or in the theme's accent - a provisional line and
  a live caption alike.
- **Underline thickness** (`link_px`): a word link's underline as a
  slider, in place of Word links' three steps while it's set.
- **Spacing** (`row_gap`, `caption_gap`): between a clause and its
  translation, and between captions.
- **The loading sign** (`loading`): the bar, three dots, or an ellipsis
  after the text still being spoken.
- **Older captions** (`older`): how much ink a caption that isn't new
  keeps - what was said; its translation steps back less, in the same
  proportion as today's (`older_translation`). 100 % is no step at all;
  `OLDER_RANGE`'s floor keeps an older line at 3:1 on Classic's panel over
  a light video.
- **Older captions dim** (`older_steps`; polyglotic-hq 305, the user,
  2026-11-13: "Lab option for gradual text colour change"): all at once to
  Older captions' ink (1, today's), or step by step - each caption back a
  step dimmer, reaching it `older_steps` captions back (`by_place`). By
  place, not time: it changes only when a caption arrives, which paints
  anyway, so nothing is drawn more while nothing comes. (Then it dims,
  above, fades by time - and only with New for above 0 s.)
- **Your own speech** (polyglotic-hq 305; the user, 2026-11-13: "Your own
  speech should be formatted differently. (perhaps right aligned? I'm not
  sure another lab setting / default some other identifier)"): on the
  right (`own_right`), a tint behind it (`own_tint`), a bar at its side
  (`own_bar`), and the "You" label as now, as a badge or not at all
  (`own_label`). On the right by default (B, the user's own first idea:
  the user, 2026-11-14, DECISIONS #133 "pick a reasonable default"; not in
  a window captioning the mic alone, `caption_window.caption_style`); the
  others off, or as now; they combine. A learner who never touched the Lab
  gets the default; one who turned it off keeps that (`to_stored`).
- **Captions fill the width** (`fill`, `join`; polyglotic-hq 309, the
  user, 2026-11-14: "I want it to use up more of the screen. often clauses
  will only be a few words and rarely make it to the complete width of the
  window ... text will fill the complete caption window line by line
  seperating by ellipsis"): a caption's clauses run on in lines as wide as
  the window, instead of a row each (`views.pour`) - what was said in the
  upper lines and its translation in the lines below (`Fill.STACKED`),
  or line by line - a line of what was said, then the line of its
  translation, cut at matching places (`Fill.PAIRED`).
  Between clauses an ellipsis, one at each line's end too, or a space
  (`Join`). No Arrows while it's on: a clause and its translation aren't
  on facing rows. Off by default: today's clause rows.
- **New layout** (`flow`, `run_on`, `aligned`; polyglotic-hq 340, decision
  0132, the user, 2026-11-15: "our frame can handle the processed data and
  efficiently customise the lines to accurately fill screen width ... the
  caption window is dynamic"): the window's captions are laid out by the
  one layout (`views.flow`) from each caption's model, whichever way
  Captions fill the width is set - with Arrows and word links in all of
  them and in the learning load. Line by line then always fills its line
  pair (a clause that doesn't fit what's left is cut there, on both
  sides), and has a choice of its own: captions run on (`run_on`) - a
  caption from the same source carries on in the line pair the one before
  ended in, instead of starting a line of its own. Parts lined up
  (`aligned`) works however captions fill the width (polyglotic-hq 372;
  Line by line's alone before): each part starts at the same place as its
  counterpart, so a word's counterpart is under it (`views.flow` says how
  in each). All off by default. Turning
  either choice on sets what it needs (`CaptionLab.choose`, 365): the
  user couldn't click them greyed out, with the reason in another row.
  **Filled lines** (`filled`, `with_filled`; polyglotic-hq 372, the user,
  2026-11-15, DECISIONS #175): New layout, Line by line and captions run
  on together - one click on a caption window's strip, the same values as
  these rows (one state), every window's like the rest of the Lab; off
  again puts the three back as they were. **Parts lined up** has its own
  click (`lined_up`, `with_lined_up`), beside it, in every way of filling.
- **Parts placed** (`placing`; polyglotic-hq 458, decision 0215, the user,
  2026-11-17: "placing characters in such a way to reducing distance
  between all arrow length sums ... a 3rd alternate lab mode could be
  clean even space everything"): in New layout, where a line's parts go
  in the room the line has - packed (the default, today's), nearest the
  words they are linked to, or a full line's spread evenly. Choosing one
  turns New layout on.
- **Learning load** (polyglotic-hq 324, then 489; the user, 2026-11-18:
  "Learning load should be a relative word known predicter. every word
  has a colour based on your knowledge of the language"): `load` turns
  the mode on - every word of a finished caption in the language in use
  in a colour by how well the learner knows it
  (`core.learning.known_chance`), red to green, in place of new-word dots,
  deck dashes and saved words' colours; word links are drawn as ever
  (340). Off by default. `load_colours`: red to green (the default, the
  user's), or orange to blue for a learner who can't tell red from green
  (`views.known_colours`). The learning load itself - the next words to
  learn, their stages and the check - stays on Learning, and is what the
  quiet view's "Learning load" choice shows in blue (decision 0226).

Plain Python, no Qt. Holds no caption text.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import StrEnum

from polyglotic_desktop.ui_next.views.arrivals import (
    OLDER_ALPHA,
    OLDER_TRANSLATION_ALPHA,
)

NEW_FOR_RANGE = (0.0, 8.0)
"""Seconds a caption stays new: 0 is today's (only the newest is). Past
the top, every caption in view is still "new" at a typical pace and the
step says nothing: a default window (960 x 300 at 100 %) shows 3 of the
recorded conversation's captions (measured offscreen, 284: 114 px each),
so at a typical 2.5 s between captions (`arrivals.TYPICAL_GAP_SEC`) the
oldest in view arrived 5 s before the newest; 8 s leaves an older caption
in view in a window twice that height (5 captions, 10 s)."""
NEW_FOR_STEP = 0.5
FADE_BACK_SEC = 1.5
"""A gradual step back takes this long, after the caption's new time: slow
enough to see as a fade, quicker than the next caption at a typical pace."""
OLDER_RANGE = (0.45, 1.0)
"""An older caption's ink, what was said: 100 % is no step back (253's C);
45 % is the least that keeps it at 3:1 - WCAG's floor for large text - on
Classic's panel (72 %) over a light video (#f3f5f7). Below it, older
captions stop being readable on a bright scene (284, computed per preset;
today's 72 % keeps 4.5:1)."""
OLDER_STEP = 0.05
OLDER_STEPS_RANGE = (1, 6)
"""Captions back an older caption reaches Older captions' ink: 1 is at
once (today's); 6, a step of a sixth each caption back. A default window
shows 3 captions (284's measure), a tall one 5 or 6: past 6 the steps are
too small to see at Older captions' default (72 %: under 5 % each)."""
ARRIVAL_GAP_RANGE = (0.0, 1.5)
"""Seconds at least between new captions in a window (`views.pacing`): 0
lets them in as they come (today's). Tried on made-up streams (polyglotic-hq
284's report: 400 captions a gaussian 2.5 s or 1.3 s apart,
three landing together every twelfth, the longest wait 3 s): at 1.5 s a
typical pace keeps the gap for 99 in 100 captions (the wait lets the
rest in) and adds 2.9 s at the 95th percentile; at 2 s the wait lets in 11
in 100 and the gap stops being kept. A fast speaker's captions (1.3 s
apart, 253's recorded conversation) keep it up to 1.0 s (2 in 100 let
in by the wait), 38 in 100 at 1.3 s."""
ARRIVAL_GAP_STEP = 0.1
LINE_GAP_RANGE = (0.0, 0.5)
"""Seconds between a new caption's lines (`views.reveal`): 0 shows them
together (today's). The user's range, 2026-11-14 ("for example 0-500 ms a
line")."""
LINE_GAP_STEP = 0.05
_TRANSLATION_SHARE = (1.0 - OLDER_TRANSLATION_ALPHA) / (1.0 - OLDER_ALPHA)
"""How much of what was said's step back the translation takes: the yellow
starts darker, so it steps back less (today's 0.72 / 0.82)."""


LINK_PX_RANGE = (1.0, 6.0)
"""A word link's underline, pixels at 21 px text (scaled with it): the
Lab's slider in place of Word links' Thin / Medium / Thick (1.4, 2.2,
3.4 - the user: "Thickness options should be more different"). Tried at
each end in a caption window (284's report has the pictures): at 0.6 px
and 70 % text size the line is drawn at well under half its colour and
the links' colours can't be told apart; at 1 px they can. At 6 px a line
is as heavy as the strokes of the words above it; at 8 it's heavier and
draws the eye off the words."""
LINK_PX_STEP = 0.2
ROW_GAP_RANGE = (0.0, 12.0)
"""Pixels between a clause and its translation, at text size 1.0 (today's
2). 0: the rows' own line spacing alone, which keeps them clear. Tried in
a caption window: at 12 a translation sat nearer the next clause (8 px
below it) than its own original, so the gap between clauses grows with
this one, staying `CLAUSE_MORE` more (`clause_gap`); past 12 a caption of
three clauses no longer fits a default window."""
CLAUSE_MORE = 6.0
CAPTION_GAP_RANGE = (4.0, 40.0)
"""Pixels between one caption and the next, at text size 1.0 (today's
10). Tried in a caption window: at 4 the label above a caption ("Discord
· Mandarin") still parts it from the one before; with no label it reads
as one caption. Past 40 a default window (300 px) shows two of the
recorded conversation's captions, not three."""
SPACING_STEP = 1.0


class Unfinished(StrEnum):
    """How text still being spoken - a provisional line (Steady, Quick
    preview) or a live caption (Live updates) - looks beside finished
    text (the user's live testing, 270's FEEDBACK.md line 20: "Mid
    transcription lines should be visually distinguishable to established
    lines")."""

    AS_NOW = "as_now"
    """Today's: a provisional line dim and italic, a live one a little dim."""
    SAME = "same"
    """Like finished text."""
    DIMMER = "dimmer"
    """Both dim, upright."""
    ITALIC = "italic"
    """Both italic, at full ink."""
    COLOUR = "colour"
    """Both in the theme's accent, readable on the panel."""


class Loading(StrEnum):
    """The sign that speech was heard and its caption is on its way (the
    listening mark; the user's live testing, 270's FEEDBACK.md line 27:
    "The loading bar doesn't look that clean, either the three dots,
    and/or ellipsis on current previewed text")."""

    BAR = "bar"
    """Today's: a bar whose lit part sweeps across it (267)."""
    DOTS = "dots"
    """Three dots, lighting up in turn."""
    ELLIPSIS = "ellipsis"
    """An ellipsis growing after the text still being spoken - or, with
    none yet, where the bar would be."""


class OwnLabel(StrEnum):
    """How the label over the user's own speech ("You") looks."""

    AS_NOW = "as_now"
    """Today's: small, in the mic's colour, like an app's name."""
    BADGE = "badge"
    """In a small filled badge of that colour."""
    NONE = "none"
    """Not shown: the other marks say whose it is."""


class Fill(StrEnum):
    """How a caption's text is laid in the window (polyglotic-hq 309)."""

    CLAUSES = "clauses"
    """Today's: a clause a row, its translation under it."""
    STACKED = "stacked"
    """Poured: what was said fills the upper lines, its translation the
    lines below, each running on by itself."""
    PAIRED = "paired"
    """Poured line by line: a line of what was said, the line of its
    translation under it, both cut at matching places (`views.pour`)."""


class Join(StrEnum):
    """What stands between two clauses run together on a line."""

    ELLIPSIS = "ellipsis"
    """An ellipsis where one clause ends and the next begins."""
    LINE_ENDS = "line_ends"
    """And one at the end of every line that runs on to the next."""
    SPACE = "space"
    """Nothing but a space."""


class Placing(StrEnum):
    """Where a line pair's parts go in the room the pair has (polyglotic-hq
    458; the user, 2026-11-17: "placing characters in such a way to
    reducing distance between all arrow length sums ... a 3rd alternate
    lab mode could be clean even space everything"). New layout's
    (`views.flow`): the lines, and what is on each, are the same in all
    three."""

    PACKED = "packed"
    """Today's: each part straight after the one before."""
    NEAREST = "nearest"
    """Each part where its word links are shortest."""
    EVENLY = "evenly"
    """A full line's parts spread over the width, the gaps alike."""


class Palette(StrEnum):
    """Learning load's colours, unknown to known (`views.known_colours`)."""

    RED_GREEN = "red_green"
    ORANGE_BLUE = "orange_blue"


class NewFade(StrEnum):
    """How a caption that's no longer new goes to an older caption's ink."""

    INSTANT = "instant"
    GRADUAL = "gradual"


@dataclass(frozen=True, slots=True)
class CaptionLab:
    """The lab's values; the defaults are the app without the lab."""

    new_for: float = 0.0
    new_fade: NewFade = NewFade.INSTANT
    older: float = OLDER_ALPHA
    arrival_gap: float = 0.0
    line_gap: float = 0.0
    unfinished: Unfinished = Unfinished.AS_NOW
    link_px: float | None = None
    """None: Word links' Thin / Medium / Thick decides."""
    row_gap: float = 2.0
    caption_gap: float = 10.0
    loading: Loading = Loading.BAR
    older_steps: int = 1
    """Older captions dim all at once (1) or step by step, over this many
    captions (305)."""
    own_right: bool = True
    own_tint: bool = False
    own_bar: bool = False
    own_label: OwnLabel = OwnLabel.AS_NOW
    """Your own speech: on the right (the default, B: the user, 2026-11-14,
    DECISIONS #133 "pick a reasonable default"), tinted, with a bar at its
    side, and its "You" label's look (305)."""
    fill: Fill = Fill.CLAUSES
    join: Join = Join.ELLIPSIS
    """Captions fill the width: a clause a row (today's), or poured - and
    what stands between clauses then (309)."""
    load: bool = False
    load_colours: Palette = Palette.RED_GREEN
    """Learning load's mode - every word coloured by how well it's known
    (489) - and its colours."""
    flow: bool = False
    run_on: bool = False
    aligned: bool = False
    """The new layout (340): the one layout lays the captions out; with
    Line by line, captions run on into each other, and parts are lined up
    over their counterparts."""
    placing: Placing = Placing.PACKED
    """Where a line pair's parts go in its room, in New layout (458)."""

    @property
    def line_by_line(self) -> bool:
        """New layout's Line by line: where `run_on` works
        (`views.flow.flow_options`). Anywhere else it keeps its value and
        does nothing."""
        return self.flow and self.fill is Fill.PAIRED

    @property
    def lined_up(self) -> bool:
        """Parts lined up, in New layout - however captions fill the width
        (372: in Line by line only before). Without New layout `aligned`
        keeps its value and does nothing."""
        return self.flow and self.aligned

    @property
    def filled(self) -> bool:
        """Filled lines (polyglotic-hq 372): New layout, Line by line and
        captions run on, all three - what a caption window's one click
        turns on."""
        return self.line_by_line and self.run_on

    def with_filled(self, on: bool, before: "CaptionLab | None" = None) -> "CaptionLab":
        """The lab with filled lines on - New layout, Line by line, captions
        run on - or off again: those three back to what they were in
        `before` (the lab when the one click turned them on), or to the
        app's own without the lab if that isn't known (turned on in the
        Lab, or before a restart). Nothing else changes: the Lab's rows
        are the same values (the user, 2026-11-15, DECISIONS #175: "a one
        click setting ... from caption window")."""
        if on:
            return replace(self, flow=True, fill=Fill.PAIRED, run_on=True)
        was = before if before is not None and not before.filled else CaptionLab()
        # parts lined up need New layout: it stays while they are
        flow = was.flow or self.lined_up
        return replace(self, flow=flow, fill=was.fill, run_on=was.run_on)

    def with_lined_up(
        self, on: bool, before: "CaptionLab | None" = None
    ) -> "CaptionLab":
        """The lab with parts lined up on - and New layout, which they need -
        or off again: New layout back to what it was in `before` (the lab
        when the one click turned them on), kept while filled lines need
        it, and as it is if that isn't known. However captions fill the
        width stays as it is (372; the user, 2026-11-15, DECISIONS #175:
        "an independent one click setting which applies to every mode")."""
        if on:
            return replace(self, flow=True, aligned=True)
        flow = self.flow
        if before is not None and not before.lined_up:
            flow = before.flow or self.filled
        return replace(self, flow=flow, aligned=False)

    def choose(self, **changes: object) -> "CaptionLab":
        """The lab with the learner's `changes` - and what a choice needs
        to do anything (polyglotic-hq 365; the user, 2026-11-15, on
        greyed-out switches: "I can't seem to select these settings"):
        turning `run_on` on turns New layout on and Captions fill the width
        to Line by line; `aligned`, New layout alone - it lines parts up
        however captions fill the width (372); a placing of the parts other
        than packed, New layout too (458); choosing Learning load's
        colours turns it on (489); choosing what stands between
        clauses while captions don't fill the width sets them to
        Translation below (polyglotic-hq 368). Turning one off, or later
        moving what it needs away, changes nothing else: it keeps its value
        for when that comes back."""
        if changes.get("run_on") is True:
            changes = {"flow": True, "fill": Fill.PAIRED, **changes}
        if changes.get("aligned") is True:
            changes = {"flow": True, **changes}
        if changes.get("placing") in (Placing.NEAREST, Placing.EVENLY):
            changes = {"flow": True, **changes}
        if "join" in changes and self.fill is Fill.CLAUSES:
            changes = {"fill": Fill.STACKED, **changes}
        if "load_colours" in changes:
            changes = {"load": True, **changes}
        return replace(self, **changes)  # type: ignore[arg-type]

    def to_stored(self) -> dict[str, object]:
        """Only what differs from the default: an untouched lab stores `{}`,
        so a later default reaches everyone who didn't move it."""
        default = CaptionLab()
        stored: dict[str, object] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value != getattr(default, f.name):
                stored[f.name] = value.value if isinstance(value, StrEnum) else value
        return stored

    @classmethod
    def from_stored(cls, stored: object) -> "CaptionLab":
        """The lab as saved: anything missing, of the wrong type or out of
        range takes its default (an old or hand-edited file never stops
        the app)."""
        if not isinstance(stored, Mapping):
            return cls()
        found: dict[str, object] = {}
        new_for = _number(stored.get("new_for"), NEW_FOR_RANGE)
        if new_for is not None:
            found["new_for"] = new_for
        if stored.get("new_fade") in {f.value for f in NewFade}:
            found["new_fade"] = NewFade(str(stored["new_fade"]))
        older = _number(stored.get("older"), OLDER_RANGE)
        if older is not None:
            found["older"] = older
        steps = stored.get("older_steps")
        if (
            isinstance(steps, int)
            and not isinstance(steps, bool)
            and OLDER_STEPS_RANGE[0] <= steps <= OLDER_STEPS_RANGE[1]
        ):
            found["older_steps"] = steps
        if stored.get("unfinished") in {u.value for u in Unfinished}:
            found["unfinished"] = Unfinished(str(stored["unfinished"]))
        if stored.get("loading") in {k.value for k in Loading}:
            found["loading"] = Loading(str(stored["loading"]))
        if stored.get("load_colours") in {k.value for k in Palette}:
            found["load_colours"] = Palette(str(stored["load_colours"]))
        for name in (
            "own_right",
            "own_tint",
            "own_bar",
            "load",
            "flow",
            "run_on",
            "aligned",
        ):
            if isinstance(stored.get(name), bool):
                found[name] = stored[name]
        if stored.get("own_label") in {k.value for k in OwnLabel}:
            found["own_label"] = OwnLabel(str(stored["own_label"]))
        for name, within in (
            ("link_px", LINK_PX_RANGE),
            ("row_gap", ROW_GAP_RANGE),
            ("caption_gap", CAPTION_GAP_RANGE),
        ):
            value = _number(stored.get(name), within)
            if value is not None:
                found[name] = value
        if stored.get("fill") in {k.value for k in Fill}:
            found["fill"] = Fill(str(stored["fill"]))
        if stored.get("join") in {k.value for k in Join}:
            found["join"] = Join(str(stored["join"]))
        if stored.get("placing") in {k.value for k in Placing}:
            found["placing"] = Placing(str(stored["placing"]))
        gap = _number(stored.get("arrival_gap"), ARRIVAL_GAP_RANGE)
        if gap is not None:
            found["arrival_gap"] = gap
        gap = _number(stored.get("line_gap"), LINE_GAP_RANGE)
        if gap is not None:
            found["line_gap"] = gap
        return replace(cls(), **found)  # type: ignore[arg-type]


def _number(value: object, within: tuple[float, float]) -> float | None:
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and within[0] <= value <= within[1]
    ):
        return round(float(value), 2)
    return None


def older_translation(older: float) -> float:
    """An older caption's translation's ink, for what was said's `older`:
    the same share of the step as today's (0.72 -> 0.82)."""
    return round(1.0 - (1.0 - older) * _TRANSLATION_SHARE, 3)


def newness(age: float | None, lab: CaptionLab) -> float:
    """How new a caption is, 1.0 to 0.0 - 1.0 drawn at full ink, 0.0 at an
    older caption's - `age` seconds after it arrived (None: it was there
    when the window opened, or it isn't known). New for `new_for` seconds;
    then at once, or over FADE_BACK_SEC."""
    if age is None or age < 0.0:
        return 0.0
    if age < lab.new_for:
        return 1.0
    if lab.new_fade is NewFade.GRADUAL and lab.new_for > 0.0:
        gone = (age - lab.new_for) / FADE_BACK_SEC
        return max(0.0, 1.0 - gone)
    return 0.0


def by_place(place: int, lab: CaptionLab) -> float:
    """How new a caption looks by its place, counting back from the newest
    (0) - 1.0 drawn at full ink, 0.0 at an older caption's: a step less each
    caption back, over `older_steps` captions (the Lab's Older captions dim
    step by step, 305); 0.0 for all but the newest at once."""
    if place <= 0:
        return 1.0
    return max(0.0, 1.0 - place / lab.older_steps)


def clause_gap(row_gap: float) -> float:
    """The gap between clauses for a gap of `row_gap` between a clause and
    its translation: today's 8, or more, so a translation stays nearer its
    own original than the next clause."""
    return max(8.0, row_gap + CLAUSE_MORE)


def ink_between(older: float, new: float) -> float:
    """An ink part way from an older caption's (`new` 0.0) to full (1.0)."""
    return older + (1.0 - older) * new


def changes_at(age: float, lab: CaptionLab) -> float | None:
    """How long after `age` a caption's newness next changes on its own -
    when it steps back, or starts or ends its fade - or None if it won't
    (it's old, or its fade is under way: drawn every frame)."""
    if age < lab.new_for:
        return lab.new_for - age
    return None
