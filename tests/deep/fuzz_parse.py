# SPDX-License-Identifier: MIT OR Apache-2.0
"""Differential grammar fuzzer: three judges of one script line must agree.

  C     `bench check`  — the binary's own parse_line + its refusal prediction
  JS    ops-check.js   — the site playground's mirror (what humans and agents read)
  RUN   `bench run`    — ground truth, on a sample and on every disagreement

Lines come from a grammar (verbs, slots, paths, numbers, separators) with hostile atoms at the
boundaries a hand-written test forgets: byte lengths 127/128/255/256 with multibyte UTF-8,
Unicode case folding (U+017F LONG S upper-cases to "S" in JS, never in C), \\v and \\f as
separators, NUL, "+5" and "05" and full-width digits, T_tool and N edges. Byte mutations of the
ROM OPS_TABLE rows add the shapes nobody would write.

A disagreement is shrunk (delta debugging) to the smallest line that still disagrees the same
way, run for real, and saved under tests/deep/corpus/parse/ with all three verdicts. The corpus
is replayed first on every run, so a fixed bug stays fixed (and `make test-deep` says which
seeds still disagree).

  python3 tests/deep/fuzz_parse.py [--n 4000] [--seed S] [--oracle 60] [--json out.json]
exit 0: no disagreement. 1: disagreements (listed, shrunk, saved). 2: setup problem.
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[2]
BENCH = IMAGE / "supervisor" / "bench"
CORPUS = IMAGE / "tests" / "deep" / "corpus" / "parse"
sys.path.insert(0, str(IMAGE / "tests" / "rom"))
sys.path.insert(0, str(IMAGE / "tests" / "harness"))

VERBS = ["READ", "WRITE", "EXEC", "TEST", "WAIT"]
SUPER = ["INSTALL_ROM", "SET_LOOP", "KILL", "UNPLUG"]
SLOTS = ["fs", "tty", "fb", "judge", "radio", "FS", "net", ""]
KINDS = ["PURE", "SCALAR", "JUDGE", "VISUAL", "pure", "Pure", "LOUD"]
SEPS = [" ", " ", " ", "\t", "  ", " \t ", "\v", "\f", "\u00a0", "\u3000"]
NUMS = ["0", "1", "5000", "5001", "3600000", "3600001", "+5", "05", "-0", "-1", "0x10", "1e3",
        "\uff11", "\u0663", "99999999999999999999", "4294967296", " 5", "5 ", "", "1.5"]
UNI = ["\u017f", "\u0131", "\u212a", "\u00e9", "\u00df", "\u00a0", "\u200b", "\ufeff", "\x00", "\r", "\r\r",
       "\u2028", "\u0085", "\u2026", "\U0001f600"]


def pad_to(prefix, nbytes, fill="a"):
    """prefix + fill until the UTF-8 byte length is exactly nbytes (multibyte fills may undershoot)."""
    s = prefix
    while len((s + fill).encode()) <= nbytes:
        s += fill
    return s


def path_atom(rng, root):
    base = rng.choice([root, "main/", "hold/", "proposed/", "tests/rom/", "tools/", "/", "", "../", "hold/../"])
    name = rng.choice(["hello.txt", "x", "test_isa.py", "hash.py", "a.py", "..", ".", "a b",
                       "ok.py.txt", "\u00e9.py", "x" * rng.choice([1, 50, 120])])
    p = base + name
    r = rng.random()
    if r < 0.12:   # byte-length boundaries of the 128/256 fields, sometimes multibyte
        n = rng.choice([127, 128, 255, 256, 257])
        p = pad_to(base, n - (3 if p.endswith(".py") else 0), rng.choice(["a", "\u00e9", "\U0001f600"]))
        if name.endswith(".py"):
            p += ".py"
    return p


def gen_line(rng):
    sep = lambda: rng.choice(SEPS) if rng.random() < 0.35 else " "   # noqa: E731
    v = rng.choice(VERBS + VERBS + SUPER + ["FOO", "#", ""])
    r = rng.random()
    if r < 0.2:
        v = "".join(c.lower() if rng.random() < 0.5 else c for c in v)
    elif r < 0.3 and v:
        i = rng.randrange(len(v))
        v = v[:i] + rng.choice(["\u017f", "\u0131", "\u212a"]) + v[i + 1:]   # folds to ASCII in JS only
    lead = rng.choice(["", "", "", " ", "\t", "\v"])
    if v in ("READ", "WRITE") or v.upper() in ("READ", "WRITE"):
        parts = [v, rng.choice(SLOTS), path_atom(rng, "hold/" if v.upper() == "WRITE" else "main/")]
        if rng.random() < 0.5:
            n = rng.choice([0, 1, 10, 254, 255, 256, 300])
            parts.append(pad_to("", n, rng.choice(["p", "\u00e9"])) if n else "")
    elif v.upper() == "EXEC":
        parts = [v, path_atom(rng, "tools/")] + [path_atom(rng, "hold/") for _ in range(rng.choice([0, 1, 2, 16, 17, 18]))]
    elif v.upper() == "TEST":
        parts = [v, rng.choice(KINDS), path_atom(rng, "tests/rom/")] + (["extra"] if rng.random() < 0.1 else [])
    elif v.upper() == "WAIT":
        parts = [v, rng.choice(NUMS)] + (["2"] if rng.random() < 0.08 else [])
    else:
        parts = [v] + [rng.choice(["x", "main/a", "1"]) for _ in range(rng.randrange(3))]
    line = lead + "".join(p + sep() for p in parts).rstrip(" ")
    if rng.random() < 0.15:
        i = rng.randrange(len(line) + 1)
        line = line[:i] + rng.choice(UNI) + line[i:]
    if rng.random() < 0.03:
        line = pad_to(line + " ", rng.choice([509, 510, 511, 512]), "z")
    return line.replace("\n", "")


def mutate_row(rng, line):
    s = list(line)
    for _ in range(rng.randint(1, 3)):
        op = rng.random()
        i = rng.randrange(len(s) + 1)
        if op < 0.4:
            s.insert(i, rng.choice(UNI + list(" \t./-+#") + [rng.choice("azAZ09")]))
        elif op < 0.7 and s:
            del s[min(i, len(s) - 1)]
        elif s:
            s[min(i, len(s) - 1)] = rng.choice(UNI + list(" \t./"))
    return "".join(s).replace("\n", "")


# ---- the judges ----

LINE_RE = re.compile(r"^line (\d+) (blank|ok|parse|run)(?: ([A-Z]+))?(?: rule=(\S+))?", re.M)


def judge_c(lines):
    """bench check, 60 lines per file (script-long counts ops across a file)."""
    out = []
    for i in range(0, len(lines), 60):
        chunk = lines[i:i + 60]
        with tempfile.NamedTemporaryFile("wb", suffix=".ops", delete=False) as f:
            f.write(b"".join(l.encode("utf-8", "surrogatepass") + b"\n" for l in chunk))
            name = f.name
        try:
            r = subprocess.run([str(BENCH), "check", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        finally:
            os.unlink(name)
        got = {}
        for m in LINE_RE.finditer(r.stdout.decode("utf-8", "replace")):
            got[int(m.group(1))] = (m.group(2), m.group(4))
        if len(got) != len(chunk):
            raise SystemExit(f"fuzz_parse: bench check answered {len(got)} of {len(chunk)} lines\n{r.stdout[:400]!r}")
        out += [got[k + 1] for k in range(len(chunk))]
    return out


def judge_js(lines):
    r = subprocess.run(["node", str(IMAGE / "tests" / "deep" / "ops_line.mjs")], input=json.dumps(lines),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
    if r.returncode:
        raise SystemExit(f"fuzz_parse: node failed: {r.stderr[:400]}")
    return [(x["kind"], x["rule"]) for x in json.loads(r.stdout)]


def norm(v):
    kind, rule = v
    return ("ok", None) if kind in ("ok", "blank") else (kind, rule)


def judge_run(world, line, i=[0]):
    """the binary, for real: returns ("ok", None) or (kind, rule) from its output."""
    i[0] += 1
    p = world.root / f"oracle-{i[0]}.ops"
    p.write_bytes(line.encode("utf-8", "surrogatepass") + b"\n")
    r = subprocess.run([str(BENCH), "run", str(p)], cwd=IMAGE, env=world.env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    text = r.stdout.decode("utf-8", "replace")
    m = re.search(r"rule=([\w-]+)", text)
    if r.returncode == 0:
        return ("ok", None)
    kind = "parse" if "frame 1 " not in text and "frame 1\t" not in text and not re.search(r"^frame \d", text, re.M) else "run"
    return (kind, m.group(1) if m else f"exit{r.returncode}")


# ---- shrink ----

def shrink(line, still_bad):
    """ddmin over characters: the smallest line for which still_bad holds."""
    s, n = line, 2
    while len(s) >= 2:
        chunk = max(1, len(s) // n)
        reduced = False
        for i in range(0, len(s), chunk):
            cand = s[:i] + s[i + chunk:]
            if cand and still_bad(cand):
                s, n, reduced = cand, max(n - 1, 2), True
                break
        if not reduced:
            if chunk == 1:
                break
            n = min(len(s), n * 2)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--oracle", type=int, default=60, help="random lines also checked against a real run")
    ap.add_argument("--json")
    a = ap.parse_args()
    if not BENCH.exists():
        print("fuzz_parse: build first (make all)")
        return 2
    seed = a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 32)
    rng = random.Random(seed)
    from test_ops import OPS_TABLE
    corpus = sorted(CORPUS.glob("*.json"))
    seeds = [json.loads(p.read_text())["line"] for p in corpus]
    rows = [l for l, _ in OPS_TABLE]
    lines = seeds + rows + [gen_line(rng) if rng.random() < 0.75 else mutate_row(rng, rng.choice(rows)) for _ in range(a.n)]
    c, js = judge_c(lines), judge_js(lines)
    diffs = [(l, x, y) for l, x, y in zip(lines, c, js) if norm(x) != norm(y)]

    from test_cli import World, rmtree_force
    world = World()
    report = {"seed": seed, "lines": len(lines), "corpus": len(seeds), "disagreements": [], "oracle": {"checked": 0, "wrong": []}}
    try:
        seen = set()
        for line, x, y in diffs:
            sig = (norm(x), norm(y))
            if sig in seen:
                continue
            seen.add(sig)
            small = shrink(line, lambda t, sig=sig: (lambda u, v: (norm(u), norm(v)) == sig)(judge_c([t])[0], judge_js([t])[0]))
            truth = judge_run(world, small)
            rec = {"line": small, "c": list(norm(judge_c([small])[0])), "js": list(norm(judge_js([small])[0])),
                   "run": list(truth), "from": line}
            report["disagreements"].append(rec)
            key = hashlib.sha256(small.encode("utf-8", "surrogatepass")).hexdigest()[:12]
            CORPUS.mkdir(parents=True, exist_ok=True)
            (CORPUS / f"{key}.json").write_text(json.dumps({"line": small, "c": rec["c"], "js": rec["js"], "run": rec["run"]},
                                                           ensure_ascii=True, indent=1) + "\n")
        # the prediction oracle: check's verdict vs a real run on a random sample
        sample = rng.sample(range(len(lines)), min(a.oracle, len(lines)))
        for k in sample:
            truth = judge_run(world, lines[k])
            report["oracle"]["checked"] += 1
            if norm(c[k]) != truth and not (truth[1] or "").startswith(("fs-path", "sandbox", "worker-setup", "exit")):
                report["oracle"]["wrong"].append({"line": lines[k], "check": list(norm(c[k])), "run": list(truth)})
    finally:
        rmtree_force(world.root)

    total = len(diffs)
    print(f"fuzz_parse seed={seed} lines={len(lines)} (corpus {len(seeds)}) C/JS disagreements={total} "
          f"distinct={len(report['disagreements'])} oracle={report['oracle']['checked']} wrong={len(report['oracle']['wrong'])}")
    for d in report["disagreements"]:
        print(f"  DIFF {d['line']!r}: C={d['c']} JS={d['js']} RUN={d['run']}")
    for w in report["oracle"]["wrong"]:
        print(f"  ORACLE {w['line']!r}: check={w['check']} run={w['run']}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, ensure_ascii=True))
    return 1 if total or report["oracle"]["wrong"] else 0


if __name__ == "__main__":
    sys.exit(main())
