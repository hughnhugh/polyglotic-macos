# Architecture

How polyglotic-desktop is organised: the module map, what each module
owns, and the rules between them. The standards behind it are in
polyglotic-hq: [ENGINEERING.md](../../polyglotic-hq/ENGINEERING.md) (ports
and adapters, the import rule) and [DOMAIN.md](../../polyglotic-hq/DOMAIN.md)
(bounded contexts, glossary, data and privacy). Structural decisions are in
[docs/decisions/](docs/decisions/). The protocol with the server is
polyglotic-server's [docs/protocol.md](../polyglotic-server/docs/protocol.md).
Last updated 2026-11-04 - the live-update timing rules are in (project 016);
`ports/` and `adapters/` added with the dictionary files (decision 0008);
Learning's rules (project 025); protocol v1's messages and the listening
session in `connection/` (project 022, decisions 0011 and 0012); caption
history and display rules (project 027); the outbox and sync sessions
(project 028, decision 0013).
The interface's rebuild beside today's `ui/` (decision 0031, 2026-11-07).

## Module map

```
src/polyglotic_desktop/
  core/              what the app does - plain Python, no I/O, no Qt
    shared/          where contexts meet: the events they publish, the IDs they share
      papers.py        the website's pages the app opens (privacy notice, tester agreement, Plus) and the agreement's version - one place (polyglotic-hq 185)
    listening/       sources, caption display state, caption history, live-update timing (v1), the playout (words at the pace they were said)
      check.py         the "no captions?" check's rule: five links from connection to captions drawn, the first broken one named (096)
      failing.py       captions failing on the server: two finished captions failed in a row are said until a caption arrives (polyglotic-hq 158)
      unreachable.py   why the server can't be reached or isn't serving (offline, no answer, down, restarting, a failed session, blocked, not secure, the PC's clock, too many sessions on the account or failed sign-ins from this network), whose side each is on, and a restart said as one while the server comes back (polyglotic-hq 251)
      maintenance.py   a planned maintenance window the server told of: when it's said (a day ahead, during it), placed by the server's time; a failed try in it said as the maintenance; the wait, at most 2 minutes, then spread over a minute at its end; kept between starts (polyglotic-hq 319, decision 0110)
      unstable.py      a connection that keeps dropping (two drops within 5 minutes, said until it has held 2 minutes) or has stalled (finished speech unanswered, or the server silent, 8 s too long) (polyglotic-hq 165)
      sources.py       a source: its id and category (never an app's name); its label on this PC - name and colour; the capture mode and what is captured (project 134)
      timing.py        the live-update timing rules, a pure state machine, and the caption modes (Steady, Quick preview, Live updates); live updates wait their turn under the server's speech ceiling (decision 0097)
      held_back.py     live updates held back (waited their turn here, or refused by the server): the learner told once in a while, the log's one line a minute (decision 0097)
      pending.py       speech waiting to be sent, latest wins
      songs.py         songs mode (decision 0287, polyglotic-hq 595): when a source is heard in it (the Lyrics switch on, a known music player, on Detect), and its frame stage - sound unheard as speech for 4 s, then 3 s sent as speech - with its values named in one place
      hidden.py        a caption window the learner hid: its own timer, paused past the learner's limit (5, 15 or 60 minutes, or never), captioning while hidden, speech starting in it (polyglotic-hq 335, decision 0128)
      captions.py      caption updates from the server: live, finished, withdrawn; clauses, translations, word links; the language each translation is written in, the server's word for it first (decision 0231)
      continuations.py display a server-marked pair in the first caption’s place and restore separate answers when the association ends
      history.py       caption history: updates applied in place, joins, withdrawals, stable keys, never blank
      established.py   established text: the start of a live caption the server says two live updates agreed on, drawn as final; a quiet correction when an update changes it (decision 0228; server decision 0095)
      settling.py      settled text: what a caption has shown for 3 s (or the shorter time the learner chose: decision 0099), or above its last two clauses, never changes; only what follows is taken from an update (decisions 0088, 0091); a row of settled words keeps the update's word links for the words both have (polyglotic-hq 340)
      display.py       caption display rules: clause rows, second language, word links drawn, one-way layout, a word's counterpart for the card (decision 0125)
      caption_model.py one model of a caption (polyglotic-hq 340, decision 0132; docs/caption-model.md): places, the units a line never breaks inside, links numbered across the caption, where both sides can be cut - built once per caption version, an unchanged clause kept; the pour's word cutter and matching cuts are its (the layouts move onto it step by step)
      selection.py     a selection in a caption window (polyglotic-hq 358, decision 0150): two places, the words they hold now across clauses, sides and captions, and their text to copy
      read_aloud.py    a selection's side in its spoken form, to read aloud (polyglotic-hq 495, decision 0229): mended only at caption cuts, fillers out, years read as years, a sentence at a time, each character knowing where it was shown
      transcript.py    the transcript written out as text, SRT or CSV
      settings.py      the user's listening settings: spoken language (each source's own, or Detect), targets (each source's own, or none),
                       spelling hints
      delays.py        each caption's delay (speech start and end to shown, the server's share) and the caption log's lines: one per caption event - sent, answered, shown, dropped and why - content-free, in logs/captions.log (polyglotic-hq 271)
      summary.py       a listening session's content-free summary: caption delay as seen, rewrite rate, dropped captions, minutes, lookups and saves counted;
                       per app vs whole system - time in each capture mode and at 0-3 apps, switches - and what the learner did (polyglotic-hq project 134)
      recheck.py       "Looks wrong?": a recheck's request and outcomes, what differs between two versions of a line, the content-free count (0030; nothing in the interface asks since 0131)
      problem_report.py "Report a problem" (alpha): the captions as shown in the last few minutes, each source's held speech, whose voices (275, 0067)
      warm_up.py       the server's warm-up notices, and when captions show one is over (Home's banner, polyglotic-hq 158)
      dictation.py     dictation - hold a key, speak, let go: each hold's pieces in order, the text typed (clauses joined, English fillers out, a space after), and what the sign says; uses own-speech captions when available, or the private `sources.DICTATION` clip
      caption_hold.py  a typing hold's caption results: finished requests settle the hold, and the display's joined and continued lines supply its text (polyglotic-hq 703)
      dictation_keys.py dictation's key as the learner chooses it - a key with modifiers, Right Ctrl alone, or modifiers alone, kept as text ("ctrl+alt+d"); Right Ctrl by default; why a key can't be one (types, Windows', every program's, Alt without Ctrl, the app's own) (polyglotic-hq 289, decision 0081)
      hotkeys.py         the app's hotkeys by name (lock, pause, hide, back to live, copy the newest caption, next preset, caption text bigger and smaller), each one's key the learner's own or its default (Ctrl+Alt+L, P, H, J; the rest none), why a key can't be one, and two sharing one (polyglotic-hq 567, decision 0273)
      respeaking.py      opt-in microphone re-speaking for the watched caption source, and the shared dictation gesture (decisions 0274 and 0292)
      type_theirs.py     F8 speaker holds use the configured output and the typed system-audio source. Original text or the chosen translation is delivered after release (decision 0296)
      offers.py        which caption timings each use offers on the bar's timing chip - Video's Instant and Delayed translation, Conversation's Steady and Instant, Learning's Steady and Calm and its translation after or with, Everyday's four: one table, `OFFERED` (polyglotic-hq 593, 585's rule 11)
      spoken.py        the spoken languages: every one the speech model can be told (its 30), for caption windows and dictation alike, and the ones named last (polyglotic-hq 317, decision 0108); when Detect has heard one steadily enough to suggest naming it (decision 0109)
      australian.py    English in Australian spelling, for dictation: colour, centre, organise, travelled; words whose spelling depends on their meaning left alone
    learning/        lookups, saved words and sentences, deck words (the line a word was learned from; decision 0026), the Anki file, word statuses, highlights, exposures
      vocabulary.py    Vocabulary: the learner's level, statuses, saved words, exposures; learning events; applying the server's
      first_known.py   "mark the first N words known" as a move of the known line, with Undo and Reset back to the line before (polyglotic-hq 342, decision 0134)
      levels.py        the level as a known line in words and the learning window past it, any size or unlimited (decisions 0114, 0144); statuses.py: statuses estimated or set, with a source
      knowledge.py     what the learner knows: one answer per word (status, confidence, reason) from the evidence, strongest first, with the line read as a frequency rank; word links ask it (decision 0163)
      known_chance.py  how well each word is known (polyglotic-hq 489, decision 0226): a chance 0-1 from what knowledge.py says - the line as a smooth curve - moved by days heard, saves and lookups; red under 0.15, green from 0.85; Learning load's colours read it
      known_map.py     the whole language at a glance (489, 0226): the tally of red, between and green words and the share heard green (by 1 / place); the same a week ago, rebuilt from the histories
      load.py          the learning load (a Lab mode, polyglotic-hq 324, decision 0117): a fixed number of the next words by frequency, each moving red, orange, yellow, green by its meetings, checked with one click, graduated and replaced; fed by hand, its size changed at any time; kept word by word, on this PC
      curriculum.py    our curriculum, 0.1.8's (polyglotic-hq 477, decision 0219): an active set of 50 words past the line, heard-first (2+ captions, in the learning window, never everyday talk) then by the load's order, filled between sittings, retired after 3 separate days met; the conversation's words entering mid-sitting at its updates, resting when no longer said (polyglotic-hq 491, decision 0227) and retiring once known (489's chance green; 496, decision 0230); and the quiet view's chosen words (curriculum, load, saved, words at your edge - 496) kept as a named word set, words at your edge aside (a rule, not a list)
      theme.py         the conversation's words (polyglotic-hq 491, decision 0227): each source's last 10 minutes of finished captions, in memory only; an update every 2 minutes of its talk; stretch words past the learning window, then theme words by keyness; never everyday talk; look-alikes; the theme's name
      saved_words.py   saved words, categories, finding them in a line
      sentences.py     saved sentences (polyglotic-hq 459, decision 0216): what the learner selected across clauses, captions and speakers, kept with its translation and word links in a category shared with saved words, on this PC only; found again by most of a query's words (each Chinese character a word) over both sides
      highlights.py    unfamiliar words, as the learner's word introductions say (Off, a few per caption under the cap, every new word)
      languages.py     the languages being learned: each caption language's tier (full, basic, none yet), the one in use and the others, "Not now" (polyglotic-hq 262); which open with learning data of their own: every full one learned, and every pack language learned whose pack is here (decision 0175)
      exposures.py     exposures, once per finished caption, and the day each word was first heard; lookups.py: lookup context, and lookups kept with their counts and last time, a word said known and looked up again offered in a check (polyglotic-hq 373)
      coverage.py      coverage: the tokens of each day's finished captions, known / in the deck / new as heard (on this PC, never sent)
      listening_time.py listening time per day and source category, from the gaps between finished captions (on this PC, never sent)
      bands.py         the words met by frequency band (top 1,000 ... 10,000, rarer) or level: known / in the deck / new / not heard yet
      anki.py          saved words as a CSV Anki imports
    lexicon/         dictionary entries, word split, readings, reverse lookup, meanings; names a dictionary lacks (a foreign name's pieces, a word its translation writes by its sound: polyglotic-hq 496, decision 0230)
      packs.py         the dictionary packs' list: which pack this app reads for a language (format, word split, oldest app), and whether the one on this PC is older (decision 0122); its riders (0133), a built-in dictionary's (0197) and the caption faces' entries (`fonts`, polyglotic-hq 482)
      pack_download.py a pack's download as the learner sees it: its steps, each way it stands still, when it's tried again, an honest time left (decision 0122)
      compounds.py     a word a basic pack hasn't got, cut into words it has: at hyphens, German's closed compounds (decision 0174), and Korean's, a noun's words of two syllables or more (decision 0240)
      vietnamese.py    Vietnamese's word split: a caption's syllables joined into a pack's words, fewest then commonest (decision 0121)
      thai.py          Thai's word split: a line written without spaces cut into a pack's words at the least cost, never inside a letter's cluster (decision 0173)
      korean_forms.py  Korean's guesses: a noun without its particles (one after another), a particle alone as the dictionary lists it, a verb or adjective's dictionary form (stem + 다) from its endings, past and merged vowels (polyglotic-hq 510, decision 0240)
      han.py           the word split `han` (Cantonese): a run of Chinese characters cut into a pack's words, fewest, most even, then commonest (decision 0160)
      jyutping.py      Jyutping over Cantonese for the reading line: each word of the han split as its pack entry reads it (decision 0160)
      korean.py        Korean in Revised Romanization for the reading line: each run of Hangul as it's said, by 370's join rules, no dictionary (polyglotic-hq 511)
      hindi.py         Hindi in Latin letters for the reading line: Wiktionary's letters, the unsaid a's left out by rule, no dictionary (polyglotic-hq 511)
      stress.py        stress marks over Russian for the reading line: an acute over each word's stressed vowel, from the pack's stressed forms and headwords, none where it's stressed two ways (polyglotic-hq 511)
      furigana.py      furigana over Japanese for the reading line: the Japanese split's kana over each word's kanji runs, the okurigana matched out, a counter read by its number (polyglotic-hq 511)
      spoken.py        everyday talk (polyglotic-hq 491, decision 0227): Mandarin's and English's words ranked by speech where the packs rank them rarer in writing (spoken_ranks.py, written by tools/spoken_ranks.py from OpenSubtitles 2018's counts), and their fillers; carried in EntryFacts
      scripts.py       a word's language by its script where its row's says otherwise: Chinese characters in an English row, Latin letters in a Chinese one, Cyrillic in either (decision 0129)
      traditional.py   Simplified Chinese to Traditional, one character for one, the longest phrase first (OpenCC's table in Taiwan's forms): "Show Mandarin in: Traditional" (polyglotic-hq 375, decision 0164)
    releases/        app version, update channel, feature flags from `welcome`
      updates.py       when to look for, download and apply an update; which channel to follow; the offer to restart into one (decisions 0017, 0090)
      milestones.py    the install's milestones as usage statistics: installed, updated, first caption shown (project 134)
      notes.py         the release notes the app carries, by version, and which show after an update: once per version, never on a fresh install (decision 0137)
      flags.py         the app's feature flags, each with an owner and an expiry: the one way code reads one, at the edges (`ui`, `ui_next`, `main`), never from another context (decision 0263)
  platform/          audio capture and speech detection, per OS
    speech_detection.py  Silero VAD on ONNX Runtime (model in data/, decision 0003); hears quiet audio raised (decision 0039), the mic's +6 dB at most (decision 0145); its state forgotten after 5 s heard as not speech, so a song's singing is heard past its intro (decision 0254); speech over music heard through a floor filter, and at a lower threshold under a steady bed of sound, the mic excepted (decision 0267)
    audio_buffer.py      each source's last 30s of audio, for cutting speech
    mic_bleed.py         the mic's audio vs what the PC played (decision 0004), cancelled out of it to judge what's left (decision 0154)
    opus.py              speech as Ogg Opus, 16kHz mono, 24 kbit/s (decision 0005)
    speech_pipeline.py   captured audio -> detection -> timing -> Opus -> waiting to send; silent in the sources that hear the PC's mix (and the mic) while the app says a word aloud (`hush`, decision 0077); the sources `main` names run through songs mode after detection (`set_songs`, decision 0287)
    sound_unheard.py     each source's stretches over 3 s of sound (-45 dBFS or more) that speech detection never heard as speech - levels, resets and times only - for the caption timelines, so a gap with nothing sent can be told from silence (decision 0256; polyglotic-hq 549)
    replay.py            audio files played into the app through the capture port: headless runs, CI, the benchmark's load
    dictation_mic.py     the mic while the dictation key is held (`ports.capture.HeldMic`): opened at the press, closed 0.2 s after the release, a long hold cut at its quiet moment, each piece handed on as Ogg Opus in order; in memory only (polyglotic-hq 283, decision 0073)
    sample.py            Home's sample when nothing is playing: a FLEURS recording in the language learned (data/samples/, CC BY 4.0), played aloud (`SoundOut`, the OS's) and captioned as a source of its own (176)
    speaking.py          the `Speaker` and `Reader` ports on a thread of its own over an OS's voices and output: voices listed in the background, a word made, its silence trimmed and played, the last click winning (polyglotic-hq 286, decision 0077); a reading a sentence at a time, each hushed on its own, each word told as it sounds, the last readings' sound kept in memory (495, decision 0229); or a chunk a voice says itself (`SaysItself`: Linux's speech-dispatcher), hushed from the ask, a little ahead at a time while it plays (591, decision 0294)
    recorded_voices.py   recorded words beside the OS's voices: a language's recordings as a voice of its own, the OS's voice for a word not recorded (decision 0133; one pace, decision 0241)
    timeline.py          keeping a capture's audio continuous on the app's clock (gaps become silence, overlaps dropped) and which device it follows: shared by every OS's capture (411)
    windows/         per-app capture, system audio, the mic (decision 0006); only main's os_adapters imports it (decision 0038)
      capture.py       WASAPI capture: one app, everything else (all but one app), the whole system, the mic; one app tried on Windows 10 2004+, with a trial that gives up on a PC where it fails (0076)
      apps.py          the apps with sound, for the app picker
      categories.py    app -> category (browser, video, call, game, other); the known-apps list's public names
      devices.py       outputs and mics, and Windows' defaults
      com.py           calling COM through ctypes
      network_cost.py  whether Windows calls the connection metered (the Network List Manager's cost): a pack's download asks first on one (decision 0122)
      keys.py          whether Esc, Backspace or a mouse button is held now, anywhere - read, not taken (a settings popover and the lookup card, without the focus)
      hotkeys.py       system-wide hotkeys (Ctrl+Alt+L/P/H/J, or the learner's own combinations: 567) on a thread of their own, working over games; `HoldKey`, dictation's key or combination held - when it's all down and when any of it comes up: registered with Windows, or for Right Ctrl alone and modifiers alone their state read every 15 ms, another key with them a shortcut - no hook (283, 289, decision 0081)
      qt_calls.py      calls into Qt's own library that don't hold Python's interpreter, by the name MSVC gives the function: Windows' fonts read (`read_fonts`), for a thread of its own (322, decision 0112) A widget given its window of Windows' the same way (`make_native_window`), on the interface thread (decision 0113).
      text_input.py    dictation's text typed into the program with the keyboard as Unicode key events, the clipboard untouched; the window that has the keyboard (283; the call that types waits for the guard - decision 0073)
      on_top.py        the caption windows back above a game that is itself always on top: whether one is in front, putting windows on top without activating them, and a watch on the foreground window (146)
      error_box.py     a plain Windows error box: the app couldn't start
      taskbar.py       whether Windows' taskbar is light or dark, for the tray icon's version (098); the ID the taskbar knows the app by - the installer's, the package's for the Microsoft Store's copy, else `Polyglotic.Desktop` from source (decisions 0051, 0056)
      package.py       whether this copy is an MSIX package - the Microsoft Store's - and the app ID Windows gave it (decision 0056)
      sound.py         a sound played aloud through Windows' PlaySound, from memory: the sample (176)
      voices.py        Windows' own voices: the OneCore voices listed and a word made into sound by WinRT's SpeechSynthesizer, played by winmm's waveOut (decision 0077)
      startup.py       starting with Windows: the user's Run key, the installed app in the tray (`--in-tray`; 176)
      one_copy.py      one copy per user and data folder: the named mutex the copy that runs holds (`Local\Polyglotic-<hash>`), and letting it to the front (decision 0101)
      process.py       when Windows started this process: the start from launch to the window, as `--check-install` reports it (136)
      system.py        which Windows this is (protocol.md's `os`, the version number feedback carries) and the data folder, `%APPDATA%\Polyglotic` (decision 0014)
    macos/           the Mac's adapters (polyglotic-hq 409, 411); only main's os_adapters imports it (decision 0038); every module imports on any OS, the frameworks loaded on first use
      system.py        which macOS this is (`macos-26`), the data folder (`~/Library/Application Support/Polyglotic`, decision 0185), the launch clock (libproc), the menu bar's light or dark, Core Foundation's error box
      keychain.py      the device token in the Keychain through Security.framework's SecItem calls (never the `security` command); the install id outlives signing out (0080)
      one_copy.py      one copy per user and data folder: an exclusive flock in the data folder's `locks/`, let go when the process ends
      translocation.py the app run from macOS's temporary copy (App Translocation: its path, or Security's `SecTranslocateIsTranslocatedURL`), where Velopack can't update it; the real app moved to `/Applications` (or `~/Applications`), one there before to the Bin, the quarantine attribute off; opened again once this process ends (polyglotic-hq 433, decision 0205)
      not_yet.py       what the Mac build hasn't got, each saying so through its port: the sample aloud
      hotkeys.py       ⌃⌘L, P, H and J, or the learner's own combinations (567), wherever the learner is: Carbon's `RegisterEventHotKey` (exclusive; no Accessibility permission), a combination another app holds reported taken (polyglotic-hq 428)
      voices.py        the card's voice: AVFoundation's voices, a word made by `AVSpeechSynthesizer` into samples and played by `AVAudioPlayer` on the default output (428); recorded words before them, as on Windows (`recorded_voices`)
      startup.py       opening at log-in: the app as a login item through `SMAppService.mainAppService` (428)
      keys.py          Esc, Backspace and clicks elsewhere, read for dictation, the settings popovers and the pinned card: AppKit's global monitor, only while asked about (polyglotic-hq 438)
      on_top.py        the caption windows over full-screen apps and on every Space: panels at the screen saver's level, joining every Space, non-activating; the front watch (macOS's notifications); the app an accessory (no Dock icon) for its whole run (polyglotic-hq 429, decision 0201)
      window_list.py   the windows on screen, front to back: numbers, levels, owners and places only (never titles or pictures)
      hold_key.py      dictation's key: Carbon's hotkey for a key with modifiers, the modifiers' state for one held alone (Right Command); no event tap (429)
      text_input.py    dictation's words typed into the front app as Unicode key events, with the Accessibility permission asked once a run; the one Mac file that sends input (429)
      mic_permission.py the microphone's permission: AVFoundation's `AVCaptureDevice` status, read, and its question asked when a caption window first shows the learner's speech (478)
      objc.py          Objective-C's runtime through ctypes: messages typed as stated, blocks, autorelease pools
      capture.py       Core Audio process taps through catap (macOS 14.2+): one app with its helper processes, everything else (all but the app and Polyglotic), the whole system; the mic through PortAudio (sounddevice); each mixed to mono, resampled to 16kHz and stamped; a permission not given (silence while something plays) said as `NOT_ALLOWED` (411)
      apps.py          the apps with sound, for the app picker: Core Audio's processes grouped by the app bundle they live in, named by bundle ID
      categories.py    bundle ID -> category; the known-apps list's public names (those Windows' list has) and Mac-only apps' names
      devices.py       outputs and mics by Core Audio UID, and macOS' defaults; a mic's PortAudio index
      cf.py            Core Foundation and Security through ctypes: strings, data, dictionaries, constants
    linux/           Linux's adapters (polyglotic-hq 546, 547, 550; decision 0258); the keyring read once a run (decision 0269); only main's os_adapters imports it (decision 0038); the app an X11 program everywhere (XWayland on Wayland desktops); every module imports on any OS, libpulse and D-Bus loaded on first use
      system.py        `linux-<kernel major>` (protocol.md's `os`), the distribution, desktop and session for feedback, the XDG folders (data in `~/.local/share/Polyglotic`), the launch clock (`/proc`), the desktop's own error box (zenity, kdialog, xmessage)
      secret_service.py the device token in the desktop's keyring: the Secret Service through jeepney, plain session; a 0600 file in `$XDG_STATE_HOME` where there's no keyring; a keyring that won't open is not signed in (0080's install id kept)
      one_copy.py      one copy per user and data folder: an exclusive flock in `$XDG_RUNTIME_DIR/Polyglotic`
      pulse.py         the sound server through libpulse by ctypes: one connection per thread on a hand-driven main loop; defaults, outputs and inputs; record streams at 16kHz mono float32, never moved by the server; its changes counted; playback streams on the default output, written as the server asks and drained (591)
      capture.py       everything the PC plays (the default or chosen output's monitor, by name) and the mic (never an output's monitor: no microphone then), following the server's changes and reconnecting; one app at a time not yet (`app_capture_support` no)
      devices.py       outputs and mics by the server's names, and its defaults; how many outputs play
      hints.py         light or dark (the settings portal's `color-scheme`; the tray's icon for a light panel only where the panel follows it: KDE, Xfce, LXQt) and a metered connection (NetworkManager's `Metered`), over D-Bus with a short timeout (571)
      on_top.py        the caption windows, popovers and cards above everything as override-redirect windows (`ui_next.above_all`), their order kept by hand: the windows given, then the app's other override-redirect windows above them
      input_method.py  which of Qt's input method plugins to ask for, before Qt starts (`main.use_input_methods`): IBus's after Fcitx's - the app carries no Fcitx plugin, and Fcitx5 answers IBus's clients, as the portal's IBus where IBus isn't installed - and IBus's where the session names none (decision 0279)
      file_dialogs.py  the desktop's own file dialogs (Save transcript, the exports for Anki), asked for before Qt starts (`main.use_file_dialogs`): Qt's portal theme, which the package carries - the portal's file chooser draws GNOME's on GNOME, KDE's on KDE - unless the session names a theme (decision 0280)
      startup.py       starting at sign-in: an XDG autostart entry for the AppImage (`--in-tray`), off until the learner turns it on, rewritten at each start while on so a moved file still starts; a desktop's own off (`Hidden`, `X-GNOME-Autostart-enabled`) read as off (571)
      voices.py        the system's voice: speech-dispatcher over its own socket (SSIP, nothing of its loaded), started as its library does where nothing listens; each module's plain voices, the default module's first, all basic; a word said and watched to its END or CANCELed (`SaysItself`; 591, decision 0294)
      sound.py         the app's own sound through the sound server: a recorded word's clip for the speaker (`PulseOutput`), Home's sample on a thread of its own (`PlayAloud`; 591)
      hotkeys.py       the hotkeys: X11's key grab (libxcb by ctypes, a connection of its own) of the kept combinations, where the session hands an X11 app every key (an Xorg session, Plasma 6); none on GNOME's Wayland session (decision 0293)
      not_yet.py       what the first Linux build hasn't got, each saying so through its port: dictation, Esc and clicks read
  connection/        talks to the server: WebSocket, handshake, speech out, captions in
    protocol.py        protocol v1's messages as pydantic models; the speech frame (decision 0011)
    listening.py       timing decisions -> speech frames and `withdraw`; `caption_update` -> core's CaptionUpdate
    learning.py        Learning's events -> `learning` events; `learning_state` -> Learning's events (the open language's dictionary's only); daily exposures -> `exposures`
    app.py             what the app tells the server about itself: version and channel (the release's stamp, which also says when it was built), Windows
    sign_in.py         an invite code read as protocol.md says and redeemed for a device token (`POST /v1/redeem`)
    open_beta.py       email verification, account status, current local prices, a typed code's offer, a plan change's preview and confirmation, and hosted checkout, as the server's open-beta contract states them (amounts as decimal strings with a currency; `percent_left`, or the older `allowance_percent`); keeps device tokens in the credential store; a code is sent, never kept (polyglotic-hq 684)
    feedback.py        reports sent to `POST /v1/feedback` on a thread of their own; what waits sent again later (project 053)
    problem_reports.py alpha testers' problem reports: built, kept and sent to `POST /v1/problem-reports` on a thread of their own (275, 0067)
    session.py         a session: hello, settings, speech out, captions in, keepalive (decision 0012); or a sync session
    reconnect.py       after a session ends: back off and retry, or stop - by close code
    tls.py             every secure connection the app makes: a failure on a certificate's dates tried once more with everything else checked, the leaf's end held against when the app was built; each failure logged once (polyglotic-hq 313, decision 0104); on a Mac, macOS's own roots trusted (polyglotic-hq 512, decision 0236); on Linux, the distribution's own bundle (polyglotic-hq 550)
    failures.py        why a try to open a session failed, from what the network said (a name not found, refused, a tunnel's 502/530, a proxy's page, TLS), and why the server closed one (1001, 1011) (polyglotic-hq 251)
    unanswered.py      finished speech not yet answered: kept in memory, sent again after a reconnect
    exchange.py        learning data, consent, usage, exposures: kept until `received`, sent on any session; consent rules (decision 0013); a sync cursor per language; a deletion made on any device applied, and what's done after it kept whatever the clock (decision 0023); a consent choice dated after the one it replaces, sent again at most once a day (decision 0102)
    milestones.py      the install's milestones kept between runs (an outbox note) and sent through the exchange, with consent (project 134)
    client.py          Connection: the listening session while listening, sync sessions otherwise (decision 0013)
  ui/                what the new interface stands on that isn't one window's - moves into ui_next at the rename (decision 0032)
    app.py             DesktopApp: the settings, the caption feed, the session's state, the commands (pause, lock and hide every caption window, my speech, feedback, quit), the hotkeys and the tray - what main builds and the windows follow
    settings.py        AppSettings: every setting with its default, read leniently, saved through the port (keys today's overlays used kept, for the migration and an older app)
    use_presets.py     presets for use cases (556, decision 0264): Everyday, Conversation, Video, Learning, Custom and the learner's own - the caption settings each names over Everyday's, bar changes saved immediately and Settings changes kept as a draft (decisions 0283 and 0290), Undo's before and after, the move from today's settings, and the preset as the session summary's usage properties
    theme.py           the window theme's colours and heading face: Margin (default), Glaze or Signal - light, dark or like Windows (decision 0029); no app-wide stylesheet
    icons.py           the app icon and the tray's listening / idle / paused icons, drawn from the SVG masters in assets/icons (098)
    assets/            icons/: symbol A's SVG masters; fonts/: the themes' heading faces, each with its OFL text; translations/: the interface's compiled translations (.qm, built from translations/*.ts, not committed - decision 0034)
    interface_language.py the interface's language - the setting, else Windows', else English - and its translations installed at start (0034); the languages offered, the picker's order by own name, which are machine drafts (0087)
    learning.py        LearningTools: the vocabulary and dictionary the learning views share - one per language learned with a dictionary here (a full one, or a pack's: decision 0175), the others beside the main one's, a line sent to its own language's (`of`; decision 0095); once the window has shown and the connection's libraries are in (314), on a thread of its own, reads the word split's data and what Words reads for every word met: facts, the bands' sizes, then each one's text for the search (136, polyglotic-hq 212, 220)
    captions.py        CaptionFeed: caption updates onto the Qt thread, into the history; exposures
    apps_with_sound.py the apps with sound, listed off the interface thread; Home's picker and main's sources share it (110)
    languages.py       the languages not offered as targets
    recorded_captions.py a developer's stand-in for the connection: a made-up conversation (the UI lab, tests)
    widgets.py         small controls today's dialogs use: labels, segmented choices
    first_run.py       the first run's screens one after another, each after the first with Back (`run`; `main.first_run` gives the steps; decision 0054; `start_at` resumes after step 1's language relaunch, 658)
    language_picker.py step 1 of first run: Your language - all offered interface languages named in themselves, preselected from the OS language, noting the default translate-into language (658)
    level_picker.py    about how many words do you know? (a language added,
                       and Words' Change; choices: ui_next/views/known_words)
    consent.py         the consent screen: what the service needs, and three choices off until yes (first run, and Account)
    delete_learning.py deleting the learning data: from the server, and from this PC only if ticked
    sign_in.py         signing in with an invite code (redeemed off the UI thread), and asking before signing out
    open_beta.py       email sign-in and purchase restore; mainland China cross-border consent; account requests off the interface thread
    one_copy.py        one copy per user and data folder: a second start asks the copy that runs, on Qt's local socket, to bring its main window forward, and ends; waits for a copy still starting or ending; says so when one doesn't answer (polyglotic-hq 310, decision 0101)
    move_to_applications.py  on a Mac run from macOS's temporary copy: "Move Polyglotic to Applications?" once, with how to do it by hand; said again plainly if the move fails (433, decision 0205)
    feedback.py        the feedback form: report a problem, suggest something - the log shown before it's sent (project 053)
    problem_report.py  "Report a problem" for alpha testers: every part ticked, with its size and Look; other people's voices said (275, 0067)
    dictation.py       `Dictating`: mic and speaker typing holds, focus checks, Esc, and the sign. A hold follows the active caption source's finished lines or records a clip when it needs its own audio (polyglotic-hq 703)
    respeaking.py      re-speaking in the running app: the key's holds, its own mic, pieces to the session as the other source's, the sign; `SharedKey`, dictation's key for both (polyglotic-hq 567); the caption bar’s passive microphone light and the sign beside the target window show the hold (636)
  ui_next/           the interface (decisions 0031 and 0032): every window and page; renamed ui once ui/'s pieces move in
    upgrade.py         the current plan, priced purchase options (Lite's card only when the server prices it), renewal terms and the same checkout link in the browser or a locally rendered QR code; "Have a code?" (the server's offer and the prices under it; checkout carries the code); a plan change reviewed before it's confirmed - today's charge, the next charge and its date, "from {date}" for one that waits, a further pass's end date - all the server's figures (polyglotic-hq 684)
    usage.py           a capped plan's usage meter (polyglotic-hq 684): its words ("Free today: 62% left - resets at midnight", the tray's line, the 20 % and 5 % warnings) and `UsageRing`, the ring a caption window's bar draws beside the mic - a percentage and a reset time from the server, never a count; nothing on an unlimited plan
    views/             what each surface shows, plain Python - no Qt
      captions.py      one app's captions (and "You", if shown) as lines: the original and one translation or none, kept in a caption history of their own (a transcript lists 1,000 - or the last 3 hours or the whole session, up to 10,000, as Settings > App chooses (334, decision 0127); Copy all and Save have the whole session, 137)
      scroll.py        following the newest line or held where scrolled back, measuring only the lines that show
      placement.py     where a caption window goes: presets, resizing anchored to the opposite edge, moving, snapping, kept on the screen (109's 10.1, 10.3); a joined window's place and equal columns (10.6)
      arrivals.py      how a new caption arrives: step and slide (D, the default: the text rises into place, the new caption in from below, at the speech's pace) or the step (B: the newest at full ink, the ones before a step back), B being D with Windows' animations off (F21; polyglotic-hq DECISIONS.md #104, 253, 267)
      cards.py         Steady's card stack: captions dealt onto one-line cards that never change shape (`Deck`: caption updates in, card caption updates out), the stack's one glide (`Glide`), where a receding card is drawn (`drum`), and Video's cards in depth (`Depth`, `DEPTH_SCALES`) - polyglotic-hq 552 and 583, decisions 0260 and 0282
      dwell.py         how long a card must stay readable: its need from its text, both sides read (`Reading`) - polyglotic-hq 585's provisional reading rules, every value named, decision 0282
      app_choices.py   the apps a caption window can caption instead: found ones, then browsers and the main apps before they play (F12, polyglotic-hq 249)
      caption_window.py a caption window's own choices, kept by source; joined or separate, and the joined window's place; the session's look; the notice line
      migration.py     today's caption settings moved to each window's own, once: the first target language, my speech, the text size, the place (by source, not language); today's keys left as they are
      transcript.py    a transcript's own state: its app's finished captions (and "You"'s while its window shows them), how far back its list goes (334), search, following or scrolled back; its text size and rail kept per app; where it opens (109's section 3)
      sentences.py     a selection in a caption window or a transcript as a sentence to save: the side dragged across as selected, the other whole, links inside both, each line's speaker; whether it's more than a word (polyglotic-hq 459); each side to read aloud, with where its text is shown (495)
      links.py         which of a caption's word links show, by what the learner chose for each row's language: every word, words past what they know, key links only where no dictionary ranks them, or none (decision 0115)
      lookup.py        W3, the lookup: what its card shows (hover, pinned, parts and Back, not in the dictionary, Chinese for it), its Learning commands, where it goes (109's section 6)
      speech.py        hearing a looked-up word: the language it's said in (the word's, never the interface's), the voice that says it, at its own pace every time; when a better voice is worth adding (`BetterVoice`, decision 0241) (polyglotic-hq 286, 518)
      home.py          Home's views: the state line's rules, and the app picker - the captioned apps' rows (at most 3), everything else beside one app (DECISIONS.md #59), the apps that could be added, everything the PC plays (109's sections 5 and 7)
      panels.py        the three shared panels' views - Languages (the session's; one window's in a transcript's rail), Timing, Look: one value each, every panel bound to it told of a change (109's section 4)
      lab.py           Settings > Captions > Lab's experimental values, one `CaptionLab` in the shared look, saved as one setting, each slider's measured range (polyglotic-hq 284)
      flow.py          the one caption layout (polyglotic-hq 340, decision 0132; the Lab's New layout): caption models composed into lines as wide as the window - a clause a row, translation below, line by line, lined up and captions that run on are options of one composer; a caption is composed from the line pair the one before left open; plain Python, the layout engine measures and places
      pour.py          poured captions (the Lab's Captions fill the width): a caption's rows as lines as wide as the window - where each row's characters go and where an ellipsis joins them; plain Python, the layout engine measures and places; stacked, or line by line cut where the word links match (decision 0100)
      load.py          the learning load as Learning's card shows it: its numbers and its words in four lists - ready to check, in the load, next to enter, graduated (polyglotic-hq 324)
      picking.py       words picked together in a list: Shift for a range, Ctrl for one more, the keyboard both, kept through a refresh (polyglotic-hq 342)
      pacing.py        captions arriving together let into a window the Lab's gap apart, in order, none dropped, none waiting past the longest wait for text (polyglotic-hq 284)
      presets.py       the ten colour presets (polyglotic-hq 248's section 6), which one a look's colours are, and the three recommended looks - whole looks, which one a look is (532); exact colours as typed, WCAG's contrast - and a label colour made readable on any panel
      preset_menu.py   the presets as the bar's dropdown and Settings > Presets show them (556): the list, the one in use, what shows and what's added; PresetsView, the learner's steps for main
      known_map.py     what Learning's map shows (489): each word's place, entry and chance in order, the tallies now and a week ago
      known_colours.py Learning load's colours (489): red to green or orange to blue by a word's chance, dark to light on a dark panel (light to dark on a light one), readable at 4.5:1
      tone.py          contrast and vibrance (481): a line's ink soft to crisp, never under the floor (3.7:1); a colour's chroma muted to vivid in OKLCH, greys left grey; readings' muted grey between the panel and what was said (532)
      reveal.py        a new caption's lines shown one at a time, the Lab's gap apart, oldest first, none waiting past the longest wait for text; all at once under the mouse, on a resize, scrolled back (polyglotic-hq 309)
      words.py         Words' rows: a word's text from the dictionary or what was saved, looked up only when its row shows; a search; the level in words (109's section 7)
    caption_layout.py  the caption layout engine: lines laid out per caption x width x text size, painted directly, marks at paint time
    reading_lines.py   a reading line over caption text (pinyin above Chinese, decision 0155): the room a reading needs beside its characters and the band above a line; the text itself unchanged (polyglotic-hq 364, 369)
    caption_surface.py one app's caption lines painted - a plain widget caption windows, transcripts and a joined window stand on
    video.py           owns Video's live and settled tracks, reading holds, history layout and painting
    caption_window.py  W1 draws the caption canvas, hover strip, notice line and Back to live (109's section 2). The strip measures its text and compresses its language, preset and timing chips to icons (polyglotic-hq 635). The window handles selection and lookup over its words (decision 0150) and holds new captions while the mouse is over words (decision 0262). The window leaves focus with the active app.
    settings_popover.py The gear menu serves caption windows, joined columns and the joined window. It opens the same dropdowns for chips that overflow the strip. Open caption bar controls gives a popover keyboard focus on request (polyglotic-hq 635).
    preset_popover.py  the bar's preset chip's dropdown (556): Preset (one), Show (one), Add (several), Customise presets…; a SettingsPopover, so it never takes the focus
    timing_popover.py  the bar's timing chip's dropdown (593): only the timings the preset's use offers (`core.listening.offers`), each with its line; folded into the preset dropdown where the bar is too narrow; a SettingsPopover
    presets_card.py    Settings > Presets: the presets to use, New preset, and the one in use to rename, reset or delete, with what it changes in words (556)
    caption_set_up.py  the first caption window on a PC asks its three language choices in it, once, never blocking: the settings popover's rows over the window, Start captions (465, decision 0217)
    unlock_spot.py     a locked caption window's Unlock: resting the mouse on its corner's lock for about a second shows a button there that takes the click the locked window passes through (polyglotic-hq 398); on a Wayland desktop its corner is a window of its own that keeps the mouse, Unlock shown as the mouse arrives, for 3 s (decision 0277)
    joined_window.py   W1j, the joined window: the apps' caption windows as its columns, side by side, equal widths or as the dividers were dragged (284); one place, lock, notice line and fade for the whole window (109's 2a, 10.6)
    caption_windows.py the caption windows, one per app captioned (at most 3): captions to each, their choices saved, what they ask of the session; joined and separated
    caption_selection.py a caption window's selection (358, decision 0150): the captions as shown, the place under the mouse, where the held words are drawn; kept until a click elsewhere or Esc, copied by a right-click or Ctrl+C, never taking the keyboard
    sentence_card.py   "Save sentence to" and the categories, under a caption window's selection of more than a word; never takes focus (polyglotic-hq 459)
    caption_marks.py   what a caption window marks at paint time: saved words, unfamiliar words and words in the deck (Learning), word links; a lookup's action forgets only the lines holding its entry; the quiet view's chosen words alone, in blue (polyglotic-hq 477)
    lookup_card.py     W3, the lookup card: one painted card for every caption window - hover after the mouse rests, pinned by a click, the actions, parts and Back, the context line, the speaker that says the word, its text selected by a drag and copied; never takes the focus (109's section 6)
    word_speech.py     the card's "say it" over the `Speaker` port: says or stops the word, its state, no voice and Windows' speech settings; the app's own sound handed to the captions' hush (polyglotic-hq 286)
    selection_reading.py Say it on a selection over the `Reader` port, app-wide: a side's spoken form read, Stop, the word being said told to the window that lights it, the side used last first, never while dictation holds the mic (polyglotic-hq 495, decision 0229)
    style.py           the window theme's colours as tokens (today's `ui.theme`, handed over by `main`) and a stylesheet scoped to one window - never the app's; the text size, Windows' times the app's own (`text_scale`, `px`: decisions 0033, 0084 and 0244)
    controls.py        small standard controls: a card, a setting's row, a row of choices, a switch, a colour choice, a status dot; every label's words can be copied (`copying.Text`); rows made again keep the keyboard on the same control, so the page doesn't scroll to the next one (`focus_kept`, polyglotic-hq 480)
    copying.py         copying any text a learner can see: a label selected with the mouse (from its first hover), Ctrl+C and its right-click menu - Copy, Select all; painted text selected by a drag (`TextSelection`, the lookup card's); a right-click copy on a window that never takes the keyboard (`copy_quietly`: the card's, and for the caption windows) (polyglotic-hq 343)
    caption_preview.py Settings > Captions > Look's live preview: two made-up captions over the app's own painted still, drawn by the caption windows' engine in the look now - never a screen capture
    lab_panel.py       Settings > Captions > Lab: the experimental controls, a preview of their own and Reset the lab - a card in its own file (polyglotic-hq 284)
    colour_controls.py the look's colour controls: the recommended looks as tiles, each a caption in it (532); the presets as tiles (as many to a row as fit) and one colour exactly - its swatches, a hex field and Pick... (the colour dialog); contrast and vibrance's two sliders (481)
    glyphs.py          the caption windows' icons - lock, settings, close, more, the mic - drawn with QPainter in the manner of Windows' icon font, which other OSes lack (polyglotic-hq 179); and Settings' sections' and cards' marks (470)
    fonts.py           each OS's own fonts, after Windows' in every font list (none on Windows: its lists are as they were); a caption's faces by its language - the learner's choice, its script's default (Chinese's a calligraphy face, its sans behind it: decision 0249), the OS's own, the Latin ones - which are never slanted (Arabic) and how much larger a script is drawn (polyglotic-hq 482, decision 0223)
    face_rows.py       Settings > Captions > Look's Fonts card: a row per captioned language, its list grouped Sans / Serif / Handwritten / This PC's own / Any font on this PC (the PC's fonts listed when first opened); the single Font row's place (polyglotic-hq 482)
    caption_faces.py   the captions' faces the app carries (`fonts.BUNDLED`, in `ui/assets/fonts`) and those downloaded before, added to Qt's fonts by the first caption layout before it lays anything out; a face that lands later added at once, every caption layout laying its rows out again (`generation`); whether a face has a weight of its own (readings' SemiBold) (482), and the lightest the faces in use have, for Look's Thickness steps (532)
    first_window.py    Windows' first-time work for a process's first window (about 0.1 s) done ahead of the main window, by a hidden widget given its window and deleted, in `main`'s wait for the fonts (322, decision 0113)
    fonts_ahead.py     Windows' fonts read ahead of the first window on a thread of their own, by the OS adapters' call that doesn't hold the interpreter; `main` waits for it before the first font is used (322, decision 0112)
    home.py            Home: the state line, the app picker, the caption windows' commands, feedback - in a centred column at most 720 px wide (Languages and Timing moved to Settings > Captions, polyglotic-hq 261)
    maintenance.py     a planned maintenance window's words for Home's banner and title (and so the tray's) and the caption windows' one line, in the learner's time (polyglotic-hq 319)
    main_window.py     W4, the new main window: the sidebar (Home, Words, Learning, Account; Settings and Help at its foot; Quit), a page at a time, opening at 960 x 680 times the text size or the size the learner left it, minimum 760 x 520 at text sizes up to 1.8 (decision 0276), its theme its own stylesheet
    no_tray.py         closing the main window where the desktop has no tray (GNOME without its extension): the app runs on, a box says so once and offers Quit, the window back from the launcher (polyglotic-hq 571, decision 0278)
    panels.py          the shared panels - Languages (Settings' Speech), Timing, and the look's Look, Word links, Behaviour and Reset - each one widget bound to one view, in Settings > Captions and a transcript's rail; each setting's line under its name in Settings, on hover in the rail
    words_page.py      Words (today's Vocabulary, renamed): a section per language learned (`LanguageSection`; one today, simply open; several fold under a heading with the count, left as the learner left them - `OpenLanguages`, polyglotic-hq 250), each that language's words (`LanguageWords`): the level, what you've heard (`heard_card`: words met, coverage of the last 7 days, listening time, and the bands - `word_bands`; the summary line under the title), words you keep hearing, your words, saved words and their categories, the Anki export; a word pins the caption windows' lookup card
    saved_sentences.py Words' Saved sentences: searched in either language by most of the query's words, filtered by category or saved word; moved, removed (polyglotic-hq 459)
    word_table.py      a list of words as a painted table as tall as its rows (the page scrolls): a row's text looked up when it first shows, its actions as buttons, the keyboard's too
    learning_page.py   Learning: a card per language being learned (its dictionary's tier and what that gives, its level, make it the main language, stop), Learn another language, Word introductions (Off · A few per caption · Every new word, with a caption drawn with the marks), the map of the language in use (known_map_card.py: its 20,000 commonest words by how well they're known, 489), Words and Anki, the dictionaries on this PC (decision 0122), Account's "Delete learning data…" (polyglotic-hq 262)
    load_card.py       Learning's card for the learning load while the Lab's mode is on: the stages in a bar, the four lists with the one-click check, "Add the next" words, and the load's rules (polyglotic-hq 324)
    pack_row.py        a language's dictionary pack on its Learning card: what it's doing in words, a flat bar that never moves by itself, and Download, Cancel, Retry, Download anyway, Get it now (decision 0122)
    account_page.py    Account: sign in or out and the account ID, what's shared, deleting learning data, feedback - today's commands, wired by `main`
    settings_page.py   Settings: ten sections at its top, each named for what a learner comes to change, every setting one click away (polyglotic-hq 304, 470; before it 248, 261) - Look (the look, Reset), Word links (and the way to Learning; the quiet view's card beside it, 477), Readings (pinyin, Jyutping, furigana, Russian's stress, Korean's and Hindi's romanization, English's respelling), Timing (timing and Behaviour), Speech, Dictation, Hotkeys (every key in one place, each changed, cleared or reset: `hotkeys_card.py`, 567), App (text size, appearance, updates, About and the third-party notices) and the experimental Lab; the title and tabs pinned while it scrolls, the card scrolled into named under them, the tabs a dropdown where they don't fit on one line, the app's language under the title (decision 0218); a caption window's "All caption settings..." opens it on Look, the tray's "More languages…" on Dictation
    settings_marks.py  Settings' cards marked: a card's title beside its mark in a soft square, and the pinned name of the card scrolled into (polyglotic-hq 470)
    help_page.py       Help: the live "no captions?" check, set-up and questions in the new interface's words, a report with the check's result
    hotkeys_card.py    Settings > Hotkeys: each hotkey's key in a box that listens for a new one, Clear and Reset all, why a key is refused, another program having it; dictation's key named; the keys windows answer, listed (polyglotic-hq 567, decision 0273)
    languages.py       languages by name, for the language chip and the language spoken; the languages to pick; dictation's - every one the speech model takes, Chinese with the characters it types (283); the spoken languages' own names, their order and how Detect and a named language are said (317)
    spoken_nudge.py    a caption window's question once Detect has heard its app speak one language steadily: "Always hear it as ...?" - Yes, Not now; never takes the keyboard (317, decision 0109)
    strip_tips.py      what a caption window's (and a joined window's) strip buttons do, said on hover: a label of its own above the window, since Qt shows tooltips only on an active window and a caption window never is (395)
    spoken_list.py     the spoken-language list, the same everywhere: Detect and how many it covers, then every language the model hears - named last, the learner's own, the rest by name; found as it's typed in Settings and a transcript's rail, no box in a caption window's settings; made when first opened (317, decision 0108)
    transcript_window.py W2, the transcript window: the app strip, the lines painted on the layout engine (only what shows; a layout cache of its own), search, Back to live, the lookup (the caption windows' card), text selected by a drag and copied, copy and save, the settings rail with the session's panels (a popover over the list below 700 px); dressed in the new interface's window theme (`style`)
    transcripts.py     the transcripts, one per app captioned, collecting from the start: each following its caption window's language and my speech, its window opened on demand (Open transcript, the tray), their rails' panels bound to the session's views, their choices saved; Quit asks once about a long one not saved (334)
    dictation_sign.py  dictation's sign: a pill above the taskbar - Listening with the mic's level, Working, then why nothing was typed, naming the key; which key to hold as dictation's turned on; never takes the focus, clicks pass through (283, 289)
    dictation_key.py   dictation's key in words ("Ctrl + Alt + D"), why one is refused, and Settings' box that listens for the key pressed (289, decision 0081)
    save_folder.py     where every save dialog opens (Save transcript as..., both Anki exports): the folder saved to last, kept in the settings, or Documents - never the install folder an update replaces (polyglotic-hq 244)
    wheel.py           the mouse wheel scrolls the page, never a list, slider or number box it passes over; a slider or number box takes it once clicked; one guard each scrolling page puts on (`home.Page`, the transcript's rail), watching only those controls (polyglotic-hq 304, decision 0092)
  perf/              measuring the interface
    budgets.py         the budgets the user agreed (DECISIONS.md #53): one place for the numbers tests and the lab check
    spans.py           named spans, off unless recording (the lab); timings as JSON - names checked to be constants, never text
    start_parts.py     the start's parts, by name: `main` marks where each ends, so the time from `main()` to the first paint is all accounted for (314)
    trace.py           each caption update's timeline from the sound to the screen - the capture, the send, the server's numbers, the interface thread, the window's hold, the paint - kept 5 minutes in memory, written to `logs/trace.jsonl` on a PC that asks (decision 0255; polyglotic-hq 543)
    trace_summary.py   what timelines say: segments, hangs and their causes (`sound_unheard` among them, decision 0256), bursts, drops; the usage statistics' summary and a problem report's rows
    turns.py           short turns at the interpreter while a long stretch of Python runs beside the interface: a pack's warm-up (decision 0207)
    watchdog.py        logs any stretch of interface-thread work over 50 ms by `file.py:function` and duration; on in normal use (`main` starts it)
  adapters/          storage and other infrastructure behind the ports
    sqlite_dictionary.py  the dictionary files (decision 0009); the learner's never stops the app (199)
    audio_file.py         a pack's commonest words recorded ahead of time, Ogg Opus with the shared header kept once, on 64 kB pages (decision 0133; polyglotic-hq 405); a pack's rider, fetched after it (0192); a built-in dictionary's (CC-CEDICT's) from the list's own `built_in` entry, only for its learners (0197)
    meanings_file.py      a dictionary's meanings in one more language, by entry ID: a rider of its pack, or of a built-in dictionary (ECDICT's in each learner's language), read through a shelf every dictionary sees; people's only - a machine's rows wait for a label (decision 0234)
    traditional_table.py  the Simplified -> Traditional table in `data/` (OpenCC's, Apache-2.0; made by `tools/traditional_table.py`), read when Traditional is first wanted (decision 0164)
    japanese_split.py     Japanese words and their dictionary forms, by Sudachi (the basic Japanese pack, decision 0035)
    spaced_split.py       words of a spaced language with simplemma's lemma (the basic Spanish pack, decision 0035)
    sqlite_learning.py    the learner's own learning data on this PC (decision 0010); what they heard, and daily counts kept 8 weeks (0041); one that can't be read set aside and kept (polyglotic-hq 206); a row it can't read left out and kept, too many refused (207); the level kept beside it too, so a store set aside keeps it; a file per language (`learning.sqlite`, `learning-en.sqlite`, `learning-ru.sqlite`: decision 0175) (0048); lookups kept, version 8 (polyglotic-hq 373)
    background_learning.py  that store on a thread of its own: Learning's saves never wait on the disk; reads wait for the writes before them (110)
    anki_package.py       the Anki deck file (.apkg), with genanki (decision 0028)
    json_settings.py      the user's settings, one JSON file (and read only, by a second start: decision 0101)
    windows_credentials.py  the device token in Windows Credential Manager; signing out keeps the install id (0080)
    sqlite_outbox.py      what waits to be sent to the server, and the consent choices (decision 0013); an unreadable file set aside
    background_outbox.py  that outbox on a thread of its own: the consent choice and every event are written in order, never on the interface thread; reads wait for the writes before them (144)
    velopack_updates.py   the installer's hooks at start, and updates through Velopack (decision 0017); on Linux's AppImage, each user's own packages folder and an update applied as the app exits (decision 0259)
    feedback_files.py     reports waiting to be sent, one JSON file each (apart from the content-free outbox)
    problem_report_files.py alpha testers' problem reports waiting to be sent, each as its request body (275)
    app_log.py            the app's log as a report attaches it: the newest part, the user's folder hidden
    signed_feed.py        the update feed checked against our signature, for its channel, before Velopack reads it (decisions 0019, 0020; off until main.FEED_KEYS is set)
    pack_list.py          the dictionary packs' list checked against the feed's keys, with a prefix of its own, and its last good copy kept (decision 0122)
    pack_downloads.py     the packs on this PC (each read by its own info) and their downloads, one at a time on a thread of their own: carried on, paused on a metered connection, retried, checked whole, opened, then renamed; each step in the log, content-free (decision 0122); a caption face's files as one download (`font`, polyglotic-hq 482)
    relaunch.py           relaunching the app into a newly chosen interface language after releasing the single-instance lock: Windows installed executable, Linux `$APPIMAGE`, macOS `open -n <Polyglotic.app>`, or source `python -m polyglotic_desktop.main` (658)
  ports/             the interfaces core needs from outside, and the plain types that cross them
    capture.py         AppList, AudioCapture, SourceCategory, AppCaptureSupport and AppCaptureTrial (0076) - what capture needs from the OS; HeldMic, MicPiece - the mic while the dictation key is held (283)
    mic_bleed.py       MicBleedCheck - the mic's audio vs what the PC played
    dictionary.py      DictionaryFile - one dictionary's entries on disk
    word_split.py      WordSplit, SplitWord - the words in a line of one language, and the dictionary forms to look them up as
    learning.py        LearningStore - the learner's own learning data on this PC
    settings.py        SettingsStore - the user's settings, remembered between launches
    credentials.py     CredentialStore, DeviceCredentials - the install id and device token
    outbox.py          Outbox, Waiting - what waits on the PC to be sent to the server
    consent.py         ConsentStore, ConsentChoice - the user's consent choices
    updates.py         Updater, Update - the installer's updates
    feedback.py        WaitingReports, Report - feedback kept on the PC until sent
    problem_reports.py WaitingProblemReports, ProblemReport - an alpha tester's report, with captions and audio if left ticked (275)
    system.py          OnTop, ForegroundWatch, Hotkeys, HoldKey, TypeText, KeyboardWindow, KeyState, LightTaskbar, TaskbarIdentity, StorePackage, OsVersion, DataFolder, ErrorBox, LaunchClock, Translocation - what the app needs from the OS beyond audio (decision 0038; Translocation, 0205)
    startup.py         StartWithWindows - the app in the tray at sign-in, once the learner says yes (176); `IN_TRAY`, the switch it starts the app with
    one_copy.py        CopyLock, LetToFront - one copy per user and data folder: the lock the copy that runs holds, and its window let to the front (decision 0101)
    speaker.py         Speaker, Reader, Voice - a word said aloud in one of the PC's voices, a selection read a sentence at a time with each word told as it sounds, and when the app's own sound plays (286, decision 0077; 495, decision 0229)
  main.py            the one place that wires everything together (the connection, the outbox and the first-run screens too); `os_adapters` picks the OS's adapters, imported only there (decision 0038)
  harness.py         a developer's command line: capture, sign in, listen to a server and print captions (no UI); consent, learn, sync, delete
docs/
  decisions/         one page per structural decision
  rule-cases/        the rules as JSON cases a later port must pass: timing, the known line, highlights, word split, display, the playout and its zones (decision 0022)
tools/
  dictionaries/      builds the dictionary files from pinned sources (decision 0009); a pack's coverage of 100 FLEURS sentences, a word shown by its parts counted as found (decision 0250); its ranks checked for junk (decision 0162) and its 200 commonest words for entries (polyglotic-hq 390; `coverage.top_words`, words kaikki's extracts lack in `packs.MISSING_PAGES`); one Wiktionary reader for spaced languages (decisions 0168, 0171); English's meanings in English, `ecdict-en.sqlite` (decision 0211); entry IDs
    registry/        the entry IDs that aren't their key's hash (decision 0007)
  protocol_examples.py  copies and checks polyglotic-server's protocol examples (decision 0011)
  tracking_plan.py   copies and checks polyglotic-server's tracking plan (decision 0271)
  rule_cases.py      writes and checks docs/rule-cases/ from the rules (decision 0022)
  caption_fonts.py   how the captions' bundled faces in `ui/assets/fonts` were made, from pinned sources: Medium instances, Noto Sans SC's and Ma Shan Zheng's cuts and readings' SemiBold, the line boxes (polyglotic-hq 482, 532; decisions 0223, 0249); not part of the build
  mypy_platforms.py  mypy as macOS and Linux see the code: only Windows' own modules may fail (decision 0038)
  linux_qt_libs.sh   Qt's system libraries for the Linux runner, unpacked without root (decision 0038)
  app_tour.py        the app from source on this OS's real windows, signed in to a stand-in server, captioning the app's own FLEURS sample fed straight in: checks and each window's grab() - Home, a caption window, the card, Words, Settings, the transcript (the macOS job, decision 0186); with `--real-capture` (Linux, 550) the sample played through the sound server and another into the mic, captured by the OS's own adapters, the token in the OS's keyring
  linux_session.sh   a Linux desktop session on GitHub's runner for the Linux job: PipeWire with a default output and a real default mic, gnome-keyring unlocked (or no keyring at all: `LINUX_SESSION_KEYRING=none`, 574), and a screen - Xvfb, or GNOME's (mutter) or KDE's (KWin) window manager headless with XWayland (polyglotic-hq 550)
  linux_desktop_tour.sh, linux_in_fedora.sh  the tour over a focused full-screen Wayland window on GNOME and KDE (Fedora 45's in a container), with the window manager's own pictures of its virtual screen (550)
  linux_desktop_pictures.py  those pictures: mutter's ScreenCast or KWin's ScreenShot2, on the tour's request; and the full-screen window beneath (550)
  linux_keyring_probe.py  which keyring answers the Secret Service and whether it takes the plain session (gnome-keyring; KDE's ksecretd or kwalletd6), through the app's own store (550)
  linux_manners.sh, linux_manners_check.py, linux_tray_menu.py  the desktop's manners on GNOME (no tray: the box, the launcher, Quit), Xfce and KDE (the tray's menu read over D-Bus as the desktop's tray reads it, an item clicked there), on GitHub's runners (`linux-manners.yml`; 571)
  linux_packed_tour.sh, linux_packed_tour.py  the packed AppImage - the release's own file, run as a learner runs it - on Ubuntu 24.04's GNOME, Ubuntu's GNOME with its AppIndicator tray, Fedora 45's GNOME, KDE Plasma 6 and Xfce with no keyring, checked only from outside: its hello to a stand-in over TLS, the sources heard (what the PC plays, the mic, one app alone), the X server's windows and the desktop's own picture of its screen (captions above a full-screen window; Home light or dark), the menu entry, the tray's menu over D-Bus, Save transcript's and the Anki export's dialogs asked of the portal (574, decision 0281)
  linux_atspi_press.py  a button of the packed app pressed as a screen reader presses it, over AT-SPI from another process, by its accessible name (574)
  linux_release_verdict.py  Linux's release check as one answer: 546's seven checks and the desktops' manners from each part's findings; a part that didn't arrive is red (`linux-release.yml`; 574)
  macos_measure.py   what a GitHub macOS machine allows for capture: BlackHole, the sound devices, whether a system-audio permission can be written; reported, never failing (decision 0186)
  macos_parity_checks.py  the Mac's hotkeys (pressed by AppleScript), the card's voice (said on BlackHole and heard; a recorded word and Say it judged for silence, clipping, level, length and pitch: polyglotic-hq 523), the menu-bar icon and the packed app's login item, on GitHub's macOS machine; pass, fail or unknown each (polyglotic-hq 428)
  macos_full_screen_checks.py  the caption windows over a full-screen TextEdit (the window list's levels and order), dictation's typing and key, Esc and clicks elsewhere, on GitHub's macOS machine; pass, fail or unknown each (polyglotic-hq 429, 438)
  macos_capture_checks.py  Mac capture checked on GitHub's macOS machine, on BlackHole: one app's tap, everything else, global and device taps, the mic, the clock's drift, the packed app's own `--check-capture`, and the permission taken away; pass, fail or unknown each, only a fail failing (polyglotic-hq 412)
  macos_learner_checks.py  the packed app as a learner's Mac meets it, on GitHub's macOS machine: python.org's Python, Homebrew and the developer tools moved aside; what the bundle links; the zip from Downloads, quarantined, through Gatekeeper, translocation and the move to Applications; a fresh macOS user's checks; pass, fail or unknown each (polyglotic-hq 523, decision 0243)
  macos_settings_sweep.py  every setting changed and put back on the Mac's windows, from source, judged: a part that broke, too few changes, an error, a setting not put back (polyglotic-hq 523, from 515's sweep)
  private_desktop.py real windows on a Windows desktop of their own, never shown: a command run there, its windows read from outside, pictures by its own grab() (docs/real-windows.md)
  window_icon.py     a window's icon as Windows draws it (title bar, taskbar, Alt-Tab), read from outside its process, and whether it's the app's (docs/real-windows.md)
  busy_pc.py         how busy the PC is: a budget test or lab state over budget gets more tries only while it's saturated (decision 0040); the start waits for it to calm, reads the rest of the PC's load during each start, and counts it busy from 30 % (decision 0103)
  ci_lock.py         CI's timed start holds a lock on the PC alone, the heavy steps share it, so the two Windows runners' jobs don't time each other's load (decision 0105)
  qt_lock.py         off CI on the user's PC, a pytest run with a Qt test in it and the UI lab's command wait their turn for the agents' shared `qt.lock` (numbered tickets in `qt.lock.queue`, oldest live first, as polyglotic-hq's `qtlock.py`) and 3.0 GB free, hold the lock as their wrappers write it, keep it fresh, and stop under 2.0 GB (pytest; polyglotic-hq 563, 569)
  learner_start.py   the app's start with a made-up learner of many words met, timed from `main()` to the window, with its parts and the threads begun before the paint: CI's start gate on the real CC-CEDICT (decision 0046)
  start_record.py    the start's parts beside main's last record on the runners' PC: CI's start tests print which part grew (314; recorded, not gated) - the gate's start and the one with real windows, whose runs on main are also kept in a history (322, decision 0111)
  trace/             the caption timelines' viewer: a page from the trace file, a problem report's log or the older caption log - each segment's percentiles, the hangs and their causes, close-ups (`python -m tools.trace <log>`, `--pictures`, `--summary`; decision 0255)
  timing_record.py   main's last timings on the runners' PC: a pull request's budget failure fails only if the change made the action 1.5x slower than main's record (344, decision 0136), at like load: main's scaled by the lab's reference step now over then (381, decision 0169); the pytest budget tests' record kept on Linux too, in the runner's home (decision 0270)
  ui_lab/            the UI lab: every state offscreen, a PNG and a timing JSON each, the code checks (clipped and small text, contrast, names, keyboard, scrollbars, squashed layouts) and golden images (goldens/, approved with `approve`), and the design detector (`design.py`: Impeccable's rules translated for Qt, gated on new findings against `design_baseline.json`, decision 0140; `design` writes its report); new parts gated on all three, today's recorded (decision 0031); `judge` writes the judge's kit - contact sheets, findings, timings, a checklist - for the review loop in JUDGE.md; `seen` finds which strings each state shows, the order of a reviewer's sheet (polyglotic-hq 294)
  i18n/              the interface's strings read from the code into translations/*.ts, compiled to .qm (`python -m tools.i18n update`; decision 0034); `draft` hands a language's untranslated strings to a drafter and checks its answers back in (`keep.py`: names, counts, tags, forms; polyglotic-hq 294); `sheet` makes a reviewer's spreadsheet
  package/           building the app testers install: the release stamp (decision 0015); PyInstaller one folder, checked (decision 0016); publishing it, the feed signed as served (decision 0020); the daily feed check, each channel against its latest Release; what a Release run does and a build promoted to another channel by repacking it, not rebuilt (`release_plan`, `promote`, `pack.sh`; decision 0044); a version's notes from RELEASE-NOTES.md, and the release's cut that moves Unreleased under its version (`release_notes`); the same build packed again as the Microsoft Store's MSIX, with the Windows SDK's tools pinned (`msix`; decision 0056); the dictionary packs and their signed list, laid out as the bucket holds them, a dry run unless `--upload` (`publish_packs`; decision 0122); chosen packs in the installer, off by default (`build --packs`, decision 0124); on macOS an app bundle, `Polyglotic.app`, its build's files in `Contents/Resources`, signed ad hoc, or with the release's self-signed certificate on the public copy (`build.Layout`, `sign`; decisions 0186, 0196); on a Mac, Velopack's packages - the portable zip testers download, the full package and the feed - with the app signed again as the build signs it (`pack.sh`, `macos_codesign.sh`), checked where they're made (`macos_release`), and an update from 0.0.1 to 0.0.2 applied and checked on GitHub's Mac (`macos_update_rehearsal.sh`; decision 0202); and the update from the published release to this build, settings, keychain item and designated requirement kept (`macos_update_from_release.sh`; decision 0243); on Linux, one `Polyglotic.AppImage` built in an Ubuntu 22.04 container, libxcb-cursor bundled and fontconfig left to the system (`linux_build.sh`, `build.LINUX`), checked on clean Ubuntu 24.04, 26.04 and Fedora 45 (`linux_linkage.sh`) and updated in place by two users (`linux_update_rehearsal.sh`; decision 0259)
translations/        the interface's translation files (.ts) - what translators and reviewers work in (README.md there; decision 0034)
build/               git-ignored: downloaded sources and built dictionary files
tests/               pytest; core tested through fakes, no devices or models
  protocol_examples/ a copy of the server's protocol examples, with its manifest (decision 0011)
  tracking_plan/     a copy of the server's tracking plan, with its manifest (decision 0271)
```

Each package's docstring says what belongs in it.

## What each module owns

| Module | Owns | Never |
|---|---|---|
| `core` | The domain rules of each context the app runs, in the glossary's words | I/O; Qt; imports of `ui`, `platform`, `connection`, `adapters`, `main` or infrastructure libraries |
| `core.shared` | Events contexts publish ("caption finished", "word looked up") and shared IDs (caption id, entry ID). Small immutable types - including what Lexicon tells Learning about the words in a line (`WordInLine`, `EntryFacts`). | Logic; imports of any context |
| `core.<context>` | That context's model and rules (DOMAIN.md's table) | Imports of another context; it reacts to others' events instead |
| `platform` | Turning one app's audio, the whole system's or the mic into speech segments | Caption rules; imports of `ui` or `connection` |
| `connection` | The WebSocket per listening session, the handshake, protocol messages <-> core, reconnecting, the offline event buffer; usage events only with consent; the server's address checked (TLS to anything but this PC, `addresses.py`) | Caption rules; imports of `ui` or `platform` |
| `ui` | Showing core's state in Qt and passing the user's actions to core | Domain rules; imports of `platform` or `connection` |
| `ui_next` | The new interface (decision 0031): what `ui` owns, rebuilt; `views` is plain Python | Domain rules; imports of `ui`, `platform` or `connection`; Qt in `views` |
| `perf` | The interface's budgets, and measuring its time - names and durations only; each caption update's timeline (times, counts, fixed words) | Caption text or words; imports of the interface |
| `ports` | Every interface core needs from outside (`typing.Protocol`s: `AppList`, `AudioCapture`, `MicBleedCheck`, `DictionaryFile`, `LearningStore`, `CredentialStore`, `SettingsStore`, `Outbox`, `ConsentStore`, `Updater`) and the plain value types that cross them (`SourceCategory`, `EntryRecord`, `DeviceCredentials`, `Waiting`, `ConsentChoice`, `Update`) | Imports of anything else in the package; infrastructure libraries |
| `adapters` | Storage and other infrastructure behind the ports: the dictionary files, the learner's learning data and the outbox (SQLite), the device token (Windows Credential Manager), the user's settings (JSON), updates (Velopack) | Domain rules; imports of `ui`, `connection` or `platform` |
| `main` | Update check first, then building platform, connection and UI, handing core its implementations, connecting them | Logic of its own |

The desktop's tunable defaults are declared beside their readers. The
`core.shared.tunables` registry validates typed layers and publishes one
snapshot. `tunable_config` wires the TOML adapter and the card reading rules
into startup and the developer CLI. See [decision 0289](docs/decisions/0289-tunables-beside-their-readers.md).

## The rules between them

| Rule | Checked by |
|---|---|
| Layers: `main` (and the developer's `harness`) → `ui` \| `ui_next` \| `connection` \| `platform` \| `adapters` → `perf` → `core` → `ports`; nothing imports upwards | import-linter `layers` |
| `ui`, `ui_next`, `connection`, `platform` and `adapters` don't import each other | import-linter `layers` (the `\|`) |
| The new interface's views use no Qt | import-linter `views-no-qt` |
| The new caption surfaces keep to their budgets at 1,000 captions | `tests/ui_next/test_budgets.py`, `test_transcript_budgets.py`; CI's UI lab job (`tools/ui_lab`, every new part's state) |
| An hour of captions, once the windows and transcripts are full, grows the app's private memory by at most 3 MB (`perf.budgets.MEMORY_HOUR`) | `tests/ui/test_memory_over_an_evening.py`, a synthetic evening on the interface as `main` wires it (Windows; decision 0049) |
| Words opens, and its first search answers, within budget (50 ms) for a learner with 10,000 words met | CI's UI lab job: the `words_met_*` states (`tools/ui_lab/pages.py`; 30,000 recorded, not held; polyglotic-hq 212, 220); `tests/ui/test_words_read_ahead.py` (the first search reads nothing) |
| Every string the interface shows reaches the translation files; English's counts read as English; translations keep their placeholders, counts, tags and forms; every language offered has its file, and every file is offered | `tests/ui/test_translations.py` (`tools/i18n`, decision 0034) |
| `perf` records names and durations only: span names are constants; the watchdog names code, never its data | `tests/test_perf.py` |
| `core` and `ports` import no Qt, audio, Windows API, network, storage or vendor library | import-linter `core-no-infrastructure` (the list is in `pyproject.toml`) |
| Contexts inside `core` don't import each other; they meet in `core.shared` | import-linter `contexts-independent` and `shared-imports-no-context`; `tests/test_layout.py` keeps the lists in step with the folders |
| `core` and the protocol (`connection`) are fully typed | mypy, strict for `core` and `connection` (normal elsewhere) |
| Only Windows' own modules (`platform/windows`, the Windows credential store), the Mac's (`platform/macos`) and Linux's (`platform/linux`) are imported by `main` alone; only Windows' may fail to type-check as macOS and Linux see them (the Mac's type-check on every OS) | import-linter `os-in-one-place`; `tools/mypy_platforms.py` in CI (decision 0038) |
| Tests that need Windows (or macOS) itself say so, and are skipped elsewhere; the rest pass on Linux | the `windows_only` and `macos_only` markers (`tests/conftest.py`); CI's Linux job (`Checks (Linux)`, Qt's libraries from `tools/linux_qt_libs.sh`) |
| The app's messages match the server's protocol examples | `tests/test_protocol.py`, against a copy kept by `tools/protocol_examples.py` (decision 0011) |
| The rules give the answers in `docs/rule-cases/` | `tests/test_rule_cases.py`, reading only the JSON (decision 0022) |
| Usage events only from the server's tracking plan, only with consent | `connection.exchange` keeps usage events and exposure counts only with their consent (`tests/test_exchange.py`); every property and value the app can send, from its own enums and builders, against a copy of the plan kept by `tools/tracking_plan.py` (`tests/test_usage_events_fit_the_plan.py`, decision 0271) |
| Flags are read only through one `flags` module | Review (the module isn't built yet) |
| Audio and caption text never logged; app names leave the PC only as categories - a known app's public name only in consented usage statistics (DECISIONS.md #30) | Review (checklist item 9); `tests/test_session_summary.py` and `tests/test_windows_capture.py` (only listed names, never with speech) |

Loosen a contract only with a decision record saying why.

## The interface's rebuild (decisions 0031 and 0032)

The interface was rebuilt, beside today's `ui/`, in Qt Widgets done
well (polyglotic-hq project 108's audit, DECISIONS.md #53). Since the
switch-over (decision 0032, 2026-11-07) it is the app:
- **`main` starts the new interface:** the caption windows
  (`ui_next.caption_windows`, one per app captioned, at most 3, or one
  joined window), a transcript window per app (`ui_next.transcripts`)
  opened from them and the tray, and the new main window
  (`ui_next.main_window`: Home, Words, Account, Settings and Help). No
  app-wide stylesheet: each window has its own. Today's tray and dialogs
  stay; `main` wires the new parts to them. `DesktopApp` (`ui.app`) keeps
  the app's state - the session's, the commands, the tray - and the
  windows follow it; today's main window, overlays and pages are gone.
  The developer switch
  `--next-interface` is accepted and ignored until the first release
  after it, then removed.
- **`ui_next/` sits in `ui/`'s layer;** neither imports the other.
- **`ui_next/views/` is plain Python, no Qt:** what each surface shows,
  tested without Qt. Qt widgets draw a view and hand actions back to it.
- **One caption layout engine** for caption windows and transcripts:
  newest first, only what shows, cached per caption x width x text size
  for the lines each surface can show again (a caption window's 150, a
  transcript's last 300 shown; polyglotic-hq 239); text painted directly;
  marks drawn at paint time.
- **`perf`** (spans, the interface-thread watchdog, timings as JSON) sits
  between the interface and core, so `ui`, `ui_next` and `main` can use
  it; the budgets live in `perf.budgets` and are tests.
- **The UI lab** (`tools/ui_lab/`) drives states offscreen and writes a
  PNG and a timing JSON per state, and runs the code checks on every
  window a state shows (`checks.py`: clipped text, text under 12 px,
  contrast, accessible names, keyboard reach, horizontal scrollbars,
  squashed layouts), and compares each new part's picture with its
  approved golden (`goldens.py`; `goldens/` holds the PNGs, made on the
  user's PC where CI runs); CI gates the new parts' budgets, checks and
  goldens and records today's interface's numbers and findings. A
  timing over budget is retried once, and up to twice more while the PC
  measures saturated (`tools/busy_pc.py`, decision 0040). On a pull
  request, a timing still over but not 1.5x slower than main's record on
  this PC is "over its budget as main is": a warning, not a failure; main's
  own runs keep the record and are held to the budget alone (the lab and
  the pytest budget tests; `tools/timing_record.py`, decision 0136). In the
  lab, main's record is first scaled to the pull request's load: a fixed
  reference step is timed before each gated state, and main's timings are
  multiplied by the steps now over main's (`tools/ui_lab/reference.py`,
  decision 0169).
- **The start's budget** is held twice: `--check-install` with an empty
  learner, and the UI lab job's start gate with a made-up learner of
  30,000 words met on the real CC-CEDICT (`tools/learner_start.py`,
  decision 0046), its tries taken on a calm PC where it can be and a
  failure while the PC was busy named "over on a busy PC" (decision 0103).
  That gate is offscreen. **The start a learner sees** - real windows on a
  private desktop, on to the first answered click - is timed beside it and
  recorded against main's, not gated yet (decision 0111).

## Decisions

- [0001 Ports and adapters on the desktop, checked by import-linter](docs/decisions/0001-ports-and-adapters.md)
- [0002 One package per bounded context; contexts meet in core.shared](docs/decisions/0002-bounded-contexts.md)
- [0003 The speech-detection model is committed, pinned by its checksum](docs/decisions/0003-speech-detection-model-committed.md)
- [0004 Mic bleed is checked against the whole system's audio](docs/decisions/0004-mic-bleed-reference-is-system-audio.md)
- [0005 Speech is sent as Ogg Opus at 24 kbit/s, encoded by libsndfile](docs/decisions/0005-speech-as-ogg-opus-24k.md)
- [0006 Windows capture is our own WASAPI code through ctypes](docs/decisions/0006-windows-capture-with-own-ctypes-wasapi.md)
- [0007 Stable entry IDs: a hash of the entry's first key, plus a registry of exceptions](docs/decisions/0007-stable-entry-ids.md)
- [0008 Every interface core needs in `ports/`; storage in `adapters/`, as on the server](docs/decisions/0008-ports-and-adapters-packages.md)
- [0009 Dictionary files: SQLite, built from pinned sources, not committed](docs/decisions/0009-dictionary-files.md)
- [0010 The learner's own learning data on the PC: one SQLite file, behind a port](docs/decisions/0010-learning-data-in-sqlite.md)
- [0011 Protocol messages as pydantic models, tested against a checked copy of the server's examples](docs/decisions/0011-protocol-models-and-a-checked-copy-of-the-examples.md)
- [0012 The server connection is `websockets` on asyncio, in a thread of its own](docs/decisions/0012-websockets-on-asyncio-in-a-thread.md)
- [0013 What waits for the server is kept in an outbox on disk; sync sessions open on threads of their own](docs/decisions/0013-outbox-and-sync-sessions.md)
- [0014 The user's data lives in `%APPDATA%\Polyglotic`, outside the installer's folder](docs/decisions/0014-user-data-in-roaming-app-data.md)
- [0015 A release's version comes from its git tag; the server and update addresses are constants in code](docs/decisions/0015-version-from-the-tag-addresses-in-code.md)
- [0016 The app is packed by PyInstaller as one folder, built and checked by `tools/package/build.py`](docs/decisions/0016-pyinstaller-one-folder-build.md)
- [0017 Updates: Velopack behind a port; core decides when; applied at the next start](docs/decisions/0017-updates-through-velopack.md)
- [0018 Releases are built, packed and published by a tag-only workflow, and the public feed is checked daily](docs/decisions/0018-release-workflow.md)
- [0019 The signed update feed: Ed25519, checked by the app before Velopack reads it - built, switched off](docs/decisions/0019-signed-update-feed.md)
- [0020 The update feed is signed and recorded as the storage serves it, with its channel inside the signature](docs/decisions/0020-feed-signed-as-served.md)
- [0021 The installer is built and tried on main, not on every pull request](docs/decisions/0021-installer-built-on-main-not-pull-requests.md)
- [0022 The app's rules are written down as shared test cases, in JSON, for any later port to pass](docs/decisions/0022-rules-as-shared-test-cases.md)
- [0023 Learning done after a deletion counts as after it, whatever the PC's clock](docs/decisions/0023-learning-after-a-deletion-whatever-the-clock.md)
- [0030 "Looks wrong?": a line checked with the best model, over the listening session, nothing kept](docs/decisions/0030-looks-wrong-checked-with-the-best-model.md) - its interface taken out by 0131
- [0031 The interface is rebuilt in Qt Widgets, beside today's, on plain-Python views](docs/decisions/0031-interface-rebuilt-in-qt-widgets-beside-today.md)
- [0032 The switch-over: the new interface is the app; today's main window and overlays go](docs/decisions/0032-switch-over-new-interface-is-the-app.md)
- [0034 The interface is translated through Qt's .ts files, read from our own wrappers, with English's counts in a file too](docs/decisions/0034-interface-translations-qt-ts-files.md)
- [0038 The OS's adapters are picked in one place, at start, and nothing else imports them](docs/decisions/0038-the-os-picked-in-one-place.md)
- [0039 Speech detection hears quiet audio raised to -20 dBFS; the audio sent is unchanged](docs/decisions/0039-speech-detection-hears-quiet-audio-raised.md)
- [0044 One build per tag: promoted to another channel by repacking it, not rebuilt; a hotfix tag publishes only where it's sent](docs/decisions/0044-one-build-per-tag-promoted-not-rebuilt.md)
- [0045 The install-and-update test runs by hand in the PC runner's own Windows account, then uninstalls](docs/decisions/0045-install-test-in-the-runners-own-account.md)
- [0046 CI holds the start to its budget with a made-up learner of 30,000 words met](docs/decisions/0046-the-start-gated-with-a-big-learner.md)
- [0048 The learner's level is kept beside the learning store as well as in it](docs/decisions/0048-the-level-kept-beside-the-learning-store.md)
- [0049 An hour of captions may leave at most 3 MB behind: a memory budget CI holds](docs/decisions/0049-an-hour-of-captions-leaves-little-behind.md)
- [0051 Windows knows the app by one taskbar ID: the installer's when installed, `Polyglotic.Desktop` from source](docs/decisions/0051-one-taskbar-id-the-installers-or-polyglotic-desktop.md)
- [0056 The Microsoft Store gets the same build, packed again as an MSIX; the Store updates that copy](docs/decisions/0056-the-store-gets-the-same-build-as-an-msix.md)
- [0057 The installer gives the app and its shortcuts one taskbar ID: the pack ID's `.Desktop`](docs/decisions/0057-the-installer-names-the-app-polyglotic-desktop.md)
- [0066 A change settles before it leaves the interface: shown at once, saved and sent 300 ms after the last](docs/decisions/0066-a-change-settles-before-it-leaves-the-interface.md)
- [0073 Dictation: a source of its own on the listening session, one piece per hold, typed into the program with the keyboard](docs/decisions/0073-dictation-rides-the-listening-session-and-is-typed.md)
- [0081 Dictation's key is the learner's choice; Right Ctrl alone is read, never hooked](docs/decisions/0081-dictations-key-is-the-learners-choice-right-ctrl-is-read-not-hooked.md)
- [0077 A looked-up word is said in Windows' own voices, behind a `Speaker` port, and kept out of the captions](docs/decisions/0077-a-word-said-in-windows-own-voices-behind-a-speaker-port.md)
- [0080 The install id outlives signing out, and each server keeps its own sign-in](docs/decisions/0080-the-install-id-outlives-signing-out.md)
- [0090 A downloaded update is offered on Home and in the tray, with Restart now](docs/decisions/0090-a-downloaded-update-is-offered-with-restart-now.md)
- [0091 Two hearings are lined up by the fewest words passed over](docs/decisions/0091-two-hearings-are-lined-up-by-the-fewest-words-passed-over.md)
- [0095 Every full language learned is open at once, each line in its own; each keeps its own learning data and categories](docs/decisions/0095-every-full-language-learned-is-open-at-once.md)
- [0097 Live updates wait their turn under the server's speech ceiling](docs/decisions/0097-live-updates-wait-their-turn-under-the-speech-ceiling.md)
- [0099 How long shown text may still change is the learner's choice, 0 to 3 seconds](docs/decisions/0099-how-long-shown-text-may-change-is-the-learners-choice.md)
- [0101 One copy per user and data folder: a named mutex holds it, a local socket asks it to show](docs/decisions/0101-one-copy-per-data-folder-a-named-mutex-and-a-local-socket.md)
- [0102 A consent choice is dated after the one it replaces, and goes again at most once a day](docs/decisions/0102-a-consent-choice-is-dated-after-the-one-it-replaces.md)
- [0100 A poured caption keeps a layout per row: the pour only says where each row's lines go](docs/decisions/0100-a-poured-caption-keeps-a-layout-per-row.md)
- [0122 Dictionary packs arrive by a signed list on the update storage, downloaded when a language is added](docs/decisions/0122-dictionary-packs-arrive-by-a-signed-list.md)
- [0123 The installed app splits a pack's words without simplemma; Sudachi stays out](docs/decisions/0123-the-installed-app-splits-pack-words-without-simplemma.md)
- [0124 Chosen dictionary packs can ride in the installer, by a build switch, off by default](docs/decisions/0124-chosen-packs-can-ride-in-the-installer.md)
- [0126 Captions are copied as the transcript copies them, to the clipboard only](docs/decisions/0126-captions-are-copied-as-the-transcript-copies-them.md)
- [0131 "Looks wrong?" leaves the interface; the protocol and the server keep the recheck](docs/decisions/0131-looks-wrong-leaves-the-interface.md)
- [0133 A full dictionary for every language pair is a pack plus riders: meanings in the learner's language, and words recorded ahead of time](docs/decisions/0133-a-full-dictionary-for-every-pair-is-a-pack-plus-riders.md)
- [0164 Mandarin is shown in Traditional by converting each caption on the PC as it arrives, one character for one](docs/decisions/0164-mandarin-in-traditional-is-converted-as-captions-arrive.md)
- [0168 Languages paired with English: one Wiktionary reader, and word splits named by what they need](docs/decisions/0168-languages-paired-with-english-one-reader-and-splits-by-what-they-need.md)
- [0171 The second batch paired with English: Persian's joiners, the affixes guessed, and a pack's own sentences in its ranks](docs/decisions/0171-the-second-batch-paired-with-english-joiners-and-affixes.md)
- [0174 A word a pack hasn't got is looked up by its parts](docs/decisions/0174-a-word-the-pack-hasnt-got-is-looked-up-by-its-parts.md)
- [0175 A pack language learned keeps its own learning data, in its own file](docs/decisions/0175-a-pack-language-learned-keeps-its-own-learning-data.md)
- [0204 Translations into Chinese are written in the script chosen for Mandarin, as a second language too](docs/decisions/0204-translations-into-chinese-follow-the-mandarin-script.md)
- [0217 The first caption window sets itself up; new windows start like the last, its spoken language only when asked](docs/decisions/0217-the-first-caption-window-sets-itself-up.md)
- [0229 A selection is read aloud a sentence at a time, behind a `Reader` port, in its spoken form](docs/decisions/0229-a-selection-read-aloud-a-sentence-at-a-time-behind-a-reader-port.md)
- [0231 A translation line is in the language the server says it is written in](docs/decisions/0231-a-translation-line-is-in-the-language-the-server-says.md)
- [0240 Korean words open on what a caption most likely means, and its compounds show their parts](docs/decisions/0240-korean-words-open-on-what-a-caption-means.md)
- [0263 Feature flags live in core.releases, read at the edges](docs/decisions/0263-feature-flags-live-in-core-releases-read-at-the-edges.md)
- [0275 A music player is heard on Detect, whatever new windows start with](docs/decisions/0275-a-music-player-is-heard-on-detect.md)
- [0287 Songs mode: a Lyrics switch has a music player on Detect sent while no speech is heard](docs/decisions/0287-songs-mode-a-lyrics-switch-for-music-players.md)
- Protocol version 1, with the app deciding live-update timing:
  polyglotic-server's decision 0003 (the server owns the protocol).
