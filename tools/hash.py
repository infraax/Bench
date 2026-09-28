# SPDX-License-Identifier: MIT OR Apache-2.0
"""tree hash. sha256 over (relpath, length, bytes), sorted. same tree, same hex.

no clock, no radio. reached only via exec.
"""
import hashlib
import os
import stat
import sys
from pathlib import Path


def _skip(name):
    # bytecode is derived, not board state (matches sha256.c walk: any entry, file or dir)
    return name == b"__pycache__" or name.endswith(b".pyc")


def _walk(abs_dir, rel, out, skip_derived=True):
    """regular files under abs_dir as (relpath bytes, abs path); symlinks are not board state.
    hold/ skips nothing: the intern writes it, so nothing in it is derived (sha256.c walk)."""
    with os.scandir(abs_dir) as it:
        for e in it:
            name = os.fsencode(e.name)
            if skip_derived and _skip(name):
                continue
            r = rel + b"/" + name
            if e.is_symlink():
                continue
            if e.is_file(follow_symlinks=False):
                out.append((r, e.path))
            elif e.is_dir(follow_symlinks=False):
                _walk(e.path, r, out, skip_derived)


def tree_hash(paths, base=Path(".")):
    """the same bytes as supervisor/sha256.c tree_hash: per top path, a missing marker, one
    regular file, or every regular file below it sorted by relpath bytes (strcmp order)."""
    h = hashlib.sha256()
    for p in paths:
        top = os.path.join(os.fsencode(base), os.fsencode(p))
        rel = os.fsencode(p)
        try:
            st = os.lstat(top)
        except FileNotFoundError:
            h.update(b"missing\0" + rel + b"\0")
            continue
        if stat.S_ISREG(st.st_mode):
            files = [(rel, top)]
        elif stat.S_ISDIR(st.st_mode):
            files = []
            _walk(top, rel, files, not (rel == b"hold" or rel.startswith(b"hold/")))
            files.sort(key=lambda x: x[0])
        else:
            continue                                  # a symlink or device at the top is skipped
        for r, a in files:
            with open(a, "rb") as f:
                data = f.read()
            h.update(r + b"\0")
            h.update(str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


if __name__ == "__main__":
    print(tree_hash(sys.argv[1:] or ["main", "hold"]))
