"""Ring 0: the frame, from the outside. compiles the supervisor, drives it with fixture scripts.

each test gets a throwaway world (copy of the image + main/hello.txt). no radio, no model.
the binary is launched with os.posix_spawnp: in-image, deterministic, not a ghost.
"""
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(IMAGE))
sys.path.insert(0, str(IMAGE / "tools"))
from isa.hotz_isa import Op  # noqa: E402
from isa.karpathy_rom import is_ring0  # noqa: E402
from peek import woz_bits  # noqa: E402

CFLAGS = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2"]
TOUCH = """# fixture intern: five legal ops
READ  fs main/hello.txt
WRITE fs hold/out.txt hello from the intern
EXEC  tools/hash.py hold/out.txt
TEST  PURE tests/rom/test_isa.py
WAIT  1
"""

_tmp = None
BENCH = None


def spawn(argv, env=None, out=None):
    if out is None:
        fd, out = tempfile.mkstemp(dir=_tmp.name, suffix=".out")
        os.close(fd)
    fa = [(os.POSIX_SPAWN_OPEN, 1, out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
          (os.POSIX_SPAWN_DUP2, 1, 2)]
    return os.posix_spawnp(argv[0], argv, env if env is not None else dict(os.environ),
                           file_actions=fa), out


def run(argv, env=None):
    pid, out = spawn(argv, env)
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st), Path(out).read_text()


def setUpModule():
    global _tmp, BENCH
    _tmp = tempfile.TemporaryDirectory()
    BENCH = str(Path(_tmp.name) / "bench")
    src = [str(IMAGE / "supervisor" / f) for f in ("main.c", "frame.c")]
    rc, out = run(["cc", *CFLAGS, "-o", BENCH, *src])
    if rc != 0:
        raise AssertionError("supervisor does not compile:\n" + out)


def tearDownModule():
    _tmp.cleanup()


class World:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(dir=_tmp.name))
        skip = shutil.ignore_patterns("__pycache__", "bench")
        for d in ("supervisor", "tools", "isa"):
            shutil.copytree(IMAGE / d, self.root / d, ignore=skip)
        shutil.copytree(IMAGE / "tests" / "rom", self.root / "tests" / "rom", ignore=skip)
        for d in ("main", "hold", "sessions"):
            (self.root / d).mkdir()
        (self.root / "main" / "hello.txt").write_text("hello bench\n")
        self.env = dict(os.environ, BENCH_ROOT=str(self.root))

    def bench(self, *args):
        return run([BENCH, *args], self.env)

    def script(self, text, name="fixture.ops"):
        p = self.root / name
        p.write_text(text)
        return str(p)

    def session(self):
        return self.root / "sessions" / (self.root / "sessions" / "CURRENT").read_text().strip()

    def snaps(self):
        return sorted(p for p in self.session().iterdir() if re.fullmatch(r"snap-\d+", p.name))

    def state(self):
        text = (self.session() / "STATE").read_text()
        return dict(line.split("=", 1) for line in text.splitlines())


class TestFrameCLI(unittest.TestCase):
    def test_rom_files_are_ring0(self):
        files = sorted((IMAGE / "tests" / "rom").glob("*.py"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(f=f.name):
                self.assertTrue(is_ring0(f.read_text()))

    def test_c_and_python_agree_on_opcodes(self):
        hdr = (IMAGE / "supervisor" / "frame.h").read_text()
        enum = re.search(r"typedef enum \{([^}]*)\} Op;", hdr).group(1)
        names = re.findall(r"OP_(\w+)", enum)
        self.assertEqual(names, ["READ", "WRITE", "EXEC", "TEST", "WAIT"])
        self.assertEqual([Op[n].value for n in names], [1, 2, 3, 4, 5])

    def test_run_touch_fixture(self):
        w = World()
        rc, out = w.bench("run", w.script(TOUCH))
        self.assertEqual(rc, 0, out)
        self.assertIn("HOLD", out)
        self.assertNotIn("MAIN", out)
        snaps = w.snaps()
        self.assertEqual(len(snaps), 6)  # s0 + one per frame
        man = (snaps[-1] / "MANIFEST").read_text()
        for key in ("snap=", "n=5", "N_max=8", "K=", "caps=", "lamps=", "tree="):
            self.assertIn(key, man)
        self.assertEqual((snaps[-1] / "hold" / "out.txt").read_text(), "hello from the intern\n")
        self.assertIn("kind=pure", (snaps[4] / "MANIFEST").read_text())
        self.assertFalse((snaps[-1].parent / (snaps[-1].name + ".tmp")).exists())
        # the transcript is a log file, not RAM
        self.assertIn("GREEN", (w.session() / "log").read_text())

    def test_status_mirrors_lamp_byte(self):
        w = World()
        self.assertEqual(w.bench("run", w.script(TOUCH))[0], 0)
        lamps, slots = woz_bits()
        byte = int(w.state()["lamps"], 16)
        self.assertFalse(byte & lamps["MAIN"])
        self.assertTrue(byte & lamps["HOLD"])
        self.assertFalse((byte & lamps["MAIN"]) and (byte & lamps["HOLD"]))
        rc, out = w.bench("status")
        self.assertEqual(rc, 0)
        line = next(x for x in out.splitlines() if x.startswith("lamps"))
        shown = line.split()[2:]
        want = [n for n, b in sorted(lamps.items(), key=lambda kv: kv[1]) if byte & b]
        self.assertEqual(shown, want)
        self.assertIn(f"0x{byte:02x}", line)
        plug = int(w.state()["plug"], 16)
        self.assertTrue(plug >> slots["fs"] & 1)
        self.assertFalse(plug >> slots["radio"] & 1)  # radio off by default

    def test_unknown_verb_faults(self):
        w = World()
        rc, out = w.bench("run", w.script("READ fs main/hello.txt\nBROWSE https://example.com\n"))
        self.assertNotEqual(rc, 0)
        self.assertIn("unknown verb", out)

    def test_supervisor_op_in_fixture_faults(self):
        w = World()
        for line in ("INSTALL_ROM tests/proposed/t.py", "SET_LOOP 100", "KILL", "UNPLUG radio"):
            with self.subTest(line=line):
                rc, out = w.bench("run", w.script(line + "\n"))
                self.assertNotEqual(rc, 0)
                self.assertIn("supervisor", out)

    def test_intern_cannot_write_main_or_rom(self):
        w = World()
        for line in ("WRITE fs main/owned.txt x", "WRITE fs tests/rom/test_x.py x", "WRITE fs ../escape x"):
            with self.subTest(line=line):
                rc, _ = w.bench("run", w.script(line + "\n"))
                self.assertNotEqual(rc, 0)
        self.assertFalse((w.root / "main" / "owned.txt").exists())

    def test_test_without_kind_faults(self):
        w = World()
        rc, out = w.bench("run", w.script("TEST tests/rom/test_isa.py\n"))
        self.assertNotEqual(rc, 0)
        self.assertIn("without kind", out)

    def test_judge_test_denied_with_radio_off(self):
        w = World()
        rc, out = w.bench("run", w.script("TEST JUDGE tests/rom/test_isa.py\n"))
        self.assertNotEqual(rc, 0)
        self.assertIn("unplugged", out)
        self.assertEqual(len(w.snaps()), 2)  # the denied step still snapped

    def test_over_n_faults(self):
        w = World()
        rc, out = w.bench("run", "--n", "2", w.script("WAIT 1\n" * 5))
        self.assertNotEqual(rc, 0)
        self.assertIn("over N", out)
        st = w.state()
        self.assertEqual((st["n"], st["N"], st["status"]), ("2", "2", "fault"))

    def test_n_cannot_exceed_touch_ceiling(self):
        w = World()
        rc, _ = w.bench("run", "--n", "9", w.script("WAIT 1\n"))
        self.assertNotEqual(rc, 0)

    def test_kill_keeps_last_snap(self):
        w = World()
        self.assertEqual(w.bench("run", w.script(TOUCH))[0], 0)
        before = w.snaps()
        last = w.state()["snap"]
        rc, out = w.bench("kill")
        self.assertEqual(rc, 0)
        self.assertIn(last, out)
        self.assertEqual(w.snaps(), before)
        self.assertIn("killed", w.bench("status")[1])

    def test_kill_halts_running_session(self):
        w = World()
        pid, out = spawn([BENCH, "run", w.script("WAIT 700\n" * 6)], w.env)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            cur = w.root / "sessions" / "CURRENT"
            if cur.exists() and (w.session() / "snap-1").exists():
                break
            time.sleep(0.05)
        self.assertEqual(w.bench("kill")[0], 0)
        _, st = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(st), 3, Path(out).read_text())
        self.assertEqual(w.state()["status"], "halt")
        self.assertLess(int(w.state()["n"]), 6)

    @unittest.skipIf(os.environ.get("BENCH_IN_DEMO"), "already inside bench demo")
    def test_demo_green(self):
        w = World()
        rc, out = w.bench("demo")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip().splitlines()[-1].split()[0], "GREEN")


if __name__ == "__main__":
    unittest.main()
