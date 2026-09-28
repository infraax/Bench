# SPDX-License-Identifier: MIT OR Apache-2.0
"""Power-cut sweep: SIGKILL the supervisor at its Nth syscall of a kind, then audit the world.

fault_sweep.py asks "what if the disk says no?". This asks "what if the machine dies right
here?" — no cleanup handler runs, no error path is taken. strace injects the kill
(--inject=<syscall>:signal=KILL:when=N) into the supervisor only (no -f: the helper and the
workers are not traced, so they see their parent vanish exactly as they would at a power cut).

After each kill, held to:
  P1 no torn evidence   every snap-<k> on disk verifies (bench verify + evidence-audit);
                        a half-built snap exists only as snap-<k>.tmp
  P2 honest status      the killed session reads crashed (or has no STATE yet), never ok/run
                        with a live lock
  P3 recoverable        the next clean run exits 0 and verifies; the world lock is free
  P4 nothing outlives   within 2 s of the kill, no process has its cwd in the world
                        (a worker or helper that keeps writing hold/ after its supervisor died
                        is exactly what custody forbids)

  python3 tests/deep/powercut_sweep.py [--max 12] [--sys rename,openat,...] [--json out.json]
exit 0: all held. 1: a violation (with the strace line to reproduce it). 2: setup.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
BENCH = IMAGE / "supervisor" / "bench"
sys.path.insert(0, str(IMAGE / "tests" / "deep"))
sys.path.insert(0, str(IMAGE / "tests" / "harness"))
from fault_sweep import WORKLOAD, check_world, orphans, sessions, whole  # noqa: E402
from test_cli import World, rmtree_force  # noqa: E402

SYSCALLS = ["openat", "write", "rename", "renameat", "renameat2", "mkdir", "mkdirat", "link", "linkat",
            "unlink", "unlinkat", "fchmodat", "chmod", "clone", "clone3", "wait4", "read", "getdents64"]


def counts(w, script):
    """per-syscall counts of one clean run of the supervisor alone (strace -c, no -f)."""
    out = w.root / "strace-c"
    r = subprocess.run(["strace", "-c", "-U", "name,calls", "-o", str(out), str(BENCH), "run", script],
                       cwd=IMAGE, env=w.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise SystemExit(f"powercut_sweep: the clean workload fails under strace:\n{r.stdout[-600:]}")
    c = {}
    for line in out.read_text().splitlines():
        m = re.match(r"^\s*(\w+)\s+(\d+)\s*$", line)
        if m:
            c[m.group(1)] = int(m.group(2))
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=12, help="kill points per syscall (strided)")
    ap.add_argument("--sys", default=",".join(SYSCALLS))
    ap.add_argument("--json")
    a = ap.parse_args()
    if not shutil.which("strace"):
        print("powercut_sweep: needs strace")
        return 2
    w = World()
    w.env["BENCH_KEEP"] = "3"
    script = w.script(WORKLOAD, name="cut.ops")
    report = {"counts": {}, "runs": 0, "violations": [], "killed": 0}
    t0 = time.monotonic()
    try:
        for _ in range(4):
            subprocess.run([str(BENCH), "run", script], cwd=IMAGE, env=w.env, stdout=subprocess.DEVNULL)
        c = counts(w, script)
        report["counts"] = {k: c[k] for k in a.sys.split(",") if c.get(k)}
        for sc, total in report["counts"].items():
            step = max(1, -(-total // a.max))
            for nth in range(1, total + 1, step):
                had = sessions(w)
                cmd = ["strace", "-qq", "-o", "/dev/null", f"--inject={sc}:signal=KILL:when={nth}",
                       str(BENCH), "run", script]
                r = subprocess.run(cmd, cwd=IMAGE, env=w.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors="replace", timeout=120)
                report["runs"] += 1
                killed = "+++ killed by SIGKILL" in r.stdout or r.returncode in (137, -9)
                report["killed"] += killed
                v = []
                deadline = time.monotonic() + 2
                orph = orphans(w.root)
                while orph and time.monotonic() < deadline:
                    time.sleep(0.05)
                    orph = orphans(w.root)
                if orph:
                    v.append(f"P4 {len(orph)} process(es) outlived the supervisor: {orph[:4]}")
                    for pid in orph:
                        try:
                            os.kill(pid, 9)
                        except OSError:
                            pass
                new = sessions(w) - had
                v += [x.replace("I3", "P1") for x in check_world(w, "P1", new)]
                torn = [sid for sid in sorted(had & sessions(w)) if not whole(w.root / "sessions" / sid)]
                if torn:
                    v.append(f"P1 an older session is no longer whole: {torn[:3]}")
                if killed:
                    for sid in new:
                        st = w.root / "sessions" / sid / "STATE"
                        if st.exists() and re.search(r"^status=ok", st.read_text(), re.M):
                            v.append(f"P2 {sid} says ok but its supervisor was killed")
                    status = subprocess.run([str(BENCH), "status", "--line"], cwd=IMAGE, env=w.env,
                                            stdout=subprocess.PIPE, text=True).stdout
                    if " run n=" in status or "lock=held" in status:
                        v.append(f"P2 status after the kill: {status.strip()[:100]}")
                rr = subprocess.run([str(BENCH), "run", script], cwd=IMAGE, env=w.env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=120)
                if rr.returncode != 0:
                    v.append(f"P3 the next clean run exits {rr.returncode}: {rr.stdout.strip()[-160:]}")
                if v:
                    rep = f"strace --inject={sc}:signal=KILL:when={nth} supervisor/bench run <cut.ops>"
                    report["violations"].append({"syscall": sc, "nth": nth, "what": v, "repro": rep})
                    print(f"VIOLATION {sc}#{nth}: {'; '.join(v)}\n  repro: BENCH_ROOT=<world> {rep}")
    finally:
        rmtree_force(w.root)
    report["seconds"] = round(time.monotonic() - t0, 1)
    print(f"powercut_sweep runs={report['runs']} killed={report['killed']} violations={len(report['violations'])} "
          f"counts={report['counts']} {report['seconds']}s")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
