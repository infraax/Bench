# Comparison — Bench vs 22 agent harnesses

Rebuilt from `docs/research/` (audit of 2026-09-28): pinned repos in `docs/research/repos.tsv`, sizes in
`docs/research/loc.txt`, code references in `docs/research/evidence.txt`, checked sources in `docs/research/sources.md`.
Every claim about another tool below is either in `evidence.txt` (file:line at the pinned SHA) or in a
source listed in `sources.md`. Re-derive with `sh docs/research/fetch.sh && sh docs/research/evidence.sh`.

---

## 1. Layers — what each harness is

A "harness" means four different things in this set. Comparing across layers is how most comparisons
go wrong, so the layer comes first.

| Layer | Job | Harnesses |
|---|---|---|
| **Loop** | Prompt → model → tool call → observation → repeat. Owns context, tools, the model. | mini-swe-agent, SWE-agent, smolagents, aider, learn-claude-code, pi-mono, prime-agent, deepagents, OpenHands (agent side), gemini-cli, goose, opencode, codex (agent side), hermes-agent, qwen-code |
| **Custody / isolation** | Decides what a tool child may touch, and records what happened. Model-agnostic. | sandbox-runtime, codex `linux-sandbox`, OpenHands runtime, **Bench** |
| **Eval / environment** | Wraps a task as reset/step/state, scores it, limits it. | inspect_ai, verifiers, OpenEnv |
| **Meta-harness** | Composes, governs or rewrites other harnesses. | omnigent, harness-zero |
| **Protocol** | Wire format between an editor/host and a loop. | agent-client-protocol (ACP) |

**Where Bench sits:** the custody layer, with an eval layer's discipline about evidence. Bench has no
model and no loop. It owns the frame clock, the gate, the write rings, and a sealed, content-hashed
snapshot after every step. A loop (any of the fifteen above) would sit on top of it as the intern.
Nearest neighbours: sandbox-runtime (isolation only, no evidence) and inspect_ai (limits + evidence,
no custody of the filesystem).

---

## 2. Size

`docs/research/loc.txt`, code and test lines at the pinned SHA.

| Harness | Code | Test | × Bench (code) |
|---|---:|---:|---:|
| **Bench** | **3,079** | **2,175** | 1 |
| mini-swe-agent | 5,123 | 9,907 | 1.7 |
| SWE-agent | 12,691 | 2,490 | 4 |
| smolagents | 12,774 | 12,635 | 4 |
| sandbox-runtime | 21,932 | 43,898 | 7 |
| aider | 25,853 | 12,311 | 8 |
| learn-claude-code | 29,316 | 6,064 | 10 |
| verifiers | 34,971 | 3,973 | 11 |
| harness-zero | 43,768 | 328,864 | 14 |
| agent-client-protocol | 46,586 | 0 | 15 |
| OpenHands | 144,039 | 193,102 | 47 |
| OpenEnv | 144,380 | 61,976 | 47 |
| pi-mono | 185,124 | 179,560 | 60 |
| prime-agent | 207,851 | 164,373 | 68 |
| inspect_ai | 251,080 | 321,782 | 82 |
| gemini-cli | 291,961 | 400,398 | 95 |
| deepagents | 296,363 | 355,934 | 96 |
| goose | 362,939 | 55,413 | 118 |
| opencode | 506,762 | 176,966 | 165 |
| omnigent | 729,562 | 1,160,969 | 237 |
| codex | 1,056,601 | 960,951 | 343 |
| hermes-agent | 1,484,105 | 1,557,043 | 482 |
| qwen-code | 1,816,840 | 2,456,200 | 590 |

Reading: Bench is the smallest by a wide margin, and one of the few with a test/code ratio near 0.7
that is **offline and exhaustive where it can be** (`bus_test.c` covers every lamp and plug byte).
Size is not the point; readability of the whole custody path in one sitting is.

---

## 3. Where Bench is already ahead

| Property | Bench | Best elsewhere in the set |
|---|---|---|
| **Every step is evidence** | Sealed (0444/0555), content-hashed (`board=`), delta snapshot after every step; `bench verify` recomputes; `restore` checks before moving anything | gemini-cli: checkpoints in a shadow git repo (`evidence.txt`), not sealed, not verified before restore. aider: commit per edit, into the user's own repo |
| **Closed action set** | Five verbs, closed in C and Python, cross-checked by ROM tables through the binary | Every loop harness ships an open shell tool (`bash`, `shell`, `run_command`) |
| **Owner arming, re-checked every step** | Token pinned (dev, ino, mtime), re-checked by bench *and* the helper before every frame; removal disarms mid-run | Approval modes exist (codex, gemini-cli, inspect_ai approvers) but are checked per tool call, not per frame, and none survive as a physical "key out" |
| **Tests cannot quietly move the world** | `TEST` post-conditions hash `main/`, ROM, the token and prior snaps; any move disarms | None found |
| **Tool output is evidence by hash** | `out-<n>` pinned by sha256 in the MANIFEST; a tool cannot write a line into the log | deepagents offloads large results to files (`evidence.txt`) — for context size, not integrity |
| **Supervisor file ops cannot be steered** | Every component opened `O_NOFOLLOW` from a world-root dirfd; regular files only | Most loops resolve paths as strings |
| **ROM crown** | `tests/rom` hashed at build; `run` refuses if it changed | None found |

### Public failures Bench's design already avoids

Not "Bench would have caught it" — the *class* of failure has no path in Bench's design.

| Incident (`sources.md`) | Class | Why it has no path in Bench |
|---|---|---|
| Replit agent deleted a production database during a declared code freeze (AIID #1152) | Freeze stated in the prompt, not enforced | The freeze is structural: the intern cannot write `main/` (Ring 0) by any verb or tool; every step is snapped and restorable |
| Gemini CLI allowlist bypass (Tracebit) | An allowlisted command prefix smuggles a second command through the shell | No shell. `EXEC` takes whitespace tokens (no quoting, no `;`, no pipes) and runs a program under `tools/`; network syscalls return `EPERM` regardless |
| Claude Code CVE-2025-54794 / 54795 (Cymulate) | Path restriction by string prefix; command injection through an approved command | Paths are walked component by component from a dirfd with `O_NOFOLLOW`; no string-prefix check exists to bypass; no command line is ever parsed by a shell |

---

## 4. Gaps other tools close that Bench does not

| Gap | Who closes it | Bench before | Status |
|---|---|---|---|
| **io_uring not denied** | codex `linux-sandbox` denies the io_uring syscalls in every network-restricted mode | seccomp list does not name them; io_uring can do I/O the per-syscall filter never sees | **closed** `a8bebc9` (killed; x32 hole closed too, `1096ebc`) |
| **Tool children see the whole filesystem** | codex and sandbox-runtime run children in their own namespaces (bubblewrap) | landlock limits *writes* for `EXEC`; reads are open; `TEST` has no landlock; same uid, so the snapshot seal is advisory against tools | **closed** `80cf6bf` (mount + user namespaces) |
| **Refusals are not actionable** | sandbox-runtime attaches a model-facing reason to a denial; SWE-agent shows the lint error and the original code back | faults name *what* broke, not a rule id or *what to do instead* | **closed** `5504dfc` (`rule=` + fix) |
| **No parallelism** | qwen-code: a git worktree per parallel session; gemini-cli: shadow repo | one world, one lock, one frame clock | **closed** `6f94f4f` (`bench fork`, 3.7× at N=4) |
| **No policy list / ASK tier** | omnigent: ALLOW / DENY / ASK + reason, fail closed; inspect_ai: approvers and limits as objects | gate is a fixed sequence of checks in `frame()` | Tier A, sprint 3 |
| **No context management** | deepagents offload, pi-mono truncation bounds (2000 lines / 50 KB), compaction in most loops | out of scope (no loop), but the 4 KiB tty cap is a blunt instrument | Tier A, sprint 4 |
| **No replay** | inspect_ai logs are re-scorable; OpenEnv `reset/step/state` | `OPS` + snaps written, never re-run | `EVOLUTION.md` next #1 |

---

## 5. Ranked ideas

Verdicts: **build** (Tier S, chosen) · **adapt** (Tier A, reshape to fit five verbs and Ring 0) ·
**later** (Tier B, needs a notch or a prior sprint) · **refuse**.

### Tier S — build now

| # | Idea | From | Bench form |
|---|---|---|---|
| S1 | Actionable refusals | sandbox-runtime (model-facing reason), SWE-agent (lint rejection shows the fix) | `rule=<id> fix: <one line>` on every fault; ROM truth table of rule → hint |
| S2 | io_uring denied | codex `landlock.rs` | three syscalls on the seccomp deny list + harness test |
| S3 | Parallel worlds | qwen-code worktrees, gemini-cli shadow repo | `bench fork <snap> <dir>`: a verified snap becomes a new, unarmed world with its own lock |
| S4 | Namespaced tool children | codex / sandbox-runtime (bubblewrap) | mount + user namespace showing only the world; fail closed if it cannot be set up |

### Tier A — adapt

| # | Idea | From | Bench form | Constraint kept |
|---|---|---|---|---|
| A1 | Gate as a list of policies | omnigent (`ALLOW\|DENY\|ASK` + reason, fail closed), inspect_ai limits | `frame()` gate = ordered table of policies, each returns verdict + rule id; budgets become policies | ASK resolves only through the owner, never the intern; no new verb |
| A2 | Reversible, evidence-backed harness refinement | prime-agent `refine`, hermes curator (archive, never delete) | intern drafts to `proposed/`, cites snap ids as evidence; human crowns; the old version is archived, never deleted | crown is human; nothing runs before it is crowned |
| A3 | Skills with progressive disclosure | pi-mono, deepagents, learn-claude-code | a skill = a ROM file: one-line summary always visible, body readable by `READ` | skills are data in ROM, not code the intern runs |
| A4 | Two-stage compaction | deepagents offload, pi-mono truncation | stage 1 rule-based elision (bounded slice + pointer to `out-<n>`), stage 2 summary written to `hold/` | the full output stays pinned by hash; a summary is never evidence |
| A5 | Protected-paths table in ROM | codex (`.git`, `.agents`, `.codex` read-only inside writable roots) | `tests/rom/test_protected.py`: paths no ring may write, checked through the binary | table in ROM, enforcement in C |
| A6 | Credential placeholders | sandbox-runtime / omnigent secret handling | for the radio notch: tools see `{{name}}`, the supervisor substitutes on the wire | only behind the radio notch; secrets never enter `hold/` or a snap |

### Tier B — later

| # | Idea | From | Waits for |
|---|---|---|---|
| B1 | Trace export as training data | harness-zero | replay (so traces are proven), evidence key table |
| B2 | Bench as custody kernel under another harness | omnigent pattern | A1 policies + S4 namespaces; a loop drives `bench run` |
| B3 | Model-aware action space; document the bash tradeoff | empirical harness-design study (176 configs), prime-agent IPython kernel | a model slot; until then, write down why Bench has no shell |
| B4 | Worktree-style cheap worlds | qwen-code | S3 first; then reflink/CoW copy instead of full copy |
| B5 | ACP host protocol | agent-client-protocol | B2; ACP would speak to the loop, never to the intern directly |

### Refuse

| Idea | From | Why not |
|---|---|---|
| Commit after every edit into the working repo | aider (`auto_commits=True`) | writes the owner's tree; Bench's crown is a human act and `main/` is Ring 0 |
| An unbounded shell tool | every loop harness | a sixth verb in a costume (`TOOLBOX.md`) — and the root of the Gemini CLI and CVE-2025-54795 class |
| Automatic lifecycle transitions of skills/harness by a background agent | hermes curator (auto-transitions) | keep only its invariant (archive, never delete); the transition itself is the owner's |
| Auto-raising a limit, retrying a faulted step | loops with retry-on-limit | makes the budget mean "until the intern likes it" (`history/DESIGN_REVIEW.md`, refusals) |
| MCP as world ontology | goose, opencode, others | world state stays files; MCP only as a `tools/` program behind radio (`EVOLUTION.md`) |
| A model in core as judge | eval harnesses with LLM scorers | a judge is a dirty device; it can annotate, never crown |
