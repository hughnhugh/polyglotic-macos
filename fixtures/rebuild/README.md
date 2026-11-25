# Rebuild behaviour fixtures

These files freeze the protocol-v1 caption view state produced by the current
Python app. Run `uv run python -m tools.rebuild_fixtures.record` to record them,
or add `--check` to detect drift without changing files. The utterances are
made-up test material derived from the repository's existing recorded captions;
they contain no user content.

Each JSON document has `schema_version`, `name`, the behaviour IDs from project
749 in `covers`, and `view` (caption mode, translation target, and visible-line
limit). `events` is the ordered wire stream: `at_seconds` is simulated elapsed
session time and `message` is the complete protocol-v1 server message.
`checkpoints` contains the view immediately after each event. Its `state.lines`
are oldest to newest and contain the stable view key, caption/source IDs,
language, `final`, and clauses. A clause records both texts, translation
language, settled status, original-side tokens and readings, and word links.
Spans are zero-based, half-open Unicode-code-point offsets. A word class is
`null` when the server did not provide it. All values are JSON primitives.

The twelve fixtures cover Mandarin→English, English→Mandarin, Japanese
readings, present and unavailable word classes, superseding live words,
live-to-finished replacement, late translation, two speakers, a mid-session
language switch, Video Instant's one-line window, and Video Scrolling's
three-line window. Their exact 749 IDs are recorded in each file rather than
duplicated here.

There is no `tools/protocol/v1.schema.json` on base `preview-6`. The recorder
therefore validates every input with the app's vendored Pydantic protocol-v1
model (`connection.protocol.CaptionUpdate`). When the JSON Schema lands, the
drift test is the place to add its second validation.
