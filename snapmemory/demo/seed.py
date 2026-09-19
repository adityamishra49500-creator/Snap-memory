"""
Demo Mode: loads a small, clearly-synthetic sample dataset through the SAME
ingestion pipeline real files go through (chunking, OCR, meeting
intelligence, embeddings) so the full product can be demonstrated even if a
judge doesn't bring their own files.

The one exception is audio: since this build environment has no
network access to obtain synthesized audio or a bundled speech model, the
demo "meeting" is seeded from a pre-written transcript text file rather
than a real audio recording. This is disclosed in the UI (transcription
provider will read "Synthetic demo transcript — no audio/speech model was
run") rather than silently pretending Whisper ran.
"""
import os
import time
import json

from core import config, hashing, privacy
from ingestion import documents as doc_ingest
from ai import vision, meeting_intelligence

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")


def _index_document(conn, path, filename, ext):
    data = open(path, "rb").read()
    file_hash = hashing.hash_bytes(data)
    cur = conn.cursor()
    cur.execute("SELECT id FROM documents WHERE file_hash=?", (file_hash,))
    if cur.fetchone():
        return None
    stored_path = os.path.join(config.FILES_DIR, f"{file_hash}{ext}")
    if not os.path.exists(stored_path):
        with open(stored_path, "wb") as out:
            out.write(data)
    chunks = doc_ingest.extract_and_chunk(ext, stored_path)
    page_count = max([c.get("page_number") or c.get("slide_number") or 0 for c in chunks], default=0)
    cur.execute(
        "INSERT INTO documents (filename, source_type, file_hash, file_path, page_count, imported_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'indexed')",
        (filename, ext.strip("."), file_hash, stored_path, page_count, time.time()))
    doc_id = cur.lastrowid
    for c in chunks:
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, page_number, slide_number, created_at) "
            "VALUES ('document', ?, ?, ?, ?, ?, ?)",
            (doc_id, c["chunk_index"], c["text"], c.get("page_number"), c.get("slide_number"), time.time()))
    privacy.log_event(conn, "file_imported", {"type": "document", "filename": filename, "demo": True})
    return doc_id


def _index_image(conn, path, filename):
    data = open(path, "rb").read()
    file_hash = hashing.hash_bytes(data)
    cur = conn.cursor()
    cur.execute("SELECT id FROM images WHERE file_hash=?", (file_hash,))
    if cur.fetchone():
        return None
    stored_path = os.path.join(config.FILES_DIR, f"{file_hash}.png")
    if not os.path.exists(stored_path):
        with open(stored_path, "wb") as out:
            out.write(data)
    result = vision.process_image(stored_path)
    cur.execute(
        "INSERT INTO images (filename, file_hash, file_path, ocr_text, description, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
        (filename, file_hash, stored_path, result["ocr_text"], result["description"], time.time()))
    image_id = cur.lastrowid
    memory_text = f"{result['description']}\n{result['ocr_text']}".strip()
    if memory_text:
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, created_at) VALUES ('image', ?, 0, ?, ?)",
            (image_id, memory_text, time.time()))
    privacy.log_event(conn, "file_imported", {"type": "image", "filename": filename, "demo": True})
    return image_id


def _index_synthetic_meeting(conn, transcript_path, filename):
    transcript = open(transcript_path, "r", encoding="utf-8").read().strip()
    file_hash = hashing.hash_bytes(transcript.encode("utf-8"))
    cur = conn.cursor()
    cur.execute("SELECT id FROM meetings WHERE file_hash=?", (file_hash,))
    if cur.fetchone():
        return None

    intelligence = meeting_intelligence.extract(transcript)
    cur.execute(
        """INSERT INTO meetings (filename, file_hash, file_path, transcript, summary, decisions,
           action_items, open_questions, important_dates, topics, people,
           transcription_status, transcription_provider, imported_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed', ?, ?)""",
        (filename, file_hash, transcript_path, transcript, intelligence["summary"],
         json.dumps(intelligence["decisions"]), json.dumps(intelligence["action_items"]),
         json.dumps(intelligence["open_questions"]), json.dumps(intelligence["important_dates"]),
         json.dumps(intelligence["topics"]), json.dumps(intelligence["people"]),
         "Synthetic demo transcript (no audio/speech model run)", time.time()))
    meeting_id = cur.lastrowid

    # chunk the transcript into pseudo-timestamped segments for retrieval/citation demo purposes
    sentences = [s.strip() for s in transcript.split(". ") if s.strip()]
    for i, sent in enumerate(sentences):
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, text, timestamp_seconds, created_at) "
            "VALUES ('meeting', ?, ?, ?, ?, ?)",
            (meeting_id, i, sent, i * 12.0, time.time()))
    privacy.log_event(conn, "file_imported", {"type": "meeting", "filename": filename, "demo": True})
    return meeting_id


def seed_demo_data(conn):
    created = {"documents": [], "images": [], "meetings": []}

    doc_files = [
        ("project_proposal.txt", ".txt"),
        ("roadmap.txt", ".txt"),
        ("architecture.pptx", ".pptx"),
    ]
    for fname, ext in doc_files:
        path = os.path.join(SAMPLE_DIR, fname)
        if os.path.exists(path):
            doc_id = _index_document(conn, path, fname, ext)
            if doc_id:
                created["documents"].append({"id": doc_id, "filename": fname})

    img_path = os.path.join(SAMPLE_DIR, "sprint_board_screenshot.png")
    if os.path.exists(img_path):
        image_id = _index_image(conn, img_path, "sprint_board_screenshot.png")
        if image_id:
            created["images"].append({"id": image_id, "filename": "sprint_board_screenshot.png"})

    meeting_path = os.path.join(SAMPLE_DIR, "meeting_transcript.txt")
    if os.path.exists(meeting_path):
        meeting_id = _index_synthetic_meeting(conn, meeting_path, "Project Sync — Demo Meeting")
        if meeting_id:
            created["meetings"].append({"id": meeting_id, "filename": "Project Sync — Demo Meeting"})

    conn.commit()
    created["is_synthetic_demo_data"] = True
    return created
