# HANDOFF — 2026-09-28 (session 10: the site)

One page. Facts, not a diary; history is in `docs/history/`.

## Head

- Default branch (product tip): `claude/bench-foundation-c015ut` at `06f5db1` (PR #4 merged).
- This session's branch: `claude/handoff-start-004f8n`, restarted from `06f5db1`, pushed:
  `6a40e62` theme · `4290914` pages · `36f2bfd` diagrams · and this file. Docs-only; no C, ROM,
  Makefile or `sandbox.c` change.
- `make test-rom`: bus ok · ROM 55 · green. `make ledger-test` not re-run (no code change); last
  full row `ledger/20260928-112345-f038429.1` (55 ROM, 146 harness).

## Done this session

- **Site: files added.** Custom Jekyll theme in `docs/` (`_layouts/`, `assets/css/crypt.css`,
  `assets/js/site.js`, `_data/perf.yml`, `_data/compare.yml`), five pages: Home (product board),
  Architecture (`/architecture/`, verb explorer), Compare (`/compare/`, filterable), Measure
  (`/measure/`, CSS bars), Start (`/start/`). Pre-rendered SVG diagrams in `assets/diagrams/`.
- Built locally with the `github-pages` gem (Jekyll 3.10) at `baseurl /Bench`; headless Chromium
  at 390 and 1280 px: no 4xx, no JS errors, no horizontal page scroll; wide diagrams scroll inside
  their card on a phone, with a condensed phone version of the process graph.

## Owner calls — open

- **Pages: the owner hard-refreshes** `https://infraax.github.io/Bench/` after this branch reaches
  the default branch (Pages builds from the default branch's `/docs`).
- Unchanged from `docs/github.md`: default branch name, About blurb and topics, private
  vulnerability reporting, Actions permissions/minutes.

## Keep in step

- Numbers on the site live in `docs/_data/perf.yml`, copied from `docs/PERF_AND_MAP.md`: change
  the doc first, then the data file.
- Diagrams: edit the Mermaid in README / `docs/architecture.md`, copy to
  `docs/assets/diagrams/src/`, re-render (see its README), run `fix_size.py`.

## Leftover (owner-gated, unchanged)

- PID namespace and an unprivileged uid for workers — worker policy.
- Prerequisite blocks; `frame_ms=` in MANIFEST; test structure (`docs/TEST_BUDGET.md`); the v1 toolbox.

## Do not touch

- `spec/` meaning · no sixth verb · `supervisor/sandbox.c` unless the owner reopens worker policy
- No trackers, no CDN, no blog; no second workflow running `make test` on hosted runners.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
