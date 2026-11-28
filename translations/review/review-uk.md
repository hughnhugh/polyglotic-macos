# Ukrainian review for 0.1.12

Check these 20 entries in the UI. The two Home and caption-toolbar
labels with unchanged English carry forward the 2026-11-24 review.

Five entries are provisional. Check whether **Link words after** reads
naturally with the frequency-rank and level choices, and whether
**Repeated words** describes newly heard words that recur. The Words
empty state and the two Learning descriptions use the same provisional
term.

| Context and control | English source | Current Ukrainian | Alternative to consider |
|---|---|---|---|
| CaptionWindow · Caption toolbar layout tooltip (caption_window.py) | Fill the width, in every window: captions run on in lines as wide as the window, each line of what was said over its translation | «На всю ширину» в усіх вікнах: субтитри займають усю ширину, переклад іде під кожним рядком оригіналу | Субтитри на всю ширину: переклад під кожним рядком оригіналу |
| CaptionWindow · Caption toolbar singing setting and audio disclosure (caption_window.py) | Captions singing in music players whose spoken language is Detect. Their sound is sent even without speech, a few seconds at a time. Off: only speech is sent | Створює субтитри до співу в музичних програвачах із режимом «Авто» для мови мовлення. Звук надсилається по кілька секунд навіть без мовлення. Якщо вимкнути, надсилається лише мовлення | Створювати субтитри до співу за автовизначення мови |
| CaptionWindow · Caption header pace next to the speaker or microphone icon (caption_window.py) | {now} wpm · avg {average} | {now} слів/хв · сер. {average} | {now} слів/хв · середнє {average} |
| DesktopApp · Tray status for hidden caption windows (check all three plural forms) (app.py) | Hidden windows paused after %n minutes - show them to resume | Приховані вікна призупинено через %n хвилину. Покажіть їх, щоб продовжити | Субтитри призупинено через %n хвилину. Покажіть вікна, щоб продовжити |
| Help · Help diagnostic results and report disclosure (help_page.py) | Your report includes these results, but nothing you heard or read. | До звіту ввійдуть результати перевірки. Звук і текст субтитрів до звіту не потраплять. | До звіту ввійдуть результати перевірки, без аудіо й тексту субтитрів |
| Help · Help topic heading (help_page.py) | Caption one app separately | Субтитри для однієї програми окремо | Окреме вікно субтитрів для однієї програми |
| Home · Home source chooser heading (home.py) | What to caption | Джерело звуку для субтитрів | Виберіть джерело звуку |
| Home · Home checkbox for the second caption window (home.py) | Also caption everything else | Також показувати субтитри до решти звуків | Субтитри й для решти звуків |
| Home · Home last-session pace summary (home.py) | Them {average} avg · {peak} peak | Інші: сер. {average} · макс. {peak} | Інші: {average} у середньому · {peak} макс. |
| Hotkeys · Hotkeys option next to the separate-key choice (hotkeys_card.py) | Share dictation's key | Клавіша диктування | Та сама клавіша, що й для диктування |
| Learning · Learning word-link options next to «Every word» and «Off» (learning_page.py) | Words beyond your level | Слова поза вашим рівнем | Складніші слова |
| Learning · Learning threshold label next to frequency and level choices (learning_page.py) | Link words after | Зв’язувати слова після | Починати зв’язки після |
| Panels · Settings explanation next to simplified and traditional script choices (panels.py) | The characters Mandarin captions are written in, with Detect too. Lookups, transcripts, copies and Anki use the same. Translations into Chinese keep the script you translate into. | Вибирає спрощені чи традиційні ієрогліфи для субтитрів мандаринською, зокрема з автовизначенням мови. Цей вибір також діє для словника, розшифровок, копіювання й Anki. Переклад китайською використовує писемність, задану мовою перекладу. | Писемність субтитрів мандаринською |
| Panels · Settings option for the quiet visual mode (panels.py) | Captions in soft grey and gold, a little bigger, with pinyin over every word and only your chosen words in blue - no underlines or arrows. Point at a word to see the word it's linked to. Turns word links off. | Трохи більші субтитри в м’яких сірих і золотистих тонах, піньїнь над кожним словом, вибрані слова синім. Підкреслень і стрілок немає. Режим вимикає «Зв’язки слів», а відповідник слова все одно можна побачити, навівши на нього вказівник. | Спокійний вигляд із піньїнем та відповідниками за наведенням |
| Presets · Preset summary and caption opacity control (presets_card.py) | Panel: how solid | Підкладка: щільність | Непрозорість підкладки |
| SettingsPopover · Caption settings, long-line mode that alternates each original row and its translation (settings_popover.py) | Display new lines | Рядок за рядком | Оригінал і переклад почергово |
| SettingsPopover · Caption settings, long-line mode that groups rows by language (settings_popover.py) | Grouped | Блоками | Спочатку оригінал, потім переклад |
| Words · Words heading for newly encountered words that recur (words_page.py) | Repeated words | Часто чуті слова | Слова, які ви часто чуєте |
| CaptionWindow · Caption toolbar visual mode toggle (caption_window.py) | Quiet view | Тихий вигляд | Спокійний вигляд |
| Home · Home source row action to open captions (home.py) | Caption | Субтитри | Створити субтитри |
