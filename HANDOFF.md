# HANDOFF — 2026-09-28 (session 9: public face)

One page. Facts, not a diary; history is in `docs/history/`.

## Head

- Default branch (product tip): `claude/bench-foundation-c015ut` at `d3d1186` — PR #3 merged.
- This session's branch: `claude/handoff-start-004f8n`, restarted from `d3d1186` (fast-forward),
  pushed; docs-only commits on top: `63bbd16`, `bd7e63b`, `6bc6ac7`, and this file.
- `make test-rom`: bus ok · ROM 55 · green. No Makefile or code change, so `make ledger-test` not
  re-run; last full row: `ledger/20260928-112345-f038429.1` (55 ROM, 146 harness, green; same code).
- All six Mermaid blocks (README 2, `docs/architecture.md` 4) parse and render with mermaid-cli 11.

## Done this session

- `63bbd16` docs: README badges (license, Linux, hosted CI = compile + test-rom), "custody crypt,
  not an agent", process graph and layer graph; architecture: same graphs + frame sequence + rings
- `bd7e63b` docs: Pages home `docs/index.md`, `docs/_config.yml` (plain Jekyll, minimal theme,
  excludes history/ and research/), `docs/github.md` (the owner's clicks)
- `6bc6ac7` docs: `SECURITY.md` (private vulnerability reporting, no bounty), `.github/CODEOWNERS` (@infraax)

## Owner calls — open (all are Settings clicks, listed in `docs/github.md`)

- **Pages: the owner flips the switch** — Settings → Pages → Deploy from a branch → default
  branch, `/docs`. Site: `https://infraax.github.io/Bench/`. Mermaid renders on github.com only.
- Default branch name (a stable `main` if wanted), About blurb and topics, private vulnerability
  reporting, Actions permissions/minutes.

## Owner calls — decided (unchanged)

- Hosted CI = compile + `make test-rom`; the full gate is `make ledger-test` on a box that runs
  workers. No sysctl / AppArmor / privileged-container changes. `sandbox.c` keeps no SPDX line.

## Leftover (owner-gated, unchanged)

- PID namespace and an unprivileged uid for workers — worker policy.
- Prerequisite blocks (`EXEC` of a missing tool, `WAIT` over `T_tool` at parse); `frame_ms=` in MANIFEST.
- Test structure from `docs/TEST_BUDGET.md`; the v1 toolbox (`docs/TOOLBOX.md`).

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- No second workflow running `make test` on hosted runners; no diagram JS on the site.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
