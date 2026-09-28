# Starting an agent session on this repo

Every agent (and every human) boots the same way, so reports compare.

## 1. Machine card, then tests — before inventing work

```
make env            # scripts/agent-setup.sh: prints the card, writes ledger/<stamp>-<sha>/ENV.txt
make ledger-test    # scripts/ledger-run.sh make test: full log to the ledger, summary to stdout
```

`make env` installs nothing. If something is missing it prints the exact install line and exits 2.

This is the full gate and it runs worker children: do it on a Linux laptop or box. `make test-rom`
(bus + ROM, no workers) is the smaller gate hosted CI runs; it never replaces `make ledger-test`.

## Hosted CI

`.github/workflows/test.yml` runs `make all` and `make test-rom` only ([`ci.md`](ci.md)). Actions
may be off for this repository (runs fail with no runner assigned): the owner enables Actions /
minutes in the repository settings when hosted runs are wanted. Do not poll Actions, and do not
change sysctls, AppArmor or worker policy to make a runner look like the local box.

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
