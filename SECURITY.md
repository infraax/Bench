# Security

Bench is a custody kernel: its job is to keep an untrusted worker inside the world it was given.
A way out of that — a worker that writes Ring 0, reads outside the world, reaches the network,
signals or controls `bench` or the helper, arms a run without the owner's token, or edits a
sealed snapshot without `bench verify` noticing — is a security bug.

## Reporting

- **Privately:** use GitHub's **Report a vulnerability** button on this repository's Security tab
  (private vulnerability reporting). Include the smallest ops script or tool that shows it, the
  kernel and distribution (`make env` prints both), and whether bench ran as root.
- **Not privately:** anything that is not an escape (a wrong message, a doc error, a flaky test)
  goes in a normal issue with the `bug` template.

Please do not post an exploit in a public issue before a fix is available.

## What to expect

This is a small project maintained by one owner. There is no bug bounty and no response-time
guarantee. Reports are read, reproduced, and answered in the advisory thread; a fix lands as a
normal commit with a harness test that fails before it and passes after, and the advisory
credits the reporter unless asked not to.

## Scope notes

- Supported: Linux, the default branch, the tree as shipped (`README.md` → Requirements).
- Known limits are documented, not secret: see `docs/reference.md` (Tool children → Known limits)
  and the owner-gated items in `HANDOFF.md` (for example, workers share bench's pid space).
- The token file is v0 presence-only by design; a hardware key is out of this tree.
