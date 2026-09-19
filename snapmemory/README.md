# SnapMemory

**Your private AI memory. Entirely on-device.**
*"Remember everything. Share nothing."*

Built for the **Snapdragon AI Lab Build & Present Challenge**.

---

## The problem

Information about what a team decided, who owns what, and when things are due is scattered
across meetings, PDFs, slide decks, and screenshots. Finding it again usually means either
digging through search history yourself, or sending that information to a cloud AI service.

## The solution

SnapMemory turns a Snapdragon-powered PC into a private, searchable AI memory. Import
documents, meeting recordings, and screenshots; ask natural-language questions; get grounded
answers with clickable source citations — with **zero data leaving the device** for the core
product to work.

## What actually works right now (tested, not aspirational)

| Feature | Status |
|---|---|
| PDF / PPTX / TXT / MD ingestion + chunking + metadata | ✅ Working |
| Image OCR (screenshots, photos) via Tesseract | ✅ Working |
| Local TF-IDF embedding + hybrid semantic/keyword retrieval | ✅ Working |
| Grounded RAG answers with source citations (page/slide/timestamp) | ✅ Working |
| Meeting intelligence (summary, decisions, action items, dates, people) | ✅ Working (rule-based extractor, see limitations) |
| Privacy Center with real audit-log-backed counters | ✅ Working |
| Performance benchmark with real measured timings | ✅ Working |
| Duplicate detection, delete, export/import backup | ✅ Working |
| Command palette (⌘K), drag-and-drop, demo mode | ✅ Working |
| Audio transcription (Whisper) | ⚠️ Requires `faster-whisper` install or Qualcomm AI Hub Whisper model — reports itself as unavailable rather than faking it (see Limitations) |
| Qualcomm AI Hub / NPU acceleration | ⚠️ Provider abstraction is built and wired in; requires the actual AI Hub models + Snapdragon hardware to activate — see `SNAPDRAGON_SETUP.md` |

## Why it's built this way

This project was authored in a sandboxed environment with **no internet access**, so no model
weights (transformer embeddings, Whisper, a local LLM, Qualcomm AI Hub models) could be
downloaded during development. Rather than fake those capabilities, SnapMemory:

1. Ships **real, working local fallbacks** for every capability (TF-IDF embeddings, an
   extractive grounded answerer, Tesseract OCR) that run with zero downloads and zero internet.
2. Has a clean **provider abstraction layer** (`ai/providers.py`, `ai/embeddings.py`,
   `ai/rag.py`, `ai/transcription.py`, `ai/vision.py`) so a real Qualcomm AI Hub model or local
   LLM can be dropped in on your actual Snapdragon hardware with **no other code changes**.
3. **Never claims NPU execution it hasn't verified.** The Performance page queries
   `onnxruntime.get_available_providers()` and only reports "NPU" if a
   `QNNExecutionProvider`/`QualcommExecutionProvider` is actually present. On a normal
   dev machine it correctly says "not detected."

See `LIMITATIONS.md` for the full, honest list of what needs your Snapdragon device + internet
to light up, and `SNAPDRAGON_SETUP.md` for exactly how to wire it in.

## Architecture at a glance

```
FILE (PDF/PPTX/TXT/MD/image/audio)
   → validation → extraction → cleaning → chunking → metadata
   → embedding (TF-IDF local, or Qualcomm AI Hub ONNX if configured)
   → SQLite (metadata + chunks + serialized embedding vectors)

QUESTION
   → embed query → cosine similarity + keyword hybrid retrieval
   → rerank → top-K chunks → grounded answerer → cited answer
```

See `ARCHITECTURE.md` for the full breakdown.

## Quick start (development / any machine)

```bash
cd snapmemory
pip install -r requirements.txt      # core deps only — no model downloads required
python run.py
```

Open **http://127.0.0.1:5057**. Click **"Load Demo Data"** in the top bar to populate the app
with a small, clearly-synthetic sample dataset (a proposal doc, a roadmap doc, an architecture
slide deck, a screenshot, and a meeting transcript) so you can try every feature immediately.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Project structure

```
snapmemory/
  app.py                    Flask app + all API routes
  run.py                    Entry point
  ai/
    providers.py             Device/NPU detection + provider registry
    embeddings.py            TF-IDF local embedding engine (+ ONNX hook)
    rag.py                   Retrieval + grounded answer generation + citations
    transcription.py         Whisper provider abstraction
    vision.py                OCR provider abstraction
    meeting_intelligence.py  Rule-based transcript extraction
  db/
    database.py               SQLite schema + connection management
  ingestion/
    documents.py              PDF/PPTX/TXT/MD extraction + chunking
  core/
    config.py, hashing.py, privacy.py, benchmark.py
  static/                    Frontend (HTML/CSS/JS, no build step)
  demo/                      Synthetic demo dataset + seeding
  tests/                     24 unit tests (all passing)
  docs: SETUP.md, SNAPDRAGON_SETUP.md, ARCHITECTURE.md, BENCHMARKS.md,
        DEMO.md, TROUBLESHOOTING.md, LIMITATIONS.md
```

## Privacy architecture

- No OpenAI / Gemini / Anthropic / other cloud API calls in the core system.
- No external vector database, no external file storage.
- Every file stays on disk in `data/files/`; every action is logged to `audit_log` in SQLite.
- The Privacy Center reads those logs directly — the "Cloud API calls: 0" you see is a live
  `COUNT(*)` query, not a hard-coded label.
- A cloud fallback path is deliberately **not wired in**. `SNAPMEMORY_ALLOW_CLOUD_FALLBACK` exists
  as a flag for future opt-in development convenience only; nothing in the app currently uses it.

## Known limitations

See `LIMITATIONS.md`. Short version: real neural embeddings, Whisper transcription, a
generative local LLM, and NPU execution all need either an internet connection (to fetch
models) or the actual Snapdragon hardware + Qualcomm AI Hub SDK — none of which were available
in the authoring sandbox. The app is architected so none of that requires touching application
code, only configuring an environment variable and dropping in a model file.

## Future improvements

- Swap TF-IDF for a real sentence-embedding model (via Qualcomm AI Hub ONNX export)
- Wire in a local LLM for generative (vs. extractive) answers
- Incremental/streaming embedding refit instead of full-corpus refit on each import
- Multi-user support / encrypted-at-rest local database
