"""Ring 0: the refusal truth table. Every rejection bench emits names a rule; every rule has a fix.

RULES mirrors supervisor/refusal.c (the harness compares it with `bench rules`).
OPS_RULES names the rule each refusal row of OPS_TABLE must print; the harness runs them.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ops import OPS_TABLE  # noqa: E402

RULES = {
    # parse: the line dies at birth, before any frame
    "line-long": "keep each line under 512 bytes",
    "script-long": "split the script: at most 64 ops per run",
    "verb-super": "that word is the owner's; use one of READ WRITE EXEC TEST WAIT",
    "verb-unknown": "use one of the five verbs: READ WRITE EXEC TEST WAIT",
    "shape-rw": "write READ fs <path> or WRITE fs <path> <one line>",
    "field-long": "shorten it: slot under 128 bytes, path and payload under 256",
    "path-escape": "use a relative path inside the world: no leading / and no ..",
    "read-payload": "READ takes <slot> <path> only; drop the words after the path",
    "write-ring": "write under hold/ or proposed/; main/ is Ring 0",
    "exec-shape": "write EXEC tools/<name>.py <args>",
    "exec-prog": "EXEC runs tools/*.py only; copy a draft to proposed/ and ask the owner to crown it",
    "exec-arg": "each EXEC arg is a relative path or word inside the world: no leading / and no ..",
    "exec-argc": "pass at most 16 args; name a file holding the rest",
    "test-kind": "write TEST PURE <tests/rom/test_x.py> (kinds: PURE SCALAR)",
    "test-shape": "write TEST <kind> <tests/rom/test_x.py> and nothing after it",
    "test-path": "TEST runs crowned tests/rom/*.py only; draft under tests/proposed/ for the owner",
    "wait-shape": "write WAIT <ms>, a whole number of milliseconds up to T_tool",
    # run: the op was framed and refused, snapped with rule= in its evidence
    "slot-unknown": "use slot fs (slots: fs tty fb judge radio)",
    "slot-pulled": "that slot is pulled in foundation; use fs",
    "judge-pulled": "JUDGE needs the judge card and radio, both pulled; use TEST PURE or SCALAR",
    "visual-pulled": "VISUAL needs the fb card, pulled; use TEST PURE or SCALAR",
    "fs-path": "name an existing regular file; no component may be a symlink",
    "fs-cap": "keep a READ or WRITE within the fs cap (4096 bytes); split the file",
    "tty-cap": "print at most 4096 bytes; bound the tool's output",
    "out-ceil": "the tool printed past 1 MiB and was killed; bound its output",
    "t-tool": "finish within T_tool (5000 ms); split the work across steps",
    "hold-bytes": "hold/ grew past its byte quota this session; write less or ask the owner for --hold-quota",
    "hold-files": "hold/ grew past its entry quota this session; write fewer files or ask for --hold-files",
    "test-moved": "a TEST may change only hold/, proposed/ and /tmp; the owner must re-arm",
    "t-frame": "the step's own bookkeeping ran past T_frame; write fewer new files per step",
    "t-session": "the session ran past T_session; use fewer or shorter steps",
    "over-n": "the run is over N steps; ask the owner for --n or split the script",
    "internal": "not the intern's to fix; the owner reads sessions/<id>/log",
    # gate: the op never ran, no snap
    "kill": "the owner stopped the run; nothing to fix from the intern side",
    "disarmed": "the owner's token is gone or changed; only the owner can re-arm",
    "helper-lost": "bench-helper stopped answering; the owner restarts the run",
}

OPS_RULES = {
    "READ fs": "shape-rw",
    "READ fs main/hello.txt extra": "read-payload",
    "WAIT": "wait-shape",
    "WAIT -1": "wait-shape",
    "WAIT 1s": "wait-shape",
    "WAIT 3600001": "wait-shape",
    "WAIT 6000": "t-tool",
    "TEST tests/rom/test_isa.py": "test-kind",
    "TEST PURE": "test-shape",
    "TEST PURE tests/rom/test_isa.py more": "test-shape",
    "WRITE fs main/owned.txt x": "write-ring",
    "WRITE fs tests/rom/test_x.py x": "write-ring",
    "WRITE fs sessions/OWNER_TOKEN x": "write-ring",
    "WRITE fs ../escape x": "path-escape",
    "WRITE fs /etc/x x": "path-escape",
    "READ fs ../x": "path-escape",
    "EXEC tools/x.sh": "exec-prog",
    "EXEC main/x.py": "exec-prog",
    "EXEC tools/../supervisor/x.py": "exec-prog",
    "EXEC tools/hash.py ../x": "exec-arg",
    "TEST PURE tests/proposed/test_x.py": "test-path",
    "TEST PURE tests/rom/../x.py": "test-path",
    "READ fb main/hello.txt": "slot-pulled",
    "READ radio main/hello.txt": "slot-pulled",
    "READ disk main/hello.txt": "slot-unknown",
    "TEST JUDGE tests/rom/test_isa.py": "judge-pulled",
    "TEST VISUAL tests/rom/test_isa.py": "visual-pulled",
    "BROWSE http://x": "verb-unknown",
    "CLICK 10 10": "verb-unknown",
    "PING": "verb-unknown",
    "ARM_OK": "verb-unknown",
    "FRAME_OK 1": "verb-unknown",
    "INSTALL_ROM tests/proposed/t.py": "verb-super",
    "SET_LOOP 99": "verb-super",
    "KILL": "verb-super",
    "UNPLUG radio": "verb-super",
    "unplug radio": "verb-super",
}

ID = re.compile(r"[a-z][a-z0-9-]*\Z")


class TestRefusalTable(unittest.TestCase):
    def test_ids_are_stable_words(self):
        for rid in RULES:
            with self.subTest(rule=rid):
                self.assertRegex(rid, ID)
                self.assertLess(len(rid), 32)

    def test_every_fix_is_one_short_line(self):
        for rid, fix in RULES.items():
            with self.subTest(rule=rid):
                self.assertTrue(fix.strip())
                self.assertNotIn("\n", fix)
                self.assertLessEqual(len(fix), 100)

    def test_every_refusal_row_names_a_rule(self):
        refused = {line for line, expect in OPS_TABLE if expect != "ok"}
        self.assertEqual(refused, set(OPS_RULES))

    def test_every_named_rule_exists(self):
        for line, rid in OPS_RULES.items():
            with self.subTest(line=line):
                self.assertIn(rid, RULES)

    def test_parse_class_matches_the_ops_table(self):
        expect = dict(OPS_TABLE)
        for line, rid in OPS_RULES.items():
            with self.subTest(line=line):
                if expect[line] == "unknown verb":
                    self.assertEqual(rid, "verb-unknown")
                if expect[line] == "supervisor":
                    self.assertEqual(rid, "verb-super")


if __name__ == "__main__":
    unittest.main()
