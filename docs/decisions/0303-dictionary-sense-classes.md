# 0303 Dictionary sense classes

- **Status** accepted
- **Date** 2026-11-23
- **Decided by** Polyglotic project 736, implemented in project 739

A sense is one displayed gloss on a dictionary entry. Its word classes
describe the lexical uses supported by that sense. A reviewed sense can
have several classes or fall outside the seven classes the app displays.
A pending sense has no reviewed class evidence.

Dictionary format 1 adds an optional SQLite `sense_classes` extension.
The extension associates classes with each entry's final gloss order, so
each gloss-language variant carries its own evidence. Existing readers
can look up the pack using the same entry IDs, meanings and forms. New
readers leave classes unknown for older or unrecognized extensions.
The accompanying `sense_prefixes` table identifies the exact length of
builder-generated labels in legacy gloss text. New cards can display the
translated class label and preserve parenthetical domains in the gloss.

For complete lexical evidence, the caption's contextual class wins when
it is among the possible classes. A sole class can supply the label when
every eligible sense belongs to it. Pending senses leave the contextual
class in place. The card shows the classes of each sense independently.
Caption evidence is computed while building the displayed lines and reused
by contextual lookup. Painting and pointer motion use the cached result.

The builders report coverage for each written gloss variant. For Mandarin
and Cantonese, `--class-reviews DIR` accepts a reviewed 746 manifest as
`<pack>.json` beside its frozen `<pack>.sqlite`. A reviewer supplies
`reviewer`, `classes`, and `human_reviewed: true`. Import verifies the
variant and frozen pack hash, then matches by stable entry ID, headword,
reading and unique gloss identity before assigning the final ordinal.
The new pack records the review manifest and frozen pack hashes.

If the taxonomy or source data changes substantially, add an extension
version and rebuild the packs from their pinned sources. If using the
pack to resolve caption classes proves inaccurate, remove that step from
caption assembly. Per-sense labels and old pack readers can continue to
use the same SQLite files.
