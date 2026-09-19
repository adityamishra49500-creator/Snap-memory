# LIMITATIONS.md

This document exists because the build spec explicitly requires never fabricating capabilities.
Here is the complete, honest list of what SnapMemory does *not* do out of the box, and exactly
why, per the rule that every user-facing claim must correspond to actual application behavior.

## 1. Embeddings are TF-IDF, not a neural model, by default

**Why:** the authoring environment had no internet access to download a sentence-transformer
or Qualcomm AI Hub embedding model.

**Effect:** retrieval is good at exact keyword/term overlap, weaker at paraphrase ("What did we
decide about login?" may not match "authentication" as well as a neural embedding would).
Mitigated partially by hybrid scoring (TF-IDF cosine + keyword overlap) in `ai/rag.py`.

**Fix:** configure `SNAPMEMORY_EMBEDDING_PROVIDER=onnx` with a real model per
`SNAPDRAGON_SETUP.md`. No other code changes required.

## 2. Answer generation is extractive, not generative

**Why:** no local LLM runtime (no torch/transformers, no llama.cpp, no network to fetch GGUF
weights) was available in the sandbox.

**Effect:** answers are built by selecting and lightly stitching the most relevant sentences
from retrieved chunks, rather than fluently synthesized prose. This is *more* conservative
than a generative LLM (it cannot hallucinate facts not present in the source), but reads less
naturally.

**Fix:** implement `LocalLlmAnswerer` in `ai/rag.py` and set `SNAPMEMORY_LLM_PROVIDER=local_llm`.

## 3. Meeting intelligence is rule-based, not LLM-based

**Why:** same LLM-availability constraint as above.

**Effect:** `ai/meeting_intelligence.py` uses regex/heuristics to find decisions ("we decided…",
"let's go with…"), action items (Name + verb pattern), dates, and people. It will miss items
phrased in ways its patterns don't anticipate. It is tested (see `tests/test_meeting_intelligence.py`)
to never invent a decision, name, or date that isn't literally in the transcript.

**Fix:** route the transcript through a configured local LLM with a structured-extraction
prompt once one is available (see `SNAPDRAGON_SETUP.md` section 5).

## 4. Audio transcription requires an install step

**Why:** no `faster-whisper`/`torch`/model weights available in the sandbox; nothing was faked.

**Effect:** uploading audio without a configured backend returns a clear
`"No speech-to-text backend is installed"` message and status `transcription_unavailable` — it
does **not** silently fail or return an empty/fake transcript. Verified live during development
(see conversation log / `TROUBLESHOOTING.md`).

**Fix:** `pip install faster-whisper` (CPU/dev) or configure the Qualcomm AI Hub Whisper model
(Snapdragon production).

## 5. No verified NPU execution in this build

**Why:** the authoring machine is x86_64 Linux with no Qualcomm hardware or QNN execution
provider available.

**Effect:** the Performance tab and `/api/models` correctly report `execution_provider: "CPU"`
and `npu_provider_detected: null` throughout this build's testing.

**Fix:** on the actual Snapdragon HP device with `onnxruntime-qnn` installed and a real AI Hub
model configured, `ai/providers.py::detect_device()` will detect and report the NPU
automatically — no code change needed, only the environment.

## 6. Scaling

TF-IDF refit is O(corpus size) per import; retrieval is brute-force cosine similarity over all
chunks. Fine for a hackathon-scale demo (tens to low hundreds of documents/chunks — tested up
to dozens of chunks live). Would need an incremental vectorizer and/or an ANN index (FAISS/
LanceDB) for a large personal archive. See `ARCHITECTURE.md`.

## 7. PDF OCR is not wired in

Scanned/image-only PDFs (no text layer) will fail extraction with a clear error rather than
silently returning empty content. Image OCR (via Tesseract) is available for standalone image
files but not yet chained into the PDF extraction path.

## 8. Single-user, single-machine

No authentication, no multi-user support, no encryption-at-rest for the SQLite file beyond
normal OS file permissions. This matches the build spec's "local-first personal memory"
framing but is worth stating explicitly.
