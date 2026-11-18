# 0223 Captions are drawn in faces chosen per language, the small ones carried by the app

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user, 2026-11-18 ~05:35, on polyglotic-hq 479's
  sheet ("The fonts look like good safe default choices, go with what
  seems best": its DECISIONS #207 as recommended - the ★ defaults,
  delivery C, a row per language in Look); built in polyglotic-hq 482.

## Situation

Captions were drawn in Windows' own faces: Segoe UI Variable for every
Latin, Cyrillic and Greek language, YaHei and JhengHei for Chinese, and
whatever Qt fell back to for the rest - Tahoma for Thai and Arabic, which
italic modes also slanted. 479 picked a face per language, measured their
size and licences, and found what a build must handle: a made-up bold in
readings, Arabic slanted, Noto CJK's taller line box, fonts arriving
mid-session.

## Decision

- **A face per language, in one place.** `ui_next.fonts` maps a caption
  language to its script (`SCRIPTS`), each script to its default face
  (`DEFAULTS`) and to the OS's own faces after it (`WINDOWS`, `also`);
  `caption_families` is a caption's family list: the learner's choice,
  the default, the OS's own, then the Latin ones. The caption layout asks
  it for every row; nothing else in the interface changes (lookup cards
  and Learning keep the OS's faces, `LATIN_FAMILIES` and `CJK_FAMILIES`).
- **The small scripts' defaults and Simplified Chinese's are carried by
  the app** (`fonts.BUNDLED`, in `ui/assets/fonts`, 5.2 MB): Noto Sans SC,
  Noto Sans Thai Looped, Be Vietnam Pro, Noto Naskh Arabic, Noto Sans
  Devanagari, PT Sans and IBM Plex Sans, added to Qt's fonts by the first
  caption layout (`caption_faces.load`, about 7 ms), before it lays
  anything out. `tools/caption_fonts.py` makes them from pinned sources.
  Traditional Chinese, Cantonese, Japanese and Korean keep the OS's faces
  until their own come as downloads.
- **Faces with a Reserved Font Name ship as published** (PT Sans, IBM
  Plex Sans, and Be Vietnam Pro's static Medium); the Noto faces are fixed
  at Medium, Noto Sans SC is cut to the 8,105 General Standard characters
  and GB2312's with a SemiBold of what readings draw, and Noto Sans SC's
  and Noto Naskh Arabic's line boxes are made YaHei UI's and one fitted to
  real Arabic. Those two are named "... Captions": some Windows 11 PCs
  have Noto Sans SC of their own, and Qt took its line box for ours under
  one name.
- **A row per captioned language in Look** (`face_rows`): its list grouped
  Sans / Serif / Handwritten / This PC's own / Any font on this PC; a
  language's choice is kept by language (`CaptionLook.faces`), the one
  font chosen before 482 still every other language's.
- **The other faces are downloaded** (`fonts.PACKED`, built by
  `tools/caption_fonts.py --packs`): Traditional Chinese's, Cantonese's,
  Japanese's and Korean's defaults once that language is captioned, every
  other face once it's chosen. They ride the signed pack list (decisions
  0122, 0133, 0192, 0197): a `fonts` entry per face - its name, family and
  credit - whose files are riders of kind `font` with their own `min_app`
  (0.1.8), which an app from before doesn't read. `FontDelivery` (`main`)
  downloads them on a `PackDeliveries` of their own into the data folder's
  `fonts`, each face's files as one download with every step said in its
  Look row; a face that lands is added to Qt's fonts and every caption
  layout lays its rows out again (`caption_faces.generation`), so no text
  laid out before is drawn in a face that came after (479 saw boxes).
  Until it's here, the OS's own draws.
- **479's must-handles:** Arabic is never slanted (`fonts.upright`), in
  Quick preview and any italic mode alike, and drawn 15 % larger;
  Devanagari 10 % larger (`fonts.SIZES`); a reading asks for SemiBold only
  where its face has one that heavy, else stays at its text's weight
  (`reading_lines.reading_font`); Mandarin shown in Traditional takes
  Traditional Chinese's faces, which the Simplified cut would draw only
  some of.

## Why

- One table is the single place to change a language's face, and the only
  thing the Look rows and font packs need to extend.
- Carrying the small faces costs little (479: about 3.7 MB in a zip) and
  fixes what is visibly wrong today; the large CJK faces only go to their
  learners, as downloads.
- Not taken: one style set for every language (479: no "handwritten"
  Thai or Arabic to match Chinese Kai); the OS's fonts only (Thai and
  Arabic stay in Tahoma).

## What would make us reverse it

- The installer's growth matters more than the faces (a size budget), or
  a face reads worse than the OS's in the learners' own feedback.
- Windows ships the same faces on every PC (this PC's Windows 11 has
  Noto Sans SC, TC and HK), making the bundled Chinese face redundant.

## How we'd reverse it

- A language back to the OS's face: its line in `DEFAULTS` (its files
  out of `BUNDLED` and `ui/assets/fonts`). Everything else follows.
- No downloads: `PACKED` empty and the list's `fonts` left out; an app
  that reads them then finds none, and its rows offer only the bundled and
  the PC's faces. A face published by mistake goes with a list published
  without its entry (`publish_packs` keeps the faces published before, so
  that's one line taken out of `--previous`'s list by hand), and its files
  then stay on the PCs that have them, unused once no row names them.
- Faces not carried at all: `BUNDLED` empty and the assets removed; the
  lists still name the OS's own faces, so nothing breaks.
