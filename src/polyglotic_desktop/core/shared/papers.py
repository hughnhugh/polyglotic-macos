"""The papers the app links to, and the tester agreement's version: one place.

The privacy notice and the tester agreement are pages on our website,
opened in the learner's browser - never shown inside the app, so the app
and the site can't drift apart (polyglotic-hq project 185). Their
addresses and the agreement's version are here and nowhere else in the
app; the site names the same things in its `site.toml` and pages.

- **The address** is the site's (`SITE`), on the same domain as
  `main.SERVER` and `main.UPDATES` (decision 0015) and changed with
  them - a test keeps the three on one domain.
- **The tester agreement's version** names the document and the date of
  its words, as the site's `content/consent.json` names its consent
  wording (`tester-2026-11-11`: the alpha's short agreement, polyglotic-hq
  040's TESTER-AGREEMENT-ALPHA-SHORT.md; before it `tester-2026-11-08`,
  DECISIONS.md #80). New words, new version: the app then asks once more at
  start, and the server keeps which one each tester accepted
  (protocol.md, `consent`'s `agreement`).

Plain values only: no logic, no Qt.
"""

SITE = "https://polyglotic.io"
"""The website (the domain since 2026-11-09)."""

PRIVACY_NOTICE = f"{SITE}/privacy/"
"""The privacy notice, version 2 (polyglotic-hq 040's PRIVACY.md)."""

MAINLAND_PRIVACY_NOTICE = f"{SITE}/zh-hans/privacy/"
TERMS = f"{SITE}/terms/"
AUTO_RENEWAL_TERMS = f"{TERMS}#auto-renewal"

TESTER_AGREEMENT = f"{SITE}/tester-agreement/"
"""The alpha's tester agreement (polyglotic-hq 040's
TESTER-AGREEMENT-ALPHA-SHORT.md)."""

TESTER_AGREEMENT_VERSION = "tester-2026-11-11"
"""The tester agreement's words this app asks a tester to accept."""

PLUS = f"{SITE}/plus/"
"""Where a learner gets a pass for Plus (polyglotic-hq 191's P4)."""

STATUS_PAGE = f"{SITE}/status/"
"""The server's status, checked from the learner's browser (polyglotic-hq
540, site #99): Help links to it, and Home while the server can't be
reached and the problem may be ours (563)."""

HELP_ANKI = f"{SITE}/help/your-words-and-anki/"
"""The site's help on putting your words into Anki - the deck file, and
importing the CSV: Words' Export for Anki links to it (polyglotic-hq 250).
The site makes each help section a page named from its heading ("Your
words and Anki"), and a test there keeps that one."""

MINIMUM_AGE = 13
"""Polyglotic is for people this old or older, and older where a country's
own minimum is higher: the age is the highest of this and the country's
(the site's content/minimum_ages.json has each country's; the privacy
notice, section 9, names them; the tester agreement, clause 1). The papers
say it; no screen does (the user, 2026-11-11: "I'd prefer it to be 13")."""
