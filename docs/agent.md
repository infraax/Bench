# Starting an agent session on this repo

Every agent (and every human) boots the same way, so reports compare.

## 1. Machine card, then tests — before inventing work

```
make env            # scripts/agent-setup.sh: prints the card, writes ledger/<stamp>-<sha>/ENV.txt
make ledger-test    # scripts/ledger-run.sh make test: full log to the ledger, summary to stdout
```

`make env` installs nothing. If something is missing it prints the exact install line and exits 2.

## 2. Report the summary, not the log

Paste `summary.md` (what `make ledger-test` printed) and cite the path to the full log. Do not
paste `make test` output into chat. For any other command:

```
scripts/ledger-run.sh make e2e
scripts/ledger-run.sh make perf
```

## 3. Read the handoff

`HANDOFF.md` (one page, from `docs/handoff.template.md`): head SHA, test counts, open owner calls,
what not to touch. History lives in `docs/history/`.

## 4. Ground rules

- Five verbs. No sixth; owner commands (`restore`, `verify`, `fork`, `rules`) are not verbs.
- `spec/` meaning is frozen. A change of meaning is a spec-amendment issue, text only.
- Tests stay offline. ROM files pass `is_ring0`. No live model.
- Never put tokens or `sessions/` contents in the ledger, a commit, or a chat.
- One small commit per concern; `make test` green before every push.

## 5. End of session

Fill `HANDOFF.md` from `docs/handoff.template.md` (not a chat log), with the ledger row of the
last green `make ledger-test`.
