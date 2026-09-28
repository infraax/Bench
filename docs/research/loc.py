# SPDX-License-Identifier: MIT OR Apache-2.0
"""Line counts per audited repo, split into source and test lines. Same method as the 2026-09-28 audit.

    python3 docs/research/loc.py [clones_dir]      # default: docs/research/clones, plus this repo as "Bench"
"""
import collections
import os
import sys

EXT = {".py": "py", ".ts": "ts", ".tsx": "ts", ".js": "js", ".rs": "rs", ".go": "go", ".c": "c", ".h": "c"}
SKIP = {"node_modules", ".git", "dist", "build", "vendor", "__pycache__", "docs", "examples", "website",
        "fixtures", "clones", "research"}


def count(root):
    code, tests, files = collections.Counter(), 0, 0
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in SKIP]
        for f in fs:
            e = os.path.splitext(f)[1]
            if e not in EXT:
                continue
            p = os.path.join(d, f)
            try:
                n = sum(1 for _ in open(p, errors="ignore"))
            except OSError:
                continue
            if "test" in p.lower():
                tests += n
            else:
                code[EXT[e]] += n
                files += 1
    return code, tests, files


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    clones = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "clones")
    roots = [(n, os.path.join(clones, n)) for n in sorted(os.listdir(clones))
             if os.path.isdir(os.path.join(clones, n))]
    roots.append(("Bench", os.path.dirname(here)))
    rows = []
    for name, path in roots:
        c, t, f = count(path)
        rows.append((name, sum(c.values()), t, f, ",".join(k for k, _ in c.most_common(2))))
    print(f"{'repo':<42} {'code':>10} {'test':>10} {'files':>6}  langs")
    for r in sorted(rows, key=lambda r: r[1]):
        print(f"{r[0]:<42} {r[1]:>10,} {r[2]:>10,} {r[3]:>6}  {r[4]}")


if __name__ == "__main__":
    main()
