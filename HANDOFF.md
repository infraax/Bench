# HANDOFF — 2026-09-28 (session 7: housekeeping)

One page. Facts, not a diary; history is in `docs/history/`.

## Head

- Branch: `claude/handoff-start-004f8n` · pushed · product tip is described as `main` in the README;
  GitHub's default branch has not been changed (owner call below)
- Last green ledger row: `ledger/20260928-110052-1b1e863.1/summary.md` (local, gitignored)
- `make test`: bus ok · ROM 55 · harness 146 · wall 22.1 s (via `make ledger-test`)
- `make e2e`: green (session 6) · `make perf`: green (session 6)
- CI run 1 (`bf68ec1`, run 36413183428): **failed before any step** — no runner was assigned
  (runner_id 0, 3 s, no logs). Not the tests: Actions is off or out of minutes/billing for the account.

## Done this session

- `96a2e86` legal: MIT OR Apache-2.0 (LICENSE, LICENSE-MIT, LICENSE-APACHE, NOTICE, THIRD_PARTY.md, SPDX lines)
- `1642c41` docs: stranger's README; handbook, architecture, compare, agent, handoff template, RELEASE;
  old README body → `docs/reference.md`; session docs → `docs/history/`; `research/` → `docs/research/`
- `e1de9f2` scripts: `make env` (machine card) and `make ledger-test` (ledger row, summary only)
- `bf68ec1` ci: Linux `make test` workflow; issue templates (bug, spec amendment, tool crown)

## Open owner calls

- **Default branch.** Rename or point GitHub's default at `main` (repo settings); no history rewrite.
- **Enable Actions / runner minutes** for `infraax/Bench`, then re-run run 36413183428.
- **CI as non-root.** GitHub runners are not root; Ubuntu 24.04's AppArmor may refuse unprivileged
  user namespaces, which makes every worker fail closed (`rule=worker-setup`). If the first run that gets a
  runner is red for that reason, the options are: allow it on the runner
  (`sysctl kernel.apparmor_restrict_unprivileged_userns=0` in the workflow), run the job as root in
  a container, or accept Linux-root-only CI. Not decided here; `sandbox.c` untouched.
- **SPDX on `supervisor/sandbox.c`** when that file is next opened.

## Leftover (owner-gated, from session 6)

- PID namespace and an unprivileged uid for workers — worker policy.
- Prerequisite blocks: `EXEC` of a missing tool, `WAIT` over `T_tool` at parse; `frame_ms=` in MANIFEST.
- Test structure from `docs/TEST_BUDGET.md` (fold duplicate FIXTURES, `repeats=`, parallel classes).

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
