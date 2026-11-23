# Third-party notices

Polyglotic includes the following third-party material, under these
licences. The full licence texts are in the `licenses` folder beside
`Polyglotic.exe`: every bundled Python package's own licence files (one
folder per package and version, collected by the build,
`tools/package/build.py`), Python's, the LGPL-3.0 and GPL-3.0 for Qt, and
the fonts' SIL Open Font License texts (`licenses/Fonts`).

## Qt and PySide6 (Qt for Python)

The interface is built with Qt 6 through PySide6 and shiboken6 (6.12),
used under the **GNU Lesser General Public License, version 3**
(`licenses/Qt-and-PySide6/LGPL-3.0.txt`, which comes with the GNU GPL
version 3, `GPL-3.0.txt`). Copyright (C) The Qt Company Ltd. and other
contributors. Polyglotic doesn't modify Qt. Qt's libraries ship as
separate, replaceable files (`_internal/PySide6/Qt6*.dll` and
`_internal/shiboken6/`): you may replace them with your own builds of the
same version. Qt's source code is at <https://download.qt.io/official_releases/qt/>
and Qt for Python's at <https://download.qt.io/official_releases/QtForPython/>,
or at <https://code.qt.io/>.

## Python

The Python 3.12 runtime (`_internal/python312.dll` and its standard
library), under the Python Software Foundation License
(`licenses/Python/LICENSE.txt`). Copyright (c) 2001 Python Software
Foundation; All Rights Reserved.

## Python packages

Each under its own licence, in `licenses/<package>-<version>/`:
ONNX Runtime (MIT, Microsoft; its third-party notices in
`licenses/onnxruntime/ThirdPartyNotices.txt`), numpy (BSD-3-Clause, with
the licences of the libraries it bundles, including OpenBLAS), pydantic
and pydantic-core (MIT), websockets (BSD-3-Clause), soundfile
(BSD-3-Clause), cffi (MIT-0), PyNaCl (Apache-2.0; it bundles
libsodium, ISC), annotated-types (MIT), typing-extensions
(PSF-2.0), typing-inspection (MIT), Segno (BSD-3-Clause, QR checkout),
genanki (MIT, Kerrick Staley and
contributors; it writes the Anki deck file) with chevron (MIT) and
cached-property (BSD-3-Clause), and PyYAML (MIT). genanki also lists
frozendict (LGPL-3.0) as a dependency, but never imports it, so it isn't
in the installed app. Only packages the app's code actually
loads are in the installed app, and only their licences are copied; the
build's summary lists each with its version and licence.

On a Mac only, sound is captured with catap (MIT, Copyright (c) 2025-2026
Sage Betko; Core Audio taps, with a native library of its own), PyObjC's
pyobjc-core, pyobjc-framework-Cocoa and pyobjc-framework-CoreAudio (MIT,
Ronald Oussoren and contributors), and sounddevice (MIT, Matthias Geier),
which bundles the PortAudio library 19.7.0 (MIT-style licence, Ross Bencina
and Phil Burk; its text in `licenses/PortAudio/LICENSE.txt`). None of these
is in the Windows app.

On Linux only, the device token is kept in the desktop's keyring through
jeepney (MIT, Copyright (c) 2017 Thomas Kluyver), which talks D-Bus in
pure Python. Sound is captured through the system's own libpulse (LGPL-2.1,
loaded from the PC, never bundled). Neither is in the Windows or Mac app.

## Velopack

The installer (`Setup.exe`), the updater (`Update.exe`) and the app's
update library (the `velopack` package) are Velopack 1.2.161, under the
MIT licence - Copyright (c) 2021 Caelan Sayler, (c) 2024 Velopack Ltd.
(`licenses/Velopack/LICENSE`; the Rust crates the library links are listed
with their licences in `licenses/velopack-1.2.161/sboms/`).

## PyInstaller's bootloader

`Polyglotic.exe` starts the app with PyInstaller's bootloader, under the
GNU GPL version 2 or later with PyInstaller's exception, which allows it
to be distributed with programs under any licence
(<https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>).

## libsndfile (through soundfile)

Speech is encoded as Ogg Opus by libsndfile 1.2.2 (LGPL-2.1), which the
`soundfile` package (BSD-3) ships as a separate library,
`_internal/_soundfile_data/libsndfile_x64.dll`, built with libopus 1.5.2
and libogg (BSD). Its licence text is in `licenses/_soundfile_data/COPYING`;
the library stays a separate, replaceable file (decision 0005), and its
source is at <https://github.com/libsndfile/libsndfile>.

## Fonts: Literata, Source Serif 4 and Overpass

The page titles' faces, one for each of the window's themes (Margin,
Glaze, Signal): `Literata-SemiBold.ttf`, `SourceSerif4-SemiBold.ttf` and
`Overpass-SemiBold.ttf` in `_internal/polyglotic_desktop/ui/assets/fonts/`,
each beside its licence text (`*-OFL.txt`, also in `licenses/Fonts/`).
All three are under the SIL Open Font License, Version 1.1, and none has a
Reserved Font Name:

- Literata - Copyright 2017 The Literata Project Authors
  (<https://github.com/googlefonts/literata>)
- Source Serif 4 - Copyright 2014 The Source Serif 4 Project Authors
  (<https://github.com/adobe-fonts/source-serif>)
- Overpass - Copyright 2021 The Overpass Project Authors
  (<https://github.com/RedHatOfficial/Overpass>)

They are modified versions, as the OFL allows: Google Fonts' variable fonts
(<https://github.com/google/fonts>, `ofl/literata`, `ofl/sourceserif4` and
`ofl/overpass` at commit `24ddc1f324cac5d9f5aedca126d298f56e3f1640`) fixed
at weight 600 (and optical size 24 for the two serifs) and cut to Latin
letters and punctuation, with fontTools 4.60.1 (`tools/heading_fonts.sh`).
They remain under the OFL.

## Fonts: the captions' faces

The faces captions are drawn in, by language, in
`_internal/polyglotic_desktop/ui/assets/fonts/`, each beside its licence
text (`*-OFL.txt`, also in `licenses/Fonts/`). All are under the SIL Open
Font License, Version 1.1:

- Noto Sans SC (as "Noto Sans SC Captions") - Copyright 2014-2021 Adobe
  (<http://www.adobe.com/>), with Reserved Font Name 'Source'
  (<https://github.com/notofonts/noto-cjk>)
- Ma Shan Zheng (as "Ma Shan Zheng Captions") - Copyright 2018 The Ma
  Shan Zheng Project Authors (<https://github.com/googlefonts/mashanzheng>)
- Noto Sans Thai Looped - Copyright 2022 The Noto Project Authors
  (<https://github.com/notofonts/thai>)
- Noto Naskh Arabic (as "Noto Naskh Arabic Captions") - Copyright 2022
  The Noto Project Authors (<https://github.com/notofonts/arabic>)
- Noto Sans Devanagari - Copyright 2022 The Noto Project Authors
  (<https://github.com/notofonts/devanagari>)
- Be Vietnam Pro - Copyright 2021 The Be Vietnam Pro Project Authors
  (<https://github.com/bettergui/BeVietnamPro>)
- PT Sans - Copyright (c) 2010, ParaType Ltd.
  (<http://www.paratype.com/public>), with Reserved Font Names "PT Sans"
  and "ParaType"
- IBM Plex Sans - Copyright © 2017 IBM Corp., with Reserved Font Name
  "Plex" (<https://github.com/IBM/plex>)

PT Sans, IBM Plex Sans and Be Vietnam Pro are as their makers publish
them, unmodified (Google Fonts' `PT_Sans-Web-*.ttf` and
`BeVietnamPro-Medium*.ttf`; IBM's `IBMPlexSans-Medium*.ttf` from
`@ibm/plex-sans` 1.1.0). The four Noto faces are modified versions, as the
OFL allows, none of them under a Reserved Font Name: Google Fonts'
variable fonts (<https://github.com/google/fonts>, commit
`7af0d90b4d532ffa4b041937b560c6df4e7b1e95`) fixed at weight 500 (Medium);
Noto Sans SC cut to the 8,105 characters of the Table of General Standard
Chinese Characters and GB2312's, with a weight 600 (SemiBold) copy of the
letters readings use, and both, and Noto Naskh Arabic, given a shorter
line box - with fontTools 4.60.1 (`tools/caption_fonts.py`). Ma Shan Zheng
(Google Fonts' `ofl/mashanzheng/MaShanZheng-Regular.ttf`, the same commit),
under no Reserved Font Name either, is cut the same way and given Noto
Sans SC's line box. They remain under the OFL.

Other caption faces are downloaded when a learner captions a language
whose default they are (Noto Sans TC, Noto Sans HK, Noto Sans JP,
Pretendard) or chooses one in Settings > Captions > Look: each comes with
its licence text beside it, in the `fonts` folder of Polyglotic's data, and
is credited in the list it comes from. All are under the SIL Open Font
License, Version 1.1. Those with a Reserved Font Name come as their makers
publish them (Pretendard, Smiley Sans, PT Serif, IBM Plex Sans Thai Looped
and IBM Plex Sans Arabic); LXGW WenKai, cut to the Simplified characters
above, comes as "Polyglotic Kai", as its Reserved Font Names ask; the rest
are cut or fixed at Medium as the bundled Noto faces are, named
"... Captions".

## The dictionaries

`cedict.sqlite`, `ecdict.sqlite` and `ecdict-en.sqlite` ship as separate, unlocked files beside
the app, in `dictionaries`, with their own `CREDITS.md` naming every source, its version,
licence and notice (written by `tools/dictionaries/build.py` from
`tools/dictionaries/sources.py`; decision 0009). In short: CC-CEDICT (CC
BY-SA 4.0), jieba's word frequencies (MIT), the hsk30 package's HSK lists
(MIT), ECDICT (MIT) and wordfreq's English frequencies (CC BY-SA 4.0,
including SUBTLEX, Google Books Ngram and OpenSubtitles data).
`ecdict-en.sqlite` is `ecdict.sqlite` with English meanings (decision
0211): Open English WordNet's (CC BY 4.0, from Princeton WordNet under the
WordNet License, whose notice `CREDITS.md` carries), ordered with counts
from UD English-EWT (CC BY-SA 4.0; counts only), and Polyglotic's own.
Both English files carry respellings of the commonest words (KAY-oss),
made by Polyglotic's own rules from the CMU Pronouncing Dictionary
(Copyright (C) 1993-2015 Carnegie Mellon University; its BSD-style
licence, in full in `CREDITS.md`), the usual pronunciation picked with
Wiktionary's help (CC BY-SA 4.0).
All three files are shared under CC BY-SA 4.0: anyone may reuse them
under that licence.

The dictionary packs for other caption languages (decision 0035) aren't
in the app: each is downloaded when its language is learned (decision
0122), into `dictionaries` in your data folder, as a separate, unlocked
file with its own `<name>.CREDITS.md` beside it (written by
`tools/dictionaries/packs.py`, carried in the signed list of packs):
Spanish, Russian and Vietnamese from Wiktionary's contributors (CC BY-SA
4.0 and GFDL), as extracted by kaikki.org, with Chinese meanings
(Spanish's and Russian's) from the Chinese edition of Wiktionary; Japanese
from JMdict (EDRDG, CC BY-SA 4.0) and Jonathan Waller's JLPT lists
(CC BY); frequency ranks from wordfreq (CC BY-SA 4.0), and for Russian
also from FrequencyWords' counts of OPUS OpenSubtitles 2018 (Hermit Dave,
CC BY-SA 4.0; the subtitles from http://www.opensubtitles.org/).
Vietnamese's frequency ranks come from OPUS OpenSubtitles v2018 (P.
Lison, J. Tiedemann and M. Kouylekov, LREC 2018; the subtitles from
http://www.opensubtitles.org/): we counted its words, and the pack holds
those counts only, as each word's rank, never a line of the subtitles'
text. OPUS states no licence for that text. Each pack is shared under
CC BY-SA 4.0.

## Everyday talk: FrequencyWords (OpenSubtitles 2018)

`core/lexicon/spoken_ranks.py` holds a rank in speech for about 3,600
Mandarin and 3,600 English words - where the dictionaries' written ranks
place them rarer - made by `tools/spoken_ranks.py` from FrequencyWords'
50,000-word lists (commit 525f9b560de45753a5ea01069454e72e9aa541c6,
`content/2018/zh_cn/zh_cn_50k.txt` and `content/2018/en/en_50k.txt`; the
same source and pin as the Russian pack's ranks). FrequencyWords by Hermit
Dave (https://github.com/hermitdave/FrequencyWords; content CC BY-SA 4.0,
code MIT), word counts from OPUS OpenSubtitles 2018 (P. Lison, J.
Tiedemann and M. Kouylekov, LREC 2018, https://opus.nlpl.eu/), whose
subtitles come from http://www.opensubtitles.org/. The ranks are an
adaptation shared under CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0/).

## Silero VAD

The speech-detection model, `silero_vad_16k_op15.onnx`
(`_internal/polyglotic_desktop/platform/data/` in the installed app), from
<https://github.com/snakers4/silero-vad> at tag v6.2.3.

```
MIT License

Copyright (c) 2020-present Silero Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## The samples: FLEURS

The recordings Home offers when nothing is playing ("Try it on a
sample"), `zh.flac` and `en.flac`
(`_internal/polyglotic_desktop/platform/data/samples/` in the installed
app): four sentences each from FLEURS, by Alexis Conneau, Min Ma, Simran
Khanuja, Yu Zhang, Vera Axelrod, Siddharth Dalmia, Jason Riesa, Clara
Rivera and Ankur Bapna ("FLEURS: Few-shot Learning Evaluation of Universal
Representations of Speech", 2022), <https://huggingface.co/datasets/google/fleurs>,
licensed under the Creative Commons Attribution 4.0 International licence
(CC BY 4.0, <https://creativecommons.org/licenses/by/4.0/>). Changed:
joined with short silences between them and evened in volume
(`tools/samples.py`). Which sentences: `samples/CREDITS.md`.

The sentences read in these recordings are FLEURS's text, which comes from
FLoRes-101 (Naman Goyal et al., "The Flores-101 Evaluation Benchmark for
Low-Resource and Multilingual Machine Translation", 2022),
<https://github.com/facebookresearch/flores>, licensed under the Creative
Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0,
<https://creativecommons.org/licenses/by-sa/4.0/>). The captions and
translations the app shows of them are made live by its models.

## OpenCC's conversion table

"Show Mandarin in: Traditional" converts captions with OpenCC's Simplified
to Traditional dictionaries (STPhrases, STCharacters and TWVariants), from
<https://github.com/BYVoid/OpenCC> at tag ver.1.1.9, copyright BYVoid
(Carbo Kuo) and OpenCC's contributors, under the **Apache License,
version 2.0** (its text: `OpenCC-LICENSE.txt` beside the table, in
`_internal/polyglotic_desktop/adapters/data/` in the installed app).
Changed: the three joined into one table, `zh_traditional.txt.gz`, with each
phrase's first choice in Taiwan's standard forms, and only pairs of Chinese
characters (`tools/traditional_table.py`).
