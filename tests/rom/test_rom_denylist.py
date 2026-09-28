# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ring 0: the denylists, pinned member by member.

mutation testing (tests/deep/mutate.py) showed 83 of the predicate's names could be dropped with
no test noticing: DIRTY rows covered a sample. here every member is written out by hand — not
read back from the module, which would test nothing — and each one is proved to refuse in
every form it can be reached by: import, from-import, attribute, call, bare name.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.karpathy_rom import DIRTY_ATTR, DIRTY_CALL, DIRTY_DUNDER, DIRTY_MODS, is_ring0  # noqa: E402

MODS = {
    "openai", "anthropic", "httpx", "requests", "urllib", "socket",
    "aiohttp", "http", "ssl", "websockets", "grpc", "smtplib", "ftplib", "telnetlib",
    "asyncio", "socketserver", "xmlrpc", "poplib", "imaplib", "nntplib", "webbrowser",
    "builtins",
    "subprocess", "multiprocessing", "ctypes", "cffi", "pty", "pexpect",
    "importlib", "imp", "runpy", "marshal", "code", "codeop", "pickle", "shelve",
    "mmap", "resource", "signal",
}
ATTRS = {
    "urlopen", "OpenAI", "Anthropic", "Client", "chat", "completions",
    "system", "popen", "fork", "forkpty",
    "exec", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawn", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp",
    "CDLL", "cdll", "WinDLL", "PyDLL", "LoadLibrary", "dlopen",
    "import_module", "loads", "load_module", "interact",
}
CALLS = {"eval", "exec", "compile", "__import__", "breakpoint", "globals", "vars"}
DUNDERS = {
    "__globals__", "__builtins__", "__code__", "__subclasses__", "__bases__", "__mro__",
    "__loader__", "__spec__", "__reduce__", "__reduce_ex__", "__getattribute__", "__import__",
}


class TestDenylistMembers(unittest.TestCase):
    def test_the_lists_are_exactly_these(self):
        # a name removed from the module fails here; a name added must be added here too
        self.assertEqual(set(DIRTY_MODS), MODS)
        self.assertEqual(set(DIRTY_ATTR), ATTRS)
        self.assertEqual(set(DIRTY_CALL), CALLS)
        self.assertEqual(set(DIRTY_DUNDER), DUNDERS)

    def test_every_module_refuses_by_import_and_from_import(self):
        for m in sorted(MODS):
            with self.subTest(module=m):
                self.assertFalse(is_ring0(f"import {m}\n"))
                self.assertFalse(is_ring0(f"import {m}.sub as x\n"))
                self.assertFalse(is_ring0(f"from {m} import thing\n"))

    def test_every_attribute_refuses_through_a_module_and_by_from_import(self):
        for a in sorted(ATTRS):
            with self.subTest(attr=a):
                self.assertFalse(is_ring0(f"def f(o):\n    return o.{a}\n"))
                self.assertFalse(is_ring0(f"from os import {a}\n"))
                self.assertFalse(is_ring0(f"def f(o):\n    return getattr(o, '{a}')\n"))

    def test_every_call_refuses_called_named_and_imported(self):
        for c in sorted(CALLS):
            with self.subTest(call=c):
                self.assertFalse(is_ring0(f"{c}('1')\n"))
                self.assertFalse(is_ring0(f"f = {c}\n"))
                self.assertFalse(is_ring0(f"from os import {c}\n"))

    def test_every_dunder_refuses_as_attribute_and_name(self):
        for d in sorted(DUNDERS):
            with self.subTest(dunder=d):
                self.assertFalse(is_ring0(f"def f(o):\n    return o.{d}\n"))
                self.assertFalse(is_ring0(f"x = {d}\n"))

    def test_near_misses_stay_clean(self):
        # the list is exact, not a prefix or substring match: ordinary names must pass
        for src in ("import os\n", "import json\n", "from os import path\n", "x = evaluate(1)\n",
                    "def f(o):\n    return o.__class__, o.__dict__, o.__slots__\n", "systems = 1\n",
                    "import codecs\n", "import signals_x\n"):
            with self.subTest(src=src):
                self.assertTrue(is_ring0(src))


if __name__ == "__main__":
    unittest.main()
