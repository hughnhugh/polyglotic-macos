# The interface's translations

Polyglotic's own words - menus, buttons, help, notes - in each interface
language (decision 0034). Not the captions: those are translated by the
server.

| File | What it holds |
|---|---|
| `polyglotic_en.ts` | English's counts only: two forms each ("1 caption", "3 captions") |
| `polyglotic_zh_CN.ts` | Simplified Chinese: every string - a draft for a native speaker's review (2026-11-07) |
| `GLOSSARY-zh_CN.md` | Our Chinese words for the app's own terms, and how the Chinese is written - use them every time |
| `polyglotic_zh_TW.ts` | Traditional Chinese, as Taiwan writes it (for Taiwan, Hong Kong and Macau): every string - drafted from the Simplified with OpenCC and Taiwan's words, for a native reader's review (2026-11-07) |
| `GLOSSARY-zh_TW.md` | Where Taiwan's words differ from the Simplified glossary, and how the draft was made |
| `polyglotic_<code>.ts`, `GLOSSARY-<code>.md` | Spanish (es), French (fr), German (de), Portuguese as Brazil writes it (pt_BR, for Portugal too), Italian (it), Japanese (ja), Korean (ko), Vietnamese (vi), Indonesian (id), Turkish (tr), Russian (ru), Polish (pl), Dutch (nl), Ukrainian (uk), Filipino (fil), Thai (th), Hindi (hi), Malay (ms), Czech (cs): every string, machine drafts by Claude (polyglotic-hq 294, 2026-11-13) for a native reader's review, each with its glossary |

The app loads the compiled `.qm` files from
`src/polyglotic_desktop/ui/assets/translations/`. They're built from the
`.ts` files, not committed (decision 0034, amended 2026-11-08): the tests,
the UI lab, CI and the package build compile them, and
`uv run python -m tools.i18n build` does it by hand - for running the app
from source before the tests have run.

## Reviewing a language (no code)

1. Open the `.ts` file in **Qt Linguist** - free, from the Qt site, or
   `uv run pyside6-linguist translations/polyglotic_<language>.ts` in this
   repo.
2. Each string shows the English, the translation, where it's used and
   any note for the translator. A **"?"** means a draft no native speaker
   has reviewed yet; a **tick** means reviewed.
3. Correct the translation if it's wrong, then mark it done (Ctrl+Enter).
   Keep `{names}` in braces exactly as they are (they're filled in by the
   app), and `%n` / `%Ln` (the number).
4. Save, and send the file back (or open a pull request with it). Then
   `uv run python -m tools.i18n update` compiles it; the tests check
   nothing was broken.

A reviewer who'd rather not install anything works in a spreadsheet
instead: `uv run python -m tools.i18n sheet zh_CN review.csv` makes one (a
row per string: where it's used, the English, the note, the translation
now). The reviewer puts anything in **ok** where it's right, writes the
right Chinese in **correction** where it isn't, and sends it back;
`uv run python -m tools.i18n apply zh_CN review.csv` puts both in, marked
reviewed, and refuses (and lists) a correction that loses a `{name}` or
the number. Excel, Numbers, LibreOffice and Google Sheets all open it.

**A friend who speaks the language, ten minutes:** the same sheet, but
only the 60 strings the interface shows most, most first, each with where
it is ("Home", "a caption window (on 89 of the UI lab's screens)"):

```
uv run python -m tools.ui_lab seen          # which strings each screen shows (once)
uv run python -m tools.i18n sheet de review-de.csv --most-seen 60
```

`apply` takes it back the same way.

What to look at, in order: the words in the glossary; anything a learner
sees in the first minute (the first-run questions, Home, a caption
window); text that's cut off in the screenshots of each state in the UI
lab (`uv run python -m tools.ui_lab --language zh_CN --out build/ui-lab-zh`).
A symbol after Chinese text (▾, ⚙) comes from Segoe UI Symbol
(`style.use_symbols`); the lab's `missing_glyph` check fails on any
character drawn as a box, in every language CI runs (project 176).

## Changing the interface's text (developers and agents)

- Every string a learner sees goes through the module's `_tr("...")`, or
  `_trn("... %n thing(s)", n)` for a count - never an f-string, never
  "(s)" outside a count. Names go in `{braces}`, filled with `.format()`.
- A note for the translator: a `#: note` comment on the line above the
  call.
- Then `uv run python -m tools.i18n update`: new strings join each `.ts`
  (English's counts get their two forms - fix them by hand if English is
  irregular), and every `.qm` is compiled again (for your checkout only:
  they aren't committed). The tests fail until you do.
- Draft each new string in every language, with the glossary's words; it
  stays a draft ("?") until a native speaker reviews it. A string you
  can't draft stays empty: the app shows its English - and the tests fail
  for an offered language until it's drafted.

## Drafting a language (polyglotic-hq 294, decision 0087)

```
uv run python -m tools.i18n draft de                       # the work
uv run python -m tools.i18n draft de --answers answers.tsv # the answers in, checked
```

1. `draft de` writes `build/i18n/draft-de.tsv`: a line per string German
   has no translation for - all of them for a new language, else only
   what's new or changed in the code since (a changed English loses its
   old translation in `update`). Each line: an id, where it's used, how
   many forms a count takes in German (`tools/i18n/keep.py`'s
   `PLURAL_FORMS`, checked against Qt's own rules), the English and the
   note for the translator. A new language's `.ts` is made too.
2. **The drafter** reads it with `GLOSSARY-de.md` (write it first: the
   product's terms - caption, lookup, "Translate into" - said one way
   every time) and writes answers: a line per string, its id, a tab and
   the translation, a count's forms split by " | ". Today the drafter is
   Claude in a Claude Code session; no outside service gets the strings
   without the user's say.
3. `draft de --answers` checks each by machine (`keep.broken`: every
   `{name}` exactly, the count in every form, HTML tags in order, the
   number of forms) and writes the good ones as drafts ("?"). A refused
   one is listed and stays empty, so the next `draft de` hands it out
   again. A glossary term the English uses and the draft doesn't is
   listed as a hint ("glossary?"), not refused: a word's ending changes
   with its place in a sentence.
4. Offer it: the language's code and own name in
   `ui/interface_language.py`'s `OFFERED` (a `.ts` that isn't offered fails
   `check`, and so does an offered language without one).
- Two pull requests changing the same `.ts`: merge `main`, keep both
  sides' translations, and run `update` again (it rewrites the file from
  the code and the translations in it). There's no `.qm` to merge.

## Patterns for numbers, counts and dates

Each language decides word order, plural forms and spacing, so the whole
phrase is one string - never a number glued to a translated word.

| What | Write | English | Chinese |
|---|---|---|---|
| a count | `_trn("%Ln word(s)", n)` | 1 word · 1,243 words | 1 个词 · 1,243 个词 |
| a count, irregular in English | `_trn("heard %Ln time(s)", n)`, then fix `polyglotic_en.ts` | heard once · heard 14 times | 听到 14 次 |
| a count beside another number | `_trn("%Ln day(s) of {total}", days).format(total=QLocale().toString(7))` | 1 day of 7 · 6 days of 7 | 7 天中的 6 天 |
| a ratio as a sentence | `_trn("%Ln word in {total} was new", ...)` - the count decides the verb too | 1 word in 11 was new · 3 words in 11 were new | 每 11 个词中有 1 个是生词 |
| a number on its own | `QLocale().toString(n)` (never `f"{n:,}"`) | 1,243 | 1,243 |
| a percentage | `_tr("{percent}%").format(percent=QLocale().toString(91))` - the language places the sign (French "91 %") | 91% | 91% |
| a duration | `_tr("{hours} h {minutes} min")`, `_tr("{minutes} min")` - abbreviations don't take plurals | 12 h 40 min | 12 小时 40 分 |
| a long duration | `_trn("about %n year(s)", n)` | about 2 years | 大约 2 年 |
| names in a sentence | `QLocale().createSeparatedList(names)` (`ui_next.languages.name_list`) | Mongolian and Kazakh | 蒙古语和哈萨克语 |
| a date, weekdays | `QLocale().toString(date, QLocale.FormatType.LongFormat)`, `QLocale().dayName(n)`, `QLocale().firstDayOfWeek()` | (Windows' regional format) | 2026年11月2日星期一 |

Numbers, dates and the week's first day follow Windows' regional format
when it's in the interface's language (an Australian English Windows keeps
its own), else the interface language's (`ui.interface_language.formats`).
Chinese counts stay exact with digit grouping ("12,430 个词"); 万 ("1.2 万")
only if a screen ever shows large rounded counts - not yet.

## The string freeze

Before a release that goes to testers: no new or changed strings for a
few days, the native reviewers go through the drafts ("?"), and the
release goes out with what's reviewed. Strings still in draft show as
drafted; strings nobody drafted show in English.
