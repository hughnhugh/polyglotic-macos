"""Interface numbers come from the values that control the feature."""

import re

from tools.i18n.extract import read

# Allow only the part of a source that contains a fixed number. A second
# number added to the same source still needs a placeholder or its own reason.
FIXED_NUMBERS = {
    # Service policy and invite-code format, owned by the server.
    "ProblemReport": ("Kept for 30 days to fix the problem",),
    "SignInDialog": ("16 letters and digits", "7KQM-X2PD-9VHT-C4RA"),
    # These durations are the fixed pass SKUs in the checkout contract.
    "Upgrade": ("1-month pass", "3-month pass", "6-month pass", "12-month pass"),
    # OS versions and the documented Anki file column positions.
    "Help": (
        "Windows 11",
        "Windows 10 can't tell apps apart",
        "macOS 14.2",
        "1 word, 4 reading, 5 meaning, 6 sentence, 7 translation",
    ),
    # License version and the one-app exclusion mode.
    "Home": ("CC BY 4.0", "1 app + everything else"),
    # Exact endpoints with special meanings in the control.
    "Lab": (
        "0 s: only the newest",
        "100%: as bright",
        "0 s: as they come",
        "0 s: together",
    ),
    # External package capability (espeak-ng), not an app tunable.
    "LookupCard": ("over 100 languages",),
    # Opacity endpoints and readability advice.
    "Panels": (
        "0 % is no box",
        "100 % hides",
        "70 % or more keeps",
    ),
    # Keys and published HSK standard names.
    "Settings": ("F9",),
    "Words": ("HSK 3.0 (2025 exam syllabus)", "HSK 3.0 (2021 standard)"),
}


def test_interface_numbers_are_placeholders_or_fixed_copy() -> None:
    problems = []
    for message in read().messages:
        remaining = message.source
        for fixed in FIXED_NUMBERS.get(message.context, ()):
            remaining = remaining.replace(fixed, "")
        if re.search(r"\d", remaining):
            problems.append(f"{message.file}:{message.line}: {message.source}")
    assert not problems, "\n".join(problems)
