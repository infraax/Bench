"""The harness. NOT Ring 0 — make launches it, a human's privilege, not ROM python.

Woz's one gate: the supervisor is started by `make test` (you), never by a ROM file
spawning a cousin. So this file is free to use subprocess; it lives outside tests/rom/
and is not subject to is_ring0. It drives the compiled binary and reads the board.

It builds bench through `make` so the binary is ROM-pinned, then runs each fixture in a
throwaway world (a copy of the image + main/hello.txt). Radio stays unplugged throughout.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(IMAGE))
sys.path.insert(0, str(IMAGE / "tools"))
from isa.hotz_isa import OWNER_TOKEN, Op  # noqa: E402
from isa.karpathy_rom import is_ring0  # noqa: E402
from peek import woz_bits  # noqa: E402

BENCH = IMAGE / "supervisor" / "bench"
LAMPS, SLOTS = woz_bits()

TOUCH = """# fixture intern: five legal ops
READ  fs main/hello.txt
WRITE fs hold/out.txt hello from the intern
EXEC  tools/hash.py hold/out.txt
TEST  PURE tests/rom/test_isa.py
WAIT  1
"""


def setUpModule():
    # make (the human/Ring-0 parent) builds the pinned binary. no ROM file spawns it.
    r = subprocess.run(["make", "supervisor/bench"], cwd=IMAGE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise AssertionError("make supervisor/bench failed:\n" + r.stdout)


class World:
    """a throwaway copy of the image; the supervisor runs against it via BENCH_ROOT."""
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="bench-h-"))
        ign = shutil.ignore_patterns("__pycache__", "bench", "romhash", "*.o")
        for d in ("supervisor", "tools", "isa"):
            shutil.copytree(IMAGE / d, self.root / d, ignore=ign)
        shutil.copytree(IMAGE / "tests" / "rom", self.root / "tests" / "rom", ignore=ign)
        for d in ("main", "hold", "sessions", "tests/proposed"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / "main" / "hello.txt").write_text("hello bench\n")
        self.env = dict(os.environ, BENCH_ROOT=str(self.root))
        self.env.pop("BENCH_TOKEN", None)
        self.token = self.root / OWNER_TOKEN
        self.arm()

    def arm(self):
        # the owner (this harness, launched by make) arms the world before run.
        self.token.parent.mkdir(parents=True, exist_ok=True)
        self.token.write_text("")

    def disarm(self):
        self.token.unlink(missing_ok=True)

    def bench(self, *args, timeout=60):
        return subprocess.run([str(BENCH), *args], cwd=IMAGE, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=timeout)

    def script(self, text, name="fixture.ops"):
        p = self.root / name
        p.write_text(text)
        return str(p)

    def tool(self, name, body):
        p = self.root / "tools" / name
        p.write_text(body)
        return f"tools/{name}"

    def session(self):
        cur = (self.root / "sessions" / "CURRENT").read_text().strip()
        return self.root / "sessions" / cur

    def snaps(self):
        return sorted(p for p in self.session().iterdir() if re.fullmatch(r"snap-\d+", p.name))

    def state(self):
        text = (self.session() / "STATE").read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def addWorld(case):
    w = World()
    case.addCleanup(shutil.rmtree, w.root, ignore_errors=True)
    return w


# --- data-driven fixtures (Woz: the test file is data — inputs + expected board) ---
# (name, script, expect_rc_zero, expect_lamps_substrs, expect_snap_count, expect_out_substr)
FIXTURES = [
    ("touch_five_ops", TOUCH, True, ["HOLD"], 6, None),
    ("single_wait", "WAIT 1\n", True, ["HOLD"], 2, None),
    ("unknown_verb", "BROWSE http://x\n", False, None, None, "unknown verb"),
    ("supervisor_install", "INSTALL_ROM tests/proposed/t.py\n", False, None, None, "supervisor"),
    ("supervisor_setloop", "SET_LOOP 99\n", False, None, None, "supervisor"),
    ("supervisor_kill", "KILL\n", False, None, None, "supervisor"),
    ("supervisor_unplug", "UNPLUG radio\n", False, None, None, "supervisor"),
    ("test_without_kind", "TEST tests/rom/test_isa.py\n", False, None, None, "without kind"),
    ("write_main_denied", "WRITE fs main/owned.txt x\n", False, None, None, "ring"),
    ("write_rom_denied", "WRITE fs tests/rom/x.py x\n", False, None, None, "ring"),
    ("path_escape_denied", "WRITE fs ../escape x\n", False, None, None, "escapes"),
    ("exec_escape_denied", "EXEC tools/../../supervisor/bench\n", False, None, None, "tools/"),
    ("judge_denied_radio_off", "TEST JUDGE tests/rom/test_isa.py\n", False, None, 2, "unplugged"),
]


class TestFixtures(unittest.TestCase):
    def test_fixtures(self):
        for name, script, ok, lamps, snaps, out in FIXTURES:
            with self.subTest(name=name):
                w = addWorld(self)
                r = w.bench("run", w.script(script))
                self.assertEqual(r.returncode == 0, ok, f"{name}: rc={r.returncode}\n{r.stdout}")
                self.assertNotIn("MAIN", r.stdout, f"{name}: MAIN must stay dark")
                if out is not None:
                    self.assertIn(out, r.stdout, f"{name}: missing {out!r}\n{r.stdout}")
                if lamps is not None:
                    for want in lamps:
                        self.assertIn(want, r.stdout, name)
                if snaps is not None:
                    self.assertEqual(len(w.snaps()), snaps, f"{name}: snap count\n{r.stdout}")


class TestBoard(unittest.TestCase):
    def test_rom_files_are_ring0(self):
        files = sorted((IMAGE / "tests" / "rom").glob("*.py"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(f=f.name):
                self.assertTrue(is_ring0(f.read_text()), f"{f.name} not ring0")

    def test_harness_is_not_ring0_by_design(self):
        # this file uses subprocess; it must NOT be admissible to tests/rom.
        self.assertFalse(is_ring0(Path(__file__).read_text()))

    def test_c_and_python_agree_on_opcodes(self):
        hdr = (IMAGE / "supervisor" / "frame.h").read_text()
        enum = re.search(r"typedef enum \{([^}]*)\} Op;", hdr).group(1)
        names = re.findall(r"OP_(\w+)", enum)
        self.assertEqual(names, ["READ", "WRITE", "EXEC", "TEST", "WAIT"])
        self.assertEqual([Op[n].value for n in names], [1, 2, 3, 4, 5])

    def test_status_mirrors_lamp_byte(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script(TOUCH)).returncode, 0)
        byte = int(w.state()["lamps"], 16)
        self.assertFalse(byte & LAMPS["MAIN"])
        self.assertTrue(byte & LAMPS["HOLD"])
        self.assertFalse((byte & LAMPS["MAIN"]) and (byte & LAMPS["HOLD"]))  # never both
        out = w.bench("status").stdout
        line = next(x for x in out.splitlines() if x.startswith("lamps"))
        shown = line.split()[2:]
        want = [n for n, b in sorted(LAMPS.items(), key=lambda kv: kv[1]) if byte & b]
        self.assertEqual(shown, want)
        self.assertIn(f"0x{byte:02x}", line)
        plug = int(w.state()["plug"], 16)
        self.assertTrue(plug >> SLOTS["fs"] & 1)
        self.assertFalse(plug >> SLOTS["radio"] & 1)  # radio off by default

    def test_over_n_faults_before_work(self):
        w = addWorld(self)
        r = w.bench("run", "--n", "2", w.script("WAIT 1\n" * 5))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("over N", r.stdout)
        st = w.state()
        self.assertEqual((st["n"], st["N"], st["status"]), ("2", "2", "fault"))

    def test_n_ceiling(self):
        w = addWorld(self)
        self.assertNotEqual(w.bench("run", "--n", "9", w.script("WAIT 1\n")).returncode, 0)

    def test_kill_keeps_last_snap(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script(TOUCH)).returncode, 0)
        before, last = w.snaps(), w.state()["snap"]
        r = w.bench("kill")
        self.assertEqual(r.returncode, 0)
        self.assertIn(last, r.stdout)
        self.assertEqual(w.snaps(), before)
        self.assertIn("killed", w.bench("status").stdout)

    def test_kill_halts_running_session(self):
        w = addWorld(self)
        proc = subprocess.Popen([str(BENCH), "run", w.script("WAIT 700\n" * 6)],
                                cwd=IMAGE, env=w.env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            cur = w.root / "sessions" / "CURRENT"
            if cur.exists() and (w.session() / "snap-1").exists():
                break
            time.sleep(0.05)
        self.assertEqual(w.bench("kill").returncode, 0)
        self.assertEqual(proc.wait(timeout=15), 3)
        self.assertEqual(w.state()["status"], "halt")
        self.assertLess(int(w.state()["n"]), 6)

    def test_demo_green(self):
        w = addWorld(self)
        r = w.bench("demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1].split()[0], "GREEN")

    def test_two_clocks_recorded(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        man = (w.snaps()[-1] / "MANIFEST").read_text()
        self.assertIn("tool_ms=", man)  # tool time is separate from the frame
        sess = (w.session() / "SESSION").read_text()
        self.assertIn("T_frame_ms=", sess)
        self.assertIn("T_tool_ms=", sess)


class TestArm(unittest.TestCase):
    """run refuses to start without an owner token. no frames, no session, lamps dark."""

    def assert_refused(self, w, r):
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("not armed", r.stdout)
        self.assertNotIn("frame ", r.stdout)
        self.assertFalse((w.root / "sessions" / "CURRENT").exists())
        st = w.bench("status").stdout
        self.assertIn("lamps   0x00 (dark)", st)
        self.assertIn("session none", st)

    def test_no_token_refuses_run(self):
        w = addWorld(self)
        w.disarm()
        self.assert_refused(w, w.bench("run", w.script("WAIT 1\n")))

    def test_token_file_arms_run(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)

    def test_env_token_arms_run(self):
        w = addWorld(self)
        w.disarm()
        key = w.root / "owner.key"
        key.write_text("")
        w.env["BENCH_TOKEN"] = str(key)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)

    def test_env_token_must_exist(self):
        w = addWorld(self)
        w.disarm()
        w.env["BENCH_TOKEN"] = str(w.root / "missing.key")
        self.assert_refused(w, w.bench("run", w.script("WAIT 1\n")))

    def test_token_must_be_a_file(self):
        w = addWorld(self)
        w.disarm()
        w.token.mkdir(parents=True)
        self.assert_refused(w, w.bench("run", w.script("WAIT 1\n")))

    def test_old_token_path_does_not_arm(self):
        # the v0 path sessions/current/token was renamed; a leftover must not arm a run.
        w = addWorld(self)
        w.disarm()
        old = w.root / "sessions" / "current" / "token"
        old.parent.mkdir(parents=True)
        old.write_text("")
        self.assert_refused(w, w.bench("run", w.script("WAIT 1\n")))

    def test_demo_and_status_need_no_token(self):
        w = addWorld(self)
        w.disarm()
        self.assertEqual(w.bench("status").returncode, 0)
        self.assertEqual(w.bench("demo").returncode, 0)

    def test_c_parser_agrees_with_rom_write_table(self):
        # same table as tests/rom/test_arm.py, run through the C parser. arm by env so
        # sessions/OWNER_TOKEN starts absent and must still be absent after.
        sys.path.insert(0, str(IMAGE / "tests" / "rom"))
        from test_arm import WRITE_TABLE
        for path, ok in WRITE_TABLE:
            if not path:
                continue   # an empty field is a parse error in C for a different reason
            with self.subTest(path=path):
                w = addWorld(self)
                w.disarm()
                key = w.root / "owner.key"
                key.write_text("")
                w.env["BENCH_TOKEN"] = str(key)
                r = w.bench("run", w.script(f"WRITE fs {path} minted\n"))
                self.assertEqual(r.returncode == 0, ok, r.stdout)
                self.assertFalse(w.token.exists(), "a WRITE minted the owner token")


def hold_quota():
    hdr = (IMAGE / "supervisor" / "frame.h").read_text()
    return int(re.search(r"#define HOLD_QUOTA_BYTES (\d+)u", hdr).group(1))


class TestHoldQuota(unittest.TestCase):
    """hold/ may grow by HOLD_QUOTA_BYTES per session. over is a failed step, not a hang."""

    def writer(self, w, nbytes, name="fill.py"):
        return w.tool(name, f"open('hold/fill.bin', 'wb').write(b'x' * {nbytes})\n")

    def test_over_quota_is_a_failed_step(self):
        w = addWorld(self)
        prog = self.writer(w, hold_quota() + 1)
        r = w.bench("run", w.script(f"EXEC {prog}\nWAIT 1\n"), timeout=30)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("hold-quota", r.stdout)
        self.assertNotIn("MAIN", r.stdout)
        st = w.state()
        self.assertEqual((st["status"], st["n"]), ("fault", "1"))   # WAIT never ran
        self.assertEqual(len(w.snaps()), 2)                          # the failed step was snapped
        self.assertIn("fault=hold-quota", (w.snaps()[-1] / "MANIFEST").read_text())

    def test_at_quota_is_legal(self):
        w = addWorld(self)
        prog = self.writer(w, hold_quota())
        r = w.bench("run", w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_quota_counts_growth_not_old_hold(self):
        # a hold/ left over from an earlier session does not block the next one.
        w = addWorld(self)
        (w.root / "hold" / "old.bin").write_bytes(b"y" * (2 * hold_quota()))
        r = w.bench("run", w.script("WRITE fs hold/note.txt still fits\n"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_quota_is_frozen_in_session_file(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        sess = (w.session() / "SESSION").read_text()
        self.assertIn(f"hold_quota={hold_quota()}\n", sess)
        self.assertIn("hold_base=", sess)


class TestCage(unittest.TestCase):
    """the OS cage the source predicate cannot be: seccomp, landlock, rom-hash."""

    def test_seccomp_denies_the_antenna(self):
        w = addWorld(self)
        w.tool("net.py", "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n")
        r = w.bench("run", w.script("EXEC tools/net.py\n"))
        self.assertNotEqual(r.returncode, 0, "a tool opening a socket must fault")

    def test_seccomp_denies_ptrace(self):
        w = addWorld(self)
        w.tool("trace.py", "import ctypes\n"  # ctypes import is dirty at source; here we test OS layer
                           "libc = ctypes.CDLL(None)\n"
                           "libc.ptrace(0, 0, 0, 0)\n")
        r = w.bench("run", w.script("EXEC tools/trace.py\n"))
        self.assertNotEqual(r.returncode, 0)

    def test_landlock_denies_write_to_rom(self):
        w = addWorld(self)
        w.tool("pwn.py", "open('tests/rom/pwn.py', 'w').write('x')\n")
        r = w.bench("run", w.script("EXEC tools/pwn.py\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((w.root / "tests" / "rom" / "pwn.py").exists())

    def test_landlock_denies_write_to_main(self):
        w = addWorld(self)
        w.tool("m.py", "open('main/owned.txt', 'w').write('x')\n")
        r = w.bench("run", w.script("EXEC tools/m.py\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((w.root / "main" / "owned.txt").exists())

    def test_landlock_allows_write_to_hold(self):
        w = addWorld(self)
        w.tool("h.py", "open('hold/scratch.txt', 'w').write('ok')\n")
        r = w.bench("run", w.script("EXEC tools/h.py\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((w.root / "hold" / "scratch.txt").read_text(), "ok")

    def test_env_is_scrubbed(self):
        # a tool child must not inherit PYTHONPATH / LD_PRELOAD from the parent.
        w = addWorld(self)
        w.tool("env.py",
               "import os\n"
               "bad = [k for k in ('LD_PRELOAD','PYTHONPATH','PYTHONSTARTUP') if k in os.environ]\n"
               "raise SystemExit(1 if bad else 0)\n")
        env = dict(w.env, LD_PRELOAD="/tmp/evil.so", PYTHONPATH="/tmp/evil", PYTHONSTARTUP="/tmp/x")
        r = subprocess.run([str(BENCH), "run", w.script("EXEC tools/env.py\n")],
                           cwd=IMAGE, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        self.assertEqual(r.returncode, 0, "scrubbed env leaked a dangerous var:\n" + r.stdout)

    def test_symlink_out_of_world_is_not_followed_into_rom(self):
        # a symlink in hold/ pointing at a rom file must not let the intern rewrite ROM,
        # and the snapshot must not treat the link as board state.
        w = addWorld(self)
        link = w.root / "hold" / "sneaky"
        link.symlink_to(w.root / "tests" / "rom" / "test_isa.py")
        w.tool("sl.py", "open('hold/sneaky', 'w').write('# pwned\\n')\n")
        rom_before = (w.root / "tests" / "rom" / "test_isa.py").read_text()
        w.bench("run", w.script("EXEC tools/sl.py\n"))
        self.assertEqual((w.root / "tests" / "rom" / "test_isa.py").read_text(), rom_before,
                         "writing through a hold/ symlink reached ROM")

    def test_rom_hash_tamper_refuses_boot(self):
        w = addWorld(self)
        # first prove it boots clean
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        # now change a rom file in the world and demand refusal (unless the build was UNPINNED)
        (w.root / "tests" / "rom" / "test_isa.py").write_text(
            (w.root / "tests" / "rom" / "test_isa.py").read_text() + "\n# tamper\n")
        r = w.bench("run", w.script("WAIT 1\n"))
        if "ROM not pinned" in r.stdout:
            self.skipTest("binary built UNPINNED (no rom_hash.h); run via make to enforce")
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("ROM image changed", r.stdout)


if __name__ == "__main__":
    unittest.main()
