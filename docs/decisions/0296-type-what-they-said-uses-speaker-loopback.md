# 0296 Type what they said uses speaker loopback

- **Status** Proposed for Preview 5
- **Date** 2026-11-22
- **Source** Polyglotic HQ project 669

The learner holds F8 while someone else speaks through the configured
Speakers output. On release Polyglotic sends one finished-caption request
on the listening session using the system-audio source `type_theirs`.
It detects the spoken language. The source can request the first configured
translation language. Its reply goes to the typing controller and stays
out of the caption feed and transcript.

Reuse the held recorder, bounded by the existing 30-second finished
caption limit, and the dictation controller. The controller tracks the
window at release and checks it again before typing. On Wayland a granted
desktop portal shortcut copies the result to the clipboard. On X11 the
app sets the clipboard and pastes using XTEST.

The prior re-speaking binding and explicit on or off preference migrate
to speaker typing. Its former microphone behaviour is available with the
hidden `legacy_respeaking` setting on Windows and macOS. Decision 0274
continues to describe that opt-in behaviour.

If hold durations above the server limit prove common, revisit the clip
limit against the protocol and measure latency before raising it. A change
to how completed text reaches other apps stays in the input adapters.
