"""
SnapMemory local RAG engine.

Pipeline: question -> embed -> vector similarity search -> keyword/hybrid
boost -> rerank -> top-K chunks -> local answer generation -> citations.

LLM note (read this before assuming a bug): a full deployment plugs in a
local LLM here (Qualcomm AI Hub LLM on the NPU, or a llama.cpp GGUF model
on CPU/GPU) to synthesize a fluent answer from the retrieved chunks. This
authoring sandbox has no internet access and no LLM runtime installed, so
`LocalExtractiveAnswerer` is used: it builds a grounded answer by selecting
and lightly stitching the most relevant sentences from the retrieved
chunks, and ONLY those chunks — it never introduces information that isn't
in the retrieved context, and every claim is traceable to a citation. This
satisfies the "never fabricate" rule even without a generative model.
Wiring in a real local LLM: implement `LocalLlmAnswerer` (stub included)
and set SNAPMEMORY_LLM_PROVIDER=local_llm — no caller code changes needed.
"""
import os
import re
import time
import json
import numpy as np

from ai import embeddings
from ai.providers import registry, ModelStatus
from core import config


class LocalExtractiveAnswerer:
    name = "Local extractive grounded answerer (no neural LLM)"

    def answer(self, question: str, chunks: list[dict]) -> str:
        if not chunks:
            return ("I couldn't find anything in your local memory relevant to that "
                    "question. Try importing the related document, meeting, or image first.")

        q_words = set(re.findall(r"[a-zA-Z]{3,}", question.lower()))
        best_sentences = []
        for c in chunks:
            for sent in re.split(r"(?<=[.!?])\s+", c["text"]):
                sent = sent.strip()
                if not sent:
                    continue
                s_words = set(re.findall(r"[a-zA-Z]{3,}", sent.lower()))
                overlap = len(q_words & s_words)
                if overlap > 0:
                    best_sentences.append((overlap, c["citation_id"], sent))

        if not best_sentences:
            # fall back to the single top chunk's opening sentences
            top = chunks[0]["text"]
            snippet = " ".join(re.split(r"(?<=[.!?])\s+", top)[:2])
            return (f"{snippet}\n\n(This is the most relevant passage found, though it "
                     f"doesn't directly overlap with your exact wording — see the source below.)")

        best_sentences.sort(key=lambda t: -t[0])
        seen_cids = []
        answer_parts = []
        for overlap, cid, sent in best_sentences[:4]:
            answer_parts.append(sent)
            if cid not in seen_cids:
                seen_cids.append(cid)

        return " ".join(dict.fromkeys(answer_parts))


class LocalLlmAnswerer:
    """Hook point for a real local LLM (Qualcomm AI Hub or llama.cpp GGUF).
    Not implemented in this build — see module docstring."""
    name = "Local LLM (not configured)"

    def __init__(self):
        raise RuntimeError(
            "No local LLM runtime configured. Install a local GGUF runtime "
            "(e.g. llama-cpp-python) with a downloaded model, or configure "
            "the Qualcomm AI Hub LLM path, and set SNAPMEMORY_LLM_PROVIDER=local_llm. "
            "See SNAPDRAGON_SETUP.md."
        )


def get_answerer():
    want_llm = os.environ.get("SNAPMEMORY_LLM_PROVIDER") == "local_llm"
    if want_llm:
        try:
            a = LocalLlmAnswerer()
            registry.register(ModelStatus(
                capability="llm", model_name="Local LLM", runtime="llama.cpp/ONNX",
                execution_provider="Unknown", installed=True))
            return a
        except RuntimeError as e:
            registry.register(ModelStatus(
                capability="llm", model_name="Local LLM", runtime="Not installed",
                execution_provider="Unavailable", installed=False, notes=str(e)))
    a = LocalExtractiveAnswerer()
    registry.register(ModelStatus(
        capability="llm", model_name="Extractive grounded answerer",
        runtime=a.name, execution_provider="CPU", installed=True,
        notes="No generative LLM configured; using grounded extractive fallback."))
    return a


_answerer = None


def answerer():
    global _answerer
    if _answerer is None:
        _answerer = get_answerer()
    return _answerer


def fetch_all_chunks(conn, source_type: str = None, source_id: int = None,
                      document_id: int = None, meeting_id: int = None, image_id: int = None):
    cur = conn.cursor()
    q = "SELECT id, source_type, source_id, text, page_number, slide_number, timestamp_seconds, embedding FROM chunks"
    clauses, params = [], []
    if source_type:
        clauses.append("source_type = ?")
        params.append(source_type)
    if document_id:
        clauses.append("source_type='document' AND source_id = ?")
        params.append(document_id)
    if meeting_id:
        clauses.append("source_type='meeting' AND source_id = ?")
        params.append(meeting_id)
    if image_id:
        clauses.append("source_type='image' AND source_id = ?")
        params.append(image_id)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    cur.execute(q, params)
    return cur.fetchall()


def _source_label(conn, source_type, source_id, page_number, slide_number, timestamp_seconds):
    cur = conn.cursor()
    if source_type == "document":
        cur.execute("SELECT filename FROM documents WHERE id=?", (source_id,))
        row = cur.fetchone()
        name = row[0] if row else "Unknown document"
        if page_number:
            return f"{name} — Page {page_number}"
        if slide_number:
            return f"{name} — Slide {slide_number}"
        return name
    if source_type == "meeting":
        cur.execute("SELECT filename FROM meetings WHERE id=?", (source_id,))
        row = cur.fetchone()
        name = row[0] if row else "Unknown meeting"
        if timestamp_seconds is not None:
            m, s = divmod(int(timestamp_seconds), 60)
            return f"{name} — {m:02d}:{s:02d}"
        return name
    if source_type == "image":
        cur.execute("SELECT filename FROM images WHERE id=?", (source_id,))
        row = cur.fetchone()
        name = row[0] if row else "Unknown image"
        return name
    return "Unknown source"


def retrieve(conn, question: str, top_k: int = None, similarity_threshold: float = None,
             filters: dict | None = None):
    """Hybrid retrieval: TF-IDF cosine similarity + keyword overlap boost."""
    top_k = top_k or config.DEFAULT_TOP_K
    similarity_threshold = (similarity_threshold if similarity_threshold is not None
                             else config.DEFAULT_SIMILARITY_THRESHOLD)
    filters = filters or {}

    rows = fetch_all_chunks(conn,
                             source_type=filters.get("source_type"),
                             document_id=filters.get("document_id"),
                             meeting_id=filters.get("meeting_id"),
                             image_id=filters.get("image_id"))
    if not rows:
        return []

    texts = [r[3] for r in rows]
    embed_matrix = np.array([
        np.frombuffer(r[7], dtype=np.float64) if r[7] else np.zeros(1)
        for r in rows
    ], dtype=object)

    # Normalize to a proper matrix (handle ragged/empty rows defensively)
    dims = [e.shape[0] for e in embed_matrix]
    max_dim = max(dims) if dims else 0
    mat = np.zeros((len(rows), max_dim))
    for i, e in enumerate(embed_matrix):
        mat[i, :e.shape[0]] = e

    q_vec = embeddings.embed_query(question)
    if q_vec.shape[0] != max_dim:
        padded = np.zeros(max_dim)
        padded[:min(max_dim, q_vec.shape[0])] = q_vec[:max_dim]
        q_vec = padded

    sims = embeddings.similarity(q_vec, mat)

    q_words = set(re.findall(r"[a-zA-Z]{3,}", question.lower()))
    scored = []
    for i, row in enumerate(rows):
        chunk_id, source_type, source_id, text, page_number, slide_number, ts, _emb = row
        keyword_overlap = len(q_words & set(re.findall(r"[a-zA-Z]{3,}", text.lower())))
        keyword_score = min(keyword_overlap / max(len(q_words), 1), 1.0)
        combined = 0.7 * float(sims[i]) + 0.3 * keyword_score
        scored.append((combined, row))

    scored.sort(key=lambda t: -t[0])

    results = []
    for score, row in scored[:top_k]:
        if score < similarity_threshold and len(results) > 0:
            continue
        chunk_id, source_type, source_id, text, page_number, slide_number, ts, _emb = row
        label = _source_label(conn, source_type, source_id, page_number, slide_number, ts)
        results.append({
            "citation_id": chunk_id,
            "source_type": source_type,
            "source_id": source_id,
            "text": text,
            "page_number": page_number,
            "slide_number": slide_number,
            "timestamp_seconds": ts,
            "label": label,
            "relevance": round(float(score), 4),
        })
    return results


def ask(conn, question: str, top_k: int = None, filters: dict | None = None) -> dict:
    t0 = time.time()
    chunks = retrieve(conn, question, top_k=top_k, filters=filters)
    answer_text = answerer().answer(question, chunks)
    latency_ms = (time.time() - t0) * 1000

    citations = [{
        "id": c["citation_id"],
        "label": c["label"],
        "source_type": c["source_type"],
        "source_id": c["source_id"],
        "page_number": c["page_number"],
        "slide_number": c["slide_number"],
        "timestamp_seconds": c["timestamp_seconds"],
        "relevance": c["relevance"],
        "excerpt": c["text"][:280],
    } for c in chunks]

    llm_status = registry.status_for("llm") or {}

    conn.execute(
        "INSERT INTO queries (question, answer, citations, latency_ms, model_used, execution_provider, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (question, answer_text, json.dumps(citations), latency_ms,
         llm_status.get("model_name", "unknown"), llm_status.get("execution_provider", "unknown"),
         time.time()),
    )
    conn.commit()

    return {
        "answer": answer_text,
        "citations": citations,
        "latency_ms": round(latency_ms, 1),
        "model_used": llm_status.get("model_name", "unknown"),
        "execution_provider": llm_status.get("execution_provider", "unknown"),
        "chunks_retrieved": len(chunks),
    }
