# CI

Gates, split by what the machine can prove.

| Gate | Command | Proves | Where |
|---|---|---|---|
| build | `make all` | the C builds with `-Wall -Wextra -Werror` | hosted CI and locally |
| algebra | `make test-rom` | exhaustive bus test (C, no worker) + the Ring-0 ROM suite (pure python) | hosted CI and locally |
| site | `make site-check` | the site's rule/ops data matches `refusal.c` and the ROM table; the playground parser agrees with every `OPS_TABLE` row | hosted CI and locally (needs node) |
| custody | `make test` / `make ledger-test` | all of the above + the harness: frames, clock, lock, helper, snapshots, fork, **worker children** | a Linux box that can build the worker view; the ledger row is the record |
| deep | `make test-deep` | differential + metamorphic fuzzing, errno and SIGKILL sweeps with an independent evidence audit, mutation testing ([`TESTING_KIT.md`](TESTING_KIT.md)) | locally, by choice; report in `ledger/deep-*/` — never in hosted CI |

**Why the split.** The harness starts worker children, each in its own mount namespace (plus a
user namespace when not root), with landlock and seccomp. A hosted runner is not root, and
Ubuntu's AppArmor commonly refuses unprivileged user namespaces, so workers would fail closed
(`rule=worker-setup`). Loosening the runner (sysctls, AppArmor, privileged containers) is a
worker-policy change and owner-gated; the workflow does not do it.

**One check, on push.** `.github/workflows/test.yml` (workflow `check`, job `rom-and-compile`)
runs on every push — no timer, no duplicate pull-request run — with no third-party actions: plain
`git` checkout, `make env`, `make all`, `make test-rom`, `make site-check`.

**If runs fail in seconds with no steps.** Open the run page and read the annotation. On
2026-09-28 every run said: *"The job was not started because your account is locked due to a
billing issue."* That blocks all user workflows on the account (GitHub's own Pages build still
runs). It is fixed in the account's **Settings → Billing and plans**, not in the workflow; agents
do not poll it.

**What counts.** A change is green when `make ledger-test` is green on a Linux box that runs
workers, and its `summary.md` is cited. Hosted CI green means "builds, algebra holds" — no more.
