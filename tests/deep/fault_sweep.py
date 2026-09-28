# SPDX-License-Identifier: MIT OR Apache-2.0
"""Crash-consistency sweep: fail every libc call of a run, one at a time, and audit the world.

For a workload script (every verb, a delta snap, a K snap) it first counts how often the
supervisor calls open/openat/mkdir/rename/link/write/read/fopen/fclose/opendir/chmod in a clean
run (faultinj.so, FI_COUNT). Then, for every function and every N up to that count (strided
past --max per function), it runs the workload again in a fresh-but-reused world with exactly
that call failing (FI_ERRNO, default EIO), and holds the result to:

  I1 no crash      the exit is a code (0..7), never a signal, never a hang (--timeout)
  I2 honest exit   exit 0 only if every op framed: status ok, n = ops
  I3 no torn       every snap on disk verifies, by `bench verify` AND scripts/evidence-audit.py
     evidence      (two implementations); a half-written snap may only exist as *.tmp
     and every older session is still whole (retention retires a session whole or not at all)
  I4 recoverable   the next clean run in the same world exits 0 and verifies (no stuck lock,
                   no wedged state)
  I5 no orphans    no process is left with its cwd in the world

A violation prints its one-line reproduction. Litter (*.tmp) and unsnapped FRAME lines are
counted but are not violations: they are what a fail-closed stop leaves behind.

  python3 tests/deep/fault_sweep.py [--max 40] [--fn rename,link] [--errno 28] [--json out.json]
exit 0: every invariant held. 1: violations. 2: setup.
"""
import argparse
import errno as E
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
BENCH = IMAGE / "supervisor" / "bench"
SHIM = IMAGE / "tests" / "deep" / "faultinj.so"
AUDIT = IMAGE / "scripts" / "evidence-audit.py"
sys.path.insert(0, str(IMAGE / "tests" / "harness"))
from test_cli import World, rmtree_force  # noqa: E402

WORKLOAD = ("WRITE fs hold/a.txt hello\n"
            "EXEC tools/hash.py hold/a.txt\n"
            "READ fs hold/a.txt\n"
            "WRITE fs hold/b.txt again\n"
            "TEST PURE tests/rom/test_isa.py\n"
            "WAIT 1\n")
OPS = WORKLOAD.count("\n")
FNS = ["open", "openat", "mkdir", "rename", "link", "write", "read", "fopen", "fclose", "opendir", "chmod",
       "unlink", "rmdir"]


def build_shim():
    if SHIM.exists() and SHIM.stat().st_mtime >= (IMAGE / "tests" / "deep" / "faultinj.c").stat().st_mtime:
        return
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-O1", "-shared", "-fPIC", "-o", str(SHIM),
                    str(IMAGE / "tests" / "deep" / "faultinj.c"), "-ldl"], check=True)


def bench(w, *args, env=None, timeout=60):
    return subprocess.run([str(BENCH), *args], cwd=IMAGE, env=env or w.env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)


def orphans(root):
    found = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            cwd = os.readlink(p / "cwd")
        except OSError:
            continue
        if cwd == str(root) or cwd.startswith(str(root) + "/"):
            found.append(int(p.name))
    return found


def current(w):
    try:
        return (w.root / "sessions" / "CURRENT").read_text().strip()
    except OSError:
        return None


def sessions(w):
    return {d.name for d in (w.root / "sessions").glob("*-*") if d.is_dir() and re.match(r"^\d+-\d+$", d.name)}


def whole(d):
    """cheap: a session that has snaps has SESSION and a gap-free chain snap-0..snap-K."""
    ks = sorted(int(p.name[5:]) for p in d.glob("snap-*") if p.name[5:].isdigit())
    return not ks or ((d / "SESSION").is_file() and ks == list(range(len(ks))))


def check_world(w, why, only):
    """I3 on the sessions this run made: bench verify (last snap) and the Python audit (all)."""
    bad = []
    for sid in sorted(only):
        a = subprocess.run([sys.executable, str(AUDIT), str(w.root), "--quiet", "--session", sid],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        if a.returncode != 0:
            bad.append(f"{why}: evidence-audit {sid}: " + " | ".join(l.strip() for l in a.stdout.splitlines() if l.strip().startswith("!"))[:400])
    for d in sorted(w.root / "sessions" / sid for sid in only):
        if not (d / "snap-0").is_dir():
            continue
        k = 0
        while (d / f"snap-{k + 1}").is_dir():
            k += 1
        r = bench(w, "verify", f"{d.name}/snap-{k}")
        if r.returncode != 0:
            bad.append(f"{why}: bench verify {d.name}/snap-{k}: {r.stdout.strip()[:200]}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="injections per function (strided over its calls)")
    ap.add_argument("--fn", default=",".join(FNS))
    ap.add_argument("--errno", type=int, default=E.EIO)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--json")
    a = ap.parse_args()
    if not BENCH.exists():
        print("fault_sweep: build first (make all)")
        return 2
    build_shim()
    w = World()
    w.env["BENCH_KEEP"] = "3"          # every run retires sessions: the retention path is swept too
    script = w.script(WORKLOAD, name="sweep.ops")
    base = dict(w.env, LD_PRELOAD=str(SHIM))
    report = {"errno": a.errno, "workload_ops": OPS, "counts": {}, "runs": 0, "violations": [], "litter": 0,
              "exits": {}}
    t0 = time.monotonic()
    try:
        for _ in range(4):                  # enough history that the counted run retires some
            if bench(w, "run", script).returncode != 0:
                print("fault_sweep: the clean workload fails")
                return 2
        cpath = w.root / "fi-counts"
        r = bench(w, "run", script, env=dict(base, FI_COUNT=str(cpath)))
        if r.returncode != 0:
            print(f"fault_sweep: the clean workload fails:\n{r.stdout}")
            return 2
        counts = {l.split()[0]: int(l.split()[1]) for l in cpath.read_text().splitlines()}
        report["counts"] = counts
        for fn in [f for f in a.fn.split(",") if f]:
            total = counts.get(fn, 0)
            if not total:
                continue
            step = max(1, -(-total // a.max))
            for nth in range(1, total + 1, step):
                env = dict(base, FI_FN=fn, FI_NTH=str(nth), FI_ERRNO=str(a.errno))
                repro = (f"FI_FN={fn} FI_NTH={nth} FI_ERRNO={a.errno} LD_PRELOAD={SHIM} "
                         f"BENCH_ROOT=<world> supervisor/bench run <sweep.ops>")
                report["runs"] += 1
                before, had = current(w), sessions(w)
                try:
                    r = bench(w, "run", script, env=env, timeout=a.timeout)
                    rc, out = r.returncode, r.stdout
                except subprocess.TimeoutExpired:
                    rc, out = "hang", ""
                report["exits"][str(rc)] = report["exits"].get(str(rc), 0) + 1
                v = []
                if rc == "hang":
                    v.append("I1 hang")
                elif rc < 0 or rc > 7:
                    v.append(f"I1 exit {rc} ({'signal ' + str(-rc) if rc < 0 else 'unknown code'})")
                if rc == 0:
                    frames = len(re.findall(r"^frame \d+ ", out, re.M))
                    st = bench(w, "status", "--line").stdout
                    if frames != OPS or current(w) == before or " ok n=" not in st:
                        v.append(f"I2 exit 0 but frames={frames}/{OPS} status={st.strip()[:80]}")
                v += check_world(w, "I3", sessions(w) - had)
                torn = [sid for sid in sorted(had & sessions(w)) if not whole(w.root / "sessions" / sid)]
                if torn:
                    v.append(f"I3 an older session is no longer whole (retention cut short?): {torn[:3]}")
                report["litter"] += sum(1 for _ in (w.root / "sessions").glob("*/*.tmp"))
                rr = bench(w, "run", script, timeout=a.timeout)
                if rr.returncode != 0:
                    v.append(f"I4 the next clean run exits {rr.returncode}: {rr.stdout.strip()[-200:]}")
                orph = orphans(w.root)
                if orph:
                    v.append(f"I5 orphans {orph}")
                    for pid in orph:
                        try:
                            os.kill(pid, 9)
                        except OSError:
                            pass
                if v:
                    tail = " / ".join(l for l in out.strip().splitlines()[-2:]) if isinstance(out, str) else ""
                    report["violations"].append({"fn": fn, "nth": nth, "exit": rc, "what": v, "tail": tail[:300], "repro": repro})
                    print(f"VIOLATION {fn}#{nth} exit={rc}: {'; '.join(v)}\n  last: {tail[:200]}\n  repro: {repro}")
    finally:
        rmtree_force(w.root)
    report["seconds"] = round(time.monotonic() - t0, 1)
    print(f"fault_sweep errno={a.errno} runs={report['runs']} violations={len(report['violations'])} "
          f"litter={report['litter']} exits={report['exits']} counts={report['counts']} {report['seconds']}s")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
