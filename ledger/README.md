# ledger/

The project's run book. One directory per run, so an agent reports a **summary and a path**, not
a pasted log. Payloads are gitignored; only this README and `.gitkeep` are tracked.

```
ledger/
  latest -> <stamp>-<sha>          newest row (symlink)
  <YYYYMMDD-HHMMSS>-<gitsha>/
    ENV.txt                        machine card (scripts/agent-setup.sh, `make env`)
    <command>.txt                  full stdout+stderr, e.g. make-test.txt
    <command>.exit                 exit code
    summary.md                     exit, wall seconds, ROM / harness counts, bus_test, failures
```

Write rows with `make env`, `make ledger-test`, or `scripts/ledger-run.sh <command...>`.

**Never here:** token files or their contents, `sessions/` dumps, snapshots, anything from outside
the repo. The ledger holds what a command printed, nothing it read. Clear it with
`find ledger -mindepth 1 ! -name README.md ! -name .gitkeep -delete`.
