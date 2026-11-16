# 0087 The interface in every main language: drafted by machine, checked by machine, and said to be a draft

- **Status:** accepted
- **Date:** 2026-11-13
- **Decided by:** polyglotic-hq project 294 (the user, 2026-11-11: "Let's
  solve the app language part to be universal (at least all the main
  languages)"); Claude reviews it with the pull requests, and the user may
  overrule it.
- **Builds on:** 0034 (Qt `.ts` files, `tools.i18n`), which stays.

## Situation

The interface was in English, Simplified and Traditional Chinese, both
Chinese versions machine drafts (projects 156, 176). The user wants the
app's own text in every main language. There is no native reader for most
of them yet, no translation service, and about 1,100 strings - a number
that grows with every pull request that adds text.

## Decision

1. **Which languages:** every language the app captions that Qt and
   Windows can show (`ui_next.languages`' targets), drafted one by one. A
   right-to-left language (Arabic) waits for its own project: the layout
   has to mirror soundly first. Cantonese reads Traditional Chinese
   (zh_TW). Each language is in `ui.interface_language.OFFERED` only once
   every string is drafted: a test fails on an offered language with an
   empty string, and on a translation file that isn't offered.
2. **Drafted by machine, with a person's glossary:** `python -m tools.i18n
   draft <language>` hands every string with no translation - all of
   them the first time, then only what's new or changed - to a drafter,
   with the language's glossary (`translations/GLOSSARY-<language>.md`:
   caption, lookup, "Translate into"... said one way every time). Today
   the drafter is Claude in a Claude Code session; no outside service gets
   the strings without the user's say. `--answers` takes the drafts back.
3. **Checked by machine before anything goes in** (`tools/i18n/keep.py`):
   every `{name}`, the count in every form, HTML tags in order, and as
   many forms of a count as Qt gives the language (tested against Qt's
   own rules). The UI lab walks every state in every language and fails
   the build on text clipped at the size its widget gives it, a glyph
   drawn as a box, or Chinese in a Japanese face (`python -m tools.ui_lab
   languages`, at the app's Normal text size).
4. **Said honestly:** a language whose file still has an unreviewed draft
   is in `DRAFTS`, and Settings says "Machine draft" beside the language
   picker, with "Tell us what reads wrong" - the feedback form ("Suggest
   something"). A test keeps `DRAFTS` true to the files. "Like this PC"
   picks a drafted language when Windows is in it: a draft in the
   learner's own language reads better than English for most.
5. **The picker** lists each language by its own name (Deutsch, 日本語),
   sorted by that name with accents set aside, so each script's names are
   together and none is pinned first.
6. **Review by people, cheaply:** `python -m tools.i18n sheet <language>
   out.csv --most-seen 60` is a sheet a friend who speaks the language
   reads in ten minutes - the 60 strings the interface shows most, with
   where each is - and `apply` takes their corrections back, reviewed.

## Why

- A draft in the learner's language, said to be one, serves a beginner
  far better than English they may not read - and every main language at
  once costs a session's drafting, not a vendor contract.
- Machine checks catch what breaks the app (a lost `{app}` fails
  `.format()`; a wrong number of forms shows the wrong one; a clipped
  button can't be read). They can't catch a wrong word: only readers can,
  so the drafts are labelled and the way to say so is one click away.
- Building the pipeline around files (`.ts` in, a TSV of work out, a TSV
  of answers in) keeps the drafter replaceable.

## What would make us reverse it, and how

- **A language's drafts read badly to its testers** (feedback through
  "Tell us what reads wrong", or a reviewer's sheet mostly corrected):
  take it out of `OFFERED` (and its file) until a person has reviewed it;
  Windows in that language falls back to English.
- **Drafting by hand in a session doesn't keep up** with new strings:
  an API drafter (the same work and answers files) or a translation
  service such as Weblate or Crowdin (both read `.ts`) replaces step 2,
  with the user's agreement on where the strings go. The checks stay.
- **Strings change too often to keep 20 languages drafted:** the string
  freeze before a release (translations/README.md) is where drafting
  happens; between freezes a language may show English for new text by
  letting `test_every_string_is_drafted` apply only at the freeze.
