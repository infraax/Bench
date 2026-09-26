# the intern is slop. this file is not.
# five ops. interned terms. hooks as rewrite. if you need a sixth, you don't.

from __future__ import annotations
from enum import IntEnum, auto
from dataclasses import dataclass
import weakref

class FastEnum(IntEnum):
    def __str__(self): return self.name

class Op(FastEnum):
    READ=auto(); WRITE=auto(); EXEC=auto(); TEST=auto(); WAIT=auto()
    # supervisor-only. intern emitting these is a spec bug, not a feature.
    INSTALL_ROM=auto(); SET_LOOP=auto(); KILL=auto(); UNPLUG=auto()

ACTUATORS = frozenset({Op.READ, Op.WRITE, Op.EXEC, Op.TEST, Op.WAIT})
SUPER     = frozenset({Op.INSTALL_ROM, Op.SET_LOOP, Op.KILL, Op.UNPLUG})

class Kind(FastEnum):
    PURE=auto(); SCALAR=auto(); JUDGE=auto(); VISUAL=auto()

class Ring(FastEnum):
    ROM=0; HOLD=1; WORK=2

class UCache(type):
    _c: dict[tuple, weakref.ReferenceType] = {}
    def __call__(cls, *a):
        # NOTE: identity equality is the CSE. do not add fields that don't belong in the key.
        k = a
        w = cls._c.get(k)
        if w is not None and (o := w()) is not None: return o
        o = super().__call__(*a)
        cls._c[k] = weakref.ref(o)
        return o

# slots=True dropped: slotted dataclass has no __weakref__, and UCache needs one.
@dataclass(eq=False)
class Step(metaclass=UCache):
    op: Op
    slot: str
    arg: str
    kind: Kind | None
    ring: Ring
    def __post_init__(self):
        if self.op in ACTUATORS and self.ring is Ring.ROM:
            raise RuntimeError("actuator cannot write ROM")
        if self.op in SUPER and self.ring is not Ring.ROM:
            raise RuntimeError(f"{self.op} is supervisor")
        if self.op is Op.TEST and self.kind is None:
            raise RuntimeError("test without kind")
        if self.kind is Kind.JUDGE and self.ring is Ring.ROM:
            raise RuntimeError("dirty DMA is not ROM")  # the wall

def hook(step: Step, plugged: frozenset[str], radio: bool) -> Step | None:
    """deny is None. rewrite must stay in ACTUATORS. no new ontology here."""
    if step.slot and step.slot not in plugged and step.op in {Op.READ, Op.WRITE, Op.EXEC}:
        return None
    if step.kind is Kind.JUDGE and not radio: return None
    if step.op in SUPER: return step  # supervisor path, already gated by Ring
    return step

def intern_ok() -> Step:
    # same args => same object. if this isn't True your metaclass is theater.
    a = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
    b = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
    assert a is b
    return a
