# 0287 Songs mode: a Lyrics switch has a music player on Detect sent while no speech is heard

- **Status:** accepted
- **Date:** 2026-11-21
- **Decided by:** the user, 2026-11-21 ~11:29 ("Yes to all", to Claude's
  recommendations: polyglotic-hq DECISIONS.md #248's option C), from
  polyglotic-hq 558's measurements; built by 595.

## Situation

Silero, the speech detector, scores singing under a band as music, and no
detector setting changes that (558). With the floor filter and the bed
threshold (decision 0267) a rock song's singing was 29 % heard, and a song
went 14-86 s with nothing sent: a learner listening to a song in Spotify
sees almost nothing (the user's report b26df5af: 143 s with no caption).

Sending a music player's sound even where no speech is heard fixes most of
it (558's option B): a rock song 25 % -> 53 % heard, the longest quiet
about 8 s. On Detect, live's speech model wrote nothing for any of 558's
580 instrumental pieces, so music alone gives no invented lyrics; told a
language, it turns music into words like "The." (decision 0275).

The user (2026-11-21 ~10:35): "Music optimisations probably shouldn't
affect non-music apps or have a toggle to translate music as well."

## Decision

- **A "Lyrics" setting** (`AppSettings.lyrics`), off by default. Its
  switch is in two places, both the one setting:
  - a music player's caption window, under They speak, in the settings
    popover and the language chip's - offered only while that window hears
    Detect (`CaptionWindow.offers_lyrics`);
  - Settings > Captions > Speech ("Lyrics in music players").
- **When a source is heard in songs mode** (`core.listening.songs.heard_as_songs`):
  the switch on, the source a known music player's (the known-apps list's
  music category, decision 0275's `music_player`), and its window on
  Detect. `CaptionWindows.songs_sources` names them; `main` hands them to
  the speech pipeline (`SpeechPipeline.set_songs`) whenever the setting or
  a window's languages change.
- **What songs mode does** (`core.listening.songs.SongsMode`, one per
  source, after speech detection): after `SONGS_AFTER_SEC` (4 s) of sound -
  every frame peaking at `SONGS_PEAK` (-45 dBFS) or louder - heard as not
  speech, the next `SONGS_SEND_SEC` (3 s) count as speech, and the caption
  timing sends them as it would speech. Speech heard starts the count
  again; quiet starts it again; digital silence (the player paused) ends a
  piece. 558's option B, with its measured values, named in one place.
- **Nothing else changes:** speech detection itself is untouched (the
  frame's peak is only reported, `FrameResult.peak`), so every other app,
  and a music player with the switch off, is heard exactly as before.
- **Counted, with consent:** a listening session's summary says how long a
  music player was heard in songs mode and how often the switch was turned
  (`lyrics_seconds`, `lyrics_switches`; polyglotic-server #357) - only in
  a session that used it.
- **Enforced by:** `tests/test_songs_mode.py` (the rule, the stage, the
  pipeline, and a recorded CC BY song through the app's own detection) and
  `tests/ui_next/test_lyrics_switch.py`.

## Why

- **Opt-in, as the user asked:** music and singing alone stay uncaptioned
  for everyone who doesn't turn it on.
- **Kept to Detect:** on Detect live's model wrote nothing for 580 of 580
  instrumental pieces; a named language would turn the extra music into
  junk lines (decision 0275).
- **Only known music players:** a game's or a video's music would be sent
  all the time (558's option D, not recommended), and their dialogue is
  already heard over music (decision 0267).
- **After detection, not in it:** the detector's measured behaviour
  (decisions 0254, 0267) stays exactly as it is, and the stage is plain
  Python, tested without the model.

**Not taken:**
- **Songs mode for every music player without a switch (558's B):** the
  user chose it opt-in.
- **A lower threshold or a second detector (YAMNet) for singing:** 558
  measured them; neither hears singing under a band.
- **Starting the count again only on longer runs of speech:** blips the
  caption timing drops (under `MIN_SPEECH_SEC`) still restart it, which is
  why a song can go about 8 s with nothing sent. Measured by 595 on 558's
  bench as a possible change (595's report); not taken without the user
  hearing songs mode first.

## What would make us reverse it

- Learners who turn it on find the extra captions wrong or noisy (a
  usage share of `lyrics_switches` turned straight off, or "Looks wrong?"
  on music players).
- The server's load: about half a speech listener's for every hour of
  music with it on (558).
- A detector that hears singing as speech, making the stage unneeded.

## How we'd reverse it

- Drop `core/listening/songs.py`, `SpeechPipeline.set_songs` and its call
  in `main`, the `lyrics` row of the settings popover and Settings >
  Speech, and the two tests. `FrameResult.peak` can stay.
- `AppSettings.lyrics` left in a settings file is ignored by a version
  without it.
