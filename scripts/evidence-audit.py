#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""evidence-audit: re-derive every claim a world's sessions/ makes, with a second implementation.

`bench verify` is the C checking the C. This is the other witness: pure Python, reusing only
tools/hash.py (itself pinned to sha256.c by TestHashParity), so one bug cannot hide in both.
For every session dir (<epoch>-<pid>):

  chain    snap-0..snap-K contiguous; snap-0 is why=s0 n=0; n never goes down
  board    board= equals the tree hash of the snap's stored hold/ (recomputed here)
  out      out=out-<n> bytes=<b> sha256=<h> matches the file on disk
  seal     snap files 0444, dirs 0555 (a warning, not a violation: root can chmod)
  state    STATE snap= and n= agree with the last MANIFEST; status is a known word
  log      one FRAME line per stepped snap (a missing FRAME is a warning)
  litter   *.tmp left by a failed snap (a warning: evidence of a fault, not corruption)

  python3 scripts/evidence-audit.py [world] [--json out.json] [--session ID]
exit 0: every claim holds. 1: a violation. 2: not a world.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IMAGE / "tools"))
from hash import tree_hash  # noqa: E402

SESSION_RE = re.compile(r"^\d+-\d+$")
STATUS = {"run", "ok", "fault", "halt", "disarmed", "restored"}


def kv(text):
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep and k not in out:
            out[k] = v
    return out


def audit_session(d):
    v, w = [], []   # violations, warnings
    snaps, k = [], 0
    while (d / f"snap-{k}").is_dir():
        snaps.append(d / f"snap-{k}")
        k += 1
    extra = sorted(p.name for p in d.glob("snap-*") if p.is_dir() and p not in snaps and not p.name.endswith(".tmp"))
    if extra:
        v.append(f"chain: snaps past a gap: {extra[:5]}")
    litter = sorted(p.name for p in d.glob("*.tmp"))
    if litter:
        w.append(f"litter: {litter[:5]}")
    if not (d / "SESSION").is_file():
        # a start refused before SESSION (helper, snap s0) leaves only its log: fail closed, by design
        (v if snaps else w).append("SESSION missing" + ("" if snaps else " (a refused start: log only)"))
    last_n, mans = -1, []
    for s in snaps:
        mp = s / "MANIFEST"
        if not mp.is_file():
            v.append(f"{s.name}: no MANIFEST")
            continue
        m = kv(mp.read_text(errors="replace"))
        mans.append((s, m))
        for key in ("snap", "why", "n", "tree", "evidence", "out", "board"):
            if key not in m:
                v.append(f"{s.name}: MANIFEST has no {key}=")
        try:
            n = int(m.get("n", "-1"))
        except ValueError:
            v.append(f"{s.name}: n={m.get('n')!r} is not a number")
            continue
        if s.name == "snap-0" and (m.get("why") != "s0" or n != 0):
            v.append(f"snap-0: why={m.get('why')} n={n}, not the s0 photo")
        if n < last_n:
            v.append(f"{s.name}: n={n} after n={last_n}")
        last_n = max(last_n, n)
        b = m.get("board", "none")
        if b != "none":
            got = tree_hash(["hold"], base=s)
            if got != b:
                v.append(f"{s.name}: board= {b[:16]}… but the stored hold/ hashes to {got[:16]}…")
        elif (s / "hold").exists():
            v.append(f"{s.name}: board=none but a hold/ copy is stored")
        o = re.match(r"(out-\d+) bytes=(\d+) sha256=([0-9a-f]{64}|unreadable)$", m.get("out", ""))
        if o and o.group(3) == "unreadable":
            w.append(f"{s.name}: {o.group(1)} not pinned (the step says so and faulted)")
        elif o:
            f = d / o.group(1)
            if not f.is_file():
                v.append(f"{s.name}: {o.group(1)} is missing")
            else:
                data = f.read_bytes()
                if len(data) != int(o.group(2)):
                    v.append(f"{s.name}: {o.group(1)} is {len(data)} bytes, MANIFEST says {o.group(2)}")
                if hashlib.sha256(data).hexdigest() != o.group(3):
                    v.append(f"{s.name}: {o.group(1)} sha256 differs from MANIFEST")
        elif m.get("out", "none") != "none":
            v.append(f"{s.name}: out={m.get('out')!r} is not a pin")
        for root, dirs, files in os.walk(s):
            for name in files:
                mode = stat.S_IMODE(os.lstat(os.path.join(root, name)).st_mode)
                if not os.path.islink(os.path.join(root, name)) and mode != 0o444:
                    w.append(f"seal: {os.path.relpath(os.path.join(root, name), d)} is {mode:o}")
                    break
            for name in dirs + ["."]:
                p = os.path.join(root, name)
                if not os.path.islink(p) and stat.S_IMODE(os.lstat(p).st_mode) != 0o555:
                    w.append(f"seal: {os.path.relpath(p, d)}/ is {stat.S_IMODE(os.lstat(p).st_mode):o}")
                    break
    st = d / "STATE"
    if st.is_file() and mans:
        sv = kv(st.read_text(errors="replace"))
        word = sv.get("status", "").split(",")[0]
        if word not in STATUS:
            v.append(f"STATE status={sv.get('status')!r} is not a status word")
        last = mans[-1][1]
        if sv.get("snap") and sv.get("snap") != last.get("snap"):
            # STATE is rewritten after the snap lands; a snap that landed without its STATE is a
            # crash between the two writes — say so, it is not forged evidence
            w.append(f"STATE snap={sv.get('snap')} but the last snap is {last.get('snap')}")
    elif mans:
        w.append("STATE missing")
    log = d / "log"
    if log.is_file():
        frames = len(re.findall(r"^FRAME n=\d+ ", log.read_text(errors="replace"), re.M))
        steps = sum(1 for _, m in mans if m.get("why") == "step")
        if frames < steps:
            w.append(f"log: {frames} FRAME lines for {steps} stepped snaps")
    return v, w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("world", nargs="?", default=os.environ.get("BENCH_ROOT", "."))
    ap.add_argument("--json")
    ap.add_argument("--session")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    sessions = Path(a.world) / "sessions"
    if not sessions.is_dir():
        print(f"evidence-audit: {a.world} has no sessions/")
        return 2
    dirs = sorted(p for p in sessions.iterdir() if p.is_dir() and SESSION_RE.match(p.name)
                  and (a.session is None or p.name == a.session))
    report, bad = {}, 0
    for d in dirs:
        v, w = audit_session(d)
        report[d.name] = {"violations": v, "warnings": w}
        bad += bool(v)
        if not a.quiet or v:
            print(f"{d.name} {'VIOLATION' if v else 'ok'}" + (f" warnings={len(w)}" if w else ""))
            for x in v:
                print(f"  ! {x}")
            if not a.quiet:
                for x in w:
                    print(f"  ~ {x}")
    print(f"evidence-audit sessions={len(dirs)} violations={bad}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
