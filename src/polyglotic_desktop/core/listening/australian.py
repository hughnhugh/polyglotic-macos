"""English in Australian spelling: what dictation types when the learner asks for it.

The speech model writes US spelling and has no setting for another
(polyglotic-hq 283, the user's feedback: "an option for Australian
English"). Australian spelling follows the Macquarie Dictionary's first
spellings: colour, centre, organise, analyse, travelled, defence,
catalogue, grey.

A word list and a few rules that are safe on their own:
- `-ize` -> `-ise` and `-yze` -> `-yse`, with their endings (realised,
  organisation, analysing) - never in size and its compounds, prize,
  seize, maize, Belize;
- `-or` -> `-our` for a list of words, with the endings that keep the
  `u` (colourful, favourite, neighbourhood) - not those that drop it
  (humorous, honorary, laborious, vigorous);
- the rest word by word: `-er` -> `-re` (centre, theatre, litre), a
  doubled `l` (travelled, cancelling, jewellery), `-ense` -> `-ence`
  (defence), `-og` -> `-ogue` (catalogue), and a few others (grey,
  aluminium, mum, pyjamas, mould, sceptical, manoeuvre).

Words whose spelling depends on their meaning are left as they are:
practice / practise, license / licence, meter / metre, check / cheque,
tire / tyre, program (Australia's government writes "program"), dialog,
judgment. A word's case is kept: Colour, COLOUR.
"""

import re

_OUR_STEMS = (
    "armor",
    "behavior",
    "candor",
    "clamor",
    "color",
    "demeanor",
    "endeavor",
    "favor",
    "fervor",
    "flavor",
    "glamor",
    "harbor",
    "honor",
    "humor",
    "labor",
    "neighbor",
    "odor",
    "parlor",
    "rigor",
    "rumor",
    "savior",
    "savor",
    "splendor",
    "tumor",
    "valor",
    "vapor",
    "vigor",
)
"""Words written `-or` in the US and `-our` in Australia."""

_OUR_ENDINGS = (
    "",
    "s",
    "ed",
    "ing",
    "ful",
    "fully",
    "less",
    "able",
    "ably",
    "ite",
    "ites",
    "itism",
    "hood",
    "hoods",
    "ly",
    "er",
    "ers",
)
"""The endings that keep `-our`'s `u` (colourful, favourite, neighbourhood);
`-ous`, `-ary`, `-ific` and `-ious` drop it (humorous, honorary) and
aren't here."""

_WORDS = {
    # -er -> -re
    "center": "centre",
    "centers": "centres",
    "centered": "centred",
    "centering": "centring",
    "theater": "theatre",
    "theaters": "theatres",
    "fiber": "fibre",
    "fibers": "fibres",
    "liter": "litre",
    "liters": "litres",
    "caliber": "calibre",
    "somber": "sombre",
    "meager": "meagre",
    "luster": "lustre",
    "saber": "sabre",
    "specter": "spectre",
    "kilometer": "kilometre",
    "kilometers": "kilometres",
    "centimeter": "centimetre",
    "centimeters": "centimetres",
    "millimeter": "millimetre",
    "millimeters": "millimetres",
    "maneuver": "manoeuvre",
    "maneuvers": "manoeuvres",
    "maneuvered": "manoeuvred",
    "maneuvering": "manoeuvring",
    # a doubled l
    "traveled": "travelled",
    "traveling": "travelling",
    "traveler": "traveller",
    "travelers": "travellers",
    "canceled": "cancelled",
    "canceling": "cancelling",
    "labeled": "labelled",
    "labeling": "labelling",
    "modeled": "modelled",
    "modeling": "modelling",
    "fueled": "fuelled",
    "fueling": "fuelling",
    "leveled": "levelled",
    "leveling": "levelling",
    "signaled": "signalled",
    "signaling": "signalling",
    "totaled": "totalled",
    "totaling": "totalling",
    "marveled": "marvelled",
    "marveling": "marvelling",
    "counseled": "counselled",
    "counseling": "counselling",
    "counselor": "counsellor",
    "counselors": "counsellors",
    "channeled": "channelled",
    "channeling": "channelling",
    "tunneled": "tunnelled",
    "quarreled": "quarrelled",
    "jeweler": "jeweller",
    "jewelers": "jewellers",
    "jewelry": "jewellery",
    "enrollment": "enrolment",
    "fulfill": "fulfil",
    "fulfills": "fulfils",
    "fulfillment": "fulfilment",
    "skillful": "skilful",
    "willful": "wilful",
    "installment": "instalment",
    # -ense -> -ence
    "defense": "defence",
    "defenses": "defences",
    "offense": "offence",
    "offenses": "offences",
    "pretense": "pretence",
    # -og -> -ogue
    "catalog": "catalogue",
    "catalogs": "catalogues",
    "analog": "analogue",
    "prolog": "prologue",
    "epilog": "epilogue",
    # one by one
    "gray": "grey",
    "grays": "greys",
    "grayish": "greyish",
    "aluminum": "aluminium",
    "mom": "mum",
    "moms": "mums",
    "pajamas": "pyjamas",
    "plow": "plough",
    "mold": "mould",
    "molds": "moulds",
    "moldy": "mouldy",
    "smolder": "smoulder",
    "skeptic": "sceptic",
    "skeptics": "sceptics",
    "skeptical": "sceptical",
    "skepticism": "scepticism",
    "pediatric": "paediatric",
    "pediatrician": "paediatrician",
    "anesthetic": "anaesthetic",
    "anemia": "anaemia",
    "estrogen": "oestrogen",
    "fetus": "foetus",
    "orthopedic": "orthopaedic",
    "mustache": "moustache",
    "cozy": "cosy",
    "aging": "ageing",
    "artifact": "artefact",
    "artifacts": "artefacts",
    "licorice": "liquorice",
    "yogurt": "yoghurt",
    "airplane": "aeroplane",
    "airplanes": "aeroplanes",
    "behavioral": "behavioural",
    "armory": "armoury",
    "savory": "savoury",
    "flavorsome": "flavoursome",
    "colorist": "colourist",
}
"""Single words: US spelling -> Australian."""

for _stem in _OUR_STEMS:
    for _ending in _OUR_ENDINGS:
        _WORDS.setdefault(_stem + _ending, _stem[:-2] + "our" + _ending)

_SIZE = re.compile(
    r"(?:cap|down|re|over|under|up|super|out|mid|bite|pint|life|king|queen|full|half|"
    r"plus|wide|man|economy|family|jumbo|mini|large|small)?siz(?:e|es|ed|ing|er|ers)"
)
"""Size and its compounds: their `-ize` is the word size, not the ending."""

_NOT_IZE = frozenset({"belize", "baize", "maize", "prize", "seize", "assize"})
"""Words ending `-ize` whose `-ize` isn't the ending (with prize's and
seize's forms caught by the stem's length)."""

_IZE = re.compile(
    r"(?P<stem>[a-z]{3,})(?P<z>iz|yz)(?P<end>e|es|ed|ing|er|ers|ation|ations)"
)
"""`-ize`, `-yze` and their endings, after a stem of three letters or more
(so prize, seize and size, whose stems are shorter, never match)."""

_WORD = re.compile(r"[A-Za-z]+")


def australian_spelling(text: str) -> str:
    """`text` (English) with US spellings in Australian spelling; anything
    else - other languages' words, numbers, punctuation - as it was."""
    return _WORD.sub(lambda m: _word(m.group()), text)


def _word(word: str) -> str:
    lower = word.lower()
    australian = _WORDS.get(lower) or _ise(lower)
    if australian is None or australian == lower:
        return word
    return _cased_like(word, australian)


def _ise(lower: str) -> str | None:
    if lower in _NOT_IZE or _SIZE.fullmatch(lower):
        return None
    found = _IZE.fullmatch(lower)
    if found is None:
        return None
    z = "is" if found["z"] == "iz" else "ys"
    return f"{found['stem']}{z}{found['end']}"


def _cased_like(word: str, australian: str) -> str:
    """`australian` in `word`'s case: all capitals, a capital first, or as
    it is."""
    if len(word) > 1 and word.isupper():
        return australian.upper()
    if word[:1].isupper():
        return australian[:1].upper() + australian[1:]
    return australian
