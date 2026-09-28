# Development plan — staged sprints

Built from the ranking in `COMPARISON.md` §5. Each sprint builds on the one before. No sprint adds a
verb; owner commands (`restore`, `verify`, `fork`) are not verbs. Every sprint ends with `make test`
green offline and one measured number committed to the tree.

```
S1 refusals + io_uring ──► S2 worlds + namespaces ──► S3 policy gate + protected paths
                                                          │
                                   S5 kernel under a loop ◄── S4 skills, compaction, refinement
```

---

## Sprint 1 — Say no clearly, close io_uring

**Goal:** every refusal is a rule the model can act on; the cheapest known filter gap is closed.

| Item | Source | Detail |
|---|---|---|
| Refusal rule ids + fix hints | S1 | one C table `rule id → hint`; `parse_line`, `t_*` denies and `run_gate` print `rule=<id> fix: <hint>`; MANIFEST of a refused step carries `rule=` |
| ROM truth table | S1 | `tests/rom/test_refusals.py` mirrors the C table |
| io_uring deny | S2 | `io_uring_setup`, `io_uring_enter`, `io_uring_register` on the seccomp deny list |

**Exit criteria**

- Harness: every refusal row in `OPS_TABLE` prints `rule=` and a non-empty `fix:`.
- Harness: a tool child calling `io_uring_setup` gets `EPERM` (or dies), never a ring fd.
- **Number:** refusal coverage = refused rows with a rule id ÷ refused rows = **100 %**.

**Unlocks:** S3's policy table reuses the rule ids as policy names.

---

## Sprint 2 — Many worlds, each one sealed

**Goal:** N worlds run in parallel; a tool child sees only its world.

| Item | Source | Detail |
|---|---|---|
| `bench fork <snap> <dir>` | S3 | verify `board=`, copy `main/ tools/ isa/ tests/rom/`, `hold/` from the snap, fresh `sessions/` with `forked_from=`; refuse if target exists; copy, never hard-link; new world unarmed |
| Namespaced tool children | S4 | user + mount namespace; the world bind-mounted, `/usr` `/lib` read-only for the interpreter, nothing else; fail closed if setup fails |

**Exit criteria**

- Fork: round trip, damaged snap refused, target exists refused, unarmed until armed, no write leaks
  across worlds, two worlds run at once.
- Namespaces: a tool child cannot read a file outside the world; cannot chmod a sealed snap; setup
  failure = child does not run.
- **Numbers:** fork time; N = 4 worlds × same script, sequential vs parallel, speed-up asserted
  clearly > 1 (`tests/perf/`); per-child start-up cost with and without namespaces.

**Unlocks:** worlds are cheap and isolated → S4 can try refinements in a forked world; S5 can hand a
world to an outside loop.

---

## Sprint 3 — The gate becomes a policy list

**Goal:** the gate is data, not a hard-coded sequence.

| Item | Source | Detail |
|---|---|---|
| Policy list | A1 | ordered table: KILL, token, helper, budgets, rings; each returns `ALLOW\|DENY\|ASK` + rule id; first DENY wins; unknown result = DENY |
| ASK | A1 | stops the frame (no step, no snap) with `ask=<rule>`; only the owner resolves it, by re-running armed. The intern cannot answer an ASK |
| Protected-paths table | A5 | `tests/rom/test_protected.py`: paths no ring may write (`sessions/`, token names, `.git`, ROM); C enforces, harness replays |

**Exit criteria**

- Every policy has a ROM row; removing a policy from C fails the harness.
- Fail-closed test: a policy that errors yields DENY.
- **Number:** gate cost per frame before vs after (must stay within `T_frame`; target < 1 ms added).

**Unlocks:** budgets and ASK as data → S4 refinements can propose policy changes as files.

---

## Sprint 4 — Knowledge in ROM, context kept small, refinement by crown

**Goal:** the intern learns across sessions without anything running uncrowned.

| Item | Source | Detail |
|---|---|---|
| Skills | A3 | `rom/skills/<name>.md`: first line = summary (always shown), body via `READ`; `is_ring0`-checked, crowned like tests |
| Two-stage compaction | A4 | stage 1: tool output > budget → bounded slice + `see out-<n> sha256=…`; stage 2: summary written to `hold/notes/`, marked `dirty=1`, never evidence |
| Refinement through `proposed/` | A2 | intern drafts `proposed/skills/…` or `proposed/policy/…` citing `snap=` ids; human crowns; replaced version moved to `rom/archive/`, never deleted |

**Exit criteria**

- A skill is invisible until crowned; its summary appears in `status`/prompt material after.
- A crowned refinement can be reverted by the owner in one command, byte-identical.
- **Number:** bytes of tool output reaching the intern per session, before vs after stage 1.

**Unlocks:** a loop on top has something to read and a way to improve that the owner controls.

---

## Sprint 5 — Bench under someone else's loop

**Goal:** Bench is the custody kernel; an outside loop is the intern.

| Item | Source | Detail |
|---|---|---|
| Kernel mode | B2 | a loop emits the five verbs as lines; Bench frames them; evidence goes back as the observation |
| Model-aware action space note | B3 | `ACTION_SPACE.md`: why no shell, what it costs on public benchmarks, when to revisit |
| Trace export | B1 | after replay exists: one JSONL line per verified step (op, evidence, `tree=`), only from sessions that replay clean |
| Credential placeholders | A6 | only with the radio notch; spec amendment first |
| Cheap worlds / ACP | B4, B5 | reflink copy for `fork`; ACP only between host and loop |

**Exit criteria:** one outside loop (mini-swe-agent: smallest, 5 k lines) runs a task through Bench
with every step snapped. **Number:** overhead per step vs the same loop without Bench.

---

## Not scheduled

Refused ideas (`COMPARISON.md` §5, Refuse) stay refused. `EVOLUTION.md` "phase next" items (replay,
evidence key table, wall clock, the v1 toolbox) run alongside: replay must land before S5's trace export.
