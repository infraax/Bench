# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ring 0 muscle. runs tests/rom (or named files there). one line on stdout: GREEN or RED.

refuses anything that is not is_ring0 before running a single test.
"""
import io
import sys
import unittest
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[1]
ROM = IMAGE / "tests" / "rom"
sys.path.insert(0, str(IMAGE))
from isa.karpathy_rom import is_ring0  # noqa: E402

RING0_KINDS = {"PURE", "SCALAR"}


def main(argv):
    kind, files = "PURE", []
    it = iter(argv)
    for a in it:
        if a == "--kind":
            kind = next(it, "").upper()
        else:
            files.append(a)
    if kind not in RING0_KINDS:
        print(f"RED kind {kind or '?'} is not Ring 0")
        return 1

    # the whole image must be clean, not just the file asked for
    for f in sorted(ROM.glob("*.py")):
        if not is_ring0(f.read_text()):
            print(f"RED not ring0: tests/rom/{f.name}")
            return 1

    targets = [(IMAGE / f).resolve() for f in files] or sorted(ROM.glob("test_*.py"))
    for t in targets:
        if t.parent != ROM.resolve() or not t.is_file():
            print(f"RED not in tests/rom: {t}")
            return 1

    sys.path.insert(0, str(ROM))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(t.stem) for t in targets)
    stream = io.StringIO()
    res = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    if res.wasSuccessful():
        print(f"GREEN {res.testsRun} tests")
        return 0
    sys.stderr.write(stream.getvalue())
    print(f"RED {len(res.failures) + len(res.errors)}/{res.testsRun} failed")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
