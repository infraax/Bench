# GitHub settings (the owner's clicks)

Settings a session cannot change from files in git. Each is a few clicks on
`https://github.com/infraax/Bench`.

## Default branch

Today the default is `claude/bench-foundation-c015ut` (PR #3 merged into it). To make the product
tip a stable name:

1. **Settings → General → Default branch** → the switch icon → pick or create the branch (e.g.
   `main`, created from the current default) → **Update** → confirm.
2. Nothing in the tree hard-codes the branch name; links use `blob/HEAD/`, which follows the
   default.

## Pages (project site from `/docs`)

1. **Settings → Pages → Build and deployment → Source: Deploy from a branch.**
2. **Branch:** the default branch · **Folder:** `/docs` → **Save**.
3. After the first build (a minute or two) the site is at `https://infraax.github.io/Bench/`.
   `docs/_config.yml` sets the title and the plain `jekyll-theme-minimal` theme and excludes
   `docs/history/` and `docs/research/` (archival; linked on github.com instead).
4. Mermaid graphs render on github.com, not on the Pages site (no diagram JS is added); the site
   links to the github.com view of `architecture.md` for pictures.

Pages builds use Actions minutes on private repositories; see "Actions" below.

## About box and topics

On the repository home page, **About → ⚙ (edit)**:

- **Description:** `Custody kernel for agent work: five verbs, framed steps, sealed snapshots, owner-only crown. Linux, offline. Not an agent.`
- **Website:** `https://infraax.github.io/Bench/` (after Pages is on)
- **Topics:** `offline` · `linux` · `agent-runtime` · `sandbox` · `custody` (it is a custody kernel,
  not an autonomous agent)
- Tick **Releases**; untick **Packages** and **Deployments** unless used.

## Features

**Settings → General → Features:**

- **Issues:** on (templates: bug, spec amendment, tool crown).
- **Discussions:** optional.
- **Wikis, Projects, Sponsorships:** off unless wanted; the docs live in `docs/`.

## Actions

- The workflow `.github/workflows/test.yml` (job `rom-and-compile`) is already in the tree: it runs
  `make all` and `make test-rom`. It does not run the full worker suite ([`ci.md`](ci.md)).
- If runs fail with "no runner assigned": **Settings → Actions → General → Actions permissions**
  → allow actions; and for a private repository, **Settings (account or org) → Billing and
  plans** → Actions minutes / spending limit.

## Security

- **Settings → Security → Private vulnerability reporting:** enable, so `SECURITY.md`'s route works.
- **Code security:** secret scanning / push protection if available on the plan; Dependabot is not
  needed (no package ecosystem in the tree).
