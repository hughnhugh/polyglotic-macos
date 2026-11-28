# Our Czech words

The app's own terms in Czech, said one way in every string. Reviewed against
**Windows Czech**, **macOS Czech**, **OBS Studio Czech**, **Discord Czech**,
and **Anki Czech** UI conventions. The 0.1.12 refresh adds labels for the new
controls. The native review priorities are in [review-cs.md](review/review-cs.md).

How the Czech is written:
- Polite plural (**vykání**) throughout; standard Czech UI buttons use the
  infinitive (*Uložit*, *Zachytávat*, *Zobrazit*, *Přihlásit se*) and
  instructions use polite imperatives (*Klikněte*, *Zvolte*, *Podržte*).
- Impersonal / verbal-noun status labels (*Naslouchání…*, *Čeká se na zvuk…*,
  *Zpracovávání…*) rather than first-person singular (*Poslouchám…*).
- Three Czech plural forms (1; 2–4; 0, 5+) with exact case agreement.
- Dynamic names in placeholders (`{app}`, `{language}`) placed in apposition
  (after a noun, colon, or dash: *jazyk {language}*, *aplikace {app}*,
  *předvolba {name}*) so Czech declension stays grammatical.
- Czech typography: `„“` quotation marks, en-dash `–` with spaces (not ASCII
  `-` or em-dash `—`), single ellipsis `…`, space before `%` (`91 %`).
- Brand and platform names stay as they are: *Polyglotic* (indeclinable),
  *Plus*, *Lite*, *Standard*, *Premium*, *Anki*, *Windows*, *macOS*, *Mac*
  (declined naturally: *Mac*, *Macu*, *na tomto Macu*), *HSK*, *Pinyin*.

| English | Čeština | Note |
|---|---|---|
| caption / subtitle (noun) | titulek, titulky | |
| Caption (capture action button) | Zachytávat | OBS Studio / Windows Czech audio-capture verb; avoids awkward *Titulkovat* |
| caption window | okno titulků | |
| finished caption | hotový titulek | it won't change |
| playing | přehrává | paired with *bez zvuku* (Windows/audio UI) |
| quiet (audio state) | bez zvuku | opposite of *přehrává*; *ztlumit* / *ztlumeno* is reserved for muted |
| Quiet view | Tlumené zobrazení | matches *Tlumené* colour preset; avoids literal *Tiché zobrazení* |
| Fade after quiet | Skrýt po odmlce | idiomatic Czech for hiding captions after silence |
| reading / Readings | výslovnost / Výslovnost | pinyin, furigana, stress marks, romanization; avoids literal *Čtení* |
| Respelling | přepis výslovnosti | English pronunciation guide under *Výslovnost* |
| preset / Preset | předvolba / Předvolba | unified across Presets, Panels, and ColourControls (Windows/OBS/Lightroom Czech) |
| Look (Settings section) | Vzhled | standard Windows/macOS Czech |
| Recommended looks | Doporučené styly | natural Czech plural; avoids *Doporučené vzhledy* |
| Look (ProblemReport preview button) | Zobrazit | clear action verb for viewing attached data |
| re-speak / Re-speaking / re-spoken | zopakovat / Zopakování / zopakováno | learner repeating someone else's speech aloud; avoids *přeříkávat* (reciting a poem) |
| Steady | Ustálené | a caption timing |
| Quick preview | Náhled | a caption timing |
| Live updates | Živé aktualizace / Živě | a caption timing |
| transcript | přepis | |
| source | zdroj / zdroj zvuku | |
| translation | překlad | |
| Translate into | Přeložit do | |
| Original only | Jen originál | |
| Detect | Auto | short spoken-language choice (consistent across bar, buttons, and notes); menu item "Detect automatically" is *Rozpoznat automaticky* |
| spoken language | mluvený jazyk | |
| This PC | Tento počítač | Windows / Linux |
| This Mac | Tento Mac | macOS; *Mac* is always preserved on Mac strings, never replaced with *počítač* |
| lookup | vyhledání | |
| deck | balíček | Anki Czech convention |
| Card stack | Karty nad sebou | avoids collision with Anki's *balíček* |
| known | známé | a word's status; button "Known" is *Znám* |
| ignored | ignorované | a word's status |
| Words met | Slyšená slova | avoids literal *Potkaná slova* (*potkan* = rat in Czech!) |
| Learning load | Dávka učení | active pool of words being absorbed (*v dávce*, *počet slov v dávce*) |
| category | kategorie | |
| level | úroveň | |
| Word links | Propojení slov | |
| Lock all | Zamknout vše | |
| Hide all | Skrýt vše | |
| Resume | Pokračovat | |
| tray | oznamovací oblast | Windows Czech (*řádek nabídek* on macOS) |
| hotkeys | klávesové zkratky | |
| metered connection | připojení účtované podle objemu dat | Windows Czech official term |
| session | relace | unified (avoids mixing *sezení* and *relace*) |
| listening allowance | limit poslechu | |
| plan | tarif | |
| pass | přístup | time-limited pass (*Přístup na 1 měsíc*) |
| auto-renew | automatické prodlužování | unified across Upgrade strings |
| invite code | kód pozvánky | |
| Sign in | Přihlásit se | "Sign out": *Odhlásit se* |
| learning data | data učení | |
| dictation | diktování | |
| Home | Domů | the page |
| Words | Slova | the page |
| Learning | Učení | the page |
| Settings | Nastavení | the page |
| Help | Nápověda | the page |
| Account | Účet | the page |
| What to caption | Co titulkovat | heading over the audio-source choices |
| Also caption everything else | Titulkovat i vše ostatní | gives the other audio its own caption window |
| speaking pace | tempo řeči | abbreviated unit: *slov/min* |
| caption info | údaje o titulku | the source, language, time, and pace above a caption |
| Long lines | Dlouhé řádky | original and translation can alternate or be grouped |
| caption actions | akce titulku | *Uložit titulek*, *Kopírovat titulek* |
| Repeated words | Opakovaně slyšená slova | words heard several times that are still new to the learner |
| new words to highlight | nová slova ke zvýraznění | a setting under *Učení* |
| level / frequency rank | úroveň / pořadí podle četnosti | separate thresholds for marking or linking words |
| session average / peak | prům. / max. | speaking pace on the recent session card |
| make a suggestion | poslat návrh | distinct from reporting a problem |
