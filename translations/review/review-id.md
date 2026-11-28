# Indonesian 0.1.12 native review

Try these 20 entries in the app at normal text size. They are ranked by
how likely an alternative is to make a setting or action easier to understand.

Entries 1, 2, 3 and 5 remain flagged as drafts in the catalog. The app
displays the Indonesian wording below while it awaits native review.

| Rank | English | Indonesian | Alternative | Where to try it |
|---:|---|---|---|---|
| 1 | Display new lines | Selang-seling | Per baris | Caption settings, Baris panjang. Each row of speech is followed by the matching translation. (`settings_popover.py`) |
| 2 | Grouped | Dikelompokkan | Pisah per bahasa | Caption settings, Baris panjang. All rows of speech come first, then all rows of translation. (`settings_popover.py`) |
| 3 | Also caption everything else | Sertakan semua suara lain | Beri subtitle untuk suara lain juga | Home, source picker. Adds a separate window for audio from apps other than the one already selected. (`home.py`) |
| 4 | Nothing selected to caption | Belum ada sumber subtitle | Belum memilih audio untuk subtitle | Tray status. The learner has yet to choose any audio source. (`app.py`) |
| 5 | Link words after | Batas tautan kata | Tautkan kata di luar batas | Learning, word links. The threshold can be a frequency rank or the learner's level. (`learning_page.py`) |
| 6 | Words beyond your level | Kata di atas levelmu | Kata yang belum kamu kuasai | Learning, word links. The app estimates these words from the learner's level. (`learning_page.py`) |
| 7 | Repeated words | Kata yang sering terdengar | Kata yang berulang | Words, deck suggestions. The app offers words heard a few times so they can be added to the deck. (`words_page.py`) |
| 8 | Remove from saved words | Hapus dari daftar tersimpan | Hapus dari kata tersimpan | Words, context menu. The action removes the saved status. (`word_table.py`) |
| 9 | Fade after silence | Pudar setelah hening | Redupkan setelah jeda | Settings and Presets, fading. Captions fade when speech stays quiet for the selected time. (`panels.py`) |
| 10 | Live lines below, earlier above | Langsung di bawah, sebelumnya di atas | Ucapan kini di bawah, riwayat di atas | Settings and Presets, scrolling. The current speech stays at the bottom. (`panels.py`) |
| 11 | Show speaking pace (WPM) | Tampilkan laju bicara (WPM) | Tampilkan kecepatan bicara (WPM) | Caption settings, switch for the words-per-minute display. (`settings_popover.py`) |
| 12 | Show caption info | Tampilkan info subtitle | Tampilkan detail subtitle | Caption settings, switch for the header with source, language, time and pace. (`settings_popover.py`) |
| 13 | Panel: how solid | Panel: kepekatan | Opasitas panel | Presets and caption settings, slider for the background's opacity. (`presets_card.py`) |
| 14 | Show my speech here | Tampilkan suaraku di sini | Tampilkan ucapanku di sini | Caption settings, microphone toggle. It controls whether the learner's speech appears in this window. (`settings_popover.py`) |
| 15 | {language} lookups aren't in this version yet. Captions and translation work. | Kamus bahasa {language} belum tersedia di versi ini. Subtitle dan terjemahan tetap berfungsi. | Arti kata dalam bahasa {language} belum tersedia di versi ini. Subtitle dan terjemahan tetap berfungsi. | Learning, language row. The unavailable feature is dictionary lookup. (`pack_row.py`) |
| 16 | Version {version} is available. Your connection is metered, so it waits: Home can download it anyway. | Versi {version} tersedia. Unduhan ditunda karena koneksi terukur. Untuk tetap mengunduh, buka Beranda. | Versi {version} tersedia. Unduhan ditunda untuk menghemat data. Buka Beranda untuk tetap mengunduh. | Settings, update status. The current network is marked as metered. (`settings_page.py`) |
| 17 | Use a code | Gunakan kode | Tukarkan kode | Upgrade, code redemption instead of a QR payment. (`upgrade.py`) |
| 18 | Chinese equivalent | Padanan Mandarin | Padanan dalam bahasa Mandarin | Word card, dictionary section showing the Chinese equivalent. (`lookup_card.py`) |
| 19 | Helpers | Alat bantu | Bantuan baca | Preset menu, controls for pronunciation guides and word links. (`preset_popover.py`) |
| 20 | Original only | Hanya asli | Ucapan asli saja | Caption bar, language selector. Shows the words in the language spoken. (`caption_window.py`) |
