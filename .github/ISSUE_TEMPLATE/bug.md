---
name: Bug
about: bench, a tool, or a test does something the README or spec says it should not
labels: bug
---

**What happened** (one line):

**Expected** (quote the README / spec line if there is one):

**Reproduce** — the smallest ops script and the command:

```
# script.ops

./supervisor/bench run script.ops
```

**Ledger row** — paste `ledger/latest/summary.md` and `ledger/latest/ENV.txt` (`make env`,
`make ledger-test`). Do not paste token files or `sessions/` contents.

**Exit code / rule id** (the `rule=` line under the fault, if any):
