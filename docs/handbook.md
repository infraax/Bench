# Owner's handbook

All commands take the world root from `BENCH_ROOT` (default: the current directory).

## Arm

```
: > sessions/OWNER_TOKEN        # arm: a regular file, yours, not group/world-writable
rm sessions/OWNER_TOKEN         # disarm (the next frame stops)
BENCH_TOKEN=/path/to/key ...    # or name a token file elsewhere
```

The token is re-checked before every frame, by bench and by the helper. Touching or replacing it
mid-run disarms. The intern cannot create it.

## Commands

| Command | Does | Needs |
|---|---|---|
| `bench run [--n N] [--hold-quota B] [--hold-files N] [--keep M] <script\|->` | frame each line of the script; snapshot after each step | armed, ROM crowned, world free |
| `bench status [--line]` | the board: session, lamps, snap, n/N, slots; `--line` is one grep-able line | — |
| `bench kill` | stop the running session (or demo) now; the cut step is snapped | a live run |
| `bench snap-ls` | list the current session's snapshots | — |
| `bench verify [snap-<k> \| <session>/snap-<k>]` | re-hash stored snapshots against `board=` | — |
| `bench restore snap-<k> \| <session>/snap-<k>` | load a verified snapshot's `hold/` as a new session; old `hold/` kept as `hold.before` | armed, ROM crowned, world free |
| `bench fork snap-<k> \| <session>/snap-<k> <dir>` | a new, unarmed world from a verified snapshot | armed, ROM crowned; `<dir>` new, outside this world |
| `bench rules` | the refusal table: `rule=<id> fix: <hint>` | — |
| `bench check [--n N] <script\|->` | lint a script without running it: each line `blank\|ok\|parse\|run` with its `rule=`, then the verdict a run would reach (`check ops= frames= exit=`, `stop line= rule=`). Same parser as `run`; refusals predicted from the foundation board | — (writes nothing) |
| `bench stats [<session>]` | where a session's time went: per verb, `frame_us` p50/p95/max (the C thread's own work) and `tool_us`, plus headroom against `T_frame` | — |
| `bench demo` | run the ROM suite as one knifed child | ROM crowned |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | fault (a step was refused or failed; see the `rule=` line) · `fork`/`restore`: snapshot damaged or target exists |
| 2 | usage |
| 3 | killed |
| 4 | ROM changed since the build — rebuild with `make` |
| 5 | not armed, or disarmed mid-run |
| 6 | helper missing, silent, lost or wrong version |
| 7 | world busy (another run or demo holds the lock) |

## Reading a fault

```
FAULT line 1: deny slot=fb unplugged rule=slot-pulled tool_ms=0
  rule=slot-pulled fix: that slot is pulled in foundation; use fs
```

The step's `MANIFEST` (`sessions/<id>/snap-<k>/MANIFEST`) carries the same evidence line with
`rule=`. Tool output is in `sessions/<id>/out-<n>`, pinned by sha256 in the MANIFEST.

## Housekeeping

- `make clean` removes build products and sessions but keeps `OWNER_TOKEN`.
- `run` keeps the newest 20 sessions (`--keep M`).
- `make env`, `make ledger-test`: machine card and a ledger row (`ledger/README.md`).
- `make audit-evidence` (or `python3 scripts/evidence-audit.py <world>`): re-derive every session's
  chain, board hashes, out pins and seals in Python — a second witness to `bench verify`.
- `make test-deep` (`DEEP=--quick` for about a minute): the adversarial pass — fuzzers, fault and
  power-cut sweeps, mutation testing. Report in `ledger/deep-*/summary.md`
  ([`TESTING_KIT.md`](TESTING_KIT.md)).

Full behavior, quotas, snapshot format and worker limits: [`reference.md`](reference.md).
