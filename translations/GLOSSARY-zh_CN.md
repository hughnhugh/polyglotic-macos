# Our Simplified Chinese words

The app's own terms in Simplified Chinese, so every string says them the
same way. First drafted in project 156 (2026-11-07); **rewritten in
polyglotic-hq 842 (2026-11-24)** after a native Mandarin speaker read the
Home page and found it "没有逻辑": "为……加字幕" said nothing a Chinese-only
reader could follow, and "安静" isn't what a sound app says. Correct a term
here first, then every string using it.

**The test for every string:** someone who reads only Chinese understands
it at a glance, and it reads as a well-known Chinese app would say it.
The models named below are the apps a Chinese PC user already knows:
Windows 11's own Chinese (实时辅助字幕, 语音输入, 音量合成器), OBS Studio
and 哔哩哔哩直播姬 (音频捕获, 窗口捕获), WeChat (你, 语音输入, 转文字),
Tencent Video and iQiyi (连续包月, 月卡), Anki's Chinese (牌组), Adobe's
Chinese (预设).

## How the Chinese is written

- Full-width punctuation (，。：；？！（）“”); a space between Chinese and
  Latin letters or numbers ("HSK 3 级", "听到 3 次", "{app} 的字幕").
- UI labels quoted inside a sentence with “” ("在主页选择“电脑播放的所有声音”"),
  where English leaves them bare; the quoted words are exactly the label's
  own translation.
- English's " - " between two parts becomes "：" or "，", or "——" before
  an aside or a next step - never an ASCII " - " (a test checks, 235);
  "…" stays "…".
- "你" throughout, never "您" (friendly, as the English is and as WeChat
  says it); "我" for the learner's own speech and choices ("我说的话").
- **Say what it does, not what the English says.** No word-for-word
  calques: drop English's "it", "this", "your" and "the" where Chinese
  leaves the subject out; no chains of "的"; no "被" where Chinese is
  active; no "请" on a label, and at most one in a message.
- **Buttons are verbs** of two to four characters (保存, 停止捕获, 重试);
  a setting's label is a noun phrase or a short verb phrase, its note one
  short sentence. The shortest wording that is still unambiguous wins.
- On a PC: 电脑 ("这台电脑"). On a Mac: Mac ("这台 Mac"), as Apple's Chinese
  says it.
- Brand and product names stay as they are: Polyglotic, Anki, Discord,
  Windows, HSK, and the plans Lite, Plus, Premium.

## Categorical fixes (842)

Words the first draft used for a product term everywhere, and what
replaced them. Never bring the left-hand ones back.

| Was | Now | Why |
|---|---|---|
| 加字幕 / 为……加字幕 / 给……加字幕 (caption an app) | 捕获 (the sound) | the app captures an app's sound and captions it; "加字幕" reads as editing subtitles into a video, and a Chinese reader asked "add captions to what?" (the friend's correction, 2026-11-24). OBS and 直播姬 say 捕获 |
| 安静 (quiet) | 暂无声音 (an app open but silent); 无声 (fade after quiet); 简洁 (the quiet view) | 安静 describes a room or a person, not a sound source |
| 听力 (listening) | 字幕 / 会话 | 听力 is the listening skill or an exam paper, never the app at work |
| 收听 (listening) | 字幕 / 正在生成字幕 | 收听 is tuning in to the radio |
| 听写 (dictation) | 语音输入 | Windows 11 (Win+H) and every Chinese keyboard call it 语音输入; to a learner 听写 is the classroom exercise |
| 通行证 (pass) | 月卡 / 年卡 | a one-off month or year, as Tencent Video and iQiyi sell them beside 连续包月; 通行证 is a game's battle pass |
| 方案 (plan) | 套餐 | one word for a plan, as Chinese services say it |
| 代码 (a code) | 兑换码 / 邀请码 | 代码 is program code |
| 读音 (readings) | 注音 | the pinyin or kana written over a word is 注音; 读音 is how a word sounds |
| 词语链接 / 单词链接 | 词语对应 | one word for word links |
| 实验室 | 实验功能 | says what's in it |
| 分开窗口 | 拆分窗口 | the opposite of 合并窗口, as Chinese apps say it |
| 您 | 你 | one register |
| 时机 (Timing) | 出字方式 | "时机" is an opportune moment; the setting is how and when words come out |
| 稳定 / 沉稳 (Steady / Calm) | 平稳 / 稳妥 | neither old name said what the mode does |
| 定稿 (finished caption) | 整句字幕 | an editor's word |
| 学习负荷 (Learning load) | 在学词 | read as "study burden"; it's the words being learned now |
| 我们的课程 (Our curriculum) | 推荐生词 | it's a few words the app picks, not a course |
| 习得 / 跟上内容 (the reading paths) | 原文优先 / 译文优先 / 同时显示 | say which line leads |
| 点击会穿过窗口 (clicks pass through) | 鼠标穿透 | the overlay apps' word |
| 应用 (Settings' App tab) | 通用 | 应用 read as the apps being captioned |
| 这台电脑 on a Mac | 这台 Mac | |

How many strings each fix touched is in polyglotic-desktop's pull request for 842.

## The words

| English | 中文 | Note |
|---|---|---|
| caption / subtitle | 字幕 | |
| live captions | 实时字幕 | Windows 11 says 实时辅助字幕, Android and iOS 实时字幕 |
| caption window | 字幕窗口 | |
| capture (sound), caption an app | 捕获 | "捕获 {app} 的声音"; the button 捕获; "停止捕获 {app}"; "正在捕获 {app}". Not 采集: that's a capture card or data harvesting, wrong for a privacy promise |
| caption (speech, the result) | 生成字幕 / 显示字幕 | "为我说的话生成字幕" |
| mute, muted | 静音 | Windows' 音量合成器 |
| playing / quiet (an app's state) | 正在播放 / 暂无声音 | |
| sound source, source | 声音来源 / 来源 | "显示来源" |
| app | 应用 | |
| Everything the PC plays | 电脑播放的所有声音 | the Mac's: Mac 播放的所有声音 |
| everything else the PC plays | 电脑播放的其他声音 | |
| Everything else | 其他所有声音 | the window beside one app |
| This PC (a source's label) | 这台电脑 | |
| mic / speakers / headset | 麦克风 / 扬声器 / 耳机 | |
| my speech, what I say | 我说的话 | |
| You (the learner's own captions) | 我 | the source label |
| re-speak (repeat what someone said into the mic) | 复述 | |
| dictation, dictate | 语音输入 | "按住 {key} 说话" |
| joined window / Join windows | 合并窗口 | |
| Separate windows | 拆分窗口 | |
| finished caption | 整句字幕 | a caption once its sentence is done; it won't change |
| live update(s) | 实时更新 | |
| Timing / Caption timing / Caption mode | 出字方式 | the Settings tab and the caption window's chip |
| Instant / Whole captions / Steady / Calm | 即时 / 整句 / 平稳 / 稳妥 | the timing modes; Taiwan's Instant is 立即 |
| Longest wait for text | 出字前最长等待 | |
| original / what was said | 原文 | "说的话" only where English says "what was said" of a person |
| translation | 译文 | the caption's line; 翻译 for the act ("翻译成") |
| Original only | 仅原文 | "仅原文（不翻译）" where English adds "(no translation)" |
| Translate into | 翻译成 | |
| second language | 第二语言 | |
| spoken language / Detect | 说话语言 / 自动识别 | |
| transcript | 字幕记录 | one app's finished captions; never 文字记录 (a test checks) |
| Back to live | 回到最新 | |
| lock / Lock all | 锁定 / 全部锁定 | clicks pass through: "鼠标穿透", the word overlay apps use |
| Hide all | 全部隐藏 | |
| Pause captions / Resume | 暂停字幕 / 继续 | |
| Reset positions | 重置位置 | |
| Panel / Strip | 面板 / 横条 | a caption window's two layouts |
| look (the caption windows') | 外观 | "字幕外观" where it's alone, and the Settings tab |
| Preset (a colour preset, in Look) | 配色 | a whole-window preset is 预设 |
| Quiet view / Fade after quiet | 简洁视图 / 无声后淡出 | |
| Follow / Acquisition / Both (what you read first) | 译文优先 / 原文优先 / 同时显示 | |
| preset | 预设 | Adobe's word; "默认" is the default |
| default | 默认 | |
| Lab | 实验功能 | |
| Settings' tabs | 预设、字幕外观、词语对应、注音、出字方式、语音、语音输入、快捷键、通用、实验功能 | "设置 > 语音输入" in a sentence |
| Learning load / in the load | 在学词 / 在学中 | |
| Our curriculum / Words at your edge | 推荐生词 / 进阶词 | |
| Past what you know | 超出水平的词 | |
| reading(s) (over a word) | 注音 | "拼音" or "假名" where it's one script's; Zhuyin is 注音符号 |
| word link(s) | 词语对应 | |
| word class | 词性 | |
| Looks wrong? | 好像不对？ | |
| our best model | 最佳模型 | |
| lookup / look up | 查词 / 查 | |
| lookup card | 查词卡 | |
| deck / Add to deck / in your deck | 牌组 / 加入牌组 / 在牌组中 | Anki's own Chinese word |
| word status: new, learning, known, ignored | 生词、在牌组中、已认识、已忽略 | the button "Known" is 认识 |
| unfamiliar word | 生词 | |
| saved words / Save to | 收藏的词 / 收藏到 | |
| category | 分类 | |
| level | 水平 | "HSK {level} 级" |
| Words you keep hearing | 常听到的生词 | |
| heard N times (exposures) | 听到 N 次 | |
| Key words / Most words | 关键词 / 大部分词 | |
| Common words only | 只标常用词 | |
| Names and slang | 名字和俚语 | spelling hints |
| Export for Anki | 导出到 Anki | |
| plan | 套餐 | "你的套餐" |
| pass (a month or a year, doesn't renew) | 月卡 / 季卡 / 半年卡 / 年卡 | "your pass" is 已购时长: a bare 卡 beside a payment reads as a bank card |
| Monthly / Yearly (auto-renewing) | 连续包月 / 连续包年 | |
| Plus has ended | Plus 已到期 | |
| auto-renew | 自动续费 | |
| subscription | 订阅 | |
| allowance (the minutes) | 额度 | "字幕时长额度已用完" |
| listening session | 会话 | in reports: "本次会话 ID"; elsewhere say 字幕 |
| Listening (the state) | 正在生成字幕 | |
| invite code / a code / an offer code | 邀请码 / 兑换码 / 优惠码 | checkout's "Have a code?" is 优惠码 |
| Sign in / Sign out | 登录 / 退出登录 | |
| tray | 托盘 | |
| hotkeys | 快捷键 | |
| usage statistics / crash reports | 使用统计 / 崩溃报告 | |
| learning data | 学习数据 | |
| Choose what to share | 选择分享内容 | |
| Report a problem / Suggest something | 报告问题 / 提建议 | |
| speech model / translator | 语音识别模型 / 翻译模型 | |
| Mandarin / Cantonese | 普通话 / 粤语 | |
| Home / Words / Learning / Account / Settings / Help | 主页 / 词汇 / 学习 / 账户 / 设置 / 帮助 | Windows 11's own 主页 and 账户 |

Counts use a measure word: 条 for captions (条字幕), 行 for lines, 个 for
words (个词), 处 for search matches (处匹配), 次 for times.
