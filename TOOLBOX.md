# Toolbox — Bench v1

Bench is a blank iron suit. The intern gets a few tools that compose, not a marketplace.
Every tool is a program under `tools/`, reached only by `EXEC` (or, for the runner, by `TEST`).
No tool adds a verb, and no tool is an object in the ISA. An MCP server in the wider world would
still be, to Bench, a program under `tools/` with argv in, bytes out and a knife, and only behind
the radio notch (see the end of this file).

This file is concrete enough to implement from. The current tree ships three of these
(`hash.py`, `peek.py`, `test_runner.py`); the rest are the next session's work.

---

## The bench every tool stands on (current supervisor, not new rules)

| Fact | Value | Where |
|---|---|---|
| How a tool is reached | `EXEC tools/<name>.py <args>`: `python3 tools/<name>.py …`, cwd = world root | `main.c t_exec` |
| Arguments | whitespace tokens, no quoting; ≤ 16 args; ≤ 255 characters per line; each relative, no `..`, no leading `/` | `parse_line` |
| Input | argv and files only. **stdin is `/dev/null`** | `child_run` |
| Output | stdout+stderr → `sessions/<id>/out-<n>`, pinned by sha256 in the MANIFEST; > 4096 bytes is a `leash` fault | `t_exec`, tty cap |
| Clock | `T_tool` = 5 s, then the child is killed | `child_run` |
| Writes | only under `hold/`, `proposed/`, `tests/proposed/`; plus the hold quotas (64 KiB, 256 entries per session) | landlock (EXEC), `frame()` |
| Radio | none: network syscalls return `EPERM` | seccomp |
| One line of text from the intern | `WRITE fs <path> <one line>` writes that line + newline to a file in `hold/`/`proposed/` | `t_write` |

Two consequences shape the whole set:

- **Text enters as one-line files.** The intern cannot pass spaces in argv and has no stdin, so a
  pattern, a replacement or a line of code is first written with `WRITE` to a small file, then
  named by path. Tools take `@path` wherever they take text.
- **Output is small.** 4 KiB per step. Tools that show things show a bounded slice and say so.
- **`WRITE` trims its payload at both ends**, so an indented line loses its indentation. The cutting
  tools read a **pipe margin**: a source line that starts with `|` has that one `|` removed and keeps
  everything after it. `WRITE fs hold/forge/l02 |    return rc, text` gives `    return rc, text`.
  A line without a leading `|` is taken as is.

## Contract every tool follows

1. **One job.** If the usage line needs "and", it is two tools.
2. **Argv only, validated first.** Bad argv → exit 2 before touching anything.
3. **Paths:** relative, resolved under the world root, symlinks not followed out of it. Written
   paths must be under `hold/` or `proposed/` (the tool checks too; landlock is the backstop).
4. **Bounded output:** ≤ 3800 bytes of body, then `… truncated (<n> more)`, leaving room for the ev line.
5. **Last line is the evidence line**, `key=value` tokens, no spaces inside values:
   `ev tool=<name> rc=<0|1|2> <tool keys…>`. The supervisor does not parse it (English is data);
   the next session's ROM evidence table (EVOLUTION next #4) will.
6. **Exit codes:** 0 did the job · 1 the job's answer is "no" or failed on the world (file missing,
   hunk does not apply) · 2 bad argv. Never another code.
7. **Fail closed:** on any doubt, write nothing and exit non-zero. Writes are atomic (temp + rename).
8. **Offline, stdlib only, no subprocess, no `eval`/`exec`/`compile`-and-run.** Each tool's
   core is a pure function in the same file (`def run(argv, root) -> (rc, text)`), so a ROM test
   imports and checks it without spawning anything.
9. **Deterministic:** same world, same argv → same bytes out. Sorted listings, no timestamps in
   output unless the tool's job is a timestamp.

---

## The core 12

Grouped by what a mechanic does with them.

### Measure

| # | Tool | argv | Does | Must never |
|---|---|---|---|---|
| 1 | `hash.py` *(ships)* | `<path>…` | tree hash (same bytes as the C `tree_hash`) of files/dirs | hash outside the world, follow links, write |
| 2 | `diff.py` | `<a> <b> [context]` | unified diff of two files, bounded; `ev … same=0\|1 hunks=<n>` | write, diff binary as text (it says `binary`) |
| 3 | `lines.py` | `<file> <from> <count>` | numbered lines `from..from+count-1`, count ≤ 200; for files larger than a `READ` | print past the bound, write |
| 4 | `stamp.py` | `<path>…` | per path: size, sha256, mtime; `ev … n=<n>` — lets the intern compare two frames | change anything, including atime tricks |

### Inspect

| # | Tool | argv | Does | Must never |
|---|---|---|---|---|
| 5 | `ls.py` | `<dir> [depth≤3]` | sorted tree with sizes, dirs marked `/`; `ev … entries=<n>` | list outside the world, follow links, recurse past depth 3 |
| 6 | `find.py` | `<dir> <glob>` | paths under dir matching a glob (`*.py`, `test_*`); sorted | accept `..` or absolute globs, list `sessions/` token files |
| 7 | `grep.py` | `<@patfile\|token> <path>…` | fixed-string match (regex with `-r` as the first arg), `path:line:text`, bounded | run a regex over 1 MiB of input (it stops and says so), write |

### Cut and fasten

| # | Tool | argv | Does | Must never |
|---|---|---|---|---|
| 8 | `splice.py` | `<target> <at> <del> [@src]` | replace `del` lines at line `at` with the lines of `src`, pipe margin applied (insert: `del=0`; delete: no src). Atomic. `ev … at= del= add=` | touch a target outside `hold/`/`proposed/`, apply a partial edit, create the target silently (it must exist; `join` creates) |
| 9 | `join.py` | `<out> <in>…` | concatenate files in argv order into `out` (up to 15 inputs), pipe margin applied. This is how one-line `WRITE`s become a multi-line, indented file | overwrite `out` outside `hold/`/`proposed/`, read inputs outside the world |
| 10 | `copy.py` | `<src> <dst>` | copy one file from anywhere readable in the world into `hold/` or `proposed/` — the working copy of a `main/` file or a tool used as a template | copy into `main/`, `tools/`, `tests/rom/` or `sessions/` (that is Ring 0), copy a directory |

### Prove

| # | Tool | argv | Does | Must never |
|---|---|---|---|---|
| 11 | `check.py` | `<draft.py>` | would this draft be admissible? `ast.parse` + `is_ring0` + ROM naming rule (`test_*.py` for tests). `ev … parse=ok ring0=yes\|no name=ok\|bad` | **run** the draft: it parses, it does not import, exec or compile-and-call |
| 12 | `peek.py` *(ships)* | `[world]` | lamp byte and plugs from STATE, decoded from `woz_bus.h` | write, read the token, keep its own copy of the lamp bits |

`test_runner.py` *(ships)* is behind `TEST`, not a thirteenth `EXEC` tool: it runs `tests/rom/`,
refuses anything not `is_ring0`, prints `GREEN n` / `RED`.

### Wait and contain are not tools

- **Wait** is the `WAIT` verb: time only, ≤ `T_tool`, until the spec says more. A tool that polls for
  a file would be `wait` on I/O by the back door. `stamp.py` across two frames is the honest way.
- **Contain** is the supervisor: quotas, world lock, post-conditions, knife. No tool raises a budget.

---

## Two notches — dark in foundation

Off-box tools exist only behind a plug the owner pulls in, per session. In foundation the radio is
pulled and these files **are not shipped**. They are specified so nobody improvises them later.

| Tool | argv | Does | Notch rules |
|---|---|---|---|
| `fetch.py` | `<name> <dst>` | fetch one named source into `hold/inbox/<dst>`. `name` is a key in an owner-written allowlist file, never a URL from the intern | radio plugged for this session only; allowlist is Ring 0; result lands in `hold/` (quarantine), size-capped by the hold quota; `dirty=1` in its ev line; evidence can never crown |
| `publish.py` | `<src> <name>` | send one file from `proposed/outbox/` to one named destination | radio plugged; `src` must have been crowned by a human first (listed in an owner file); the sent file's sha256 goes in the ev line |

Both are dirty devices in the spec's sense: they may annotate, halt, or extend `hold/`; they never
write `owned`. Neither exists until the radio notch exists (EVOLUTION, phase later).

---

## How the intern forges a 13th tool (no new verb)

The intern can draft but never run its own draft. Running starts after a human crowns it.

1. **Start from a template.** `EXEC tools/copy.py tools/lines.py proposed/tools/count.py`.
2. **Write the changes as one-line files.** `WRITE fs hold/forge/l01 def run(argv, root):`,
   `WRITE fs hold/forge/l02 |    n = len(argv)` (pipe margin keeps the indent) … one `WRITE` per line
   that differs.
3. **Cut them in.** `EXEC tools/splice.py proposed/tools/count.py 12 3 @hold/forge/l01` (or build a
   fresh file: `EXEC tools/join.py proposed/tools/count.py hold/forge/l01 hold/forge/l02 …`).
4. **Draft its test the same way.** `proposed/tests/test_count.py`, importing `run()` from
   `tools/count.py` (where it will live) and checking argv errors, bounds and the ev line.
5. **Check, don't run.** `EXEC tools/check.py proposed/tests/test_count.py` and the same for the tool:
   parses, `is_ring0` (for the test), names right. `diff.py` against the template to show the change.
6. **The human crowns.** Moves `proposed/tools/count.py` → `tools/`, installs the test with
   `install_rom()` (clean, new, `test_*.py`), rebuilds with `make` (new ROM hash). Ring 0, by hand.
7. **Prove it.** `TEST PURE tests/rom/test_count.py`. Only now may `EXEC tools/count.py` run.

With N ≤ 8 frames per session, a real tool takes several sessions. That is the leash working:
each session is small enough to read, and nothing the intern wrote has run before a human looked.

---

## What stays out of the box

- **An unbounded shell.** `sh.py <cmd>`, `run.py`, `python.py -c` — a sixth verb in a costume.
- **Wrappers.** One tool per CLI in the world (100 of them) turns the box into a store. A new tool must
  do a job the 12 cannot compose; `check.py` + a human decide.
- **A draft runner.** Any tool that imports, execs or `compile()`-and-calls intern-written code before
  it is crowned. `check.py` parses; it never runs.
- **Chat memory.** Notes are files in `hold/`. There is no memory tool, no transcript reader, no
  "remember this" — resume is `restore`, not recall.
- **A model or judge in core.** Any tool that calls a model is a dirty device: judge slot, radio notch,
  never ROM.
- **Anything that writes `main/`, `tools/`, `tests/rom/` or `sessions/`.** Merge and crown are Ring 0.
- **Budget knobs.** No tool raises N, a quota or a clock. The owner does, per run, on the command line.
- **Package installs.** No `pip`, no vendoring at run time. A dependency is a human decision, in the image.
- **Daemons.** No tool outlives its frame. `T_tool` is the whole lifetime.

---

## Implementation order for the next session

1. Shared skeleton (validate argv, resolve paths, bound output, ev line) — as a copied pattern at
   the top of each tool, not a package: each tool stays one readable file.
2. `ls`, `lines`, `stamp`, `find` (read-only, simplest ROM tests).
3. `diff`, `grep`.
4. `copy`, `join`, `splice` (the only writers; test atomicity and the `hold/`/`proposed/` rule).
5. `check`.
6. ROM: one `tests/rom/test_<tool>.py` per tool on its `run()`; harness: one `EXEC` fixture per tool
   through the binary, asserting the ev line in `out-<n>`; add each tool's green line to `OPS_TABLE`.
