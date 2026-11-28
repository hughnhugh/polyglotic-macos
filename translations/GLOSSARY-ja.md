# Our Japanese words

The app's own terms in Japanese, said one way in every string. Revised
2026-11-24 (polyglotic-hq 851) against Windows 11, macOS, OBS, YouTube, and
Anki Japanese UI conventions. Project 860 reviewed the full interface and refreshed it for 0.1.12 on
2026-11-25 (project 971). See [the Japanese review](review/review-ja.md)
for the 20 choices to check with a native reader.

How the Japanese is written:
- Polite です・ます in full sentences and explanations; concise verb or
  action forms on buttons (e.g. キャプチャ, 保存, 既知にする, 確認).
- Full-width punctuation (、。：？！「」（）); never ASCII ` - ` or bare
  ASCII `:` beside Japanese characters (except file-dialog filters like
  `(*.txt)` and keyboard shortcuts like `Ctrl+Alt+L`).
- A half-width space around Latin product names, variables, and numbers where
  natural (matching Windows Japanese UI), never inside Japanese-only runs.
- Drawn in Yu Gothic UI or Meiryo UI, never a Chinese face
  (`style.SCRIPT_FACES`).
- Product and standard names stay as they are: Polyglotic, Plus, Lite, Anki,
  Windows, Mac, Discord, Zoom, Chrome, HSK, SRT, CSV.

| English | 日本語 | Note |
|---|---|---|
| caption (noun) / subtitle | 字幕 | Universal in YouTube, Netflix, Windows/macOS |
| caption (verb, Home button / capture audio) | キャプチャ | Action button to capture an app's audio (`{app} をキャプチャ`, `{app} のキャプチャを停止`); not `字幕にする` |
| capture (audio) | キャプチャ | OBS / Windows / macOS convention |
| caption window | 字幕ウィンドウ | |
| joined window / Join windows | 統合ウィンドウ / ウィンドウを統合 | "Separate windows": ウィンドウを分離 |
| finished caption | 確定した字幕 | It won't change (not `完成した字幕`) |
| Instant | 即時 | Caption timing mode |
| Whole captions | 文ごとの字幕 | Caption timing mode |
| Steady | 安定 | Caption timing mode |
| Calm | 落ち着き | Caption timing mode that waits for words the model is sure of |
| Quick preview | プレビュー | Caption timing (legacy/Lab reference) |
| Live updates | リアルタイム更新 | Caption timing / live streaming updates (not bare `ライブ`) |
| Back to live | 最新に戻る | Jump to newest captions (not `ライブに戻る`) |
| transcript | 書き起こし | One app's finished captions (not `文字起こし`) |
| translation | 翻訳 | |
| Translate into | 翻訳先 | |
| Long lines | 長い字幕の表示 | The menu offers `各行の下に訳` and `原文と訳を別々に`. These two options are still marked for native review. |
| speaking pace (WPM) | 話す速さ（語/分） | In Home's last-session summary, `平均` is the average and `最高` is the peak |
| caption info | 字幕情報 | In the caption window menu |
| Original only | 原文のみ | |
| Detect | 自動検出 | |
| spoken language / They speak | 話されている言語 | |
| quiet (app audio status: no sound) | 無音 | Audio silence (not `静か`) |
| mute / muted | ミュート | Windows / macOS / Discord standard |
| Quiet (colour preset) / Quiet view | 控えめ / 控えめ表示 | Visually understated mode (not `静かな表示`) |
| source (OS audio device) | 音声ソース | In system/device lists |
| source (label above caption) | 発言元 | App name or “You” above each caption. Settings and presets call the toggle `ソースを表示`. |
| Source (caption window menu) | キャプチャ対象 | The application or audio this window is capturing |
| This PC / This Mac | このPC / このMac | |
| Everything the PC plays / Everything the Mac plays | PCで再生されるすべて / Macで再生されるすべて | System-wide audio capture |
| Everything else | その他すべて | All system audio except the apps already captured separately |
| Also caption everything else | その他の音声もキャプチャ | The helper text explains that the other audio opens in its own caption window |
| preset | プリセット | Adobe / OBS / macOS standard |
| Look (caption windows' visual style) | 見た目 | Distinct from app `Appearance` (`外観`); ProblemReport `Look` button is `確認` |
| Appearance (app window) | 外観 | Settings > App > Appearance |
| Word links | 単語リンク | |
| Readings | 読み | Ruby/reading lines above captions (furigana, pinyin, Jyutping, respelling) |
| re-speak / Re-speaking | 復唱 / 復唱中 | Repeating what the other speaker said |
| dictation | 音声入力 | Windows 11 & macOS standard |
| Learning load | 学習セット | The small set of words the learner is currently working on |
| Repeated words | よく聞く単語 | Words page list of new words the learner has heard repeatedly |
| listening allowance | リスニング利用枠 | Short form: `利用枠` |
| plan | プラン | `現在のプラン`, `プランを選択` |
| pass (prepaid period) | パス | `1か月パス`, `3か月パス`, `6か月パス`, `12か月パス` |
| lookup / look up | 辞書引き / 調べる | |
| deck | デッキ | Anki's Japanese word (`デッキに追加`, `デッキ内`) |
| known (status / button) | 既知 / 既知にする | Status badge: `既知`; action button: `既知にする` |
| ignored | 無視 | Word status |
| category | カテゴリ | |
| level | レベル | |
| Lock all | すべてロック | Clicks pass through: `クリックが下に通ります` |
| Hide all | すべて非表示 | |
| Pause captions / Resume | 字幕を一時停止 / 再開 | |
| Reset positions | 位置をリセット | |
| tray | 通知領域 | Windows taskbar tray |
| hotkeys | ショートカットキー | Never `ホットキー` |
| invite code | 招待コード | |
| Sign in / Sign out | サインイン / サインアウト | Windows standard (not `ログイン`, except macOS `ログイン項目`) |
| learning data | 学習データ | |
| Lab | ラボ | Experimental settings section |
| Home | ホーム | Page |
| Words | 単語 | Page |
| Learning | 学習 | Page |
| Account | アカウント | Page |
| Settings | 設定 | Page |
| Help | ヘルプ | Page |
