# SPDX-License-Identifier: MIT OR Apache-2.0
"""make test-deep: every deep tool once, one report.

Writes ledger/deep-<stamp>-<sha>/ (gitignored): each tool's JSON and output, and summary.md —
the table a human reads and an agent parses. stdout gets the table only.

  python3 tests/deep/run_all.py [--quick] [--c]
    --quick   smaller budgets (about a minute): for a pre-push check
    --c       also C mutation testing of the parser (minutes)
exit 0: every tool green. 1: any finding (the summary names it and where its detail is).
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
DEEP = IMAGE / "tests" / "deep"


def sha():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=IMAGE, stdout=subprocess.PIPE, text=True)
    return r.stdout.strip() or "nogit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--c", action="store_true")
    a = ap.parse_args()
    out = IMAGE / "ledger" / f"deep-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{sha()}"
    out.mkdir(parents=True, exist_ok=True)
    q = a.quick
    tools = [
        ("parse differential", [sys.executable, DEEP / "fuzz_parse.py", "--n", "1500" if q else "6000",
                                "--oracle", "20" if q else "80", "--json", out / "fuzz_parse.json"]),
        ("hash differential+metamorphic", [sys.executable, DEEP / "hash_fuzz.py", "--trees", "40" if q else "200"]),
        ("fault injection sweep", [sys.executable, DEEP / "fault_sweep.py", "--max", "8" if q else "40",
                                   "--json", out / "fault_sweep.json"]),
        ("fault injection sweep ENOSPC", [sys.executable, DEEP / "fault_sweep.py", "--max", "4" if q else "20",
                                          "--errno", "28", "--json", out / "fault_sweep_enospc.json"]),
        ("power-cut sweep (SIGKILL)", [sys.executable, DEEP / "powercut_sweep.py", "--max", "3" if q else "12",
                                       "--json", out / "powercut_sweep.json"]),
        ("mutation: python ISA vs ROM", [sys.executable, DEEP / "mutate.py", "--json", out / "mutate_py.json",
                                         "--min-score", "0.9"]),
    ]
    if a.c:
        tools.append(("mutation: C parser vs harness", [sys.executable, DEEP / "mutate.py", "--lang", "c",
                                                        "--json", out / "mutate_c.json", "--min-score", "0.8"]))
    rows, bad = [], 0
    for name, cmd in tools:
        t0 = time.monotonic()
        r = subprocess.run([str(c) for c in cmd], cwd=IMAGE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        secs = time.monotonic() - t0
        slug = name.split(":")[0].replace(" ", "_").replace("+", "_")
        (out / f"{slug}.txt").write_text(r.stdout)
        last = [l for l in r.stdout.strip().splitlines() if l and not l.startswith(" ")]
        line = last[-1] if last else "(no output)"
        rows.append((name, "ok" if r.returncode == 0 else "FINDING", f"{secs:.0f}s", line))
        bad += r.returncode != 0
    md = ["# test-deep", "", f"- tree: `{sha()}` · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · "
          f"{'quick' if q else 'full'}{' + C mutation' if a.c else ''}", "",
          "| tool | verdict | time | result |", "|---|---|---|---|"]
    md += [f"| {n} | {v} | {t} | `{l}` |" for n, v, t, l in rows]
    md += ["", "Detail per tool: the `.txt` and `.json` files beside this one. Read `docs/TESTING_KIT.md`."]
    (out / "summary.md").write_text("\n".join(md) + "\n")
    (out / "summary.json").write_text(json.dumps([dict(zip(("tool", "verdict", "time", "result"), r)) for r in rows], indent=1))
    width = max(len(r[0]) for r in rows)
    for n, v, t, l in rows:
        print(f"{n:<{width}}  {v:<7} {t:>5}  {l}")
    print(f"test-deep: {len(rows) - bad}/{len(rows)} green -> {out.relative_to(IMAGE)}/summary.md")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
