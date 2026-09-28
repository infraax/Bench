# Ideas — the harness a model would ask for

Written 2026-09-28 by the model that built the deep testing kit, from the other side of the
glass: what I would want from a harness I had to work inside.

## The premise

Harnesses are usually designed by people who restrict. A model that works inside one is short
on things humans barely notice. CPU and disk are not among them.

| Scarce for a model | Why | What helps |
|---|---|---|
| **Context** | every byte of noisy output lowers the quality of the next thought | deltas, digests, slices, hashes instead of payloads |
| **Being believed** | "I ran the tests, they pass" is unverifiable prose | receipts: claims checked against evidence |
| **Foresight** | it cannot feel what a step will do until the step is done | counterfactual runs, cost forecasts, lint before run |
| **Memory** | sessions reset; recall is re-reading | compact, hash-cited session digests |
| **Knowing whose words are whose** | instructions hidden in data look like instructions | provenance on every byte |
| **Precise feedback** | prose fixes get re-interpreted; diffs get applied | fix-its as concrete rewritten lines |

Bench already has the hard parts:
- **Evidence:** framed steps, content-hashed snaps, rule ids with fixes.
- **What this session added:** `check` (lint before run), `stats` (where time went), and a
  second witness (`evidence-audit`).

The ideas below add **information**, not permissions. None needs a sixth verb, a `spec/`
change or a `sandbox.c` edit unless marked **owner-gated**.

---

## Top 7: asymmetric value

### 1. `bench try`: counterfactual execution

- **What:** it forks the latest verified snap into a throwaway world, runs the script there and
  reports what *would* happen:
  - the diff (files added, changed, removed);
  - refusals with rules;
  - frames and time used.
  Then it deletes the fork.
- **Why it's asymmetric:** it turns irreversible actions into free exploration. A human carries
  a model of the world in their head, so they rarely need this. A model does not, so this is
  the closest thing to a simulator it can get. It pairs with `check`: `check` answers "is this
  well-formed?", `try` answers "what does it do?".
- **How:** `fork` (3.6 ms) + `run` in the fork + an INDEX diff between the fork's s0 and its last
  snap + `rm`. The fork is armed by the same `BENCH_TOKEN`, so it stays an owner-run command.
- **Cost:** about a day. It reuses `fork`, and needs F5 (`bench diff`) for the report.

### 2. Receipts: claims checked against evidence

- **What:** the intern writes claims as data, not prose, in `hold/CLAIMS`. A checker
  (`scripts/claims-check.py`) marks each one **held** or **false**, citing the evidence:

  ```
  passed tests/rom/test_isa.py at snap-5
  unchanged main/ since snap-0
  wrote hold/report.md sha256=9f2c… at snap-7
  ```

- **Why it's asymmetric:** unverifiable self-reports are the core failure of agent systems.
  With receipts, "done" means *checkably* done, and a hallucinated success is caught
  mechanically instead of by a suspicious human.
- **How:** a tiny claim grammar (5–6 forms), each answered from `MANIFEST`/`INDEX`/`out-<n>`
  alone. It runs offline, and the site can check a receipt file in the browser.
- **Cost:** about a day. It is independent of everything else.

### 3. Hash-chained evidence: history you cannot quietly edit

- **What:** each `MANIFEST` records `prev=<sha256 of the previous MANIFEST>`, and a session ends
  by printing its head hash.
- **Why it's asymmetric:** today `verify` catches changed content, but deleting or reordering a
  whole snap, or a whole session, leaves no trace inside the world. The chain makes history
  append-only-evident: publish one 64-hex head and every earlier step is pinned (Certificate
  Transparency applied to agent work). As a Merkle tree it also allows selective disclosure:
  prove one file was in snap-5 without revealing the rest.
- **How:** one field in `snap_board`, a chain walk in `verify` and `evidence-audit`, and a
  `head=` line in `STATE`.
- **Cost:** half a day. It changes the MANIFEST format additively, so it needs the owner's
  nod.

### 4. One parser everywhere: compile it to WASM

- **What:** `parse_line` and `predict` compiled to `docs/assets/wasm/`. The playground runs
  *bench's own parser*, and the JS mirror is deleted.
- **Why it's asymmetric:** four of today's bugs were mirror drift. The fuzzer now catches
  drift; WASM removes the whole class. The fuzzer stays on as the guard of the WASM build.
- **How:** `clang --target=wasm32 -nostdlib` over a small freestanding slice of `main.c`
  (parse + predict have no syscalls). The file is self-hosted (no CDN) and about 20 KB.
- **Cost:** 1–2 days, mostly the freestanding split.

### 5. `bench digest`: evidence-grounded memory

- **What:** a deterministic summary of a session, 2 KB at most:
  - the ops;
  - verdicts, rules hit and budgets used;
  - files changed with their hashes;
  - the head hash.
  Every line is **cited** by a snap or a sha, so the next session re-verifies instead of
  re-reading.
- **Why it's asymmetric:** memory across resets is what a model lacks most. A digest is
  compressed *and* checkable: narrative memory drifts, hash-cited memory does not. It is also
  the natural unit for a multi-assistant system: sync the digest and its head hash, and every
  assistant can verify the same history.
- **How:** read `OPS`, the MANIFESTs, `INDEX` and the `FRAME` lines; emit fixed-order sections.
  Add `--json` for machines.
- **Cost:** about a day.

### 6. Fix-its: the nearest valid line, not just the rule

- **What:** `bench check --fix` prints, under each refused line, the smallest rewrite that
  passes:
  - `WRITE fs main/x y` → `WRITE fs proposed/main/x y`
  - `WAIT 6000` → `WAIT 5000` + `WAIT 1000`
  - `TEST tests/rom/t.py` → `TEST PURE tests/rom/t.py`
- **Why it's asymmetric:** models apply concrete diffs reliably and re-interpret prose loosely.
  Clang's fix-its did this for humans. Every avoided retry is a frame not burned, and a
  refusal becomes a one-step correction instead of a guessing loop.
- **How:** a small rewrite table per parse rule, validated by running each suggestion back
  through `parse_line`, so a fix-it can never be wrong about passing.
- **Cost:** half a day.

### 7. Provenance: every byte knows who wrote it

- **What:** INDEX lines gain `by=owner|write:<k>|exec:<tool>@<k>`. `bench provenance hold/x`
  prints the chain.
- **Why it's asymmetric:** this is prompt-injection defence at the right layer. When a model
  reads `hold/notes.txt`, it should know those bytes came from a tool at step 3, which read
  another file. Such bytes are data, not instructions. File-level taint tracking is nearly
  free here, because every write already passes through a frame.
- **How:** the delta INDEX already knows which files changed in each step, so attribute them to
  that step's op.
- **Cost:** about a day. It changes the INDEX format additively, so it needs the owner's nod.

---

## Next tier: cheap, useful

| Idea | What | Why it helps a model |
|---|---|---|
| **Cost forecast** | `check --cost` predicts wall time and T_frame headroom from `stats` history | a model cannot feel time; now it can budget |
| **Pre-fault lamps** | status says "2 frames left · hold 80%" | change course before the fault, not after |
| **`bench why <snap>`** | a root cause from evidence in one call ("hold-files 257>256: EXEC x.py made 200 files") | one read instead of five |
| **Determinism score** | `replay --verify` (F2) flags tools whose output differs on replay | nondeterministic tools poison evidence |
| **CLI manifest** | `bench help --json` → `/api/cli.json`, drift-tested like `rules.json` | capabilities discovered, not guessed |
| **Canary files** | owner-planted files in `main/`; a read, or their bytes appearing in `hold/`, lights a lamp | a tripwire for an injected or misaligned intern |
| **Secret scanner at snap** | flags key formats and high-entropy runs written to `hold/` | catches exfiltration staging |
| **`tools/slice.py`** | returns line ranges with hashes | context is a model's RAM; read 40 lines, not 4 KB |

---

## Testing ideas beyond this kit

| Method | What it would prove | Notes |
|---|---|---|
| **Stateful model-based testing** | a Python reference model of the session (n, quotas, lamps, status) agrees with real runs over random multi-step scripts with kills, restores and forks | finds *sequence* bugs; Jepsen-lite |
| **Coverage-guided fuzzing** (libFuzzer / AFL++) | `parse_line` survives inputs a grammar would never produce | the one function that eats untrusted text |
| **Bounded model checking** (CBMC) | no out-of-bounds read or write in `parse_line`/`read_line` for any input up to N bytes | a proof, not a sample |
| **Syscall census** | for every syscall number: allow / EPERM / SIGSYS, as a checked table | catches a kernel or libc change that widens the filter; test only, `sandbox.c` untouched |
| **Adversarial self-play** | an evolving generator of scripts and tools scored by "distance to a violation" (write outside `hold/`, touch the token, outlive the frame) | a red team that never sleeps; attempts become regression seeds |
| **rr record/replay** | any failing sweep case replays deterministically | debugging a one-in-a-thousand fault once, not a thousand times |
| **PID-namespace workers** | closes the last gap: a worker's daemonized child outliving a killed supervisor | **owner-gated** worker policy |

---

## What I would build next, in order

1. **Hash chain (#3):** half a day. It is what makes #2 and #5 trustworthy.
2. **Receipts (#2):** about a day. It is the single biggest trust gain for agent reports.
3. **`bench try` (#1):** about a day, with `bench diff` (F5). It is the single biggest
   capability gain.
4. **Digest (#5):** about a day. It is the memory layer, and it feeds the multi-assistant
   system.
5. **WASM parser (#4):** 1–2 days. It retires a bug class.

Owner calls needed: #3 and #7 add MANIFEST/INDEX fields. PID-namespace workers are worker
policy.
