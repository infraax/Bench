# Evolution — Bench

What exists, what comes next, what waits. Each line is either in the tree, in `DESIGN_REVIEW.md`,
or in `spec/BENCH_SPEC.md`. Nothing here adds a verb. The spec is unchanged.

---

## Phase now — shipped (sessions 1–3)

**Machine**

- Five intern verbs, closed in C (`parse_line`) and Python (`Op`), checked against each other by
  three ROM-owned tables run through the binary: WRITE paths, `hook()` gates, 45 opcode rows.
- Frame: gate → [TEST board read] → tool → [TEST post-conditions] → quotas → snap → inhibit.
  `T_frame` is the C thread's own work; `T_tool` the child's; budget faults name themselves.
- Snapshots by delta (hard links from the previous snap, verified by ino/size/mtime/ctime),
  `restore` with hash check before anything moves, retention (newest 20).
- Tool output in `out-<n>`, pinned by sha256 in the MANIFEST; the log is the supervisor's.

**Owner's hand**

- Token v0: a regular file, the runner's uid, not group/world-writable, pinned per run and
  re-checked before every frame.
- Helper mailbox: three words (`PING`, `ARM_OK`, `FRAME_OK`), version-pinned (`helper v0`),
  veto-only, parent-only, fail closed.
- World lock (`sessions/LOCK`), demo lock (`sessions/DEMO`); `kill` signals only a proven pid;
  `crashed` is a status.
- `status --line`: the whole board on one line.

**Budgets**

- N ≤ 8, `T_frame` 200 ms, `T_tool` 5 s, `T_session` 60 s, fs/tty caps 4 KiB,
  hold growth 64 KiB and 256 entries (per-run override), 20 sessions.

**Tests**: bus (exhaustive C), 50 ROM, 99 harness — offline.

---

## Phase next — the S-list is empty; this is what the review still asks for

Ordered. Each is a supervisor change or a tool, never a verb.

1. **Cover `sessions/` in TEST post-conditions.** Add the current session's MANIFEST/INDEX hashes and
   `CURRENT` to the TEST board read (new edge after S7: linked snaps share inodes).
2. **Reconcile file quota and `T_frame`.** Measure create cost per file on the target disk; either the
   default drops (~256) or `T_frame` is set per notch. Owner decides; the code already reports both faults.
3. **`bench replay --verify <session>`.** In a scratch world: restore `snap-0`, re-run `OPS`, compare
   every step's `tree=` and `out=` sha256 with the original MANIFESTs. Output: first divergent step, or
   `REPLAY ok n=<n>`. Turns "deterministic" from a comment into a number. Owner command, not an op.
4. **Evidence key table in ROM.** `tests/rom/test_evidence.py`: for each op, the keys its evidence line
   must carry (`op= kind= slot= … dirty=`), and for each tool in `TOOLBOX.md` its `ev` line keys.
   Harness checks real MANIFESTs against it. The MANIFEST becomes checkable, not just readable.
5. **Wall clock in `SESSION`.** `started=<RFC 3339>` and `ended=`, informational only. Budgets stay on
   the monotonic clock.
6. **The v1 toolbox** (`TOOLBOX.md`): 12 `tools/*.py`, each with a ROM test that imports its pure
   core, and an `ev` line. Implementable without new philosophy.
7. **`T_session` that can bind.** Pre-check before a step: remaining budget ≥ `T_tool` + `T_frame`, else
   stop at the gate. Matters only once N grows.
8. **Token lifetime.** Optional `--consume-token`: the run renames `OWNER_TOKEN` to
   `OWNER_TOKEN.used-<session>` at arm, so one token = one run. Keeps v0's presence rule.

---

## Phase later — needs a notch, an owner call, or hardware

- **Overnight N.** N > 8 is `SET_LOOP`, Ring 0. Needs: a notch file the owner writes (N, K, T_*,
  quotas) hashed into s0; the K-snap cadence actually exercised; `T_session` binding (next #7);
  file quota and `T_frame` reconciled (next #2); retention sized for long runs.
- **Radio as an explicit plug.** Today radio is always pulled and tool children get `EPERM` on the
  network. A radio notch would be: owner flips the plug bit for one session, BLIND goes dark, the
  lamp byte finally carries information, and only the two notch tools in `TOOLBOX.md` (`fetch`,
  `publish`) are allowed to use it — through a supervisor-side path, not by loosening tool children.
  Needs a spec amendment and an owner review before any code.
- **Hardware token answering `ARM_OK`.** The mailbox already has the seam: the helper answers `ARM_OK`
  and `FRAME_OK`. A key replaces the helper's file check; bench keeps its own check (veto-only, both
  must say yes). Version bump to `helper v1`, pinned by bench. No USB or firmware design in this repo.
- **`hold/ → main/` merge (MAIN lamp).** Ring 0 only: a human command that copies a proposed diff
  into `main/` after a green `TEST PURE` the human chose. First code that may set `LAMP_MAIN`.
- **Judge and eyes slots.** `TEST JUDGE`, `TEST VISUAL`, `fb.read(rect, scale)` — dirty devices,
  never crowning. Only after radio exists as a plug.
- **MCP as an adapter.** A program under `tools/` that speaks to one outside server, gated by the radio
  notch. World state stays files; MCP never becomes ontology.

---

## Spec amendments still waiting on humans

From `DESIGN_REVIEW.md`. None applied; the code works without them but depends on the reading given.

| # | Amendment | Seats that must initial | Code already assumes |
|---|---|---|---|
| 1 | Invariant 7 is per **world**, not per process | Carmack, Lamport | `sessions/LOCK` |
| 2 | Name the helper: "key socket — supervisor-only, veto-only, this machine only" | Woz, Wilson | `bench-helper` |
| 3 | Side effects are part of purity: a pure `test` that moves `main/`, ROM or the token is a fault | Hotz, Karpathy, Lamport | M1 post-conditions |
| 4 | BLIND = fb **and** radio both pulled | Woz | `woz_bus.h` `pull()` |

Proposed for the next review round:

| # | Amendment | Seats |
|---|---|---|
| 5 | `restore` is the spec's "Open snap"; `hold.before` is kept, never deleted | Carmack, Woz |
| 6 | Tool output is evidence by hash (`out=`), not by log line | Karpathy, Lamport |
