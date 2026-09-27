"""Ring 0: the owner arms a session. the intern's WRITE rule cannot reach the token."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from isa.hotz_isa import INTERN_WRITE_ROOTS, OWNER_TOKEN, intern_may_write  # noqa: E402

# (path, intern may write it). the harness runs the same table through the C parser.
WRITE_TABLE = [
    ("hold/out.txt", True),
    ("hold/deep/dir/out.txt", True),
    ("proposed/tests/test_x.py", True),
    (OWNER_TOKEN, False),
    ("sessions/current", False),
    ("sessions/CURRENT", False),
    ("hold/../sessions/current/token", False),
    ("proposed/../../sessions/current/token", False),
    ("/sessions/current/token", False),
    ("./sessions/current/token", False),
    ("main/hello.txt", False),
    ("tests/rom/test_isa.py", False),
    ("holdings/x", False),
    ("", False),
]


class TestArm(unittest.TestCase):
    def test_token_lives_outside_intern_roots(self):
        self.assertFalse(OWNER_TOKEN.startswith(INTERN_WRITE_ROOTS))

    def test_fixture_cannot_mint_the_token(self):
        for path, ok in WRITE_TABLE:
            with self.subTest(path=path):
                self.assertIs(intern_may_write(path), ok)

    def test_non_string_is_not_a_path(self):
        self.assertFalse(intern_may_write(None))
        self.assertFalse(intern_may_write(b"hold/x"))


if __name__ == "__main__":
    unittest.main()
