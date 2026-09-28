# HANDOFF — 2026-09-28 (session 13: deep testing kit, check/stats, eleven fixes)

One page. Facts, not a diary; history is in `docs/history/`.
Audits: [`docs/AUDIT.md`](docs/AUDIT.md) · Kit: [`docs/TESTING_KIT.md`](docs/TESTING_KIT.md) ·
Ideas: [`docs/IDEAS.md`](docs/IDEAS.md).

## Head

- Default branch: `claude/bench-foundation-c015ut` (PR #6 merged, `c03afcb`). Sessions 12 and 13
  are on `claude/handoff-start-004f8n`, **not merged yet**.
- Session 12: `e6a6411` … `fa8bd8b` (audit fixes, sanitize, hash parity, is_ring0, kill race).
- Session 13: `20c89b5` check/stats + six fixes · `8917ce3` deep kit + four fixes ·
  `24673f1` worker dies with a killed supervisor + power-cut sweep · this docs commit.
- `make test`: ROM 64, harness 167 green. `make test-sanitize`: 167 green. `make site-check`:
  49 rows, 39 rules. `make test-deep DEEP=--quick`: all green.
- ROM crown changed (new ROM rows and `test_rom_denylist.py`); `make` rebuilds it.

## New for the owner

- `bench check [--n N] <script|->`: lint without running; `bench stats [<session>]`.
- `make test-deep` (`DEEP=--quick`, `DEEP=--c`), report in `ledger/deep-*/summary.md`.
- `make audit-evidence`: a Python second witness to `bench verify`.
- New rule `line-nul`. `WAIT` is stricter (no `\v`/`\f` lead). The hash no longer skips `*.pyc`
  under `hold/` (the ROM crown is unaffected; a board with `.pyc` in hold/ hashes differently).

## Owner calls

- Carried over: token fallback (`BENCH_TOKEN` set but invalid falls back to the file);
  `BENCH_DURABLE`; the CI billing lock.
- New: hash-chained MANIFESTs and INDEX provenance (IDEAS #3, #7) add fields. Yes or no?
- The PID namespace would close the last custody gap (a worker's daemonized child outliving a
  killed supervisor).

## Next

IDEAS order: hash chain → receipts → `bench try` (+ F5 diff) → digest → WASM parser.
AUDIT: F1 digest cache / tree hash v2, F2 replay --verify.

## Keep in step

- Change a rule or an OPS_TABLE row → `python3 scripts/site-data.py`, commit the JSON.
- Change parse rules in `main.c` → mirror in `docs/assets/js/ops-check.js`; `make site-check`,
  then `python3 tests/deep/fuzz_parse.py` (it replays `tests/deep/corpus/parse/` first).
- Change the tree walk in `sha256.c` → same in `tools/hash.py`; `TestHashParity` and
  `tests/deep/hash_fuzz.py`.
- Add a denylist name in `isa/karpathy_rom.py` → add it to `tests/rom/test_rom_denylist.py`.

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- No trackers, no CDN, no blog; one CI check, compile + ROM + site; the worker suite and the
  deep kit are never on hosted runners.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
