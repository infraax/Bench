# Test budget — Bench, 2026-09-28

How to keep `make test` fast and unflaky without losing a rule's only test. Numbers from this
machine (4 CPUs, Python 3.11.15, root, stdlib unittest); per-test times from one timed run of the
harness (`unittest` with a timing result class), suite walls from repeated `make test`.

## Where the time goes

| Layer | Tests | Wall | What it proves |
|---|---:|---:|---|
| bus (`bus_test.c`) | exhaustive | < 0.1 s | every lamp byte × bit, plug byte × pull |
| ROM (`tests/rom/`) | 55 | 0.02 s in-process, 80 ms with python boot | pure tables and algebra; Ring 0 |
| harness (`tests/harness/`) | 146 | 18–23 s | the binary, through worlds |

`make test` wall: **22.2 s median, 23.2 s p95 (n=20, 139 harness tests)** before this session's
test-only change; **21.0 s median (n=5, 146 tests)** after. Run-to-run spread (18–24 s) is larger
than the gain.

Harness time by class (one run, 22.8 s total):

| Class | Tests | s | Why it costs |
|---|---:|---:|---|
| TestBoard | 18 | 6.7 | token/kill tests run `WAIT 400 × 6` so the gate can be caught mid-run; one test runs two sessions against the lock |
| TestMailbox | 12 | 3.5 | `test_silent_helper_fails_closed` waits out the helper's 2 s open timeout (3.05 s alone) |
| TestFork | 11 | 2.4 | `test_two_worlds_run_at_the_same_time` runs two `WAIT 1500` worlds (1.6 s) |
| TestDeltaSnaps | 5 | 2.0 | 1000-file holds, on purpose |
| TestCage | 22 | 1.7 | one python worker per test |
| everything else | 78 | 6.5 | ~50–100 ms each: one world, one or two `bench run`s |

**Clock-bound floor:** the helper timeout (2 s), the deliberate `WAIT`s (~4.5 s together) and the
1000-file snaps (~1.5 s) are what the tests exist to measure. They are ~8 s of the 22 s and cannot
shrink without changing what is proved.

## ROM vs harness

- **ROM** holds truth tables and pure checks: `OPS_TABLE` (45 rows), `WRITE_TABLE`, `hook()` rows,
  `RULES` + `OPS_RULES` (refusals), ISA types, `is_ring0`, arm rules. Milliseconds.
- **Harness** replays those tables through the binary (one test per table, not one per row) and
  covers what only a process can: the clock, the lock, the helper, the worker view, snapshots,
  fork, the post-condition backstop.

## The pattern to keep: one ROM table + one C replay

This is the pattern that caught the `hook()` bug and keeps the refusal ids honest. Candidates to
fold into it (behavior coverage kept; each row still runs through the binary):

| Today | Fold into | Saves |
|---|---|---|
| `FIXTURES` in the harness (unknown verb, supervisor words…) — 4 rows repeat `OPS_TABLE` rows | drop the 4 duplicate fixture rows; `OPS_TABLE` + `OPS_RULES` already assert verb class **and** rule | 4 worlds (~0.3 s), no coverage lost: same line, same binary, stricter assertion |
| `TestCage` seccomp cases (socket, ptrace, io_uring ×3, x32, mount API ×3) — each its own tool file | one `SYSCALL_TABLE` in the harness: (name, nr, args, expect) run in one world, one step per row | ~9 worlds; one place to read what is killed vs EPERM |
| `TestRefusals.test_manifest_of_a_refused_step_carries_the_rule` (3 lines) | add a `manifest=True` column to `OPS_RULES` rows that frame | the MANIFEST check covers every runtime refusal, not 3 |

Not yet done: each is a test-structure change worth its own commit with a before/after count of
asserted rules. The rule is: **never delete the only test of a rule** — fold only rows whose line
already appears in a ROM table replayed through the binary.

## Timing tests that need `repeats=`, not one sample

| Test | Asserts | Risk |
|---|---|---|
| `test_kill_reaches_a_running_child` | KILL lands < 2.0 s | single wall sample on a loaded CI box |
| `test_kill_reaches_a_running_demo` | < 2.0 s | same |
| `test_two_worlds_run_at_the_same_time` | two 1.5 s worlds < 2.8 s | margin 1.3 s; under parallel test load it shrinks |
| flood knife | < 10 s | wide margin |
| retention / crash status | < 8 s | wide margin |

0 of 23 `make test` runs tripped any of them. The fix when one does: assert the **mechanism**
(exit code, `halt op=exec` in the MANIFEST, both worlds' STATE says ok with overlapping
`started`/`ended` stamps) and keep the wall bound as a generous ceiling, sampled with
`repeats=3, pass if best < bound`. Do not widen a bound to hide a regression.

## Faster without losing coverage

1. **Done:** harness worlds copy only `supervisor/woz_bus.h` (World() 24.7 → 11.4 ms).
2. **Parallel classes.** Worlds are independent temp dirs and the binary is built before the
   harness starts, so classes can run in 4 processes. Expected: ~22 s → ~8 s (bounded by
   TestBoard's ~6.7 s of waits). Cost: timing tests above lose margin under load — do item 3 of
   the previous section first.
3. **The 2 s helper timeout** is the single slowest test. It proves "silent helper → exit 6 within
   T_open". Keep it; it is one test.
4. **The ROM suite is not the problem**: 55 tests in 20 ms. Push more checks down into ROM tables
   where they are pure; that is where coverage is cheap.

## Measured, not guessed

Re-measure with: `make test` ×N around a `date` pair; per-test times with a `TextTestResult`
subclass that records `start/stopTest`; world cost with `World()` in a loop. Report median and
p95, n, machine, and whether the run was root.
