# docs/research/ — the 2026-09-28 harness audit, raw

Raw material behind the Bench-vs-harnesses comparison. No third-party code is committed here: the
22 repos are pinned by commit and re-fetched on demand (~2.8 GB; several pack files exceed GitHub's
100 MB push limit, and nested `.git` dirs would commit as empty gitlinks).

| File | What |
|---|---|
| `repos.tsv` | name, URL, exact commit SHA, commit date, license for all 22 repos |
| `fetch.sh` | re-fetches every repo (or a subset) at its pinned SHA into `clones/` (gitignored) |
| `loc.py` / `loc.txt` | source/test line counts per repo, and the captured output of the audit run |
| `evidence.sh` / `evidence.txt` | file:line references behind each ranked idea, and the captured output |
| `sources.md` | papers, docs and incident reports that were checked during the audit |

```
sh docs/research/fetch.sh                 # all 22, or: sh docs/research/fetch.sh codex omnigent
python3 docs/research/loc.py              # recount
sh docs/research/evidence.sh              # re-derive the references
```

Licenses: all 22 are MIT, Apache-2.0 or BSD (see `repos.tsv`). Nothing is redistributed; only
URLs and hashes are stored.
