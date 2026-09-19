# ARCHITECTURE.md

## Overview

```
                     ┌─────────────────────────────┐
                     │        Browser UI            │
                     │  static/index.html + app.js   │
                     └───────────────┬───────────────┘
                                     │ fetch() JSON
                     ┌───────────────▼───────────────┐
                     │        Flask app (app.py)      │
                     │   API routes, request/response  │
                     └───────┬───────────────┬────────┘
             ┌───────────────┘               └────────────────┐
   ┌─────────▼──────────┐                          ┌───────────▼────────────┐
   │   Ingestion layer    │                          │      AI layer          │
   │ ingestion/documents.py│                         │ ai/embeddings.py        │
   │ (PDF/PPTX/TXT/MD)     │                         │ ai/rag.py                │
   │ ai/vision.py (OCR)     │                        │ ai/transcription.py      │
   │                        │                        │ ai/meeting_intelligence  │
   └───────────┬────────────┘                        │ ai/providers.py (device) │
               │                                      └───────────┬─────────────┘
               │                                                  │
               └─────────────────────┬────────────────────────────┘
                                     │
                       ┌─────────────▼──────────────┐
                       │   db/database.py (SQLite)    │
                       │  documents, meetings, images,  │
                       │  chunks, queries, audit_log,    │
                       │  benchmarks                      │
                       └─────────────┬──────────────┘
                                     │
                       ┌─────────────▼──────────────┐
                       │   core/privacy.py (audit)    │
                       │   core/benchmark.py           │
                       └────────────────────────────┘
```

## Data flow: importing a document

1. `POST /api/documents/upload` receives the file.
2. `ingestion/documents.py::validate_file` checks extension, size, non-empty, sanitizes the
   filename against path traversal.
3. `core/hashing.py::hash_bytes` computes a SHA-256 hash for duplicate detection against the
   `documents.file_hash` UNIQUE constraint.
4. `extract_and_chunk` dispatches to `extract_pdf` (pdfplumber, falling back to pypdf on
   malformed files), `extract_pptx` (python-pptx, including table cell text), or plain-text
   read for TXT/MD — each returns `(text, page_or_slide_number)` pairs, then `chunk_text`
   slides a sentence-aware window over each page/slide's text.
5. Each chunk is inserted into `chunks` with `source_type='document'`, `source_id`, and its
   page/slide number preserved for citation purposes.
6. `refit_embeddings()` (in `app.py`) refits the TF-IDF vectorizer over the *entire* corpus
   (all chunks across all documents/meetings/images) and re-embeds every chunk. This is
   simple and correct but O(corpus size) per import — see "Scaling limitations" below.
7. `core/privacy.py::log_event` records a `file_imported` audit event.

## Data flow: asking a question

1. `POST /api/ask` → `ai/rag.py::ask()`.
2. `retrieve()` embeds the query with the same TF-IDF vectorizer, computes cosine similarity
   against every chunk's stored embedding, blends it 70/30 with a keyword-overlap score (this
   hybrid approach compensates for TF-IDF's weakness at paraphrase/semantic matching), and
   returns the top-K chunks above a similarity floor.
3. The configured answerer (`LocalExtractiveAnswerer` by default) builds an answer using only
   sentences drawn from those chunks — it cannot introduce outside information because it has
   no generative capability, only selection.
4. Citations are built directly from the same chunk objects `retrieve()` returned — there is
   no separate "citation generation" step that could drift from what was actually retrieved.
5. The query, answer, citations, latency, and model/execution-provider are logged to the
   `queries` table and to the audit log.

## Why SQLite + BLOB embeddings instead of a separate vector database

The build spec allows LanceDB, Chroma, or FAISS. This implementation stores each chunk's
embedding vector as a serialized `float64` BLOB in the same `chunks` row as its text and
metadata, in the same SQLite file as everything else. Rationale:

- **Single portable file.** The entire memory store — metadata, text, and vectors — is one
  `snapmemory.db` file, which makes "Export Memory" / "Import Memory" (backup/restore) a
  simple file copy rather than a multi-store synchronization problem.
- **No additional service or index-persistence format to keep in sync** with the SQL metadata.
- **Honest about the tradeoff:** at corpus sizes beyond roughly tens of thousands of chunks, a
  brute-force `cosine_similarity` over a dense NumPy matrix (what `ai/embeddings.py::similarity`
  does) will become the bottleneck. A production-scale version would either (a) swap in
  LanceDB/FAISS behind the same `retrieve()` function signature, or (b) add an approximate
  nearest-neighbor index (e.g. `faiss.IndexHNSWFlat`) computed alongside the SQLite writes.
  Because `ai/rag.py::retrieve()` is the only caller of the embedding/similarity functions,
  this swap does not require touching the ingestion pipeline or the API layer.

## Development mode vs. Snapdragon production mode

Both modes run the exact same application code. What differs is which concrete provider class
`ai/providers.py`'s registry resolves to for each capability:

| Capability | Development mode (this build) | Snapdragon production mode |
|---|---|---|
| Embeddings | `TfidfEmbeddingProvider` (scikit-learn, CPU) | `OnnxEmbeddingProvider` (Qualcomm AI Hub model via QNN) |
| Speech-to-text | Unavailable, or `FasterWhisperProvider` if installed | `QualcommWhisperProvider` (AI Hub Whisper via QNN) |
| Vision/OCR | `TesseractOcrProvider` | `QualcommVisionProvider` (AI Hub model) or Tesseract |
| Answer generation | `LocalExtractiveAnswerer` (grounded, non-generative) | `LocalLlmAnswerer` (local LLM, generative) |

The active mode for each capability is always visible in the Performance tab (`GET
/api/models`), which reports `installed`, `runtime`, and `execution_provider` per capability —
this is how a judge or user can verify, at a glance, exactly what's really running.

## Privacy layer

Every filesystem/model/network-touching action calls `core/privacy.py::log_event`, which
writes one row to `audit_log`. `get_privacy_summary()` computes every number shown in the
Privacy Center via `SELECT COUNT(*) ... WHERE event_type=...` — there is no hard-coded value
anywhere in that code path. `cloud_api_calls` counts `network_request` events, which nothing
in the core system currently emits (there is no cloud call site to emit one from).

## Scaling limitations (disclosed, not hidden)

- Full-corpus TF-IDF refit on every import is O(n) in total corpus size. Fine for a
  hackathon-scale demo (dozens to low hundreds of documents); would need an incremental /
  hashing vectorizer for a large personal archive.
- Brute-force cosine similarity over all chunks on every query. Fine up to tens of thousands
  of chunks; would need an ANN index beyond that (see above).
- Meeting intelligence is regex/heuristic-based, not LLM-based (see `ai/meeting_intelligence.py`
  docstring and `LIMITATIONS.md`) — it will miss decisions/action items phrased in ways its
  patterns don't cover, though it will also never invent ones that aren't there.
