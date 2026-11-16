"""What a translation must keep from its English, checked by machine
(decision 0034; polyglotic-hq 294, decision 0087).

- **Its `{names}`**, each exactly as written: the app fills them in with
  `.format()`, which fails on one lost or renamed.
- **The count** (`%n`, `%Ln`) in every form of a count's text.
- **Its HTML tags**, in the same order: a tag changed or lost breaks the
  text a label shows as rich text.
- **How many forms a count has** in the language (`PLURAL_FORMS`, Qt's
  rules: Japanese one, German two, Polish three) - any other number and
  Qt shows the wrong form, or none.

Used where a translation comes in - a reviewer's sheet (`review`), a
drafter's answers (`draft`) - and by the tests, over every file.
"""

import re

PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
COUNT = re.compile(r"%L?n")
TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")

PLURAL_FORMS = {
    # one form: no plural in the language (Qt's "Japanese style")
    "ja": 1,
    "ko": 1,
    "zh_CN": 1,
    "zh_TW": 1,
    "vi": 1,
    "id": 1,
    "ms": 1,
    "th": 1,
    "tr": 1,
    # two: one, and the rest (French and Brazil's Portuguese count 0 as one)
    "en": 2,
    "es": 2,
    "fr": 2,
    "de": 2,
    "it": 2,
    "nl": 2,
    "pt_BR": 2,
    "hi": 2,
    "fil": 2,
    # three: one, a few, many (Slavic)
    "pl": 3,
    "ru": 3,
    "uk": 3,
    "cs": 3,
}
"""How many forms a count's text has in each language, as Qt's `lrelease`
and `QTranslator` count them (`tests/tools/test_i18n_draft.py` checks each
against Qt's own)."""


def broken(source: str, forms: tuple[str, ...], language: str | None = None) -> str:
    """What's wrong with `forms` as a translation of `source` - "" if
    nothing. `language` also checks a count's number of forms."""
    if not any(forms):
        return "empty"
    wanted = sorted(PLACEHOLDER.findall(source))
    tags = TAG.findall(source)
    counted = bool(COUNT.search(source))
    if counted and language in PLURAL_FORMS and len(forms) != PLURAL_FORMS[language]:
        return f"a count has {PLURAL_FORMS[language]} form(s) in {language}, not {len(forms)}"
    if not counted and len(forms) != 1:
        return f"one form, not {len(forms)}"
    for form in forms:
        if not form.strip():
            return "a form is empty"
        if sorted(PLACEHOLDER.findall(form)) != wanted:
            return f"keep {', '.join(wanted) or 'no {names}'} exactly: {form!r}"
        if counted and not COUNT.search(form):
            return f"keep the count (%n or %Ln): {form!r}"
        if TAG.findall(form) != tags:
            return f"keep the tags {' '.join(tags) or '(none)'} in order: {form!r}"
        if "\t" in form or "\n" in form:
            return f"no tab or line break: {form!r}"
    return ""
