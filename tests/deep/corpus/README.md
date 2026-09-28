# Corpus

Seeds the deep tools found. Each file is one input that once made two judges disagree; the
tools replay every seed before generating new inputs, so a fixed bug stays fixed.

- `parse/*.json` — script lines for `fuzz_parse.py`: `line` (the input), `why` (what broke),
  `found` (when, by what). New disagreements are shrunk and written here automatically; commit
  the ones worth keeping, with a `why`.
