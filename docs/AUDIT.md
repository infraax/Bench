# Audit — 2026-09-28 (session 12)

A pass over the whole tree: supervisor C, the Python mirror, tools, harness, site. What was wrong,
what was fixed (with the test that pins it), what is open, what was measured and dropped, and a
feature list. Branch `claude/handoff-start-004f8n`.

## Round 2 — found by the deep kit (session 13)

The adversarial pass ([`TESTING_KIT.md`](TESTING_KIT.md)) found eleven more. Each fix has a test
that fails on the old code (or a corpus seed / ROM row that pins it).

| # | Found by | Finding | Fix |
|---|---|---|---|
| 10 | fuzz_parse | a NUL byte read as `line-long`; `check` swallowed the next line | lines read by length; rule `line-nul` |
| 11 | fuzz_parse | `WAIT \v2` ran as `WAIT 2` (`strtoul` skips `\v`) | digits, optionally after one `+` |
| 12 | fuzz_parse | site mirror folded U+017F/U+0131 to ASCII | ASCII-only case, like `strcasecmp` |
| 13 | fuzz_parse | site mirror kept a stray CR on `WAIT 1\r\rx` | cut at the first CR/LF |
| 14 | fault_sweep | exit 0 while the final `STATE` write failed | exit 1, `rule=internal` |
| 15 | fault_sweep | a step passed with unpinned output (`sha256=unreadable`) | the step faults |
| 16 | fault_sweep | retention cut short left a torn half-session (43 violations → 0) | retire by rename, then delete |
| 17 | hash_fuzz | `*.pyc`/`__pycache__` skipped under `hold/` too: bytes parked there were not evidence | `hold/` skips nothing |
| 18 | powercut_sweep | bench killed mid-EXEC left the worker writing `hold/` with no knife | `PR_SET_PDEATHSIG` on workers |
| 19 | mutate (py) | 83 denylist names removable unnoticed (score 61% → 93%) | `test_rom_denylist.py` |
| 20 | mutate (py) | `is_ring0` missed a door named without a call (`f = eval`) | bare-name rule |

Also new: **F3 is done** (`FRAME` log lines + `bench stats`), and `bench check` (the planner's
lint; the pieces of F4 that need no world are in it). Ideas for what comes next, from a model's
point of view: [`IDEAS.md`](IDEAS.md).

## Fixed (each has a test that fails on the old binary)

| # | Finding | Fix | Pinned by |
|---|---|---|---|
| 1 | **A worker could outlive its frame.** A tool that double-forks or `setsid()`s left a grandchild writing `hold/` after the frame was snapped (custody hole). | bench is a child subreaper; each tool runs in its own process group; at frame end the group is killed and every stray child is reaped (`/proc/self/task/<pid>/children`), helper excepted. `strays=N` in evidence. | `test_a_daemonized_child_dies_with_its_frame`, `test_a_setsid_child_dies_with_its_frame`, `test_a_clean_tool_reports_no_strays` |
| 2 | **`bench kill` missed a run that was starting.** Between the lock and CURRENT, KILL went to the previous session (mislabelled it killed) and the new run carried on. Also: SIGTERM before the handler was installed killed setup midway. | kill asks the world lock first and signals a holder the PID file does not name; handlers installed before the lock (run, restore, demo). | `test_kill_during_session_start_halts_the_new_run` |
| 3 | **Undefined behaviour:** `qsort(NULL, 0, …)` in three places (session retain, tree hash, snap INDEX). | guarded with `if (n)`. | `make test-sanitize` (ASan + UBSan, whole harness) |
| 4 | **Truncation:** `FORKED_FROM` record and session names could be cut silently (`-Wformat-truncation` at `-O1`). | sized buffer; a cut record is refused, not written. | sanitize build is `-Werror` |
| 5 | **Mailbox budget restarted per byte.** A helper dribbling one byte per 200 ms stretched a 500 ms answer to seconds. | one deadline per answer (`CLOCK_MONOTONIC`). | `test_a_dribbling_helper_is_lost_within_one_budget` |
| 6 | **`tools/hash.py` disagreed with the C tree hash** (walk order, symlinks, `__pycache__`, non-UTF-8 names). | rewritten to mirror `sha256.c` byte for byte. | `TestHashParity.test_python_and_c_agree_on_a_hostile_tree` |
| 7 | **`is_ring0` bypasses (5):** `from os import system`, `… popen as p`, `… posix_spawn`, `from builtins import eval`, `import builtins; builtins.eval`. | from-imports checked against DIRTY_ATTR/DIRTY_CALL; `builtins` is dirty. | 5 new DIRTY rows in `test_rom_predicate.py` |
| 8 | **Tree hash could hang or be redirected:** a FIFO in `hold/` blocked `open`; a symlink swapped in after `lstat` was followed; header size and hashed bytes could differ. | `O_NOFOLLOW \| O_NONBLOCK`, `fstat` on the open fd, exactly `st_size` bytes or error. | harness hostile-tree test; parity with `hash.py` |
| 9 | `tools/peek.py` in a world with no session printed a traceback. | prints a dark board. | manual; trivial |

## Open — needs a decision (not changed)

| Finding | Risk | Recommendation | Gate |
|---|---|---|---|
| **Token fallback:** if `BENCH_TOKEN` is set but fails its check, `token_read` silently falls back to `sessions/OWNER_TOKEN`. An owner who *meant* the env token gets armed by the file. | medium: arms on a token the owner did not name | when `BENCH_TOKEN` is set, use only it; report its reason. One line in `arm.c`. | owner (arming semantics) |
| **No fsync.** `write_atomic` renames without `fsync(file)` + `fsync(dir)`. After a power cut, STATE/MANIFEST can be empty but present. | low on a dev box; real on a Pi on a flaky supply | `BENCH_DURABLE=1` → fsync on MANIFEST/STATE/CURRENT only (measure cost per frame first). | none — additive |
| **Stale `KILL` file** after a crash stays in that session forever; `status` shows `(killed)`. | cosmetic | fine as a record; document it. | — |
| **Cold-cache frame tail.** First frame over ~1000 fresh files can exceed `T_frame` (seen once: 677 ms). | flaky fault on slow disks | digest cache (feature F1) removes most of the work. | — |
| **PID namespace / unprivileged uid for workers.** The subreaper closes the stray-process hole in-process; a PID namespace would also hide other processes from `/proc`. | defence in depth | still owner-gated worker policy. | owner |

## Measured and dropped

| Idea | Result | Kept? |
|---|---|---|
| `hash_one_file` via `fstat` + exact reads (fewer syscalls) | 46.1 → 45.7 ms median, 1000-file frame: noise | kept for robustness (#8), not speed |
| `seal()` skips `chmod` on files already 0444 (halves chmods on a mostly-linked board) | 36.8 → 37.5 ms median, n = 48 interleaved: noise | **reverted** — no win, one more branch |

`strace -c` of eight `WAIT 0` frames over 1000 files: `openat` 6046 calls (48 % of syscall time),
`newfstatat` 10031, `read` 6105, `close` 6047, `fstat` 4044, `chmod` 2008, `link` 1000. The frame is
dominated by **re-hashing unchanged files**, not by snapshotting them. That is where a real
speed-up lives (F1).

## Feature list

Ranked by value ÷ cost. **None needs a sixth verb, a `spec/` change or a `sandbox.c` edit** unless marked.

### Tier 1 — do next

- **F1 Digest cache (tree hash v2 input).** The snap INDEX already records `(ino, size, mtime, ctime)`
  per file; add the file's sha256. A file whose stat matches reuses its digest. Expected: frame over
  1000 unchanged files from ~40 ms to a few ms; kills the cold-cache tail. **Cost:** today's tree
  hash streams every file's bytes into one sha256, so cached per-file digests cannot feed it. v2
  hashes `(relpath, size, sha256(file))` records instead: new crown values, old MANIFESTs keep
  `tree=` under a `hash=v1` tag, `tools/hash.py` and `romhash` move in the same commit.
- **F2 `bench replay --verify <session>`.** Re-run `OPS` in a forked world from s0 and compare every
  snap's tree hash. Turns "replay is stream + snapshots" from a claim into a check. Prerequisite
  for Sprint 5 trace export.
- ~~**F3 `frame_ms=` in MANIFEST.**~~ **Done (session 13)** as a `FRAME … frame_us= tool_us=` log
  line per step (a MANIFEST cannot hold the time of the snap that writes it) + `bench stats`.
- **F4 Prerequisite blocks at parse time.** Refuse `EXEC` of a tool not on disk and `WAIT > T_tool`
  before any frame runs (new rule ids, not new verbs). Faults move from frame 7 to line 7.

### Tier 2 — useful, cheap

- **F5 `bench diff <snapA> <snapB>`.** Files added / removed / changed between two snaps, from their
  INDEX files (no content read unless asked). The obvious human question after a fault.
- **F6 `bench doctor`.** One screen: userns/landlock/seccomp availability, AppArmor userns sysctl,
  helper version, ROM crown, token source (env vs file), disk free. Replaces guessing on a new box.
- **F7 `BENCH_DURABLE=1`.** fsync for MANIFEST/STATE/CURRENT (see Open).
- **F8 Parallel harness.** Worlds are independent; `unittest` in 4 processes cuts `make test` from
  ~25 s toward ~8 s. See `TEST_BUDGET.md` for the folding plan.
- **F9 `bench explain <rule-id>`** prints the rule's page text offline (same data as the site's
  Rules page); agents get the "why" without a network.

### Tier 3 — bigger bets

- **F10 Content-addressed snap store.** Snaps hard-link into `sessions/objects/<sha>`; retention
  becomes refcounting, forks share everything. Depends on F1.
- **F11 Evidence as JSON Lines** alongside the log (`bench log --json`), one object per frame:
  drop-in for outside loops (Sprint 5) and for the site's status decoder.
- **F12 Trace export (Sprint 5).** A session → one self-contained tarball (OPS, MANIFESTs, INDEX,
  tree hashes), verifiable offline with `tools/hash.py`. Needs F2.
- **F13 Workers in a PID namespace + unprivileged uid.** *Owner-gated worker policy.*

## Suggested order

F1 → F2 → F4, then F5/F6 as the first human-facing tools (F3 done). The model-centric list in
[`IDEAS.md`](IDEAS.md) ranks hash-chained evidence, receipts and `bench try` first. Owner calls first: token fallback
(one line) and whether `BENCH_DURABLE` should be the default.
