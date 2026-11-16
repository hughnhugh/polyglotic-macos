"""Chinese in Traditional characters, from Simplified (polyglotic-hq 375;
decision 0164).

The speech model writes Mandarin as it was trained to - mostly in
Simplified characters. A learner who reads Traditional chooses "Show
Mandarin in: Traditional", and each caption's Chinese is converted on the
PC, before anything else sees it: the caption window, the transcript, copy,
lookups and saved words' lines all have the Traditional text.

**One character for one.** Every conversion keeps the text's length in
code points, so a span the server sent (a word link's, protocol.md) still
marks the same characters, and so does a selection or a word found in the
line. A table that would change a length is refused when it's made.

**Phrase-aware**, as OpenCC is: the longest phrase the table has at each
place wins (头发 -> 頭髮 "hair", 发展 -> 發展 "develop"), then the
character's own (发 -> 發). The table is OpenCC's (Apache-2.0), with
Taiwan's standard forms (為, 裡, 著: CC-CEDICT's own, so a lookup finds
the word's entry rather than a "variant of" one), built by
`tools/traditional_table.py` and read by `adapters.traditional_table`.
"""

from collections import Counter
from collections.abc import Mapping

from polyglotic_desktop.core.lexicon.chinese import is_han


class TableError(ValueError):
    """A conversion table that would change a text's length."""


class TraditionalChinese:
    """Simplified Chinese to Traditional, one character for one.

    `table`: Simplified -> Traditional, single characters and phrases, each
    pair the same length. Text that isn't Chinese characters is left as it
    is; a character the table hasn't got is its own Traditional form."""

    def __init__(self, table: Mapping[str, str]) -> None:
        for simplified, traditional in table.items():
            if not simplified or len(simplified) != len(traditional):
                raise TableError(f"{simplified!r} -> {traditional!r}")
        self._table = dict(table)
        self._longest = max(map(len, self._table), default=1)

    def simplified_of(self) -> dict[str, str]:
        """Each Traditional character this converter writes in place of
        another -> that Simplified character (for one written for several,
        the one it is written for most in the table: 乾 -> 干, from 乾淨,
        乾燥...). What `ChineseDictionary.read_traditional` takes, so a
        converted line splits as its Simplified one did."""
        sources: dict[str, Counter[str]] = {}
        for simplified, traditional in self._table.items():
            for s, t in zip(simplified, traditional, strict=True):
                if s != t:
                    sources.setdefault(t, Counter())[s] += 1
        return {t: found.most_common(1)[0][0] for t, found in sources.items()}

    def convert(self, text: str) -> str:
        """`text` in Traditional characters, the same length."""
        if not any(is_han(c) for c in text):
            return text
        table, longest = self._table, self._longest
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            if not is_han(text[i]):
                out.append(text[i])
                i += 1
                continue
            j = i  # a run of Chinese characters: phrases never cross out of it
            while j < n and is_han(text[j]):
                j += 1
            while i < j:
                for size in range(min(longest, j - i), 0, -1):
                    found = table.get(text[i : i + size])
                    if found is not None:
                        out.append(found)
                        i += size
                        break
                else:
                    out.append(text[i])
                    i += 1
        return "".join(out)
