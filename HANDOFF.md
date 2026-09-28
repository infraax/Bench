# HANDOFF — 2026-09-28 (session 11: CI cause, site round 2)

One page. Facts, not a diary; history is in `docs/history/`.

## Head

- Default branch (product tip): `claude/bench-foundation-c015ut` at `eed6b35` (PR #5 merged).
- This session's branch: `claude/handoff-start-004f8n`, from `eed6b35`, pushed: `e96e32c`, `5647da3`,
  `d04e09e`, `a4e338b`, and this file. No C, ROM or `sandbox.c` change.
- `make test-rom`: green (bus ok, ROM 55). `make site-check`: green. `make ledger-test` not re-run
  (no code change); last full row `ledger/20260928-112345-f038429.1`.

## CI: cause found

- Every Actions run fails before a runner is assigned. The run page annotation says:
  **"The job was not started because your account is locked due to a billing issue."**
  Account-level; blocks all user workflows. Pages builds are separate and kept deploying.
- **Owner:** account Settings → Billing and plans → fix payment / lock. Nothing in the repo can.
- The workflow is now one push-only check, no third-party actions, `ubuntu-24.04`:
  `make env`, `make all`, `make test-rom`, `make site-check`. Verified locally step by step.

## Site: round 2 (live after merge + hard refresh)

- New pages: Playground (script checker + status decoder), Rules (38, anchored, searchable),
  Agents (grammar, protocol, endpoints). Machine side: `/llms.txt`, `/api/*.json`, `sitemap.xml`.
- Home: "would bench take it?" line and two doors (people / agents). README: site link + badge.
- Drift guard: `scripts/site-data.py` regenerates `docs/_data/{rules,ops}.json` from `refusal.c`
  and the ROM table; `tests/site/parity.mjs` proves the playground parser agrees (in CI).

## Keep in step

- Change a rule or an OPS_TABLE row → `python3 scripts/site-data.py`, commit the JSON.
- Change parse rules in `main.c` → mirror in `docs/assets/js/ops-check.js`; `make site-check`.
- Numbers: `PERF_AND_MAP.md` first, then `docs/_data/perf.yml`. Diagrams: see `docs/assets/diagrams/src/README.md`.

## Leftover (owner-gated, unchanged)

- PID namespace and an unprivileged uid for workers — worker policy.
- Prerequisite blocks; `frame_ms=` in MANIFEST; test structure (`docs/TEST_BUDGET.md`); the v1 toolbox.

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- No trackers, no CDN, no blog; one CI check, compile + ROM + site, never the worker suite on hosted runners.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
