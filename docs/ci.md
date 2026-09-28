# CI

Two gates, split by what the machine can prove.

| Gate | Command | Proves | Where |
|---|---|---|---|
| build | `make all` | the C builds with `-Wall -Wextra -Werror` | hosted CI and locally |
| algebra | `make test-rom` | exhaustive bus test (C, no worker) + the Ring-0 ROM suite (pure python) | hosted CI and locally |
| custody | `make test` / `make ledger-test` | all of the above + the harness: frames, clock, lock, helper, snapshots, fork, **worker children** | a Linux box that can build the worker view; the ledger row is the record |

**Why the split.** The harness starts worker children, each in its own mount namespace (plus a
user namespace when not root), with landlock and seccomp. A hosted runner is not root, and
Ubuntu's AppArmor commonly refuses unprivileged user namespaces, so workers would fail closed
(`rule=worker-setup`). Loosening the runner (sysctls, AppArmor, privileged containers) is a
worker-policy change and owner-gated; the workflow does not do it.

**Actions may be off.** If the repository has no Actions minutes or Actions is disabled, runs
fail before any step ("no runner assigned"). That is a repository setting, not a test failure; the
owner enables Actions / minutes when hosted runs are wanted. Agents do not poll it.

**What counts.** A change is green when `make ledger-test` is green on a Linux box that runs
workers, and its `summary.md` is cited. Hosted CI green means "builds, algebra holds" — no more.
