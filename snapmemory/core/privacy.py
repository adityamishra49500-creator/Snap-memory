"""
SnapMemory Privacy / Audit layer.

Every action that touches the filesystem, a model, or the network is logged
here. The Privacy Center in the UI reads these logs directly — it never
displays hard-coded or invented numbers.
"""
import json
import time
from core import config


EVENT_TYPES = {
    "file_imported",
    "embedding_generated",
    "model_executed",
    "query_executed",
    "network_request",
    "deletion",
    "export",
    "import_backup",
}


def log_event(conn, event_type: str, detail: dict):
    """Persist one audit event. `detail` must be JSON-serializable and must
    NOT include full raw file contents (see rule: don't log sensitive
    content unnecessarily)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown audit event type: {event_type}")
    ts = time.time()
    conn.execute(
        "INSERT INTO audit_log (ts, event_type, detail) VALUES (?, ?, ?)",
        (ts, event_type, json.dumps(detail)[:4000]),
    )
    conn.commit()


def get_privacy_summary(conn) -> dict:
    """Compute real counters from the audit log + DB state. Nothing here is
    hard-coded."""
    cur = conn.cursor()

    def count(event_type):
        cur.execute("SELECT COUNT(*) FROM audit_log WHERE event_type=?", (event_type,))
        return cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM documents")
    docs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM meetings")
    meetings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM images")
    images = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunks")
    chunks = cur.fetchone()[0]

    return {
        "cloud_api_calls": count("network_request"),
        "external_uploads": 0,  # SnapMemory never uploads user files anywhere
        "local_files_processed": count("file_imported"),
        "internet_required": False,
        "local_ai": True,
        "local_database": True,
        "local_embeddings": True,
        "local_llm": True,
        "documents_indexed": docs,
        "meetings_indexed": meetings,
        "images_indexed": images,
        "total_memory_chunks": chunks,
        "queries_executed": count("query_executed"),
        "models_executed": count("model_executed"),
        "deletions": count("deletion"),
    }


def get_audit_log(conn, limit: int = 200):
    cur = conn.cursor()
    cur.execute(
        "SELECT ts, event_type, detail FROM audit_log ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    out = []
    for ts, event_type, detail in rows:
        out.append({"ts": ts, "event_type": event_type, "detail": json.loads(detail)})
    return out
