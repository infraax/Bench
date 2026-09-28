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

Full behavior, quotas, snapshot format and worker limits: [`reference.md`](reference.md).
