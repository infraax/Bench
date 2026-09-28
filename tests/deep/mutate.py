# SPDX-License-Identifier: MIT OR Apache-2.0
"""Mutation testing: test the tests. A mutant that survives is a behaviour no test pins.

Every mutant runs in a private copy of the tree (never this checkout), so an interrupted run
cannot leave a mutated file behind.

  --lang py   AST mutants of isa/*.py (compare flips, and/or, not, constants, set/tuple members
              dropped, returns negated), judged by the ROM suite (tests/rom). Seconds.
  --lang c    operator mutants inside chosen functions of supervisor/main.c (== !=, < <=, > >=,
              && ||, a dropped '!', an integer +-1), built with -Werror, judged by the harness
              classes that pin those functions (--tests). Minutes.

  python3 tests/deep/mutate.py                                    # py, all of isa/
  python3 tests/deep/mutate.py --lang c --func parse_line,predict,line_bad
  python3 tests/deep/mutate.py --json out.json

Output: one line per SURVIVED mutant (file:line, what changed): each is a missing test or a
dead branch. Score = killed / (killed + survived); build failures do not count.
exit 0 always unless --min-score is given and missed (so it can gate later, by choice).
"""
import argparse
import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
SKIP = {".git", "sessions", "ledger", "__pycache__", "docs", "node_modules"}


def private_tree():
    d = Path(tempfile.mkdtemp(prefix="bench-mut-"))
    for p in IMAGE.iterdir():
        if p.name in SKIP:
            continue
        if p.is_dir():
            shutil.copytree(p, d / p.name, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(p, d / p.name)
    (d / "sessions").mkdir()
    return d


# ---- python: AST mutants ----

FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
        ast.GtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}


def py_sites(tree):
    """(node path, description, apply(node) -> new node or None) for every mutation site."""
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in FLIP:
                    sites.append((node, f"{type(op).__name__}->{FLIP[type(op)].__name__}", ("cmp", i)))
        elif isinstance(node, ast.BoolOp):
            sites.append((node, f"{type(node.op).__name__}->{'Or' if isinstance(node.op, ast.And) else 'And'}", ("bool",)))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append((node, "drop not", ("not",)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            sites.append((node, f"{node.value}->{not node.value}", ("const",)))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            sites.append((node, f"{node.value}->{node.value + 1}", ("const",)))
        elif isinstance(node, (ast.Set, ast.Tuple, ast.List)) and 1 < len(node.elts) <= 40 and isinstance(getattr(node, "ctx", ast.Load()), ast.Load):
            for i, e in enumerate(node.elts):
                label = ast.unparse(e)[:30]
                sites.append((node, f"drop member {label}", ("drop", i)))
        elif isinstance(node, ast.Return) and node.value is not None:
            sites.append((node, "return not <x>", ("ret",)))
    return sites


def py_apply(node, how):
    k = how[0]
    if k == "cmp":
        node.ops[how[1]] = FLIP[type(node.ops[how[1]])]()
    elif k == "bool":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif k == "not":
        return node.operand
    elif k == "const":
        node.value = (not node.value) if isinstance(node.value, bool) else node.value + 1
    elif k == "drop":
        del node.elts[how[1]]
    elif k == "ret":
        node.value = ast.UnaryOp(op=ast.Not(), operand=node.value)
    return node


class Swap(ast.NodeTransformer):
    def __init__(self, target, how):
        self.target, self.how = target, how

    def visit(self, node):
        if node is self.target:
            return py_apply(node, self.how)
        return self.generic_visit(node)


def run_py(files, jobs, timeout):
    work = private_tree()
    results = []
    try:
        mutants = []
        for rel in files:
            src = (IMAGE / rel).read_text()
            tree = ast.parse(src)
            for idx, (node, desc, how) in enumerate(py_sites(tree)):
                mutants.append((rel, idx, node.lineno, desc, how))

        def one(m):
            rel, idx, line, desc, how = m
            d = Path(tempfile.mkdtemp(prefix="m-", dir=work))
            try:
                shutil.copytree(work / "isa", d / "isa")
                shutil.copytree(work / "tests", d / "tests", ignore=shutil.ignore_patterns("harness", "deep", "site"))
                tree = ast.parse((IMAGE / rel).read_text())
                node, _, h = py_sites(tree)[idx]
                new = ast.fix_missing_locations(Swap(node, h).visit(tree))
                try:
                    code = ast.unparse(new)
                    compile(code, rel, "exec")
                except Exception:
                    return (m, "invalid")
                (d / rel).write_text(code)
                try:
                    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/rom", "-p", "test_*.py", "-q"],
                                       cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
                    return (m, "killed" if r.returncode else "survived")
                except subprocess.TimeoutExpired:
                    return (m, "killed")   # a hang is caught by the suite's clock
            finally:
                shutil.rmtree(d, ignore_errors=True)

        with ThreadPoolExecutor(jobs) as ex:
            for m, verdict in ex.map(one, mutants):
                results.append({"file": m[0], "line": m[2], "mutant": m[3], "verdict": verdict})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return results


# ---- C: operator mutants inside named functions ----

C_OPS = [(r"==", "!="), (r"!=", "=="), (r"<=", "<"), (r">=", ">"), (r"(?<![<>=!-])<(?![<=])", "<="),
         (r"(?<![<>=-])>(?![>=])", ">="), (r"&&", "||"), (r"\|\|", "&&"), (r"!(?=[a-z_(])", ""),
         (r"(?<![\w.])(\d+)(?![\w.])", None)]


def c_function_span(lines, name):
    start = next((i for i, l in enumerate(lines) if re.match(rf"^static [^;]*\b{name}\(", l)), None)
    if start is None:
        raise SystemExit(f"mutate: no function {name} in main.c")
    depth, seen = 0, False
    for j in range(start, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        seen = seen or "{" in lines[j]
        if seen and depth == 0:
            return start, j
    return start, len(lines) - 1


def c_mutants(lines, funcs):
    out = []
    for f in funcs:
        a, b = c_function_span(lines, f)
        in_comment = False
        for i in range(a + 1, b):
            raw = lines[i]
            if in_comment:
                if "*/" not in raw:
                    continue
                raw, in_comment = raw.split("*/", 1)[1], False
            if "/*" in raw and "*/" not in raw.split("/*", 1)[1]:
                in_comment = True
            code = re.sub(r"/\*.*?\*/", "", raw).split("/*")[0].split("//")[0]
            if code != lines[i] and code not in lines[i]:
                continue   # a line that ends a comment: leave it
            if code.strip().startswith(("#", "*", "fprintf", "printf", "snprintf(why", "FAULT(\"internal")):
                continue
            if '"' in code:   # mutate only outside string literals
                segs = re.split(r'("(?:[^"\\]|\\.)*")', code)
            else:
                segs = [code]
            pos = 0
            for si, seg in enumerate(segs):
                if si % 2 == 1:
                    pos += len(seg)
                    continue
                for pat, rep in C_OPS:
                    for m in re.finditer(pat, seg):
                        s0, s1 = pos + m.start(), pos + m.end()
                        if rep is None:
                            v = int(m.group(1))
                            if v > 100000:
                                continue
                            new = code[:s0] + str(v + 1) + code[s1:]
                            desc = f"{v}->{v + 1}"
                        else:
                            new = code[:s0] + rep + code[s1:]
                            desc = f"{m.group(0)}->{rep or 'drop !'}"
                        out.append((f, i, desc, lines[i].replace(code, new, 1)))
                pos += len(seg)
    return out


def run_c(funcs, tests, jobs, timeout):
    src = (IMAGE / "supervisor" / "main.c").read_text().split("\n")
    mutants = c_mutants(src, funcs)
    results = []
    base = private_tree()
    try:
        r = subprocess.run(["make", "-s", "all"], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if r.returncode:
            raise SystemExit(f"mutate: the unmutated tree does not build:\n{r.stdout.decode()[-400:]}")

        def one(m):
            f, i, desc, new = m
            d = Path(tempfile.mkdtemp(prefix="c-", dir=base.parent))
            try:
                shutil.copytree(base, d, dirs_exist_ok=True, symlinks=True)
                lines = list(src)
                lines[i] = new
                (d / "supervisor" / "main.c").write_text("\n".join(lines))
                b = subprocess.run(["make", "-s", "supervisor/bench"], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if b.returncode:
                    return (m, "unbuildable")
                try:
                    t = subprocess.run([sys.executable, "-m", "unittest", *tests, "-q"], cwd=d,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
                    return (m, "killed" if t.returncode else "survived")
                except subprocess.TimeoutExpired:
                    return (m, "killed")
            finally:
                shutil.rmtree(d, ignore_errors=True)

        with ThreadPoolExecutor(jobs) as ex:
            for m, verdict in ex.map(one, mutants):
                results.append({"file": f"supervisor/main.c:{m[0]}", "line": m[1] + 1, "mutant": m[2], "verdict": verdict})
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["py", "c"], default="py")
    ap.add_argument("--files", default="isa/hotz_isa.py,isa/karpathy_rom.py")
    ap.add_argument("--func", default="parse_line,predict,line_bad,read_line")
    ap.add_argument("--tests", default="tests.harness.test_cli.TestCheck,tests.harness.test_cli.TestOpsTable,"
                                       "tests.harness.test_cli.TestRefusals,tests.harness.test_cli.TestParseEdges")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--min-score", type=float)
    ap.add_argument("--json")
    a = ap.parse_args()
    t0 = time.monotonic()
    if a.lang == "py":
        res = run_py(a.files.split(","), a.jobs, a.timeout)
    else:
        res = run_c(a.func.split(","), a.tests.split(","), a.jobs, a.timeout)
    killed = sum(r["verdict"] == "killed" for r in res)
    surv = [r for r in res if r["verdict"] == "survived"]
    score = killed / max(1, killed + len(surv))
    for r in sorted(surv, key=lambda r: (r["file"], r["line"])):
        print(f"SURVIVED {r['file']}:{r['line']}  {r['mutant']}")
    other = {v: sum(r["verdict"] == v for r in res) for v in ("invalid", "unbuildable") if any(r["verdict"] == v for r in res)}
    print(f"mutate lang={a.lang} mutants={len(res)} killed={killed} survived={len(surv)} "
          f"score={score:.1%} {other if other else ''} {time.monotonic() - t0:.0f}s")
    if a.json:
        Path(a.json).write_text(json.dumps({"lang": a.lang, "score": score, "results": res}, indent=1))
    return 1 if a.min_score is not None and score < a.min_score else 0


if __name__ == "__main__":
    sys.exit(main())
