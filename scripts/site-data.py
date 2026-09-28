#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""site-data.py — build the site's data from the tree, so the site cannot drift from the binary.

  docs/_data/rules.json   every refusal rule in supervisor/refusal.c: id, fix, phase
  docs/_data/ops.json     every row of the ROM OPS_TABLE, with the rule OPS_RULES names

  python3 scripts/site-data.py           write both files
  python3 scripts/site-data.py --check   exit 1 if either file is stale (CI, make site-check)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "rom"))
from test_ops import OPS_TABLE  # noqa: E402
from test_refusals import OPS_RULES  # noqa: E402

PHASES = {"parse": "parse", "run": "run", "gate": "gate"}


def rules():
    out, phase = [], None
    for line in (ROOT / "supervisor" / "refusal.c").read_text().splitlines():
        m = re.match(r"\s*/\* (parse|run|gate):", line)
        if m:
            phase = PHASES[m.group(1)]
            continue
        m = re.match(r'\s*\{"([a-z0-9-]+)",\s*"((?:[^"\\]|\\.)*)"\},', line)
        if m:
            out.append({"id": m.group(1), "fix": m.group(2), "phase": phase})
    return out


def ops():
    return [{"line": line, "expect": expect, "rule": OPS_RULES.get(line)} for line, expect in OPS_TABLE]


def render():
    return {
        "rules.json": json.dumps(rules(), indent=1, ensure_ascii=False) + "\n",
        "ops.json": json.dumps(ops(), indent=1, ensure_ascii=False) + "\n",
    }


def main():
    check = "--check" in sys.argv[1:]
    stale = []
    for name, text in render().items():
        p = ROOT / "docs" / "_data" / name
        if check:
            if not p.exists() or p.read_text() != text:
                stale.append(str(p.relative_to(ROOT)))
        else:
            p.write_text(text)
            print("wrote", p.relative_to(ROOT))
    if stale:
        print("site-data: stale, run `python3 scripts/site-data.py`:", " ".join(stale), file=sys.stderr)
        return 1
    if check:
        print("site-data: in sync with refusal.c and the ROM ops table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
