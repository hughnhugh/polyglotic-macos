# 0229 A selection is read aloud a sentence at a time, behind a `Reader` port, in its spoken form

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** polyglotic-hq project 495, from 488's design and
  measurements; DECISIONS #212 (the user, 2026-11-18 ~07:08, "go with
  defaults": Windows' voices first, Kokoro later after a GPL-free study, GPU
  voices only where the PC has none). Claude reviews it with the pull
  request.

## Situation

The learner wants to hear a selection - one to three sentences across
captions, what was said or its translation - read aloud, with the word
being said lit. Decision 0077 gave the lookup card a `Speaker` for one word
at a time over Windows' voices; a reading is longer (a 10 s reading would
hush the captions for 10 s however soon it was stopped), its text is a
caption's as cut (a syllable said on both sides of a cut, a stray full
stop), and a moving highlight needs to know when each word sounds. A better
voice (Kokoro on the PC) streams a chunk at a time and is planned next.

## Decision

- **A `Reader` port** beside `Speaker` (`ports/speaker.py`): the same voices,
  `read(chunks, voice, rate, sounding, ended, spoken)` and `stop`. One
  speaker serves both (`platform.speaking.SpeakerThread`): a reading stops
  a word, a word stops a reading.
- **A chunk at a time:** each chunk (a sentence) made, played and handed to
  the captions' hush on its own (`sounding` per chunk); the next made while
  one plays; a short pause between. Stopped half-way, the captions are
  hushed no longer than the chunk it was in.
- **Word times from the voice:** `Clip.words` (`speaking.WordTime`) - the
  Windows adapter asks WinRT for word boundaries
  (`SpeechSynthesizerOptions.IncludeWordBoundaryMetadata`) and reads the
  stream's "SpeechWord" cues through ctypes; `spoken` is told as each
  sounds. A voice that gives none (the Mac's adapter today) has each chunk
  told whole as it starts: the seam for its words.
- **The spoken form** is plain Python in `core.listening.read_aloud`: mended
  only at caption cuts, fillers out, years read as years (English and
  Chinese), sentences as chunks, and each character's origin kept so the
  word said lights where it is shown.
- **Kept in memory only:** the last readings' sound (about 10 MB,
  `KEPT_BYTES`), so a second Say it plays at once; never on disk, gone
  when the app closes. Words the lookup card says aren't kept (a pack's
  recording may arrive).
- The interface (`ui_next.selection_reading.SelectionReading`) is app-wide:
  the sentence card's Say it row and the transcript's Say it menu. `main`
  hands it the speaker, the hush, dictation's hold and the setting that
  remembers which side was used last.

## Why

- **Per-chunk hush:** the hush can't be cut short once told (0077's
  `SpeechPipeline.hush` keeps spans); telling it per chunk bounds what a
  stopped reading costs the captions to one sentence.
- **Per-chunk making** is what a streaming voice (Kokoro, 488: first sound
  in 0.13-0.84 s chunked against 1.0-2.9 s whole) needs; Windows' voices
  make a sentence in 8-90 ms (measured 2026-11-18 on the user's PC), so
  they lose nothing by it.
- **A second port, not a wider `Speaker`:** the word's callers and fakes
  stay as they are; a reader is what Say it needs.
- **Word boundaries from WinRT** come with the same synthesis call; the
  alternative, estimating by length, lights the wrong word in Chinese.

## What would make us reverse it

- A voice that can't be chunked well (prosody across sentences matters
  more than the hush): read whole, and tell the hush per sentence from the
  word times instead.
- Learners say the pause between sentences is too long or too short:
  `CHUNK_PAUSE_SEC`.
- WinRT's word cues break on a Windows build: the reading still plays,
  each sentence lit whole.

## How we'd reverse it

The chunking is one loop in `SpeakerThread._say`; the port's `read` takes
chunks, so reading whole is passing one chunk. Word times are an optional
field of `Clip`: an adapter that gives none changes nothing else.
