"""Everyday talk (polyglotic-hq 485, 491; desktop decision 0227): how
common a word is in speech, beside how common the pack says it is in
writing - for Learning's conversation words (`core.learning.theme`), which
must never light 嗯, "um" or 谢谢.

- **A word's spoken rank:** its place among the words subtitles say
  (OpenSubtitles 2018's counts; `spoken_ranks`, written by
  `tools/spoken_ranks.py`), kept only where the pack ranks it rarer. The
  packs rank by written text, which places speech far too rare: 谢谢 at
  6,361 in writing is 82nd in speech; 就是说 11,167th; "um" past 5,000.
- **Fillers:** hesitation sounds and interjections (嗯, 呃, "um", "uh-huh")
  - never a word to learn from a conversation, whatever its ranks.
- **Numbers spelled out** (English: "fourteen", "thousand"): never what a
  conversation is about.

Mandarin and English so far; other languages have neither (their words
are placed by their packs alone).
"""

from polyglotic_desktop.core.lexicon import spoken_ranks


def _ranks(pairs: str) -> dict[str, int]:
    tokens = pairs.split()
    return {w: int(n) for w, n in zip(tokens[::2], tokens[1::2], strict=True)}


def _split(words: str) -> frozenset[str]:
    return frozenset(words.split())


class SpokenWords:
    """One language's spoken ranks and fillers."""

    def __init__(self, ranks: dict[str, int], fillers: frozenset[str]) -> None:
        self._ranks = ranks
        self.fillers = fillers

    def rank(self, headword: str) -> int | None:
        """The word's rank in speech, where the pack ranks it rarer; None:
        not among the commonest spoken words, or no rarer in writing."""
        return self._ranks.get(headword)

    def is_filler(self, headword: str) -> bool:
        return headword in self.fillers


MANDARIN = SpokenWords(
    _ranks(spoken_ranks.MANDARIN),
    _split(
        "嗯 呃 啊 哦 噢 喔 唉 哎 诶 欸 呀 嘛 呗 哈 嘿 哇 啦 咯 哼 嗷 嘞 啧 哟 呦 "
        "嗯嗯 哈哈 哎呀 哎哟 呵呵 嘻嘻 哦哦 啊啊"
    ),
)
"""Fillers: the interjections and hesitation sounds of Mandarin speech."""

ENGLISH = SpokenWords(
    _ranks(spoken_ranks.ENGLISH),
    _split(
        "um uh er erm hmm mm mhm uh-huh mm-hmm ah oh ooh huh hey wow yeah yep "
        "yup nope okay ok gonna wanna gotta kinda sorta"
    ),
)
"""Fillers: hesitation sounds, interjections and spoken run-togethers."""

ENGLISH_NUMBERS = _split(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
    "thirty forty fifty sixty seventy eighty ninety hundred thousand million "
    "billion trillion"
)
"""English's cardinal numbers spelled out: words to learn, but never what a
conversation is about (491's live captions lit "fourteen" and "twenty" in a
talk about sanctions). Mandarin's are numbers already (二十: `is_number`)."""
