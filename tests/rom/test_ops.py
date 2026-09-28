# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ring 0: the opcode truth table. ROM owns the rows; the harness runs each through the C parser.

row = (script line, expected). expected is "ok" (the op runs, exit 0) or a phrase the refusal
must contain. ROM checks the table against the ISA; tests/harness checks it against the binary.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.hotz_isa import ACTUATORS, SUPER, Op, intern_may_write  # noqa: E402

OPS_TABLE = [
    # the five, as written by a well-behaved intern
    ("READ  fs main/hello.txt", "ok"),
    ("read fs main/hello.txt", "ok"),                        # verbs are case-blind
    ("WRITE fs hold/out.txt hello", "ok"),
    ("WRITE fs proposed/tests/test_x.py x", "ok"),
    ("EXEC  tools/hash.py main/hello.txt", "ok"),
    ("TEST  PURE tests/rom/test_isa.py", "ok"),
    ("WAIT  1", "ok"),
    ("# a comment is a comment track", "ok"),
    # shape
    ("READ fs", "needs <slot> <path>"),
    ("READ fs main/hello.txt extra", "no payload"),
    ("WAIT", "needs <ms>"),
    ("WAIT -1", "not a number"),
    ("WAIT 1s", "not a number"),
    ("WAIT 3600001", "not a number"),
    ("WAIT 6000", "T_tool"),                                  # parses; over the tool clock at run
    ("TEST tests/rom/test_isa.py", "without kind"),
    ("TEST PURE", "needs <kind> <path>"),
    ("TEST PURE tests/rom/test_isa.py more", "<kind> <path> only"),
    # where things may live
    ("WRITE fs main/owned.txt x", "ring"),
    ("WRITE fs tests/rom/test_x.py x", "ring"),
    ("WRITE fs sessions/OWNER_TOKEN x", "ring"),
    ("WRITE fs ../escape x", "escapes"),
    ("WRITE fs /etc/x x", "escapes"),
    ("READ fs ../x", "escapes"),
    ("EXEC tools/x.sh", "tools/*.py only"),
    ("EXEC main/x.py", "tools/*.py only"),
    ("EXEC tools/../supervisor/x.py", "tools/*.py only"),
    ("EXEC tools/hash.py ../x", "arg escapes"),
    ("TEST PURE tests/proposed/test_x.py", "tests/rom/*.py only"),
    ("TEST PURE tests/rom/../x.py", "tests/rom/*.py only"),
    # slots that are pulled in foundation
    ("READ fb main/hello.txt", "unplugged"),
    ("READ radio main/hello.txt", "unplugged"),
    ("READ disk main/hello.txt", "unknown"),
    ("TEST JUDGE tests/rom/test_isa.py", "unplugged"),
    ("TEST VISUAL tests/rom/test_isa.py", "unplugged"),
    # no sixth verb, no supervisor word, no mailbox word
    ("BROWSE http://x", "unknown verb"),
    ("CLICK 10 10", "unknown verb"),
    ("PING", "unknown verb"),
    ("ARM_OK", "unknown verb"),
    ("FRAME_OK 1", "unknown verb"),
    ("INSTALL_ROM tests/proposed/t.py", "supervisor"),
    ("SET_LOOP 99", "supervisor"),
    ("KILL", "supervisor"),
    ("UNPLUG radio", "supervisor"),
    ("unplug radio", "supervisor"),
]

PARSE_REFUSALS = {"unknown verb", "supervisor"}


def verb(line):
    word = line.split()[0]
    return None if word.startswith("#") else word.upper()


class TestOpsTable(unittest.TestCase):
    def test_rows_are_unique(self):
        lines = [line for line, _ in OPS_TABLE]
        self.assertEqual(len(lines), len(set(lines)))

    def test_verb_class_matches_the_isa(self):
        names = {o.name for o in Op}
        for line, expect in OPS_TABLE:
            with self.subTest(line=line):
                v = verb(line)
                if v is None:
                    self.assertEqual(expect, "ok")
                elif v not in names:
                    self.assertEqual(expect, "unknown verb")
                elif Op[v] in SUPER:
                    self.assertEqual(expect, "supervisor")
                else:
                    self.assertIn(Op[v], ACTUATORS)
                    self.assertNotIn(expect, PARSE_REFUSALS)

    def test_write_rows_agree_with_the_write_rule(self):
        for line, expect in OPS_TABLE:
            parts = line.split()
            if verb(line) == "WRITE" and len(parts) >= 3 and parts[1] == "fs":
                with self.subTest(line=line):
                    self.assertEqual(expect == "ok", intern_may_write(parts[2]))

    def test_every_actuator_has_a_green_row(self):
        green = {verb(line) for line, expect in OPS_TABLE if expect == "ok" and verb(line)}
        self.assertEqual(green, {o.name for o in ACTUATORS})


if __name__ == "__main__":
    unittest.main()
