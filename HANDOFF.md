# HANDOFF — 2026-09-28 (session 12: audit, fixes, feature list)

One page. Facts, not a diary; history is in `docs/history/`. The full audit is
[`docs/AUDIT.md`](docs/AUDIT.md).

## Head

- Default branch (product tip): `claude/bench-foundation-c015ut` (PR #6 merged, `c03afcb`).
- This session's branch: `claude/handoff-start-004f8n`, from `c03afcb`, pushed:
  `e6a6411` audit fixes (subreaper + strays, UB, truncation, mailbox budget) · `0fdd54e`
  `make test-sanitize` · `0db6a0f` hash.py parity · `491c69c` is_ring0 bypasses · `e5e7fea` peek.py ·
  `89dd583` hash_one_file hardening · `0fe07a9` kill reaches a starting run · this file + AUDIT + reference.
- No `sandbox.c`, `spec/` or worker-policy change. No new verb.
- `make test`: bus ok, ROM 55, harness 152 green. `make test-sanitize` (ASan+UBSan): 152 green.
  `make site-check`: green. ROM crown and `tools/hash.py` agree.

## What changed in behaviour

- **No worker outlives its frame.** bench is a child subreaper; tools run in their own process
  group; strays are killed and reaped at frame end (`strays=N` in evidence).
- **`bench kill`** signals a lock holder that is still starting (was: marked the previous session).
- Tree hash opens files `O_NOFOLLOW|O_NONBLOCK` (a FIFO in `hold/` no longer hangs it).
- `is_ring0` closes 5 import bypasses — ROM crown value changed (rebuilt by `make`).

## Owner calls (from the audit)

- Token fallback: a set-but-invalid `BENCH_TOKEN` silently falls back to `sessions/OWNER_TOKEN`.
  Recommend: env token set → use only it.
- `BENCH_DURABLE=1` (fsync on MANIFEST/STATE/CURRENT): add, and default on or off?
- CI: account billing lock still blocks Actions (Settings → Billing and plans).

## Next (feature list in AUDIT.md)

F1 digest cache / tree hash v2 → F3 `frame_ms=` → F2 `replay --verify` → F4 prerequisite blocks.

## Keep in step

- Change a rule or an OPS_TABLE row → `python3 scripts/site-data.py`, commit the JSON.
- Change parse rules in `main.c` → mirror in `docs/assets/js/ops-check.js`; `make site-check`.
- Change the tree walk in `sha256.c` → same change in `tools/hash.py`; `TestHashParity` guards it.
- Numbers: `PERF_AND_MAP.md` first, then `docs/_data/perf.yml`.

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- No trackers, no CDN, no blog; one CI check, compile + ROM + site, never the worker suite on hosted runners.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
