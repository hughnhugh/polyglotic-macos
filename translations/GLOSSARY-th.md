# Our Thai words

The app's own terms in Thai, said one way in every string. **A machine
draft** (polyglotic-hq 294, 2026-11-13, by Claude) for a native speaker's
review: correct a term here first, then every string using it.

How the Thai is written: neutral and polite without particles (no ครับ/ค่ะ),
as Thai software is; a space between phrases where Thai puts one; drawn in
Leelawadee UI (`style.SCRIPT_FACES`); Polyglotic, Plus, Anki, Windows, HSK
stay as they are.

Qt on Windows can't break a line inside a run of Thai (it has no Thai
word breaker there), so a long run with no space overflows a narrow
label. Keep a space between phrases in long text; the UI lab's
clipped-text check finds a run too long for its place (the note on
Mongolian and Kazakh needed one, 2026-11-13).

| English | ไทย | Note |
|---|---|---|
| caption | คำบรรยาย | |
| caption window | หน้าต่างคำบรรยาย | |
| finished caption | คำบรรยายฉบับสมบูรณ์ | it won't change |
| Steady | คงที่ | a caption timing |
| Quick preview | พรีวิว | a caption timing |
| Live updates | สด | a caption timing |
| transcript | บันทึกคำบรรยาย | |
| translation | คำแปล | |
| Translate into | แปลเป็น | |
| Original only | ต้นฉบับเท่านั้น | |
| Detect | อัตโนมัติ | |
| spoken language | ภาษาที่พูด | |
| This PC | พีซีเครื่องนี้ | |
| lookup | ค้นคำ | |
| deck | สำรับ | Anki's word |
| known | รู้แล้ว | a word's status |
| ignored | ข้าม | a word's status |
| category | หมวด | |
| level | ระดับ | |
| Word links | จับคู่คำ | |
| Lock all | ล็อกทั้งหมด | |
| Hide all | ซ่อนทั้งหมด | |
| Resume | ทำต่อ | |
| tray | ถาดระบบ | |
| hotkeys | ปุ่มลัด | |
| invite code | รหัสเชิญ | |
| Sign in | ลงชื่อเข้าใช้ | "Sign out": ออกจากระบบ |
| learning data | ข้อมูลการเรียน | |
| dictation | พิมพ์ด้วยเสียง | |
| Home | หน้าแรก | the page |
| Words | คำศัพท์ | the page |
| Settings | การตั้งค่า | the page |
| Help | ช่วยเหลือ | the page |
| Account | บัญชี | the page |
