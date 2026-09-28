# Perf and map — Bench, 2026-09-28

A mechanic's report: who starts whom, what each class of work costs on this machine, how far the
tests can be trusted, and what is dead weight. Every number below was measured in this session;
re-run with `python3 tests/perf/perf_map.py 20` and `make perf`.

**Machine:** 4 CPUs · Linux 6.18 · Python 3.11.15 · suite ran as **root** (uid 0) · no pytest
(stdlib unittest) · `hyperfine` and `perf` not installed, so timing is `time.perf_counter` around
the binary. Numbers are ms unless marked; median / p95 (nearest rank), n as stated.

---

## A. Process map

```
owner shell
 └─ bench run <script>                       one per world: fcntl lock on sessions/LOCK (held to exit)
     │  fds: LOCK (CLOEXEC) · sessions/<id>/log (O_APPEND, CLOEXEC) · mailbox cfd (CLOEXEC)
     ├─ bench-helper <root> <lfd>             forked+exec'd at session start, from bench's own dir
     │     inherits ONLY the mailbox listener (lfd); accepts once, SO_PEERCRED = parent; env: BENCH_TOKEN
     │     words: PING (start) · ARM_OK (start) · FRAME_OK <n> (every frame, T_ask 500 ms)
     └─ per EXEC / TEST step: tool child       fork → stdin=/dev/null · stdout=pipe · stderr=out-<n>
           chdir(world) → namespace view → landlock (EXEC only) → seccomp → execvpe python3 …
           bench reads the pipe into sessions/<id>/out-<n> (O_CLOEXEC in bench, dup2'd into the child)
           knife: T_tool 5 s · output ceiling 1 MiB · KILL reaches it at once

 bench demo                                   own lock sessions/DEMO; one test_runner child, knife 5 s × ROM files
 bench status | rules | snap-ls | verify      no lock, no children; read STATE / MANIFEST only
 bench restore | fork                         owner commands: armed, ROM crowned; restore takes LOCK, fork writes
                                              only the new world (target claimed by mkdir)
```

Files that carry state: `sessions/LOCK` (who owns the frame clock), `sessions/CURRENT`,
`sessions/<id>/{SESSION,OPS,STATE,PID,log,out-<n>,snap-<k>/}`, `sessions/OWNER_TOKEN` (presence),
`sessions/FORKED_FROM` (fork worlds). The helper socket path is unlinked the moment both ends pair.

---

## B. Timing classes (this machine)

| Class | What was timed | median | p95 | n |
|---|---|---:|---:|---:|
| boot | `bench status`, cold process, no session | 1.60 | 2.18 | 20 |
| boot | `bench rules` | 1.66 | 2.07 | 20 |
| arm | `bench run` with one `WAIT 0`: lock, helper spawn + PING/ARM_OK, s0 snap, one frame, status | 25.3 | 31.0 | 20 |
| frame empty | marginal `WAIT 0` frame (gate + FRAME_OK + snap of an empty hold) | 0.6 – 2.7 | 1.1 – 4.2 | 20 ×2 worlds |
| EXEC tiny | marginal `EXEC tools/hash.py` frame | 37.3 | 42.1 | 20 |
| EXEC tiny | `tool_ms` of that child (fork + jail + python boot + hash) | 32 | 42 | 180 |
| worker jail | `/bin/true`: bare → namespaces → full jail (µs) | 1345 → 2091 → 2542 | — | 50 |
| worker jail | `python3 -S -c pass`: bare → full jail (µs) | 9062 → 10175 | — | 50 |
| snap | marginal frame, hold = 0 files | 0.59 | 1.08 | 20 |
| snap | marginal frame, hold = 1 × 64 KiB | 1.78 | 2.68 | 20 |
| snap | marginal frame, hold = 256 × 1 B (unchanged → linked) | 10.5 | 15.4 | 20 |
| snap | marginal frame, hold = 1000 × 1 B (unchanged → linked) | 41.8 | 48.7 | 20 |
| snap | whole 1-step run over 1000 × 1 B (s0 copies all) | 129 | 149 | 20 |
| snap | 1-step run minus `tool_ms`, tool writes +64 / +256 new files | 19.4 / 29.7 | 22.0 / 40.7 | 20 |
| snap | same, +1000 new files (`--hold-files 2000`) | 62 | 430 (1 of 9 tripped `T_frame`) | 9 |
| fork world | `bench fork` wall incl. process start (`make perf`) | 5.5 | — | 5 |
| fork world | 4 worlds × 5-op script: sequential → parallel (s) | 1.36 → 0.38 (3.6×) | — | 1 |
| ROM suite | `unittest discover tests/rom` wall (python boot + 55 tests; in-process 0.02 s) | 80 | 135 | 20 |
| full suite | `make test` wall (s) | 22.2 | 23.2 | 20 |

Reading it:

- **The frame clock is not the bottleneck.** `T_frame` is 200 ms; the worst steady frame measured
  (1000 unchanged files) is 42 ms. A step that creates 256 new files adds ~15 ms of copy over a
  session start. At 1000 new files the median is 62 ms but the tail reaches the clock (1 of 9
  runs: 430 ms, `fault=T_frame rule=t-frame`, whose fix already says "write fewer new files per
  step"). The default file quota (256) keeps a step well inside `T_frame`; no snap work is
  justified by these numbers (§2 item 6: not done).
- **Frame cost scales with the size of hold/, not with the step.** Unchanged files are linked, but
  every frame still hashes all of `main/`+`hold/` for `tree=` and the snap's `hold/` for `board=`:
  ~40 µs per file. The README's "1000 unchanged files: ~8 ms" is the copy/link part only; the frame
  is ~42 ms. Fixed in the README (§2).
- **Python boot is the unit of cost.** An EXEC is ~32 ms, of which the jail is ~1.1 ms and python
  ~9 ms bare; the rest is `hash.py`'s imports and work. Arming a session costs less than one EXEC.
- **The empty-frame range (0.6–2.7 ms) is noise between two worlds**, not a finding; the helper
  round trip (FRAME_OK) and the gate's token stat are in both.

---

## C. Reliability of tests

**Flakes:** `make test` run **23 times** (3 + 20): 23 green, 0 failures, 0 errors. Wall 18.8–24.4 s.
Nothing moved. The first three runs drifted 18.8 → 23.2 s; the 20-run batch shows that is
spread, not a trend (median 22.2, max 24.4). Five single-sample timing assertions exist
(`assertLess(wall…)` at kill ≤ 2 s, demo kill ≤ 2 s, two worlds ≤ 2.8 s, flood knife ≤ 10 s, ≤ 8 s);
none tripped in 23 runs, but each is one sample — see `docs/TEST_BUDGET.md`.

**Tests that cannot fire their claim:**

| Test | Claim in the name | Still true? |
|---|---|---|
| `TestPostconditions.*_is_refused` (6) | the move is refused and nothing moved | **yes** — renamed last session; they assert EROFS in the child and an unchanged board |
| frame post-conditions (`frame.c`, `moved=main,rom,sessions,token`) | a TEST that moves the board disarms | **no test reaches it**: the worker view refuses every move first. The code is live but unexercised. §2 adds a harness test that moves the board from *outside* the child during a TEST |
| `test_isolation_that_cannot_be_set_up_fails_closed` | setup failure → child does not run | yes, but it asserts `rc=125`, which a tool can also print by `exit(125)` (see D) |

**Dual sources of truth — still covered:**

| Pair | Checked by |
|---|---|
| `parse_line` (C) ↔ `Op` (Python) | `OPS_TABLE` (45 rows) through the binary |
| C slot gates ↔ `hook()` | `test_hook_agrees_with_c_gates` (8 lines) |
| C WRITE rule ↔ `intern_may_write` | `WRITE_TABLE` through the binary |
| `refusal.c` ↔ `test_refusals.RULES` | `bench rules` compared to ROM; every refusal row prints its rule |
| `woz_bus.h` ↔ `peek.py` / harness | parsed from the header, never copied — but the header must exist (D) |

---

## D. Dead weight (Hotz pass)

Each finding reproduced on this machine; each fix is a diff in §2 or a proposal in E.

1. **"fixed PATH" is half true.** `tool_env()` sets `PATH=/usr/bin:/bin`, but glibc `execvpe`
   searches the **caller's** PATH. Proof: `PATH=/nonexistent bench run` → every EXEC is `rc=127`.
   Two-line fix: set `environ = env` in the child and `execvp`. *(§2)*
2. **Exit 125 is two things.** Jail setup failure `_exit(125)`, chdir failure 126, exec failure 127
   — all indistinguishable from a tool that exits with those codes (`sys.exit(125)` → the same
   `rc=125` evidence, no `rule=`). Fix: a CLOEXEC status pipe; the child writes one byte only if it
   fails before exec → `child_run` returns `-6`, evidence `rule=worker-setup`. *(§2)*
3. **`peek.py` dies in a fork world.** It reads `supervisor/woz_bus.h`; `fork` does not copy
   `supervisor/`. Fix: fork copies that one header (binaries still by path). *(§2)*
4. **One rewrite rule written three times.** `restore`, `verify`, `fork` each parse
   `snap-<k> | <session>/snap-<k>` (~20 lines each). One `snap_ref()` helper. *(§2)*
5. **Comments that lie.** `main.c` arm comment: "TEST children are not write-limited"; README
   frame section: TEST children "can reach `sessions/` where `EXEC` cannot". Both false since the
   worker view. README snap cost "~8 ms" (see B). *(§2)*
6. **Dead line.** `(void)op;` at the end of `frame()` — `op` is used above it. *(§2)*
7. **Harness copies build products.** `World` copies `supervisor/` (380 KiB incl. binaries) into
   each of ~117 worlds; the ignore list misses `ns_cost`. Only `woz_bus.h` is read from it.
   *(TEST_BUDGET)*
8. **Committed binaries:** none (`ns_cost` is gitignored and not tracked).
9. **Unused flags:** none found. `K` is passed as `N`, so the K-cadence snap fires once, on the last
   step; that is spec behavior for foundation, not dead code.

---

## E. PRISM-shaped edits (methodology only)

Framing from PRISM (`research/sources.md`): harness edits are budgeted and come in three kinds —
**silent correction** (the harness fixes it, the model never sees it), **error block** (refuse with a
reason the model can act on), **prerequisite block** (refuse before work starts because a known
precondition fails). Each is scored by **reliable lift**: does it turn a class of failure into a
deterministic, testable outcome — not by average improvement. Capped at 12, no new verb.

| # | Edit | Kind | Files | Test that fails today | Cost |
|---|---|---|---|---|---|
| 1 | exec search uses the worker env's PATH | silent correction | `frame.c` | EXEC with bench `PATH=/nonexistent` → `rc=127` | 2 lines |
| 2 | setup failure has its own return + `rule=worker-setup` | error block | `frame.c`, `main.c`, `refusal.c`, ROM mirror | `sys.exit(125)` tool must *not* carry `rule=worker-setup`; setup failure must | ~20 lines |
| 3 | fork copies `supervisor/woz_bus.h` | silent correction | `main.c` | `EXEC tools/peek.py` in a fork world → rc=1 | 3 lines |
| 4 | layer-2 post-condition test (board moved from outside during a TEST) | coverage | harness | none fails — the path has no test at all | ~40 lines test |
| 5 | `snap_ref()` shared by restore / verify / fork | hygiene | `main.c` | none (behavior-neutral; existing usage tests hold it) | −40 lines |
| 6 | stale comments + README snap numbers | hygiene | `main.c`, `README.md` | — | text |
| 7 | `EXEC tools/<missing>.py` refused before fork, `rule=exec-missing` | prerequisite block | `main.c`, `refusal.c`, ROM | today: python prints "can't open file", `rc=2`, no rule | ~6 lines |
| 8 | `WAIT <ms>` over `T_tool` refused at parse, not after the session starts | prerequisite block | `main.c` | `WAIT 6000` today starts a session and faults at frame 1 | 2 lines |
| 9 | harness `World` copies only `supervisor/woz_bus.h` | silent correction (tests) | harness | — | ~1 s off `make test` (est.) |
| 10 | per-frame `T_frame` in the MANIFEST (`frame_ms=`) | error block (for the owner) | `frame.c` | the snap classes above had to be derived from wall clocks | 2 lines |
| 11 | timing asserts sampled with `repeats=` | test reliability | harness | none today (0/23 flaked) | small |
| 12 | `hold/` hash cost: reuse `INDEX` to skip re-hashing unchanged files | performance | `frame.c` | none: 42 ms at 1000 files ≪ 200 ms | ~60 lines — **not justified yet** |

Done this session: 1, 2, 3, 4, 5, 6. Proposed for the owner: 7, 8, 10. Left: 9, 11 (see
`TEST_BUDGET.md`), 12 (numbers do not justify it).

---

## F. Tools used

`make` (`test`, `perf`, `e2e`), `tests/perf/perf_fork.py`, `tests/perf/ns_cost.c`, the new
`tests/perf/perf_map.py` (stdlib `time.perf_counter`, `subprocess`), `strace` for one trace in the
previous session, shell `date` around `make test`. No `hyperfine` or `perf` on this machine; no
tracing stack added.
