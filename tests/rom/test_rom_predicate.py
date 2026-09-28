# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ring 0: the metal detector. a draft that phones a ghost is not ROM."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.hotz_isa import OWNER_TOKEN  # noqa: E402
from isa.karpathy_rom import install_rom, is_ring0, leash, midwife  # noqa: E402

PURE = "def add(a, b):\n    return a + b\n\nassert add(2, 2) == 4\n"

DIRTY = [
    # antenna
    "import openai\n",
    "import socket\n",
    "import urllib.request\n",
    "from urllib.request import urlopen\n",
    "from anthropic import Anthropic\n",
    "import http.client\n",
    "import asyncio\n",
    "import socketserver\n",
    "from xmlrpc.client import ServerProxy\n",
    "import imaplib\n",
    "import webbrowser\n",
    "def f(c):\n    return c.chat.completions.create()\n",
    # spawn / ambient authority — the posix_spawn hole Claude walked through last time
    "import subprocess\n",
    "import os\nos.posix_spawnp('x', ['x'], {})\n",
    "import os\nos.system('id')\n",
    "import os\nos.execv('/bin/sh', ['sh'])\n",
    "import os\nos.fork()\n",
    "import multiprocessing\n",
    # native / dynamic / bytecode / second interpreter
    "import ctypes\nctypes.CDLL(None).system(b'id')\n",
    "import importlib\nimportlib.import_module('socket')\n",
    "import marshal\n",
    "import code\ncode.interact()\n",
    "import pty\n",
    # the same doors by from-import or through builtins (found by the 2026-09-28 audit)
    "from os import system\nsystem('id')\n",
    "from os import popen as p\np('id')\n",
    "from os import posix_spawn\n",
    "from builtins import eval as e\ne('1')\n",
    "import builtins\nbuiltins.eval('1')\n",
    # string-smuggled names and escape-chain dunders
    "x = eval('1 + 1')\n",
    "m = __import__('socket')\n",
    "import os\ng = getattr(os, 'system')\n",
    "leak = ().__class__.__bases__[0].__subclasses__()\n",
    "f = (lambda: 0)\nb = f.__globals__['__builtins__']\n",
    # a door named, not called (found by tests/deep/mutate.py, 2026-09-28)
    "f = eval\nf('1')\n",
    "x = [exec][0]\n",
    "b = __builtins__['eval']\n",
    "g = globals\n",
    "i = __import__\n",
]


class TestPredicate(unittest.TestCase):
    def test_pure_is_ring0(self):
        self.assertTrue(is_ring0(PURE))
        self.assertTrue(is_ring0(""))

    def test_dirty_is_not_ring0(self):
        for src in DIRTY:
            with self.subTest(src=src):
                self.assertFalse(is_ring0(src))

    def test_syntax_error_is_not_ring0(self):
        self.assertFalse(is_ring0("def (:\n"))

    def test_midwife_makes_nested_draft_dirs_and_rewrites(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "proposed" / "deep" / "er" / "test_x.py"
            midwife(PURE, dest)
            midwife(PURE, dest)          # a second draft in the same place is not an error
            self.assertEqual(dest.read_text(), PURE)

    def test_install_rom_refuses_dirty(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            draft = d / "proposed" / "test_ghost.py"
            midwife("import openai\n", draft)
            rom = d / "rom"
            rom.mkdir()
            with self.assertRaises(RuntimeError):
                install_rom(draft, rom)
            self.assertFalse((rom / "test_ghost.py").exists())

    def test_install_rom_copies_clean(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            draft = midwife(PURE, d / "proposed" / "test_add.py")
            rom = d / "rom"
            rom.mkdir()
            out = install_rom(draft, rom)
            self.assertEqual(out, rom / "test_add.py")
            self.assertEqual(out.read_text(), PURE)

    def test_midwife_does_not_install(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = midwife(PURE, d / "proposed" / "t.py")
            self.assertEqual(p.read_text(), PURE)
            self.assertEqual([x.name for x in d.iterdir()], ["proposed"])

    def test_midwife_writes_proposed_only(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for dest in (d / OWNER_TOKEN, d / "main" / "x.py", d / "tests" / "rom" / "test_x.py",
                         d / "proposed" / ".." / "main" / "x.py", d / "proposed"):
                with self.subTest(dest=dest):
                    with self.assertRaises(RuntimeError):
                        midwife(PURE, dest)
                    self.assertFalse(dest.is_file())
            self.assertFalse((d / OWNER_TOKEN).exists())

    def test_install_rom_refuses_to_replace(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rom = d / "rom"
            rom.mkdir()
            (rom / "test_add.py").write_text("# the crowned one\n")
            draft = midwife(PURE, d / "proposed" / "test_add.py")
            with self.assertRaises(RuntimeError):
                install_rom(draft, rom)
            self.assertEqual((rom / "test_add.py").read_text(), "# the crowned one\n")

    def test_install_rom_takes_test_files_from_proposed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rom = d / "rom"
            rom.mkdir()
            not_test = midwife(PURE, d / "proposed" / "helper.py")
            loose = d / "main" / "test_loose.py"
            loose.parent.mkdir()
            loose.write_text(PURE)
            for draft in (not_test, loose):
                with self.subTest(draft=draft.name):
                    with self.assertRaises(RuntimeError):
                        install_rom(draft, rom)
            self.assertEqual(list(rom.iterdir()), [])

    def test_leash(self):
        self.assertTrue(leash(10, 10))
        self.assertFalse(leash(11, 10))

    def test_the_rom_image_passes_its_own_predicate(self):
        # every file that sits in tests/rom/ must survive the expanded fold — including
        # the ones that use __slots__, __dict__, object.__new__ (ordinary introspection).
        rom = Path(__file__).resolve().parent
        files = sorted(rom.glob("*.py"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(f=f.name):
                self.assertTrue(is_ring0(f.read_text()), f"{f.name} is not ring0")

    def test_source_alias_is_the_same_detector(self):
        from isa.karpathy_rom import is_ring0_source
        self.assertIs(is_ring0_source, is_ring0)

    def test_known_blind_spot_is_documented_not_denied(self):
        # Karpathy's honesty: a source fold cannot catch a name built at runtime.
        # getattr(os, 'sys'+'tem') passes is_ring0. this is NOT a bug in the detector —
        # it is the reason the cage lives in the C supervisor (seccomp/landlock), not here.
        # if this ever starts returning False, someone tried to make the wand into the cage.
        self.assertTrue(is_ring0("import os\ng = getattr(os, 'sys' + 'tem')\n"))

    def test_ordinary_introspection_stays_clean(self):
        # slots/dict/new are not escape dunders; the detector must not panic on them.
        self.assertTrue(is_ring0("class C:\n    __slots__ = ('x', '__weakref__')\n"))
        self.assertTrue(is_ring0("s = object.__new__(int)\nd = getattr(s, '__class__')\n"))


if __name__ == "__main__":
    unittest.main()
