# Evolution — Bench

What exists, what comes next, what waits. Each line is either in the tree, in `DESIGN_REVIEW.md`,
or in `spec/BENCH_SPEC.md`. Nothing here adds a verb. The spec is unchanged.

---

## Phase now — shipped (sessions 1–4)

**Machine**

- Five intern verbs, closed in C (`parse_line`) and Python (`Op`), checked against each other by
  three ROM-owned tables run through the binary: WRITE paths, `hook()` gates, 45 opcode rows.
- Frame: gate → [TEST board read] → tool → [TEST post-conditions] → quotas → snap → inhibit.
  `T_frame` is the C thread's own work; `T_tool` the child's; budget faults name themselves.
- Snapshots by delta (hard links from the previous snap, verified by ino/size/mtime/ctime).

**Snapshots as evidence** (session 4)

- **Sealed** read-only on landing (files `0444`, dirs `0555`): a shared hard-linked inode cannot be
  written in place through any link. Stops every non-root writer; mode bits are advisory against root.
- **Content-addressed**: each snap records `board=<sha256 of its stored hold>`. `bench verify`
  recomputes and compares — the root-proof guarantee, independent of `main/` and of who owns the files.
- `restore` checks `board=`, then `main/`+`hold/` against `tree=`, before anything moves; old `hold/`
  kept as `hold.before`. Retention keeps the newest 20 (unseals only to delete).
- TEST post-conditions cover `main/`, `tests/rom/`, the token, **and** the session's frozen artifacts
  (`SESSION`, `OPS`, every prior snap).

**Supervisor file safety** (session 4)

- `READ`/`WRITE` anchored at the world root, every component `O_NOFOLLOW`: no intern-planted symlink
  is ever followed out of the world (closed a proven root escape).
- `READ`/`WRITE` act on regular files only (`O_NONBLOCK` + `S_ISREG`): a fifo/device cannot hang the
  frame clock.
- Tool output to disk capped at `OUT_CEIL_BYTES` (1 MiB): a flood is killed, not left to fill the disk.

**Owner's hand**

- Token v0: a regular file, the runner's uid, not group/world-writable, pinned per run and
  re-checked before every frame.
- Helper mailbox: three words (`PING`, `ARM_OK`, `FRAME_OK`), version-pinned (`helper v0`),
  veto-only, parent-only, fail closed.
- World lock (`sessions/LOCK`), demo lock (`sessions/DEMO`); `kill` signals only a proven pid;
  `crashed` is a status. `status --line`: the whole board on one line.

**Budgets**

- N ≤ 8, `T_frame` 200 ms, `T_tool` 5 s, `T_session` 60 s, fs/tty caps 4 KiB,
  hold growth 64 KiB and 256 entries (per-run override), out ceiling 1 MiB, 20 sessions.

**Tests**: bus (exhaustive C), 50 ROM, 117 harness — offline.

---

## Phase next — what the review still asks for

Ordered. Each is a supervisor change or a tool, never a verb. (Sessions 3–4 cleared the whole S-list,
`sessions/` coverage, the quota/`T_frame` reconciliation, sealing and `verify`.)

1. **`bench replay --verify <session>`.** In a scratch world: restore `snap-0`, re-run `OPS`, compare
   every step's `tree=`, `board=` and `out=` sha256 with the original MANIFESTs. Output: first divergent
   step, or `REPLAY ok n=<n>`. Turns "deterministic" from a comment into a number. Owner command, not an op.
2. **Evidence key table in ROM.** `tests/rom/test_evidence.py`: for each op, the keys its evidence line
   must carry (`op= kind= slot= … dirty=`), and for each tool in `TOOLBOX.md` its `ev` line keys.
   Harness checks real MANIFESTs against it. The MANIFEST becomes checkable, not just readable.
3. **Wall clock in `SESSION`.** `started=<RFC 3339>` and `ended=`, informational only. Budgets stay on
   the monotonic clock.
4. **The v1 toolbox** (`TOOLBOX.md`): 12 `tools/*.py`, each with a ROM test that imports its pure
   core, and an `ev` line. Implementable without new philosophy.
5. **`T_session` that can bind.** Pre-check before a step: remaining budget ≥ `T_tool` + `T_frame`, else
   stop at the gate. Matters only once N grows.
6. **Token lifetime.** Optional `--consume-token`: the run renames `OWNER_TOKEN` to
   `OWNER_TOKEN.used-<session>` at arm, so one token = one run. Keeps v0's presence rule.
7. **Prune `snap-<k>.tmp` litter** on `run` start (a faulted snap can leave one). Cosmetic; retention
   already reclaims it with the session.

---

## Phase later — needs a notch, an owner call, or hardware

- **Overnight N.** N > 8 is `SET_LOOP`, Ring 0. Needs: a notch file the owner writes (N, K, T_*,
  quotas) hashed into s0; the K-snap cadence actually exercised; `T_session` binding (next #5);
  retention sized for long runs.
- **Tool children under their own uid.** Today a tool runs as the owner (root here), so it can read any
  file the owner can and chmod past a snap seal — the seal is advisory against it and `bench verify` is
  the guarantee. Running each tool child as an unprivileged uid (or in a mount namespace that shows only
  the world) would make the seal binding against tools too and close read-outside-the-world. This is
  `sandbox.c` / kernel-policy work — deliberately out of scope until the owner asks for it.
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
