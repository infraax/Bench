# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ring 0 is dead code.

3.0 may midwife a test. 1.0 crowns. this file is the midwife's metal detector:
if the draft phones a ghost, it is not ROM.

the whole check is a walk of the syntax tree. no regex religion.
each node returns a local "dirty" bit. we OR them on the way up.
that is the backward of purity — same shape as micrograd, different object.

honesty (Karpathy): this is the metal detector, NOT the cage.
    is_ring0_source (here)  = an AST fold. stops an *accidental* `import openai`
                              or `os.posix_spawn` in a test file. teaching + midwife.
    is_sealed_exec (not here) = the OS. seccomp + landlock + a rom-image hash, in the
                              C supervisor. that is the cage. see supervisor/sandbox.c
                              and supervisor/rom_hash.h.
A source-level banlist cannot bind a model that can write bytecode, reach through
getattr on a built string, or ship a .pyc. Do not let this function impersonate the
cage. The intern's real leash is that it never holds a general-purpose interpreter
with your UID (Law 1: no ambient authority). This fold is the courtesy layer above it.
"""
from __future__ import annotations
import ast
from pathlib import Path

# names that mean "we left the snapshot". add here, don't invent a parser per vendor.
# expanded past the antenna to the ambient-authority doors a model reaches for:
# process spawning, native code, dynamic import, bytecode, a second interpreter.
DIRTY_MODS = {
    # antenna
    "openai", "anthropic", "httpx", "requests", "urllib", "socket",
    "aiohttp", "http", "ssl", "websockets", "grpc", "smtplib", "ftplib", "telnetlib",
    "asyncio", "socketserver", "xmlrpc", "poplib", "imaplib", "nntplib", "webbrowser",
    # the builtins module is eval/exec/__import__ by another name
    "builtins",
    # ambient authority: spawn, native, dynamic, bytecode, second interpreter
    "subprocess", "multiprocessing", "ctypes", "cffi", "pty", "pexpect",
    "importlib", "imp", "runpy", "marshal", "code", "codeop", "pickle", "shelve",
    "mmap", "resource", "signal",
}
# attribute names that mean the same, reached through a module object (os.posix_spawn, ...).
DIRTY_ATTR = {
    # antenna / clients
    "urlopen", "OpenAI", "Anthropic", "Client", "chat", "completions",
    # os.* ambient authority
    "system", "popen", "fork", "forkpty",
    "exec", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawn", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp",
    # native / dynamic doors
    "CDLL", "cdll", "WinDLL", "PyDLL", "LoadLibrary", "dlopen",
    "import_module", "loads", "load_module", "interact",
}
# bare call names that are their own door regardless of module.
DIRTY_CALL = {"eval", "exec", "compile", "__import__", "breakpoint", "globals", "vars"}
# escape-chain dunders. NOT all dunders — __slots__/__dict__/__new__/__class__ are ordinary
# introspection the ROM tests themselves use. these are the ones that walk out of the object graph.
DIRTY_DUNDER = {
    "__globals__", "__builtins__", "__code__", "__subclasses__", "__bases__", "__mro__",
    "__loader__", "__spec__", "__reduce__", "__reduce_ex__", "__getattribute__", "__import__",
}

def _dirty_node(n: ast.AST) -> bool:
    if isinstance(n, ast.Import):
        return any(a.name.split(".")[0] in DIRTY_MODS for a in n.names)
    if isinstance(n, ast.ImportFrom):
        # `from os import system` reaches the same door as `os.system`: judge the names too
        if n.module and n.module.split(".")[0] in DIRTY_MODS:
            return True
        return any(a.name in DIRTY_ATTR or a.name in DIRTY_CALL for a in n.names)
    if isinstance(n, ast.Attribute) and n.attr in DIRTY_ATTR:
        return True
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DIRTY_CALL:
        return True
    # getattr(x, "system") / __import__("socket") smuggle the name as a string literal.
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr":
        for a in n.args[1:2]:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value in (DIRTY_ATTR | DIRTY_CALL):
                return True
    # escape-chain dunder reach: ().__class__.__bases__, x.__globals__, obj.__builtins__.
    if isinstance(n, ast.Attribute) and n.attr in DIRTY_DUNDER:
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

# explicit name so callers cannot mistake the metal detector for the cage.
# is_sealed_exec is the C supervisor's job (seccomp/landlock/rom-hash), not python's.
is_ring0_source = is_ring0

def _in_proposed(p: Path) -> bool:
    # a draft lives under some proposed/ dir, and never climbs back out of it.
    return "proposed" in p.parts[:-1] and ".." not in p.parts

def midwife(draft: str, dest: Path) -> Path:
    """intern writes proposed/, and only there. this function does not INSTALL_ROM."""
    dest = Path(dest)
    if not _in_proposed(dest):
        raise RuntimeError(f"midwife writes under proposed/ only, not {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(draft)
    return dest

def install_rom(draft: Path, rom_dir: Path) -> Path:
    """proposed/test_*.py -> rom_dir, if clean and new. replacing a ROM file is not an install."""
    draft = Path(draft)
    if not _in_proposed(draft):
        raise RuntimeError(f"install takes a draft from proposed/, not {draft}")
    if not (draft.name.startswith("test_") and draft.suffix == ".py"):
        raise RuntimeError(f"ROM holds test_*.py only (the runner loads nothing else): {draft.name}")
    src = draft.read_text()
    if not is_ring0(src):
        raise RuntimeError("wall: draft calls a ghost — stay in proposed/")
    out = Path(rom_dir) / draft.name
    if out.exists():
        raise RuntimeError(f"{out.name} is already ROM; replacing it is a human edit, not an install")
    out.write_text(src)
    return out

def leash(n_bytes: int, cap: int) -> bool:
    """stop emit when the human cannot check. True = still legal."""
    return n_bytes <= cap

# column 1: predicate   column 2: midwife   column 3: leash
# that is the whole Ring-0 story.
