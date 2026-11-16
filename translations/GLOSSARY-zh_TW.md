# Our Traditional Chinese (Taiwan) words

The interface in Traditional Chinese, as Taiwan writes it - for Taiwan,
Hong Kong and Macau Windows. **A draft** (project 156, 2026-11-07, by
Claude) for a native reader in Taiwan, and one in Hong Kong for the words
Hong Kong says differently.

**How it was made:** the Simplified draft (`polyglotic_zh_CN.ts`, its
terms in `GLOSSARY-zh_CN.md`) through OpenCC's `s2twp` (Simplified to
Taiwan, with Taiwan's phrases: 软件 軟體, 视频 影片, 设置 設定, 窗口 視窗,
默认 預設, 服务器 伺服器...), then the Taiwan words below that `s2twp`
leaves as the mainland says them, and Taiwan's quotation marks 「」.
A new string is drafted the same way, or by hand with these words.

| English | 繁體（台灣） | 简体 | Note |
|---|---|---|---|
| caption window | 字幕視窗 | 字幕窗口 | |
| app | 應用程式 | 应用 | |
| Home | 首頁 | 主页 | |
| Settings | 設定 | 设置 | |
| Help | 說明 | 帮助 | Windows' own word in Taiwan |
| help (the verb) | 幫助 | 帮助 | 說明 is only the Help page's name (235) |
| kind, type | 類型 | 类型 | never 型別, a programming word (235) |
| Account | 帳戶 | 账户 | |
| Sign in / Sign out | 登入 / 登出 | 登录 / 退出登录 | |
| Quit | 結束 | 退出 | |
| tray | 系統匣 | 托盘 | Windows itself says 通知區域 |
| hotkeys | 快速鍵 | 快捷键 | |
| speakers | 喇叭 | 扬声器 | |
| full screen | 全螢幕 | 全屏 | |
| feedback | 意見回饋 | 反馈 | |
| email | 電子郵件 | 邮箱 | |
| Refresh / Search | 重新整理 / 搜尋 | 刷新 / 搜索 | |
| level | 程度 | 水平 | "你的程度" |
| the app's log | 記錄檔 | 日志 | |
| Export / import | 匯出 / 匯入 | 导出 / 导入 | |
| Mandarin | 華語 | 普通话 | **check:** 國語 is as common in Taiwan; Hong Kong says 普通話 |
| Cantonese | 粵語 | 粤语 | Hong Kong also says 廣東話 |
| deck | 牌組 | 牌组 | Anki's own word in Taiwan too |

To look at first: 華語, 系統匣, 程度, 說明, and the help texts (the
longest strings, where machine conversion reads least natural).
