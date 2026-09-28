"""Timing classes for docs/PERF_AND_MAP.md. A measurement, not a test of meaning.

Run by hand (`python3 tests/perf/perf_map.py [N]`), never by ROM. Every class is sampled N times
(default 20) in throwaway worlds; prints median and p95 (nearest rank) in ms. Frame costs are
marginal: (wall of an 8-step run - wall of a 1-step run) / 7, per pair of runs, so the fixed cost
of starting a session (helper, s0 snap, status) drops out.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(IMAGE / "tests" / "harness"))
from test_cli import BENCH, World, rmtree_force  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def stats(xs):
    s = sorted(xs)
    p95 = s[max(0, -(-len(s) * 95 // 100) - 1)]
    return f"median={s[len(s) // 2]:8.2f}  p95={p95:8.2f}  n={len(s)}"


def wall(w, *args):
    t0 = time.perf_counter()
    r = subprocess.run([str(BENCH), *args], cwd=IMAGE, env=w.env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ms = (time.perf_counter() - t0) * 1000
    return ms, r


def run_ok(w, script, name):
    ms, r = wall(w, "run", w.script(script, name=name))
    if r.returncode != 0:
        raise SystemExit(f"perf_map: run failed ({name}):\n{r.stdout}")
    return ms


def tool_ms(w):
    out = []
    for snap in w.snaps():
        m = re.search(r"tool_ms=(\d+)", (snap / "MANIFEST").read_text())
        if m and "op=exec" in (snap / "MANIFEST").read_text():
            out.append(int(m.group(1)))
    return out


def marginal(w, step, name):
    """per-frame cost of `step`: (8 steps - 1 step) / 7, one estimate per pair."""
    est = []
    for i in range(N):
        one = run_ok(w, step, f"{name}1.ops")
        eight = run_ok(w, step * 8, f"{name}8.ops")
        est.append((eight - one) / 7)
    return est


def fill_hold(w, files, size):
    h = w.root / "hold"
    for i in range(files):
        (h / f"f{i:05d}").write_bytes(b"x" * size)


def main():
    worlds = []

    def world():
        w = World()
        worlds.append(w)
        return w

    try:
        print(f"# python {sys.version.split()[0]}  cpus={os.cpu_count()}  uid={os.getuid()}  N={N}")
        w = world()
        # boot: a cold process, no session work
        print("boot  status      ", stats([wall(w, "status")[0] for _ in range(N)]))
        print("boot  rules       ", stats([wall(w, "rules")[0] for _ in range(N)]))
        # arm: token present, run with one empty frame, to exit (helper, s0, frame, status)
        print("arm   run WAIT 0  ", stats([run_ok(w, "WAIT 0\n", "arm.ops") for _ in range(N)]))
        # frame empty: marginal WAIT 0
        print("frame WAIT 0      ", stats(marginal(w, "WAIT 0\n", "wait")))
        # EXEC tiny: marginal frame, and the child's own tool_ms from the MANIFESTs
        we = world()
        est, tms = [], []
        for i in range(N):
            one = run_ok(we, "EXEC tools/hash.py main/hello.txt\n", "e1.ops")
            eight = run_ok(we, "EXEC tools/hash.py main/hello.txt\n" * 8, "e8.ops")
            tms += tool_ms(we)
            est.append((eight - one) / 7)
        print("exec  hash.py frame", stats(est))
        print("exec  hash.py tool ", stats(tms), " (tool_ms: fork + jail + python + hash)")
        # snap: steady-state frame cost with hold/ pre-filled (delta snaps link unchanged files),
        # and the s0 cost of a session start over that hold/ (a full copy).
        base1 = [run_ok(world(), "WAIT 0\n", "b.ops") for _ in range(3)]
        for label, files, size in (("0 files", 0, 0), ("1 x 64KiB", 1, 65536),
                                   ("256 x 1B", 256, 1), ("1000 x 1B", 1000, 1)):
            ws = world()
            fill_hold(ws, files, size)
            print(f"snap  {label:10s} frame", stats(marginal(ws, "WAIT 0\n", "s")))
            s0 = [run_ok(ws, "WAIT 0\n", "s0.ops") for _ in range(N)]
            print(f"snap  {label:10s} run  ", stats(s0), f" (1-frame run; empty-hold run ~{sorted(base1)[1]:.1f})")
        # new files in one step: a tool writes K fresh files; the snap copies them all.
        for k in (64, 256):
            wn = world()
            wn.tool("mk.py", f"import sys\nfor i in range({k}):\n"
                             "    open(f'hold/n{sys.argv[1]}_{i:04d}', 'w').write('x')\n")
            est = []
            for i in range(N):
                ms = run_ok(wn, f"EXEC tools/mk.py {i}\n", f"mk{i}.ops")
                t = tool_ms(wn)[-1]
                est.append(ms - t)
                rmtree_force(wn.root / "hold")
                (wn.root / "hold").mkdir()
            print(f"snap  +{k} new files run-minus-tool", stats(est))
        # ROM suite, in-process cost of a python boot + 55 pure tests
        rom = []
        for _ in range(N):
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/rom",
                                "-p", "test_*.py", "-q"], cwd=IMAGE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rom.append((time.perf_counter() - t0) * 1000)
            if r.returncode != 0:
                raise SystemExit("perf_map: ROM suite red")
        print("rom   suite wall  ", stats(rom))
    finally:
        for w in worlds:
            rmtree_force(w.root)


if __name__ == "__main__":
    main()
