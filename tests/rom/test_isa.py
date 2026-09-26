"""Ring 0: the term algebra. illegal terms die at birth."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.hotz_isa import ACTUATORS, SUPER, Kind, Op, Ring, Step, hook, intern_ok  # noqa: E402


class TestISA(unittest.TestCase):
    def test_five_actuators_closed(self):
        self.assertEqual({o.name for o in ACTUATORS}, {"READ", "WRITE", "EXEC", "TEST", "WAIT"})
        self.assertEqual({o.name for o in SUPER}, {"INSTALL_ROM", "SET_LOOP", "KILL", "UNPLUG"})
        self.assertFalse(ACTUATORS & SUPER)
        self.assertEqual(set(Op), ACTUATORS | SUPER)

    def test_interned_identity(self):
        a = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        b = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        self.assertIs(a, b)
        self.assertIs(intern_ok(), a)

    def test_different_args_different_term(self):
        a = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        b = Step(Op.READ, "fs", "main/y", None, Ring.WORK)
        self.assertIsNot(a, b)

    def test_actuator_rom_raises(self):
        for op in ACTUATORS:
            with self.assertRaises(RuntimeError):
                Step(op, "fs", "x", Kind.PURE, Ring.ROM)

    def test_supervisor_outside_rom_raises(self):
        for op in SUPER:
            for ring in (Ring.HOLD, Ring.WORK):
                with self.assertRaises(RuntimeError):
                    Step(op, "fs", "x", None, ring)

    def test_test_without_kind_raises(self):
        with self.assertRaises(RuntimeError):
            Step(Op.TEST, "fs", "tests/rom/test_isa.py", None, Ring.WORK)

    def test_judge_rom_raises(self):
        # actuators already die in ROM; the judge wall must hold for supervisor ops too
        with self.assertRaises(RuntimeError):
            Step(Op.INSTALL_ROM, "fs", "tests/proposed/t.py", Kind.JUDGE, Ring.ROM)

    def test_failed_birth_is_not_cached(self):
        with self.assertRaises(RuntimeError):
            Step(Op.TEST, "fs", "t", None, Ring.WORK)
        with self.assertRaises(RuntimeError):
            Step(Op.TEST, "fs", "t", None, Ring.WORK)

    def test_hook_unplugged_slot_is_none(self):
        s = Step(Op.READ, "fb", "rect", None, Ring.WORK)
        self.assertIsNone(hook(s, frozenset({"fs"}), radio=False))
        for op in (Op.WRITE, Op.EXEC):
            self.assertIsNone(hook(Step(op, "fb", "x", None, Ring.WORK), frozenset({"fs"}), radio=False))

    def test_hook_plugged_passes_same_term(self):
        s = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        self.assertIs(hook(s, frozenset({"fs"}), radio=False), s)

    def test_hook_judge_without_radio_is_none(self):
        s = Step(Op.TEST, "judge", "score", Kind.JUDGE, Ring.HOLD)
        self.assertIsNone(hook(s, frozenset({"fs", "judge"}), radio=False))

    def test_hook_output_stays_in_isa(self):
        s = Step(Op.WAIT, "", "1", None, Ring.WORK)
        out = hook(s, frozenset({"fs"}), radio=False)
        self.assertIn(out.op, ACTUATORS)


if __name__ == "__main__":
    unittest.main()
