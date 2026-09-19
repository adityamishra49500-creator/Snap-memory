import unittest
from ingestion.documents import chunk_text, clean_text, validate_file, UnsupportedFileError, ExtractionError


class TestChunking(unittest.TestCase):
    def test_short_text_single_chunk(self):
        text = "This is a short sentence."
        chunks = chunk_text(text, chunk_size=900, overlap=150)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_long_text_multiple_chunks(self):
        text = ("Sentence number %d about SnapMemory. " % 0) * 400
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 500 * 1.5 + 1)

    def test_empty_text(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   "), [])

    def test_clean_text_collapses_whitespace(self):
        dirty = "Hello   world\n\n\n\nGoodbye\x00"
        cleaned = clean_text(dirty)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\n\n\n", cleaned)


class TestValidation(unittest.TestCase):
    def test_rejects_unsupported_extension(self):
        with self.assertRaises(UnsupportedFileError):
            validate_file("malware.exe", b"data")

    def test_rejects_empty_file(self):
        with self.assertRaises(ExtractionError):
            validate_file("notes.txt", b"")

    def test_accepts_supported_extension(self):
        ext, name = validate_file("notes.txt", b"hello")
        self.assertEqual(ext, ".txt")
        self.assertEqual(name, "notes.txt")

    def test_sanitizes_path_traversal_filename(self):
        ext, name = validate_file("../../etc/passwd.txt", b"hello")
        self.assertEqual(name, "passwd.txt")


if __name__ == "__main__":
    unittest.main()
