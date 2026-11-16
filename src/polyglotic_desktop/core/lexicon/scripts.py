"""A word's language by its script, where its caption row's says otherwise
(polyglotic-hq 337; decision 0129).

A caption has one language - the first the speech model names - and every
row of it is looked up in that language's dictionary. A mixed line isn't
one language: "这个iPhone真的很好" is a Chinese line with an English
word, "We had 火锅 last night" an English line with a Chinese one, "Он
сказал OK" a Russian line with an English one, and a short line the model
named wrongly is all in another. The word's script says which, where the
row's language isn't written in it:

- Chinese characters: Chinese (a Japanese or Cantonese row keeps them);
- kana: Japanese; Hangul: Korean; Thai: Thai; Greek: Greek; Hebrew:
  Hebrew; Devanagari: Hindi;
- Cyrillic: Russian (a Ukrainian, Bulgarian or Macedonian row keeps it);
- Arabic script: Arabic (a Persian row keeps it);
- Latin letters: English, in a row not written in them or of a language
  not known. In a row of a language written in Latin letters (Vietnamese,
  Spanish, French...) they stay that language's: the script can't tell
  English from it, and a Latin word in a Vietnamese line is far more often
  Vietnamese than English.

Each script's language is its commonest among the languages captions come
in (`listening.spoken`, Qwen3-ASR's 30): a guess only where the script is
shared, and the row's language wins whenever it shares the script.
"""

import unicodedata

from polyglotic_desktop.core.lexicon.chinese import is_han

SCRIPTS: dict[str, tuple[str, frozenset[str]]] = {
    "han": ("zh", frozenset({"zh", "ja", "yue"})),
    "kana": ("ja", frozenset({"ja"})),
    "hangul": ("ko", frozenset({"ko"})),
    "cyrillic": ("ru", frozenset({"ru", "uk", "bg", "mk", "sr", "be", "kk"})),
    "thai": ("th", frozenset({"th"})),
    "arabic": ("ar", frozenset({"ar", "fa", "ur"})),
    "hebrew": ("he", frozenset({"he", "yi"})),
    "greek": ("el", frozenset({"el"})),
    "devanagari": ("hi", frozenset({"hi", "mr", "ne"})),
}
"""Each script told apart: the language a word in it is taken for, and the
languages written in it - a row in one of those keeps its own."""

_NAMED = {
    "HIRAGANA": "kana",
    "KATAKANA": "kana",
    "HANGUL": "hangul",
    "CYRILLIC": "cyrillic",
    "THAI": "thai",
    "ARABIC": "arabic",
    "HEBREW": "hebrew",
    "GREEK": "greek",
    "DEVANAGARI": "devanagari",
    "LATIN": "latin",
}
"""Unicode's names for the scripts' letters begin with these."""

_NON_LATIN_ROWS = frozenset().union(*(written for _, written in SCRIPTS.values()))
"""Every row language written in a script other than Latin letters."""


def _code(row_language: str) -> str:
    """`zh-hant` -> `zh` (protocol.md's codes; as `learning.languages`
    has it, which this context doesn't import)."""
    return row_language.lower().split("-")[0]


def script_of(char: str) -> str | None:
    """The script of one character, of those told apart here (and
    "latin"); None for a digit, a mark, punctuation or another script."""
    if is_han(char):
        return "han"
    if not char.isalpha():
        return None
    name = unicodedata.name(char, "")
    if name.startswith("KATAKANA-HIRAGANA"):  # ー, the long vowel mark
        return "kana"
    return next((s for prefix, s in _NAMED.items() if name.startswith(prefix)), None)


def word_script(word: str) -> str | None:
    """A word's script: kana if it has any (食べる is Japanese), else that
    of its first letter told apart here."""
    found = [s for s in map(script_of, word) if s is not None]
    if "kana" in found:
        return "kana"
    return found[0] if found else None


def is_latin(word: str) -> bool:
    """Whether `word`'s letters are all Latin ones (English's, and accented
    Latin): at least one letter, and no other script's."""
    letters = [c for c in word if c.isalpha()]
    return bool(letters) and all(script_of(c) == "latin" for c in letters)


def written_in(word: str, row_language: str | None) -> str | None:
    """The language `word`'s script says it's in, when its row's language
    (`row_language`; None: not known) isn't written in that script - else
    None, and the row's language holds."""
    code = _code(row_language) if row_language else None
    script = word_script(word)
    if script == "latin":
        return (
            "en"
            if (code is None or code in _NON_LATIN_ROWS) and is_latin(word)
            else None
        )
    if script is None:
        return None
    taken_for, written = SCRIPTS[script]
    return taken_for if code not in written else None


def fits(word: str, language: str) -> bool:
    """Whether `language` is written in `word`'s script: a Chinese word
    fits Chinese, Japanese and Cantonese; a kana one only Japanese; a
    Latin one every language not written in another script; a word with
    no letters told apart (digits) none."""
    script = word_script(word)
    code = _code(language)
    if script is None:
        return False
    if script == "latin":
        return code not in _NON_LATIN_ROWS
    return code in SCRIPTS[script][1]
