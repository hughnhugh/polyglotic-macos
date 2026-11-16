## Intent

<!-- The written intent this change starts from: a brief, an issue, a line
in MVP.md (polyglotic-hq). One concern per pull request. Anything found
along the way that isn't part of the intent is noted here, not fixed. -->

## What changed

## Release notes

<!-- Would people using the app notice this? Then add one plain-language
line to RELEASE-NOTES.md's Unreleased, under New, Better or Fixed, in this
pull request, and copy it here. Otherwise write "none". -->

## What was tested

<!-- What you ran and what it showed, and what wasn't tested. A bug fix
comes with a test that fails without the fix. -->

## Review checklist

From polyglotic-hq ENGINEERING.md. Tick each, or say why it doesn't apply.

**Reversible and substitutable**
- [ ] 1. If today's assumption is wrong and we want to change this decision six months from now, have we built it in a way that makes that easy? What would have to change?
- [ ] 2. Could we substitute the payment system, the speech model, the translator, the database, the transport, or this feature, without touching `core`?

**Domain and boundaries**
- [ ] 3. Is the logic in the right module, and does it use the domain's words (the glossary) for things?
- [ ] 4. Does `core` stay free of infrastructure imports? Does anything reach into another module's internals rather than its interface?

**Simple and readable**
- [ ] 5. Is there speculative generality - abstraction with no second use? Could it be simpler?
- [ ] 6. Could someone new understand it from its names and the module's documentation alone?

**Tested and safe**
- [ ] 7. Is the behaviour tested at the domain level? Does a bug fix come with a test that fails without it?
- [ ] 8. Does it change the protocol between desktop and server? If so, do older app versions still work?
- [ ] 9. Does anything log or send audio, caption text or other personal data? Usage tracking stays content-free.

**Housekeeping**
- [ ] 10. Does `ARCHITECTURE.md` or a decision record need updating?
- [ ] 11. If it's behind a feature flag, is there a plan to remove the flag?
