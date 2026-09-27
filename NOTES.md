# NOTES

## Session 2 — design pass + four-seat sources

### Start

- Head `4425b74`, tree clean. `make test`: 37 ROM + 30 harness, green, offline.

### Owner calls applied

| Call | Commit | Result |
|---|---|---|
| Token path | `bench: owner token path OWNER_TOKEN` | `sessions/OWNER_TOKEN` (file). `BENCH_TOKEN` kept. `make clean` keeps the token. Old path does not arm. |
| Quota knob | `bench: hold quota override at run` | `--hold-quota` > `BENCH_HOLD_QUOTA` > 64 KiB. Frozen in SESSION. Bad value = exit 2. |
| Mailbox ≠ radio | `bench: helper mailbox PING` | **Implemented.** `bench-helper`, three words, veto-only, fail closed (exit 6). |
| Mac | — | Not ported. Token rename was the only Mac-facing change. |

### Seat passes

| Seat | File(s) | Verdict | What changed |
|---|---|---|---|
| Hotz | `isa/hotz_isa.py` | **changed** | `hook()` disagreed with C (denied every real EXEC; JUDGE/VISUAL gates missing). Exact field types (no `str` subclass with a `__dict__`). ROM + harness agreement table. |
| Karpathy | `isa/karpathy_rom.py` | **changed** | `midwife()` wrote anywhere incl. `OWNER_TOKEN`; `install_rom()` silently replaced ROM. Both fixed. Seven stdlib network modules added to the import fold. |
| Woz | `supervisor/woz_bus.h` | **changed** | Exhaustive `bus_test.c` found `lamp_set` could light MAIN+HOLD (two ways). HOLD wins now. `pull()` derives BLIND from plugs; comment said "or", code meant "and". |
| Carmack | `supervisor/frame.c` `frame.h` `main.c` | **changed** | Gate inside `frame()` (KILL, token every frame, helper). KILL kills a running child now. `T_frame` has one owner. Over-quota snap skips the board. Budget faults name themselves. `WAIT` records `slept=`. |

`supervisor/sandbox.c`, `sandbox.h`, `spec/`: not touched.

### End

- `make test` from a clean tree: `bus_test: ok`, **46 ROM + 51 harness**, green, offline. `make e2e` green.
- Every `tests/rom/*.py` passes `is_ring0`. No socket in ROM; the mailbox tests are harness-only.
- No sixth verb. No code sets `LAMP_MAIN`. Mailbox words are "unknown verb" to the parser.

### Files changed this session

`isa/hotz_isa.py`, `isa/karpathy_rom.py`, `supervisor/{main.c,frame.c,frame.h,woz_bus.h}`,
new `supervisor/{arm.c,arm.h,mailbox.c,mailbox.h,helper.c,bus_test.c}`, `Makefile`, `.gitignore`,
`tests/rom/{test_isa.py,test_arm.py,test_rom_predicate.py}`, `tests/harness/test_cli.py`,
`README.md`, `NOTES.md`, new `DESIGN_REVIEW.md`.

### DEFERRED

- None of this session's asks. Next work is ordered in `DESIGN_REVIEW.md` → "Improvements".

### Open for the owner

1. **A crowned ROM test can mint `OWNER_TOKEN`** (TEST children are not write-limited). Proposed fix
   without kernel changes: frame post-conditions on `TEST` steps (`DESIGN_REVIEW.md`, Improvement 1
   and spec amendment 3).
2. **Four spec amendment requests** in `DESIGN_REVIEW.md` (world lock, name the helper, side effects in
   purity, BLIND definition). None applied; the spec is unchanged.

---

## Session 1 — maintenance (A–D)

### What existed at start

- Commits: `202314e` foundation, `b91154c` hardening. Tree clean on `claude/bench-maintenance-3739it`.
- C supervisor (`run status kill demo snap-ls`), interned `Step`, `is_ring0`, three tools,
  ROM + harness tests. README claims matched the files; no claims about a helper or new worker policy.
- No `NOTES.md` before this one.

### `make test` at start (clean tree, offline, Python 3.11, no pytest)

- Ring 0: 29 tests, OK. Harness: 19 tests, OK. **Zero failures.** No foundation regressions to fix.

### Defects found on read (fixed)

- `Step` fields were writable: `s.op = Op.WRITE` changed the interned term for every holder.
- Raw ints passed birth checks: `Step(Op.READ, "fs", "x", None, 0)` built, since `0 is Ring.ROM` is False.
  Also `Step(1, ...)` shared an intern key with `Step(Op.READ, ...)`.
- `weakref_slot=True` was passed unconditionally → `TypeError` at import on Python 3.10.
- Intern cache kept dead weakref entries forever (unbounded growth).

### Done

| Item | Commit | What |
|---|---|---|
| B Step object | `bench: step object frozen, typed at birth, weak intern table` | frozen; type + arity check before lookup; `weakref_slot` on 3.11+, hand `__slots__` on 3.10; `WeakValueDictionary`. 5 new ROM tests. ROM suite green on 3.10–3.13. |
| C Hold quota | `bench: hold quota` | `HOLD_QUOTA_BYTES` 64 KiB growth per session, checked in `frame()` after every tool. Over = snapped failed step. 4 harness fixtures. |
| D Session arm | `bench: session arm requires token file` | `BENCH_TOKEN` file or `sessions/current/token`; else exit 5, no frames, dark. `intern_may_write` + `tests/rom/test_arm.py`; harness checks C parser agrees and never mints the token. |
| A Honesty pass | `bench: readme honesty pass, notes` | Platform section (Linux only), arm, quota, current tool-child behavior, exit codes, "Not in this tree". |

### `make test` at end

- Ring 0: 37 tests, OK. Harness: 30 tests, OK. Offline. `make e2e` green (`GREEN 37 tests`).
- Every `tests/rom/*.py` passes `is_ring0` (checked by both suites).
- No sixth verb. No code sets `LAMP_MAIN`. No model, no GUI, no network.

### Files changed

`isa/hotz_isa.py`, `supervisor/main.c`, `supervisor/frame.c`, `supervisor/frame.h`, `Makefile`,
`tests/rom/test_isa.py`, `tests/rom/test_arm.py` (new), `tests/harness/test_cli.py`, `README.md`, `NOTES.md`.

Not touched: `supervisor/sandbox.c`, `sandbox.h`, `isa/karpathy_rom.py`, `spec/`.

### DEFERRED

- **E Helper mailbox.** Needs the supervisor to create a unix socket in `sessions/`. Invariant 5
  says radio off in foundation, and `seccomp` already returns `EPERM` for socket syscalls in tool
  children. Whether a local `AF_UNIX` mailbox owned by the supervisor counts as "radio" is an owner
  decision. Needs: a yes/no on that, then a spec line for it. Protocol is ready to write once decided
  (`PING` / `ARM_OK` / `FRAME_OK` + one-line reason; missing helper → `run` fails closed like no token).

### Open questions for the owner

1. **macOS path clash (future).** `sessions/CURRENT` (file, existing) and `sessions/current/`
   (dir, new token path) collide on a case-insensitive filesystem (macOS default APFS). Irrelevant
   today because the supervisor is Linux-only, but it will break the day it builds on a Mac.
   Suggest renaming one before then (e.g. token at `sessions/OWNER_TOKEN`). Spec'd path kept as given.
2. **Quota value.** 64 KiB is a placeholder sized for Touch/Chunk (N ≤ 8, 4 KiB fs cap per op).
   Overnight will need it in the notch, not a compile-time constant.
3. **Token content.** v0 checks presence only. Any later check (content, owner uid, mode bits)
   is a spec change.
