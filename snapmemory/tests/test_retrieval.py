import unittest
import sqlite3
import time
from db.database import SCHEMA
from ai import embeddings, rag


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT INTO documents (id, filename, source_type, file_hash, imported_at) VALUES (1, 'auth.txt', 'txt', 'h1', ?)",
            (time.time(),))

        self.texts = [
            "We decided to use Firebase authentication for rapid deployment.",
            "The launch date is scheduled for December 12th this year.",
            "James owns the backend indexing pipeline due November 28.",
        ]
        for i, t in enumerate(self.texts):
            self.conn.execute(
                "INSERT INTO chunks (source_type, source_id, chunk_index, text, page_number, created_at) "
                "VALUES ('document', 1, ?, ?, ?, ?)", (i, t, i + 1, time.time()))
        self.conn.commit()

        # fit embeddings over this small corpus
        embeddings.refit_corpus(self.texts)
        cur = self.conn.cursor()
        cur.execute("SELECT id, text FROM chunks")
        for cid, text in cur.fetchall():
            vec = embeddings.embed_texts([text])[0]
            self.conn.execute("UPDATE chunks SET embedding=? WHERE id=?", (vec.astype("float64").tobytes(), cid))
        self.conn.commit()

    def test_retrieve_returns_relevant_chunk_first(self):
        results = rag.retrieve(self.conn, "What did we decide about authentication?", top_k=3)
        self.assertGreater(len(results), 0)
        self.assertIn("Firebase", results[0]["text"])

    def test_citations_reference_real_chunk_ids(self):
        results = rag.retrieve(self.conn, "backend pipeline deadline", top_k=3)
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM chunks")
        real_ids = {row[0] for row in cur.fetchall()}
        for r in results:
            self.assertIn(r["citation_id"], real_ids)

    def test_source_label_includes_page_number(self):
        results = rag.retrieve(self.conn, "Firebase authentication", top_k=1)
        self.assertIn("Page", results[0]["label"])

    def test_ask_never_returns_citation_for_empty_corpus(self):
        empty_conn = sqlite3.connect(":memory:")
        empty_conn.executescript(SCHEMA)
        result = rag.ask(empty_conn, "anything at all?")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["chunks_retrieved"], 0)


if __name__ == "__main__":
    unittest.main()
