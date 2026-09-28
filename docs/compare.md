# Where Bench sits

Layers, not a brand war. "Agent harness" means different things; compare within a layer.
Full audit (22 repos pinned by commit, sizes, file:line evidence, the ranked idea list):
[`history/comparison-2026-09-28.md`](https://github.com/infraax/Bench/blob/HEAD/docs/history/comparison-2026-09-28.md) and [`research/`](https://github.com/infraax/Bench/tree/HEAD/docs/research).

| Layer | Job | Examples (audited 2026-09-28) |
|---|---|---|
| **Loop** | prompt → model → tool → observe → repeat; owns the model and context | mini-swe-agent, SWE-agent, smolagents, aider, pi-mono, OpenHands, gemini-cli, goose, opencode, codex, qwen-code |
| **Custody / isolation** | what a worker may touch, and what happened | sandbox-runtime, codex `linux-sandbox`, OpenHands runtime, **Bench** |
| **Eval / environment** | a task as reset/step/state, scored and limited | inspect_ai, verifiers, OpenEnv |
| **Meta-harness** | composes or rewrites other harnesses | omnigent, harness-zero |
| **Protocol** | host ↔ loop wire format | agent-client-protocol |

**Bench is custody** with an eval layer's discipline about evidence: no model, no loop. A loop sits
on top and drives the intern.

## What Bench does that the layer usually does not

- A sealed, content-hashed snapshot after **every** step; `verify` before `restore` or `fork`.
- A closed action set (five verbs) instead of an open shell.
- The owner's token re-checked before every frame; removing it stops the next step.
- `TEST` steps cannot move `main/`, ROM, the token or prior snapshots (worker view + frame hashes).
- Every refusal names a stable rule and a fix.
- Small: ~3 k lines of code, readable in one sitting.

## What it leaves to others

A model, context management, a policy list with an ASK tier, network access for workers, replay —
see [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md).
