# HANDOFF — 2026-09-28 (session 8: CI split)

One page. Facts, not a diary; history is in `docs/history/`.

## Head

- Branch: `claude/handoff-start-004f8n` (the product tip; the default branch is the owner's setting) · pushed
- Code head before this file: `f038429`
- Last green ledger rows (local, gitignored):
  - `ledger/20260928-112345-f038429.1/summary.md` — `make test`: exit 0 · bus ok · ROM 55 · harness 146 · 17.7 s
  - `ledger/20260928-112308-c26733f/summary.md` — `make test-rom`: exit 0 · bus ok · ROM 55 · 0.2 s
- `make e2e`, `make perf`: green in session 6; not re-run (no code path they cover changed)

## Done this session

- `c26733f` make: `test-rom` — bus test + ROM suite, no worker children
- `f038429` ci: the hosted job is `rom-and-compile` (`make all`, `make test-rom`); it no longer claims the worker suite
- `docs: ci split and handoff` — `docs/ci.md`; README, `docs/agent.md`, `docs/RELEASE.md` say which gate is where

## Owner calls — decided

- **Branch:** stay on `claude/handoff-start-004f8n`; no merge, no default-branch rename from a session.
- **Actions:** the owner enables Actions / minutes in repository settings when hosted runs are
  wanted. Sessions do not poll it. (Run 36413183428 failed with no runner assigned.)
- **Hosted CI vs full suite:** hosted = compile + `test-rom`; full `make test` = the ledger on a
  Linux box that runs the worker view. No sysctl / AppArmor / privileged-container changes.
- **SPDX on `supervisor/sandbox.c`:** left off; the project license covers it.
- **`main/` `hold/` `sessions/` at the root:** kept; they are the world's working dirs.

## Open owner calls

- A Linux machine (self-hosted runner or a box) that already runs the worker view, if the full
  gate should run outside a session. Until then the ledger row is the record.

## Leftover (owner-gated, unchanged)

- PID namespace and an unprivileged uid for workers — worker policy.
- Prerequisite blocks (`EXEC` of a missing tool, `WAIT` over `T_tool` at parse); `frame_ms=` in MANIFEST.
- Test structure from `docs/TEST_BUDGET.md`; the v1 toolbox (`docs/TOOLBOX.md`).

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
