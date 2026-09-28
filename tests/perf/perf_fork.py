"""Measurement, not a test of meaning: what a fork costs, and what N parallel worlds buy.

Run by `make perf` (a human), never by ROM. Prints one line per number and fails (exit 1) if
N = 4 worlds in parallel are not clearly faster than the same four runs one after another.
Timing depends on the machine; the assertion is a ratio, not an absolute.
"""
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(IMAGE / "tests" / "harness"))
from test_cli import BENCH, Forked, World, rmtree_force  # noqa: E402

N = 4
FORKS = 5
MIN_SPEEDUP = 1.5
# a working step of each kind; interpreter boots dominate, as they do in a real run.
SCRIPT = """READ  fs main/hello.txt
WRITE fs hold/note.txt forked world
EXEC  tools/hash.py main/hello.txt
TEST  PURE tests/rom/test_isa.py
WAIT  200
"""


def run(world, script):
    return subprocess.Popen([str(BENCH), "run", script], cwd=IMAGE, env=world.env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def wait_ok(procs):
    for p in procs:
        out, _ = p.communicate(timeout=120)
        if p.returncode != 0:
            raise SystemExit(f"perf: a world run failed (rc={p.returncode}):\n{out}")


def main():
    src = World()
    base = Path(tempfile.mkdtemp(prefix="bench-perf-"))
    try:
        r = subprocess.run([str(BENCH), "run", src.script(SCRIPT)], cwd=IMAGE, env=src.env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0:
            raise SystemExit("perf: source run failed:\n" + r.stdout)

        fork_ms = []
        for i in range(FORKS):
            t0 = time.perf_counter()
            r = subprocess.run([str(BENCH), "fork", "snap-5", str(base / f"f{i}")], cwd=IMAGE, env=src.env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            fork_ms.append((time.perf_counter() - t0) * 1000)
            if r.returncode != 0:
                raise SystemExit("perf: fork failed:\n" + r.stdout)
        print(f"fork       median={statistics.median(fork_ms):.1f}ms  (n={FORKS}, wall incl. process start)")

        worlds = []
        for i in range(N):
            w = Forked(base / f"f{i}")
            w.arm()
            worlds.append((w, w.script(SCRIPT)))

        t0 = time.perf_counter()
        for w, s in worlds:
            wait_ok([run(w, s)])
        seq = time.perf_counter() - t0

        t0 = time.perf_counter()
        wait_ok([run(w, s) for w, s in worlds])
        par = time.perf_counter() - t0

        speedup = seq / par
        print(f"worlds     N={N} sequential={seq:.2f}s parallel={par:.2f}s speedup={speedup:.2f}x "
              f"(cpus={os.cpu_count()})")
        if speedup < MIN_SPEEDUP:
            print(f"FAIL parallel worlds are not clearly faster: {speedup:.2f}x < {MIN_SPEEDUP}x")
            return 1
        print(f"PERF ok speedup={speedup:.2f}x >= {MIN_SPEEDUP}x")
        return 0
    finally:
        rmtree_force(base)
        rmtree_force(src.root)


if __name__ == "__main__":
    sys.exit(main())
