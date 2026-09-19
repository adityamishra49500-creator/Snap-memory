"""
Real, measured performance benchmarks. Nothing here is a made-up number —
every value is timed on this machine, right now, against whatever chunks
actually exist in the local memory store.
"""
import time
import json
import numpy as np

from ai import embeddings, rag
from ai.providers import registry


def run_benchmark(conn) -> dict:
    results = {}

    # 1. Embedding throughput on a fixed sample text
    sample_texts = [f"Benchmark sample sentence number {i} about SnapMemory performance." for i in range(50)]
    t0 = time.time()
    embeddings.provider()  # ensure loaded
    if embeddings.provider().vectorizer is None:
        embeddings.refit_corpus(sample_texts)
    mat = embeddings.embed_texts(sample_texts)
    t1 = time.time()
    embed_ms = (t1 - t0) * 1000
    results["embedding_throughput"] = {
        "metric": "texts_per_second",
        "value": round(len(sample_texts) / max(t1 - t0, 1e-6), 2),
        "unit": "texts/sec",
        "raw_ms_for_50_texts": round(embed_ms, 2),
    }

    # 2. Retrieval latency against the real corpus
    t0 = time.time()
    chunks = rag.retrieve(conn, "What are the important decisions and deadlines?", top_k=5)
    t1 = time.time()
    results["retrieval_latency"] = {
        "metric": "ms",
        "value": round((t1 - t0) * 1000, 2),
        "chunks_in_corpus": _count_chunks(conn),
        "chunks_returned": len(chunks),
    }

    # 3. Full ask() round trip (retrieval + answer generation)
    t0 = time.time()
    result = rag.ask(conn, "Summarize what is stored in memory.", top_k=5)
    t1 = time.time()
    results["end_to_end_query_latency"] = {
        "metric": "ms",
        "value": round((t1 - t0) * 1000, 2),
        "model_used": result["model_used"],
        "execution_provider": result["execution_provider"],
    }

    # 4. Document indexing throughput estimate (chars/sec) using chunking only
    from ingestion.documents import chunk_text
    big_text = ("SnapMemory keeps your data on device. " * 4000)
    t0 = time.time()
    chunks_out = chunk_text(big_text)
    t1 = time.time()
    results["chunking_throughput"] = {
        "metric": "chars_per_second",
        "value": round(len(big_text) / max(t1 - t0, 1e-6), 2),
        "chunks_produced": len(chunks_out),
    }

    results["device"] = registry.device.__dict__
    results["model_statuses"] = registry.all_statuses()
    results["measured_at"] = time.time()

    for name, data in results.items():
        if isinstance(data, dict) and "value" in data:
            conn.execute(
                "INSERT INTO benchmarks (name, metric, value, unit, provider, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, data.get("metric", ""), float(data["value"]), data.get("unit", ""),
                 result.get("execution_provider", "") if name == "end_to_end_query_latency" else "", time.time()),
            )
    conn.commit()
    return results


def _count_chunks(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chunks")
    return cur.fetchone()[0]


def history(conn, limit=50):
    cur = conn.cursor()
    cur.execute("SELECT name, metric, value, unit, provider, created_at FROM benchmarks ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    return [
        {"name": n, "metric": m, "value": v, "unit": u, "provider": p, "created_at": c}
        for n, m, v, u, p, c in rows
    ]
