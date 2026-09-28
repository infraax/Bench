# SPDX-License-Identifier: MIT OR Apache-2.0
"""tree hash. sha256 over (relpath, length, bytes), sorted. same tree, same hex.

no clock, no radio. reached only via exec.
"""
import hashlib
import sys
from pathlib import Path


def tree_hash(paths, base=Path(".")):
    h = hashlib.sha256()
    for p in paths:
        top = base / p
        if not top.exists():
            h.update(b"missing\0" + p.encode() + b"\0")
            continue
        # bytecode is derived, not board state: skip __pycache__ and .pyc (matches sha256.c)
        files = [top] if top.is_file() else sorted(
            f for f in top.rglob("*")
            if f.is_file() and not f.is_symlink()
            and "__pycache__" not in f.parts and f.suffix != ".pyc")
        for f in files:
            data = f.read_bytes()
            h.update(f.relative_to(base).as_posix().encode() + b"\0")
            h.update(str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


if __name__ == "__main__":
    print(tree_hash(sys.argv[1:] or ["main", "hold"]))
