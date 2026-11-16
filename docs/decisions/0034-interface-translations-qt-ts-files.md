# 0034 The interface is translated through Qt's .ts files, read from our own wrappers, with English's counts in a file too

- **Status:** accepted
- **Date:** 2026-11-07
- **Decided by:** Claude, for polyglotic-hq project 156 (the user,
  2026-11-07: "good internationalisation design in this app ... at least
  language support for each of the languages that we are targetting";
  DECISIONS.md #61 C: a Chinese interface for Chinese speakers learning
  English). Reversible - a technical choice.

## Situation

Every interface string already went through Qt's `translate()` - each
module through a one-line wrapper, `_tr("Start listening")` calling
`QApplication.translate("Home", text)` - but there was no translation file
at all. So:

- Qt's own tool, `pyside6-lupdate`, saw 154 of the 615 strings: it can't
  follow a wrapper, and gives a call inside a class the class's name as
  its context, not the wrapper's.
- Qt's plural forms (`translate(..., n)` with `%n`) need a translation file
  even in English; without one the source's "(s)" shows, which is how "1
  caption(s)" reached the screen (polyglotic-hq 133). 137 worked round it
  by writing English's two forms by hand (`if count == 1`), which no other
  language can follow (Russian has three forms, Chinese one).
- Numbers were grouped by Python (`f"{n:,}"`) and lists joined with ", ",
  whatever the language.

## Decision

- **Qt's formats, our extractor.** `tools/i18n` reads the code with
  Python's `ast` the way it runs - each module's wrapper and its context,
  `self.tr` in its class's context, `translate("Context", ...)`,
  `QT_TRANSLATE_NOOP` - and writes one `.ts` file per interface language in
  `translations/`, keeping every translation already there. `lrelease`
  (PySide6's) compiles each to the `.qm` the app loads, in
  `ui/assets/translations/` (packed with the other assets).
  `python -m tools.i18n update` does both. *(Amended 2026-11-08: the
  `.qm` files are built, not committed - see "Amendments".)*
- **Counts through Qt's plural forms, English included.** A count's text
  goes through a `_trn(text, n)` wrapper with `%n` (or `%Ln`, digits
  grouped) and "(s)": `_trn("Heard in %Ln caption(s)", count)`. English's
  file, `polyglotic_en.ts`, holds only counts - two forms each, written
  from "(s)"/"(es)" when a count is added and fixed by hand where English
  is irregular ("heard once"). The app installs it beneath the chosen
  language, so a count a translator hasn't reached reads as English, not
  "(s)".
- **The interface language** is a setting (`interface_language`; Settings,
  Language): "Like this PC" ("Like Windows" until 2026-11-08, polyglotic-hq 179; the default - the first of Windows' display
  languages that's offered, else English) or one offered language. It
  applies at the next start. Traditional Chinese Windows gets English
  until a Traditional interface exists, not Simplified unasked.
  `ui/interface_language.py` picks it and installs our file, English's
  counts, and Qt's own (`qtbase_<language>.qm`: OK, Cancel, Copy...).
- **Numbers, dates and lists by the language:** `QLocale.setDefault` -
  Windows' regional format when it's in the interface's language (an
  Australian English Windows keeps its dates and Monday first), else the
  interface language's own - then `QLocale().toString(n)`, `%Ln` and
  `QLocale().createSeparatedList()`. The patterns for counts, ratios,
  durations and dates are in `translations/README.md`.
- **A translation is a draft until a native speaker reviews it:** Qt's
  "unfinished" state with text in it. `lrelease` includes drafts, so they
  show; Qt Linguist's "done" mark is the review (`translations/README.md`).
- **Enforced by tests** (`tests/ui/test_translations.py`): nothing the
  extractor can't translate (an f-string or joined string handed to a
  wrapper, "(s)" outside a count, a count without `%n`, a string
  translated at import - before `main` installs the language); every `.ts` up to
  date with the code (and, until 2026-11-08, every `.qm` compiled from
  its `.ts`); English's
  counts read as English; each translation keeps its `{placeholders}` and
  its count, so `.format()` can't fail on one.

## Why

- `.ts` is what translators' tools read - Qt Linguist (free, offline, for
  a reviewer who doesn't code), Weblate and Crowdin - with plural forms per
  language and a reviewed / not reviewed state. The app's text already
  went through Qt's `translate()`; gettext (`.po`) would have meant
  rewriting every call and losing Qt's own translations for its buttons.
- Our own extractor rather than rewriting 524 wrapper calls as
  `QApplication.translate("Home", "...")` for lupdate: the wrappers are
  shorter, every agent already writes them, and the extractor can fail on
  what can't be translated, which lupdate can't.
- Qt's plural forms rather than an English-only helper (`plural(n, "word",
  "words")`): a helper has no answer for a language with one form or three;
  Qt's forms come from each language's rules, and the English file costs
  one small file.
- At the next start rather than at once: every window sets its text as
  it's built; changing it live means a `LanguageChange` handler in every
  one. Changing the language is rare.

## What would make us reverse it

- A translation service that needs another format (`.po`, XLIFF) - Weblate
  and Crowdin both read `.ts`, so unlikely.
- The `.ts`-up-to-date test costing more in merge conflicts between
  parallel pull requests than it saves.
- Learners asking to switch language without restarting.

## How we'd reverse it

- Another format: a writer beside `tools/i18n/ts.py`; the extractor and
  the code's wrappers stay.
- Conflicts: drop the up-to-date part of the test and run `update` at a
  string freeze before each release instead (`translations/README.md`
  describes both).
- Switching live: a `changeEvent(LanguageChange)` in each window that sets
  its text again - a few hours per window.

## Amendments

### 2026-11-08: the `.qm` files are built, not committed (polyglotic-hq 179)

- **Situation:** every pull request that changed interface text also
  changed the three committed `.qm` files, and two such pull requests
  always conflicted in them - binaries git can't merge. #210 and #224
  needed hand rebuilds on 2026-11-07, with several agents changing text
  at once.
- **Change:** the `.qm` files are git-ignored and compiled from the `.ts`
  files by `python -m tools.i18n build` - before the tests
  (`tests/conftest.py`), in CI's checks and UI lab jobs, by the UI lab
  itself and by the package build (`tools/package/build.py`, which lists
  them among the parts the packed app needs). `lrelease` is PySide6's own
  copy on every platform. The `.ts` files stay committed - they're the
  source, and what reviewers edit - and the test that each `.ts` is up to
  date with the code stays. The test that each `.qm` matched its `.ts` is
  gone: nothing committed can drift. A test checks they're ignored and
  that none is committed.
- **What it costs:** running the app from source needs
  `python -m tools.i18n build` once (or a test run) before the
  translations show; without them the app starts in English and counts
  read "(s)", as before 0034.
- **How we'd reverse it:** un-ignore the folder, run `update`, commit the
  three files and put the byte comparison back in `problems()`.
