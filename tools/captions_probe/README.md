# Real captions for measuring word links

`zh.txt` and `en.txt`: one sentence per line, the first 100 sentences of
the FLEURS test split's transcripts in Chinese and English - the same
sentences, in the same order, as the coverage probe's other languages
(`tools/dictionaries/probe/`), taken the same way from polyglotic-hq
project 086's `results/mt/zh-en.json` and `en-zh.json` (the `source`
column; whitespace collapsed).

`tools.links_measured` runs them through the caption window's word links
"past what you know" (polyglotic-hq 338). They live apart from the
coverage probe because a change there rebuilds every dictionary pack in
CI.

- FLEURS: Google, https://huggingface.co/datasets/google/fleurs, CC BY 4.0
  (as polyglotic-hq project 086 recorded it); its sentences are
  FLoRes-101's (Meta AI) - see `tools/dictionaries/probe/README.md`.
- Read text, not conversation.
