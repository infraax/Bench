---
name: Tool crown
about: ask the owner to crown a drafted tool from proposed/ into tools/ (see docs/TOOLBOX.md)
labels: crown
---

**Tool**: `proposed/tools/<name>.py` → `tools/<name>.py`

**One job** (usage line, no "and"):

**Its ROM test**: `proposed/tests/test_<name>.py` (imports `run()`, checks argv errors, bounds, ev line)

**Evidence** — `tools/check.py` output for both files, and the snap ids of the session that drafted
them:

**Contract checklist** (`docs/TOOLBOX.md`):

- [ ] argv only, validated first, exit 2 on bad argv
- [ ] writes only under `hold/` or `proposed/`, atomic
- [ ] bounded output, last line `ev tool=<name> rc=…`
- [ ] offline, stdlib only, no subprocess, no eval/exec
- [ ] deterministic

The crown is the owner's act: move the file, `install_rom()` the test, `make` (new ROM hash).
