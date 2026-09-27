"""The harness. NOT Ring 0 — make launches it, a human's privilege, not ROM python.

Woz's one gate: the supervisor is started by `make test` (you), never by a ROM file
spawning a cousin. So this file is free to use subprocess; it lives outside tests/rom/
and is not subject to is_ring0. It drives the compiled binary and reads the board.

It builds bench through `make` so the binary is ROM-pinned, then runs each fixture in a
throwaway world (a copy of the image + main/hello.txt). Radio stays unplugged throughout.
"""
import hashlib
import os
import re
import shutil
import stat
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(IMAGE))
sys.path.insert(0, str(IMAGE / "tools"))
from isa.hotz_isa import OWNER_TOKEN, Kind, Op, Ring, Step, hook  # noqa: E402
from isa.karpathy_rom import is_ring0  # noqa: E402
from peek import woz_bits  # noqa: E402

BENCH = IMAGE / "supervisor" / "bench"
HELPER = IMAGE / "supervisor" / "bench-helper"
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
    r = subprocess.run(["make", "supervisor/bench", "supervisor/bench-helper"], cwd=IMAGE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise AssertionError("make supervisor/bench supervisor/bench-helper failed:\n" + r.stdout)


class World:
    """a throwaway copy of the image; the supervisor runs against it via BENCH_ROOT."""
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="bench-h-"))
        ign = shutil.ignore_patterns("__pycache__", "bench", "bench-helper", "bus_test", "romhash", "*.o")
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


def rmtree_force(path):
    # snaps are sealed read-only (dirs 0555); restore write so the temp world can be removed.
    def fix(func, p, exc):     # (function, path, exc) — matches onexc (3.12+) and onerror (older)
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    arg = "onexc" if sys.version_info >= (3, 12) else "onerror"
    try:
        shutil.rmtree(path, **{arg: fix})
    except OSError:
        pass


def addWorld(case):
    w = World()
    case.addCleanup(rmtree_force, w.root)
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

    def test_hook_agrees_with_c_gates(self):
        # default board: fs + tty plugged, fb/judge/radio pulled. hook() deny <=> C deny.
        plugged = frozenset({"fs", "tty"})
        table = [
            ("READ fs main/hello.txt", Step(Op.READ, "fs", "main/hello.txt", None, Ring.WORK)),
            ("READ fb main/hello.txt", Step(Op.READ, "fb", "main/hello.txt", None, Ring.WORK)),
            ("READ judge main/hello.txt", Step(Op.READ, "judge", "main/hello.txt", None, Ring.WORK)),
            ("EXEC tools/hash.py main/hello.txt", Step(Op.EXEC, "tools/hash.py", "main/hello.txt", None, Ring.WORK)),
            ("TEST PURE tests/rom/test_isa.py", Step(Op.TEST, "fs", "tests/rom/test_isa.py", Kind.PURE, Ring.WORK)),
            ("TEST JUDGE tests/rom/test_isa.py", Step(Op.TEST, "fs", "tests/rom/test_isa.py", Kind.JUDGE, Ring.HOLD)),
            ("TEST VISUAL tests/rom/test_isa.py", Step(Op.TEST, "fs", "tests/rom/test_isa.py", Kind.VISUAL, Ring.WORK)),
            ("WAIT 1", Step(Op.WAIT, "", "1", None, Ring.WORK)),
        ]
        for line, step in table:
            with self.subTest(line=line):
                w = addWorld(self)
                r = w.bench("run", w.script(line + "\n"))
                c_denied = "deny" in r.stdout
                self.assertEqual(hook(step, plugged, radio=False) is None, c_denied, r.stdout)

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

    def start(self, w, script):
        proc = subprocess.Popen([str(BENCH), "run", w.script(script)], cwd=IMAGE, env=w.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if (w.root / "sessions" / "CURRENT").exists() and (w.session() / "snap-1").exists():
                return proc
            time.sleep(0.02)
        self.fail("session never reached snap-1")

    def test_kill_reaches_a_running_child(self):
        # KILL must not wait out T_tool: the child is killed at once, the step is snapped, then stop.
        w = addWorld(self)
        w.tool("slow.py", "import time\ntime.sleep(4)\nopen('hold/done', 'w').write('x')\n")
        proc = self.start(w, "WAIT 1\nEXEC tools/slow.py\nWAIT 1\n")
        time.sleep(0.5)                      # the child is up and sleeping
        t0 = time.monotonic()
        self.assertEqual(w.bench("kill").returncode, 0)
        out, _ = proc.communicate(timeout=15)
        self.assertLess(time.monotonic() - t0, 2.0, "supervisor waited out the child after KILL")
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(w.state()["status"], "halt")
        self.assertFalse((w.root / "hold" / "done").exists())
        self.assertIn("halt op=exec", (w.snaps()[-1] / "MANIFEST").read_text())
        self.assertEqual(w.state()["n"], "2")   # WAIT, EXEC (cut). the last WAIT never ran.

    def test_removing_the_token_stops_the_next_frame(self):
        w = addWorld(self)
        proc = self.start(w, "WAIT 400\n" * 6)
        w.disarm()
        out, _ = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 5, out)
        self.assertIn("disarmed", out)
        self.assertEqual(w.state()["status"], "disarmed")
        self.assertLess(int(w.state()["n"]), 6)
        self.assertNotIn("MAIN", out)

    def test_replacing_the_token_stops_the_next_frame(self):
        # a different file at the same path is not the token that armed this run.
        # replace atomically (write temp, rename onto the path) so the gate never sees a gap:
        # the file is always present, only its identity (ino) changes -> "changed since arm".
        w = addWorld(self)
        proc = self.start(w, "WAIT 400\n" * 6)
        tmp = w.token.with_suffix(".new")
        tmp.write_text("")
        os.replace(tmp, w.token)
        out, _ = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 5, out)
        self.assertIn("changed since arm", out)
        self.assertEqual(w.state()["status"], "disarmed")

    def test_touching_the_token_stops_the_next_frame(self):
        w = addWorld(self)
        proc = self.start(w, "WAIT 400\n" * 6)
        st = w.token.stat()
        os.utime(w.token, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        out, _ = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 5, out)
        self.assertIn("changed since arm", out)

    def test_second_run_in_the_same_world_is_refused(self):
        w = addWorld(self)
        first = self.start(w, "WAIT 300\n" * 4)
        cur = (w.root / "sessions" / "CURRENT").read_text()
        r = w.bench("run", w.script("WAIT 1\n", name="second.ops"))
        self.assertEqual(r.returncode, 7, r.stdout)
        self.assertIn("world busy", r.stdout)
        self.assertIn(f"pid {first.pid}", r.stdout)
        self.assertEqual((w.root / "sessions" / "CURRENT").read_text(), cur)   # untouched
        out, _ = first.communicate(timeout=15)
        self.assertEqual(first.returncode, 0, out)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n", name="third.ops")).returncode, 0)

    def test_kill_never_signals_a_stale_pid(self):
        # a run that died hard left PID behind and STATE at run. the pid now belongs to
        # something else: kill must not touch it, and status must say crashed.
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        other = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: other.poll() is None and other.kill())
        (w.session() / "PID").write_text(f"{other.pid}\n")
        st = (w.session() / "STATE").read_text().replace("status=ok", "status=run")
        (w.session() / "STATE").write_text(st)
        r = w.bench("kill")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("not signalled", r.stdout)
        time.sleep(0.2)
        self.assertIsNone(other.poll(), "kill signalled a pid that is not the live run")
        self.assertIn("crashed", w.bench("status").stdout)

    def test_wait_evidence_says_what_was_slept(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 20\n")).returncode, 0)
        man = (w.snaps()[-1] / "MANIFEST").read_text()
        slept = int(re.search(r"slept=(\d+)", man).group(1))
        self.assertGreaterEqual(slept, 20)

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

    def test_token_must_not_be_group_or_world_writable(self):
        for mode in (0o666, 0o620, 0o602):
            with self.subTest(mode=oct(mode)):
                w = addWorld(self)
                w.token.chmod(mode)
                r = w.bench("run", w.script("WAIT 1\n"))
                self.assert_refused(w, r)
                self.assertIn("writable", r.stdout)

    def test_token_may_be_owner_only(self):
        w = addWorld(self)
        w.token.chmod(0o600)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)

    def test_token_must_belong_to_the_runner(self):
        if os.getuid() != 0:
            self.skipTest("needs root to hand the token to another uid")
        w = addWorld(self)
        os.chown(w.token, 65534, 65534)
        r = w.bench("run", w.script("WAIT 1\n"))
        self.assert_refused(w, r)
        self.assertIn("not owned", r.stdout)

    def test_token_link_does_not_arm(self):
        w = addWorld(self)
        real = w.root / "real.key"
        real.write_text("")
        w.disarm()
        w.token.symlink_to(real)
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


# a stand-in helper: same argv and socket as bench-helper, scripted answers. harness only.
STUB = """#!{py}
import socket, sys, time
ls = socket.socket(fileno=int(sys.argv[2]))
c, _ = ls.accept()
ls.close()
ANS = {answers!r}
for line in c.makefile("rb"):
    a = ANS.get(line.decode().split()[0])
    if a is None:
        break
    if a == "SLEEP":
        time.sleep(10)
        break
    c.sendall((a + "\\n").encode())
"""


LINE = re.compile(
    r"^(?P<id>\S+) (?P<status>\S+) n=(?P<n>\d+)/(?P<N>\d+) snap=(?P<snap>\S+) lamps=(?P<lamps>\S+) "
    r"hold=(?P<hold>[+-]\d+)/(?P<hq>\d+) files=(?P<files>[+-]\d+)/(?P<fq>\d+) "
    r"armed=(?P<armed>yes|no) helper=(?P<helper>\S+) lock=(?P<lock>held|free)$")


class TestStatusLine(unittest.TestCase):
    """bench status --line: one line, the whole board, grep-able."""

    def line(self, w):
        r = w.bench("status", "--line")
        out = r.stdout.strip()
        self.assertEqual(len(out.splitlines()), 1, out)
        return r, out

    def test_no_session(self):
        w = addWorld(self)
        r, out = self.line(w)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out, "none dark armed=yes lock=free")
        w.disarm()
        self.assertEqual(self.line(w)[1], "none dark armed=no lock=free")

    def test_after_a_run(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WRITE fs hold/a.txt hello\nWAIT 1\n")).returncode, 0)
        _, out = self.line(w)
        m = LINE.match(out)
        self.assertIsNotNone(m, out)
        self.assertEqual(m["id"], w.state()["session"])
        self.assertEqual((m["status"], m["n"], m["N"]), ("ok", "2", "8"))
        self.assertEqual(m["snap"], w.state()["snap"])
        self.assertEqual(m["lamps"], "HOLD,BLIND")
        self.assertEqual((m["hold"], m["hq"]), ("+6", str(hold_quota())))
        self.assertEqual((m["files"], m["fq"]), ("+1", str(hold_files_quota())))
        self.assertEqual((m["armed"], m["helper"], m["lock"]), ("yes", "v0", "free"))

    def test_while_running_and_after_a_crash(self):
        w = addWorld(self)
        proc = subprocess.Popen([str(BENCH), "run", w.script("WAIT 400\n" * 4)], cwd=IMAGE, env=w.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not ((w.root / "sessions" / "CURRENT").exists()
                                                   and (w.session() / "snap-1").exists()):
            time.sleep(0.02)
        m = LINE.match(self.line(w)[1])
        self.assertEqual((m["status"], m["lock"]), ("run", "held"))
        proc.kill()          # a hard stop: no end written
        proc.wait(timeout=10)
        m = LINE.match(self.line(w)[1])
        self.assertEqual((m["status"], m["lock"]), ("crashed", "free"))

    def test_status_takes_only_line(self):
        w = addWorld(self)
        self.assertEqual(w.bench("status", "--json").returncode, 2)


from hash import tree_hash  # noqa: E402  (tools/hash.py: same bytes as the C tree hash)


NOBODY = 65534


def write_as_nobody(path):
    """try to open path for writing after dropping to an unprivileged uid, in a child.
    returns 'denied' (PermissionError), 'wrote' (succeeded), or 'skip' (cannot drop)."""
    r, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        try:
            os.setgroups([]); os.setgid(NOBODY); os.setuid(NOBODY)
        except OSError:
            os.write(wfd, b"skip"); os._exit(0)
        try:
            with open(path, "r+") as f:
                f.write("x")
            os.write(wfd, b"wrote")
        except PermissionError:
            os.write(wfd, b"denied")
        except OSError:
            os.write(wfd, b"denied")
        os._exit(0)
    os.close(wfd)
    out = os.read(r, 16).decode()
    os.close(r)
    os.waitpid(pid, 0)
    return out


class TestSealing(unittest.TestCase):
    """a finished snapshot is sealed read-only on disk: files 0444, dirs 0555. mode bits stop
    every non-root writer (the intended deployment). Root ignores them — the absolute guarantee
    is the content hash checked by `bench verify` (see TestVerify)."""

    def test_snap_tree_is_read_only(self):
        w = addWorld(self)
        (w.root / "hold" / "keep.txt").write_text("base\n")
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        snap = w.snaps()[-1]
        self.assertEqual(stat.S_IMODE((snap / "hold").stat().st_mode), 0o555)
        self.assertEqual(stat.S_IMODE((snap / "hold" / "keep.txt").stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE((snap / "MANIFEST").stat().st_mode), 0o444)

    def test_a_non_root_actor_cannot_write_a_shared_inode(self):
        # keep.txt is unchanged across three steps, so snap-1 and snap-2 hard-link snap-0's copy.
        w = addWorld(self)
        (w.root / "hold" / "keep.txt").write_text("frozen\n")
        self.assertEqual(w.bench("run", w.script("WAIT 1\nWAIT 1\n")).returncode, 0)
        s0, s1, s2 = (snap / "hold" / "keep.txt" for snap in w.snaps())
        self.assertEqual(s0.stat().st_ino, s2.stat().st_ino)      # one inode, three links
        self.assertGreaterEqual(s0.stat().st_nlink, 3)
        for link in (s0, s1, s2):                                  # no link is a writable door in
            outcome = write_as_nobody(link)
            if outcome == "skip":
                self.skipTest("cannot drop privileges to test non-root denial")
            self.assertEqual(outcome, "denied", f"a non-root write to {link} was not denied")
        self.assertEqual(s0.read_text(), "frozen\n")

    def test_restore_and_retention_still_work_on_sealed_snaps(self):
        w = addWorld(self)
        (w.root / "hold" / "keep.txt").write_text("v1\n")
        self.assertEqual(w.bench("run", w.script("WRITE fs hold/keep.txt v2\n")).returncode, 0)
        old = w.session().name
        self.assertEqual(w.bench("restore", f"{old}/snap-0").returncode, 0)   # reads sealed snap
        self.assertEqual((w.root / "hold" / "keep.txt").read_text(), "v1\n")
        # retention must be able to delete a sealed snap tree
        r = w.bench("run", "--keep", "1", w.script("WAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertFalse((w.root / "sessions" / old).exists())


class TestDeltaSnaps(unittest.TestCase):
    """an unchanged hold/ file is hard-linked from the previous snap; the snap is still the board."""

    def world_with(self, count):
        w = addWorld(self)
        (w.root / "hold" / "m").mkdir()
        for i in range(count):
            (w.root / "hold" / "m" / str(i)).write_text(f"file {i}\n")
        return w

    def delta(self, snap):
        man = (snap / "MANIFEST").read_text()
        m = re.search(r"delta=linked:(\d+) copied:(\d+)", man)
        return int(m[1]), int(m[2])

    def assert_snaps_are_the_board(self, w):
        # each board snap's hold/, with main/, hashes to the MANIFEST tree= (main/ is read-only).
        for snap in w.snaps():
            man = (snap / "MANIFEST").read_text()
            tree = re.search(r"^tree=(\S+)$", man, re.M)[1]
            if tree.startswith("skipped:"):
                continue
            base = Path(tempfile.mkdtemp(prefix="bench-snapcheck-"))
            self.addCleanup(shutil.rmtree, base, ignore_errors=True)
            shutil.copytree(w.root / "main", base / "main")
            if (snap / "hold").exists():
                shutil.copytree(snap / "hold", base / "hold")
            self.assertEqual(tree_hash(["main", "hold"], base), tree, snap.name)

    def test_unchanged_files_are_linked(self):
        w = self.world_with(300)
        r = w.bench("run", w.script("WAIT 1\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        s0, s1, s2 = w.snaps()
        self.assertEqual(self.delta(s0), (0, 300))
        self.assertEqual(self.delta(s1), (300, 0))
        self.assertEqual((s0 / "hold/m/5").stat().st_ino, (s2 / "hold/m/5").stat().st_ino)
        self.assert_snaps_are_the_board(w)

    def test_changed_file_is_copied_even_with_mtime_put_back(self):
        # same size, mtime restored: ctime still moved, so the snap copies the new bytes.
        w = self.world_with(20)
        w.tool("edit.py", "import os\np = 'hold/m/3'\nst = os.stat(p)\n"
                          "open(p, 'r+').write('FILE 3')\n"
                          "os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))\n")
        r = w.bench("run", w.script("EXEC tools/edit.py\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        s0, s1, s2 = w.snaps()
        self.assertEqual(self.delta(s1), (19, 1))
        self.assertEqual((s1 / "hold/m/3").read_text(), "FILE 3\n")
        self.assertEqual((s0 / "hold/m/3").read_text(), "file 3\n")      # the old snap kept its bytes
        self.assertNotEqual((s0 / "hold/m/3").stat().st_ino, (s1 / "hold/m/3").stat().st_ino)
        self.assert_snaps_are_the_board(w)

    def test_new_and_removed_files(self):
        w = self.world_with(5)
        r = w.bench("run", w.script("WRITE fs hold/m/new.txt fresh\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.delta(w.snaps()[1]), (5, 1))
        self.assert_snaps_are_the_board(w)

    def test_a_name_with_a_newline_is_always_copied(self):
        w = self.world_with(2)
        w.tool("nl.py", "open('hold/m/a\\nb', 'w').write('x')\n")
        r = w.bench("run", w.script("EXEC tools/nl.py\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        s2 = w.snaps()[2]
        self.assertEqual(self.delta(s2), (2, 1))
        self.assertNotIn("a\nb", (s2 / "INDEX").read_text())
        self.assert_snaps_are_the_board(w)

    def test_a_thousand_files_fit_the_frame(self):
        # the case that faulted T_frame before delta snaps: 1000 files already in hold/.
        w = self.world_with(1000)
        r = w.bench("run", w.script("WAIT 1\nWAIT 1\nWAIT 1\n"), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.delta(w.snaps()[-1]), (1000, 0))


class TestRestore(unittest.TestCase):
    """bench restore <snap>: resume = load snap. verified before anything moves."""

    def two_writes(self):
        w = addWorld(self)
        r = w.bench("run", w.script("WRITE fs hold/a.txt one\nWRITE fs hold/a.txt two\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        return w, w.state()["session"]

    def test_restore_round_trip(self):
        w, old = self.two_writes()
        tree1 = re.search(r"^tree=(\S+)$", (w.session() / "snap-1" / "MANIFEST").read_text(), re.M)[1]
        r = w.bench("restore", "snap-1")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((w.root / "hold" / "a.txt").read_text(), "one\n")
        new = w.session()
        self.assertNotEqual(new.name, old)
        self.assertEqual((new / "hold.before" / "a.txt").read_text(), "two\n")    # kept, not deleted
        self.assertIn(f"tree={tree1}", (new / "snap-0" / "MANIFEST").read_text())
        self.assertIn(f"restored_from={old}/snap-1", (new / "SESSION").read_text())
        self.assertEqual(w.state()["status"], "restored")
        # hold/ is the tools' to write: it must never share an inode with a snap
        self.assertEqual((w.root / "hold" / "a.txt").stat().st_nlink, 1)
        # and the world runs on from the restored board
        self.assertEqual(w.bench("run", w.script("READ fs hold/a.txt\n")).returncode, 0)
        self.assertEqual((w.session() / "out-1").read_text(), "one\n")

    def test_named_session_snap(self):
        w, old = self.two_writes()
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        r = w.bench("restore", f"{old}/snap-1")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((w.root / "hold" / "a.txt").read_text(), "one\n")

    def test_damaged_snap_moves_nothing(self):
        w, _ = self.two_writes()
        victim = w.session() / "snap-1" / "hold" / "a.txt"
        os.chmod(w.session() / "snap-1" / "hold", 0o700)   # sealed: an attacker must unseal first
        victim.chmod(0o600)
        victim.write_text("forged\n")
        r = w.bench("restore", "snap-1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("does not hash", r.stdout)
        self.assertEqual((w.root / "hold" / "a.txt").read_text(), "two\n")

    def test_main_changed_since_moves_nothing(self):
        w, _ = self.two_writes()
        (w.root / "main" / "hello.txt").write_text("edited by the owner\n")
        r = w.bench("restore", "snap-1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual((w.root / "hold" / "a.txt").read_text(), "two\n")

    def test_snap_without_a_board_is_refused(self):
        w = addWorld(self)
        w.bench("run", "--hold-quota", "1", w.script("WRITE fs hold/a.txt too big\n"))
        r = w.bench("restore", "snap-1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("holds no board", r.stdout)

    def test_restore_needs_the_owner(self):
        w, _ = self.two_writes()
        w.disarm()
        self.assertEqual(w.bench("restore", "snap-1").returncode, 5)
        self.assertEqual((w.root / "hold" / "a.txt").read_text(), "two\n")

    def test_bad_names(self):
        w, old = self.two_writes()
        for bad in ("../x/snap-1", "snap-", "snap-1x", f"{old}/../snap-1", "/snap-1", "MANIFEST"):
            with self.subTest(bad=bad):
                self.assertEqual(w.bench("restore", bad).returncode, 2)
        self.assertEqual(w.bench("restore").returncode, 2)


class TestDemo(unittest.TestCase):
    """demo: a knife sized to the ROM, a lock that proves its pid to kill."""

    def slow_demo(self, w):
        (w.root / "tools" / "test_runner.py").write_text("import time\ntime.sleep(20)\nprint('GREEN 0 tests')\n")
        proc = subprocess.Popen([str(BENCH), "demo"], cwd=IMAGE, env=w.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (w.root / "sessions" / "DEMO").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        return proc

    def test_knife_is_t_tool_per_rom_file(self):
        w = addWorld(self)
        roms = len(list((w.root / "tests" / "rom").glob("test_*.py")))
        r = w.bench("demo")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"demo: roms={roms} knife={5000 * roms}ms", r.stdout)

    def test_kill_reaches_a_running_demo(self):
        w = addWorld(self)
        proc = self.slow_demo(w)
        t0 = time.monotonic()
        r = w.bench("kill")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"KILL demo pid {proc.pid}", r.stdout)
        out, _ = proc.communicate(timeout=10)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("HALT demo killed", out)

    def test_one_demo_at_a_time(self):
        w = addWorld(self)
        self.slow_demo(w)
        r = w.bench("demo")
        self.assertEqual(r.returncode, 7, r.stdout)
        self.assertIn("already running", r.stdout)


class TestOpsTable(unittest.TestCase):
    """every row of tests/rom/test_ops.py OPS_TABLE, through the binary."""

    def test_c_agrees_with_the_rom_ops_table(self):
        sys.path.insert(0, str(IMAGE / "tests" / "rom"))
        from test_ops import OPS_TABLE
        w = addWorld(self)
        for i, (line, expect) in enumerate(OPS_TABLE):
            with self.subTest(line=line):
                r = w.bench("run", w.script(line + "\n", name=f"row{i}.ops"))
                if expect == "ok":
                    self.assertEqual(r.returncode, 0, r.stdout)
                else:
                    self.assertNotEqual(r.returncode, 0, r.stdout)
                    self.assertIn(expect, r.stdout)
                self.assertNotIn(" MAIN", r.stdout)


class TestRetention(unittest.TestCase):
    """run keeps the newest M session dirs (default 20), counting its own."""

    def fake_sessions(self, w, count):
        names = [f"{1000000000 + i}-{100 + i}" for i in range(count)]
        for n in names:
            (w.root / "sessions" / n).mkdir()
            (w.root / "sessions" / n / "STATE").write_text("status=ok\n")
        return names

    def session_dirs(self, w):
        return sorted(p.name for p in (w.root / "sessions").iterdir()
                      if p.is_dir() and re.fullmatch(r"\d+-\d+", p.name))

    def test_default_keeps_twenty(self):
        w = addWorld(self)
        names = self.fake_sessions(w, 25)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        left = self.session_dirs(w)
        self.assertEqual(len(left), 20)
        self.assertIn(w.session().name, left)
        self.assertTrue(set(names[-19:]) <= set(left))             # the newest old ones
        self.assertFalse(set(names[:6]) & set(left))
        self.assertIn("RETAIN keep=20 removed=6", (w.session() / "log").read_text())

    def test_keep_flag_and_env(self):
        w = addWorld(self)
        self.fake_sessions(w, 6)
        self.assertEqual(w.bench("run", "--keep", "3", w.script("WAIT 1\n")).returncode, 0)
        self.assertEqual(len(self.session_dirs(w)), 3)
        prev = w.session().name
        w.env["BENCH_KEEP"] = "1"
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        # keep=1, but the previous run was CURRENT when pruning ran: it stays (a failed start
        # must not leave CURRENT pointing at a deleted dir). the next run then prunes it.
        self.assertEqual(self.session_dirs(w), sorted([prev, w.session().name]))
        last = w.session().name
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        self.assertEqual(self.session_dirs(w), sorted([last, w.session().name]))
        for bad in ("0", "x", "-1"):
            self.assertEqual(w.bench("run", "--keep", bad, w.script("WAIT 1\n")).returncode, 2)

    def test_never_pruned(self):
        w = addWorld(self)
        names = self.fake_sessions(w, 5)
        (w.root / "sessions" / "CURRENT").write_text(names[0] + "\n")     # oldest is CURRENT
        (w.root / "sessions" / names[1] / "hold.before").mkdir()          # owner's old hold/
        (w.root / "sessions" / "notes").mkdir()                             # not a session dir
        (w.root / "sessions" / "e2e-1").mkdir()
        self.assertEqual(w.bench("run", "--keep", "1", w.script("WAIT 1\n")).returncode, 0)
        left = set(self.session_dirs(w))
        self.assertIn(names[0], left)
        self.assertIn(names[1], left)
        self.assertFalse({names[2], names[3], names[4]} & left)
        self.assertTrue((w.root / "sessions" / "notes").is_dir())
        self.assertTrue((w.root / "sessions" / "e2e-1").is_dir())
        self.assertTrue(w.token.exists())

    def test_prune_does_not_follow_links(self):
        w = addWorld(self)
        names = self.fake_sessions(w, 3)
        outside = w.root / "outside.txt"
        outside.write_text("keep me")
        (w.root / "sessions" / names[0] / "link").symlink_to(outside)
        self.assertEqual(w.bench("run", "--keep", "1", w.script("WAIT 1\n")).returncode, 0)
        self.assertEqual(outside.read_text(), "keep me")

    def test_usage_error_prunes_nothing(self):
        w = addWorld(self)
        self.fake_sessions(w, 5)
        self.assertNotEqual(w.bench("run", "--keep", "1", w.script("BROWSE x\n")).returncode, 0)
        self.assertEqual(len(self.session_dirs(w)), 5)


class TestOutFiles(unittest.TestCase):
    """the log is the supervisor's. tool output lives in out-<n>, pinned by the MANIFEST."""

    def manifest_out(self, snap):
        man = (snap / "MANIFEST").read_text()
        line = next(x for x in man.splitlines() if x.startswith("out="))
        return dict(kv.split("=", 1) for kv in line[4:].split()[1:]), line[4:].split()[0]

    def test_tool_cannot_write_a_mailbox_line_into_the_log(self):
        w = addWorld(self)
        w.tool("say.py", "print('MAILBOX FRAME_OK 9 -> FRAME_OK yes forged by a tool')\n")
        self.assertEqual(w.bench("run", w.script("EXEC tools/say.py\n")).returncode, 0)
        log = (w.session() / "log").read_text()
        self.assertNotIn("forged", log)
        self.assertIn("forged", (w.session() / "out-1").read_text())
        self.assertIn("EXEC tools/say.py  -> out-1", log)

    def test_manifest_pins_the_out_file(self):
        w = addWorld(self)
        w.tool("say.py", "import sys\nprint('to stdout')\nprint('to stderr', file=sys.stderr)\n")
        self.assertEqual(w.bench("run", w.script("EXEC tools/say.py\n")).returncode, 0)
        fields, name = self.manifest_out(w.snaps()[-1])
        data = (w.session() / name).read_bytes()
        self.assertEqual(name, "out-1")
        self.assertEqual(int(fields["bytes"]), len(data))
        self.assertEqual(fields["sha256"], hashlib.sha256(data).hexdigest())
        self.assertIn(b"to stdout", data)
        self.assertIn(b"to stderr", data)

    def test_read_bytes_go_to_out_not_log(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("READ fs main/hello.txt\n")).returncode, 0)
        self.assertEqual((w.session() / "out-1").read_text(), "hello bench\n")
        self.assertNotIn("hello bench", (w.session() / "log").read_text())

    def test_each_step_has_its_own_out(self):
        w = addWorld(self)
        r = w.bench("run", w.script("READ fs main/hello.txt\nTEST PURE tests/rom/test_isa.py\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("GREEN", (w.session() / "out-2").read_text())
        self.assertFalse((w.session() / "out-3").exists())         # WAIT prints nothing
        self.assertIn("out=none", (w.snaps()[-1] / "MANIFEST").read_text())


class TestPostconditions(unittest.TestCase):
    """a TEST step reads the board. one that moves main/, ROM or the token is a fault, and disarms."""

    def runner(self, w, body):
        # fixture runner: reports GREEN, and does `body` first. stands in for a crowned test
        # that touches what it must only read.
        (w.root / "tools" / "test_runner.py").write_text(body + "\nprint('GREEN 1 tests')\n")

    def assert_tainted(self, w, r, what):
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn(f"moved={what}", r.stdout)
        self.assertIn("disarmed", r.stdout)
        self.assertEqual(w.state()["status"], "disarmed")
        man = (w.snaps()[-1] / "MANIFEST").read_text()
        self.assertIn("tree=skipped:tainted", man)
        self.assertFalse((w.snaps()[-1] / "hold").exists())
        self.assertIn("TAINT", (w.session() / "log").read_text())

    def test_clean_test_passes(self):
        w = addWorld(self)
        r = w.bench("run", w.script("TEST PURE tests/rom/test_isa.py\nWAIT 1\n"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_moving_main_disarms(self):
        w = addWorld(self)
        self.runner(w, "open('main/moved.txt', 'w').write('x')")
        r = w.bench("run", w.script("TEST PURE tests/rom/test_isa.py\nWAIT 1\n"))
        self.assert_tainted(w, r, "main")
        self.assertEqual(w.state()["n"], "1")          # WAIT never ran

    def test_moving_rom_disarms(self):
        w = addWorld(self)
        self.runner(w, "open('tests/rom/test_isa.py', 'a').write('# moved\\n')")
        self.assert_tainted(w, w.bench("run", w.script("TEST PURE tests/rom/test_isa.py\n")), "rom")

    def test_minting_the_token_disarms_and_quarantines_it(self):
        w = addWorld(self)
        w.disarm()
        key = w.root / "owner.key"
        key.write_text("")
        w.env["BENCH_TOKEN"] = str(key)
        self.runner(w, "open('sessions/OWNER_TOKEN', 'w').write('')")
        r = w.bench("run", w.script("TEST PURE tests/rom/test_isa.py\n"))
        self.assert_tainted(w, r, "token")
        self.assertFalse(w.token.exists(), "a minted token was left in place")
        self.assertEqual(len(list((w.root / "sessions").glob("OWNER_TOKEN.tainted-*"))), 1)
        del w.env["BENCH_TOKEN"]
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 5)   # it arms nothing

    def test_touching_the_owner_token_disarms(self):
        w = addWorld(self)
        self.runner(w, "import os\nst = os.stat('sessions/OWNER_TOKEN')\n"
                       "os.utime('sessions/OWNER_TOKEN', ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))")
        r = w.bench("run", w.script("TEST PURE tests/rom/test_isa.py\n"))
        self.assert_tainted(w, r, "token")
        self.assertFalse(w.token.exists())

    def test_exec_is_not_held_to_test_postconditions(self):
        # EXEC writes hold/ by design; the post-condition is TEST's contract, not EXEC's.
        w = addWorld(self)
        w.tool("h.py", "open('hold/x', 'w').write('x')\n")
        self.assertEqual(w.bench("run", w.script("EXEC tools/h.py\n")).returncode, 0)


class TestMailbox(unittest.TestCase):
    """bench <-> bench-helper: PING, ARM_OK, FRAME_OK over a unix socket in sessions/<id>/."""

    def bench_with_helper(self, w, answers=None):
        # a copy of bench in its own dir, with a stub helper beside it (or none at all).
        d = w.root / "bin"
        d.mkdir(exist_ok=True)
        shutil.copy2(BENCH, d / "bench")
        if answers is not None:
            h = d / "bench-helper"
            h.write_text(STUB.format(py=sys.executable, answers=answers))
            h.chmod(0o755)
        return d / "bench"

    def run_copy(self, w, exe, script, timeout=30):
        return subprocess.run([str(exe), "run", w.script(script)], cwd=IMAGE, env=w.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)

    def assert_no_session(self, w, r, rc, text):
        self.assertEqual(r.returncode, rc, r.stdout)
        self.assertIn(text, r.stdout)
        self.assertNotIn("frame ", r.stdout)
        self.assertFalse((w.root / "sessions" / "CURRENT").exists())
        self.assertIn("session none", w.bench("status").stdout)

    # --- the real helper, through bench ---

    def test_log_records_the_three_words(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\nWAIT 1\n")).returncode, 0)
        log = (w.session() / "log").read_text()
        self.assertIn("MAILBOX PING -> PING yes", log)
        self.assertIn("MAILBOX ARM_OK -> ARM_OK yes", log)
        self.assertIn("MAILBOX FRAME_OK 1 -> FRAME_OK yes", log)
        self.assertIn("MAILBOX FRAME_OK 2 -> FRAME_OK yes", log)

    def test_socket_path_is_gone_after_pairing(self):
        w = addWorld(self)
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)
        self.assertEqual(list(w.session().glob("*.sock")), [])

    def test_mailbox_words_are_not_verbs(self):
        for line in ("PING", "ARM_OK", "FRAME_OK 1"):
            with self.subTest(line=line):
                w = addWorld(self)
                r = w.bench("run", w.script(line + "\n"))
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("unknown verb", r.stdout)

    # --- bench with a missing or scripted helper: fail closed ---

    def test_missing_helper_fails_closed(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, answers=None)
        self.assert_no_session(w, self.run_copy(w, exe, "WAIT 1\n"), 6, "helper missing")

    def test_silent_helper_fails_closed(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, {"PING": "SLEEP"})
        t0 = time.monotonic()
        self.assert_no_session(w, self.run_copy(w, exe, "WAIT 1\n"), 6, "helper silent")
        self.assertLess(time.monotonic() - t0, 8)

    def test_helper_refusing_arm_stops_start(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, {"PING": "PING yes helper v0", "ARM_OK": "ARM_OK no stub says no"})
        self.assert_no_session(w, self.run_copy(w, exe, "WAIT 1\n"), 5, "stub says no")

    def test_helper_refusing_frame_stops_before_the_step(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, {"PING": "PING yes helper v0", "ARM_OK": "ARM_OK yes stub",
                                         "FRAME_OK": "FRAME_OK no stub stops frames"})
        r = self.run_copy(w, exe, "WAIT 1\n")
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("stub stops frames", r.stdout)
        self.assertEqual((w.state()["status"], w.state()["n"]), ("disarmed", "0"))
        self.assertEqual(len(w.snaps()), 1)          # s0 only: the step never happened

    def test_wrong_helper_version_is_refused(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, {"PING": "PING yes helper v1", "ARM_OK": "ARM_OK yes stub"})
        self.assert_no_session(w, self.run_copy(w, exe, "WAIT 1\n"), 6, "helper version")

    def test_wrong_word_in_reply_is_a_broken_line(self):
        w = addWorld(self)
        exe = self.bench_with_helper(w, {"PING": "PING yes helper v0", "ARM_OK": "ARM_OK yes stub",
                                         "FRAME_OK": "PING yes not the question"})
        r = self.run_copy(w, exe, "WAIT 1\n")
        self.assertEqual(r.returncode, 6, r.stdout)
        self.assertIn("helper-lost", r.stdout)

    # --- the real helper, driven directly ---

    def start_helper(self, w):
        path = str(w.root / "sessions" / "direct.sock")
        ls = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ls.bind(path)
        ls.listen(1)
        proc = subprocess.Popen([str(HELPER), str(w.root), str(ls.fileno())],
                                pass_fds=(ls.fileno(),), env={})
        ls.close()
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return path, proc

    def ask(self, f, line):
        f.write((line + "\n").encode())
        f.flush()
        return f.readline().decode().rstrip("\n")

    def test_helper_three_words(self):
        w = addWorld(self)
        path, proc = self.start_helper(w)
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(path)
        f = c.makefile("rwb", buffering=0)
        self.assertEqual(self.ask(f, "PING"), "PING yes helper v0")
        self.assertEqual(self.ask(f, "ARM_OK"), "ARM_OK yes owner token present")
        self.assertEqual(self.ask(f, "FRAME_OK 7"), "FRAME_OK yes armed n=7")
        w.disarm()
        self.assertEqual(self.ask(f, "ARM_OK"), "ARM_OK no owner token absent")
        self.assertTrue(self.ask(f, "FRAME_OK 8").startswith("FRAME_OK no "))
        # one connection, ever: the listener is closed once the first is taken
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as late:
            with self.assertRaises(OSError):
                late.connect(path)
        # not one of the three words: the line closes, the helper exits nonzero
        self.assertEqual(self.ask(f, "UNPLUG radio"), "")
        c.close()
        self.assertEqual(proc.wait(timeout=5), 1)

    def test_helper_exits_on_eof(self):
        w = addWorld(self)
        path, proc = self.start_helper(w)
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(path)
        c.close()
        self.assertEqual(proc.wait(timeout=5), 0)

    def test_helper_answers_only_its_parent(self):
        # the helper's parent here is this test process; a sibling that connects first gets nothing.
        w = addWorld(self)
        path, proc = self.start_helper(w)
        sib = subprocess.run([sys.executable, "-c",
                              "import socket, sys\n"
                              "c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                              "c.connect(sys.argv[1]); c.sendall(b'PING\\n')\n"
                              "try:\n    got = c.recv(64)\n"
                              "except ConnectionResetError:\n    got = b''\n"
                              "print(repr(got))\n", path],
                             stdout=subprocess.PIPE, text=True, timeout=10)
        self.assertEqual(sib.stdout.strip(), "b''")
        self.assertEqual(proc.wait(timeout=5), 1)


def hold_quota():
    hdr = (IMAGE / "supervisor" / "frame.h").read_text()
    return int(re.search(r"#define HOLD_QUOTA_BYTES (\d+)u", hdr).group(1))


def hold_files_quota():
    hdr = (IMAGE / "supervisor" / "frame.h").read_text()
    return int(re.search(r"#define HOLD_QUOTA_FILES (\d+)u", hdr).group(1))


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
        man = (w.snaps()[-1] / "MANIFEST").read_text()
        self.assertIn("fault=hold-quota", man)
        # ...but not its oversized board: evidence yes, a copy of the thing the quota refused, no.
        self.assertIn("tree=skipped:over-quota", man)
        self.assertFalse((w.snaps()[-1] / "hold" / "fill.bin").exists())

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

    def test_flag_raises_quota_for_one_run(self):
        w = addWorld(self)
        prog = self.writer(w, hold_quota() + 1)
        r = w.bench("run", "--hold-quota", str(hold_quota() + 1), w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"hold_quota={hold_quota() + 1}\n", (w.session() / "SESSION").read_text())

    def test_env_lowers_quota(self):
        w = addWorld(self)
        w.env["BENCH_HOLD_QUOTA"] = "10"
        r = w.bench("run", w.script("WRITE fs hold/a.txt eleven bytes\n"))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("hold-quota", r.stdout)

    def test_flag_beats_env(self):
        w = addWorld(self)
        w.env["BENCH_HOLD_QUOTA"] = "10"
        r = w.bench("run", "--hold-quota", "100", w.script("WRITE fs hold/a.txt eleven bytes\n"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("hold_quota=100\n", (w.session() / "SESSION").read_text())

    def test_zero_quota_means_hold_may_not_grow(self):
        w = addWorld(self)
        ok = w.bench("run", "--hold-quota", "0", w.script("WAIT 1\n"))
        self.assertEqual(ok.returncode, 0, ok.stdout)
        grow = w.bench("run", "--hold-quota", "0", w.script("WRITE fs hold/a.txt x\n"))
        self.assertIn("hold-quota", grow.stdout)

    def test_bad_quota_is_usage_error_before_any_session(self):
        for bad in ("-1", "1k", " 5", "", "0x10", "99999999999"):
            with self.subTest(bad=bad):
                w = addWorld(self)
                r = w.bench("run", "--hold-quota", bad, w.script("WAIT 1\n"))
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertFalse((w.root / "sessions" / "CURRENT").exists())
        w = addWorld(self)
        w.env["BENCH_HOLD_QUOTA"] = "lots"
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 2)
        w.env["BENCH_HOLD_QUOTA"] = ""          # empty env is unset: the default applies
        self.assertEqual(w.bench("run", w.script("WAIT 1\n")).returncode, 0)

    def many(self, w, count, name="many.py"):
        return w.tool(name, f"import os\nos.makedirs('hold/m', exist_ok=True)\n"
                            f"for i in range({count}):\n    open(f'hold/m/{{i}}', 'w').close()\n")

    def test_too_many_files_is_a_files_fault(self):
        # 1025 empty files: zero bytes, over the entry quota.
        w = addWorld(self)
        prog = self.many(w, hold_files_quota())
        r = w.bench("run", w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("fault=hold-quota-files", r.stdout)
        self.assertNotIn("hold-quota-bytes", r.stdout)
        self.assertIn("tree=skipped:over-quota", (w.snaps()[-1] / "MANIFEST").read_text())

    def test_over_bytes_names_bytes(self):
        w = addWorld(self)
        prog = self.writer(w, hold_quota() + 1)
        r = w.bench("run", w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertIn("fault=hold-quota-bytes", r.stdout)

    def test_dirs_count_as_entries(self):
        w = addWorld(self)
        prog = self.many(w, 2)          # hold/m + 2 files = 3 entries
        ok = w.bench("run", "--hold-files", "3", w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        w2 = addWorld(self)
        prog = self.many(w2, 2)
        over = w2.bench("run", "--hold-files", "2", w2.script(f"EXEC {prog}\n"), timeout=30)
        self.assertIn("hold-quota-files grew=3 quota=2", over.stdout)

    def test_files_flag_and_env(self):
        # the flag lowers or raises the default; kept small so the snap stays inside T_frame.
        w = addWorld(self)
        prog = self.many(w, 20)
        r = w.bench("run", "--hold-files", "21", w.script(f"EXEC {prog}\n"), timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("hold_files_quota=21\n", (w.session() / "SESSION").read_text())
        w1 = addWorld(self)
        r = w1.bench("run", "--hold-files", "5", w1.script(f"EXEC {self.many(w1, 20)}\n"), timeout=30)
        self.assertIn("hold-quota-files", r.stdout)
        w2 = addWorld(self)
        w2.env["BENCH_HOLD_FILES"] = "0"
        r = w2.bench("run", w2.script("WRITE fs hold/a.txt x\n"))
        self.assertIn("hold-quota-files", r.stdout)
        w2.env["BENCH_HOLD_FILES"] = "many"
        self.assertEqual(w2.bench("run", w2.script("WAIT 1\n")).returncode, 2)
        self.assertEqual(w2.bench("run", "--hold-files", "-1", w2.script("WAIT 1\n")).returncode, 2)

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
