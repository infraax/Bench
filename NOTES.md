# NOTES

## Session 4 — hardening + adversarial pass

### Start

- Head `ae9a22d`, tree clean. `make test`: bus ok, 50 ROM + 99 harness, green.

### Owner asks

| Ask | Commit | Result |
|---|---|---|
| File quota → 256 | `bench: file quota default 256` | Default now snaps inside T_frame (1024 new files ≈ 350 ms > 200 ms budget). |
| Linked snaps — properly solve | `bench: seal snapshots read-only` + `bench: verify` | Two layers: sealing (0444/0555, prevention, non-root) + `board=` content hash and `bench verify` (guarantee, root-proof). restore checks board= first. |
| TEST covers `sessions/` | `bench: TEST post-conditions cover the session's snapshots` | pre/post hash of SESSION, OPS, every prior snap; `moved=sessions` disarms. |

### Adversarial pass — breaks found and fixed

| # | Break | Commit |
|---|---|---|
| 1 | **Root escape**: intern-planted symlink in hold/ + supervisor WRITE (as owner) wrote outside the world. Proven. | `bench: WRITE/READ symlink escape` — O_NOFOLLOW component walk anchored at the world root |
| 2 | **Frame-clock hang**: a tool mkfifo'd in hold/, a READ blocked the supervisor forever. Proven. | `bench: READ/WRITE refuse fifos and devices` — O_NONBLOCK + S_ISREG |
| 3 | **Disk DoS**: tool output streamed to out-<n> with no cap. | `bench: hard output ceiling` — killed past 1 MiB |

### Root reality

- This container runs as **root**; tool children run as root too (sandbox.c drops syscalls, not uid).
  Mode-bit sealing is therefore advisory against the tools — the content hash (`bench verify`) is the
  real guarantee, and the sealing tests prove denial via a **setuid-nobody child**, not as root.

### Left open (honest, none are new escapes)

- A tool can **read** any file the owner can (it is root) and READ/print it — not a new capability
  (it could already print to stdout); consistent with the model (leash is on writes/network/crown).
  The fix is an unprivileged tool uid / mount namespace = sandbox.c, out of scope.
- `snap-<k>.tmp` litter from a faulted snap; self-limiting, retention reclaims it.
- `T_session` never binds at foundation budgets; lamp byte constant; Python mirrors C by tables.

### End

- `make test` from a clean tree: `bus_test: ok`, **50 ROM + 117 harness**, green, offline. `make e2e`
  green; `bench verify` on the e2e session passes (checked=6).
- Every `tests/rom/*.py` passes `is_ring0`. No socket in ROM. No sixth verb.
- `supervisor/sandbox.c`, `sandbox.h`, `spec/`: not touched. No live model.

### Exit codes now

0 ok · 1 fault (incl. output ceiling, symlink/fifo refusal) · 2 usage · 3 killed · 4 ROM changed ·
5 not armed / disarmed / tainted · 6 helper missing/silent/lost/wrong version · 7 world busy / demo running.
`verify`: 0 intact · 1 mismatch/damaged · 2 usage.

---

## Session 3 — implementation pass (review → code)

### Start

- Head `a1bad86`, tree clean. `make test`: bus ok, 46 ROM + 51 harness, green, offline.

### Shipped, in order

| Item | Commit | Notes |
|---|---|---|
| M2 token identity | `bench: M2 token identity` | Landed before M1: M1 reuses the token pin. Regular file, runner's uid, not g/o-writable; (dev, ino, mtime) pinned; checked every frame. |
| M1 TEST post-conditions | `bench: M1 test postconditions` | `main/`, `tests/rom/` hashes + raw token stats before/after each TEST. Fault → disarmed (exit 5), board not snapped, touched token renamed `.tainted-<id>`. `is_ring0` unchanged. |
| M3 split the log | `bench: M3 split the log` | `out-<n>` per step, `out=` sha256 in MANIFEST. READ bytes moved out of the log too. |
| M4 world lock | `bench: M4 world lock` | **fcntl, not flock** — `F_GETLK` names the holder pid, which is what `kill` needs as proof. Exit 7 when busy. `crashed` status. |
| M6 file quota | `bench: M6 file quota` | Done before M5 so the status line could show it. Counts files + dirs. |
| M5 status --line | `bench: M5 status --line, helper version pin` | Plus the cheap mailbox item: `PING` must answer `helper v0`. |
| S7 snap by delta | `bench: S7 snap by delta` | Measured first: copy 344 ms vs link 8 ms per 1000 files on this disk. INDEX with ino/size/mtime/ctime. |
| S8 restore | `bench: S8 restore a snap` | Owner command. Hash check before anything moves; old hold/ kept as `hold.before`. |
| S9 demo | `bench: S9 demo inside reach` | `sessions/DEMO` lock, knife = 5 s × ROM files. |
| S10 ops table | `bench: S10 ROM ops table through the binary` | 45 rows. Verified a flipped row fails. |
| S11 retention | `bench: S11 session retention` | Keep 20; never CURRENT, `hold.before`, or non-session dirs. |

Docs: README rewritten to the tree; `DESIGN_REVIEW.md` status block; new `EVOLUTION.md`, `TOOLBOX.md`.

### S-items not shipped

- **None.** S7–S11 all landed with tests. Nothing fought the five-verb ISA: `restore`, `status --line`,
  retention and `demo` are owner commands; no intern op was added.

### Found while implementing (recorded in DESIGN_REVIEW status block)

- Linked snaps share inodes; a write under `sessions/` changes every linked snap (restore detects it).
- TEST post-conditions do not yet cover `sessions/` beyond the token.
- Default file quota (1024) vs `T_frame` (200 ms): 1024 **new** files in one step ≈ 350–390 ms to snap.
  Owner call: lower the default or make `T_frame` per notch.
- `WRITE` trims its payload, so indented code cannot be written line by line; `TOOLBOX.md` answers
  with the pipe margin in `join`/`splice`.

### End

- `make test` from a clean tree: `bus_test: ok`, **50 ROM + 99 harness**, green, offline. `make e2e` green.
- Every `tests/rom/*.py` passes `is_ring0`. No socket in ROM.
- No sixth verb; mailbox words and supervisor words are refused by the parser (OPS_TABLE).
- `supervisor/sandbox.c`, `sandbox.h`, `spec/`: not touched. No live model.

### Exit codes now

0 ok · 1 fault · 2 usage · 3 killed · 4 ROM changed · 5 not armed / disarmed / tainted ·
6 helper missing/silent/lost/wrong version · 7 world busy / demo running.

---

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
