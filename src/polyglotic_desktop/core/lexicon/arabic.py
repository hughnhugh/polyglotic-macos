"""Arabic as captions write it: without the vowel marks (polyglotic-hq 380).

Wiktionary's inflection tables mark every vowel ("الْكِتَابُ"); speech
models and most text write none ("الكتاب"). A form is looked up, and kept
in a pack, as `plain` writes it: the short vowels, tanween, shadda and
sukun, the dagger alif and the tatweel taken off. Hamza and madda stay:
they are letters' own parts (أ, إ, آ), kept whole by NFC first.
"""

import unicodedata

_MARKS = dict.fromkeys([*range(0x064B, 0x0653), *range(0x0656, 0x0660), 0x0670, 0x0640])
"""Fathatan to sukun, the marks after hamza below, the dagger alif, and
the tatweel (a stretch, not a letter)."""


def plain(text: str) -> str:
    """`text` without Arabic's vowel marks: "الْكِتَابُ" -> "الكتاب"."""
    return unicodedata.normalize("NFC", text).translate(_MARKS)
