# HANDOFF — instructions for the next session

Written 2026-09-28 at the end of a long session. Start the next session fresh and give it this file.

## Where the repo stands

- Branch `claude/bench-maintenance-3739it`. Last code commit: `3689c25` (docs for the hardening pass).
- `make test` green offline: `bus_test: ok`, 50 ROM + 117 harness. `make e2e` green.
- History of what shipped and why: `NOTES.md` (sessions 1–4), `DESIGN_REVIEW.md`, `EVOLUTION.md`, `TOOLBOX.md`.
- `research/` holds the raw audit of 22 other agent harnesses: pinned repos (`repos.tsv` + `fetch.sh`),
  line counts (`loc.txt`), code references per idea (`evidence.txt`), checked sources (`sources.md`).

## Tasks, in this order

Commit and push after each step. One small commit per logical change; `make test` green before every push.

### 1. `COMPARISON.md` — Bench vs the other harnesses

The owner has the full comparison from the previous session in chat. Either they paste it in to be
committed as-is, or rebuild it from `research/`. It must cover:
- what layer each harness is (loop vs custody/isolation vs eval vs meta-harness) and where Bench sits;
- the size table (`research/loc.txt`);
- where Bench is already ahead, and which public failures in other tools Bench's design already avoids
  (`research/sources.md`);
- gaps other tools close that Bench does not (see task 5 and task 6 below);
- the ranked list of ideas to copy, adapt, build later, or refuse.

### 2. `DEVELOPMENT_PLAN.md` — staged sprints

Group the ranked ideas into sprints that build on each other. Ideas to place (from the ranking):

- **Tier A (adapt):** gate as a list of policies (ALLOW/DENY/ASK + reason, fail closed, budgets) ·
  reversible, evidence-backed harness refinement through `proposed/` and a human crown · skills with
  progressive disclosure, kept in ROM · two-stage context compaction (rule-based elision, then summary) ·
  protected-paths table in ROM · credential placeholders for the future radio notch.
- **Tier B (later):** trace export as training data (Harness-Zero) · Bench as the custody kernel under
  another harness (Omnigent pattern) · model-aware action space (document the bash tradeoff) ·
  worktree-style cheap worlds · ACP host protocol.
- **Tier S already chosen for implementation:** see tasks 3–6.

Each sprint: goal, items, exit criteria (tests + a measured number), what it unlocks for the next sprint.

### 3. Refusals the model can act on

Every rejection the binary emits (parser faults in `parse_line`, runtime denies in `t_*`, gate stops in
`run_gate`) gets a stable rule id and a one-line fix:

```
FAULT line 2: ring: intern writes hold/ or proposed/ only, not main/x
  rule=write-ring fix: write under hold/ or proposed/; main/ is Ring 0
```

- One table in C (rule id → hint), mirrored as a ROM truth table (`tests/rom/test_refusals.py`).
- Harness test: every refusal row in `tests/rom/test_ops.py` `OPS_TABLE` prints its `rule=` and a
  non-empty `fix:`; the MANIFEST of a refused step carries `rule=`.
- No new verb. Evidence stays key=value.

### 4. Parallel worlds (`bench fork`)

Chosen approach: a world forked from a verified snapshot. It keeps "one process owns the frame clock
per world" and reuses snapshot, seal and verify.

- `bench fork <snap | session/snap> <new-world-dir>`: verify the snap's `board=`, then build a complete
  new world: copy `main/`, `tools/`, `isa/` and `tests/rom/`, and take `hold/` from the snap. The
  `supervisor/` binaries are used by path, not copied. Fresh `sessions/`, with `forked_from=` recorded.
  Refuse if the target exists.
- Copy, never hard-link, between worlds (a write in one world must never reach another).
- The new world is **not armed**; the owner arms it (or uses one `BENCH_TOKEN` for several worlds).
- Each world has its own `sessions/LOCK`, so N worlds run truly in parallel.
- Tests: fork round trip, damaged snap refused, target exists refused, unarmed until armed, a write in
  one world does not appear in the other, two worlds run at the same time.
- Measurement (`make perf` or `tests/perf/`): time to fork; N worlds × the same script run sequentially
  vs in parallel; report the speed-up. Assert parallel is clearly faster than sequential for N = 4.

### 5. Worker isolation: io_uring (owner has unfrozen `supervisor/sandbox.c`)

Codex's Linux filter denies the io_uring syscalls in every network-restricted mode (see
`codex/codex-rs/linux-sandbox/src/landlock.rs` after `sh research/fetch.sh codex`). Bench's filter does
not list them. Add them to Bench's deny list, with a harness test that a tool child cannot use them.

### 6. Worker isolation: namespaces (owner has unfrozen `supervisor/sandbox.c`)

Codex and sandbox-runtime run tool children in their own namespaces (via bubblewrap). Bench's tool
children see the whole filesystem as the owner's uid. Goal: a tool child sees only the world, so
snapshot sealing binds against it and reads outside the world are gone. Keep "fail closed if the
isolation cannot be set up". Tests + a measured per-child start-up cost.

## Ground rules (unchanged from earlier sessions)

- Five intern verbs only; no sixth. Owner commands (`restore`, `verify`, `fork`) are not verbs.
- Offline tests; ROM files pass `is_ring0`; no live model; `spec/` meaning frozen.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` plus the session link.
