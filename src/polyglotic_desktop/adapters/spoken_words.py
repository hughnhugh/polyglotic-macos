"""Dictionary word counts for speaking pace, with ICU/spaced fallback.

Uses the same dictionary word split that lookups use when installed (Sudachi
mode C for Japanese, CC-CEDICT longest-match for Chinese, pack splits for
other unspaced/dictionary-split languages), and falls back to the operating
system's ICU word iterator (then spaced word runs) otherwise.
"""

import ctypes
import ctypes.util
import logging
import re
import sys
from collections.abc import Callable
from functools import cache

from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.core.learning.languages import learned_code
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, is_han
from polyglotic_desktop.core.listening.pace import WordCount, spaced_word_count
from polyglotic_desktop.ports.word_split import WordSplit

log = logging.getLogger(__name__)

# ICU's UBreakIteratorType and UWordBreak enums (unicode/ubrk.h).
_WORD = 1
_WORD_NONE_LIMIT = 100


class _WordBreaks:
    def __init__(self, name: str) -> None:
        lib = ctypes.CDLL(name)
        # Linux distributions export ICU's ABI major in the symbol names.
        version = re.search(r"\.so\.(\d+)", name)
        suffix = "_" + version[1] if version else ""
        self.open = getattr(lib, "ubrk_open" + suffix)
        self.open.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.open.restype = ctypes.c_void_p
        self.next = getattr(lib, "ubrk_next" + suffix)
        self.status = getattr(lib, "ubrk_getRuleStatus" + suffix)
        self.close = getattr(lib, "ubrk_close" + suffix)
        for fn in (self.next, self.status, self.close):
            fn.argtypes = (ctypes.c_void_p,)
        self.next.restype = self.status.restype = ctypes.c_int32
        self.close.restype = None

    def count(self, text: str, language: str | None) -> int:
        # All desktop targets are little-endian. ICU lengths are UTF-16 units,
        # including both units of a supplementary character.
        data = text.encode("utf-16-le", errors="surrogatepass")
        error = ctypes.c_int32()
        iterator = self.open(
            _WORD,
            (language or "").encode("ascii", "ignore"),
            data,
            len(data) // 2,
            ctypes.byref(error),
        )
        if not iterator:
            return spaced_word_count(text, language)
        try:
            if error.value > 0:  # ICU uses negative codes for successful fallbacks
                return spaced_word_count(text, language)
            count = 0
            while self.next(iterator) != -1:
                if self.status(iterator) >= _WORD_NONE_LIMIT:
                    count += 1
            return count
        finally:
            self.close(iterator)


@cache
def _word_breaks() -> _WordBreaks | None:
    if sys.platform == "win32":
        name = "icu.dll"
    elif sys.platform == "darwin":
        name = "/usr/lib/libicucore.A.dylib"
    else:
        name = ctypes.util.find_library("icuuc")
    if name:
        try:
            return _WordBreaks(name)
        except (OSError, AttributeError):
            pass
    logging.getLogger(__name__).warning(
        "System word segmentation unavailable for speaking pace"
    )
    return None


def count_spoken_words(text: str, language: str | None) -> int:
    segmenter = _word_breaks()
    if segmenter is None:
        return spaced_word_count(text, language)
    return segmenter.count(text, language)


def count_chinese_words(
    dictionary: ChineseDictionary,
    text: str,
    fallback: WordCount = count_spoken_words,
) -> int:
    """Count Chinese dictionary words plus any non-Han words/numbers in `text`."""
    total = 0
    for start, end in dictionary.split(text):
        if is_han(text[start]):
            total += 1
        else:
            piece = text[start:end]
            if any(char.isalnum() for char in piece):
                total += fallback(piece, None)
    return total


type PaceDictionary = ChineseDictionary | BasicDictionary | WordSplit


def spoken_word_counter(
    dictionary_for: Callable[[str], PaceDictionary | None],
    fallback: WordCount = count_spoken_words,
) -> WordCount:
    """Build a pace word counter backed by installed lookup word splits.

    Uses the Chinese dictionary's split, Japanese Sudachi mode C, or any other
    non-spaced dictionary split installed for the caption's language, falling
    back to ICU/spaced word counts when no dictionary split applies.
    """

    def count(text: str, language: str | None) -> int:
        if not text or not text.strip():
            return 0
        if language:
            dictionary = dictionary_for(learned_code(language))
            if dictionary is not None:
                try:
                    if isinstance(dictionary, ChineseDictionary):
                        return count_chinese_words(dictionary, text, fallback)
                    if isinstance(dictionary, BasicDictionary):
                        if not dictionary.is_absent and not isinstance(
                            dictionary.word_split, SpacedSplit
                        ):
                            return len(dictionary.split(text))
                    elif not isinstance(dictionary, SpacedSplit):
                        return len(dictionary.words(text))
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "Dictionary word count fell back to system breaks: %s",
                        type(exc).__name__,
                    )
        return fallback(text, language)

    return count
