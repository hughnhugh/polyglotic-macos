"""What the interface says about when the mic is sent (polyglotic-hq 576).

Since a new learner's first window shows their speech from the start
(decision 0220), and dictation and re-speaking open the mic while their key
is held (0274), no switch is the only way the mic reaches the server. Seven
notes said "sent to the server only while this is on" (or "while you hold
the key") as if it were; each now says what it covers - "for your
captions", "For dictation" - as the privacy notice 3.4 and Help's mic topic
do."""

import re

from tools.i18n import extract

SENT_ONLY_WHILE = re.compile(
    r"\b(mic|microphone|voice|speech)\b.*\b(sent|goes)\b.*\bonly while\b", re.IGNORECASE
)
"""A sentence saying the mic (or the learner's voice or speech) is sent only
while something is so."""
SAYS_WHAT_IT_COVERS = re.compile(r"\bfor (your captions|dictation)\b", re.IGNORECASE)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def test_no_note_says_one_switch_is_the_only_way_the_mic_is_sent() -> None:
    claims = [
        f"{message.file}:{message.line}: {sentence}"
        for message in extract.read().messages
        for sentence in sentences(message.source)
        if SENT_ONLY_WHILE.search(sentence) and not SAYS_WHAT_IT_COVERS.search(sentence)
    ]
    assert claims == [], "\n".join(claims)


def test_the_check_finds_the_old_claims() -> None:
    """The notes as they were before 576, which the check must refuse."""
    for old in (
        "Your microphone is sent to the server only while this is on",
        'Shown as "You". Your mic is sent to the server only while it\'s on.',
        (
            "My speech: shown in {windows} - sent to the server only while a "
            "window shows it"
        ),
        (
            "Your voice goes to our server only while you hold the key, and "
            "nothing is kept."
        ),
    ):
        assert any(
            SENT_ONLY_WHILE.search(s) and not SAYS_WHAT_IT_COVERS.search(s)
            for s in sentences(old)
        ), old
