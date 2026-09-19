import unittest
from core.hashing import hash_bytes


class TestDedup(unittest.TestCase):
    def test_same_content_same_hash(self):
        a = hash_bytes(b"hello world")
        b = hash_bytes(b"hello world")
        self.assertEqual(a, b)

    def test_different_content_different_hash(self):
        a = hash_bytes(b"hello world")
        b = hash_bytes(b"hello world!")
        self.assertNotEqual(a, b)

    def test_hash_is_deterministic_length(self):
        h = hash_bytes(b"x")
        self.assertEqual(len(h), 64)  # sha256 hex digest


if __name__ == "__main__":
    unittest.main()
