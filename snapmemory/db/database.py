"""
SnapMemory local database layer.

SQLite holds all metadata: documents, meetings, images, chunks, citations,
queries, and the audit log. Vector data (TF-IDF weight vectors, see
ai/embeddings.py) is stored alongside chunks as serialized numpy arrays in a
BLOB column — this keeps the whole memory store in a single portable file
with zero external services, which is the cleanest reliable local
architecture for a desktop-class app like this (see ARCHITECTURE.md for the
tradeoffs vs. a separate vector DB such as LanceDB/Chroma/FAISS).
"""
import sqlite3
import threading
from core import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    source_type TEXT NOT NULL,        -- pdf | pptx | txt | md
    file_hash TEXT NOT NULL UNIQUE,
    file_path TEXT,
    page_count INTEGER,
    imported_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'indexed'
);

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    file_path TEXT,
    duration_seconds REAL,
    transcript TEXT,
    summary TEXT,
    decisions TEXT,          -- JSON list
    action_items TEXT,       -- JSON list
    open_questions TEXT,     -- JSON list
    important_dates TEXT,    -- JSON list
    topics TEXT,             -- JSON list
    people TEXT,             -- JSON list
    transcription_status TEXT NOT NULL DEFAULT 'pending',
    transcription_provider TEXT,
    imported_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    file_path TEXT,
    ocr_text TEXT,
    description TEXT,
    imported_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,     -- document | meeting | image | note
    source_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    slide_number INTEGER,
    timestamp_seconds REAL,
    created_at REAL NOT NULL,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT,
    citations TEXT,           -- JSON list of chunk ids
    latency_ms REAL,
    model_used TEXT,
    execution_provider TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    provider TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type, source_id);
"""


def get_conn():
    """One SQLite connection per thread (Flask's dev server is
    multi-threaded by default)."""
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return _local.conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def reset_db():
    """Used by tests / 'Delete All' to get a clean slate."""
    conn = get_conn()
    tables = ["documents", "meetings", "images", "chunks", "queries", "audit_log", "benchmarks"]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
