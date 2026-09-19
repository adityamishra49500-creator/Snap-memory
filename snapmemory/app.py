"""
SnapMemory — Flask application entry point.

Run with: python run.py
Then open http://127.0.0.1:5057
"""
import os
import io
import json
import time
import shutil
import zipfile
import tempfile

from flask import Flask, request, jsonify, send_from_directory, send_file

from core import config, hashing, privacy, benchmark
from db import database
from ai import embeddings, rag, vision, transcription, meeting_intelligence
from ai.providers import registry
from ingestion import documents as doc_ingest

app = Flask(__name__, static_folder="static", static_url_path="")


# ---------------------------------------------------------------- utilities

def get_db():
    conn = database.get_conn()
    return conn


def refit_embeddings(conn):
    """Refit the TF-IDF vectorizer over the full corpus and re-embed every
    chunk. Simple and correct; documented in ARCHITECTURE.md as the scaling
    limitation of a from-scratch-refit local embedding model."""
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM chunks")
    rows = cur.fetchall()
    if not rows:
        return
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    embeddings.refit_corpus(texts)
    mat = embeddings.embed_texts(texts)
    for cid, vec in zip(ids, mat):
        conn.execute("UPDATE chunks SET embedding=? WHERE id=?",
                     (vec.astype("float64").tobytes(), cid))
    conn.commit()
    privacy.log_event(conn, "embedding_generated", {"chunks": len(ids)})


def error_response(message, status=400):
    return jsonify({"error": message}), status


# ------------------------------------------------------------------ static

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# --------------------------------------------------------------- dashboard

@app.route("/api/dashboard")
def api_dashboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    docs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM meetings")
    meetings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM images")
    images = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunks")
    total_memories = cur.fetchone()[0]
    cur.execute("SELECT question, answer, created_at FROM queries ORDER BY created_at DESC LIMIT 5")
    recent_questions = [{"question": q, "answer": a, "created_at": c} for q, a, c in cur.fetchall()]
    cur.execute(
        "SELECT source_type, source_id, chunk_index, text, created_at FROM chunks ORDER BY created_at DESC LIMIT 5")
    recent_memories = [
        {"source_type": st, "source_id": sid, "snippet": t[:140], "created_at": c}
        for st, sid, _, t, c in cur.fetchall()
    ]
    privacy_summary = privacy.get_privacy_summary(conn)

    return jsonify({
        "app_name": config.APP_NAME,
        "tagline": config.TAGLINE,
        "documents": docs,
        "meetings": meetings,
        "images": images,
        "total_memories": total_memories,
        "recent_memories": recent_memories,
        "recent_questions": recent_questions,
        "cloud_requests": privacy_summary["cloud_api_calls"],
        "internet_required": False,
        "ai_mode": "LOCAL",
        "device": registry.device.__dict__,
        "db_path": config.DB_PATH,
    })


# --------------------------------------------------------------- documents

@app.route("/api/documents", methods=["GET"])
def list_documents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, filename, source_type, page_count, imported_at, status FROM documents ORDER BY imported_at DESC")
    rows = cur.fetchall()
    out = []
    for id_, filename, source_type, page_count, imported_at, status in rows:
        cur.execute("SELECT COUNT(*) FROM chunks WHERE source_type='document' AND source_id=?", (id_,))
        chunk_count = cur.fetchone()[0]
        out.append({"id": id_, "filename": filename, "source_type": source_type,
                     "page_count": page_count, "imported_at": imported_at,
                     "status": status, "chunk_count": chunk_count})
    return jsonify(out)


@app.route("/api/documents/upload", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return error_response("No file provided.")
    f = request.files["file"]
    data = f.read()
    try:
        ext, safe_name = doc_ingest.validate_file(f.filename, data)
    except doc_ingest.UnsupportedFileError as e:
        return error_response(str(e), 415)
    except doc_ingest.ExtractionError as e:
        return error_response(str(e), 422)

    file_hash = hashing.hash_bytes(data)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, filename FROM documents WHERE file_hash=?", (file_hash,))
    existing = cur.fetchone()
    action = request.form.get("duplicate_action", "skip")
    if existing and action == "skip":
        return jsonify({"status": "duplicate", "message": "The file already exists in SnapMemory.",
                         "existing_id": existing[0], "filename": existing[1]}), 200

    stored_path = os.path.join(config.FILES_DIR, f"{file_hash}{ext}")
    if not os.path.exists(stored_path):
        with open(stored_path, "wb") as out:
            out.write(data)

    try:
        chunks = doc_ingest.extract_and_chunk(ext, stored_path)
    except doc_ingest.ExtractionError as e:
        return error_response(str(e), 422)

    if existing and action == "replace":
        conn.execute("DELETE FROM chunks WHERE source_type='document' AND source_id=?", (existing[0],))
        conn.execute("UPDATE documents SET filename=?, page_count=?, imported_at=?, status='indexed' WHERE id=?",
                     (safe_name, max((c.get("page_number") or 0) for c in chunks) if chunks else 0,
                      time.time(), existing[0]))
        doc_id = existing[0]
    else:
        page_count = max([c.get("page_number") or 0 for c in chunks], default=0)
        cur.execute(
            "INSERT INTO documents (filename, source_type, file_hash, file_path, page_count, imported_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'indexed')",
            (safe_name, ext.strip("."), file_hash, stored_path, page_count, time.time()))
        doc_id = cur.lastrowid

    for c in chunks:
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, page_number, slide_number, timestamp_seconds, created_at) "
            "VALUES ('document', ?, ?, ?, ?, ?, NULL, ?)",
            (doc_id, c["chunk_index"], c["text"], c.get("page_number"), c.get("slide_number"), time.time()))
    conn.commit()

    privacy.log_event(conn, "file_imported", {"type": "document", "filename": safe_name, "chunks": len(chunks)})
    refit_embeddings(conn)

    return jsonify({"status": "ok", "document_id": doc_id, "filename": safe_name, "chunks": len(chunks)})


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    conn = get_db()
    conn.execute("DELETE FROM chunks WHERE source_type='document' AND source_id=?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    privacy.log_event(conn, "deletion", {"type": "document", "id": doc_id})
    refit_embeddings(conn)
    return jsonify({"status": "deleted"})


# ----------------------------------------------------------------- images

@app.route("/api/images", methods=["GET"])
def list_images():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, filename, ocr_text, description, imported_at FROM images ORDER BY imported_at DESC")
    return jsonify([
        {"id": i, "filename": f, "ocr_text": (o or "")[:200], "description": d, "imported_at": ts}
        for i, f, o, d, ts in cur.fetchall()
    ])


@app.route("/api/images/upload", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return error_response("No file provided.")
    f = request.files["file"]
    data = f.read()
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        return error_response(f"Unsupported image type: {ext}", 415)
    if not data:
        return error_response("File is empty.", 422)

    file_hash = hashing.hash_bytes(data)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM images WHERE file_hash=?", (file_hash,))
    if cur.fetchone():
        return jsonify({"status": "duplicate", "message": "The file already exists in SnapMemory."})

    stored_path = os.path.join(config.FILES_DIR, f"{file_hash}{ext}")
    with open(stored_path, "wb") as out:
        out.write(data)

    result = vision.process_image(stored_path)

    cur.execute(
        "INSERT INTO images (filename, file_hash, file_path, ocr_text, description, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
        (os.path.basename(f.filename), file_hash, stored_path, result["ocr_text"], result["description"], time.time()))
    image_id = cur.lastrowid

    memory_text = f"{result['description']}\n{result['ocr_text']}".strip()
    if memory_text:
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, created_at) VALUES ('image', ?, 0, ?, ?)",
            (image_id, memory_text, time.time()))
    conn.commit()

    privacy.log_event(conn, "file_imported", {"type": "image", "filename": f.filename})
    privacy.log_event(conn, "model_executed", {"model": "vision", "provider": vision.provider().name if vision.provider() else "unavailable"})
    refit_embeddings(conn)

    return jsonify({"status": "ok", "image_id": image_id, **result})


@app.route("/api/images/<int:image_id>", methods=["DELETE"])
def delete_image(image_id):
    conn = get_db()
    conn.execute("DELETE FROM chunks WHERE source_type='image' AND source_id=?", (image_id,))
    conn.execute("DELETE FROM images WHERE id=?", (image_id,))
    conn.commit()
    privacy.log_event(conn, "deletion", {"type": "image", "id": image_id})
    refit_embeddings(conn)
    return jsonify({"status": "deleted"})


# --------------------------------------------------------------- meetings

@app.route("/api/meetings", methods=["GET"])
def list_meetings():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, filename, transcription_status, transcription_provider, imported_at, summary FROM meetings ORDER BY imported_at DESC")
    return jsonify([
        {"id": i, "filename": f, "status": s, "provider": p, "imported_at": ts, "summary": summary}
        for i, f, s, p, ts, summary in cur.fetchall()
    ])


@app.route("/api/meetings/<int:meeting_id>", methods=["GET"])
def get_meeting(meeting_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT filename, transcript, summary, decisions, action_items, open_questions,
                   important_dates, topics, people, transcription_status, transcription_provider
                   FROM meetings WHERE id=?""", (meeting_id,))
    row = cur.fetchone()
    if not row:
        return error_response("Meeting not found.", 404)
    keys = ["filename", "transcript", "summary", "decisions", "action_items", "open_questions",
            "important_dates", "topics", "people", "status", "provider"]
    result = dict(zip(keys, row))
    for k in ["decisions", "action_items", "open_questions", "important_dates", "topics", "people"]:
        result[k] = json.loads(result[k]) if result[k] else []
    return jsonify(result)


@app.route("/api/meetings/upload", methods=["POST"])
def upload_meeting():
    if "file" not in request.files:
        return error_response("No file provided.")
    f = request.files["file"]
    data = f.read()
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in {".wav", ".mp3", ".m4a", ".webm"}:
        return error_response(f"Unsupported audio type: {ext}", 415)
    if not data:
        return error_response("File is empty.", 422)

    file_hash = hashing.hash_bytes(data)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM meetings WHERE file_hash=?", (file_hash,))
    if cur.fetchone():
        return jsonify({"status": "duplicate", "message": "The file already exists in SnapMemory."})

    stored_path = os.path.join(config.FILES_DIR, f"{file_hash}{ext}")
    with open(stored_path, "wb") as out:
        out.write(data)

    cur.execute(
        "INSERT INTO meetings (filename, file_hash, file_path, transcription_status, imported_at) VALUES (?, ?, ?, 'processing', ?)",
        (os.path.basename(f.filename), file_hash, stored_path, time.time()))
    meeting_id = cur.lastrowid
    conn.commit()
    privacy.log_event(conn, "file_imported", {"type": "meeting", "filename": f.filename})

    try:
        result = transcription.transcribe(stored_path)
    except RuntimeError as e:
        conn.execute("UPDATE meetings SET transcription_status='unavailable' WHERE id=?", (meeting_id,))
        conn.commit()
        return jsonify({"status": "transcription_unavailable", "meeting_id": meeting_id, "message": str(e)}), 200

    intelligence = meeting_intelligence.extract(result["transcript"], result.get("segments"))

    conn.execute(
        """UPDATE meetings SET transcript=?, summary=?, decisions=?, action_items=?, open_questions=?,
           important_dates=?, topics=?, people=?, transcription_status='indexed', transcription_provider=?,
           duration_seconds=? WHERE id=?""",
        (result["transcript"], intelligence["summary"], json.dumps(intelligence["decisions"]),
         json.dumps(intelligence["action_items"]), json.dumps(intelligence["open_questions"]),
         json.dumps(intelligence["important_dates"]), json.dumps(intelligence["topics"]),
         json.dumps(intelligence["people"]), result["provider"], result.get("duration_seconds"), meeting_id))

    for seg in result.get("segments", []):
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, timestamp_seconds, created_at) "
            "VALUES ('meeting', ?, ?, ?, ?, ?)",
            (meeting_id, 0, seg["text"], seg["start"], time.time()))
    conn.commit()

    privacy.log_event(conn, "model_executed", {"model": "speech", "provider": result["provider"], "latency_ms": result["latency_ms"]})
    refit_embeddings(conn)

    return jsonify({"status": "ok", "meeting_id": meeting_id, "provider": result["provider"], **intelligence})


@app.route("/api/meetings/<int:meeting_id>", methods=["DELETE"])
def delete_meeting(meeting_id):
    conn = get_db()
    conn.execute("DELETE FROM chunks WHERE source_type='meeting' AND source_id=?", (meeting_id,))
    conn.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
    conn.commit()
    privacy.log_event(conn, "deletion", {"type": "meeting", "id": meeting_id})
    refit_embeddings(conn)
    return jsonify({"status": "deleted"})


# --------------------------------------------------------------------- ask

@app.route("/api/ask", methods=["POST"])
def api_ask():
    payload = request.get_json(force=True, silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return error_response("Question is required.")
    filters = payload.get("filters") or {}
    top_k = payload.get("top_k")

    conn = get_db()
    result = rag.ask(conn, question, top_k=top_k, filters=filters)
    privacy.log_event(conn, "query_executed", {"question": question[:200], "chunks": result["chunks_retrieved"]})
    return jsonify(result)


# ---------------------------------------------------------------- memories

@app.route("/api/memories", methods=["GET"])
def list_memories():
    conn = get_db()
    source_type = request.args.get("type")
    search = request.args.get("q", "").strip()
    cur = conn.cursor()
    q = "SELECT id, source_type, source_id, text, page_number, slide_number, timestamp_seconds, created_at FROM chunks"
    clauses, params = [], []
    if source_type and source_type != "all":
        clauses.append("source_type=?")
        params.append(source_type)
    if search:
        clauses.append("text LIKE ?")
        params.append(f"%{search}%")
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY created_at DESC LIMIT 300"
    cur.execute(q, params)
    rows = cur.fetchall()
    out = []
    for id_, st, sid, text, pg, sl, ts, created in rows:
        label = rag._source_label(conn, st, sid, pg, sl, ts)
        out.append({"id": id_, "source_type": st, "source_id": sid, "snippet": text[:220],
                     "label": label, "created_at": created})
    return jsonify(out)


# ---------------------------------------------------------------- timeline

@app.route("/api/timeline")
def api_timeline():
    conn = get_db()
    cur = conn.cursor()
    items = []
    cur.execute("SELECT filename, imported_at, 'document' FROM documents")
    items += cur.fetchall()
    cur.execute("SELECT filename, imported_at, 'meeting' FROM meetings")
    items += cur.fetchall()
    cur.execute("SELECT filename, imported_at, 'image' FROM images")
    items += cur.fetchall()
    items.sort(key=lambda t: t[1], reverse=True)
    return jsonify([{"filename": f, "imported_at": ts, "type": t} for f, ts, t in items])


# ---------------------------------------------------------------- privacy

@app.route("/api/privacy")
def api_privacy():
    conn = get_db()
    return jsonify({
        "summary": privacy.get_privacy_summary(conn),
        "audit_log": privacy.get_audit_log(conn, limit=100),
    })


# ------------------------------------------------------------------ model

@app.route("/api/models")
def api_models():
    return jsonify({
        "device": registry.device.__dict__,
        "statuses": registry.all_statuses(),
    })


# ------------------------------------------------------------- benchmark

@app.route("/api/benchmark/run", methods=["POST"])
def api_benchmark_run():
    conn = get_db()
    results = benchmark.run_benchmark(conn)
    return jsonify(results)


@app.route("/api/benchmark/history")
def api_benchmark_history():
    conn = get_db()
    return jsonify(benchmark.history(conn))


@app.route("/api/benchmark/export")
def api_benchmark_export():
    conn = get_db()
    data = benchmark.history(conn, limit=1000)
    fmt = request.args.get("format", "json")
    if fmt == "csv":
        import csv
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["name", "metric", "value", "unit", "provider", "created_at"])
        writer.writeheader()
        writer.writerows(data)
        mem = io.BytesIO(buf.getvalue().encode("utf-8"))
        return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="snapmemory_benchmarks.csv")
    mem = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
    return send_file(mem, mimetype="application/json", as_attachment=True, download_name="snapmemory_benchmarks.json")


# ----------------------------------------------------------- data mgmt

@app.route("/api/data/delete_all", methods=["POST"])
def delete_all():
    conn = get_db()
    database.reset_db()
    privacy.log_event(conn, "deletion", {"type": "all"})
    return jsonify({"status": "deleted_all"})


@app.route("/api/data/export")
def export_backup():
    conn = get_db()
    tmp = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(config.DB_PATH, arcname="snapmemory.db")
        for root, _, files in os.walk(config.FILES_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                zf.write(full, arcname=os.path.join("files", fn))
    privacy.log_event(conn, "export", {"path": tmp})
    return send_file(tmp, mimetype="application/zip", as_attachment=True, download_name="snapmemory_backup.zip")


@app.route("/api/data/import", methods=["POST"])
def import_backup():
    if "file" not in request.files:
        return error_response("No backup file provided.")
    f = request.files["file"]
    tmp_dir = tempfile.mkdtemp()
    zpath = os.path.join(tmp_dir, "backup.zip")
    f.save(zpath)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp_dir)
    db_src = os.path.join(tmp_dir, "snapmemory.db")
    if not os.path.exists(db_src):
        return error_response("Invalid backup file: snapmemory.db not found.", 422)
    shutil.copy(db_src, config.DB_PATH)
    files_src = os.path.join(tmp_dir, "files")
    if os.path.isdir(files_src):
        for fn in os.listdir(files_src):
            shutil.copy(os.path.join(files_src, fn), os.path.join(config.FILES_DIR, fn))
    conn = get_db()
    privacy.log_event(conn, "import_backup", {"filename": f.filename})
    return jsonify({"status": "restored"})


# --------------------------------------------------------------- demo mode

@app.route("/api/demo/seed", methods=["POST"])
def demo_seed():
    from demo.seed import seed_demo_data
    conn = get_db()
    result = seed_demo_data(conn)
    refit_embeddings(conn)
    return jsonify(result)


if __name__ == "__main__":
    database.init_db()
    app.run(host="127.0.0.1", port=5057, debug=True, threaded=True)
