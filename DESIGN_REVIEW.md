# Design review — Bench

Reviewer: implementer, after two maintenance sessions on this tree (head at the time of writing:
`bench: helper mailbox PING` + this file). Scope: `isa/`, `supervisor/` (not `sandbox.c`), `tests/`,
against `spec/BENCH_SPEC.md`. The spec is unchanged; disagreements are marked **spec amendment request**
with the seats that would have to initial them.

Legend: **[fixed]** landed this session · **[open]** still true in the tree · **[bet]** unmeasured.

## Status after session 4 (hardening + adversarial pass)

Owner asks, all done:

- **File quota → 256** (`bench: file quota default 256`). The default now snaps inside `T_frame`.
- **Linked snapshots — properly solved**, in two independent layers:
  - *Prevention*: snaps are **sealed** read-only on landing (files `0444`, dirs `0555`), so a shared
    hard-linked inode cannot be written in place through any link (`bench: seal snapshots read-only`).
    Honest limit surfaced: this container runs as **root**, and mode bits are advisory against root —
    sealing stops every non-root writer, not root.
  - *Guarantee*: each snap records `board=<sha256 of its stored hold>`, and **`bench verify`**
    recomputes and compares — catching a mutation of any shared inode regardless of who made it,
    root included (`bench: verify`). `restore` checks it first.
- **TEST post-conditions now cover `sessions/`** (`bench: TEST post-conditions cover the session's
  snapshots`): the pre/post board read hashes `SESSION`, `OPS`, and every prior `snap-*/`, so a
  crowned TEST that rewrites history mid-run is caught (`moved=sessions`).

Adversarial pass — two real breaks found and fixed, one hang, plus hardening:

1. **[fixed] Root escape via symlink.** The supervisor's `READ`/`WRITE` (run as the owner, not
   landlocked) only string-checked the path prefix. A tool planted `hold/x -> /outside` and a later
   `WRITE fs hold/x/f` wrote outside the world as the owner — proven, an outside file was overwritten.
   Fixed by walking every component with `O_NOFOLLOW` anchored at the world root
   (`bench: WRITE/READ symlink escape`).
2. **[fixed] Frame-clock hang via fifo.** A tool `mkfifo`'d in `hold/` (landlock does not restrict
   fifo creation) and a `READ` of it blocked the supervisor forever. Fixed: finals open `O_NONBLOCK`
   and must be regular files (`bench: READ/WRITE refuse fifos and devices`).
3. **[fixed] Unbounded tool output to disk.** `child_run` streamed to `out-<n>` with no hard cap.
   Now killed past `OUT_CEIL_BYTES` (1 MiB) (`bench: hard output ceiling`).

Still open, recorded honestly (none are new escapes):

- **[open] A tool can read outside the world.** It runs as root and may `open()` or hard-link any file
  it can read, then `READ`/print it. This is not a new capability — a tool could already print any
  file to stdout — and is consistent with the model (the leash is on *writes*, network, and the crown,
  not reads). The real fix is running tool children under an unprivileged uid or a mount namespace,
  which is `sandbox.c`/kernel-policy territory, out of scope this session.
- **[open] `snap-<k>.tmp` litter** from a failed snap stays until the session is pruned. Self-limiting
  (one per faulted session; `snap-ls`/`verify`/retention ignore `.tmp`).
- **[open] `T_session` never binds** at foundation budgets (edge 12 below); **lamp byte is constant**
  (edge 15); **Python mirrors C by tables** (edge 16). Unchanged.

## Status after session 3 (implementation pass)

| Review item | Status | Commit |
|---|---|---|
| Improvement 1 — TEST post-conditions (sharp edge 6) | **done** | `bench: M1 test postconditions` |
| Improvement 2 — token identity and mode (sharp edge 7, mostly) | **done** | `bench: M2 token identity` |
| Improvement 3 — split the log (sharp edge 8) | **done** | `bench: M3 split the log` |
| Improvement 4 — world lock (sharp edges 9, 10) | **done** (fcntl, not flock: `F_GETLK` names the holder) | `bench: M4 world lock` |
| Improvement 5 — `status --line` | **done**, plus helper version pin | `bench: M5 status --line, helper version pin` |
| Improvement 6 — file quota | **done** | `bench: M6 file quota` |
| Improvement 7 — snap by delta (sharp edge 11) | **done**, measured 344 ms → 8 ms per 1000 unchanged files | `bench: S7 snap by delta` |
| Improvement 8 — `bench restore` | **done** | `bench: S8 restore a snap` |
| Improvement 9 — demo inside reach (sharp edge 14) | **done** (lock + knife = T_tool × ROM files) | `bench: S9 demo inside reach` |
| Improvement 10 — ROM owns the tables | **done** (`tests/rom/test_ops.py`, 45 rows) | `bench: S10 ROM ops table through the binary` |
| Improvement 11 — retention for `sessions/` | **done** | `bench: S11 session retention` |

Still open from the list below: sharp edges 12 (`T_session` never binds), 13 (`WAIT` is time only),
15 (constant lamp byte), 16 (Python models C by tables), and the permanent-token half of 7.

New edges found while implementing:

- **Linked snaps share inodes.** After S7, one in-place write to a file under `sessions/<id>/snap-k/hold/`
  changes every snap that links it. Only the owner and `TEST` children can write `sessions/`.
  `restore` re-hashes before it moves anything, so damage is detected, not prevented.
- **TEST post-conditions do not cover `sessions/`** beyond the token files. A crowned test could edit
  a snap or a log without tripping M1. Next step: include `sessions/<id>/` MANIFEST + INDEX hashes in the
  TEST board read.
- **Default file quota vs `T_frame`.** 1024 *new* files in one step cost ~350 ms to snap on the test
  disk (creation, not copying, dominates). The quota admits a step the frame then faults. Either the
  default drops (~256) or `T_frame` becomes per-notch. Owner call.

---

## What already holds

- **Five verbs, closed in two languages, checked for agreement.** `parse_line` in `main.c` and `Op` in
  `hotz_isa.py` are the two definitions. The harness proves they match on opcode numbers, on a WRITE
  path table owned by ROM (`tests/rom/test_arm.py`), and on `hook()` vs the C slot gates (8 script lines).
  Supervisor words (`INSTALL_ROM`, `SET_LOOP`, `KILL`, `UNPLUG`) and mailbox words (`PING`, `ARM_OK`,
  `FRAME_OK`) are all "unknown verb" or "supervisor" to the parser.
- **Snapshot or the step did not happen.** `frame()` snaps before it inhibits; a failed snap rolls `n`
  back. Every fault path now snaps first and stops second, and names its reason in the evidence.
- **The frame owns its edges.** gate → tool → quota → snap → inhibit, all inside `frame()`. `T_frame` is
  the C thread's own work (gate + quota walk + snap); tool time is `T_tool`, separately knifed.
- **ROM is crowned.** `bench run` and `bench demo` refuse (exit 4) when `tests/rom` does not match the
  hash baked by `make`. Every ROM file passes `is_ring0`, checked by both suites.
- **Terms are terms.** `Step` is interned, frozen, slotted, exactly typed at birth; the intern table is
  weak. Mutating or subclassing your way to a sixth field is a `TypeError` / `FrozenInstanceError`.
- **One lamp byte.** `woz_bus.h` is the only definition; `tools/peek.py` and the harness parse it. An
  exhaustive C test (`bus_test.c`) covers every lamp byte × bit and every plug byte × pull.
- **Arming is the owner's.** `sessions/OWNER_TOKEN` or `BENCH_TOKEN`, checked at start and before every
  frame, by bench *and* by the helper. Either can stop a run; neither the intern (no path, no verb) nor
  the helper alone can start one.
- **Fail closed is the default everywhere I looked.** Unjailable child → `_exit(125)`. Missing, silent or
  garbled helper → exit 6. Bad quota → exit 2 before any session. No token → exit 5, dark.

## Lies or sharp edges in the current tree

Fixed this session (kept here so the pattern is visible):

1. **[fixed]** `hook()` denied every real `EXEC` (it looked the program path up as a slot) and let
   `TEST VISUAL` and half-plugged `TEST JUDGE` through. The ROM test encoded the mismatch.
2. **[fixed]** `lamp_set(x, MAIN|HOLD)` lit both lamps; a bad byte passed through untouched. Unreachable
   from current callers; the header promised it for every input. Found by the exhaustive bus test.
3. **[fixed]** `midwife()` wrote anywhere (including `sessions/OWNER_TOKEN`); `install_rom()` silently
   replaced an existing ROM file with any `is_ring0`-clean draft.
4. **[fixed]** `KILL` did not reach a running child — the supervisor waited out `T_tool` (5 s). The quota
   walk was billed to the tool, not the frame. An over-quota step still hashed and copied the oversized
   `hold/` into its snap — the exact cost the quota exists to refuse.
5. **[fixed]** The arm comment in `main.c` said tool children are write-limited to `hold/` and
   `proposed/`. Only `EXEC` children are.

Still true:

6. **[open] A crowned ROM test can mint the owner token.** `TEST` children run without the write jail
   (the runner needs `/tmp`). So the chain *intern drafts `proposed/test_x.py` → human installs it →
   a later `TEST PURE` runs it* can create `sessions/OWNER_TOKEN` or edit `main/`. `is_ring0` does not
   look at file writes and should not start (see Refusals). The fix belongs in the frame, not the
   predicate — Improvement 1.
7. **[open] The token is presence-only and permanent.** Once `OWNER_TOKEN` exists, every future run is
   armed until someone deletes it. `make clean` deliberately keeps it. Any process with the owner's
   uid can create or swap it; mode and owner are not checked. It is a key left in the ignition.
8. **[open] Tool output and supervisor lines share one `log`.** `EXEC`/`TEST` stdout is copied into
   `sessions/<id>/log`, where `MAILBOX … -> FRAME_OK yes` lines also live. A tool can print a line that
   looks exactly like a helper answer. The MANIFEST is the record of evidence; the log is not, but
   nothing says so and a human reading the log cannot tell.
9. **[open] `bench kill` can hit the wrong process.** It sends `SIGTERM` to the pid in `sessions/<id>/PID`
   if that pid is alive. A run that died hard (SIGKILL, power) leaves `PID` behind; after pid reuse,
   `bench kill` signals whatever the owner is running under that number.
10. **[open] Two runs in one world are not excluded.** Invariant 7 ("one process owns the frame clock")
   holds per process. Two `bench run` in the same `BENCH_ROOT` race on `CURRENT`, share `hold/`, and each
   measures the other's writes against its own quota baseline.
11. **[open] Snap cost scales with `hold/`, not with the step.** Every snap hashes `main/`+`hold/` and
   copies all of `hold/`, including whatever was there before the session. The quota counts bytes, not
   files: 64 KiB of 1-byte files is 65 536 files, and copying those per step blows `T_frame` (200 ms).
   That fails closed, but the fault says `T_frame`, not "too many files".
12. **[open] `T_session` never binds in foundation.** `N ≤ 8`, `WAIT ≤ T_tool`, each child ≤ `T_tool` (5 s):
   the worst run is ~8 × 5 s + snaps ≈ 41 s < 60 s. It is checked only after a step, so its real bound is
   `T_session + T_tool + T_frame`. A budget that can never fire is decoration until Overnight raises `N`.
13. **[open] `WAIT` cannot starve the frame clock, but it is not the spec's `wait`.** It is bounded by
   `T_tool` and counted as tool time, and it consumes `N`, so it is budgeted. The spec's `wait` yields
   "until time, I/O, or a gate"; ours is time only. Fine for Touch/Chunk; say it.
14. **[open] `demo` lives outside the clock.** It runs the whole ROM suite with a 300 s child knife, no
   session, no PID, no snap. `bench kill` cannot reach it. 300 s is 60 × `T_tool` with no written reason.
15. **[open] The lamp byte is constant in practice.** Foundation always pulls fb and radio, so `status`
   shows `HOLD BLIND` for every session, ok or faulted. The lamps are truthful and carry no information
   today; the owner reads `STATUS=` from STATE instead.
16. **[open] Python models C by tables, not by construction.** `hook()`, `intern_may_write()` and the
   `Op` numbering are re-statements of C rules. Harness tables catch drift on the cases listed, not on
   cases nobody wrote down.

## Improvements I would ship next (ordered)

1. **Frame post-conditions for `TEST`** (fixes 6, no kernel change). A `TEST` step may change nothing but
   `hold/`, `proposed/` and `/tmp`. The frame already hashes `main/`; hash `main/` and `tests/rom/`
   separately before and after a `TEST`, and record the token's (dev, ino, mtime) at session start. If
   `main/` or ROM moved, or the token appeared or changed, the step is a fault and the run disarms.
   Cost: one extra tree hash per `TEST` frame. This is supervisor bookkeeping, the frame's own job.
2. **Token identity and mode** (fixes most of 7). At start, require `OWNER_TOKEN` to be a regular file
   owned by the runner's uid and not group/world-writable; pin its (dev, ino, mtime) for the session;
   the gate and `FRAME_OK` fail on any change. Still presence-only content — no crypto in v0.
3. **Split the log** (fixes 8). Tool stdout/stderr go to `sessions/<id>/out-<n>`; `log` holds only
   supervisor and mailbox lines. Snap MANIFEST gets `out=<bytes>` and the file hash. One file, one writer.
4. **World lock** (fixes 10, and 9 on the side). `bench run` takes `flock(sessions/LOCK)` for its life.
   `bench kill` signals the pid only while that lock is held (a dead run holds no lock), and
   `status` can say `crashed` when STATE says `run` but nobody holds the lock.
5. **`bench status --line`.** One line, the owner's whole board, grep-able:
   `1790485971-4453 ok n=5/8 snap=005-bfa7 HOLD BLIND hold=+12/65536 armed helper=ok`
   Same data as today, from STATE + SESSION; no new state. This is the observability the owner needs
   without a GUI.
6. **Quota counts files too** (fixes the attribution in 11). `HOLD_QUOTA_FILES` (default 1024) beside the
   byte quota, same override pattern. The fault then names the real cause.
7. **Snap by delta** (fixes the cost in 11). Hard-link unchanged files from the previous snap, copy only
   changed ones. Cost becomes proportional to the step's writes, which is what `T_frame` should measure.
8. **`bench restore <snap>`.** Invariant 3 (resume = load snap) is aspirational: nothing loads a snap.
   Restore = copy `snap-k/hold/` back over `hold/`, verify the tree hash matches the MANIFEST, write a
   new session whose s0 is that snap. The spec's "Open snap" control, no new verb.
9. **`demo` as a one-frame session.** Arm-free is fine (it only reads ROM), but give it a PID, a knife
   derived from `T_tool × ROM file count`, and one snap-free STATE line so `kill` and `status` see it.
10. **Keep ROM tiny, let ROM own the tables.** The pattern that caught real bugs this session is *ROM holds
   a pure truth table, the harness runs it through C* (`WRITE_TABLE`, `hook` table). Extend it: one
   `OPS_TABLE` in ROM (script line → expected accept/deny/verb) that the harness replays through the
   binary. ROM stays data + algebra (46 tests in 14 ms today); the world-building stays in the harness.
11. **Retention for `sessions/`.** Quota protects `hold/`; nothing protects `sessions/`, which grows by a
   full `hold/` copy per step, forever. Keep the last M sessions (owner-set, default 20) on `run` start.

## Features the four seats did not spend tokens on

- **Crash semantics.** What `status` says after a hard stop (STATE `run`, no process) — "crashed" is a
  third truth next to ok/fault, and today it prints `run`.
- **Who armed it and when.** The token has no content, SESSION has no wall-clock time. Monotonic time is
  right for budgets; the owner still needs "started 14:02" in SESSION (informational, never a budget).
- **Replay as a measurement.** `OPS` + `snap-0` + tools should reproduce `snap-n`'s tree hash. A
  `bench replay --verify` in a scratch world turns "deterministic" from a comment into a number.
- **Disk as a budget.** Every other resource has a cap (N, T_*, fs/tty caps, hold quota). `sessions/`
  has none.
- **Helper version.** `PING` answers `helper v0`; bench does not check it. When a hardware key answers
  `ARM_OK`, bench must know which helper it is talking to. Pin the version string in bench now.
- **Evidence schema.** The evidence line is `key=value` text truncated at 256 bytes. A ROM table of the
  keys each op must emit would make the MANIFEST checkable, not just readable.

## Things I refuse (and why they look tempting)

- **Growing the helper past three words.** Tempting: "while we have a socket, add STATUS / LOG / CONFIG".
  The helper's only growth path is *who answers `ARM_OK`* — today a file, later a hardware key. Anything
  that lets the helper arm without bench's own check, hold state across sessions, or reach off-box turns
  a veto into an authority.
- **Teaching `is_ring0` about the token or file writes.** Tempting after sharp edge 6. A literal-string rule
  is defeated by `open(OWNER_TOKEN, "w")` with the imported name, and flagging the name breaks the ROM
  tests that must refer to it. The metal detector stays an import fold; the post-condition belongs in the
  frame (Improvement 1).
- **A mailbox word the intern can reach.** An `ARM` opcode, or letting `EXEC` tools talk to the helper,
  is a sixth verb in a costume. The socket is unlinked after pairing, its fds are `CLOEXEC`, and the
  helper answers only its parent — keep it that way.
- **Auto-raising the quota or retrying a faulted step.** Tempting for Overnight. It makes the quota mean
  "until the intern likes it" — the same failure Round 4 rejected for `N`.
- **Status as JSON / a dashboard.** One line of text (Improvement 5) is the ceiling. Woz's bet in §5: if
  the lamps become a dashboard, the board has too many vias.
- **Promoting `hold/ → main/` after a green `TEST`.** Tempting because `TEST PURE` is Ring 0 muscle. But
  the test was chosen by the intern; the crown is a human act.
- **Resume from the log.** The log is a comment track and, per sharp edge 8, not even trustworthy.
- **Moving the supervisor to Python "for speed of iteration".** The frame clock and the knife live in C
  because they must not pay an interpreter boot.

## Spec amendment requests

1. **Invariant 7 per world, not per process.** "One process owns the frame clock *of a world*."
   Needed for Improvement 4. Seats: Carmack (clock), Lamport (process).
2. **Name the helper as supervisor hardware.** The mailbox is not a slot (the intern cannot reach it) and
   not radio (owner call). §3.2 has no word for a Ring-0 device on the supervisor's side of the bus.
   Proposed ink: "key socket — supervisor-only, veto-only, this machine only". Seats: Woz (parts),
   Wilson (if it is not an instruction, say what it is).
3. **Side effects are part of purity.** §3.6 defines `is_ring0` by source. Proposed addition: "a pure
   `test` step that changes `main/`, ROM or the owner token is a fault, whatever its source said."
   Needed for Improvement 1. Seats: Hotz (crown), Karpathy (the predicate), Lamport (initial the wording).
4. **Ink what BLIND means.** The code has always lit BLIND when fb **and** radio are both out; the old
   header comment said "or". The spec lists the lamp without a definition. Seat: Woz.
