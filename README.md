# Bench

> Bench is a bench, not an assistant. Five intern ops, framed steps, typed evidence, ROM crowns. This repo is the foundation image.

The spec is ROM: [`spec/BENCH_SPEC.md`](spec/BENCH_SPEC.md). If the code and the spec disagree, the code is wrong.

## Parts

- `supervisor/` — C. One thread owns the frame: clock, snapshot, lamps, kill.
- `isa/` — Python. `hotz_isa.py` (closed terms), `karpathy_rom.py` (`is_ring0`).
- `tools/` — programs reached only via `EXEC`: `hash.py`, `peek.py`, `test_runner.py`.
- `tests/rom/` — Ring 0. Every file must pass `is_ring0`.
- `main/`, `hold/` — the two address spaces. `sessions/` — snapshots and logs.

## Use

```
make test                               # offline, radio unplugged
make e2e                                # fixture intern → frames → snaps → demo
./supervisor/bench run [--n N] script   # one opcode per frame, N ≤ 8
./supervisor/bench status | kill | demo | snap-ls
```

## Not in this foundation

No model slot, no GUI, no network, no MCP, no multi-agent, no skills runtime,
no Overnight density, no `hold/ → main/` merge. MAIN stays dark.
