"""Ring 0: the term algebra. illegal terms die at birth."""
import dataclasses
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
        self.assertIsNone(hook(Step(Op.WRITE, "fb", "x", None, Ring.WORK), frozenset({"fs"}), radio=False))

    def test_hook_exec_slot_is_the_program(self):
        # EXEC's slot is the program path, not a slot name. it needs fs, where tools live.
        s = Step(Op.EXEC, "tools/hash.py", "hold/x", None, Ring.WORK)
        self.assertIs(hook(s, frozenset({"fs"}), radio=False), s)
        self.assertIsNone(hook(s, frozenset({"tty"}), radio=False))

    def test_hook_judge_needs_judge_and_radio(self):
        s = Step(Op.TEST, "fs", "tests/rom/t.py", Kind.JUDGE, Ring.HOLD)
        self.assertIsNone(hook(s, frozenset({"fs"}), radio=True))
        self.assertIs(hook(s, frozenset({"fs", "judge"}), radio=True), s)

    def test_hook_visual_needs_fb(self):
        s = Step(Op.TEST, "fs", "tests/rom/t.py", Kind.VISUAL, Ring.WORK)
        self.assertIsNone(hook(s, frozenset({"fs"}), radio=False))
        self.assertIs(hook(s, frozenset({"fs", "fb"}), radio=False), s)

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

    # --- Hotz's throws: the term is only what the key says ---

    def test_step_is_slotted_no_surprise_fields(self):
        # slots is the constructor law. step.planner = "..." must not be legal python.
        self.assertTrue(hasattr(Step, "__slots__"))
        s = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        self.assertFalse(hasattr(s, "__dict__"))  # the instance carries no surprise bag
        with self.assertRaises(AttributeError):
            s.extra = 1            # the sixth field, taped on at runtime
        with self.assertRaises(AttributeError):
            s.planner = "gpt"

    def test_slotted_and_still_weakrefable(self):
        # tinygrad's UOp is interned AND slotted. proving both here.
        self.assertIn("__weakref__", Step.__slots__)
        a = Step(Op.EXEC, "tools/x.py", "", None, Ring.WORK)
        b = Step(Op.EXEC, "tools/x.py", "", None, Ring.WORK)
        self.assertIs(a, b)

    def test_replace_cannot_forge_a_term(self):
        # the interner key is positional-only, so replace()'s kwargs path can't build a Step.
        # there is one door: the positional constructor. no keyword bypass around post_init.
        s = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        with self.assertRaises(TypeError):
            dataclasses.replace(s, arg="main/y")

    def test_object_new_yields_an_unusable_shell_not_a_term(self):
        # object.__new__ skips __init__/__post_init__, but a slotted shell has no fields set
        # and is never entered in the intern cache — it cannot masquerade as a legal term.
        shell = object.__new__(Step)
        with self.assertRaises(AttributeError):
            _ = shell.op
        real = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        self.assertIsNot(shell, real)

    def test_kind_none_is_part_of_the_key(self):
        # kind=None vs a real kind are different coordinates; neither collides.
        none = Step(Op.WAIT, "", "1", None, Ring.WORK)
        pure = Step(Op.WAIT, "", "1", Kind.PURE, Ring.WORK)
        self.assertIsNot(none, pure)
        self.assertIs(none, Step(Op.WAIT, "", "1", None, Ring.WORK))

    # --- the interned term is shared, so it is frozen and typed at birth ---

    def test_interned_term_is_not_field_writable(self):
        s = Step(Op.WAIT, "", "1", None, Ring.WORK)
        for field, value in (("op", Op.WRITE), ("slot", "fb"), ("arg", "2"),
                             ("kind", Kind.PURE), ("ring", Ring.HOLD)):
            with self.subTest(field=field):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(s, field, value)
        # the shared term is unchanged for every other holder of the key
        again = Step(Op.WAIT, "", "1", None, Ring.WORK)
        self.assertIs(again, s)
        self.assertEqual((again.op, again.arg, again.ring), (Op.WAIT, "1", Ring.WORK))

    def test_cannot_delete_a_field(self):
        s = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            del s.op

    def test_raw_ints_are_not_terms(self):
        # IntEnum compares equal to int. without a type check, ring=0 would dodge the ROM wall
        # and Step(1, ...) would share an intern key with Step(Op.READ, ...).
        with self.assertRaises(TypeError):
            Step(Op.READ, "fs", "main/x", None, 0)
        with self.assertRaises(TypeError):
            Step(1, "fs", "main/x", None, Ring.WORK)
        with self.assertRaises(TypeError):
            Step(Op.TEST, "fs", "t", 1, Ring.WORK)
        with self.assertRaises(TypeError):
            Step(Op.READ, b"fs", "main/x", None, Ring.WORK)

    def test_str_subclass_is_not_a_field(self):
        # a subclass can carry a mutable __dict__; the term would no longer be frozen.
        class Sticky(str):
            pass
        tag = Sticky("main/x")
        tag.note = "mutable"
        with self.assertRaises(TypeError):
            Step(Op.READ, "fs", tag, None, Ring.WORK)

    def test_op_is_closed(self):
        # no sixth op by subclassing, by value, or by name.
        with self.assertRaises(TypeError):
            class Op6(Op):
                BROWSE = 10
        with self.assertRaises(ValueError):
            Op(10)
        with self.assertRaises(KeyError):
            Op["BROWSE"]

    def test_wrong_arity_is_not_a_term(self):
        with self.assertRaises(TypeError):
            Step(Op.READ, "fs", "main/x", None)
        with self.assertRaises(TypeError):
            Step(Op.READ, "fs", "main/x", None, Ring.WORK, "planner")

    def test_intern_cache_holds_weak_references(self):
        # the cache is an interner, not an owner: a term nobody holds leaves the table.
        cache = type(Step)._c
        key = (Op.READ, "fs", "main/weak-probe", None, Ring.WORK)
        s = Step(*key)
        self.assertIs(cache.get(key), s)
        del s
        self.assertIsNone(cache.get(key))

    def test_hook_never_emits_a_non_actuator(self):
        # deny is None; a pass-through actuator stays an actuator. no new ontology in the rewrite.
        for op in ACTUATORS:
            s = Step(op, "fs", "main/x", Kind.PURE if op is Op.TEST else None, Ring.WORK)
            out = hook(s, frozenset({"fs"}), radio=False)
            if out is not None:
                self.assertIn(out.op, ACTUATORS)


if __name__ == "__main__":
    unittest.main()
