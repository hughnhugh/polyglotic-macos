"""Policy for text a learner sends in feedback or a problem report.

Reports are read with AI assistance, so their free text is untrusted data rather
than instructions. Cleaning is deterministic and preserves ordinary writing.
"""

import re
import unicodedata

PROBLEM_TEXT_LIMIT = 2_000
SUGGESTION_TEXT_LIMIT = 1_500
QUESTION_TEXT_LIMIT = 1_500
WORK_WITH_US_TEXT_LIMIT = 5_000  # Existing protocol allowance; unchanged by 912.
REPLY_TO_LIMIT = 254  # RFC 5321's maximum mailbox length.
COUNTER_THRESHOLD = 0.8  # Quiet until useful; avoids noise while drafting.
LOG_TEXT_LIMIT = 256 * 1024  # Keeps the request comfortably below 512 KiB.

TEXT_LIMITS = {
    "problem": PROBLEM_TEXT_LIMIT,
    "suggestion": SUGGESTION_TEXT_LIMIT,
    "question": QUESTION_TEXT_LIMIT,
    "work_with_us": WORK_WITH_US_TEXT_LIMIT,
}

_REMOVED_FORMATS = (
    frozenset(range(0x200B, 0x200E))
    | {0x2060, 0xFEFF}
    | frozenset(range(0x202A, 0x202F))
    | frozenset(range(0x2066, 0x206A))
)


def clean_report_text(text: str) -> str:
    """Return NFC text without invisible controls or excessive blank lines."""
    normal = unicodedata.normalize("NFC", text)
    visible = "".join(
        character
        for character in normal
        if ord(character) not in _REMOVED_FORMATS
        and (character in "\n\t" or unicodedata.category(character) != "Cc")
    )
    # Three newlines are two blank lines; further blank lines add no meaning.
    return re.sub(r"\n{4,}", "\n\n\n", visible).strip()


def limited_clean_text(text: str, limit: int) -> str:
    """Clean then limit by Unicode code points (Python string characters)."""
    # Cutting can leave whitespace at the new end; clean once more so the value
    # shown in a field is stable when it is cleaned again for preview or send.
    return clean_report_text(clean_report_text(text)[:limit])
