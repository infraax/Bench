# the intern is slop. this file is not.
# five ops. interned terms. hooks as rewrite. if you need a sixth, you don't.

from __future__ import annotations
from enum import IntEnum, auto
from dataclasses import FrozenInstanceError, dataclass
import sys
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
    # interns Step only (the type table below is Step's), so the key is the fields alone.
    # dead terms drop out of the table on their own; the cache never holds a term alive.
    _c: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
    def __call__(cls, *a):
        # NOTE: identity equality is the CSE. do not add fields that don't belong in the key.
        # type check before the lookup: Op.READ == 1 as an IntEnum, so a raw int would
        # otherwise share a key with the real term, and `ring is Ring.ROM` would miss 0.
        _typecheck(a)
        o = cls._c.get(a)
        if o is not None: return o
        o = super().__call__(*a)
        cls._c[a] = o
        return o

# exact types, not isinstance: a str subclass could carry a __dict__ into a frozen term.
_TYPES = ((Op,), (str,), (str,), (Kind, type(None)), (Ring,))

def _typecheck(a: tuple) -> None:
    if len(a) != len(_TYPES):
        raise TypeError(f"Step takes {len(_TYPES)} positional fields, got {len(a)}")
    for v, t in zip(a, _TYPES):
        if type(v) not in t:
            raise TypeError(f"Step field {v!r} is not exactly {' | '.join(x.__name__ for x in t)}")

# slots is the constructor law: no extra attributes, no sixth field taped on at runtime.
# frozen: a term is shared by every holder of the same key, so it may not change after birth.
# a slotted dataclass has no __weakref__ by default and UCache needs one, so ask for it.
# 3.11+ has weakref_slot=True; on 3.10 spell __slots__ by hand incl. "__weakref__".
if sys.version_info >= (3, 11):
    _step_dc = dataclass(eq=False, frozen=True, slots=True, weakref_slot=True)
else:
    _step_dc = dataclass(eq=False, frozen=True)

@_step_dc
class Step(metaclass=UCache):
    if sys.version_info < (3, 11):
        __slots__ = ("op", "slot", "arg", "kind", "ring", "__weakref__")
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

# frozen+slots on 3.11+ rebuilds the class, and the generated __setattr__ still names the old
# one: an unknown attribute then raises TypeError, not AttributeError. one refusal, every version.
def _no_write(self, name, value):
    raise FrozenInstanceError(f"Step is frozen: cannot assign {name!r}")

def _no_delete(self, name):
    raise FrozenInstanceError(f"Step is frozen: cannot delete {name!r}")

Step.__setattr__ = _no_write
Step.__delattr__ = _no_delete

# the intern's WRITE rule, as the C parser applies it (supervisor/main.c parse_line).
# relative, no climbing, and only quarantine or drafts. everything else is Ring 0 or the owner's.
INTERN_WRITE_ROOTS = ("hold/", "proposed/")
OWNER_TOKEN = "sessions/OWNER_TOKEN"     # the owner arms a session here; never the intern

def intern_may_write(path: str) -> bool:
    return (isinstance(path, str) and path != "" and not path.startswith("/")
            and ".." not in path and path.startswith(INTERN_WRITE_ROOTS))

def hook(step: Step, plugged: frozenset[str], radio: bool) -> Step | None:
    """deny is None; a pass is the same term. no rewrite, no new ontology here.
    the same gates as the C tools (supervisor/main.c wired / t_exec / t_test)."""
    if step.op in SUPER: return step                       # ring-gated at birth
    if step.op in (Op.READ, Op.WRITE) and step.slot not in plugged: return None
    if step.op is Op.EXEC and "fs" not in plugged: return None    # slot is the program; tools live on fs
    if step.kind is Kind.JUDGE and not ("judge" in plugged and radio): return None
    if step.kind is Kind.VISUAL and "fb" not in plugged: return None
    return step

def intern_ok() -> Step:
    # same args => same object. if this isn't True your metaclass is theater.
    a = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
    b = Step(Op.READ, "fs", "main/x", None, Ring.WORK)
    assert a is b
    return a
