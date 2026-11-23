# Release notes

What changed in each version of Polyglotic, in plain words for the people
who use it. One source, used four times (polyglotic-hq RELEASING.md
section 10): the GitHub Release's text above the SHA-256s (`release.yml`),
the app's What's new, the website's What's new and the Discord post.

- **A pull request people would notice** adds one line under Unreleased,
  in New, Better or Fixed (the pull request template asks; "none" is fine
  for the rest). Say what changed for the learner, not how it was done.
  Its first sentence stands alone, in 110 characters at most: Home's
  What's new shows only that, cut there (a test checks Unreleased).
  A server change people would notice (a better translator, a new
  language) gets a line too, in the next app release.
- **No promise the work doesn't back:** no speed or accuracy figures
  unless polyglotic-hq says they can be claimed, and nothing about privacy
  beyond what the privacy notice says (polyglotic-hq project 181's
  CLAIMS-V2.md).
- **At a release,** Unreleased moves under `## X.Y.Z - YYYY-MM-DD` in the
  release's prep pull request, before the tag or the alpha's build:
  `python -m tools.package.release_notes vX.Y.Z --cut --date YYYY-MM-DD`
  (Melbourne's day; `--dry-run` shows it first). The three empty groups
  stay for the next line. A tag without its section doesn't release
  (`python -m tools.package.release_notes vX.Y.Z`), and a line under a
  version can't sit under Unreleased too.

## Unreleased

<!-- open beta:
When the open-beta server is live, move this copy into the release groups
before cutting its notes. For another alpha cut, lift this block out before
running the cut and put it back here afterwards.

New

Sign in using a code sent to your email.
See your listening allowance on Home and Account. Use Upgrade to pay in
your browser or scan the checkout code on your phone. To restore a
purchase, sign in with the email you paid with.

The ring beside the caption bar's mic shows your remaining listening allowance.
It appears at every bar width on Free, Lite and Standard passes. Hover
over it to see the percentage and reset time. The tray menu and tooltip
also show your allowance, and the app tells you when 20% and 5% remain.
When it runs out, the main window opens Upgrade. Unlimited plans have no ring.

Use Have a code? in Upgrade to apply a discount to your first payment.
Before you confirm a plan or pass change, see today's charge, the next
charge and its date. If you change down, you'll see when the change starts.
If you add another pass, you'll see when it ends. Passes are for 3, 6 or
12 months.

Fixed

Email sign-in stays available if the app's first server check fails.
Code and payment messages explain the next step, including while a plan
change is being confirmed.
-->

### New

### Better

### Fixed

- Home's source choices fit at larger text sizes. Thai and French settings fit in narrower windows.

## 0.1.10 - 2026-11-24

### New

- Video captions can show readings, word links and translations alongside the spoken words.
  Both Instant and Scrolling use the same readings, word links and
  lookups as Everyday. When the server sends live translations, they
  appear with the caption as in Everyday.
- Choose how many subtitle lines Video shows.
  In the preset menu, use Lines shown to choose 1, 2 or 3. It starts at 2.
- Word links are coloured by word class: nouns, verbs, adjectives, adverbs and more.
  Rest the mouse on Word links on the caption bar to see which colour is which.
  A word whose class isn't known still links, in its own colour.

- Polyglotic is now available on Linux as an x86-64 AppImage.
  Make it executable and run it without an installer or libfuse2.
  Captions can hear everything the PC plays, one app or your microphone
  over PipeWire or PulseAudio. The AppImage was tested on Ubuntu 24.04
  and 26.04 and Fedora 45, with desktop checks on GNOME, KDE Plasma 6
  and Xfce. Polyglotic uses your desktop's keyring
  when available, follows its theme and uses its file dialogs. It says
  words aloud with recordings or speech-dispatcher, and applies
  downloaded updates when you quit if the AppImage is writable.
  X11 and KDE Plasma 6 support Ctrl+Alt+Shift+L, P, H and J. On GNOME
  Wayland you can set desktop shortcuts with the commands
  --lock, --pause and --hide, or unlock from the screen corner or Home.
  The GNOME tray needs the AppIndicator extension. Microphone dictation
  is unavailable on Linux.

- Choose Everyday, Conversation, Video or Learning from the caption bar.
  Video puts large, centred captions near the bottom of the screen.
  Switching out of Video restores the window's previous position.
  The preset menu also lets you choose which lines to show and turn on
  word links, quiet view, readings or your own speech. Changes there
  save to the active preset. Settings > Presets lets you save, rename,
  restore or create a preset, or discard a draft. Switching away from a
  draft offers Undo, and drafts survive a restart. Existing choices
  are kept in Custom.

- The timing menu on the caption bar shows the choices for your preset.
  Video offers Instant and Scrolling. Conversation offers Instant and
  Steady. Learning offers Instant, Steady and Calm, and can show the
  translation with the line or after you've read it in Steady and Calm.
  Everyday offers Instant, Steady, Calm and Whole captions.

- Instant is the default timing for Everyday captions.
  Steady shows words one by one at the speaker's pace, with upcoming
  words in faint text. In Settings > Timing, you can hide Words ahead
  or highlight the newest word. Calm shows only words the app is more
  sure it heard. Whole captions shows each caption when it is finished.
  If you used Quick preview, it now opens as Steady.

- Click the microphone on the caption bar to switch captioning of your own speech on or off.
  When it's on, a meter lights up as you speak. When it's off, the mic
  shows a slash. Conversation starts with your speech on and Video
  starts with it off. If you turn it on in Video, your speech appears
  in a separate, compact strip above the subtitles, in plain text.

- Set caption and translation sizes independently in each window's gear menu and Settings > Look.
  Changing one never moves the other; each shows its language and percentage, with a Match
  button to set translation equal to caption, script-matched 100% heights, readings that
  follow their own characters, and Learning starting with larger originals.

- Choose what you read first in Settings > Timing: Follow, Acquisition or
  Both. In Follow the translation leads; in Acquisition what was said
  comes first, its translation a moment later.

- With the card stack off, Steady keeps the lines being spoken at the foot
  of the caption window. Once you've read a caption, it moves up, with its
  translation, into a clean transcript above. Each caption starts its own
  line, a long one stays whole until it moves up, and when nobody is
  talking the transcript has the whole window. You can turn this off in
  Settings > Timing.

- What's already said in your translation language now comes with an
  English line under it. That's when your captions are in a language other
  than English. Choose another language, or none, in a caption window's
  settings ("When they already speak ...") or Settings > Speech.

- Hold F8 to type what someone said through your speakers into another app.
  Let go to type the original or the translation you selected in Settings > Dictation.

- Word lookups in Korean, with English meanings: download Korean's
  dictionary on Learning. A word is found under its particles and endings
  (학교에서 is 학교, "school"; 먹었는데 is 먹다, "to eat"), and a compound
  the dictionary hasn't got shows its parts (국립공원: 국립 "national" +
  공원 "park").

- Lookup cards show the word class beside each definition when the dictionary pack provides one.

- Chinese captions are in calligraphy, Simplified and Traditional alike.
  Simplified is in Ma Shan Zheng, a brush's regular script that comes with
  the app, and Traditional in LXGW WenKai TC, downloaded the first time
  Traditional is captioned. Pinyin and zhuyin over them stay in a plain
  face, easy to read, and so do English words and numbers said among the
  Chinese. Settings > Look > Fonts lists them under Calligraphy and
  Handwritten, with Noto Sans and the others still there to choose.

- Three recommended looks in Settings > Look: Quiet, Paper and Broadcast.
  Each sets the colours, caption text, readings and Chinese fonts
  together, in one click. Change anything after; your other choices stay.
  Quiet is the look from the first preview, with a more solid panel so
  busy windows behind it don't show through.

- Lyrics: turn it on to caption the singing in Spotify and other music players.
  Off by default. With it on, a music player heard on Detect has its music
  sent even while no speech is heard, a few seconds at a time, so sung
  lines are captioned too; turn it on in the music player's caption
  window (under They speak) or in Settings > Speech.

- Change, clear or reset your shortcuts in Settings > Hotkeys.
  Use Back to live to return caption windows and transcripts to the
  newest line. The default is Ctrl+Alt+J on Windows, Control+Command+J
  on Mac and Ctrl+Alt+Shift+J on supported Linux desktops. You can also
  set keys to copy the newest caption, switch presets or resize caption
  text. Settings tells you if a key is already taken or reserved.

- Choose your interface language as the first set-up step and restart into it immediately.
  All 22 interface languages are listed by their own name, preselected from your OS language;
  keeping the language already showing continues without a restart, while picking another
  saves it, defaults translations to it until you choose otherwise, and relaunches directly
  into step 2. Changing the app language later in Settings now offers Restart now beside Later.

- Settings > App has a Start at sign-in switch to turn automatic launch on
  or off. Start Polyglotic with Windows (or at login on a Mac or Linux)
  whenever you like.

- Home has a Server status link when Polyglotic's server can't be reached
  and the problem may be ours. It opens polyglotic.io/status, which says
  whether the server is up. Help has it too, beside Check again.

### Better

- Video's Instant mode fills subtitle lines word by word, and Scrolling moves words sideways.
  Both modes can show the original, the translation or both. If you
  used the older scrolling-style Instant, it now opens as Scrolling.
  Saved Subtitle blocks and Delayed translation settings open as Instant.
- Finished Video subtitles stay in place for at least half a second before moving on.
  This gives the last words of a caption time on screen.

- Captions have a more solid background by default, so busy scenes show through less.
  Upcoming words are clearer, and your own background setting is kept.

- Steady and Calm keep words in place on cards as they appear.
  Older cards glide up and ready translations have room on their cards.
  Everyday and Learning reserve room as captions appear. To turn the
  cards off, use Card stack in Settings > Timing.

- In Everyday, translations glide with their cards as older captions roll up.

- A second caption window joins the first as it opens: one window, a
  column each. A new window's question about its languages shows in its
  column. Choose Separate windows and new ones open on their own from then
  on.

- Use Ctrl+scroll in a caption window to resize both rows together. On a Mac, use Cmd+scroll or Ctrl+scroll.

- Narrow caption bars group the language, preset and timing icons together. Preset and window names keep their ampersands in menus and buttons.
  Set the Open caption bar controls shortcut in Settings > Hotkeys to use them by keyboard.

- The caption window's gear menu is shorter.
  It gives you the app, languages when the language chip is folded,
  caption and translation sizes, Open transcript, Join windows,
  Stop captioning and All caption settings.

- When Mandarin speech continues after a pause, the caption can show the whole sentence with one translation.

- Captions keep going while you dictate or hold F8.
  Dictation appears in the window when your own speech is captioned.
  F8 uses the caption window's words or translation when it already hears that audio.

- When captions are off, Home offers one click to caption a playing app or everything you hear.

- Word links use colours that stand out from the caption text.
  The linked word and its translation still share a colour.

- The card that saves a phrase you drag across now has "Look it up". A
  set phrase of four characters or more, like 一石二鸟, opens its
  dictionary card from there.

- Pinyin and other readings are a quiet grey, so the words lead. Grey is
  the quiet view's, and the default everywhere else, where a linked
  word's reading still takes its link's colour. Settings > Look >
  Readings has Grey beside Same as its line, Its word link's colour and
  Custom.

- In Steady, the language spoken is named when it changes, not over
  every caption.

- Detect stays: a caption window no longer asks whether to always hear
  its app in the language Detect has heard. You can still choose one in
  the window's settings.

- Chinese, Japanese and Korean captions are no longer slanted in the
  quiet view or while a line is being spoken.

- Word links reach every word again in the languages you learn, not only
  the words past what you know. If you chose to start them from a number
  of words, or turned them off, that stays; Learning has the choice.

- The app's text is larger by default (Settings > App > Text size).
  Normal is now between the old Larger and Largest, and every step moved
  up with it: Smaller is the old Normal, Larger the old Largest, and a new
  Largest is bigger still. If you never changed it, you get the new
  Normal; if you did, your text stays about the size it was. Captions keep
  their own size.

- Home offers the Mac's audio privacy settings when Polyglotic cannot hear other apps.

- The Mac menu-bar menu shows the shortcuts for pausing, locking and hiding captions.

- Joined caption windows resize more smoothly.

- Fill the width has been removed from the caption bar and Lab.
  If you used it, captions return to one phrase per row with arrows.

- "Report a problem" now says how long each caption took to reach the
  screen, over the last 5 minutes. It's in the app's log, which you can
  look at before sending, so a caption that stalled comes with where it
  stalled. Times only, never what was said.

### Fixed

- Back to live in Video shows one copy of each caption and keeps wrapped translations readable.
  Long subtitles wrap to fit the window.

- Switching to Video starts with new captions.

- Video's large subtitles are sharp. Their outline no longer blurs the
  letters, and the faint words still to come are a clear grey, not a smudge.

- Edits to captions already on screen keep the live edge and your scroll-back position anchored.

- New captions keep coming while you hover over the caption window.
  The words under your mouse stay still briefly for lookups, and Back
  to live counts newer captions. Single and joined windows catch up
  when you move the mouse away. In Instant, you have time to read the
  next caption before it catches up, or you can choose Back to live.

- Resizing a caption window keeps your place. The lines you were reading
  stay where they are, and the window no longer jumps back to live or to
  the start.

- In Steady, words said with pauses between them now share a line until it's full.
  Before, each short phrase got a line of its own down the window's left
  edge. A pause of more than about 5 seconds, another speaker or another
  language still starts a new line.

- A line whose final version never came back from the server no longer
  stays half-finished for good. Whether it failed there or was lost on the
  way, it settles as it was shown, and is in the transcript and Copy all.

- Polyglotic can caption speech over steady background music from your speakers.
  In our tests, speech 5 dB over music no longer went unheard for more
  than 2 seconds.

- Lyrics can pick up sung lines later in a song.
  Songs are still captioned in part. Help's Questions explains that
  songs work best with Spoken language on Detect.

- Music no longer turns into captions like "The.", "Music." or "Piano."
  when you've chosen the language spoken. A caption of only such a word is
  dropped.

- Spotify, Apple Music and other music players are heard on Detect,
  whatever language your other windows have. Told a language, music turned
  into stray words. To hear a music player in a language, choose it in
  that player's own caption window.

- Changing caption sources keeps the current listening session when another source is already selected.

- Turning the quiet view off brings your word links back as they were,
  instead of leaving them off.

- Captions resume after an unexpected error in the server connection.
  The app reconnects automatically, as it does when the network drops.
  A saved lookup or statistic it can't read is skipped so listening can
  start.

- Captions resume when hearing an app, the PC or your microphone fails unexpectedly.
  The app tries again on its own. Help's No captions? check now tells
  you when hearing has stopped.

- The speaker-typing sign stays steady while you hold F8.
  Key repeat keeps a single hold and sends one caption request after release.

- Caption notices stay in place when the bar appears if there is room.
- You can copy the word class legend in Settings.

- Caption and translation size labels work across languages.

- On a Mac, the menu-bar icon brings Home forward and its menu actions work while another app is active.

- On a Mac, Home can shrink further, and Home and caption windows have wider resize handles.
  Joined captions also stay on screen when resized.

- Pressing Return now selects the highlighted language in the Mac caption controls.

- On a Mac, opening the Speakers or Microphone list no longer freezes the
  app for a couple of seconds. The lists (Home's Sound, or Settings >
  Speech) are made in the background.

- Home can be resized from any edge and opens at the size you left it.

- A new caption window's set-up no longer covers its bottom edge. In a
  window too short for it, it shows just above the window instead.

- Joined caption windows stay centred when another app's window joins,
  and can be widened from either side. They sat at the screen's left and
  couldn't grow.

- Joined caption windows always leave room for their buttons. After a
  preset with a longer name, they could be dragged narrower.

- A transcript window can always be made smaller, even at the largest
  text on a small screen. It opens at the size you left it.

- In a narrow caption window, the hint on its bar no longer covers the
  preset button. It moves under the bar when there's no room beside it.

- A long word or phrase on a dictionary card no longer runs under its
  speaker and close buttons. It gets a little smaller, then wraps.

- Settings > Look > Thickness no longer offers Light and Regular when the
  captions' fonts haven't got them. They looked just like Medium. Choose
  one of this PC's fonts with a Light weight and they come back.

- If you learn two languages, the quiet view marks your words only in the
  line you're learning. It marked them in its translation as well. Look
  has "Mark my words in" to choose.

- Home no longer shows a "Pause captions" button while nothing is captioned.

- Planned maintenance times now name your PC's time zone, as in "until
  7:30 AM (AEDT)". Where your language has no short name for the zone,
  they give its offset, like "(UTC+9)". During it the caption windows say
  until when too, not only that it's planned.

- The card that saves a sentence now says "Add an English voice", not "Add
  a English voice". That's with no English voice on the PC.

- Language names follow the grammar of the app's interface language.
  For example, Spanish now says "Decirla en ingl?s".

- Help explains when Polyglotic listens to your microphone.
  It listens while a window captions your speech or while you hold
  the key to dictate or re-speak.

- The caption windows no longer cover the app's own dialogs. While Save
  transcript, the Anki export, the colour picker or a question is open,
  they step out of the way and come back where they were when it closes.
  Captions keep coming meanwhile.

- The app now looks for updates only for its own system. It ignores an
  update channel meant for another one, such as Windows' updates on a Mac.

## 0.1.9 - 2026-11-18

### New

- The app tells you when a better voice can be installed: on a Mac,
  each time a word or sentence is said in macOS's basic voice for its
  language, it says where to add a more natural one for free, with
  "Don't show again" for that language.
- Learning load (Settings > Lab) now colours every word of a
  caption by how well you know it: red for words you've never met or
  that are far past what you know, the colours between for words
  you've heard or partly know, and green for words you've mastered.
  Hearing a word on more days, saving it, or keeping it after a lookup
  moves it along; a fresh lookup moves it back. Choose red to green, or
  orange to blue if red and green look alike to you.
- Learning shows the whole language at a glance: its 20,000 most common
  words, one square each, in the colour of how well you know it. See how
  many are red and green, how much of what you hear is green, and how
  that moved in the last week. Point at a square to see its word and why.
- The quiet view: one button on a caption window shows every caption in
  quiet grey and gold, a little bigger, with pinyin over every word and
  only the words you're learning in blue - no underlines or arrows. Point
  at a word to see its partner. Choose which words are blue in the
  window's settings or in Settings > Word links: our curriculum (a few words just past
  what you know, the ones you hear most first), your learning load, your
  saved words.
- Caption text: three sliders in Settings, under Look, beside the colour
  presets. Contrast takes captions from soft - as faint as Quick
  preview's line, never too faint to read - to crisp, every line at full
  strength. Vibrance takes their colours from muted to vivid; white and
  grey stay as they are, and word links keep their colours so you can
  tell them apart. Thickness takes their letters from Light to Bold, with
  pinyin a step thicker. Visibility draws a soft shadow or an outline
  around the letters, for busy videos. Transcripts follow the contrast
  and colours. In the middle, and with no outline, as before.
- More faces for captions, downloaded when you choose one: Kai, Song and FangSong for Chinese, Mincho and textbook handwriting for Japanese, Hong Kong's own forms for Cantonese, and serif faces for every language. Traditional Chinese, Cantonese, Japanese and Korean get their new default faces the same way, once you caption them.
- Settings > Look has a Fonts card: a row for each language your captions are in ("Chinese (Simplified) captions in: Noto Sans SC"), each with its own list of faces, this PC's own fonts and any font on it.
- Say it: the card that saves a selection reads it aloud too, in the
  language it was spoken in or its translation, in your PC's own voice -
  each word lights as it's said. It reads the words as they'd be said,
  not as the captions cut them, and years as years. Click again or press
  Esc to stop. In a transcript, right-click a selection and choose Say it.
- Save sentences: drag across more than a word in a caption window - across lines, captions and speakers - and the card at the mouse saves it into a category, with its translation and word links; in a transcript, right-click a selection and choose Save sentence to. Saved sentences stay on your PC.
- An English word's card explains it in English: short everyday
  definitions, the commonest meaning first, each with its part of speech
  and the first with an example. The meanings are in Chinese only when
  the app's language is Chinese.
- An English word's card can explain it in your own language: where the
  app's language has the word in Wiktionary's translations, its meanings
  are shown in that language (Spanish, Japanese, Vietnamese and more),
  and in English where it hasn't.
- Lab: Parts placed. With Fill the width or Line up the parts on, a line's
  parts can sit nearest the words they are linked to, so the word links
  and Arrows are short, or be spread evenly over the width. Packed, as
  before, unless you choose.
- Cantonese is a language of its own to learn. Its dictionary reads a
  Cantonese line's words in Jyutping with Cantonese meanings (係 is
  "hai⁶: to be", not Mandarin's "xì"), finds words like 佢哋 and 而家
  whole, and keeps your words as every other language does. The Chinese
  dictionary still answers a word it hasn't got, and the card says so.
- Jyutping above Cantonese, as pinyin goes above Chinese: on from the
  start once you learn Cantonese (turn it off in Settings > Readings). It
  takes the same size, words and colour choices as pinyin, which are now
  under Readings.
- A caption window sets itself up when it opens: it asks what they
  speak, what to translate into, and what to do when they already speak
  that language - each already filled in. Choose Use as my default and
  new windows start the same way, without asking again (the languages on
  any window's bar bring it back). Captions start as soon as there's
  sound, whether you've answered or not. Every caption window's bar now shows its languages ("Detect →
  English"); click them to change them.
- Everything on from the start, for someone new: your first caption
  window captions what you say too, as "You" (its set-up shows the switch,
  to turn it off); word links show with their lines; dictation is on -
  hold Right Ctrl, speak, let go; a hidden caption window comes back when
  its app starts speaking; and readings like pinyin are on, over every
  word. On a Mac, macOS asks for the
  microphone then; if it's refused, the switch goes off and says where to
  allow it. If you've used Polyglotic before, your settings stay as they
  are.
- The quiet view follows the conversation: every couple of minutes our
  curriculum lights the words the talk is about - just past what you
  know, and its own key words a step further (业主 in a residents'
  meeting, "rubber" in a design meeting) - a few to a screen, never
  sounds like 嗯 or "um". Words that stop being said give their place
  back. Point at the window to see what it's about now.
- In the quiet view a word the talk is about stays blue until you know
  it, not just for three days: a series' own words keep lighting episode
  after episode.
- The quiet view's "Words at your edge", on from the start: any word in
  your learning window lights blue as it's said - a couple a caption at
  most, never names, numbers or everyday talk - so a Mandarin talk shows
  a few blue words on most screens, not one in six. The learning window
  you chose on Learning counts.
- Names in Chinese captions stay names: 杜瓦尔, or the 万里 of 黄万里, are
  neither blue in the quiet view nor coloured as words to learn.
- Furigana above Japanese: small kana over each word's kanji, in what
  was said and in translations into Japanese - on from the start once you
  learn Japanese, with pinyin's size, words and colour choices.
- Respelling above English: how each English word sounds, in plain
  letters with the stressed part in capitals (KAY-oss, ri-SEET, TYME), for
  the commonest words - on from the start once you learn English, at first
  only over the words past what you know.
- Stress marks over Russian: an accent over the stressed vowel of each
  Russian word (молоко́), from the Russian dictionary - on from the start
  once you learn Russian. A word the dictionary stresses two ways (ру́ки,
  руки́) gets none, and its card shows both.
- Romanization above Korean (한국어: hangugeo, in the official Revised
  Romanization, as it's said) and Latin letters above Hindi (किताब: kitāb),
  on from the start. Each reading has its own switch in Settings >
  Readings.
### Better
- Quick preview is the caption timing from the start: a dim first line
  about 2 seconds into a sentence, then the finished caption and its
  translation when it ends - between Steady (each sentence once, finished)
  and Live updates. A timing you chose yourself stays.
- A word plays in the same voice every time you press its
  speaker - its recording, or the best voice for its language - at its
  natural pace. The second press no longer says it slower in another,
  robotic voice.
- Pinyin and other readings are on from the start: pinyin over Chinese
  and Jyutping over Cantonese, over every word - unless the app or your
  translations are in that language. Turn any of them off in Settings >
  Readings; your choice is kept.
- Thai captions' word links are cut at Thai words, as the word card
  splits them, instead of underlining a whole phrase; particles such as
  ครับ, ค่ะ and นะ aren't linked.
- Live updates: words the server has heard the same way twice are drawn
  as final, in full colour, while the rest of the line is still dim; if
  a later hearing changes them, the new words glow warm for a moment.
- Live updates come every second by default, not every 1.5 seconds, so
  more of what was said can be shown as final sooner. An interval you
  chose yourself stays.

- A quicker first start: once you've signed in, everything your PC plays
  is captioned straight away, in one window called "Everything the PC
  plays" that sets itself up. Home says so (a call's voices too), and one
  click on an app there captions just that app instead.
- Settings is easier to find your way around. Each section's tab and
  each card's title has a small picture beside its name, the titles are
  bigger, and the title and tabs stay at the top as you scroll, with the
  name of the card you're in under them. Word links and Readings are
  sections of their own now, out of Look, and the app's language is set
  in one place, under the title. In a narrow window the tabs become a
  list.
- Captions in a face chosen for each language: Chinese in Noto Sans SC, Thai in Noto Sans Thai Looped, Vietnamese in Be Vietnam Pro, Arabic in Noto Naskh Arabic (always upright, a little larger), Hindi in Noto Sans Devanagari, Russian in PT Sans and the Latin languages in IBM Plex Sans, with real italics; pinyin in a true semi-bold.

### Fixed

- On a Mac, a caption window's settings and its language chip's choices
  stay in front of the window: they went behind it within a second of
  opening.
- English cards open on the right word more often: "does" on do (not a
  deer), "am" on be, and lower-case "north", "i", "i'm" and "mr" are
  found. A few dozen rarer forms (ruined, panicked, scrolling) open on
  their own verb.
- On a Mac, a caption window shows its buttons, marks the word under the
  mouse and opens a word's card when you rest on it while you're in
  another app, as it does on Windows: before, nothing came until you
  clicked Polyglotic itself.
- An English word's Chinese meanings start with the everyday one: can is
  能, 可以 (not 装罐, "to can"), will 将, may 可能, well 很好地, good 好的
  and give 给. "tv", "ok", "uk" and a few dozen other abbreviations are
  found in lower case, "number" no longer opens numb, and "gonna",
  "cannot", "wanna" and "gotta" open go, can, want and get.
- People's names in English captions are names: "John" opens 约翰 (not
  john, a toilet), "Bill" inside a sentence is the name, and Mary, David,
  Michael and about 1,300 more are no longer counted as words you've heard
  or marked as new. "a bit" opens bit (一点, not bite), "later" opens
  later (以后), and "training", "meeting", "interesting" and a dozen more
  open their own meaning first and count as their own word.
- On a Mac, Report a problem (for alpha testers) opens, from a
  caption window's strip and from Help: it stopped before its window
  came up.
- Changing a setting on Learning - a learning window, word links, where
  links start, Mark known - no longer jumps the page down to its middle:
  it stays where you were, with the keyboard on the same control. The same
  for removing a dictionary there, and for renaming or recolouring a
  category on Words.
- When someone mixes Mandarin and English, the Chinese translation of an
  English sentence has its pinyin, is written in Traditional if that's
  your choice, and is saved as Chinese in the transcript. It was taken
  for English. (Needs the server update that comes with this version.)

## 0.1.8 - 2026-11-18

### Fixed

- The Mac app couldn't sign in: every try said "Something on this network
  is in the way" whatever the network, and never reached our server. It
  now trusts the certificates macOS itself trusts, so signing in, live
  captions, updates and dictionary downloads connect.
- On a Mac, a caption window resized by its edge or corner keeps its new
  size, and never shrinks past its smallest: macOS resized it itself, so
  the size wasn't remembered and the window could become a sliver.

## 0.1.7 - 2026-11-17

### New

- Every language with a dictionary now keeps your words, as Chinese and
  English do. Learn Russian, Spanish, Japanese or any other language
  whose dictionary is downloaded, and a word's card has Save to, Add to
  deck and Known; Words has a section for the language, with its own
  categories and what you've heard; and captions count and mark its
  words against your level, a number of words. Each language's words are
  kept in their own file on this PC.
- The whole learning view in one click, from a caption window's Word
  links button. It turns on word links with the lines that join them,
  each linked word in its link's colour in what was said and in the
  translation, and pinyin over a Chinese window's words in the same
  colour - so a word, its pinyin and its translation match. Click it
  again to go back to how they were.
- Mandarin's captions can be shown in Traditional characters, and
  translations into Chinese with them. Choose it in Settings > Speech >
  Show Mandarin in (or a transcript's Languages), with Detect too; on a
  Taiwan or Hong Kong Windows it starts at Traditional. Lookups, the
  transcript, Copy, Save, Anki and the caption preview in Settings
  follow, and so does a translation into Chinese as a second language.
  A saved or copied transcript names its lines
  Chinese (Traditional), and the language pickers call the language
  Chinese.
- Polyglotic on a Mac, as an early preview: download it from the alpha
  page, for a Mac with Apple silicon and macOS 14.2 or later. Captions
  stay over full-screen videos and apps, and on every desktop (Space).
  It lives in the menu bar, not the Dock, and can start at login.
  ⌃⌘L, ⌃⌘P and ⌃⌘H lock, pause and hide the caption windows whatever
  app is in front, and you hold Right ⌘ to dictate into the app you're
  using (macOS asks once for the Accessibility permission it needs). A
  word's card speaks in the Mac's own voices, and Settings, Help, Home
  and the caption windows name a Mac's keys (⌘, ⌥, ⌃) and its menu bar.
  Opened from Downloads, it offers to move itself to Applications, and
  from there it updates itself.
- Spanish, Italian and Portuguese words are recorded: the speaker on a
  word's card says the language's 10,000 commonest words even on a PC
  with no Windows voice for it. The recordings come after the language's
  dictionary: Learning says both sizes before the download, and says when
  they're there.
- Chinese words are recorded too: the 10,000 commonest words in
  CC-CEDICT, said by an open voice model. They download quietly for
  anyone learning Chinese (30 MB, never on a metered connection), and
  Chinese's card on Learning says when they're there. They play for a
  word written in Traditional characters too.
- An Anki deck for every language with a dictionary: Words' Export
  writes a language's words to its own deck (Polyglotic::Russian) with
  its own note type, the word marked in its sentence, and Anki reads it
  aloud in that language's voice.
- Learning shows your level for every language whose dictionary is
  downloaded - Change your level, Mark the most common words known - as
  it does for Chinese and English.
- Zhuyin (bopomofo, ㄅㄆㄇㄈ) above Chinese, for readers who learnt it in
  Taiwan: Settings - Look - Pinyin - Readings above Chinese: Pinyin or
  Zhuyin. The same readings, with zhuyin's tone marks, over what was said
  and over translations into Chinese.
- Pinyin's colour (Settings - Look - Pinyin): the same as its line, its
  word link's colour, or one you pick. And linked words in their link's
  colour, each side on its own - "Colour linked words in what was said"
  and "Colour linked words in the translation", in Settings - Look - Word
  links and in a caption window's settings: with both, and pinyin in its
  word link's colour, a word, its pinyin and its translation all match.
  Link colours are lightened or darkened only as far as they need to
  stay readable on the panel, including over a bright scene behind a
  see-through one.
- French has a dictionary: download it on Learning and French words in
  captions can be looked up - l'homme and d'accord are read as their
  words.
- Word lookups in German, Portuguese, Italian, Indonesian, Arabic, Hindi
  and Polish, with English meanings: download the language's dictionary
  on Learning. Arabic words are found with "and" or "the" written onto
  them, and Italian's dell'anno is read as its two words.
- Word lookups in Turkish, with English meanings: a word is found under
  its suffixes (verilen is vermek, evlerimizde is ev), and names under
  theirs (Afrika'daki is Afrika).
- Word lookups in Dutch, Ukrainian, Persian, Swedish, Czech, Romanian,
  Greek, Filipino and Macedonian, with English meanings: download the
  language's dictionary on Learning. Persian's داستان‌ها and می‌کنم are
  found as their words, and Filipino's isang as isa.
- Pinyin above Chinese (Settings - Look - Pinyin): a small syllable
  over each Chinese character, in what was said and in translations into
  Chinese, on caption windows and transcripts, Small or Medium. It isn't
  part of the text: copying, looking up words and Anki cards work as
  before. Off unless you turn it on. Pinyin over Past what you know puts
  it only over the words past your known line, the ones word links point
  out, so there's less to read as you learn.
- Fill the width in one click: a new button on a caption window's strip
  (beside Word links) turns on New layout, Line by line and Captions run
  on together, in every window, so captions use the window's whole width.
  Click it again to go back to how they were. The Lab's rows show and
  change the same settings.
- Line up the parts in one click: a button beside it on a caption window's
  strip puts each part of what was said at the same place as its
  translation, so a word's translation sits under it - now in every way
  captions fill the width (a clause a row, Translation below and Line by
  line), not only Line by line. It turns on New layout with it.
- Sound on Home: choose which speakers Everything the PC plays is heard
  from and which microphone is captioned (this PC's default, or one
  plugged in), turn Caption what I say on or off, and see your
  microphone's level while it's on. Settings > Speech has the same card.
  Dictation uses the microphone chosen too.
- A locked caption window can be unlocked from the window itself: rest
  the mouse on the lock in its corner for a moment, then click Unlock.
- The privacy notice is now version 3.2 (polyglotic.io/privacy). What
  changed: how many times you've looked up each dictionary word, and
  when you last did, is kept on your PC with the rest of your learning
  data, and deleted with it.

### Better

- On a Mac, the app uses a Mac's words: Settings > Dictation names the
  keys as ⌘, ⌥ and ⌃ (Right ⌘, ⌃⌘E), and Help, Home and the caption
  windows say the menu bar, not the tray, and ⌘ to zoom and copy.
- Word links' colours are easier to tell apart: the brown that looked
  like the orange is now an olive, the lime a green, and the magenta a
  little pinker, so no two links' colours are close, on any colour
  preset, as lines or as coloured words.
- A word card in the downloaded dictionaries shows the word's everyday
  meaning first: Spanish's "de" is "of", not the letter's name; Arabic's
  بعد is "after"; old and rare meanings come last. A word you marked by
  hand may show as new again where its first meaning changed.
- A German compound or a hyphenated word the dictionary hasn't got
  (Internetmaterialien, Blog-Erfahrung) is looked up by its parts: the
  card says it isn't in the dictionary as a whole and shows each part's
  meaning, and a word link over it counts its parts as words you know or
  don't.
- A caption window's strip buttons say what they do: rest the mouse on
  one (word links, fill the width, line up the parts, lock, settings,
  close, the mic mark) and a label above the window says it, in the
  interface's language.
- Selecting in a caption window follows the mouse character by character,
  in every language: drag over 刚 then 刚刚 then 刚刚呢, and copy gives
  exactly what's highlighted. A double-click selects a whole word.
- Polyglotic keeps, on your PC, how often you've looked up each word and
  when you last did, with the rest of your learning data, and deletes it
  with your learning data.
- Japanese captions' word links are cut at Japanese words, as the word
  card splits them.
- Explanations in Settings, Learning, Account, Help and Home keep to a
  readable line length instead of running the full width of the window,
  and Settings' rows line up from one section to the next.
- Boxes that open a list of choices (the app's language, speakers, a
  wait in Timing) have a small arrow like the other choosers, in place
  of a dark arrow box that poked past the box's rounded corner.
- Home's notes under the apps ("My speech: ...", "0 of 3") and Words'
  summary line are quiet again, as notes are everywhere else; "3 of 3 -
  stop one to add another" is in the warning colour.
- Home's "show my speech in this window" button is a drawn microphone,
  the same one a caption window shows, in place of an emoji.
- Help's check list lines up: its ticks, crosses and dashes sit in a
  column of their own, so every line's words start at the same place.
- A caption window's notice line ("Click any word to look it up",
  "Reconnecting", "Paused") no longer drops over the top caption when
  the mouse is on the window: it stays where it is, in the strip's gap,
  and captions start below it.
- Word links in English captions leave out English's small words (the,
  of, to ...) the way other languages' links leave out theirs.
- Cantonese captions are written in the characters Hong Kong uses, and
  keep the Traditional characters the speech model wrote.

### Fixed

- A coloured word in captions (the learning load's, a saved word's, a
  word link's) right after another coloured word keeps its colour; it was
  sometimes drawn plain, most often with captions filling the window's
  width.
- Check boxes and round choices - on Your data, the level you know,
  and in the app's other windows - are plain to see in every theme,
  light or dark: drawn for Windows' own mode, they could all but vanish
  when it differed from the app's. The code box has an edge you can see
  too.
- Learning no longer says "No dictionary yet" for a language whose
  dictionary came out since you last opened the app: it checks the list
  of dictionaries as you open it, and says it's checking meanwhile.
- Pinyin and Zhuyin show over a translation into Chinese as a second
  language too: English heard in a window set to English, with Chinese
  as its second language, had its Chinese lines read as English - no
  reading over them, in any layout.
- Clicking a word once - to select it, or hear it on its card - no longer
  marks it as a word you don't know: common words such as "the" and
  "that" were being dotted as new and linked after one click. Clicking a
  less common word twice still does, and words one click had marked go
  back to what your level says.
- Double-clicking a word in a transcript selects it and looks it up
  once, as in a caption window: it counted as two clicks, enough to mark
  a common word as one you don't know.
- Deleting your learning data with "Also delete it from this PC" also
  empties the words of a language you've stopped learning, or whose
  dictionary you removed. Before, only the languages open at the time
  were emptied on this PC.
- Pinyin shows with Translation below and Line by line too (the Lab's
  ways of filling the width without the New layout): it was missing there,
  over what was said in Chinese and over translations into Chinese. And
  with Chinese not learned (so no Chinese dictionary to read it from), a
  translation into Chinese no longer has an empty gap above it.
- What your speakers play, even turned right down, and what your
  headphones let out are now rarely captioned as your own speech. Your
  own speech is still captioned while something plays.
- Before you choose a language to learn, a caption's words can be looked
  up whatever language Polyglotic's own text is in: a German interface's
  first Chinese caption had no word to click, yet said "Click any word to
  look it up". The hint now shows only where a word can be looked up.
- Polyglotic no longer lists itself, or another copy of itself, under Add
  an app when its sample or a word's sound plays.
- Lab: Between clauses can be chosen while Captions fill the width is Off,
  and choosing one sets it to Translation below; before, it was greyed out.
- "Polyglotic's server is restarting" shows only when the server said it
  was restarting; otherwise it says it can't reach the server, and tries
  again as before.
- Home says Paused, not Listening, while every caption window has paused
  after being hidden, and says how to carry on.
- Anki: a deck file and a CSV each remember their own exports, so "Only
  words not exported yet" in one no longer leaves out the words you sent
  to the other.
- Links inside a line of text (Settings > Look's "Learning", the Lab's
  "Open it on Learning") are readable: they were dark blue on the dark
  theme.
- What's new's All the changes opens Help at What's new's heading, with the
  newest version's notes from their start - not in the middle of them.
- An update's card on Home has its frame again, like the cards beside it.
- A custom learning window typed in full-width digits (１２００, from a Chinese
  or Japanese keyboard) is taken as the number, not ignored.
- A Chinese word with several readings shows the everyday one first on
  its card: 结果 jié guǒ ("result") before jiē guǒ ("to bear fruit"),
  教授 jiào shòu ("professor"), 东西 dōng xi ("thing"), 更 gèng ("more").
  About 200 words change, and a caption's word counts for that reading.
- Lab: Captions run on and Parts lined up can always be switched on, and
  switching one on turns on what it needs with it (New layout, and Line
  by line for Captions run on); before, they stayed greyed out until
  both were set. Dimmed, for words outside the learning load, likewise
  turns the load on.
- In the Lab's new layout with Captions run on, a caption no longer draws
  over the last line of the one before when that one's translation ran
  past what was said: it starts on the line below.
- In the Lab's new layout with word links off, a line scrolled off the top
  no longer leaves its new words' dots behind, alone over the first line.
- A caption window's very corners resize it. Before, the outer tip of
  each corner let the click through to the app underneath, so a corner
  sometimes wouldn't take hold.
- When Ctrl+Alt+L doesn't work on your PC, a locked caption window no
  longer tells you to press it: it says to unlock on Home or from the
  tray, and so does the lock button's tip before you lock.
- Home and Help name Ctrl+Alt+L, Ctrl+Alt+H and Ctrl+Alt+P only when they
  work on your PC - when another app has one, they say where else to find
  Lock all, Hide all and Resume.
- A saved or copied transcript puts a second-language line under its own
  language: with Chinese as English's second language, an English
  caption's Chinese line was saved in the English column, and the Chinese
  one was empty.
- A word's card plays its recording as soon as the language's recorded
  words have downloaded: the first card opened just after could say there
  was no voice for the language, or use Windows' own voice instead.
- A translation that comes back in the wrong writing system (Chinese
  characters in an English line) is asked for again instead of shown;
  if it's wrong again, the part is shown untranslated.
- Word links leave out small words written with a curly apostrophe
  (I’m, you’re, didn’t) as they do the same words written with a
  straight one; and they no longer pass over a name that is also a
  small word, such as "May" the month in "On May 15th".
- A translation never shows the translator's own label ("[Pending
  translation text]") as if it were the translation: the label is taken
  off, and a part that is only the label is shown untranslated.

## 0.1.6 - 2026-11-15

### New

- Select captions to copy: drag from a word across lines, captions or
  into the translation, then right-click the highlight to copy it (or
  Ctrl+C while Polyglotic's main window has the keyboard). A drag within
  one phrase still looks the phrase up, and can be copied the same way;
  Esc or a click elsewhere lets go. It never takes the keyboard from a
  game.
- The learning window on Learning has two more choices: Unlimited, where
  any word past what you know can be pointed out, and Custom, where you
  type how many words it holds (10 to 100,000).
- Mark the most common words known at once: on Learning, a language's
  card marks the first 1,000 to 10,000 words known (or a number you
  type), with Undo right after and Reset later. Words you marked
  yourself stay as you set them.
- Pick several words at once in Words' lists and the learning load's:
  Shift-click a second word to pick every word between, Ctrl-click to
  add one, or Shift and the arrow keys; then "I know these", Add to
  deck, or the list's other actions, for all of them.
- Lab: New layout, to try (Settings - Lab). With Captions fill the width
  set to Line by line, turn on Captions run on and a caption carries on
  in the line the one before ended in, so a wide window's lines fill up.
  Parts lined up puts each word's translation under it. Arrows work
  however captions fill the width. Off unless you turn it on.

### Better

- Word links in Russian, Spanish, French, Vietnamese and 23 more languages
  know their own small words: articles are no longer linked, and words
  like pronouns no longer count as key links.
- Korean, Hindi and Persian words are underlined whole, not a syllable or
  a letter at a time.
- A transcript says "Copied" when you copy: by the mouse for a line's
  Copy, and on the button for Copy all.
- A caption window's settings no longer offer Copy the newest caption.
  Copy all captions is still there, and right-click a caption to copy
  that one.
- The learning load's switch (Settings > Lab) and its card on Learning
  lead to each other: "Open it on Learning" under the switch, and the
  card says where it's turned on.
- Copy any text in the main window: drag across it with the mouse, then
  press Ctrl+C or right-click for Copy and Select all - on Home, Learning,
  Words, Settings, Help and Account. Copy with nothing selected copies all
  of the text you right-clicked.
- Copy from the word card: once it's pinned, drag across the word, its
  readings and meanings, its parts or the sentence it came from, then
  right-click to copy it - the card never takes the keyboard from your
  game. Ctrl+C copies it too while Polyglotic's window has the keyboard.
- Copy from a transcript: drag across its lines (Shift-click to extend),
  then press Ctrl+C or right-click for Copy and Select all. What was said
  and its translation are copied as they show, in order. A click on a word
  still looks it up.
- "Looks wrong?" is gone: a caption or transcript line no longer offers
  it, nor does a transcript line's right-click menu, and Ctrl+Alt+W no
  longer checks the newest line.
- What's new after an update: the first time Polyglotic starts after it
  updates, Home says what changed in the new version in a few lines,
  until you close it, and Help keeps every version's notes. A new
  install doesn't show it.
- On a metered connection, an update isn't downloaded by itself: Home
  says how big it is and offers Download anyway, as the dictionaries do.
  On any other connection updates download as before.

### Fixed

- When you switch between English and Chinese with only a short pause, a
  caption no longer loses the sentence in the first language: both parts
  stay, each translated.
- Numbers written as words, like 二十 (twenty) and 十五 (fifteen), are no
  longer pointed out as new words or linked "Past what you know": they
  count as known, as 20 and 15 do.
- Chinese captions are cut into the words you'd read: 生活中的 is 中 + 的,
  not 中的 "to hit the target", and 有了 is no longer "to be pregnant".
  Names, idioms and HSK words such as 有的 stay whole.
- On a small screen (1280 x 720, or 1366 x 768 at 150 %), Polyglotic's
  pages no longer scroll sideways or cut words off, in any language or text
  size up to Windows' 150 % with Larger: rows of buttons, switches and
  Settings' sections go onto a second line instead, and Words' tables
  narrow their columns.
- Word links "Past what you know" no longer link words you know: very
  common words your level's syllabus leaves out (与, 而, 一个), common
  names (美国, America) and numbers. With no level set, a Chinese
  caption had 62 % of its words linked; it now has 44 %, as at 1,000
  words.
- Learning Chinese and English, a word link now follows the language
  you hear: a word you know is no longer linked because its translation
  is one you don't, and "Every word" for one language no longer links
  every word of the other's captions.
- "Past what you know" in Russian or Vietnamese linked every word. With
  the language's dictionary downloaded, words past the 1,000 commonest
  are linked, and Learning lets you choose where links start.
- English words such as "thousands", "chilies" and "don't" are found in the
  dictionary by their base word: their card shows it, and "Past what you
  know" no longer links them as rare.
- Word links no longer vanish from a whole line of a caption when its
  finished text differs by a word from what was already shown. The words
  that stayed the same keep their links.
- Two parts of a caption that share a line no longer use the same
  colour for different word links. A caption's links are now numbered
  across the whole caption.
- Learning's word-introduction sample shows its Chinese in the same
  typeface as your captions.
- A name spelt by sound no longer shows other words inside it on its
  card: 德克萨斯 (Texas) no longer lists 萨斯 as "SARS", nor 纳米比亚
  (Namibia) 纳米 as "nanometre". Names like 北京大学 still show 北京 and
  大学.
- A caption window's question "This sounds like Mandarin. Always hear it
  as Mandarin?" no longer covers the top caption: the captions make room
  below it. Left unanswered, it goes after a minute and is asked again
  the next time you start Polyglotic.
- Lab: word links are drawn in Learning load too. They were switched off
  while it was on.
- A word that isn't in its line's language's dictionary is looked up in
  the window's translation languages' dictionaries and your other
  languages', and the card says which one answered ("From the English
  dictionary").
- With several languages learned, a word is looked up in its own
  language's dictionary on any line: an English word in a Chinese line gets
  its English entry, a Chinese word in an English line (or a line whose
  language wasn't recognised) can be hovered and looked up where before it
  couldn't, and a Russian word in an English or Chinese line opens
  Russian's dictionary. The same goes for any language learned whose
  writing tells it apart.
- What your speakers play quietly, or your headphones let out, is far less
  often captioned as your own speech. Your own speech, even quiet, is
  still captioned.

## 0.1.5 - 2026-11-15

### New

- Chinese and English dictionaries work at once for a learner of both.
  A word on a Chinese line is looked up in the Chinese dictionary and one
  on an English line in the English one, on both caption lines, whichever
  you learn first. Words you save, put in your deck or hear count toward
  their own language, each with its own level, categories, Words section
  and Anki export. A language you add works at once.
- Deleting your learning data on Account with "Also delete it from this
  PC" ticked now deletes it on this PC in every language you're learning,
  not only one. If some of it can't be deleted, Home says which language.
- Russian's dictionary: learn Russian on the Learning page and its card
  offers the dictionary to download (about 13 MB; 62 MB once unpacked). A
  bar and a line say what it's doing - downloading 4.5 of 13.1 MB,
  checking the file - and, if it stops, why: no connection (it tries
  again by itself and carries on where it stopped), a metered connection
  (Download anyway), not enough room. Words in Russian captions can be
  looked up as soon as it's in, no restart, and Home says so if you're
  elsewhere. Learning lists the dictionaries on this PC with their size,
  and Remove.
- Vietnamese's dictionary: learn Vietnamese on the Learning page and its
  card offers the dictionary to download (about 2 MB; 4.5 MB once
  unpacked), with meanings in English. It finds words as Vietnamese
  writes them, of one syllable or several ("học sinh", student, is one
  word), and words in Vietnamese captions can be looked up as soon as
  it's in, no restart.
- A word you look up in a caption now says what it is in that line's
  translation, in your language: "Here: ngân hàng", first on its card,
  hovered or pinned. It comes from the word links the caption already
  has, so it works for every language pair - and for a language with no
  dictionary yet, it's what the card shows. It isn't kept with a saved
  word or put on an Anki card.

- Planned maintenance is said ahead: from a day before, Home says when
  ("Planned maintenance today, 15:00-15:30") in your own time, and the
  caption windows say it once, five minutes before. During it, Home and
  the tray say "Planned maintenance until 15:30" instead of "Polyglotic's
  server is down" - even while the server can't be reached - and
  captions come back by themselves at the end, with what's said from then
  on.
- Any of the 30 languages Polyglotic hears can now be chosen as a
  window's Spoken language - Russian, Japanese, Korean, Spanish and the
  rest, not only English, Mandarin and Cantonese. Detect says what it
  covers ("Detect · 30 languages"), and a language chosen reads "Always
  Russian". The list puts the languages you chose last first, then your
  own, each also written in its own words ("Russian · Русский"); in
  Settings - Speech you can type to find one. Dictation's Detect choice
  is now called "Detect automatically" too.
- When Detect has heard an app speak one language for a while, its
  caption window asks: "This sounds like Russian. Always hear it as
  Russian?" Yes sets that window's Spoken language - short or mumbled
  speech is then never taken for another language; Not now keeps Detect
  and the window won't ask about that language again.
- Polyglotic's own words in Spanish, French, German, Portuguese (Brazil),
  Italian, Japanese, Korean, Vietnamese, Indonesian, Turkish, Russian,
  Polish, Dutch, Ukrainian, Filipino, Thai, Hindi, Malay and Czech:
  Settings > App language, or "Like this PC" picks one when Windows is in
  it. They're drafted by machine and not yet
  checked by native speakers - Settings says so, with "Tell us what reads
  wrong" beside it.
- When an update has downloaded, Home says so - "Version X is ready.
  Restart to install it." - with what's new in two lines, Restart now and
  Later; the tray's menu offers it too. Polyglotic never restarts by
  itself: Later leaves it for the next time it starts. Settings - App -
  Updates now says what Check now found.
- Text size: Settings > App > Text size makes Polyglotic's own words
  smaller or larger - Settings, Words, Help, a word's card and its
  explanations, menus, and the buttons on caption windows and transcripts
  - at once, on top of Windows' own text size. Captions keep their own
  size (A- and A+ on each caption window and transcript).
- Dictation (preview) is held on Right Ctrl, a key nearly every keyboard
  has, or on any key or combination you choose: in Settings - Dictation,
  click the key and press the one you want - F9, Ctrl + Alt + D... If a key
  can't be used (it types, Windows keeps it, another program has it), it
  says why and keeps the one you had. A key you already chose stays.
- Translation size, in a caption window's settings under Text size: the
  translation from half to twice the size of what was said, for each
  window, with "Same as what was said" to put it back. 100 %, as before,
  unless you change it.
- A caption window's text goes from 60 % to 400 % now (it was 70 % to
  200 %), with a slider between A- and A+ in its settings to land between
  their steps.
- Your own speech lines up on the right, like a chat, in a caption window
  that shows it beside what you hear. Settings - Lab puts it
  back on the left, and has more to try: a tint behind it, a bar at its
  side, and its "You" label as a badge or not shown.
- You choose how long words on screen may still be corrected as more is
  heard: Settings - Timing, "Text can still change for", from
  0 to 3 seconds (3 as before). Shorter means fewer words changing while
  you read, and more mistakes left as they were first heard.
- Settings - Lab: Older captions dim all at once, as now, or
  step by step - each caption back a little dimmer, over 2 to 6 captions.
- Settings - Lab, more to try: Captions fill the width - what was said runs
  on across the window's width, its translation in the lines below it or
  line by line under it - with what stands between clauses run together;
  and Gap between new lines, so a new caption's lines arrive one at a time.
  Off until you choose them.

- Your level is now about how many words you know. Adding a language
  on Learning asks once - "About how many Chinese words do you know?" -
  with a few choices (for Chinese, each beside its HSK level) and "Not
  sure". The most common words up to there count as known, the next ones
  are the ones pointed out in captions, and rarer words are left alone
  until you hover or click them. Nothing changes for a level you already
  set until you choose again (Words - Change your level). A language you
  add from now on also starts with word links only on words past what
  you know.
- Learning has two new choices for each language. Learning window: how
  many of the next words past what you know are pointed out - 100, 500,
  1,000 or 2,000 (once your level is a number of words). Word links:
  every word, only words past what you know (or from a place you pick),
  or off for that language.
- Lab: Learning load, a second way to see new words (Settings - Lab,
  off until you turn it on). A set number of the next
  words past what you know - 500 unless you change it - are coloured in
  captions by how often you've heard them since: red, orange, yellow,
  green, each with its own underline. A word past green is ready to
  check: one click says "I know this" and the next word takes its place.
- Copy captions from a caption window: right-click a caption to copy it,
  or use Copy the newest caption and Copy all captions in the window's
  settings. You get each caption's time, what was said and its
  translation, as the transcript's Copy gives them, ready to paste
  anywhere.
- Copy on a word's card: the word, its reading and meaning, ready to
  paste. Ctrl+C does the same while a Polyglotic window has the keyboard.
- Right-click a line in a transcript for two more copies: Copy what was
  said, and Copy the translation, each on its own without the time.
- Transcripts can keep a whole lecture: Settings > App > Transcripts lets a
  transcript window scroll back and search the last 3 hours or the whole
  session, not only its newest 1,000 lines. Copy all and Save still have
  the whole session; the caption windows stay as short and quick as before.
  With either of those chosen, Quit asks before a long transcript that
  isn't saved is gone: Save..., Quit without saving or Cancel ("Don't ask
  again" turns it off; the same card turns it back on).
- Hidden caption windows stop listening after 15 minutes, so a window
  you hid and forgot no longer keeps sending its app's sound. Home and
  the tray say so, and showing the windows (Ctrl+Alt+H, the tray, or
  Captions on Home) carries on. While a hidden window is still captioning,
  the tray and Home say that too. Settings - Timing - Behaviour sets
  the time (5, 15 or 60 minutes, or Never) and can bring a hidden window
  back when speech starts. A window whose transcript is open keeps
  captioning: you're reading it there.
- The privacy notice is now version 3.1 (polyglotic.io/privacy). What
  changed: it says that a dictionary you choose to download comes
  through Cloudflare, which processes your IP address to deliver it, and
  that your learning load and the dictionaries you download stay on
  your PC.

### Better

- When this PC's clock looks wrong, Home says so in one quiet line - the
  date and time it shows, and where to set it - and captions keep working.
  When an out-of-date certificate on the network is what's in the way, most
  often an antivirus's HTTPS scanning or a VPN, Polyglotic says that
  instead of asking you to check a clock that's right.
- The app's language in Settings is a list, each language by its own
  name, none pinned first. A language whose text was drafted by machine
  and not yet checked by a native speaker says "Machine draft" beside
  it, with "Tell us what reads wrong".
- Live updates: a long stretch of speech now finishes in pieces, at a
  pause or a breath, as it does in Steady. The words you've already read
  stay as they are instead of all being rewritten when the speaker
  finally stops.
- Live updates with several apps talking at once: live updates used to
  stop for seconds at a time (only finished captions came) when two or
  three apps talked together at a fast setting. Now they slow down
  evenly, each app in turn, and the caption window says so once: "Lots
  of speech at once - live updates slowed; captions continue".
- Captions settle: words a caption has shown for about three seconds,
  and lines above its last two, no longer change when Polyglotic hears
  the speech again - their translations stay too. Only the newest words
  are still corrected.
- The line saying Cantonese and Vietnamese speech is captioned less
  accurately is gone from Settings, from each caption
  window's settings and from Help's questions.
- Polyglotic no longer asks which language you're learning before it
  opens. It starts translating into your PC's language when captions can
  be translated into it (else English) and detects the language spoken;
  choose the language you're learning on Learning, and change any of
  them in Settings whenever you like.
- It doesn't ask your level before it opens either. Until you set it,
  words count as known up to a middle level (HSK 3, or the 3,000 most
  common English words), and a quiet line on Home offers to set it.
- Language lists start with your PC's own language, then every other
  language by name; Chinese and English are no longer pinned on top for
  everyone.
- Settings - Timing shows only the chosen timing's own
  settings, in seconds, each with what it trades: Quick preview says when
  its dim lines come, and Live updates says when the longest wait for
  text makes it update sooner than the interval you chose.
- Settings is bigger and sorted by what you come to change, in six
  sections at its top: Look, Timing, Speech, Dictation, App and the
  experimental Lab - every setting one click away, each with a line saying
  what it does. A caption window's "All caption settings…" opens it on
  Look, and the tray's "More languages…" on Dictation; the small Look
  window is gone, and so are Home's Languages
  and Timing panels (the window's settings keep a Timing shortcut).
  Resetting the look no longer moves your caption windows: Home's Reset
  positions does that.

- Polyglotic's window opens sooner when you start it, and answers your
  first click sooner.

### Fixed

- Pointing at a word with 's in an English caption - "the game's graphics" -
  said it wasn't in the dictionary. It now shows the word's own entry, and
  counts it as heard.
- Looking up a word in a caption in a language Polyglotic has no dictionary for
  yet - Vietnamese, say - could show "Chinese for it" with unrelated Chinese
  words, matched by chance in the dictionary's English meanings. It now says
  there's no dictionary for that language yet.
- Opening Polyglotic while it was already running started a second copy,
  and the two could overwrite each other's settings. Now only one runs:
  opening it again brings the one that's running to the front - from the
  tray, or minimised.
- Scrolling Settings with the mouse wheel changed the lists and sliders it
  passed over - the timing, the background, the Lab, even the app's
  language. The wheel now scrolls the page. A slider takes the wheel only
  after you click it, and a list only while it's open. The same goes for a
  transcript's settings, Learning and Words.
- Some PCs couldn't sign in or caption: "Check this PC's date and time",
  though the date was right. An out-of-date certificate kept by Windows
  (or an antivirus) stopped the secure connection to Polyglotic's server.
  The connection now checks everything else as before and goes ahead; a
  PC whose clock is wrong connects too. The update check does the same.
- The grey hint in a box with nothing typed in it yet - Names and slang's
  "e.g. rizz, no cap, yyds" in Settings - was too faint to read easily.
  It's as clear as the other secondary text now, in every theme.
- An update cut short by a connection that drops started again from
  nothing at the next try, so on a shaky connection it could take many
  tries to arrive. It now carries on from where it stopped, and is still
  checked whole before it's installed.
- Settings - App - Hotkeys wrote Ctrl+Alt+L, P and H in English while the
  rest of the app wrote them in its own language (Strg+Alt+L in German).
  They're written the same way everywhere now.
- Report a problem on a laptop's short screen, at a larger text size or in a
  longer language (German, Japanese), was squeezed to fit: the line for what
  happened covered the first part and the last lines were cut off. Now the
  window fits the screen and what's between the title and Send scrolls.
- Moving the mouse over a caption window while a caption was sliding in
  stopped it halfway, its last lines cut off at the bottom for as long as
  the mouse stayed. The caption now settles in place at once, whole.
- Dictation with the server out of reach said "Working…" for 10 seconds
  before giving up. It now says "Not connected to the server" at once,
  and nothing you said is sent later.
- With "Caption my own speech" on, what you dictated also showed as a
  "You" line, and its minutes counted twice. While the dictation key is
  held, your mic now goes to dictation only; a line you were saying as
  you pressed it is finished with what you said before.
- After choosing another language to learn - English instead of Chinese,
  say - Words went on showing the other language's words without saying
  so, until Polyglotic started again. It now says whose words they are
  and that the new language is used from the next start.
- Fast speech with no pauses (a quick-talking video, say) was cut into
  captions every 6 seconds wherever the cut fell: mid-word, each piece
  ending in a full stop, often with the last word or two repeated at the
  start of the next. It's now cut at the quietest moment just before,
  with no words repeated and no full stop where the speech goes on.
- On some PCs (one seen on Windows 10), Polyglotic froze for about a
  second as Home opened, while it asked Windows which apps play sound.
  It now asks in the background.
- When Windows' text size changes while Polyglotic is open, a caption
  window's or transcript's notice ("Paused", "Reconnecting...") and Back
  to live, the "Looks wrong?" card and the pages of the main window all
  grow with it - nothing is cut off until a restart.
- A word you save is coloured at once, on the line you saved it from too:
  a line still being spoken - the dim one Steady shows during a long
  stretch of speech, and Quick preview's - showed saved words only once
  its finished caption came. Un-saving takes the colour off at once.
- Saved words stand out on every colour preset: on Paper's cream their
  colours were too pale to read, and where a category's colour matched
  its line's own (Saved's blue in Teletext's cyan translation) a saved
  word looked like the rest of the line. They're darker on Paper now, and
  a word that would match its line has a soft tint of its colour behind it.
- A problem report's log no longer shows your Windows user folder's
  name in the updater's lines (it was hidden everywhere else already).

## 0.1.4 - 2026-11-12

### New

- On Windows 10 version 2004 or later, Polyglotic now tries captioning
  apps one by one, as on Windows 11. If Windows on your PC can't, it
  says so once and captions everything the PC plays, as before; Try
  apps again on Home tries once more, and so does each Windows update.
- Dictation (preview), off until you turn it on in Settings > App or
  the tray: hold a key (Insert, unless you pick another), speak, let
  go, and your words are typed where your cursor is, in any program.
  It detects the language each time, or set one of 30 - English,
  Mandarin, Cantonese... - from Settings or the tray, and it's always
  heard as that; English can come out in Australian spelling. Esc
  cancels before the text arrives.
- Hear a word: the speaker beside Close on a word's card says it aloud
  in one of Windows' own voices, and again more slowly on the next
  click (R does the same in Polyglotic's own windows). It's said on
  your PC - nothing is sent - and it's left out of your captions. If
  Windows has no voice for the word's language, the card says how to
  add one, free, in Windows' Settings.

### Better

- The first screen asks only that you agree to the tester agreement;
  it no longer asks you to state your age (the agreement and the
  privacy notice say who Polyglotic is for).

### Fixed

- With "Caption my own speech" on, sound from your speakers that your
  mic picks up is caught more often and not shown as yours - when it
  reaches the mic late, as from Bluetooth speakers, or while Windows'
  volume is low and the speakers are turned up.
- Signing in, updates and reports could be refused before they reached
  our server ("Something on this network is in the way"). Fixed on our
  side for every version, and the app now says who it is.
- Your invite code now works again on the PC you used it on, as often
  as you need: after signing out, or if Polyglotic ever asks you to
  sign in again, type the same code. Another PC still needs its own
  code.

## 0.1.3 - 2026-11-11

One change: the first screen's yes is for people 14 or older (it was 16).

## 0.1.2 - 2026-11-11

### New

- Testing the alpha? Report a problem - the flag on a caption window's
  top bar, the tray's menu, Home, Account and Help - can now send what
  was shown and heard in the last few minutes, so we can see the
  problem again. You see each part first and can untick it; reports
  are deleted after 30 days.
- A shorter tester agreement: seven points. The app asks you to agree
  to it once more.

## 0.1.1 - 2026-11-11

Nothing you'd notice: from this version, Polyglotic checks that an update
comes from us before it installs it.

## 0.1.0 - 2026-11-11

The first test version, for friends: unsigned, on the alpha channel, with
captions from a server on our own PC. Thank you for trying it - tell us
what breaks with Report a problem.

### New

- Captions of what you hear, with a translation underneath: pick up to
  three apps, each in a caption window of its own, or everything the PC
  plays.
- Your own speech captioned too, in the window you choose ("Show my speech
  here").
- A translation language for each window, or the original only.
- Three caption timings: Steady (each sentence appears once, finished),
  Quick preview and Live updates.
- Caption windows as a panel, moved and resized from any edge, with
  bigger or smaller text, a lock, and a fade - they never take the focus
  from your game.
- A transcript for each app: search it, copy it, or save it as text, SRT
  or CSV.
- Look up any word in a caption: Chinese (CC-CEDICT, with HSK 3.0 levels)
  and English (ECDICT) dictionaries on your PC, with how common each word
  is.
- Mark words as learning, known or ignored; words you don't know yet are
  marked in finished captions.
- Words: your saved words, the words you keep hearing, and how much of
  what you hear you already know.
- Export for Anki: a ready-made deck file (.apkg) or a CSV, each card with
  the sentence you heard the word in.
- "Looks wrong?" on a finished line asks the server to check it again with
  its best models.
- Report a problem and Suggest something, from Help.
- The interface in English, Simplified Chinese and Traditional Chinese
  (the Chinese wording is still being reviewed).
- Three looks - Margin, Glaze and Signal - in light and dark; text follows
  Windows' text size.
- Sign in with your invite code. Usage statistics are sent only if you
  agree, and never what's said.
- Updates download quietly and apply the next time Polyglotic starts.
- Click a word in a language you aren't learning - Japanese in a
  Japanese stream - and its card asks once whether you're learning it
  too: Learn it too adds it to Learning; Not now doesn't ask again. In
  a language with no dictionary yet, the card says so rather than "Not
  in the dictionary".
- A Learning page, beside Words: the languages you're learning and
  what each one's dictionary gives, your level, and Word
  introductions - Off, A few per caption or Every new word - with what
  the marked words mean and where they go. "You're learning" and
  "Common words only" moved there.
- Ten colour presets for the caption windows, in Settings - Captions:
  Classic (as before), Broadcast, Teletext, Ember, Violet, Forest,
  Paper, Quiet, High contrast and Clear (safe for every kind of colour
  blindness). Change any colour after: type its exact value, or Pick…
  it.
- A live preview at the top of Settings - Captions shows two captions
  as your caption windows will: every change to the colours, panel,
  font or word links shows there at once.
- Word links can be Arrows again: a curve joins each word to its
  translation, as well as their shared colour (Settings - Captions -
  Word links).
- Pick the app a caption window captions from the window itself: click
  its name, or Captioning in its settings. Browsers and the main apps
  are listed even before they play, and start captioning when they do.
- In every timing, a small loading bar under the newest caption shows
  that speech is being heard and its caption is on its way - for your
  own speech too. With Windows' animation effects off, it stands
  still.
- Choose how new captions arrive, for every window, in Settings -
  Captions - Behaviour: Slide in (the default) or Appear.
- Each caption window has its own spoken language in its settings: a
  Chinese stream in one window and an English call in another are each
  heard as what they are, and Detect is there for mixed talk. Lines
  already in a window's language can be shown in another language from
  the same settings.
- Longest wait for text, in Settings - Captions - Timing: how long
  anyone can talk before you see text, in every timing - from 2 to 6
  seconds, 3 unless you change it. A smaller number means more
  updates.
- A caption window opens as soon as you choose an app, or everything
  your PC plays, and says it's waiting for audio until the first
  captions come.

### Better

- After you send a report or a suggestion, a notification says when it
  has reached us - or that it's saved to send later - so you see it in
  a game or a call too. Not while Polyglotic's Home is in front, which
  says it already.
- Moving the mouse across a caption window's words is lighter: only
  the captions it passes over are redrawn, and a lookup card following
  the mouse looks up the word it stops on, not every word on the way.
- The Panel | Strip choice is gone from the caption windows' settings:
  every window is a panel the size you set, and one you had as a strip
  opens as a panel.
- Settings is bigger and has three sections at its top: Captions,
  Learning and App. Captions holds every caption window's settings in
  one place - the look, word links, timing, fading and names and
  slang - each with a line saying what it does. A caption window's
  "All caption settings…" opens it; the small Look window is gone, and
  so are Home's Languages and Timing panels (the window's settings
  keep a Timing shortcut). Resetting the look no longer moves your
  caption windows: Home's Reset positions does that.
- A caption window's settings show Timing on one line, the timing now
  on a button that opens the three choices; all of it is in Settings.
- Settings' "Ask me the first-run questions again" is split where each
  answer belongs: change your level on Learning, and what you share on
  Account.
- Steady is the default timing again: each sentence appears once,
  finished and translated. A timing you chose stays; Help's "When do
  captions appear?" says what each does.
- In Steady and Quick preview, someone talking on without a pause is
  captioned in shorter pieces, so the next caption comes sooner.
- When Polyglotic's server can't be reached, Home, the caption windows
  and the tray say why - no internet, our server down or restarting, a
  firewall or proxy, the PC's clock - whose problem it is, and what to
  do, instead of just "Reconnecting".
- Signing in while Polyglotic's server can't be reached says whose
  problem it is, instead of always asking you to check your internet.
- Captions no longer fade away when nobody is talking, unless you
  choose a time in Settings - Captions - Fade after quiet. A time you
  chose before is kept.
- The caption font Polyglotic picks is now called "Polyglotic
  (Default)".
- Quick preview's dim first lines come with their translation too,
  until the finished caption replaces them.
- Names and slang shows examples you'll recognise (rizz, yyds, 鸡你太美, a
  streamer's or a game's name), and takes Chinese commas and 、 between
  them.
- "Looks wrong?" now says what it does and what it sends before it
  sends anything: choose Send report, or Cancel.
- Steady, Quick preview and Live updates each say what they do when
  you point at them, and so do a caption window's settings, All
  caption settings… and Open transcript.
- A locked caption window says how to unlock it (Ctrl+Alt+L) when you
  lock it, then shows the keys faintly in its corner.
- A caption window's settings no longer have Position: drag the window
  where you want it, and it stays there.
- Word links have a button of their own on each caption window. The
  text size buttons (A- / A+) moved into the window's settings. While
  the original is hidden, the button is dimmed and says why: word
  links need what was said shown.
- The newest caption stands out: as it comes in, the captions before
  it slide up and step back a little, and it rises into place from
  below - quicker when people talk quicker - so you can tell what just
  came in from the corner of your eye. Nothing moves under the mouse;
  with Windows' animation effects off, it simply appears. With
  Windows' high contrast, nothing steps back. While you've scrolled
  back to read, every caption is at full brightness.
- Word links' underlines sit below letters like g and y instead of
  through them, and you can make them thinner or thicker and closer or
  further in Settings - Captions - Word links.
- Words: Your words shows its first 8 words, then Show all - or search
  for the one you want - instead of every word you've met.
- Words: Saved words shows its first 8 words, then Show all, instead
  of every word you've saved.
- Words: Words you keep hearing shows the top 5, and Show more adds 10
  at a time.
- Words: Export for Anki links to How to import into Anki, on our
  website's help.
- The first run has Back on every screen after the first, keeping what
  you entered, and asks for your code before the main window opens.
- Save transcript as... and Export for Anki open in your Documents
  folder, or where you saved last - never in the app's own folder,
  which updates replace.
- Quick preview keeps its dim line up to date while someone talks on,
  instead of one first guess and then nothing until they pause.
- Steady no longer goes quiet through a long stretch of talk: once
  someone has talked for 3 seconds, a dim, translated line shows what
  they've said so far, until the finished caption takes its place.
  Quick preview and Live updates never leave you longer than that
  without text either.

### Fixed

- Exporting your words for Anki no longer freezes the app while the
  file is written, and it says where the file went.
- Dragging a slider in Settings no longer floods the server with your
  settings, which could make it turn away the speech sent at the same
  moment. The server now gets a change once you let go, and only one
  it needs.
- Dragging the panel's slider in Settings > Captions no longer holds
  up the app: the caption windows follow it as you drag, and it's
  saved once you let go.
- Your level's screen, learning Chinese, opens faster and no longer
  flashes its drop-down as a window of its own first.
- Polyglotic open on too many of your PCs, or too many failed sign-ins
  from your network, say so - they read "Reconnecting", like a dropped
  connection.
- Polyglotic's windows show its own icon, in their title bars and in
  Alt-Tab, instead of Windows' plain one.
- A code from a Plus email whose subscription was cancelled before it
  was used says so, and how to get Plus, instead of "This code doesn't
  work".
- A new caption's last line - often its translation - no longer stays
  cut off at the bottom of the caption window after sliding in.
- A caption on its way when you changed what's captioned is no longer
  lost: it's shown once the new captioning starts.
- A caption window's panel stays the size you set: it no longer grows
  and shrinks with the text as live captions come, and a joined
  window's quiet column shows its panel beside the others.
- After locking and unlocking Windows, moving the mouse over a caption
  window shows its top bar again.
- A caption window Windows minimises - "Show desktop", for one - comes
  straight back instead of staying gone until you restart Polyglotic.
- A caption window's top bar - its icons and its app's name - is
  readable on every colour preset and any panel colour you pick: dark
  on Paper's cream, where it was white.
- The first run's Your data screen no longer flashes a scroll bar over
  its text as it opens.
