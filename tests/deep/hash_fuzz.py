# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tree-hash fuzzer: two implementations, one meaning, checked on trees nobody would write.

The tree hash is the whole evidence story (tree=, board=, the ROM crown), and it exists twice:
supervisor/sha256.c (via supervisor/romhash) and tools/hash.py. Random hostile trees go to both
(differential), and each tree is also transformed in ways that must or must not move the hash
(metamorphic), so a bug that both implementations share is still caught:

  must NOT move   rebuilt in another creation order · mtime/mode changes · an empty dir added ·
                  a symlink or a fifo added (not board state) · under tests/rom only:
                  __pycache__/ and *.pyc added (the owner's python's by-products)
  under hold/     a *.pyc or __pycache__/ file MUST move it: hold/ is the intern's, nothing
                  in it is derived (the fuzzer found that it did not, 2026-09-28)
  MUST move       one byte flipped · one byte appended · a file renamed · an empty file added ·
                  two files' contents swapped · a file moved into a subdir

Names cover what walkers get wrong: strcmp order across directory levels ("a/b" vs "a.b" vs
"a0": '/' sorts between '.' and '0'), non-UTF-8 bytes, newline and space in names, dotfiles,
deep nesting; contents cover empty, NUL-filled and framing-lookalike bytes ("x\\0" + digits).

  python3 tests/deep/hash_fuzz.py [--trees 60] [--seed S]
exit 0: all agree and every relation holds. 1: a failure (tree kept, path printed).
"""
import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
ROMHASH = IMAGE / "supervisor" / "romhash"
sys.path.insert(0, str(IMAGE / "tools"))
from hash import tree_hash  # noqa: E402

NAMES = [b"a", b"a.b", b"a0", b"a-b", b"b", b"A", b"z", b".hidden", b"sp ace", b"new\nline", b"\xff\xfe",
         b"caf\xc3\xa9", b"x" * 100, b"__init__.py", b"t.py", b"d.pyc", b"__pycache__"]
CONTENTS = [b"", b"\0", b"\0" * 64, b"x\0" + b"12\0", b"hello\n", os.urandom(300), b"1\0a\0" * 10]


def build(root, spec, order):
    """spec: {relpath bytes: content bytes | None (dir)}; created in `order`."""
    base = os.fsencode(root)
    for rel in order:
        p = os.path.join(base, rel)
        v = spec[rel]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if v is None:
            os.makedirs(p, exist_ok=True)
        else:
            with open(p, "wb") as f:
                f.write(v)


def random_spec(rng):
    spec = {}
    for _ in range(rng.randint(1, 18)):
        depth = rng.choice([0, 0, 1, 1, 2, 4])
        parts = [rng.choice(NAMES) for _ in range(depth + 1)]
        if any(p in (b"__pycache__",) for p in parts) or parts[-1].endswith(b".pyc"):
            continue   # derived files are exercised by the metamorphic step, not the base tree
        rel = b"/".join(parts)
        # a path cannot be both a file and a dir
        if any(rel.startswith(k + b"/") or k.startswith(rel + b"/") for k in spec):
            continue
        spec[rel] = rng.choice(CONTENTS) if rng.random() < 0.9 else None
    # the strcmp-order trap, often
    if rng.random() < 0.4:
        for rel, v in ((b"a/b", b"1"), (b"a.b", b"2"), (b"a0", b"3")):
            if not any(rel.startswith(k + b"/") or k.startswith(rel + b"/") or k == rel for k in spec):
                spec[rel] = v
    return spec


TOP = "tests/rom"   # set per tree: tests/rom (derived bytecode skipped) or hold (nothing skipped)


def hashes(world):
    c = subprocess.run([str(ROMHASH), str(world), TOP], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ch = c.stdout.decode().strip() if c.returncode == 0 else f"error:{c.stderr.decode().strip()}"
    return ch, tree_hash([TOP], base=world)


def derived(rel):
    return any(p == b"__pycache__" or p.endswith(b".pyc") for p in rel.split(b"/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trees", type=int, default=60)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    if not ROMHASH.exists():
        subprocess.run(["make", "-s", "supervisor/romhash"], cwd=IMAGE, check=True)
    seed = a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 32)
    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="bench-hashfuzz-"))
    fails, checks = [], 0

    def world(spec, order=None, name="w"):
        w = tmp / f"{name}-{rng.randrange(1 << 30)}"
        (w / TOP).mkdir(parents=True)
        build(w / TOP, spec, order or sorted(spec))
        return w

    try:
        global TOP
        for t in range(a.trees):
            TOP = "hold" if t % 2 else "tests/rom"
            skips = TOP != "hold"
            spec = random_spec(rng)
            base = world(spec)
            c0, p0 = hashes(base)
            checks += 1
            if c0 != p0:
                fails.append(f"tree {t}: C {c0[:16]} != py {p0[:16]} ({base})")
                continue
            # under tests/rom a file inside a *.pyc dir is skipped by design: it cannot move the hash
            files = [k for k, v in spec.items() if v is not None and not (skips and derived(k))]

            def expect(label, mutate, moves):
                nonlocal checks
                w = world(spec, name=label)
                mutate(w / TOP)
                c, p = hashes(w)
                checks += 1
                if c != p:
                    fails.append(f"tree {t} {label}: C and py disagree after the change ({w})")
                elif (c != c0) != moves:
                    fails.append(f"tree {t} {label}: hash {'did not move' if moves else 'moved'} ({w})")
                else:
                    shutil.rmtree(w, ignore_errors=True)

            order = list(spec)
            rng.shuffle(order)
            w2 = world(spec, order, "reorder")
            if hashes(w2) != (c0, p0):
                fails.append(f"tree {t}: creation order moved the hash ({w2})")
            checks += 1
            b = os.fsencode

            def chmod_all(r):
                for dp, dn, fn in os.walk(r):
                    for f in fn:
                        os.utime(os.path.join(dp, f), (1, 1))
                        os.chmod(os.path.join(dp, f), 0o600)
            expect("times-modes", chmod_all, False)
            expect("empty-dir", lambda r: os.makedirs(os.path.join(b(r), b"emptydir/deeper")), False)
            expect("pycache", lambda r: (os.makedirs(os.path.join(b(r), b"__pycache__")),
                                         open(os.path.join(b(r), b"__pycache__", b"m.cpython.pyc"), "wb").write(b"x"),
                                         open(os.path.join(b(r), b"stray.pyc"), "wb").write(b"y")), not skips)
            expect("symlink", lambda r: os.symlink("/etc/hostname", os.path.join(b(r), b"link")), False)
            expect("fifo", lambda r: os.mkfifo(os.path.join(b(r), b"pipe")), False)
            expect("empty-file", lambda r: open(os.path.join(b(r), b"zz-new-empty"), "wb").close(), True)
            if files:
                f = rng.choice(files)
                fp = lambda r, f=f: os.path.join(b(r), f)   # noqa: E731

                def flip(r, fp=fp):
                    data = bytearray(open(fp(r), "rb").read())
                    if data:
                        i = rng.randrange(len(data))
                        data[i] ^= 1 << rng.randrange(8)
                    else:
                        data = bytearray(b"\0")
                    open(fp(r), "wb").write(bytes(data))
                expect("flip", flip, True)
                expect("append", lambda r, fp=fp: open(fp(r), "ab").write(b"\0"), True)
                expect("rename", lambda r, fp=fp: os.rename(fp(r), fp(r) + b"~"), True)
                # renamed into the skipped namespace: it leaves the tests/rom hash (moves), and in
                # hold/ it is still counted under its new name (moves)
                expect("rename-to-pyc", lambda r, fp=fp: os.rename(fp(r), fp(r) + b".pyc"), True)

                def edit_in_pyc(r):
                    d = os.path.join(b(r), b"cache.pyc")
                    os.makedirs(d, exist_ok=True)
                    open(os.path.join(d, b"payload"), "wb").write(b"parked")
                # bytes parked inside a *.pyc dir: invisible under tests/rom by design, counted in hold/
                expect("park-in-pyc-dir", edit_in_pyc, not skips)
                expect("into-subdir", lambda r, fp=fp, f=f: (os.makedirs(os.path.join(b(r), b"sub"), exist_ok=True),
                                                            os.rename(fp(r), os.path.join(b(r), b"sub", os.path.basename(f) + b"_m"))), True)
                others = [g for g in files if g != f and spec[g] != spec[f]]
                if others:
                    g = rng.choice(others)

                    def swap(r, f=f, g=g):
                        pf, pg = os.path.join(b(r), f), os.path.join(b(r), g)
                        x, y = open(pf, "rb").read(), open(pg, "rb").read()
                        open(pf, "wb").write(y)
                        open(pg, "wb").write(x)
                    expect("swap", swap, True)
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(w2, ignore_errors=True)
        # framing: trees whose naive concatenation would collide must not
        pairs = [({b"a": b"b\x001\x00c"}, {b"a": b"b", b"c": b""}), ({b"ab": b""}, {b"a": b"b"}),
                 ({b"a": b"12"}, {b"a": b"1", b"b": b"2"})]
        for i, (x, y) in enumerate(pairs):
            wx, wy = world(x, name=f"frame{i}x"), world(y, name=f"frame{i}y")
            checks += 1
            if hashes(wx)[0] == hashes(wy)[0]:
                fails.append(f"framing pair {i}: two different trees share a hash ({wx} {wy})")
    finally:
        if not fails:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"hash_fuzz seed={seed} trees={a.trees} checks={checks} failures={len(fails)}")
    for f in fails[:20]:
        print(f"  FAIL {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
