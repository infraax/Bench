"""Ring 0 is dead code.

3.0 may midwife a test. 1.0 crowns. this file is the midwife's metal detector:
if the draft phones a ghost, it is not ROM.

the whole check is a walk of the syntax tree. no regex religion.
each node returns a local "dirty" bit. we OR them on the way up.
that is the backward of purity — same shape as micrograd, different object.
"""
from __future__ import annotations
import ast
from pathlib import Path

# names that mean "we left the snapshot". add here, don't invent a parser per vendor.
DIRTY_MODS = {
    "openai", "anthropic", "httpx", "requests", "urllib", "socket",
    "aiohttp", "http", "ssl", "subprocess", "pickle", "ctypes",
}
DIRTY_ATTR = {"urlopen", "OpenAI", "Client", "chat", "completions"}

def _dirty_node(n: ast.AST) -> bool:
    if isinstance(n, ast.Import):
        return any(a.name.split(".")[0] in DIRTY_MODS for a in n.names)
    if isinstance(n, ast.ImportFrom) and n.module:
        return n.module.split(".")[0] in DIRTY_MODS
    if isinstance(n, ast.Attribute) and n.attr in DIRTY_ATTR:
        return True
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"eval", "exec", "__import__"}:
        return True
    return False

def is_ring0(src: str) -> bool:
    """True iff this source may sit in tests/rom/.
    no model, no radio, no eval door. deterministic is the caller's problem
    after this — we only refuse the antenna."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    # local dirty on each node, reduce OR — intern this idea, don't decorate it
    return not any(_dirty_node(n) for n in ast.walk(tree))

def midwife(draft: str, dest: Path) -> Path:
    """intern writes proposed/. this function does not INSTALL_ROM."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(draft)
    return dest

def install_rom(draft: Path, rom_dir: Path) -> Path:
    src = draft.read_text()
    if not is_ring0(src):
        raise RuntimeError("wall: draft calls a ghost — stay in proposed/")
    out = Path(rom_dir) / draft.name
    out.write_text(src)
    return out

def leash(n_bytes: int, cap: int) -> bool:
    """stop emit when the human cannot check. True = still legal."""
    return n_bytes <= cap

# column 1: predicate   column 2: midwife   column 3: leash
# that is the whole Ring-0 story.
