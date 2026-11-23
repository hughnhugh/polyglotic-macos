"""The sources the dictionaries are built from, each pinned to one version
by its checksum (decision 0009), and fetching them.

To move a source to a newer version: change its entry here (URL, version,
checksum), run `update_ids` for CC-CEDICT or ECDICT (decision 0007), build,
and commit the pin and the registry together.

Downloads are data, never code: each goes into the sources folder, is
checked against its checksum before anything reads it, and is only ever
parsed (a wheel is opened as a zip archive for its data files).
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

MIT = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy of "
    'this software and associated documentation files (the "Software"), to deal in '
    "the Software without restriction, including without limitation the rights to "
    "use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of "
    "the Software, and to permit persons to whom the Software is furnished to do so, "
    "subject to the following conditions:\n\n"
    "The above copyright notice and this permission notice shall be included in all "
    "copies or substantial portions of the Software.\n\n"
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR '
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS "
    "FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR "
    "COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN "
    "AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION "
    "WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."
)


CC0 = "CC0 1.0"
"""Dedicated to the public domain (no conditions; credited anyway)."""
COUNTS_ONLY = "none stated; word counts only"
"""A source whose text never reaches a file - only word counts made from
it - and whose publisher states no licence (OPUS's OpenSubtitles asks for
a link to opensubtitles.org and a citation; polyglotic-hq 325)."""


@dataclass(frozen=True)
class Source:
    name: str
    title: str
    version: str
    url: str
    sha256: str
    filename: str
    homepage: str
    licence: str  # "CC BY-SA 4.0", "CC BY", "MIT", CC0 or COUNTS_ONLY
    notice: str  # the copyright line or credit the licence asks us to keep
    used_for: str


CEDICT = Source(
    name="cedict",
    title="CC-CEDICT",
    version="2026-09-27T12:50:23Z (125,127 entries)",
    # MDBG publishes only the latest release; the Wayback Machine's copy of
    # it is the pinned, durable one.
    url=(
        "https://web.archive.org/web/20260927184748id_/"
        "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
    ),
    sha256="05bb7cf923fd24cd636a703da2b0172d3b8686c3de28f613ac924e57ea44a95a",
    filename="cedict_1_0_ts_utf-8_mdbg-2026-09-27.txt.gz",
    homepage="https://cc-cedict.org/wiki/",
    licence="CC BY-SA 4.0",
    notice="CC-CEDICT, by MDBG and the CC-CEDICT editors (https://www.mdbg.net/chinese/dictionary?page=cc-cedict)",
    used_for="the Chinese dictionary's entries: words, pinyin and English meanings",
)

JIEBA = Source(
    name="jieba",
    title="jieba dict.txt",
    version="commit 67fa2e36e72f69d9134b8a1037b83fbb070b9775 (2020-02-15)",
    url=(
        "https://raw.githubusercontent.com/fxsjy/jieba/"
        "67fa2e36e72f69d9134b8a1037b83fbb070b9775/jieba/dict.txt"
    ),
    sha256="7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8",
    filename="jieba-dict-67fa2e3.txt",
    homepage="https://github.com/fxsjy/jieba",
    licence="MIT",
    notice="Copyright (c) 2013 Sun Junyi",
    used_for="Chinese word frequencies, as frequency ranks",
)

HSK30 = Source(
    name="hsk30",
    title="hsk30 (Python package; only its data files are read)",
    version="0.2.1 (2026-09-06)",
    url=(
        "https://files.pythonhosted.org/packages/f3/f3/"
        "dcc5dcd4cb902582b5e770164443dc9ae6985dcad0e0d58db56cb195dee6/"
        "hsk30-0.2.1-py3-none-any.whl"
    ),
    sha256="0a6973d37dc934a37ff0dea50982de0e597505e04fe264cb43c9bae30d7dd166",
    filename="hsk30-0.2.1-py3-none-any.whl",
    homepage="https://github.com/harukicoder/hsk30",
    licence="MIT",
    notice=(
        "Copyright (c) 2026 Alvaro Serrano. Its word lists are transcriptions of "
        "ivankra/hsk30 (MIT) and drkameleon/complete-hsk-vocabulary (MIT)"
    ),
    used_for=(
        "HSK 3.0 levels: the 2025 exam syllabus (hsk-2025) and the 2021 standard "
        "GF0025-2021 (hsk-2021)"
    ),
)

ECDICT = Source(
    name="ecdict",
    title="ECDICT",
    version="commit 39cfb9672c0906b63569e0453c2e6abfb9ab182a (2026-11-02), ecdict.csv",
    url=(
        "https://raw.githubusercontent.com/skywind3000/ECDICT/"
        "39cfb9672c0906b63569e0453c2e6abfb9ab182a/ecdict.csv"
    ),
    sha256="d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc",
    filename="ecdict-39cfb96.csv",
    homepage="https://github.com/skywind3000/ECDICT",
    licence="MIT",
    notice="Copyright (c) 2025 Linwei",
    used_for=(
        "the English dictionary's entries: words, IPA, Chinese meanings, inflections "
        "and frequency ranks; cut to the commonest words, without its collins and "
        "oxford columns"
    ),
)

WORDFREQ = Source(
    name="wordfreq",
    title="wordfreq (Python package; only its English data file is read)",
    version="3.1.1 (2023-11-21), wordfreq/data/large_en.msgpack.gz",
    url=(
        "https://files.pythonhosted.org/packages/24/61/"
        "62835c475d69872d30689f284497853fe33fe1d6dd18f57346d13305861d/"
        "wordfreq-3.1.1-py3-none-any.whl"
    ),
    sha256="4b1c6ecffc6198be3396d5cf871c4423ca71c907c231348d352dd54d62b97473",
    filename="wordfreq-3.1.1-py3-none-any.whl",
    homepage="https://github.com/rspeer/wordfreq",
    licence="CC BY-SA 4.0",
    notice=(
        "wordfreq by Robyn Speer (data CC BY-SA 4.0; code Apache-2.0), "
        "https://doi.org/10.5281/zenodo.7199437. It contains data from the SUBTLEX "
        "word lists by Marc Brysbaert et al. - SUBTLEX is freely available data, "
        "http://crr.ugent.be/programs-data/subtitle-frequencies; from Google Books "
        "Ngram Viewer, http://books.google.com/ngrams; from OPUS OpenSubtitles 2018, "
        "originally the OpenSubtitles project, http://www.opensubtitles.org/; and "
        "from the Leeds Internet Corpus, Wikipedia and ParaCrawl"
    ),
    used_for="English frequency ranks, per entry with its inflected forms",
)

WORDNET_LICENCE = (
    "WordNet 3.1 Copyright 2011 by Princeton University. All rights reserved.\n\n"
    "Permission to use, copy, modify and distribute this software and database and "
    "its documentation for any purpose and without fee or royalty is hereby granted, "
    "provided that you agree to comply with the following copyright notice and "
    "statements, including the disclaimer, and that the same appear on ALL copies of "
    "the software, database and documentation, including modifications that you make "
    "for internal use or for distribution.\n\n"
    'THIS SOFTWARE AND DATABASE IS PROVIDED "AS IS" AND PRINCETON UNIVERSITY MAKES NO '
    "REPRESENTATIONS OR WARRANTIES, EXPRESS OR IMPLIED. BY WAY OF EXAMPLE, BUT NOT "
    "LIMITATION, PRINCETON UNIVERSITY MAKES NO REPRESENTATIONS OR WARRANTIES OF "
    "MERCHANTABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF THE "
    "LICENSED SOFTWARE, DATABASE OR DOCUMENTATION WILL NOT INFRINGE ANY THIRD PARTY "
    "PATENTS, COPYRIGHTS, TRADEMARKS OR OTHER RIGHTS.\n\n"
    "The name of Princeton University or Princeton may not be used in advertising or "
    "publicity pertaining to distribution of the software and/or database. Title to "
    "copyright in this software, database and any associated documentation shall at "
    "all times remain with Princeton University and LICENSEE agrees to preserve same."
)
"""Princeton WordNet's licence, which Open English WordNet's underlying data
keeps (its WNDB_License.txt): its notice goes with every copy."""

OEWN = Source(
    name="oewn",
    title="Open English WordNet (the 2025+ edition, with names and places)",
    version="2025 edition (2025-12-31), english-wordnet-2025-plus.xml.gz",
    url=(
        "https://github.com/globalwordnet/english-wordnet/releases/download/"
        "2025-edition/english-wordnet-2025-plus.xml.gz"
    ),
    sha256="31f4af16c54b532fd5484d4cc33aee588a31bb5b70683ae8197842fde5b586bc",
    filename="english-wordnet-2025-plus.xml.gz",
    homepage="https://en-word.net",
    licence="CC BY 4.0",
    notice=(
        "Copyright (c) 2019-present, The Open English WordNet Team "
        "(https://github.com/globalwordnet/english-wordnet). Derived from "
        "Princeton WordNet under the WordNet License (below)"
    ),
    used_for=(
        "the English dictionary's English meanings (ecdict-en.sqlite): definitions, "
        "parts of speech and examples, shortened at their first semicolon"
    ),
)

CMUDICT = Source(
    name="cmudict",
    title="The CMU Pronouncing Dictionary (CMUdict)",
    version="commit 74790861f652b15e4ac49015a90074ad62a27690 (2025-10-24), cmudict.dict",
    url=(
        "https://raw.githubusercontent.com/cmusphinx/cmudict/"
        "74790861f652b15e4ac49015a90074ad62a27690/cmudict.dict"
    ),
    sha256="81917843c7f44ce2b094ac63873c2c7a4cf802040792c455ba3ca406891c3d22",
    filename="cmudict-7479086.dict",
    homepage="https://github.com/cmusphinx/cmudict",
    licence="BSD 2-clause style (CMUdict's own; its text is in the credits)",
    notice="Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved",
    used_for=(
        "the English dictionary's respellings (KAY-oss) of the commonest words, "
        "for the reading line over English: each word's American sounds and stress"
    ),
)
"""`respell` reads it (polyglotic-hq 471), for the English dictionary's
respellings (511)."""

SOURCES = (CEDICT, JIEBA, HSK30, ECDICT, WORDFREQ, OEWN, CMUDICT)


# -- the basic packs (polyglotic-hq project 164; nothing ships with the app) --
# kaikki.org rewrites its files in place at each extraction and marks the
# per-language ones "deprecated, to be removed": these pins break loudly
# (ChecksumError) when that happens. Our own copies (R2) are to come.

WIKTIONARY_NOTICE = (
    "Wiktionary's contributors (https://en.wiktionary.org; each page's history "
    "names them), CC BY-SA 4.0 and GFDL (Wikimedia Terms of Use, section 7); "
    "extracted by kaikki.org with wiktextract (Tatu Ylonen, "
    "https://github.com/tatuylonen/wiktextract)"
)

KAIKKI_ES = Source(
    name="kaikki-es",
    title="Wiktionary (English edition): Spanish, as extracted by kaikki.org",
    version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
    url="https://kaikki.org/dictionary/Spanish/kaikki.org-dictionary-Spanish.jsonl.gz",
    sha256="b25cd18584e510c516e4c9afac42a87e5acfd6bc1a13ea96a94057899521a427",
    filename="kaikki-Spanish-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/Spanish/",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE,
    used_for="the Spanish dictionary: words, English meanings, IPA, inflections",
)

KAIKKI_FR = Source(
    name="kaikki-fr",
    title="Wiktionary (English edition): French, as extracted by kaikki.org",
    version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
    url="https://kaikki.org/dictionary/French/kaikki.org-dictionary-French.jsonl.gz",
    sha256="224fce45865bad43c4f43f11d0f6fc84e044ffda8407c549609639cfc7d38cc7",
    filename="kaikki-French-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/French/",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE,
    used_for=("the French dictionary: words, English meanings, IPA, inflected forms"),
)


def kaikki_source(code: str, language: str, sha256: str) -> Source:
    """A language's Wiktionary as kaikki.org extracted it on 2026-10-30 (the
    extract the other packs pin), for `packs.wiktionary_pack`
    (polyglotic-hq 380)."""
    return Source(
        name=f"kaikki-{code}",
        title=f"Wiktionary (English edition): {language}, as extracted by kaikki.org",
        version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
        url=(
            f"https://kaikki.org/dictionary/{language}/"
            f"kaikki.org-dictionary-{language}.jsonl.gz"
        ),
        sha256=sha256,
        filename=f"kaikki-{language}-20261030.jsonl.gz",
        homepage=f"https://kaikki.org/dictionary/{language}/",
        licence="CC BY-SA 4.0",
        notice=WIKTIONARY_NOTICE,
        used_for=(
            f"the {language} dictionary: words, English meanings, readings, "
            "inflected forms"
        ),
    )


KAIKKI_DE = kaikki_source(
    "de", "German", "e16ea346863a1d0bc9e0533f83015b3847ec8b0a065ad2620b76a19bb005b520"
)
KAIKKI_PT = kaikki_source(
    "pt",
    "Portuguese",
    "0db87ddd508032c4e986fe818826801c9b167b2ee4f8315763166f0fa4014480",
)
KAIKKI_IT = kaikki_source(
    "it", "Italian", "edfb787898b80c6ed20db5601741c8d42ad6f59c1c618e396ab34c702a448b63"
)
KAIKKI_ID = kaikki_source(
    "id",
    "Indonesian",
    "b4dbd2267b7f60e7d28ae6acc4d470bc055ca27e039646f9ec278759fe386443",
)
KAIKKI_AR = kaikki_source(
    "ar", "Arabic", "b833fc5017d51a7ef1edf428272067b112281d9a79150d1f2ac7646b178065a3"
)
KAIKKI_HI = kaikki_source(
    "hi", "Hindi", "e60b373dbec502cbbd916e286b6156f582bb5cab85e279d8f0c09a763331e0e7"
)
KAIKKI_PL = kaikki_source(
    "pl", "Polish", "c620e7fc1fe4287720cbb72939e5fa0e4cd95797c1719a5c480b16de5d959bd0"
)
KAIKKI_MS = kaikki_source(
    "ms", "Malay", "d456a0d525f5d264883e585d21cee5b9f9414a6968db8e8830f5329340ca490e"
)
KAIKKI_TR = kaikki_source(
    "tr", "Turkish", "ccaa8909f6f6ad3403d5891cbbd94799b56c67176d18967502f20baa29a6cb32"
)
# the second batch paired with English (polyglotic-hq 387)
KAIKKI_NL = kaikki_source(
    "nl", "Dutch", "17499b37f390857aa36aa59cff7370d09158db15b3c09ee2dc9e8d7790c4eb4d"
)
KAIKKI_UK = kaikki_source(
    "uk",
    "Ukrainian",
    "2b8074025c192314a3906b6bb33587ff1c97f06b398f422308001561124b9586",
)
KAIKKI_FA = kaikki_source(
    "fa", "Persian", "d425896d1963647622358dd309ab0cc6dbbc557301421f505b8a8232d82454b5"
)
KAIKKI_SV = kaikki_source(
    "sv", "Swedish", "b9c5b0f7dfe4f4895582449c5970c0efaa232f9861f5fe3527012555a234ae91"
)
KAIKKI_CS = kaikki_source(
    "cs",
    "Czech",
    "059a3ce05418761b751f22d588b58b46adc927d8dbccb50cc53cb9962b6b0037",
)
KAIKKI_RO = kaikki_source(
    "ro",
    "Romanian",
    "820a084160beef8856a268ebdc9488ba2a7f2c1aa62d18fb9484a006f0c0b652",
)
KAIKKI_EL = kaikki_source(
    "el",
    "Greek",
    "cbf73c15005e143c496dc46c155a593e8d59880ef2059761d26e89fe2f96ff25",
)
KAIKKI_TL = kaikki_source(
    "tl",
    "Tagalog",
    "9c4bd39ae1876a324abb37a7848240a192e04cb8b4d657dc7c5748b1f98f7b94",
)
KAIKKI_MK = kaikki_source(
    "mk",
    "Macedonian",
    "0568e00d91bb122d07d123fa35dd41302448ca5781b3dfe3591abb63d5648efc",
)

KAIKKI_KO = kaikki_source(
    "ko", "Korean", "2bf0aeac466458f2621e0ecfdd72b7b5b00a90c0e775443d55d369d6dab5ea83"
)
KAIKKI_TH = kaikki_source(
    "th", "Thai", "fcd83d053ccc7856192ba785fe8be00eaf9b8e50ff1efbc97b2a8758a34f2c2c"
)

COMMON_VOICE_COMMIT = "4ace1f340535029c89d99d77b3af2fdd794f268916"
"""common-voice/common-voice's main of 2026-11-15, as polyglotic-hq 374
read it."""
COMMONVOICE_TH = Source(
    name="commonvoice-th",
    title="Common Voice: Thai sentences (Sentence Collector)",
    version=f"commit {COMMON_VOICE_COMMIT[:12]} (2026-11-15; 62,875 sentences)",
    url=(
        "https://raw.githubusercontent.com/common-voice/common-voice/"
        f"{COMMON_VOICE_COMMIT}/server/data/th/sentence-collector.txt"
    ),
    sha256="9fbd58d33edd6da3ccf631b21fe6d7a48b1d7c8bfab5b0acdfbac9f0ab7b01ab",
    filename=f"commonvoice-th-sentence-collector-{COMMON_VOICE_COMMIT}.txt",
    homepage="https://github.com/common-voice/common-voice",
    licence=CC0,
    notice=(
        "Common Voice's Thai sentences, from the Common Voice community's "
        "Sentence Collector (Mozilla Foundation), released under CC0"
    ),
    used_for=(
        "Thai frequency ranks: its words counted by the app's word split (the "
        "sentences' text is not in the pack)"
    ),
)

KAIKKI_RU = Source(
    name="kaikki-ru",
    title="Wiktionary (English edition): Russian, as extracted by kaikki.org",
    version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
    url="https://kaikki.org/dictionary/Russian/kaikki.org-dictionary-Russian.jsonl.gz",
    sha256="86a781a5685d614efd439e326eed0bf0ad9cda9f67b854f8b6c93212c5345b3e",
    filename="kaikki-Russian-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/Russian/",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE,
    used_for=(
        "the Russian dictionary: words, English meanings, stress marks, inflections"
    ),
)

KAIKKI_VI = Source(
    name="kaikki-vi",
    title="Wiktionary (English edition): Vietnamese, as extracted by kaikki.org",
    version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
    url=(
        "https://kaikki.org/dictionary/Vietnamese/"
        "kaikki.org-dictionary-Vietnamese.jsonl.gz"
    ),
    sha256="6adcb83f6a00e17ee2f3f658f7da61e38fd90ceabaa8a5f9bd4d2500cc40d309",
    filename="kaikki-Vietnamese-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/Vietnamese/",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE,
    used_for=(
        "the Vietnamese dictionary: words of one or more syllables, English "
        "meanings, IPA, other spellings"
    ),
)

COMMONVOICE_COMMIT = "4ace1f340535029c89d99d77b3af2fdd794f2689"
"""Common Voice's repository as polyglotic-hq 374 measured it (2026-11-15)."""
COMMONVOICE_FA = Source(
    name="commonvoice-fa",
    title="Common Voice: Persian sentences (Sentence Collector)",
    version=f"commit {COMMONVOICE_COMMIT[:10]} of 2026-11-15; 44,097 sentences",
    url=(
        "https://raw.githubusercontent.com/common-voice/common-voice/"
        f"{COMMONVOICE_COMMIT}/server/data/fa/sentence-collector.txt"
    ),
    sha256="b5dec2955e266875071c3c48e2dcb4bc8232b593fe1ef8c5fd1d1da29b57d571",
    filename=f"commonvoice-fa-{COMMONVOICE_COMMIT}.txt",
    homepage="https://github.com/common-voice/common-voice",
    licence=CC0,
    notice=(
        "Sentences written for Mozilla Common Voice through its Sentence "
        "Collector, released under CC0 (the repository's README, \"Licensing "
        'and content source")'
    ),
    used_for=(
        "the Persian pack's ranks: its words counted, beside wordfreq's "
        "(polyglotic-hq 374: better than wordfreq alone in Persian)"
    ),
)

OPENSUBTITLES_VI = Source(
    name="opensubtitles-vi",
    title="OPUS OpenSubtitles v2018: Vietnamese (monolingual text)",
    version="v2018 (file of 2018-11-17; 5.1 million lines, 34 million syllables)",
    url="https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2018/mono/vi.txt.gz",
    sha256="1aae9970414129b76a4be17dd55f0b9ec6156c1ca0d7a6ec4bee852f453ae2a1",
    filename="opensubtitles-v2018-vi.txt.gz",
    homepage="https://opus.nlpl.eu/",
    licence=COUNTS_ONLY,
    notice=(
        "OPUS OpenSubtitles v2018 (P. Lison, J. Tiedemann and M. Kouylekov, "
        "OpenSubtitles2018: Statistical Rescoring of Sentence Alignments in "
        "Large, Noisy Parallel Corpora, LREC 2018), from the subtitles of "
        "http://www.opensubtitles.org/"
    ),
    used_for=(
        "Vietnamese frequency ranks: its words counted (the subtitles' text "
        "is not in the pack)"
    ),
)

KAIKKI_ZH = Source(
    name="kaikki-zh",
    title="Wiktionary (Chinese edition), as extracted by kaikki.org",
    version="extracted 2026-10-30 (zh-extract.jsonl.gz)",
    url="https://kaikki.org/dictionary/downloads/zh/zh-extract.jsonl.gz",
    sha256="30f175aa641b204c43755e942a6e97d38cf5e93d7815ce1e2475e68c068b82c0",
    filename="kaikki-zh-extract-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/rawdata.html",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE.replace("en.wiktionary.org", "zh.wiktionary.org"),
    used_for=(
        "Chinese meanings of Spanish, Japanese and Russian words, for Chinese speakers"
    ),
)


KAIKKI_EN = Source(
    name="kaikki-en",
    title="Wiktionary (English edition): English, as extracted by kaikki.org",
    version="extracted 2026-10-30 from the enwiktionary dump of 2026-10-01",
    url="https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz",
    sha256="4d03b6cba283744756c57ff661c2c6cbfe34fcf8ff513a966576cf7d97e91a99",
    filename="kaikki-English-20261030.jsonl.gz",
    homepage="https://kaikki.org/dictionary/English/",
    licence="CC BY-SA 4.0",
    notice=WIKTIONARY_NOTICE,
    used_for=("English words' meanings in learners' languages: the translation tables"),
)


def edition_source(code: str, language: str, sha256: str) -> Source:
    """A language's own Wiktionary as kaikki.org extracted it on 2026-10-30:
    its English words, defined in that language (`english_pairs`;
    polyglotic-hq 510)."""
    return Source(
        name=f"kaikki-{code}-edition",
        title=f"Wiktionary ({language} edition), as extracted by kaikki.org",
        version=f"extracted 2026-10-30 ({code}-extract.jsonl.gz)",
        url=f"https://kaikki.org/dictionary/downloads/{code}/{code}-extract.jsonl.gz",
        sha256=sha256,
        filename=f"kaikki-{code}-extract-20261030.jsonl.gz",
        homepage="https://kaikki.org/dictionary/rawdata.html",
        licence="CC BY-SA 4.0",
        notice=WIKTIONARY_NOTICE.replace("en.wiktionary.org", f"{code}.wiktionary.org"),
        used_for=f"English words' meanings in {language}",
    )


WIKTIONARY_EDITIONS = {
    "es": edition_source(
        "es",
        "Spanish",
        "0a7a02456ecf34dd3419e0d5adf4f18da5531487dde31829d126afe86eade861",
    ),
    "pt": edition_source(
        "pt",
        "Portuguese",
        "26b244e5b25629e9a88cf926813e6987289fa61e8b8a2faa68aef78ed6efaaa6",
    ),
    "ja": edition_source(
        "ja",
        "Japanese",
        "cf8d3f8e35b87d9c94fe61baa0dd9bf5abbe84a2bc4b656c9465a15538c3394d",
    ),
    "ko": edition_source(
        "ko",
        "Korean",
        "7ce75eec9ac9d198a510eb9db57e1831810bba941099d3580ae59a7b026aaec1",
    ),
    "vi": edition_source(
        "vi",
        "Vietnamese",
        "f2139c262f45cbe32dbc8e7478369fbc936ff6640deec0d2b6e7ad647d58f273",
    ),
    "id": edition_source(
        "id",
        "Indonesian",
        "0c54402893e77610fa7a757cb5c56d0d1134047c0123079f84cee0f8d285dbc6",
    ),
    "tr": edition_source(
        "tr",
        "Turkish",
        "09bc9e87b010dcee5e22c48ae1f8379cef3e4fefaefbb7c8e5453b8c0ea88f6d",
    ),
    "ru": edition_source(
        "ru",
        "Russian",
        "fdcb978c76b660e0e43977bbf7487c812e6d42e965b0a73e3f5b4ba6981174c4",
    ),
    "fr": edition_source(
        "fr",
        "French",
        "61d27bfc4bef9eb8f19d6e280ebf310adb07196da41d2f5777ff5942bef66a28",
    ),
    "de": edition_source(
        "de",
        "German",
        "39ea559834e4cbcd2f1cc686037fc6ddc4590f29af94fd143292146ad9bf24c5",
    ),
    "it": edition_source(
        "it",
        "Italian",
        "9f35d5ac30f2fbab4774eb3e81ec6394806bd2723f802b405e7e9901185d5229",
    ),
    "th": edition_source(
        "th",
        "Thai",
        "62dba8c33491dcd78a37f0f3c34fbb4ffa2f5a79afbfb4fdc45a226dd73a13e9",
    ),
    "pl": edition_source(
        "pl",
        "Polish",
        "c76fa8c844231ab2d27b79a88eb105b19ed6e873b2fdbc54826713fd8353db2c",
    ),
    "nl": edition_source(
        "nl",
        "Dutch",
        "6eee5015514661292f5915c6c2fcc7da7ebff32714dd704217ea28ae37650801",
    ),
    "cs": edition_source(
        "cs",
        "Czech",
        "bb7bde6f575d081ae8d3d19e68e8975c541b9102822c7651af401f0b04f98bb8",
    ),
    "ms": edition_source(
        "ms",
        "Malay",
        "ecd4789b6518067369b51ae97ddaa39f6db1d70dd2956d13f9454d164082c64c",
    ),
}
"""Each language whose own Wiktionary kaikki.org extracts (none for Hindi,
Ukrainian or Filipino), for English's meanings in it."""

FREQUENCYWORDS_RU = Source(
    name="frequencywords-ru",
    title="FrequencyWords: Russian, OpenSubtitles 2018 (the 50,000 commonest words)",
    version="commit 525f9b560de45753a5ea01069454e72e9aa541c6 (2022-02-07), "
    "content/2018/ru/ru_50k.txt",
    url=(
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
        "525f9b560de45753a5ea01069454e72e9aa541c6/content/2018/ru/ru_50k.txt"
    ),
    sha256="6095f507cc167488ec66ada5a85ac50433503a08ad24a07c6eabdf54352c4e7f",
    filename="frequencywords-ru_50k-525f9b5.txt",
    homepage="https://github.com/hermitdave/FrequencyWords",
    licence="CC BY-SA 4.0",
    notice=(
        "FrequencyWords by Hermit Dave (content CC BY-SA 4.0; code MIT), word "
        "counts from OPUS OpenSubtitles 2018 (P. Lison, J. Tiedemann and M. "
        "Kouylekov, LREC 2018, https://opus.nlpl.eu/), whose subtitles come from "
        "http://www.opensubtitles.org/"
    ),
    used_for=(
        "Russian frequency ranks as spoken in films and series, averaged with "
        "wordfreq's"
    ),
)

JMDICT = Source(
    name="jmdict",
    title="JMdict (English glosses), as jmdict-simplified JSON",
    version="jmdict-simplified 3.6.2+20261102210542 (JMdict of 2026-11-02)",
    url=(
        "https://github.com/scriptin/jmdict-simplified/releases/download/"
        "3.6.2%2B20261102210542/jmdict-eng-3.6.2%2B20261102210542.json.zip"
    ),
    sha256="851791d3cc98a29ca7e4f65532966cdee637a1bc218cf1c99b4895b780edb101",
    filename="jmdict-eng-3.6.2+20261102210542.json.zip",
    homepage="https://www.edrdg.org/jmdict/j_jmdict.html",
    licence="CC BY-SA 4.0",
    notice=(
        "JMdict, the property of the Electronic Dictionary Research and "
        "Development Group (EDRDG), used in conformance with the Group's licence "
        "(https://www.edrdg.org/edrdg/licence.html); converted to JSON by "
        "jmdict-simplified (https://github.com/scriptin/jmdict-simplified)"
    ),
    used_for="the Japanese dictionary: words, readings, English meanings",
)

JLPT = Source(
    name="jlpt",
    title="JLPT vocabulary lists (unofficial), by Jonathan Waller, as CSV",
    version="Bluskyo/JLPT_Vocabulary commit 4358f932937ad0232194a36e9f4f875094910c6b (2026-07-15)",
    url=(
        "https://raw.githubusercontent.com/Bluskyo/JLPT_Vocabulary/"
        "4358f932937ad0232194a36e9f4f875094910c6b/data/vocab/results/JLPT_vocab_ALL.csv"
    ),
    sha256="810c776c7a72fe9a6860d8629e7f4d3903545808e6cbcff8dde3b52b01800f24",
    filename="JLPT_vocab_ALL-4358f93.csv",
    homepage="https://www.tanos.co.uk/jlpt/",
    licence="CC BY",
    notice=(
        "JLPT word lists by Jonathan Waller (tanos.co.uk), Creative Commons BY; "
        "unofficial - no official list exists since 2010; converted to CSV by "
        "Bluskyo (https://github.com/Bluskyo/JLPT_Vocabulary, MIT)"
    ),
    used_for="Japanese levels N5-N1 (unofficial)",
)

# -- Cantonese (polyglotic-hq 371 and 450; decision 0160) ------------------------

CC_CANTO = Source(
    name="cc-canto",
    title="CC-Canto",
    version="2017-02-02 (34,335 lines)",
    # cantonese.org publishes only this release; the Wayback Machine's copy
    # of it is the pinned, durable one (the same bytes, 2026-11-17)
    url=(
        "https://web.archive.org/web/20220122063705id_/"
        "https://cantonese.org/cccanto-170202.zip"
    ),
    sha256="0cc9e600a19c02405064d6d227d96563c09da1a0af1c7717508c0f231028af27",
    filename="cccanto-170202.zip",
    homepage="https://cantonese.org/",
    licence="CC BY-SA 3.0",
    notice="CC-Canto, Copyright (c) 2015-17 Pleco Inc (cantonese.org)",
    used_for="Cantonese words with their Jyutping and English meanings",
)

CANTO_READINGS = Source(
    name="canto-readings",
    title="Cantonese readings for CC-CEDICT",
    version="2015-09-23",
    url=(
        "https://web.archive.org/web/20251203213516id_/"
        "https://cantonese.org/cccedict-canto-readings-150923.zip"
    ),
    sha256="f6d99991791f49aaf96d97b2838a3ba9e057e060a5a9e24311cf851f8f71a950",
    filename="cccedict-canto-readings-150923.zip",
    homepage="https://cantonese.org/",
    licence="CC BY-SA 3.0",
    notice=(
        "Cantonese readings for CC-CEDICT, Copyright (c) 2015 Pleco Inc (cantonese.org)"
    ),
    used_for="the Jyutping of CC-CEDICT's entries",
)

CEDICT_FOR_CANTONESE = replace(
    CEDICT,
    used_for=(
        "the English meanings of Chinese words read in Cantonese, after CC-Canto's own"
    ),
)

RIME_CANTONESE_COMMIT = "259f0e48bba840c3a2e0d117539e96937f3d89bc"
"""rime/rime-cantonese's main of 2026-08-13, as polyglotic-hq 450 read it."""
_RIME_NOTICE = (
    "rime-cantonese (jyut6ping3), by the Cantonese Computational Linguistics "
    "Infrastructure Development Workgroup (CanCLID) and its contributors"
)
RIME_WORDS = Source(
    name="rime-words",
    title="rime-cantonese: word readings (jyut6ping3.words.dict.yaml)",
    version=f"commit {RIME_CANTONESE_COMMIT[:12]} (2026-08-13; 103,077 lines)",
    url=(
        "https://raw.githubusercontent.com/rime/rime-cantonese/"
        f"{RIME_CANTONESE_COMMIT}/jyut6ping3.words.dict.yaml"
    ),
    sha256="54d174ad2bb997e4a678b7b076b84e4dc5914481b32467cdea3b43e88b7d5474",
    filename=f"jyut6ping3.words-{RIME_CANTONESE_COMMIT[:12]}.dict.yaml",
    homepage="https://github.com/rime/rime-cantonese",
    licence="CC BY 4.0",
    notice=_RIME_NOTICE,
    used_for=(
        "each word's everyday Jyutping: which of a word's entries comes first, "
        "and a reading for an entry that has none"
    ),
)
RIME_CHARS = Source(
    name="rime-chars",
    title="rime-cantonese: character readings (jyut6ping3.chars.dict.yaml)",
    version=f"commit {RIME_CANTONESE_COMMIT[:12]} (2026-08-13)",
    url=(
        "https://raw.githubusercontent.com/rime/rime-cantonese/"
        f"{RIME_CANTONESE_COMMIT}/jyut6ping3.chars.dict.yaml"
    ),
    sha256="9b053a594c80eae76545bcdd83239884a49b1ba48b89ca0ab9e8daac79f33013",
    filename=f"jyut6ping3.chars-{RIME_CANTONESE_COMMIT[:12]}.dict.yaml",
    homepage="https://github.com/rime/rime-cantonese",
    licence="CC BY 4.0",
    notice=_RIME_NOTICE,
    used_for="each character's everyday Jyutping, by its weight",
)

HKCANCOR = Source(
    name="hkcancor",
    title="Hong Kong Cantonese Corpus (HKCanCor)",
    version=(
        "fcbond/hkcancor commit 39aeadf920e0 (2025-11-03), data/hkcancor-utf8.zip "
        "(128,205 words in Chinese characters, of conversation and radio, 1997-98)"
    ),
    url=(
        "https://raw.githubusercontent.com/fcbond/hkcancor/"
        "39aeadf920e0b5ca93d0ad7792c59e740e7bdd65/data/hkcancor-utf8.zip"
    ),
    sha256="09223963b8756254e15353cad843f8a4b0cbc4b9223dc8a8fa27fb1cf846057e",
    filename="hkcancor-utf8-39aeadf.zip",
    homepage="https://github.com/fcbond/hkcancor",
    licence="CC BY 4.0",
    notice=(
        "Hong Kong Cantonese Corpus, by K. K. Luke and May L. Y. Wong. "
        "Only word counts made from it are in the pack, as frequency ranks"
    ),
    used_for=(
        "Cantonese frequency ranks: its words as spoken (its own word split), "
        "averaged with wordfreq's written Chinese"
    ),
)

WORDFREQ_ZH = replace(
    WORDFREQ,
    title="wordfreq (Python package; only its Chinese data file is read)",
    version="3.1.1 (2023-11-21), wordfreq/data/large_zh.msgpack.gz",
    used_for=(
        "Cantonese frequency ranks: written Chinese's word frequencies, by each "
        "word's Simplified form, averaged with HKCanCor's"
    ),
)

PACK_SOURCES = (
    KAIKKI_ES,
    KAIKKI_FR,
    KAIKKI_DE,
    KAIKKI_PT,
    KAIKKI_IT,
    KAIKKI_ID,
    KAIKKI_AR,
    KAIKKI_HI,
    KAIKKI_PL,
    KAIKKI_TR,
    KAIKKI_MS,
    KAIKKI_NL,
    KAIKKI_UK,
    KAIKKI_FA,
    KAIKKI_SV,
    KAIKKI_CS,
    KAIKKI_RO,
    KAIKKI_EL,
    KAIKKI_TL,
    KAIKKI_MK,
    KAIKKI_TH,
    KAIKKI_RU,
    KAIKKI_VI,
    KAIKKI_ZH,
    OPENSUBTITLES_VI,
    COMMONVOICE_FA,
    COMMONVOICE_TH,
    FREQUENCYWORDS_RU,
    JMDICT,
    JLPT,
    WORDFREQ,
    CC_CANTO,
    CANTO_READINGS,
    RIME_WORDS,
    RIME_CHARS,
    HKCANCOR,
)


class ChecksumError(Exception):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(source: Source, folder: Path) -> Path:
    """The source's file in `folder`, downloaded if it isn't there already,
    and checked against its pinned checksum either way."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / source.filename
    if not path.exists():
        part = path.with_name(path.name + ".part")
        request = urllib.request.Request(
            source.url, headers={"User-Agent": "polyglotic-build"}
        )
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            part.open("wb") as out,
        ):
            while block := response.read(1 << 20):
                out.write(block)
        part.replace(path)
    actual = sha256_of(path)
    if actual != source.sha256:
        bad = path.with_name(path.name + ".bad")
        path.replace(bad)
        raise ChecksumError(
            f"{source.name}: checksum {actual} isn't the pinned {source.sha256}; "
            f"moved aside to {bad.name}"
        )
    return path
