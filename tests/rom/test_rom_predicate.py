"""Ring 0: the metal detector. a draft that phones a ghost is not ROM."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.karpathy_rom import install_rom, is_ring0, leash, midwife  # noqa: E402

PURE = "def add(a, b):\n    return a + b\n\nassert add(2, 2) == 4\n"

DIRTY = [
    "import openai\n",
    "import socket\n",
    "import urllib.request\n",
    "from urllib.request import urlopen\n",
    "from anthropic import Anthropic\n",
    "import subprocess\n",
    "import http.client\n",
    "x = eval('1 + 1')\n",
    "m = __import__('socket')\n",
    "def f(c):\n    return c.chat.completions.create()\n",
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

    def test_leash(self):
        self.assertTrue(leash(10, 10))
        self.assertFalse(leash(11, 10))


if __name__ == "__main__":
    unittest.main()
