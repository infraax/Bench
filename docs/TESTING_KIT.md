# Testing kit — the adversarial pass

`make test` asks "does Bench do what the tests say?". The deep kit asks the questions a test
suite cannot ask itself:

- **Do two implementations of one meaning actually agree?** (differential)
- **Does the output move exactly when it should?** (metamorphic)
- **What happens when the disk says no, or the machine dies, at *every* possible point?**
  (fault injection, power cut)
- **Would the tests notice if the code were wrong?** (mutation)

One command runs all of it and writes one report:

```
make test-deep                 # full: ~5 min on 4 CPUs
make test-deep DEEP=--quick    # ~1 min, a pre-push check
make test-deep DEEP=--c        # full + C mutation testing of the parser (+6 min)
```

The report lands in `ledger/deep-<stamp>-<sha>/` (gitignored): `summary.md` holds the table,
and each tool's `.txt` and `.json` sit beside it. Exit 0 means every tool is green.

The deep pass is **not** in CI and **not** in `make test`. It is slow, it needs `strace`, `cc`
and `node`, and a finding from it is a design conversation, not a red build.

---

## The tools

### 1. `fuzz_parse.py`: three judges, one line

**What.** It generates script lines from the ops grammar and from byte mutations of the ROM
`OPS_TABLE` rows. Three judges rule on each line:

| Judge | Implementation | Why it is here |
|---|---|---|
| C | `bench check` | the binary's own `parse_line` and refusal prediction |
| JS | `docs/assets/js/ops-check.js` | the site playground's mirror: what humans and agents read |
| RUN | `bench run` in a throwaway world | ground truth, for every disagreement and a random sample |

**Why.** A mirror is a promise ("the site tells you what bench will do"), and a promise
nobody checks will drift. Hand-written rows test what a person thought of. The generator is
built from what people forget:
- byte lengths at 127/128/255/256 with multibyte UTF-8;
- Unicode case folding;
- `\v` and `\f` as separators;
- NUL and CR;
- `+5`, `05` and full-width digits;
- every limit ±1.

**Found (2026-09-28), each now a ROM row or a corpus seed:**
- `WAIT 1\0x`: `fgets` misreported a NUL byte as `line-long`, and `check` swallowed the next
  line. Bench now reads lines by length, and there is a new rule, `line-nul`.
- `TEſT …`: JS `toUpperCase()` folds U+017F to `S`, so the site accepted a verb bench refuses.
- `WAIT \v2`: `strtoul` skips a leading `\v`, so bench ran it as `WAIT 2`.
- `WAIT 1\r\rx`: the site's `/[\r\n].*$/` stops at the second CR, so it kept a stray `\r`.

**How it shrinks.** Delta debugging (ddmin) reduces a disagreeing line to the smallest one
that disagrees the same way. The result goes to `tests/deep/corpus/parse/<hash>.json` along
with all three verdicts. The corpus is replayed first on every run.

```
python3 tests/deep/fuzz_parse.py [--n 6000] [--seed S] [--oracle 80] [--json out.json]
```

### 2. `hash_fuzz.py`: one hash, two implementations, and relations that must hold

**What.** It builds random hostile trees and hashes each one with `sha256.c` (via
`supervisor/romhash <root> <tree>`) and with `tools/hash.py`. Each tree is then transformed:

| Must not move the hash | Must move the hash |
|---|---|
| another creation order | one byte flipped |
| mtime/mode change | one byte appended |
| an empty dir | a file renamed |
| a symlink or a fifo | an empty file added |
| `*.pyc` and `__pycache__/`, under `tests/rom` only | two contents swapped |
| | a file moved into a subdir |
| | under `hold/`: bytes parked in a `.pyc`-named dir |

Framing pairs check that two different trees never share a hash.

**Why.** A differential test cannot catch a bug that both implementations share. A metamorphic
relation can. The name set targets the classic walker bug: `'/'` sorts between `'.'` and `'0'`,
so `a/b`, `a.b` and `a0` order differently per directory than they do per path.

**Found:** both implementations skipped `*.pyc` and `__pycache__` everywhere, `hold/` included.
A tool could park bytes in `hold/x.pyc/` that no `tree=` or `board=` covered, so `bench verify`
could not see changes to them. `hold/` now skips nothing, and the ROM crown is unchanged.

```
python3 tests/deep/hash_fuzz.py [--trees 200] [--seed S]
```

### 3. `faultinj.c` + `fault_sweep.py`: the disk says no, at every call

**What.** `faultinj.so` is an `LD_PRELOAD` shim that makes the Nth call of one of 13 libc
functions fail with a chosen errno. The functions are `open`, `openat`, `mkdir`, `rename`,
`link`, `write`, `read`, `fopen`, `fclose`, `opendir`, `chmod`, `unlink` and `rmdir`. Only the
process named `bench` is affected, and only in its own pid: the helper and the workers pass
through.

The sweep counts one clean workload's calls (every verb, delta snaps, retention). It then
replays the workload once per (function, N) and holds the world to five invariants:

| Invariant | Rule |
|---|---|
| I1 no crash | an exit code 0..7, never a signal or a hang |
| I2 honest exit | exit 0 only if every op framed and status says ok |
| I3 no torn evidence | every snap verifies by `bench verify` **and** `scripts/evidence-audit.py`, and every older session is still whole |
| I4 recoverable | the next clean run in the same world exits 0 |
| I5 no orphans | no process is left with its cwd in the world |

**Why.** Error paths are the least-run code in any program, and custody lives in them. Sweeping
every call site turns "we handle errors" into "we handled all 1,000 of them".

**Found:**
- **Dishonest exit 0:** exit 0 while the final `STATE` write had failed, so `status` then said
  `crashed`.
- **Unpinned output passed:** a step passed with its out file unpinned (`sha256=unreadable`).
- **Torn sessions:** retention cut short left a half-deleted session that read as torn
  evidence. The old code produced 43 violations, the fix produces 0.

```
python3 tests/deep/fault_sweep.py [--max 40] [--fn rename,link] [--errno 28] [--json out.json]
FI_FN=rename FI_NTH=3 FI_ERRNO=5 LD_PRELOAD=tests/deep/faultinj.so supervisor/bench run s.ops   # one repro
```

Litter (`snap-<k>.tmp` left by a failed snap) is counted but is not a violation. It is what a
fail-closed stop leaves behind.

### 4. `powercut_sweep.py`: the machine dies, at every syscall

**What.** It runs `strace --inject=<syscall>:signal=KILL:when=N` on the supervisor alone. No
cleanup handler runs; the helper and the workers see their parent vanish. The invariants:

| Invariant | Rule |
|---|---|
| P1 | no torn evidence |
| P2 | status never says ok or run for a killed session |
| P3 | the next clean run exits 0 |
| P4 | nothing outlives the supervisor |

**Found:** bench killed mid-`EXEC` (`kill -9`, OOM) left the worker running with no knife and
no snap, still writing `hold/`. Workers now set `PR_SET_PDEATHSIG`, pinned by
`test_a_worker_dies_with_a_killed_supervisor`.

```
python3 tests/deep/powercut_sweep.py [--max 12] [--sys rename,openat] [--json out.json]
```

### 5. `mutate.py`: test the tests

**What.** It makes small wrong versions of the code and checks that some test fails for each.
Every mutant runs in a private copy of the tree, never in this checkout.

- `--lang py`: AST mutants of `isa/*.py`: flipped comparisons, and/or, a dropped `not`,
  changed constants, dropped set members, negated returns. The ROM suite judges them in seconds.
- `--lang c`: operator mutants inside chosen functions of `main.c` (`parse_line`, `predict`,
  `line_bad`, `read_line`). Each is built with `-Werror` and judged by the harness classes that
  pin those functions.

A **SURVIVED** line means one of two things: a behaviour no test pins (write the test), or an
equivalent mutant (list it below).

**Found:**
- **Python, 61.5% → 92.8%:** 83 denylist names could be removed with no test noticing.
  `tests/rom/test_rom_denylist.py` now pins every member in every reachable form. The survivors
  also showed that `is_ring0` missed a door named without a call (`f = eval`, `[exec][0]`,
  `__builtins__[...]`), which is now closed.
- **C parser, 64.7% → 82.1%:** every limit is now tested on both sides (`TestParseEdges`).

**Known equivalent mutants.** They survive by construction; they are not gaps.
- Python-version gates in `hotz_isa.py`: the 3.10 branch doesn't run on 3.11+.
- `Ring` enum numbering: identity, not value, carries meaning.
- `n.args[1:2]` → `[1:3]` in the getattr check: it would also flag a default argument.
- The `Call` branch for `DIRTY_CALL` in `is_ring0`: the bare-name rule now covers it.
- In C:
  - buffer sizes grown by one;
  - `predict`'s `fs-cap` check: a payload under 256 bytes never reaches 4096;
  - `read_line`'s store bound: lines that long are refused anyway;
  - `a[0] <= '9'` → `a[1]` in the `WAIT` lead check: `strtoul` + `*end` reject the rest.

```
python3 tests/deep/mutate.py [--lang py|c] [--func parse_line,predict] [--min-score 0.9] [--json out.json]
```

### 6. `scripts/evidence-audit.py`: the second witness

**What.** It re-derives every claim in every session of a world, in Python, reusing only
`tools/hash.py`, which `TestHashParity` pins to the C:
- the snap chain is contiguous;
- `board=` matches the stored `hold/`;
- each `out=` pin matches its file;
- seals are 0444/0555;
- `STATE` agrees with the last `MANIFEST`;
- `FRAME` lines match the snaps.

**Why.** `bench verify` is C checking C. An independent witness means one bug cannot hide in
both. Run it on a real world any time:

```
make audit-evidence                       # this world
python3 scripts/evidence-audit.py <world> [--json out.json] [--session ID]
```

---

## Adding to the kit

- **A new judge** (for example a WASM build of the parser): add a `judge_*` function to
  `fuzz_parse.py` and compare it with `norm()`.
- **A new invariant:** add it to `fault_sweep.check_world` and it applies to both sweeps.
- **A new mutation site:** name a function with `--func`; the harness classes that pin it go
  in `--tests`.
- **A seed worth keeping:** commit its `corpus/parse/*.json` with a `why`.

## Costs (4 CPUs, 2026-09-28)

| Tool | Quick | Full |
|---|---|---|
| fuzz_parse | 1,500 lines, <1 s | 6,000 lines + 80 real runs, ~10 s |
| hash_fuzz | 40 trees, 2 s | 200 trees, ~3,000 checks, ~8 s |
| fault_sweep (EIO) | 93 runs, 31 s | ~260 runs, ~70 s |
| fault_sweep (ENOSPC) | 50 runs, 17 s | ~155 runs, ~40 s |
| powercut_sweep | ~20 kills, ~8 s | ~67 kills, ~26 s |
| mutate py | 250 mutants, ~20 s | same |
| mutate c | — | ~100 mutants, ~6 min |
