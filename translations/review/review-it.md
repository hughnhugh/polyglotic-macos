# Italian interface strings for native review

These 20 drafts are in the 0.1.12 catalog. Try each in its listed control
and choose the Italian wording that fits how the control behaves.

| English | Current Italian | Alternative | Where to check |
|---|---|---|---|
| Shows words right away for general listening. | Mostra subito le parole per l'ascolto quotidiano. | Mostra subito le parole per seguire l'ascolto di tutti i giorni. | **CaptionWindow** (`preset_reading.py`). Check the register of the general-listening timing preset. |
| Keeps the previous subtitle above the next one when space allows. | Se c’è spazio, il sottotitolo precedente rimane sopra quello successivo. | Se c'è spazio, il sottotitolo precedente resta sopra quello nuovo. | **CaptionWindow** (`preset_reading.py`). Check how the two subtitle rows are described. |
| Back to the newest captions | Torna ai sottotitoli più recenti | Torna agli ultimi sottotitoli | **CaptionWindow** (`caption_window.py`). Check the short action shown when the learner scrolls back. |
| Words at your edge | Parole al tuo limite | Parole appena oltre il tuo livello | **CaptionWindow** (`caption_window.py`). Check the label for words just past the learner's current vocabulary. |
| Learning load | Carico di apprendimento | Parole in apprendimento | **CaptionWindow** (`caption_window.py`). Check whether the label conveys the colour view of how well you know each word. |
| Match | Uniforma | Stessa dimensione | **CaptionWindow** (`caption_window.py`). Check the short button for making the translation text match the caption text. |
| Whole captions | Sottotitoli interi | Sottotitoli completi | **CaptionWindow** (`timing_popover.py`). Check the timing mode that waits for a whole caption. |
| Calm | Pacato | Calmo | **CaptionWindow** (`timing_popover.py`). Check the timing mode that waits for more certain words. |
| Broadcast | TV | Televisivo | **ColourControls** (`colour_controls.py`). Check the colour preset with a TV-style appearance. |
| Ember | Brace | Braci | **ColourControls** (`colour_controls.py`). Check the warm colour preset name. |
| Light | Sottile | Leggero | **ColourControls** (`colour_controls.py`). Check font weight next to the other weights. |
| Soft | Morbido | Attenuato | **ColourControls** (`colour_controls.py`). Check the lowest contrast setting next to the other levels. |
| {name} is quiet: no sound from it in the last %Ln second(s) | {name} è senza audio: nessun suono nell’ultimo %Ln secondo / {name} è senza audio: nessun suono negli ultimi %Ln secondi | Nessun audio da {name} nell'ultimo %Ln secondo / Nessun audio da {name} negli ultimi %Ln secondi | **Help** (`help_page.py`). Check the audio diagnostic for recent silence. |
| Faint ahead | Tenui in anticipo | Anticipo attenuato | **Panels** (`panels.py`). Check the mode that previews upcoming words in faint text. The same label is used in Presets. |
| Conversation | Conversazione | Conversazioni | **Presets** (`preset_popover.py`). Check the preset for calls and chats. |
| Pinyin, Jyutping or a respelling over the words | Pinyin, Jyutping o pronuncia sopra le parole | Pinyin, jyutping o una guida alla pronuncia sopra le parole | **Presets** (`preset_popover.py`). Check the compact description covering both phonetic spelling and romanization. |
| Readings | Letture | Guide alla pronuncia | **Settings** (`settings_page.py`). Check the heading for pinyin, furigana, jyutping, stress marks and respelling. |
| Display new lines | Alternate | Riga per riga | **SettingsPopover** (`settings_popover.py`). Check the Long lines option that interleaves each original line with its translation. |
| following | segue | segue la diretta | **TranscriptWindow** (`transcript_window.py`). Check the transcript's follow-live status. |
| heard %Ln time(s) | sentita %Ln volta / sentita %Ln volte | ascoltata %Ln volta / ascoltata %Ln volte | **Words** (`words_page.py`). Check the word's exposure count and feminine agreement. |
