# Dictionary sense-class coverage

Built on 2026-11-23 from the sources and checksums pinned in the Desktop builder.
Each row counts the final displayed senses in one SQLite pack. Classifier notes are counted separately.

- Wiktionary packs with English glosses have 1,155,768 of 1,170,540 (98.74%) senses with a structured class. The rate across the packs excluding Korean and Malay is 1,100,682 of 1,101,866 (99.89%). Malay includes Indonesian fallback glosses that remain pending. Korean includes pending phrase and replacement glosses and 744 senses reviewed outside the seven classes.
- The Japanese Chinese-gloss variant uses the originating Chinese Wiktionary class when a gloss aligns with a single JMdict headword and reading and the source classes agree. Unresolved glosses remain pending.
- This run had no reviewed project 746 drafts for Mandarin or Cantonese. Their lexical senses remain pending.

Structured senses carry source classes. Verified senses carry classes imported with reviewer and source records. Multi-class is a subset of structured and verified. The denominator is structured plus verified plus reviewed outside the seven classes plus pending.

| SQLite pack | Headword language | Gloss language | Senses | Structured | Verified | Multi-class | Reviewed outside | Pending | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cedict | zh | en | 198,228 | 0 | 0 | 0 | 0 | 198,228 | 1,469 |
| ecdict-en | en | en | 94,393 | 94,393 | 0 | 0 | 0 | 0 | 0 |
| ecdict | en | zh | 81,178 | 60,383 | 0 | 0 | 0 | 20,795 | 0 |
| wiktar | ar | en | 41,987 | 41,935 | 0 | 0 | 34 | 18 | 0 |
| wiktcs | cs | en | 44,276 | 44,269 | 0 | 0 | 0 | 7 | 0 |
| wiktde | de | en | 94,431 | 94,402 | 0 | 0 | 0 | 29 | 0 |
| wiktel | el | en | 18,326 | 18,322 | 0 | 0 | 0 | 4 | 0 |
| wiktes | es | en | 93,054 | 92,944 | 0 | 0 | 36 | 74 | 0 |
| wiktes-zh | es | zh | 80,360 | 78,873 | 0 | 0 | 20 | 1,467 | 0 |
| wiktfa | fa | en | 17,192 | 17,123 | 0 | 0 | 46 | 23 | 0 |
| wiktfr | fr | en | 76,335 | 76,283 | 0 | 0 | 3 | 49 | 0 |
| wikthi | hi | en | 18,821 | 18,817 | 0 | 0 | 2 | 2 | 0 |
| wiktid | id | en | 26,002 | 25,949 | 0 | 0 | 3 | 50 | 0 |
| wiktit | it | en | 109,865 | 109,796 | 0 | 0 | 0 | 69 | 0 |
| jmdict | ja | en | 87,350 | 84,041 | 0 | 4,072 | 0 | 3,309 | 0 |
| jmdict-zh | ja | zh | 91,853 | 49,225 | 0 | 1,441 | 0 | 42,628 | 0 |
| wiktko | ko | en | 48,530 | 44,866 | 0 | 0 | 744 | 2,920 | 0 |
| wiktmk | mk | en | 34,992 | 34,985 | 0 | 0 | 0 | 7 | 0 |
| wiktms | ms | en | 20,144 | 10,220 | 0 | 0 | 4 | 9,920 | 0 |
| wiktnl | nl | en | 63,712 | 63,676 | 0 | 0 | 0 | 36 | 0 |
| wiktpl | pl | en | 94,835 | 94,830 | 0 | 0 | 0 | 5 | 0 |
| wiktpt | pt | en | 71,246 | 71,205 | 0 | 0 | 0 | 41 | 0 |
| wiktro | ro | en | 20,173 | 20,148 | 0 | 0 | 0 | 25 | 0 |
| wiktru | ru | en | 76,973 | 76,957 | 0 | 0 | 7 | 9 | 0 |
| wiktru-zh | ru | zh | 75,774 | 55,985 | 0 | 0 | 7 | 19,782 | 0 |
| wiktsv | sv | en | 58,852 | 58,831 | 0 | 0 | 1 | 20 | 0 |
| wiktth | th | en | 26,158 | 26,067 | 0 | 0 | 0 | 91 | 0 |
| wikttl | tl | en | 21,609 | 21,602 | 0 | 0 | 0 | 7 | 0 |
| wikttr | tr | en | 19,756 | 19,736 | 0 | 0 | 0 | 20 | 0 |
| wiktuk | uk | en | 40,493 | 40,488 | 0 | 0 | 1 | 4 | 0 |
| wiktvi | vi | en | 32,778 | 32,317 | 0 | 0 | 64 | 397 | 0 |
| canto | yue | en | 255,153 | 0 | 0 | 0 | 0 | 255,153 | 1,350 |

## Lookup cards

The UI lab uses controlled entries to exercise sense rendering. The Chinese image illustrates reviewed classes using a fixture.

- [English](lookup-en.png)
- [Japanese](lookup-ja.png)
- [Simplified Chinese](lookup-zh-CN.png)
