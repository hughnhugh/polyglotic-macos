# 0249 Chinese captions default to calligraphy, with the sans behind it

- **Status:** accepted (amends 0223's Chinese defaults)
- **Date:** 2026-11-20
- **Decided by:** the user, on preview 1 (2026-11-18 ~21:55: "how do i
  access chinese calligraphy font? make a stand out one the default and
  customisable (should have recommended presets)"); the face picked in
  polyglotic-hq 532 by its measure, for the user to confirm in the next
  preview.

## Situation

0223 drew Chinese captions in Noto Sans SC (bundled) and Noto Sans TC
(downloaded). The user asked for a stand-out calligraphy face as the
default. 532 measured the open-licensed candidates (its report and
`projects/532-*/results/coverage.tsv` in polyglotic-hq):

- Ma Shan Zheng, Zhi Mang Xing, Long Cang and Liu Jian Mao Cao (Google
  Fonts, OFL, no Reserved Font Name) share one character set: GB2312's
  6,763 - every character of HSK 1-9's words and FLEURS' Mandarin, 81.9 %
  of the 8,105 General Standard ones, 55 % of the commonest 3,500's
  Traditional forms - and no pinyin tone marks. Of the four, only Ma Shan
  Zheng is a regular script (kaishu): the others are running and cursive
  hands a learner can't read yet.
- LXGW WenKai TC (OFL) covers 99.9 % of the 8,105's Traditional forms; AR
  PL UKai (Arphic Public License, a copyleft) 96-97 %; no brush face
  under an open licence covers Traditional.

## Decision

- **Simplified Chinese's default is Ma Shan Zheng,** carried by the app
  (`fonts.BUNDLED`, "Ma Shan Zheng Captions": cut by
  `tools/caption_fonts.py`, given YaHei UI's line box, 5.8 MB, about 3.8
  MB compressed in the installer). No pack list publish is needed.
- **Traditional Chinese's default is LXGW WenKai TC,** downloaded when
  Traditional is captioned, as Noto Sans TC was (0223): it waits on the
  caption faces' riders being published, as Noto Sans TC already did.
- **The script's sans stays behind the calligraphy** (`fonts.BEHIND`):
  Noto Sans SC after Ma Shan Zheng draws the characters it hasn't (the
  rarer 1,342 of the 8,105) and, while LXGW WenKai TC isn't here, Noto
  Sans TC if it is, then Windows' JhengHei.
- **Readings never use a face without their tone marks** (`Face.reads`,
  `fonts.reading_families`): pinyin over Ma Shan Zheng is in Noto Sans
  SC's SemiBold, not a brush's consonants beside another face's vowels.
- **Calligraphy is its own group in Look's Fonts card** (`CALLIGRAPHY`),
  so it can be found; Noto Sans SC stays listed under Sans.

## Why

- Ma Shan Zheng is the one stand-out face a learner can read: brush
  strokes, but the regular script they learn to write, legible from the
  captions' 21 px up (532's sheet). Its characters cover everything the
  test texts use; the sans behind it covers the rest without boxes.
- Carrying it keeps the default working on day one, offline, without a
  publish that needs the user's word.
- Not taken: Zhi Mang Xing, Long Cang, Liu Jian Mao Cao (running and
  cursive hands); LXGW WenKai for Simplified (a pen's kai, less of a
  stand-out; still offered as "Polyglotic Kai"); AR PL UKai (thin at
  21 px, and a copyleft licence for a cut); Windows' KaiTi and DFKai-SB
  (only on PCs with Chinese supplemental fonts).

## What would make us reverse it

- Learners find brush text harder to read at speed than the sans (a
  lookup or "too hard" signal, or the user's preview).
- An open brush face that covers Traditional appears, or the installer's
  size budget can't carry 3.8 MB more.

## How we'd reverse it

- Back to the sans: `DEFAULTS["zh"]` and `["zh-hant"]` to Noto Sans SC
  and TC Captions; learners who chose a face keep it. Ma Shan Zheng can
  stay in `BUNDLED` as an option, or go with its files.
- `BEHIND` and `Face.reads` then do nothing and can go.
