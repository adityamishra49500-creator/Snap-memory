import unittest
import sqlite3
import time
from db.database import SCHEMA
from core import privacy


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)

    def test_schema_creates_all_tables(self):
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        expected = {"documents", "meetings", "images", "chunks", "queries", "audit_log", "benchmarks"}
        self.assertTrue(expected.issubset(tables))

    def test_document_insert_and_dedup_constraint(self):
        self.conn.execute(
            "INSERT INTO documents (filename, source_type, file_hash, imported_at) VALUES (?, ?, ?, ?)",
            ("a.txt", "txt", "hash123", time.time()))
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO documents (filename, source_type, file_hash, imported_at) VALUES (?, ?, ?, ?)",
                ("b.txt", "txt", "hash123", time.time()))

    def test_audit_log_and_privacy_summary(self):
        privacy.log_event(self.conn, "file_imported", {"type": "document", "filename": "a.txt"})
        privacy.log_event(self.conn, "query_executed", {"question": "hi"})
        summary = privacy.get_privacy_summary(self.conn)
        self.assertEqual(summary["local_files_processed"], 1)
        self.assertEqual(summary["queries_executed"], 1)
        self.assertEqual(summary["cloud_api_calls"], 0)
        self.assertTrue(summary["local_ai"])

    def test_audit_log_rejects_unknown_event_type(self):
        with self.assertRaises(ValueError):
            privacy.log_event(self.conn, "not_a_real_event", {})


if __name__ == "__main__":
    unittest.main()
