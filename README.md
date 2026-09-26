# Bench

> Bench is a bench, not an assistant. Five intern ops, framed steps, typed evidence, ROM crowns. This repo is the foundation image.

The spec is ROM: [`spec/BENCH_SPEC.md`](spec/BENCH_SPEC.md). If the code and the spec disagree, the code is wrong.

## Parts

- `supervisor/` — C. One thread owns the frame: clock, C tree-hash snapshot, lamps, kill.
  `sandbox.c` drops authority on tool children; `sha256.c` hashes the board; the ROM
  crown (`rom_hash.h`) is baked at build.
- `isa/` — Python. `hotz_isa.py` (interned, slotted terms), `karpathy_rom.py` (`is_ring0`).
- `tools/` — programs reached only via `EXEC`: `hash.py`, `peek.py`, `test_runner.py`.
- `tests/rom/` — Ring 0, pure algebra. Every file must pass `is_ring0`.
- `tests/harness/` — driven by `make` (a human, not ROM); may use subprocess to run the binary.
- `main/`, `hold/` — the two address spaces. `sessions/` — snapshots and logs.

## Conservation of authority (the cage, not the wand)

`is_ring0` is a source metal detector — it stops an accidental ghost import, nothing more.
The cage is the C TCB, applied to every tool child:

- **seccomp** — the antenna (socket/connect/…) returns `EPERM`; ptrace, mount, namespaces
  and the key ring are `KILL`.
- **landlock** — an `EXEC`'d intern tool may write only `hold/` and `proposed/`; `main/` and
  `tests/rom/` are read-only to it.
- **scrubbed env** — no `LD_PRELOAD` / `PYTHONPATH`; fixed `PATH`.
- **ROM crown** — `bench` refuses to boot if `tests/rom` no longer matches the hash baked at
  build. Changing ROM is Ring 0: rebuild with `make`.

Honest limit: on stock Linux with a Python tool, `execve` stays allowed (the filter is
installed before the tool's own exec). Full exec-lockdown needs a sealed non-python tool.

## Use

```
make test                               # ring 0 + harness, offline, radio unplugged
make e2e                                # fixture intern -> frames -> snaps -> demo
./supervisor/bench run [--n N] script   # one opcode per frame, N <= 8
./supervisor/bench status | kill | demo | snap-ls
```

## Not in this foundation

No model slot, no GUI, no network, no MCP, no multi-agent, no skills runtime,
no Overnight density, no `hold/ -> main/` merge. MAIN stays dark.
