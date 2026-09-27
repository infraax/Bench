# NOTES — maintenance session 2026-09-27

## What existed at start

- Commits: `202314e` foundation, `b91154c` hardening. Tree clean on `claude/bench-maintenance-3739it`.
- C supervisor (`run status kill demo snap-ls`), interned `Step`, `is_ring0`, three tools,
  ROM + harness tests. README claims matched the files; no claims about a helper or new worker policy.
- No `NOTES.md` before this one.

## `make test` at start (clean tree, offline, Python 3.11, no pytest)

- Ring 0: 29 tests, OK. Harness: 19 tests, OK. **Zero failures.** No foundation regressions to fix.

## Defects found on read (fixed)

- `Step` fields were writable: `s.op = Op.WRITE` changed the interned term for every holder.
- Raw ints passed birth checks: `Step(Op.READ, "fs", "x", None, 0)` built, since `0 is Ring.ROM` is False.
  Also `Step(1, ...)` shared an intern key with `Step(Op.READ, ...)`.
- `weakref_slot=True` was passed unconditionally → `TypeError` at import on Python 3.10.
- Intern cache kept dead weakref entries forever (unbounded growth).

## Done

| Item | Commit | What |
|---|---|---|
| B Step object | `bench: step object frozen, typed at birth, weak intern table` | frozen; type + arity check before lookup; `weakref_slot` on 3.11+, hand `__slots__` on 3.10; `WeakValueDictionary`. 5 new ROM tests. ROM suite green on 3.10–3.13. |
| C Hold quota | `bench: hold quota` | `HOLD_QUOTA_BYTES` 64 KiB growth per session, checked in `frame()` after every tool. Over = snapped failed step. 4 harness fixtures. |
| D Session arm | `bench: session arm requires token file` | `BENCH_TOKEN` file or `sessions/current/token`; else exit 5, no frames, dark. `intern_may_write` + `tests/rom/test_arm.py`; harness checks C parser agrees and never mints the token. |
| A Honesty pass | `bench: readme honesty pass, notes` | Platform section (Linux only), arm, quota, current tool-child behavior, exit codes, "Not in this tree". |

## `make test` at end

- Ring 0: 37 tests, OK. Harness: 30 tests, OK. Offline. `make e2e` green (`GREEN 37 tests`).
- Every `tests/rom/*.py` passes `is_ring0` (checked by both suites).
- No sixth verb. No code sets `LAMP_MAIN`. No model, no GUI, no network.

## Files changed

`isa/hotz_isa.py`, `supervisor/main.c`, `supervisor/frame.c`, `supervisor/frame.h`, `Makefile`,
`tests/rom/test_isa.py`, `tests/rom/test_arm.py` (new), `tests/harness/test_cli.py`, `README.md`, `NOTES.md`.

Not touched: `supervisor/sandbox.c`, `sandbox.h`, `isa/karpathy_rom.py`, `spec/`.

## DEFERRED

- **E Helper mailbox.** Needs the supervisor to create a unix socket in `sessions/`. Invariant 5
  says radio off in foundation, and `seccomp` already returns `EPERM` for socket syscalls in tool
  children. Whether a local `AF_UNIX` mailbox owned by the supervisor counts as "radio" is an owner
  decision. Needs: a yes/no on that, then a spec line for it. Protocol is ready to write once decided
  (`PING` / `ARM_OK` / `FRAME_OK` + one-line reason; missing helper → `run` fails closed like no token).

## Open questions for the owner

1. **macOS path clash (future).** `sessions/CURRENT` (file, existing) and `sessions/current/`
   (dir, new token path) collide on a case-insensitive filesystem (macOS default APFS). Irrelevant
   today because the supervisor is Linux-only, but it will break the day it builds on a Mac.
   Suggest renaming one before then (e.g. token at `sessions/OWNER_TOKEN`). Spec'd path kept as given.
2. **Quota value.** 64 KiB is a placeholder sized for Touch/Chunk (N ≤ 8, 4 KiB fs cap per op).
   Overnight will need it in the notch, not a compile-time constant.
3. **Token content.** v0 checks presence only. Any later check (content, owner uid, mode bits)
   is a spec change.
